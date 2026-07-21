#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (  # noqa: E402
    check_artifact_paths,
    finish,
    has_any_evidence_ids,
    limitations,
    outputs,
    require_non_empty_list,
    require_non_empty_string,
    run_cli,
    validate_schema,
)

SCHEMA = "autosci_operator_smoke.v1"


def _count(items: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("execution_status") == status)


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    smoke = outputs(payload).get("smoke")
    if not isinstance(smoke, dict):
        reasons.append("outputs.smoke must be an object")
        return finish(payload, reasons, warnings, path=path)

    actions_raw = require_non_empty_list(smoke.get("core_actions"), "outputs.smoke.core_actions", reasons)
    actions: list[dict[str, Any]] = []
    for index, action in enumerate(actions_raw):
        if not isinstance(action, dict):
            reasons.append(f"core_actions[{index}] must be an object")
            continue
        actions.append(action)
        require_non_empty_string(action.get("action"), f"core_actions[{index}].action", reasons)
        require_non_empty_string(action.get("schema"), f"core_actions[{index}].schema", reasons)
        require_non_empty_string(action.get("evidence_path"), f"core_actions[{index}].evidence_path", reasons)
        status = str(action.get("status") or "")
        gate_status = str(action.get("gate_status") or "")
        if status == "failed" or gate_status == "failed":
            reasons.append(f"core_actions[{index}] failed: {action.get('action')}")
        if not has_any_evidence_ids(action.get("evidence_ids")):
            reasons.append(f"core_actions[{index}].evidence_ids must contain at least one id")

    items_raw = require_non_empty_list(smoke.get("items"), "outputs.smoke.items", reasons)
    items: list[dict[str, Any]] = []
    seen_skills: set[str] = set()
    core_action_names = {str(action.get("action") or "") for action in actions}
    for index, item in enumerate(items_raw):
        if not isinstance(item, dict):
            reasons.append(f"items[{index}] must be an object")
            continue
        items.append(item)
        skill = require_non_empty_string(item.get("native_skill"), f"items[{index}].native_skill", reasons)
        if skill in seen_skills:
            reasons.append(f"items[{index}].native_skill duplicates route for {skill}")
        seen_skills.add(skill)
        for field in (
            "autosci_feature",
            "solar_backend_action",
            "physical_operator",
            "side_effect_policy",
            "execution_status",
        ):
            require_non_empty_string(item.get(field), f"items[{index}].{field}", reasons)
        execution_status = str(item.get("execution_status") or "")
        side_effect_policy = str(item.get("side_effect_policy") or "")
        smoke_steps = item.get("smoke_steps") if isinstance(item.get("smoke_steps"), list) else []
        if execution_status in {"completed", "partial"}:
            if not smoke_steps:
                reasons.append(f"items[{index}] {execution_status} route requires at least one smoke step")
            missing_steps = sorted(str(step) for step in smoke_steps if str(step) not in core_action_names)
            if missing_steps:
                reasons.append(f"items[{index}] references missing smoke steps: {', '.join(missing_steps)}")
            require_non_empty_list(item.get("evidence_paths"), f"items[{index}].evidence_paths", reasons)
            require_non_empty_list(item.get("gate_statuses"), f"items[{index}].gate_statuses", reasons)
        if execution_status == "gated":
            if side_effect_policy != "approval_required":
                reasons.append(f"items[{index}] gated route requires approval_required side effect policy")
            if not item.get("limitations"):
                reasons.append(f"items[{index}] gated route requires limitations")
        if execution_status in {"failed", "unbound"}:
            reasons.append(f"items[{index}] route is {execution_status}: {skill}")
        if not has_any_evidence_ids(item.get("evidence_ids")):
            reasons.append(f"items[{index}].evidence_ids must contain at least one id")

    expected_route_count = int(smoke.get("route_count") or 0)
    if expected_route_count != len(items):
        reasons.append(f"route_count={expected_route_count} does not match items length={len(items)}")
    expected_core_count = int(smoke.get("core_action_count") or 0)
    if expected_core_count != len(actions):
        reasons.append(f"core_action_count={expected_core_count} does not match core_actions length={len(actions)}")
    bound_count = int(smoke.get("bound_count") or 0)
    if bound_count != len(items) - _count(items, "unbound"):
        reasons.append("bound_count does not match route item binding status")

    for field, status in (
        ("completed_count", "completed"),
        ("partial_count", "partial"),
        ("gated_count", "gated"),
        ("failed_count", "failed"),
        ("unbound_count", "unbound"),
    ):
        expected = int(smoke.get(field) or 0)
        actual = _count(items, status)
        if expected != actual:
            reasons.append(f"{field}={expected} does not match actual {actual}")
    if int(smoke.get("failed_count") or 0):
        reasons.append("operator smoke must not contain failed route items")
    if int(smoke.get("unbound_count") or 0):
        reasons.append("operator smoke must not contain unbound route items")
    if int(smoke.get("gated_count") or 0):
        warnings.append("operator smoke includes approval-gated operators that were not externally executed")
    if not limitations(payload):
        reasons.append("top-level limitations must describe smoke scope")
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
