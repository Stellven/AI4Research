#!/usr/bin/env python3
"""Validate frozen SchedulerInput and project it into Solar's runtime graph.

``scheduler_input.json`` is immutable planning authority.  The projection made
here is a compatibility view for the existing graph scheduler; all mutable
state is written to a separate ``task_graph_state.json`` ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


SOURCE_HARNESS_DIR = Path(__file__).resolve().parents[1]
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR") or SOURCE_HARNESS_DIR)
SCHEMA_PATH = Path(
    os.environ.get(
        "SOLAR_SCHEDULER_INPUT_SCHEMA",
        HARNESS_DIR / "schemas" / "planning" / "scheduler-input.v1.schema.json",
    )
)
if not SCHEMA_PATH.exists():
    SCHEMA_PATH = SOURCE_HARNESS_DIR / "schemas" / "planning" / "scheduler-input.v1.schema.json"

MUTABLE_NODE_FIELDS = {
    "status",
    "attempt",
    "selected_operator",
    "lease_id",
    "dispatch_id",
    "assigned_to",
    "result",
    "updated_at",
}
RUNTIME_PROJECTION_NODE_FIELDS = {
    "assigned_to",
    "attempt",
    "candidate_observations",
    "blocking_reason",
    "closeout_receipt",
    "dispatch_id",
    "eval_json",
    "evaluation_results",
    "evaluation_state",
    "execution_attempt",
    "execution_attempt_error",
    "failure_policy_exhausted",
    "gate_status",
    "human_review",
    "lease_id",
    "queued_pane",
    "repair_attempts",
    "result",
    "result_path",
    "selected_operator",
    "scheduler_candidate_observations",
    "status",
    "updated_at",
    "worker_match_details",
}
RUNTIME_PROJECTION_ROOT_FIELDS = {
    "schema_version",
    "sprint_id",
    "graph_id",
    "planning_authority",
    "test_policy",
    "scheduler_input_ref",
    "run_contract_ref",
    "runtime_input_bindings",
    "runtime_state_filename",
    "runtime_work_dir",
    "nodes",
}
RUNTIME_PROJECTION_ROOT_MUTABLE_FIELDS = {
    "_solar_runtime",
    "gate_results",
    "node_results",
}

# Controller-owned request data is delivered inside the immutable physical
# operator envelope.  It is an artifact-type identity in PlanIR/SchedulerInput,
# not a staging-workspace filename.  Project it to the exact runtime authority
# understood by graph_node_dispatcher instead of treating the schema URI as a
# relative path below the node work directory.
CONTROLLER_DISPATCH_ROUTES = {
    "schema:request-envelope.schema.json": "dispatch/envelope.json",
}

# Scheduler records nest sprint, node, and dispatch IDs. Keep each component
# short enough that the full path remains usable by non-long-path-aware Windows
# processes even when the repository and pytest roots are already deep.
_MAX_RECORD_COMPONENT_LENGTH = 24
_WINDOWS_RESERVED_PATH_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class SchedulerInputError(ValueError):
    """A frozen scheduler input is malformed or cannot be trusted."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bounded_record_component(value: Any, *, fallback: str) -> str:
    """Return a deterministic, readable path component safe on Windows."""
    raw = str(value or fallback).strip()
    safe = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in raw
    ).strip(" .")
    safe = safe if safe not in {"", ".", ".."} else fallback
    reserved = safe.split(".", 1)[0].upper() in _WINDOWS_RESERVED_PATH_NAMES
    if safe == raw and not reserved and len(safe) <= _MAX_RECORD_COMPONENT_LENGTH:
        return safe
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    prefix_length = _MAX_RECORD_COMPONENT_LENGTH - len(digest) - 1
    prefix = safe[:prefix_length].rstrip(" ._-") or fallback[:prefix_length]
    return f"{prefix}-{digest}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchedulerInputError(f"SCHEDULER_INPUT_UNREADABLE:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise SchedulerInputError("SCHEDULER_INPUT_ROOT_NOT_OBJECT")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_errors(value: dict[str, Any]) -> list[str]:
    schema = _read_json(SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = "/".join(str(item) for item in error.absolute_path) or "$"
        errors.append(f"SCHEMA:{location}:{error.message}")
    return errors


def _ancestor_ids(node_id: str, nodes: dict[str, dict[str, Any]]) -> set[str]:
    pending = list(nodes[node_id].get("depends_on") or [])
    seen: set[str] = set()
    while pending:
        candidate = str(pending.pop())
        if candidate in seen or candidate not in nodes:
            continue
        seen.add(candidate)
        pending.extend(nodes[candidate].get("depends_on") or [])
    return seen


def semantic_errors(value: dict[str, Any]) -> list[str]:
    """Return stable DAG, handoff, and cross-field contract violations."""
    graph = value.get("graph") if isinstance(value.get("graph"), dict) else {}
    raw_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    errors: list[str] = []
    nodes: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id") or "")
        if node_id in nodes:
            duplicate_ids.add(node_id)
        else:
            nodes[node_id] = raw
        forbidden = sorted(MUTABLE_NODE_FIELDS.intersection(raw))
        if forbidden:
            errors.append(f"MUTABLE_FIELD_IN_FROZEN_NODE:{node_id}:{','.join(forbidden)}")
        ranks = [candidate.get("rank") for candidate in raw.get("physical_candidates") or [] if isinstance(candidate, dict)]
        if len(ranks) != len(set(ranks)):
            errors.append(f"DUPLICATE_CANDIDATE_RANK:{node_id}")
        if "execution_authority" in raw:
            from execution_authority import validate
            try:
                authority = raw["execution_authority"]
                validate(authority)
                expected_operators = {row["operator_id"] for row in raw.get("physical_candidates") or []}
                if set(authority["operators"]) != expected_operators:
                    errors.append(f"EXECUTION_AUTHORITY_CANDIDATES_MISMATCH:{node_id}")
                if not set((raw.get("capsule_binding") or {}).get("capsule_ids") or []).issubset(authority["capsules"]):
                    errors.append(f"EXECUTION_AUTHORITY_CAPSULES_MISMATCH:{node_id}")
            except (ValueError, TypeError, KeyError) as exc:
                errors.append(f"EXECUTION_AUTHORITY_INVALID:{node_id}:{exc}")
        resources = raw.get("resource_requirements") if isinstance(raw.get("resource_requirements"), dict) else {}
        effects = set(raw.get("effects") or [])
        network = str(resources.get("network") or "")
        if network == "required" and "network" not in effects:
            errors.append(f"NETWORK_REQUIRED_WITHOUT_EFFECT:{node_id}")
        if network == "forbidden" and "network" in effects:
            errors.append(f"NETWORK_FORBIDDEN_WITH_EFFECT:{node_id}")
    for node_id in sorted(duplicate_ids):
        errors.append(f"DUPLICATE_NODE_ID:{node_id}")

    for node_id, node in nodes.items():
        for dependency in node.get("depends_on") or []:
            dependency = str(dependency)
            if dependency == node_id:
                errors.append(f"SELF_DEPENDENCY:{node_id}")
            elif dependency not in nodes:
                errors.append(f"MISSING_DEPENDENCY:{node_id}:{dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            errors.append(f"DAG_CYCLE:{node_id}")
            return
        visiting.add(node_id)
        for dependency in nodes[node_id].get("depends_on") or []:
            dependency = str(dependency)
            if dependency in nodes:
                visit(dependency)
        visiting.discard(node_id)
        visited.add(node_id)

    for node_id in sorted(nodes):
        visit(node_id)

    producers: dict[str, str] = {}
    for node_id, node in nodes.items():
        contract = node.get("artifact_contract") if isinstance(node.get("artifact_contract"), dict) else {}
        for artifact in contract.get("produces") or []:
            artifact = str(artifact)
            if artifact in producers:
                errors.append(f"DUPLICATE_ARTIFACT_PRODUCER:{artifact}:{producers[artifact]}:{node_id}")
            else:
                producers[artifact] = node_id
    if not any(error.startswith("DAG_CYCLE:") for error in errors):
        for node_id, node in nodes.items():
            ancestors = _ancestor_ids(node_id, nodes)
            contract = node.get("artifact_contract") if isinstance(node.get("artifact_contract"), dict) else {}
            for artifact in contract.get("consumes") or []:
                producer = producers.get(str(artifact))
                if producer is not None and producer not in ancestors:
                    errors.append(f"ARTIFACT_PRODUCER_NOT_ANCESTOR:{node_id}:{artifact}:{producer}")
    return errors


def validate(value: dict[str, Any], *, require_runtime_authority: bool = False) -> dict[str, Any]:
    errors = _schema_errors(value)
    errors.extend(semantic_errors(value))
    if require_runtime_authority and value.get("artifact_role") != "runtime_execution_authority":
        errors.append("NOT_RUNTIME_EXECUTION_AUTHORITY")
    return {"ok": not errors, "errors": errors}


def load_and_validate(path: str | Path, *, require_runtime_authority: bool = False) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    value = _read_json(source)
    result = validate(value, require_runtime_authority=require_runtime_authority)
    if not result["ok"]:
        raise SchedulerInputError("; ".join(result["errors"]))
    return value


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _runtime_node(node: dict[str, Any], artifact_paths: dict[str, str] | None = None) -> dict[str, Any]:
    binding = deepcopy(node["evaluation_binding"])
    semantic_evaluators = list(binding.get("semantic_evaluator_ids") or [])
    deterministic_gates = list(binding.get("deterministic_gate_ids") or [])
    failure = deepcopy(node["failure_policy"])
    candidates = sorted(deepcopy(node["physical_candidates"]), key=lambda item: (item["rank"], item["operator_id"]))
    artifact_paths = artifact_paths or {}
    consumes = list(node["artifact_contract"]["consumes"])
    produces = list(node["artifact_contract"]["produces"])
    consume_paths = {
        item: artifact_paths.get(item) or CONTROLLER_DISPATCH_ROUTES.get(item) or item
        for item in consumes
    }
    return {
        "id": node["id"],
        "goal": node["goal"],
        **({"retrieval_contract": deepcopy(node["retrieval_contract"])} if node.get("retrieval_contract") else {}),
        "logical_operator": node["logical_operator"],
        "dispatch_task_type": node["dispatch_task_type"],
        "task_type": node["dispatch_task_type"],
        "depends_on": deepcopy(node["depends_on"]),
        "requirement_ids": deepcopy(node["requirement_ids"]),
        "capsule_binding": deepcopy(node["capsule_binding"]),
        "capability_capsule_id": node["capsule_binding"]["capsule_ids"][0],
        "required_capabilities": deepcopy(node["capsule_binding"]["capsule_ids"]),
        "physical_candidates": candidates,
        "artifact_contract": deepcopy(node["artifact_contract"]),
        "artifact_routes": {
            "consumes": consume_paths,
            "produces": {item: artifact_paths.get(item) for item in produces},
        },
        "evaluation_binding": binding,
        "evaluator_gate": deepcopy(node.get("evaluator_gate") or {}),
        "evaluation_policy": deepcopy(node.get("evaluation_policy") or {}),
        "evaluation_plan": {
            "review_mode": "single",
            "required_evaluators": 1 if semantic_evaluators else 0,
            "evaluator_classes": semantic_evaluators or deterministic_gates,
            "evidence_requirements": ["handoff_md", "session_log", "artifact_contract"],
        },
        "resource_requirements": deepcopy(node["resource_requirements"]),
        **({"execution_authority": deepcopy(node["execution_authority"])} if "execution_authority" in node else {}),
        "effects": deepcopy(node["effects"]),
        "priority": node["priority"],
        "failure_policy": failure,
        "max_repair_attempts": max(0, int(failure["max_attempts"]) - 1),
        "on_failure_exhausted": failure["on_exhausted"],
        "read_scope": [consume_paths[item] for item in consumes],
        "write_scope": [artifact_paths.get(item) or item for item in produces],
        "acceptance": [
            *[f"deterministic gate: {item}" for item in deterministic_gates],
            *[f"semantic evaluator: {item}" for item in semantic_evaluators],
        ],
    }


def _run_contract_ref(run_contract_path: str | Path | None, scheduler_path: Path, digest: str) -> dict[str, Any]:
    if run_contract_path is None:
        return {
            "scheduler_input_id": _read_json(scheduler_path).get("scheduler_input_id"),
            "sha256": digest,
        }
    contract_path = Path(run_contract_path).expanduser().resolve()
    contract = _read_json(contract_path)
    if contract.get("schema_version") == "solar.run_contract.frozen.v2":
        binding = contract.get("scheduler_input_ref") if isinstance(contract.get("scheduler_input_ref"), dict) else {}
        scheduler_id = str(_read_json(scheduler_path).get("scheduler_input_id") or "")
        if str(binding.get("scheduler_input_id") or "") != scheduler_id:
            raise SchedulerInputError("RUN_CONTRACT_SCHEDULER_INPUT_ID_MISMATCH")
        if str(binding.get("sha256") or "") != digest:
            raise SchedulerInputError("RUN_CONTRACT_SCHEDULER_INPUT_HASH_MISMATCH")
        return {
            "run_contract_id": f"run-contract-{contract.get('sprint_id') or scheduler_id}",
            "contract_sha256": str(contract.get("contract_sha256") or ""),
            "sha256": file_sha256(contract_path),
            "path": str(contract_path),
        }
    matching = [
        item for item in contract.get("frozen_artifacts") or []
        if isinstance(item, dict) and item.get("name") == "scheduler_input.json"
    ]
    if len(matching) != 1:
        raise SchedulerInputError("RUN_CONTRACT_SCHEDULER_INPUT_BINDING_MISSING")
    if str(matching[0].get("sha256") or "") != digest:
        raise SchedulerInputError("RUN_CONTRACT_SCHEDULER_INPUT_HASH_MISMATCH")
    return {
        "run_contract_id": str(contract.get("run_contract_id") or ""),
        "sha256": file_sha256(contract_path),
        "path": str(contract_path),
    }


def _runtime_input_bindings(bindings: dict[str, str] | None) -> dict[str, dict[str, str]]:
    resolved: dict[str, dict[str, str]] = {}
    for artifact_type, raw_path in sorted((bindings or {}).items()):
        name = str(artifact_type or "").strip()
        path = Path(str(raw_path or "")).expanduser().resolve()
        if not name:
            raise SchedulerInputError("RUNTIME_INPUT_ARTIFACT_TYPE_MISSING")
        if not path.is_file():
            raise SchedulerInputError(f"RUNTIME_INPUT_ARTIFACT_MISSING:{name}:{path}")
        resolved[name] = {"path": str(path), "sha256": file_sha256(path)}
    return resolved


def _resume_existing_runtime_graph(
    graph_path: Path,
    state_path: Path,
    *,
    scheduler_input_id: str,
    scheduler_input_sha256: str,
    run_contract_ref: dict[str, Any],
    runtime_input_bindings: dict[str, dict[str, str]],
) -> Path | None:
    """Resume a matching runtime pair without destroying its mutable ledger."""
    graph_exists = graph_path.exists()
    state_exists = state_path.exists()
    if not graph_exists and not state_exists:
        return None
    if graph_exists != state_exists:
        raise SchedulerInputError("SCHEDULER_RUNTIME_PAIR_INCOMPLETE")

    graph = _read_json(graph_path)
    verification = verify_runtime_projection(graph, graph_path=graph_path)
    if not verification.get("ok"):
        errors = ",".join(str(item) for item in verification.get("errors") or [])
        raise SchedulerInputError(f"SCHEDULER_RUNTIME_PROJECTION_INVALID:{errors}")

    source_ref = (
        graph.get("scheduler_input_ref")
        if isinstance(graph.get("scheduler_input_ref"), dict)
        else {}
    )
    if (
        str(source_ref.get("scheduler_input_id") or "") != scheduler_input_id
        or str(source_ref.get("sha256") or "") != scheduler_input_sha256
    ):
        raise SchedulerInputError("SCHEDULER_RUNTIME_INPUT_CONFLICT")
    if graph.get("run_contract_ref") != run_contract_ref:
        raise SchedulerInputError("SCHEDULER_RUNTIME_RUN_CONTRACT_CONFLICT")
    if graph.get("runtime_input_bindings") != runtime_input_bindings:
        raise SchedulerInputError("SCHEDULER_RUNTIME_ARTIFACT_BINDINGS_CONFLICT")

    state = _read_json(state_path)
    node_ids = {
        str(node.get("id") or "")
        for node in graph.get("nodes") or []
        if isinstance(node, dict)
    }
    state_nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    node_results = (
        state.get("node_results")
        if isinstance(state.get("node_results"), dict)
        else {}
    )
    ready_nodes = state.get("ready_nodes") if isinstance(state.get("ready_nodes"), list) else None
    revision = state.get("revision")
    state_valid = (
        state.get("schema_version") == "solar.task_graph_state.v1"
        and state.get("artifact_role") == "mutable_execution_ledger"
        and state.get("scheduler_input_ref") == source_ref
        and state.get("run_contract_ref") == graph.get("run_contract_ref")
        and set(state_nodes) == node_ids
        and set(node_results) == node_ids
        and ready_nodes is not None
        and all(isinstance(node_id, str) and node_id in node_ids for node_id in ready_nodes)
        and isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision >= 0
        and isinstance(state.get("events"), list)
    )
    if not state_valid:
        raise SchedulerInputError("SCHEDULER_RUNTIME_STATE_INVALID")
    return graph_path


def prepare_runtime_graph(
    scheduler_input_path: str | Path,
    output_dir: str | Path,
    *,
    run_contract_path: str | Path | None = None,
    artifact_bindings: dict[str, str] | None = None,
) -> Path:
    source = Path(scheduler_input_path).expanduser().resolve()
    value = load_and_validate(source, require_runtime_authority=True)
    digest = file_sha256(source)
    sprint_id = str(value["sprint_id"])
    destination = Path(output_dir).expanduser().resolve()
    graph_path = destination / f"{sprint_id}.task_graph.json"
    state_name = f"{sprint_id}.task_graph_state.json"
    work_dir = destination / sprint_id / "workdir"
    input_bindings = _runtime_input_bindings(artifact_bindings)
    artifact_paths: dict[str, str] = {
        artifact_type: item["path"] for artifact_type, item in input_bindings.items()
    }
    for node in value["graph"]["nodes"]:
        for artifact in node["artifact_contract"]["produces"]:
            safe_name = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in artifact)
            artifact_paths[artifact] = str((work_dir / "artifacts" / node["id"] / safe_name).resolve()) + os.sep
    source_ref = {
        "path": str(source),
        "scheduler_input_id": value["scheduler_input_id"],
        "sha256": digest,
    }
    run_contract_ref = _run_contract_ref(run_contract_path, source, digest)
    graph = {
        "schema_version": "solar.scheduler_runtime_projection.v1",
        "sprint_id": sprint_id,
        "graph_id": value["graph"]["graph_id"],
        "planning_authority": value["planning_authority"],
        "test_policy": deepcopy(value.get("test_policy") or {}),
        "scheduler_input_ref": source_ref,
        "run_contract_ref": run_contract_ref,
        "runtime_input_bindings": input_bindings,
        "runtime_state_filename": state_name,
        "runtime_work_dir": str(work_dir.resolve()),
        "nodes": [_runtime_node(node, artifact_paths) for node in value["graph"]["nodes"]],
    }
    node_state = {
        node["id"]: {
            "status": "pending",
            "attempt": 0,
            "blocked_by": list(node["depends_on"]),
        }
        for node in value["graph"]["nodes"]
    }
    state = {
        "schema_version": "solar.task_graph_state.v1",
        "artifact_role": "mutable_execution_ledger",
        "run_contract_ref": deepcopy(graph["run_contract_ref"]),
        "scheduler_input_ref": source_ref,
        "revision": 0,
        "run_status": "queued",
        "nodes": node_state,
        "node_results": {node_id: {"status": "pending"} for node_id in node_state},
        "ready_nodes": [node_id for node_id, item in node_state.items() if not item["blocked_by"]],
        "last_event_id": None,
        "updated_at": _now(),
        "events": [],
    }
    resumed = _resume_existing_runtime_graph(
        graph_path,
        destination / state_name,
        scheduler_input_id=str(value["scheduler_input_id"]),
        scheduler_input_sha256=digest,
        run_contract_ref=run_contract_ref,
        runtime_input_bindings=input_bindings,
    )
    if resumed is not None:
        return resumed
    _atomic_json_write(graph_path, graph)
    _atomic_json_write(destination / state_name, state)
    return graph_path


def verify_runtime_projection(
    graph: dict[str, Any],
    *,
    graph_path: str | Path | None = None,
) -> dict[str, Any]:
    if graph.get("schema_version") != "solar.scheduler_runtime_projection.v1":
        return {"ok": False, "errors": ["NOT_SCHEDULER_RUNTIME_PROJECTION"]}
    root_fields = set(graph)
    if (
        not RUNTIME_PROJECTION_ROOT_FIELDS.issubset(root_fields)
        or bool(root_fields - RUNTIME_PROJECTION_ROOT_FIELDS - RUNTIME_PROJECTION_ROOT_MUTABLE_FIELDS)
    ):
        return {"ok": False, "errors": ["SCHEDULER_RUNTIME_ROOT_FIELDS_TAMPERED"]}
    reference = graph.get("scheduler_input_ref") if isinstance(graph.get("scheduler_input_ref"), dict) else {}
    source = Path(str(reference.get("path") or "")).expanduser()
    if not source.is_file():
        return {"ok": False, "errors": ["SCHEDULER_INPUT_SOURCE_MISSING"]}
    actual = file_sha256(source)
    if actual != str(reference.get("sha256") or ""):
        return {"ok": False, "errors": ["SCHEDULER_INPUT_SOURCE_HASH_MISMATCH"]}
    try:
        value = load_and_validate(source, require_runtime_authority=True)
    except SchedulerInputError as exc:
        return {"ok": False, "errors": [str(exc)]}
    expected_source_ref = {
        "path": str(source.resolve()),
        "scheduler_input_id": value["scheduler_input_id"],
        "sha256": actual,
    }
    if reference != expected_source_ref:
        return {"ok": False, "errors": ["SCHEDULER_INPUT_REFERENCE_TAMPERED"]}
    if (
        graph.get("sprint_id") != value["sprint_id"]
        or graph.get("graph_id") != value["graph"]["graph_id"]
        or graph.get("planning_authority") != value["planning_authority"]
        or graph.get("test_policy") != (value.get("test_policy") or {})
        or graph.get("runtime_state_filename")
        != f"{value['sprint_id']}.task_graph_state.json"
    ):
        return {"ok": False, "errors": ["SCHEDULER_RUNTIME_ROOT_TAMPERED"]}
    run_contract_ref = graph.get("run_contract_ref")
    if not isinstance(run_contract_ref, dict):
        return {"ok": False, "errors": ["RUN_CONTRACT_REFERENCE_INVALID"]}
    try:
        expected_run_contract_ref = _run_contract_ref(
            run_contract_ref.get("path"),
            source.resolve(),
            actual,
        )
    except (OSError, SchedulerInputError):
        return {"ok": False, "errors": ["RUN_CONTRACT_REFERENCE_INVALID"]}
    if run_contract_ref != expected_run_contract_ref:
        return {"ok": False, "errors": ["RUN_CONTRACT_REFERENCE_TAMPERED"]}
    work_dir = Path(str(graph.get("runtime_work_dir") or ""))
    if not work_dir.is_absolute():
        return {"ok": False, "errors": ["SCHEDULER_RUNTIME_WORK_DIR_INVALID"]}
    if str(graph_path or "").strip():
        resolved_graph_path = Path(str(graph_path)).expanduser().resolve()
        runtime_root = resolved_graph_path.parent
        expected_graph_path = runtime_root / f"{value['sprint_id']}.task_graph.json"
        expected_work_dir = runtime_root / str(value["sprint_id"]) / "workdir"
        if resolved_graph_path != expected_graph_path or work_dir.resolve() != expected_work_dir.resolve():
            return {"ok": False, "errors": ["SCHEDULER_RUNTIME_ROOT_BINDING_INVALID"]}
    input_bindings = (
        graph.get("runtime_input_bindings")
        if isinstance(graph.get("runtime_input_bindings"), dict)
        else {}
    )
    artifact_paths: dict[str, str] = {}
    for artifact_type, item in input_bindings.items():
        if not isinstance(item, dict):
            return {"ok": False, "errors": ["RUNTIME_INPUT_BINDING_INVALID"]}
        path = Path(str(item.get("path") or "")).expanduser()
        if not path.is_file():
            return {"ok": False, "errors": [f"RUNTIME_INPUT_ARTIFACT_MISSING:{artifact_type}"]}
        if file_sha256(path) != str(item.get("sha256") or ""):
            return {"ok": False, "errors": [f"RUNTIME_INPUT_ARTIFACT_HASH_MISMATCH:{artifact_type}"]}
        artifact_paths[str(artifact_type)] = str(path.resolve())
    for node in value["graph"]["nodes"]:
        for artifact in node["artifact_contract"]["produces"]:
            safe_name = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in artifact)
            artifact_paths[artifact] = str((work_dir / "artifacts" / node["id"] / safe_name).resolve()) + os.sep
    expected = [_runtime_node(node, artifact_paths) for node in value["graph"]["nodes"]]
    actual_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    if len(actual_nodes) != len(expected):
        return {"ok": False, "errors": ["SCHEDULER_RUNTIME_PROJECTION_TAMPERED"]}
    for expected_node, actual_node in zip(expected, actual_nodes):
        extra_keys = (
            set(actual_node) - set(expected_node)
            if isinstance(actual_node, dict)
            else set()
        )
        if (
            not isinstance(actual_node, dict)
            or bool(extra_keys - RUNTIME_PROJECTION_NODE_FIELDS)
            or any(
            actual_node.get(key) != expected_value
            for key, expected_value in expected_node.items()
            )
        ):
            return {"ok": False, "errors": ["SCHEDULER_RUNTIME_PROJECTION_TAMPERED"]}
    return {"ok": True, "errors": []}


