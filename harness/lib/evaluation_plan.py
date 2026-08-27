"""Compile frozen per-node evaluation contracts from admitted Planner artifacts."""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from intent_compiler import sha256_payload


HARNESS_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = HARNESS_DIR / "config"
SCHEMA_DIR = HARNESS_DIR / "schemas" / "planning"
CHECK_REGISTRY_PATH = CONFIG_DIR / "evaluation-checks.v1.json"
ARTIFACT_TYPES_PATH = CONFIG_DIR / "artifact-types.v1.json"
CHECK_REGISTRY_SCHEMA = SCHEMA_DIR / "evaluation-check-registry.v1.schema.json"
EVALUATION_PLAN_SCHEMA = SCHEMA_DIR / "evaluation-plan.v1.schema.json"
EVALUATION_VALIDATION_SCHEMA = SCHEMA_DIR / "evaluation-plan-validation.v1.schema.json"


class EvaluationPlanError(RuntimeError):
    """Raised when evaluation contracts cannot be represented truthfully."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationPlanError(f"expected JSON object: {path}")
    return value


def _validate_schema(payload: dict[str, Any], schema_path: Path, label: str) -> None:
    errors = sorted(
        Draft202012Validator(_load_json(schema_path)).iter_errors(payload),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.absolute_path) or "$"
        raise EvaluationPlanError(f"{label} schema invalid at {path}: {first.message}")


def _resolve_callable(reference: str) -> bool:
    module_name, _, attribute = reference.partition(":")
    if not module_name or not attribute:
        return False
    harness_text = str(HARNESS_DIR)
    inserted = harness_text not in sys.path
    if inserted:
        sys.path.insert(0, harness_text)
    try:
        module = importlib.import_module(module_name)
        return callable(getattr(module, attribute, None))
    except Exception:
        return False
    finally:
        if inserted and harness_text in sys.path:
            sys.path.remove(harness_text)


def load_evaluation_check_registry(path: Path = CHECK_REGISTRY_PATH) -> dict[str, Any]:
    registry = _load_json(path)
    _validate_schema(registry, CHECK_REGISTRY_SCHEMA, "evaluation check registry")
    rows = [row for row in registry.get("checks") or [] if isinstance(row, dict)]
    check_ids = [str(row.get("check_id") or "") for row in rows]
    if len(check_ids) != len(set(check_ids)):
        raise EvaluationPlanError("evaluation check registry contains duplicate check_id values")
    artifact_registry = _load_json(ARTIFACT_TYPES_PATH)
    known_artifacts = {
        str(row.get("artifact_type") or "")
        for row in artifact_registry.get("artifact_types") or []
        if isinstance(row, dict)
    }
    for row in rows:
        applies = row.get("applies_to") or {}
        if applies.get("kind") == "artifact_type":
            unknown = sorted(set(applies.get("artifact_types") or []) - known_artifacts)
            if unknown:
                raise EvaluationPlanError(
                    f"{row.get('check_id')} references unregistered artifact types: {unknown}"
                )
        deterministic = row.get("deterministic")
        if isinstance(deterministic, dict):
            reference = str(deterministic.get("implementation_ref") or "")
            if not _resolve_callable(reference):
                raise EvaluationPlanError(
                    f"{row.get('check_id')} implementation is not callable: {reference}"
                )
    return registry


def _requirements(requirement_ir: dict[str, Any]) -> list[dict[str, Any]]:
    rows = requirement_ir.get("requirements")
    if not isinstance(rows, list):
        rows = requirement_ir.get("obligations")
    return [dict(row) for row in (rows or []) if isinstance(row, dict)]


def _requirement_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("requirement_id") or row.get("obligation_id") or "")


def _requirement_check(row: dict[str, Any]) -> str:
    check = row.get("check")
    value: Any
    if isinstance(check, dict):
        value = check.get("check_id") or check.get("id")
    else:
        value = check
    return str(
        value
        or row.get("verifier_id")
        or row.get("verification_method")
        or "not_machine_checkable"
    )


def _machine_check_required(row: dict[str, Any]) -> bool:
    check = row.get("check") if isinstance(row.get("check"), dict) else {}
    # `checkable` means that the Requirement Compiler supplied a named route
    # to a verifier.  That verifier may be an independent semantic evaluator.
    # Only the explicit `machine_checkable` flag promises a deterministic
    # implementation and is therefore allowed to trigger the stronger
    # pre-runtime implementation check below.
    return bool(
        row.get("machine_checkable") is True
        or check.get("machine_checkable") is True
    )


def _output_contracts(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in node.get("produces") or [] if isinstance(row, dict)]


def _copy_check(
    row: dict[str, Any], *, source: str, outputs: list[str]
) -> dict[str, Any]:
    return {
        "check_id": str(row.get("check_id") or ""),
        "source": source,
        "mode": str(row.get("mode") or ""),
        "applies_to_outputs": sorted(set(outputs)),
        "decision": str(row.get("decision") or ""),
        "deterministic": copy.deepcopy(row.get("deterministic")),
        "semantic": copy.deepcopy(row.get("semantic")),
    }


def _gate_policy(graph_node: dict[str, Any]) -> dict[str, Any]:
    gate = graph_node.get("evaluator_gate") if isinstance(graph_node.get("evaluator_gate"), dict) else {}
    repairs = graph_node.get("max_repair_attempts")
    if not isinstance(repairs, int) or isinstance(repairs, bool):
        repairs = ((gate.get("repair") or {}).get("max_attempts"))
    if not isinstance(repairs, int) or isinstance(repairs, bool):
        repairs = 1 if str(gate.get("on_fail") or "") == "repair_once_then_fail" else 0
    normalized_repairs = max(0, min(int(repairs), 2))
    on_fail = str(gate.get("on_fail") or "").strip()
    if not on_fail:
        on_fail = "repair_once_then_fail" if normalized_repairs else "fail"
    return {
        "kind": str(gate.get("kind") or "none"),
        "on_fail": on_fail,
        "maximum_repairs": normalized_repairs,
    }


_SELF_CHECK_RUNTIME_FIELDS = {
    "check.guard_decision_written": "guard_decision",
    "check.resource_binding_written": "resource_binding",
    "check.handoff_written": "handoff_md",
    "check.eval_written": "eval_json",
}


def _runtime_proof_field(obligation: dict[str, Any]) -> str:
    field = str(obligation.get("field") or "").strip()
    if field:
        return field
    kind = str(obligation.get("kind") or "").strip()
    requirement = str(obligation.get("requirement") or "").strip()
    if kind == "external_verifier":
        return "eval_json"
    mapped = _SELF_CHECK_RUNTIME_FIELDS.get(requirement)
    if mapped:
        return mapped
    if kind in {"pass_condition", "postcondition"} and requirement.endswith(" exists"):
        return requirement[: -len(" exists")].strip()
    return ""


def compile_evaluation_plan(
    requirement_ir: dict[str, Any],
    plan_ir: dict[str, Any],
    capsule_plan: dict[str, Any],
    task_graph: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve requirement checks and capsule proof criteria before runtime."""
    registry = copy.deepcopy(registry or load_evaluation_check_registry())
    check_by_id = {
        str(row.get("check_id") or ""): row
        for row in registry.get("checks") or []
        if isinstance(row, dict)
    }
    requirements = {_requirement_id(row): row for row in _requirements(requirement_ir)}
    capsule_nodes = {
        str(row.get("node_id") or ""): row
        for row in capsule_plan.get("nodes") or []
        if isinstance(row, dict)
    }
    graph_nodes = {
        str(row.get("id") or ""): row
        for row in task_graph.get("nodes") or []
        if isinstance(row, dict)
    }
    plan_nodes = {
        str(row.get("node_id") or ""): row
        for row in plan_ir.get("nodes") or []
        if isinstance(row, dict)
    }
    unresolved: list[dict[str, str]] = []
    compiled_nodes: list[dict[str, Any]] = []
    for graph_node in task_graph.get("nodes") or []:
        if not isinstance(graph_node, dict):
            continue
        node_id = str(graph_node.get("id") or "")
        semantic_contract = (
            graph_node.get("semantic_artifact_contract")
            if isinstance(graph_node.get("semantic_artifact_contract"), dict)
            else {}
        )
        semantic_node = plan_nodes.get(node_id) or {}
        outputs = [
            row
            for row in semantic_contract.get("produces") or []
            if isinstance(row, dict)
        ] or _output_contracts(semantic_node)
        output_types = [str(row.get("artifact_type") or "") for row in outputs if row.get("artifact_type")]
        checks: list[dict[str, Any]] = []
        seen_checks: set[tuple[str, tuple[str, ...]]] = set()

        def add_check(check: dict[str, Any], source: str, applies: list[str]) -> None:
            signature = (str(check.get("check_id") or ""), tuple(sorted(set(applies))))
            if not applies or signature in seen_checks:
                return
            seen_checks.add(signature)
            checks.append(_copy_check(check, source=source, outputs=applies))

        owned_source = (
            graph_node.get("requirement_ids")
            if "requirement_ids" in graph_node
            else semantic_node.get("requirement_ids") or []
        )
        owned_ids = [str(value) for value in owned_source or []]
        for requirement_id in owned_ids:
            requirement = requirements.get(requirement_id)
            if requirement is None:
                unresolved.append({"code": "REQUIREMENT_UNKNOWN", "node_id": node_id, "detail": requirement_id})
                continue
            check_id = _requirement_check(requirement)
            check = check_by_id.get(check_id)
            if check is None:
                unresolved.append({"code": "CHECK_UNREGISTERED", "node_id": node_id, "detail": check_id})
                continue
            bound_outputs = [
                str(output.get("artifact_type") or "")
                for output in outputs
                if check_id in [str(value) for value in output.get("verifier_ids") or []]
            ]
            if not bound_outputs:
                unresolved.append(
                    {
                        "code": "REQUIREMENT_CHECK_NOT_BOUND",
                        "node_id": node_id,
                        "detail": f"{requirement_id}:{check_id}",
                    }
                )
                continue
            if _machine_check_required(requirement) and check.get("mode") == "semantic":
                unresolved.append(
                    {
                        "code": "MACHINE_CHECK_IMPLEMENTATION_MISSING",
                        "node_id": node_id,
                        "detail": check_id,
                    }
                )
            add_check(check, "requirement", bound_outputs)

        for check in check_by_id.values():
            applies = check.get("applies_to") or {}
            if applies.get("kind") != "artifact_type" or applies.get("auto_apply") is not True:
                continue
            matched = sorted(set(output_types) & set(applies.get("artifact_types") or []))
            add_check(check, "artifact_auto", matched)

        criteria: list[dict[str, str]] = []
        for obligation in (capsule_nodes.get(node_id) or {}).get("proof_obligations") or []:
            if not isinstance(obligation, dict):
                continue
            text = str(obligation.get("requirement") or "").strip()
            source_capsule = str(obligation.get("source_capsule_id") or "unknown-capsule")
            kind = str(obligation.get("kind") or "unspecified")
            if text in check_by_id:
                add_check(check_by_id[text], "capsule_contract", output_types)
                continue
            runtime_field = _runtime_proof_field(obligation)
            criteria.append(
                {
                    "source_capsule_id": source_capsule,
                    "kind": kind,
                    "text": text or kind,
                    "field": runtime_field or None,
                    "disposition": "runtime_proof" if runtime_field else "semantic_review",
                }
            )

        gate_policy = _gate_policy(graph_nodes.get(node_id) or {})
        semantic_criteria = [
            str(value)
            for check in checks
            for value in ((check.get("semantic") or {}).get("rubric") or [])
        ]
        semantic_criteria.extend(
            row["text"] for row in criteria if row["disposition"] == "semantic_review"
        )
        semantic_criteria = list(dict.fromkeys(value for value in semantic_criteria if value))
        if gate_policy["kind"] == "llm_eval" and not semantic_criteria:
            semantic_criteria.append(
                "Judge whether the produced artifacts satisfy the node objective: "
                f"{graph_node.get('goal') or semantic_node.get('objective') or node_id}"
            )
        semantic_required = bool(semantic_criteria)
        if semantic_required and gate_policy["kind"] != "llm_eval":
            unresolved.append(
                {
                    "code": "SEMANTIC_REVIEW_GATE_MISSING",
                    "node_id": node_id,
                    "detail": f"gate_kind={gate_policy['kind']}",
                }
            )
        compiled_nodes.append(
            {
                "node_id": node_id,
                "placement": "after_node_output",
                "requirement_ids": owned_ids,
                "produced_artifacts": output_types,
                "checks": sorted(checks, key=lambda row: (row["check_id"], row["source"])),
                "capsule_contract_criteria": criteria,
                "gate_policy": gate_policy,
                "semantic_review": {
                    "required": semantic_required,
                    "evaluator_role": "evaluator",
                    "criteria": semantic_criteria,
                },
            }
        )

    artifact = {
        "schema_version": "solar.evaluation_plan.v1",
        "artifact_role": "runtime_artifact",
        "evaluation_plan_id": f"evaluation-plan-{plan_ir.get('plan_ir_id') or 'request'}",
        "requirement_ir_ref": {"sha256": sha256_payload(requirement_ir)},
        "plan_ir_ref": {"sha256": sha256_payload(plan_ir)},
        "capsule_plan_ref": {"sha256": sha256_payload(capsule_plan)},
        "task_graph_ref": {"sha256": sha256_payload(task_graph)},
        "registry_ref": {"registry_id": registry.get("registry_id"), "sha256": sha256_payload(registry)},
        "nodes": compiled_nodes,
        "unresolved": unresolved,
        "verdict": "fail" if unresolved else "pass",
    }
    _validate_schema(artifact, EVALUATION_PLAN_SCHEMA, "evaluation plan")
    return artifact


