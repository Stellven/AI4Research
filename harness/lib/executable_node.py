"""Canonical executable-node view shared by planning and runtime seams.

Planner graphs remain shape-free, but every node needs one immutable semantic
identity.  This module normalizes the planner-authored fields into the single
view consumed by validation, scheduling, physical binding, attribution, and
presentation. The planner may freeze an approved ordered candidate set, but
the runtime alone chooses which approved candidate is active for a dispatch.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "solar.executable_node.v1"


_ROLE_ALIASES = {
    "architect": "planner",
    "build": "builder",
    "builder-main": "builder",
    "implementation": "builder",
    "implementer": "builder",
    "judge": "evaluator",
    "reviewer": "evaluator",
    "verifier": "evaluator",
    "product": "pm",
    "product-manager": "pm",
}


_PHYSICAL_ROLE_COMPATIBILITY = {
    "planner": frozenset({"planner", "architect", "builder"}),
    "architect": frozenset({"architect", "planner", "builder"}),
    "builder": frozenset({"builder"}),
    "evaluator": frozenset({"evaluator", "builder"}),
    "pm": frozenset({"pm", "observer"}),
}

_GOVERNED_SOURCE_FIELDS = frozenset({
    "id",
    "goal",
    "description",
    "depends_on",
    "logical_operator",
    "node_kind",
    "allowed_operators",
    "allowed_capsules",
    "capability_capsule_id",
    "dispatch_task_type",
    "task_type",
    "type",
    "read_scope",
    "write_scope",
    "outputs",
    "acceptance",
    "required_skills",
    "required_capabilities",
    "proof_obligations",
    "evaluator_gate",
    "evaluation_policy",
    "gate",
    "max_repair_attempts",
    "on_human_review",
    "requirement_ids",
    "acceptance_ids",
    "planning_authority",
    "approved_physical_operator_ids",
    "capsule_plan_ir",
    "physical_plan_ir",
    "semantic_artifact_contract",
    "operator_requirements",
})

_FROZEN_PLAN_FIELDS = frozenset({
    "planning_authority",
    "approved_physical_operator_ids",
    "capsule_plan_ir",
    "physical_plan_ir",
    "semantic_artifact_contract",
    "operator_requirements",
})


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value]


def _logical_operator_registry_path() -> Path:
    explicit = str(os.environ.get("SOLAR_LOGICAL_OPERATORS") or "").strip()
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[1] / "config" / "logical-operators.json"


@lru_cache(maxsize=4)
def _logical_operator_roles(path_text: str) -> dict[str, str]:
    try:
        payload = json.loads(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    operators = payload.get("logical_operators") if isinstance(payload, dict) else {}
    if not isinstance(operators, dict):
        return {}
    return {
        str(name): str(spec.get("primary_role") or "").strip().lower()
        for name, spec in operators.items()
        if isinstance(spec, dict)
    }


def logical_role(node: Mapping[str, Any]) -> str:
    operator = logical_operator(node)
    if not operator:
        return ""
    return _logical_operator_roles(str(_logical_operator_registry_path())).get(operator, "")


def normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower().replace("_", "-")
    return _ROLE_ALIASES.get(role, role)


def logical_operator(node: Mapping[str, Any]) -> str:
    """Return the semantic operator, with legacy IR fallbacks for old graphs."""
    for source in (
        node,
        node.get("logical_plan_node") if isinstance(node.get("logical_plan_node"), Mapping) else {},
        node.get("capsule_plan_ir") if isinstance(node.get("capsule_plan_ir"), Mapping) else {},
        node.get("physical_plan_ir") if isinstance(node.get("physical_plan_ir"), Mapping) else {},
    ):
        value = str(source.get("logical_operator") or "").strip()
        if value:
            return value
    return ""


def dispatch_role(node: Mapping[str, Any]) -> str:
    """Return the node's logical execution role, never its selected host role."""
    primary_role = normalize_role(logical_role(node))
    if primary_role in {"builder", "planner", "evaluator", "pm"}:
        return primary_role
    if primary_role in {"knowledge-extractor", "auditor"}:
        if any(str(item or "").strip() for item in _as_string_list(node.get("write_scope"))):
            return "builder"
        return "planner" if primary_role == "knowledge-extractor" else "evaluator"
    if primary_role == "router":
        return "planner"

    for source in (
        node.get("logical_plan_node") if isinstance(node.get("logical_plan_node"), Mapping) else {},
        node.get("capsule_plan_ir") if isinstance(node.get("capsule_plan_ir"), Mapping) else {},
        node,
    ):
        for field in ("dispatch_role", "execution_role", "target_role", "role"):
            role = normalize_role(source.get(field))
            if role:
                return role

    allowed = node.get("allowed_operators") if isinstance(node.get("allowed_operators"), Mapping) else {}
    return normalize_role(allowed.get("role")) or "builder"