def write_dispatch_records(
    output_root: str | Path,
    *,
    graph: dict[str, Any],
    node: dict[str, Any],
    profile: dict[str, Any],
    submit_result: dict[str, Any],
    dispatch_id: str,
) -> dict[str, str]:
    """Persist the scheduler decision and lease in a GUI-readable location."""
    root = (
        Path(output_root)
        / _bounded_record_component(graph.get("sprint_id"), fallback="unknown-sprint")
        / _bounded_record_component(node.get("id"), fallback="unknown-node")
        / _bounded_record_component(dispatch_id, fallback="unknown-dispatch")
    )
    candidates = deepcopy(profile.get("scheduler_candidate_observations") or [])
    selected = str(submit_result.get("operator_id") or profile.get("operator_id") or "")
    execution_attempt = node.get("execution_attempt") if isinstance(node.get("execution_attempt"), dict) else {}
    attempt = max(1, int(execution_attempt.get("sequence") or 1))
    dispatch = {
        "schema_version": "solar.dispatch_record.v1",
        "artifact_role": "runtime_dispatch_decision",
        "run_contract_ref": deepcopy(graph.get("run_contract_ref") or {}),
        "node": node.get("id"),
        "attempt": attempt,
        "decision": "selected",
        "selected_operator": selected,
        "candidates": candidates,
        "excluded": [item for item in candidates if item.get("operator_id") != selected],
        "reason": "first currently dispatchable candidate in ascending frozen rank order",
        "lease_id": submit_result.get("lease_id"),
    }
    lease = {
        "schema_version": "solar.lease_record.v1",
        "artifact_role": "runtime_operator_lease",
        "lease_id": submit_result.get("lease_id"),
        "run_contract_id": (graph.get("run_contract_ref") or {}).get("run_contract_id"),
        "node": node.get("id"),
        "attempt": attempt,
        "operator_id": selected,
        "issued_at": submit_result.get("submitted_at") or _now(),
        "expires_at": submit_result.get("expires_at"),
        "heartbeat_at": submit_result.get("submitted_at") or _now(),
        "fencing_token": attempt,
        "status": "active",
    }
    dispatch_path = root / "dispatch_record.json"
    lease_path = root / "lease_record.json"
    _atomic_json_write(dispatch_path, dispatch)
    _atomic_json_write(lease_path, lease)
    return {"dispatch_record": str(dispatch_path), "lease_record": str(lease_path)}
