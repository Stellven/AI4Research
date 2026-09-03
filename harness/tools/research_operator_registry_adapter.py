#!/usr/bin/env python3
"""Execute a frozen research-registry operator through its typed worker boundary."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


HARNESS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS_DIR.parent
RUN_DIR = Path(
    os.environ.get("SOLAR_MULTI_TASK_RUN_DIR")
    or HARNESS_DIR / "run" / "multi-task"
)
OPERATOR_LEASE_DIR = Path(
    os.environ.get("SOLAR_OPERATOR_LEASE_DIR")
    or HARNESS_DIR / "run" / "operator-leases"
)
SPRINTS_DIR = Path(
    os.environ.get("SPRINTS_DIR")
    or os.environ.get("HARNESS_SPRINTS_DIR")
    or HARNESS_DIR / "sprints"
)
for entry in (str(HARNESS_DIR / "lib"), str(HARNESS_DIR), str(REPO_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from physical_operator_worker import run_physical_operator  # noqa: E402
from research_orchestration.runtime import default_production_resolver  # noqa: E402
# Import the service through the same canonical package identity used by
# ``default_production_resolver``.  Loading the service as ``plugins.*`` while
# the action registry is loaded as ``harness.plugins.*`` creates two distinct
# ResearchOperatorError classes, so typed provider failures are accidentally
# reclassified as operator_internal_error at the package boundary.
from harness.plugins.autosci.services.codex_research import (  # noqa: E402
    CodexResearchModelService,
)
import model_registry  # noqa: E402
import scheduler_input  # noqa: E402


class RegistryAdapterError(ValueError):
    """A fail-closed registry dispatch error."""


_ALLOWED_REGISTRIES = {
    "plugins.autosci.operators.scientific_lifecycle.evidence.registry": "operator_id",
    "plugins.autosci.operators.scientific_lifecycle.registry": "implementation_operator_id",
}
_NODE_INPUT_PAYLOAD_KEYS = {
    "literature_discover": {},
    "discovery_ingest": {
        "literature_discovery.v1": "discovery_evidence",
    },
    "source_assess": {
        "literature_discovery.v1": "discovery_evidence",
        "research_paper.v1": "paper_evidence",
    },
    "paper_analyze": {
        "research_paper.v1": "paper_evidence",
    },
    "claim_extract": {
        "research_paper.v1": "paper_evidence",
    },
    "claim_select_one": {
        "research_paper.v1": "paper_evidence",
    },
    "method_extract": {
        "research_paper.v1": "research_paper",
    },
    "dataset_prepare": {
        "research_claims.v1": "research_claims",
    },
    "idea_evaluate": {
        "idea_candidate.v1": "idea_candidate",
    },
    "experiment_design": {
        "idea_candidate.v1": "idea_candidate",
        "research_claims.v1": "research_claims",
        "dataset_manifest.v1": "dataset_manifest",
    },
    "experiment_approval_gate": {
        "experiment_plan.v1": "experiment_plan",
    },
    "experiment_run": {
        "experiment_plan.v1": "experiment_plan",
        "experiment_approval.v1": "experiment_approval",
    },
    "experiment_monitor": {
        "experiment_plan.v1": "experiment_plan",
        "experiment_result.v1": "experiment_result",
    },
    "claim_verify": {
        "research_claims.v1": "claims",
        "research_paper.v1": "research_paper",
        "experiment_result.v1": "experiment_result",
        "code_evidence_map.v1": "code_evidence_map",
    },
    "memory_update_initial": {
        "research_paper.v1": "paper_evidence",
        "claim_verdict.v1": "verdict_evidence",
        "research_method.v1": "research_method",
        "research_source_assessment.v1": "source_assessment",
        "scientific_report_plan.v1": "report_plan",
        "scientific_report.v1": "report_evidence",
    },
    "report_plan": {
        "requirement_ir.v1": "requirement_ir",
        "claim_verdict.v1": "verdicts",
        "literature_discovery.v1": "literature_discovery",
        "research_method.v1": "research_method",
        "research_source_assessment.v1": "source_assessment",
        "experiment_plan.v1": "experiment_plan",
        "experiment_result.v1": "experiment_result",
    },
    "report_draft": {
        "scientific_report_plan.v1": "report_plan",
        "scientific_report_plan_review.v1": "report_plan_review",
        "claim_verdict.v1": "verdicts",
        "research_method.v1": "research_method",
        "research_source_assessment.v1": "source_assessment",
        "experiment_plan.v1": "experiment_plan",
        "experiment_result.v1": "experiment_result",
    },
    "artifact_review": {
        "scientific_report_plan.v1": "report_plan",
        "scientific_report.v1": "report",
    },
    "publication_produce": {
        "requirement_ir.v1": "requirement_ir",
        "scientific_report.v1": "report",
    },
}
_MULTI_DOCUMENT_PAYLOAD_NODES = {"claim_verify"}


def _registry_node_kind(node: dict[str, Any]) -> str:
    candidates = [item for item in node.get("physical_candidates") or [] if isinstance(item, dict)]
    for candidate in candidates:
        binding = candidate.get("runtime_binding") if isinstance(candidate.get("runtime_binding"), dict) else {}
        node_id = str(binding.get("node_id") or "")
        if node_id:
            return node_id
    binding = node.get("runtime_binding") if isinstance(node.get("runtime_binding"), dict) else {}
    return str(binding.get("node_id") or "")


def _experiment_run_write_scope(graph: dict[str, Any]) -> list[str]:
    matches = [
        [str(value) for value in item.get("write_scope") or [] if str(value).strip()]
        for item in graph.get("nodes") or []
        if isinstance(item, dict) and _registry_node_kind(item) == "experiment_run"
    ]
    matches = [values for values in matches if values]
    if len(matches) != 1:
        return []
    return matches[0]


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryAdapterError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RegistryAdapterError(f"{label} must be a JSON object: {path}")
    return payload


def _runtime_execution_snapshot(
    graph: dict[str, Any], envelope: dict[str, Any]
) -> dict[str, Any]:
    """Capture the mutable node ledger without changing frozen graph authority."""

    graph_path = Path(str(envelope.get("graph_path") or "")).resolve()
    state_path = graph_path.with_name(f"{graph_path.stem}_state.json")
    if not state_path.is_file():
        return {
            "schema": "solar.publication_execution_snapshot.v1",
            "availability": "unavailable",
            "reason": "task_graph_state_missing_at_operator_dispatch",
            "graph_path": str(graph_path),
            "state_path": str(state_path),
            "closure_status": "pending_scheduler_closure",
            "nodes": [],
        }
    raw = state_path.read_bytes()
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegistryAdapterError(
            f"task graph state is not readable JSON: {state_path}"
        ) from exc
    if not isinstance(state, dict):
        raise RegistryAdapterError(f"task graph state must be an object: {state_path}")
    graph_sprint_id = str(graph.get("sprint_id") or "")
    state_sprint_id = str(state.get("sprint_id") or "")
    if state_sprint_id != graph_sprint_id:
        raise RegistryAdapterError("task graph state sprint_id does not match frozen graph")
    state_nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    nodes: list[dict[str, Any]] = []
    for item in graph.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or item.get("node_id") or "")
        observed = state_nodes.get(node_id) if isinstance(state_nodes.get(node_id), dict) else {}
        status = str(observed.get("status") or "").strip()
        if not node_id or not status:
            raise RegistryAdapterError(
                f"task graph state is missing runtime status for frozen node: {node_id or '<empty>'}"
            )
        nodes.append(
            {
                "node_id": node_id,
                "status": status,
                "attempt": int(observed.get("attempt") or 0),
                "blocked_by": [
                    str(value) for value in observed.get("blocked_by") or []
                ],
                "is_current_node": node_id == str(envelope.get("node_id") or ""),
            }
        )
    return {
        "schema": "solar.publication_execution_snapshot.v1",
        "availability": "available",
        "captured_from_state_updated_at": str(state.get("updated_at") or ""),
        "state_revision": int(state.get("revision") or 0),
        "state_sha256": hashlib.sha256(raw).hexdigest(),
        "graph_path": str(graph_path),
        "state_path": str(state_path),
        "run_status": str(state.get("run_status") or ""),
        "closure_status": "pending_scheduler_closure",
        "nodes": nodes,
    }


def _expected_schema(contract_value: str) -> str:
    name = Path(str(contract_value).replace("schema:", "")).name
    return name.removesuffix(".schema.json")


def _resolved_path(value: Any, *, label: str, strict: bool = False) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise RegistryAdapterError(f"{label} is missing")
    try:
        return Path(raw).expanduser().resolve(strict=strict)
    except OSError as exc:
        raise RegistryAdapterError(f"{label} is not a valid path: {raw}") from exc


def _require_within(path: Path, root: Path, *, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RegistryAdapterError(f"{label} escapes scheduler runtime_work_dir") from exc


def _verified_dispatch_authority(
    envelope: dict[str, Any],
    *,
    configured_binding: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    graph_path = _resolved_path(envelope.get("graph_path"), label="graph_path", strict=True)
    runtime_root = graph_path.parent
    graph = _read_object(graph_path, label="runtime graph")
    verification = scheduler_input.verify_runtime_projection(graph, graph_path=graph_path)
    if not verification.get("ok"):
        errors = ",".join(str(item) for item in verification.get("errors") or [])
        raise RegistryAdapterError(f"runtime graph verification failed: {errors or 'unknown'}")

    sprint_id = str(graph.get("sprint_id") or "")
    node_id = str(envelope.get("node_id") or "")
    expected_graph_path = runtime_root / f"{sprint_id}.task_graph.json"
    work_dir = _resolved_path(graph.get("runtime_work_dir"), label="runtime_work_dir", strict=True)
    expected_work_dir = runtime_root / sprint_id / "workdir"
    if graph_path != expected_graph_path or work_dir != expected_work_dir.resolve():
        raise RegistryAdapterError("graph_path and runtime_work_dir do not match the scheduler projection layout")
    if _resolved_path(envelope.get("work_dir"), label="work_dir", strict=True) != work_dir:
        raise RegistryAdapterError("envelope work_dir does not match the verified runtime graph")
    if str(envelope.get("sprint_id") or "") != sprint_id:
        raise RegistryAdapterError("envelope sprint_id does not match the verified runtime graph")

    matching = [
        item for item in graph.get("nodes") or []
        if isinstance(item, dict) and str(item.get("id") or "") == node_id
    ]
    if len(matching) != 1:
        raise RegistryAdapterError(f"envelope node_id is not unique in the verified runtime graph: {node_id}")
    node = matching[0]
    operator_id = str(envelope.get("operator_id") or "")
    candidates = [item for item in node.get("physical_candidates") or [] if isinstance(item, dict)]
    selected = [item for item in candidates if str(item.get("operator_id") or "") == operator_id]
    if len(selected) != 1:
        raise RegistryAdapterError("envelope operator_id is not a frozen physical candidate for the graph node")
    supplied_rank = envelope.get("physical_candidate_rank")
    if supplied_rank is not None and supplied_rank != selected[0].get("rank"):
        raise RegistryAdapterError("envelope physical_candidate_rank does not match the frozen graph node")

    exact_fields = {
        "artifact_contract": node.get("artifact_contract") or {},
        "artifact_routes": node.get("artifact_routes") or {},
        "capsule_binding": node.get("capsule_binding") or {},
        "resource_requirements": node.get("resource_requirements") or {},
        "write_scope": node.get("write_scope") or [],
    }
    for field, expected in exact_fields.items():
        if envelope.get(field) != expected:
            raise RegistryAdapterError(f"envelope {field} does not match the frozen graph node")
    if envelope.get("runtime_binding") != configured_binding:
        raise RegistryAdapterError("envelope runtime_binding does not match the configured operator")

    routes = node.get("artifact_routes") if isinstance(node.get("artifact_routes"), dict) else {}
    input_bindings = (
        graph.get("runtime_input_bindings")
        if isinstance(graph.get("runtime_input_bindings"), dict)
        else {}
    )
    for route_kind in ("consumes", "produces"):
        route_map = routes.get(route_kind) if isinstance(routes.get(route_kind), dict) else {}
        for artifact_type, raw_route in route_map.items():
            if _expected_schema(str(artifact_type)) == "request-envelope":
                continue
            route = Path(str(raw_route))
            route = route if route.is_absolute() else work_dir / route
            resolved_route = route.resolve()
            if route_kind == "consumes" and not resolved_route.is_relative_to(work_dir):
                binding = input_bindings.get(str(artifact_type))
                bound_path = (
                    _resolved_path(binding.get("path"), label=f"runtime input {artifact_type}", strict=True)
                    if isinstance(binding, dict)
                    else None
                )
                if bound_path is None or resolved_route != bound_path:
                    raise RegistryAdapterError(
                        f"consumes route {artifact_type} is not an exact verified runtime input binding"
                    )
            else:
                _require_within(resolved_route, work_dir, label=f"{route_kind} route {artifact_type}")

    handoff_path = _resolved_path(envelope.get("handoff_path"), label="handoff_path")
    expected_handoff = runtime_root / f"{sprint_id}.{node_id}-handoff.md"
    if handoff_path != expected_handoff.resolve():
        raise RegistryAdapterError("handoff_path does not match the configured sprint/node handoff")
    return graph, node, work_dir, handoff_path


def _validated_binding(envelope: dict[str, Any]) -> dict[str, str]:
    operator_id = str(envelope.get("operator_id") or "").strip()
    operators = _read_object(
        HARNESS_DIR / "config" / "physical-operators.json",
        label="physical operator registry",
    ).get("operators")
    operator = operators.get(operator_id) if isinstance(operators, dict) else None
    if not isinstance(operator, dict) or str(operator.get("backend") or "") != "research_operator_registry":
        raise RegistryAdapterError(f"operator is not an admitted research registry operator: {operator_id or '<missing>'}")
    configured = operator.get("runtime_binding")
    supplied = envelope.get("runtime_binding")
    if not isinstance(configured, dict) or not isinstance(supplied, dict) or supplied != configured:
        raise RegistryAdapterError(f"runtime_binding does not match configured operator {operator_id}")
    registry_name = str(configured.get("registry") or "")
    implementation_key = _ALLOWED_REGISTRIES.get(registry_name)
    if implementation_key is None:
        raise RegistryAdapterError(f"research registry is not allowlisted: {registry_name or '<missing>'}")
    node_id = str(configured.get("node_id") or "")
    implementation_id = str(configured.get("implementation_operator_id") or "")
    if node_id not in _NODE_INPUT_PAYLOAD_KEYS or not implementation_id:
        raise RegistryAdapterError(f"research registry node is not allowlisted: {node_id or '<missing>'}")
    registry = importlib.import_module(registry_name)
    entries = registry.registration_entries()
    matches = [item for item in entries if str(item.get("node_id") or "") == node_id]
    implementation_matches = [
        item
        for item in matches
        if str(item.get(implementation_key) or "") == implementation_id
    ]
    # The unified scientific-lifecycle registry intentionally exposes both the
    # legacy synthesis implementation and the typed action implementation for
    # a few shared node names (for example ``report_draft``).  Node identity is
    # therefore not unique by itself; the frozen implementation identity is.
    if len(implementation_matches) != 1:
        raise RegistryAdapterError(
            f"configured implementation_operator_id is not registered for {registry_name}:{node_id}"
        )
    return {
        "operator_id": operator_id,
        "registry": registry_name,
        "node_id": node_id,
        "implementation_operator_id": implementation_id,
    }


def _document_identity(document: dict[str, Any]) -> str:
    schema = str(document.get("schema") or "").strip()
    if schema:
        return schema
    schema_version = str(document.get("schema_version") or "").strip()
    if schema_version.startswith("solar.requirement_ir."):
        return "requirement_ir.v1"
    return ""


def _document_matches_contract(document: dict[str, Any], expected: str) -> bool:
    return _document_identity(document) == expected


def _payload_for_documents(node_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    mapping = _NODE_INPUT_PAYLOAD_KEYS.get(node_id)
    if not isinstance(mapping, dict):
        raise RegistryAdapterError(f"research registry node is not allowlisted: {node_id or '<missing>'}")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        identity = _document_identity(document)
        payload_key = mapping.get(identity)
        if not payload_key:
            raise RegistryAdapterError(
                f"input artifact {identity or '<missing-schema>'} is not admitted for registry node {node_id}"
            )
        grouped.setdefault(payload_key, []).append(document)
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in sorted(grouped.items())
    }


def _inline_operator_payload(
    expected: dict[str, str], documents: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compatibility boundary for callers that already resolved a binding."""
    node_id = str(expected.get("node_id") or "")
    if not documents:
        raise RegistryAdapterError("no routed documents are available for registry dispatch")
    if node_id in _MULTI_DOCUMENT_PAYLOAD_NODES:
        mapping = _NODE_INPUT_PAYLOAD_KEYS.get(node_id) or {}
        payload_key = next(iter(mapping.values()), "")
        if not payload_key:
            raise RegistryAdapterError(
                f"research registry node is not allowlisted: {node_id or '<missing>'}"
            )
        return {payload_key: documents}
    return _payload_for_documents(node_id, documents)


