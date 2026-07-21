"""Convert AutoSci experiment designs to `experiment_plan.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    envelope = envelope or {}
    inputs = envelope.get("inputs") if isinstance(envelope.get("inputs"), dict) else {}
    execution_mode = str(
        raw.get("execution_mode")
        or inputs.get("execution_mode")
        or envelope.get("mode")
        or "fixture"
    )
    plan = {
        "experiment_id": str(raw.get("experiment_id") or "exp-001"),
        "objective": str(raw.get("objective") or "Validate the AutoSci adapter fixture path."),
        "hypothesis": str(raw.get("hypothesis") or "Fixture conversion produces valid Solar Evidence ABI output."),
        "variables": list(raw.get("variables") or ["adapter_action", "fixture_payload"]),
        "metrics": list(raw.get("metrics") or ["schema_present", "status_completed"]),
        "procedure": list(raw.get("procedure") or [
            "Run the bridge in fixture mode",
            "Write result.json and evidence.jsonl",
            "Validate required evidence fields",
        ]),
        "approval_required": bool(raw.get("approval_required", False)),
        "expected_artifacts": list(raw.get("expected_artifacts") or ["result.json", "evidence.jsonl"]),
        "execution_mode": execution_mode,
        "baseline": str(raw.get("baseline") or "fixture previous run output"),
        "baseline_absence_reason": str(raw.get("baseline_absence_reason") or ""),
        "success_criteria": list(raw.get("success_criteria") or ["fixture_passed == true"]),
        "command_allowlist": list(raw.get("command_allowlist") or ["python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment"]),
        "resource_limits": dict(raw.get("resource_limits") or {"network": "denied", "write_scope": "artifact_dir_only"}),
    }
    for key in ("review_llm", "evidence_ids", "source_context"):
        if raw.get(key) is not None:
            plan[key] = raw[key]
    return evidence_base(
        "experiment_plan.v1",
        envelope,
        {"experiment_plan": plan},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Fixture plan; no experiment has been executed."]),
    )