def physical_role(node: Mapping[str, Any]) -> str:
    """Return the planner's physical-role constraint, defaulting to logical role."""
    allowed = node.get("allowed_operators") if isinstance(node.get("allowed_operators"), Mapping) else {}
    return normalize_role(allowed.get("role")) or dispatch_role(node)


def physical_role_is_compatible(node: Mapping[str, Any]) -> bool:
    logical = dispatch_role(node)
    physical = physical_role(node)
    return physical in _PHYSICAL_ROLE_COMPATIBILITY.get(logical, frozenset({logical}))


def canonical_executable_node(node: Mapping[str, Any]) -> dict[str, Any]:
    """Build the immutable planner/runtime contract for one graph node.

    Runtime state (status, pane, dispatch id, leases, attempts, selected
    operator) is intentionally excluded. A physical operator is selected later
    from the contract's approved candidates when frozen planning is active.
    """
    allowed = node.get("allowed_operators") if isinstance(node.get("allowed_operators"), Mapping) else {}
    gate = node.get("evaluator_gate") if isinstance(node.get("evaluator_gate"), Mapping) else {}
    task_type = str(
        node.get("dispatch_task_type")
        or node.get("task_type")
        or node.get("type")
        or ""
    ).strip()
    repair_budget = node.get("max_repair_attempts")
    if repair_budget is None:
        repair_budget = {
            "fail": 0,
            "repair_once_then_fail": 1,
        }.get(str(gate.get("on_fail") or ""))
    frozen_execution = (
        str(node.get("planning_authority") or "") == "frozen_execution_plan_v1"
    )
    governed_source_fields = (
        _GOVERNED_SOURCE_FIELDS
        if frozen_execution
        else _GOVERNED_SOURCE_FIELDS - _FROZEN_PLAN_FIELDS
    )
    return {
        "schema_version": SCHEMA_VERSION,
        # Presence is evidence too: adding a default-valued governed field
        # after certification must still invalidate the plan certificate.
        "declared_fields": sorted(field for field in governed_source_fields if field in node),
        "node_id": str(node.get("id") or "").strip(),
        "goal": str(node.get("goal") or ""),
        "description": str(node.get("description") or ""),
        "depends_on": _as_string_list(node.get("depends_on")),
        "logical_operator": logical_operator(node),
        "logical_role": logical_role(node),
        "dispatch_role": dispatch_role(node),
        "physical_role": physical_role(node),
        "node_kind": str(node.get("node_kind") or ""),
        "allowed_operators": deepcopy(dict(allowed)),
        "allowed_capsules": _as_string_list(node.get("allowed_capsules")),
        "capability_capsule_id": str(node.get("capability_capsule_id") or "").strip(),
        "dispatch_task_type": task_type,
        "task_type": str(node.get("task_type") or ""),
        "node_type": str(node.get("type") or ""),
        "read_scope": _as_string_list(node.get("read_scope")),
        "write_scope": _as_string_list(node.get("write_scope")),
        "outputs": _as_string_list(node.get("outputs")),
        "acceptance": deepcopy(list(node.get("acceptance") or [])),
        "required_skills": _as_string_list(node.get("required_skills")),
        "required_capabilities": _as_string_list(node.get("required_capabilities")),
        "proof_obligations": deepcopy(list(node.get("proof_obligations") or [])),
        "evaluator_gate": deepcopy(dict(gate)),
        "evaluation_policy": deepcopy(
            node.get("evaluation_policy")
            if isinstance(node.get("evaluation_policy"), Mapping)
            else {}
        ),
        "gate": str(node.get("gate") or ""),
        "max_repair_attempts": repair_budget,
        "on_human_review": node.get("on_human_review"),
        "requirement_ids": _as_string_list(node.get("requirement_ids")),
        "acceptance_ids": _as_string_list(node.get("acceptance_ids")),
        "planning_authority": (
            "frozen_execution_plan_v1" if frozen_execution else ""
        ),
        "approved_physical_operator_ids": _as_string_list(
            node.get("approved_physical_operator_ids") if frozen_execution else []
        ),
        "capsule_plan_ir": deepcopy(
            node.get("capsule_plan_ir")
            if frozen_execution and isinstance(node.get("capsule_plan_ir"), Mapping)
            else {}
        ),
        "physical_plan_ir": deepcopy(
            node.get("physical_plan_ir")
            if frozen_execution and isinstance(node.get("physical_plan_ir"), Mapping)
            else {}
        ),
        "semantic_artifact_contract": deepcopy(
            node.get("semantic_artifact_contract")
            if frozen_execution and isinstance(node.get("semantic_artifact_contract"), Mapping)
            else {}
        ),
        "operator_requirements": deepcopy(
            node.get("operator_requirements")
            if frozen_execution and isinstance(node.get("operator_requirements"), Mapping)
            else {}
        ),
    }