def _explicit_report_title(
    node: dict[str, Any], documents: list[dict[str, Any]]
) -> str:
    """Resolve only an explicitly requested title from frozen RequirementIR.

    A report-planning node's goal describes *how to plan the report*; it is not
    the report title.  When the final report node quotes a project title, bind
    that exact quoted value only if the frozen RequirementIR also requires it.
    This avoids inventing a title or parsing arbitrary prose as routing truth.
    """

    goal = str(node.get("goal") or "")
    quoted = {
        value.strip()
        for value in re.findall(r'"([^"\n]+)"', goal)
        if value.strip()
    }
    for document in documents:
        if _document_identity(document) != "requirement_ir.v1":
            continue
        for requirement in document.get("requirements") or []:
            if not isinstance(requirement, dict):
                continue
            acceptance = (
                requirement.get("acceptance")
                if isinstance(requirement.get("acceptance"), dict)
                else {}
            )
            for value in acceptance.get("required_values") or []:
                candidate = str(value).strip()
                if candidate in quoted or (
                    candidate
                    and candidate.casefold() in goal.casefold()
                    and any(token in str(requirement.get("statement") or "").casefold() for token in ("title", "project name", "report name"))
                ):
                    return candidate
    return ""


def _report_title_from_frozen_context(
    graph: dict[str, Any], node: dict[str, Any], documents: list[dict[str, Any]]
) -> str:
    title = _explicit_report_title(node, documents)
    if title:
        return title

    bindings = (
        graph.get("runtime_input_bindings")
        if isinstance(graph.get("runtime_input_bindings"), dict)
        else {}
    )
    binding = bindings.get("requirement_ir.v1")
    if not isinstance(binding, dict):
        return ""
    path = _resolved_path(binding.get("path"), label="requirement_ir runtime input", strict=True)
    expected_hash = str(binding.get("sha256") or "").lower()
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if not expected_hash or actual_hash != expected_hash:
        raise RegistryAdapterError("requirement_ir runtime input hash does not match frozen binding")
    requirement_ir = _read_object(path, label="requirement_ir runtime input")

    # The planner and drafter may be separate nodes.  The final report node is
    # authoritative for an explicitly quoted title, while RequirementIR proves
    # the quoted value came from the accepted user request.
    candidates = [node]
    candidates.extend(
        item
        for item in graph.get("nodes") or []
        if isinstance(item, dict) and _registry_node_kind(item) == "report_draft"
    )
    for candidate_node in candidates:
        title = _explicit_report_title(candidate_node, [requirement_ir])
        if title:
            return title
    return ""


