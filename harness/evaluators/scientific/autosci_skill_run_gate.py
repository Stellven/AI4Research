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
    require_non_empty_string,
    run_cli,
    validate_schema,
)

SCHEMA = "autosci_skill_run.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    skill_run = outputs(payload).get("skill_run")
    if not isinstance(skill_run, dict):
        reasons.append("outputs.skill_run must be an object")
        return finish(payload, reasons, warnings, path=path)

    selected_skill = require_non_empty_string(skill_run.get("selected_skill"), "outputs.skill_run.selected_skill", reasons)
    require_non_empty_string(skill_run.get("autosci_command"), "outputs.skill_run.autosci_command", reasons)
    execution_status = str(skill_run.get("execution_status") or "")
    side_effect_policy = str(skill_run.get("side_effect_policy") or "")
    evidence_status = str(payload.get("status") or "")
    if execution_status in {"partial", "gated"} and evidence_status == "completed":
        reasons.append(
            "partial or gated skill runs must use top-level status inconclusive, not completed"
        )
    if execution_status == "gated" and side_effect_policy != "approval_required":
        reasons.append("gated execution requires approval_required side_effect_policy")
    if execution_status == "failed":
        reasons.append(f"skill execution failed: {selected_skill}")
    if execution_status in {"partial", "gated"}:
        warnings.append(f"skill route is {execution_status}; limitations must be read before treating as full parity")

    actions = skill_run.get("actions")
    if not isinstance(actions, list):
        reasons.append("outputs.skill_run.actions must be an array")
        actions = []
    expected_count = int(skill_run.get("action_count") or 0)
    if expected_count != len(actions):
        reasons.append(f"action_count={expected_count} does not match actions length={len(actions)}")

    passed = schema_only = failed = 0
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            reasons.append(f"actions[{index}] must be an object")
            continue
        require_non_empty_string(action.get("action"), f"actions[{index}].action", reasons)
        require_non_empty_string(action.get("schema"), f"actions[{index}].schema", reasons)
        require_non_empty_string(action.get("evidence_path"), f"actions[{index}].evidence_path", reasons)
        status = str(action.get("status") or "")
        gate_status = str(action.get("gate_status") or "")
        if status == "passed":
            passed += 1
        elif status == "schema_only":
            schema_only += 1
        elif status == "failed":
            failed += 1
        if status == "failed" or gate_status == "failed":
            reasons.append(f"actions[{index}] failed: {action.get('action')}")
        if not has_any_evidence_ids(action.get("evidence_ids")):
            reasons.append(f"actions[{index}].evidence_ids must contain at least one id")

    if int(skill_run.get("passed_count") or 0) != passed:
        reasons.append("passed_count does not match action statuses")
    if int(skill_run.get("schema_only_count") or 0) != schema_only:
        reasons.append("schema_only_count does not match action statuses")
    if int(skill_run.get("failed_count") or 0) != failed:
        reasons.append("failed_count does not match action statuses")
    if failed:
        reasons.append("skill run must not contain failed bridge actions")
    if expected_count == 0 and execution_status not in {"gated", "partial"}:
        reasons.append("zero-action skill runs must be partial or gated")
    if not limitations(payload):
        reasons.append("top-level limitations must describe skill run scope")
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