def validate_evaluation_plan(
    evaluation_plan: dict[str, Any],
    requirement_ir: dict[str, Any],
    plan_ir: dict[str, Any],
    capsule_plan: dict[str, Any],
    task_graph: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_evaluation_check_registry()
    check_ids = {
        str(row.get("check_id") or "")
        for row in registry.get("checks") or []
        if isinstance(row, dict)
    }
    checks: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            errors.append({"code": name.upper(), "detail": detail})

    record("requirement_ref", (evaluation_plan.get("requirement_ir_ref") or {}).get("sha256") == sha256_payload(requirement_ir))
    record("plan_ref", (evaluation_plan.get("plan_ir_ref") or {}).get("sha256") == sha256_payload(plan_ir))
    record("capsule_plan_ref", (evaluation_plan.get("capsule_plan_ref") or {}).get("sha256") == sha256_payload(capsule_plan))
    record("task_graph_ref", (evaluation_plan.get("task_graph_ref") or {}).get("sha256") == sha256_payload(task_graph))
    record("registry_ref", (evaluation_plan.get("registry_ref") or {}).get("sha256") == sha256_payload(registry))
    expected_nodes = {
        str(row.get("id") or "")
        for row in task_graph.get("nodes") or []
        if isinstance(row, dict)
    }
    actual_nodes = {str(row.get("node_id") or "") for row in evaluation_plan.get("nodes") or [] if isinstance(row, dict)}
    record("node_set", actual_nodes == expected_nodes, f"expected={sorted(expected_nodes)} actual={sorted(actual_nodes)}")
    used_checks = {
        str(check.get("check_id") or "")
        for node in evaluation_plan.get("nodes") or []
        for check in (node.get("checks") or [] if isinstance(node, dict) else [])
        if isinstance(check, dict)
    }
    unknown_checks = sorted(used_checks - check_ids)
    record("registered_checks", not unknown_checks, ",".join(unknown_checks))
    record("unresolved_empty", not evaluation_plan.get("unresolved"), json.dumps(evaluation_plan.get("unresolved") or [], sort_keys=True))
    record("verdict", evaluation_plan.get("verdict") == "pass", str(evaluation_plan.get("verdict")))
    artifact = {
        "schema_version": "solar.evaluation_plan_validation.v1",
        "artifact_role": "runtime_artifact",
        "validation_id": f"evaluation-plan-validation-{evaluation_plan.get('evaluation_plan_id') or 'request'}",
        "evaluation_plan_ref": {"sha256": sha256_payload(evaluation_plan)},
        "registry_ref": {"sha256": sha256_payload(registry)},
        "checks": checks,
        "errors": errors,
        "status": "fail" if errors else "pass",
    }
    _validate_schema(artifact, EVALUATION_VALIDATION_SCHEMA, "evaluation plan validation")
    return artifact