def _matching_input_documents(
    graph: dict[str, Any],
    node: dict[str, Any],
    work_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    contract = node.get("artifact_contract") if isinstance(node.get("artifact_contract"), dict) else {}
    routes = node.get("artifact_routes") if isinstance(node.get("artifact_routes"), dict) else {}
    consume_routes = routes.get("consumes") if isinstance(routes.get("consumes"), dict) else {}
    documents: list[dict[str, Any]] = []
    source_paths: list[str] = []
    input_bindings = (
        graph.get("runtime_input_bindings")
        if isinstance(graph.get("runtime_input_bindings"), dict)
        else {}
    )
    for artifact_type in contract.get("consumes") or []:
        expected = _expected_schema(str(artifact_type))
        raw_route = str(consume_routes.get(artifact_type) or "").strip()
        if not raw_route or expected in {"", "request-envelope"}:
            continue
        route = Path(raw_route)
        route = route if route.is_absolute() else work_dir / route
        candidates = [route] if route.is_file() else sorted(route.rglob("*.json")) if route.is_dir() else []
        matched = False
        for candidate in candidates:
            resolved_candidate = candidate.resolve()
            if not resolved_candidate.is_relative_to(work_dir):
                binding = input_bindings.get(str(artifact_type))
                bound_path = (
                    _resolved_path(binding.get("path"), label=f"runtime input {artifact_type}", strict=True)
                    if isinstance(binding, dict)
                    else None
                )
                if bound_path is None or resolved_candidate != bound_path:
                    raise RegistryAdapterError("consumed artifact is outside verified scheduler authority")
            try:
                document = _read_object(resolved_candidate, label="input artifact")
            except RegistryAdapterError:
                continue
            if not _document_matches_contract(document, expected):
                continue
            documents.append(document)
            source_paths.append(str(resolved_candidate))
            matched = True
        if not matched:
            raise RegistryAdapterError(
                f"no artifact matching frozen consume contract {artifact_type} was found"
            )
    return documents, source_paths


def _verified_workspace_sources(
    graph: dict[str, Any],
    node: dict[str, Any],
) -> list[dict[str, str]]:
    """Resolve only the exact hash-bound workspace files frozen for this node."""

    rows = [row for row in node.get("workspace_reads") or [] if isinstance(row, dict)]
    if not rows:
        return []
    authority = (
        graph.get("workspace_authority_ref")
        if isinstance(graph.get("workspace_authority_ref"), dict)
        else {}
    )
    root = _resolved_path(
        authority.get("workspace_root"), label="workspace authority root", strict=True
    )
    if not root.is_dir() or root.is_symlink():
        raise RegistryAdapterError("workspace authority root is unavailable or unsafe")
    declared_scope = {str(value) for value in node.get("read_scope") or []}
    result: list[dict[str, str]] = []
    for row in rows:
        relative = str(row.get("relative_path") or "")
        relative_path = Path(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        ):
            raise RegistryAdapterError("workspace source path is not a safe relative file")
        cursor = root
        for part in relative_path.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise RegistryAdapterError(f"workspace source contains a symlink: {relative}")
        source = (root / relative_path).resolve(strict=True)
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise RegistryAdapterError(f"workspace source escapes authority: {relative}") from exc
        if not source.is_file() or str(source) not in declared_scope:
            raise RegistryAdapterError(f"workspace source is not in frozen read scope: {relative}")
        actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        expected_hash = str(row.get("sha256") or "").lower()
        if not expected_hash or actual_hash != expected_hash:
            raise RegistryAdapterError(f"workspace source hash does not match: {relative}")
        result.append(
            {
                "path": str(source),
                "relative_path": relative,
                "sha256": actual_hash,
            }
        )
    return result


def _run_contract_ref(graph: dict[str, Any], envelope: dict[str, Any]) -> dict[str, str]:
    ref = graph.get("run_contract_ref") if isinstance(graph.get("run_contract_ref"), dict) else {}
    return {
        "run_contract_id": str(ref.get("run_contract_id") or ref.get("scheduler_input_id") or envelope.get("sprint_id") or ""),
        "sha256": str(ref.get("sha256") or ""),
    }


def _lease_id(envelope: dict[str, Any]) -> str:
    task_id = str(envelope.get("task_id") or "").strip()
    if (
        not task_id
        or "/" in task_id
        or "\\" in task_id
        or Path(task_id).name != task_id
        or task_id in {".", ".."}
    ):
        raise RegistryAdapterError("task_id is not a safe scheduler dispatch identifier")
    status_path = RUN_DIR / task_id / "status.json"
    if status_path.is_file():
        status = _read_object(status_path, label="scheduler task status")
        status_source = "scheduler lease status"
    else:
        operator_id = str(envelope.get("operator_id") or "").strip()
        if (
            not operator_id
            or "/" in operator_id
            or "\\" in operator_id
            or Path(operator_id).name != operator_id
            or operator_id in {".", ".."}
        ):
            raise RegistryAdapterError("operator_id is not a safe lease identifier")
        lease_path = OPERATOR_LEASE_DIR / f"{operator_id}.json"
        if not lease_path.is_file():
            raise RegistryAdapterError(
                "neither scheduler task status nor an active operator lease exists for registry dispatch"
            )
        status = _read_object(lease_path, label="operator runtime lease")
        status_source = "operator runtime lease"
        state = str(status.get("state") or "")
        if state not in {"leased", "running"}:
            raise RegistryAdapterError(f"operator runtime lease is not active: {state or 'missing'}")
        try:
            expires_at = datetime.datetime.fromisoformat(
                str(status.get("expires_at") or "").replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise RegistryAdapterError("operator runtime lease expiry is invalid") from exc
        now = datetime.datetime.now(datetime.timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        if expires_at.astimezone(datetime.timezone.utc) <= now:
            raise RegistryAdapterError("operator runtime lease has expired")
    exact_fields = {
        "task_id": task_id,
        "sprint_id": str(envelope.get("sprint_id") or ""),
        "node_id": str(envelope.get("node_id") or ""),
        "operator_id": str(envelope.get("operator_id") or ""),
    }
    if status_source == "scheduler lease status":
        exact_fields.update(
            {
                "id": task_id,
                "graph": str(
                    _resolved_path(envelope.get("graph_path"), label="graph_path", strict=True)
                ),
            }
        )
    for field, expected in exact_fields.items():
        if str(status.get(field) or "") != expected:
            raise RegistryAdapterError(f"{status_source} {field} does not match dispatch envelope")
    lease_id = str(status.get("lease_id") or "").strip()
    if not lease_id and status_source == "operator runtime lease":
        leased_at = str(status.get("leased_at") or "").strip()
        if leased_at:
            lease_id = f"{status['operator_id']}:{task_id}:{leased_at}"
    if not lease_id:
        raise RegistryAdapterError(f"{status_source} has no lease identifier")
    return lease_id


def _verified_model_service_route(
    envelope: dict[str, Any],
    node: dict[str, Any],
) -> dict[str, str]:
    """Verify the exact model route selected for this frozen dispatch.

    The model belongs to the scheduler dispatch envelope, not to the long-lived
    operatord environment.  Validate it against both the capsule's frozen
    default profile and the canonical model registry before constructing a
    provider service.  This prevents ambient configuration from silently
    changing or erasing the selected route.
    """
    profile_name = str(envelope.get("profile") or "").strip()
    model = str(envelope.get("model") or "").strip()
    reasoning_effort = str(envelope.get("reasoning_effort") or "").strip()
    if not profile_name or not model or not reasoning_effort:
        raise RegistryAdapterError(
            "model-backed registry dispatch requires profile, model, and reasoning_effort in the scheduler envelope"
        )

    authority = node.get("execution_authority")
    capsules = authority.get("capsules") if isinstance(authority, dict) else None
    capsule_ids = [
        str(value)
        for value in (node.get("capsule_binding") or {}).get("capsule_ids") or []
        if str(value).strip()
    ]
    frozen_profiles: list[str] = []
    for capsule_id in capsule_ids:
        snapshot = capsules.get(capsule_id) if isinstance(capsules, dict) else None
        value = str(
            snapshot.get("default_operator_profile") if isinstance(snapshot, dict) else ""
        ).strip()
        if value and value not in frozen_profiles:
            frozen_profiles.append(value)
    if len(frozen_profiles) != 1 or profile_name != frozen_profiles[0]:
        raise RegistryAdapterError(
            "scheduler envelope profile does not match the frozen capsule default_operator_profile"
        )

    profiles = _read_object(
        HARNESS_DIR / "config" / "multi-task-profiles.json",
        label="multi-task profile registry",
    ).get("profiles")
    profile = profiles.get(profile_name) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        raise RegistryAdapterError(f"scheduler envelope profile is not registered: {profile_name}")
    if model != str(profile.get("model") or "").strip():
        raise RegistryAdapterError("scheduler envelope model does not match its registered profile")
    if reasoning_effort != str(profile.get("reasoning_effort") or "").strip():
        raise RegistryAdapterError(
            "scheduler envelope reasoning_effort does not match its registered profile"
        )

    try:
        model_spec = model_registry.spec(model_registry.load_registry(), model)
    except SystemExit as exc:
        raise RegistryAdapterError(f"scheduler envelope model is not registered: {model}") from exc
    provider = str(model_spec.get("provider") or "").strip()
    if provider != "openai":
        raise RegistryAdapterError(
            f"selected provider {provider or '<missing>'} is unsupported by the Codex research model service"
        )
    return {
        "profile": profile_name,
        "model": model,
        "provider": provider,
        "reasoning_effort": reasoning_effort,
    }


def _production_service_overrides(
    node_id: str,
    *,
    envelope: dict[str, Any],
    node: dict[str, Any],
    work_dir: Path,
) -> dict[str, Any] | None:
    """Return only deliberate per-node overrides.

    ``default_production_resolver`` assigns a different meaning to ``None``
    and ``{}``: None loads the production service bundle, while an explicit
    mapping is treated as the complete injected bundle.  Native evidence
    nodes such as literature discovery therefore must return None so their
    multi-provider production service is installed.
    """

    if node_id not in {"report_draft", "publication_produce", "artifact_review"}:
        return None
    model_route = _verified_model_service_route(envelope, node)
    model_service = CodexResearchModelService(
        work_dir,
        model=model_route["model"],
        role="reviewer" if node_id == "artifact_review" else "writer",
        reasoning_effort=model_route["reasoning_effort"],
        timeout_seconds=int(
            os.environ.get("SOLAR_RESEARCH_MODEL_TIMEOUT_SEC") or "900"
        ),
    )
    return {
        "review_model_generate" if node_id == "artifact_review" else "model_generate": model_service
    }


def execute(envelope: dict[str, Any], *, receipt_path: Path) -> dict[str, Any]:
    expected = _validated_binding(envelope)
    operator_id = expected["operator_id"]
    graph, node, work_dir, handoff_path = _verified_dispatch_authority(
        envelope,
        configured_binding={
            "registry": expected["registry"],
            "node_id": expected["node_id"],
            "implementation_operator_id": expected["implementation_operator_id"],
        },
    )
    documents, source_paths = _matching_input_documents(graph, node, work_dir)
    workspace_sources = _verified_workspace_sources(graph, node)
    runtime_execution_snapshot = (
        _runtime_execution_snapshot(graph, envelope)
        if expected["node_id"] == "publication_produce"
        else None
    )
    if not documents and expected["node_id"] != "literature_discover":
        raise RegistryAdapterError("no artifact matching the frozen consume contract was found")
    payload = {
        **_payload_for_documents(expected["node_id"], documents),
        "source_artifacts": [
            {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            for path in source_paths
        ] + [
            {"path": row["path"], "sha256": row["sha256"]}
            for row in workspace_sources
        ],
        "task_contract": {"user_intent": str(node.get("goal") or "")},
        "requirement_ids": [
            str(item) for item in node.get("requirement_ids") or [] if str(item).strip()
        ],
        "run_context": {
            "sprint_id": str(graph.get("sprint_id") or ""),
            "run_contract_ref": _run_contract_ref(graph, envelope),
            **(
                {"runtime_execution_snapshot": runtime_execution_snapshot}
                if runtime_execution_snapshot is not None
                else {}
            ),
            "frozen_nodes": [
                {
                    "node_id": str(item.get("id") or item.get("node_id") or ""),
                    "depends_on": [str(value) for value in item.get("depends_on") or []],
                    "logical_operator": str(item.get("logical_operator") or ""),
                    "physical_operator_ids": [
                        str(candidate.get("operator_id") or "")
                        for candidate in item.get("physical_candidates") or []
                        if isinstance(candidate, dict) and str(candidate.get("operator_id") or "")
                    ],
                    "artifact_routes": item.get("artifact_routes") or item.get("output_routes") or [],
                }
                for item in graph.get("nodes") or []
                if isinstance(item, dict)
            ],
        },
    }
    experiment_write_scope = _experiment_run_write_scope(graph)
    if expected["node_id"] == "dataset_prepare":
        if len(experiment_write_scope) != 1:
            raise RegistryAdapterError("dataset preparation requires one frozen experiment-run output scope")
        payload["experiment_result_scope"] = str(Path(experiment_write_scope[0]) / "raw_measurement.json")
    network_mode = str((node.get("resource_requirements") or {}).get("network") or "optional")
    if expected["node_id"] == "discovery_ingest":
        payload["max_sources"] = min(10, len(documents[0].get("outputs", {}).get("candidates") or []))
    if expected["node_id"] == "literature_discover":
        payload.update(
            {
                "query": str(node.get("goal") or "").strip(),
                "mode": "topic",
                "allow_network_fetch": network_mode != "forbidden",
                "require_online_source_evidence": network_mode == "required",
            }
        )
        if workspace_sources:
            payload["local_sources"] = workspace_sources
            payload["max_retries"] = 0
            payload["max_retry_wait_seconds"] = 0
    if expected["node_id"] in {"report_plan", "report_draft"}:
        payload["topic"] = (
            _report_title_from_frozen_context(graph, node, documents)
            or str(node.get("goal") or "Scientific research report")
        )

    external_inputs = {
        str(_resolved_path(item.get("path"), label=f"runtime input {artifact_type}", strict=True))
        for artifact_type, item in (graph.get("runtime_input_bindings") or {}).items()
        if isinstance(item, dict)
    }
    read_scope = sorted({
        path if path in external_inputs else str(Path(path).parent) + os.sep
        for path in source_paths
    } | {row["path"] for row in workspace_sources})
    write_scope = [str(item) for item in node.get("write_scope") or [] if str(item).strip()]
    required_authorizations = [
        str(value)
        for value in (node.get("resource_requirements") or {}).get("required_authorizations") or []
        if str(value).strip()
    ]
    run_contract_ref = _run_contract_ref(graph, envelope)
    request = {
        "schema": "research_node_request.v1",
        "task_id": str(envelope.get("task_id") or ""),
        "run_id": str(graph.get("sprint_id") or ""),
        "workflow_id": "scheduler_frozen_research_registry_v1",
        "node_id": str(node.get("id") or expected["node_id"]),
        "implementation_node_id": expected["node_id"],
        "scheduled_node_id": str(node.get("id") or expected["node_id"]),
        "logical_operator": {
            "operator_id": str(node.get("id") or expected["node_id"]),
            "operator_kind": "logical",
            "capabilities": list((node.get("capsule_binding") or {}).get("capsule_ids") or []),
        },
        "physical_operator": {
            "operator_id": operator_id,
            "operator_kind": "physical",
            "capabilities": list((node.get("capsule_binding") or {}).get("capsule_ids") or []),
        },
        "typed_inputs": {"input_schema": f"{expected['node_id']}.scheduler.v1", "payload": payload},
        # Cross-node scheduler task ids differ. Inline hash-recorded documents
        # preserve provenance without pretending they share one task identity.
        "input_artifact_refs": [],
        "authorization": {
            "scope_id": f"{graph.get('sprint_id')}:{node.get('id')}",
            "approved_capabilities": list(dict.fromkeys([
                *list((node.get("capsule_binding") or {}).get("capsule_ids") or []),
                *required_authorizations,
            ])),
            "allow_network": network_mode != "forbidden",
            "allow_live_provider": network_mode != "forbidden",
            "secret_refs": [],
            "approval_ref": (
                f"run-contract:{run_contract_ref.get('sha256')}"
                if "execute_experiment" in required_authorizations and run_contract_ref.get("sha256")
                else ""
            ),
            "approved_write_scope": experiment_write_scope if required_authorizations else write_scope,
        },
        "read_scope": read_scope,
        "write_scope": write_scope,
        "timeout_retry_policy": {"timeout_seconds": 900, "max_attempts": 1, "retry_on": []},
    }
    services = _production_service_overrides(
        expected["node_id"],
        envelope=envelope,
        node=node,
        work_dir=work_dir,
    )
    resolver = default_production_resolver(services=services, workspace_root=work_dir)
    resolver_operator_id = f"{expected['node_id']}_worker"

    def execute_registered(request: dict[str, Any]) -> dict[str, Any]:
        if resolver_operator_id == operator_id:
            return resolver.execute(request)
        registry_request = dict(request)
        registry_request["physical_operator"] = {
            **dict(request.get("physical_operator") or {}),
            "operator_id": resolver_operator_id,
        }
        return resolver.execute(registry_request)

    receipt = run_physical_operator(
        request,
        operator_id=operator_id,
        runner=execute_registered,
        envelope_path=receipt_path,
        attempt=1,
        lease_id=_lease_id(envelope),
        run_contract_ref=run_contract_ref,
    )
    if handoff_path and receipt.get("status") == "completed":
        artifact_paths = [
            work_dir / str(item.get("path") or "")
            for item in receipt.get("artifacts") or []
            if isinstance(item, dict) and str(item.get("path") or "").strip()
        ]
        primary_result = artifact_paths[0].resolve() if artifact_paths else None
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_text(
            "# Research registry operator handoff\n\n"
            f"- operator: `{operator_id}`\n"
            f"- registry node: `{expected['node_id']}`\n"
            f"- Result: `{primary_result or 'N/A'}`\n"
            f"- receipt: `{receipt_path}`\n"
            f"- artifacts: `{len(receipt.get('artifacts') or [])}`\n",
            encoding="utf-8",
        )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt_path = args.envelope.with_name("node_envelope.json")
    try:
        receipt = execute(_read_object(args.envelope, label="operator envelope"), receipt_path=receipt_path)
    except (OSError, RegistryAdapterError, ValueError) as exc:
        failure = {"ok": False, "reason": "research_operator_registry_dispatch_failed", "error": str(exc)[:500]}
        print(json.dumps(failure, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": receipt.get("status") == "completed", "receipt": receipt}, ensure_ascii=False))
    return 0 if receipt.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
