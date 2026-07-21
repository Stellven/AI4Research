#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, outputs, require_non_empty_list, run_cli, validate_schema

SCHEMA = "experiment_plan.v1"
SAFE_EXECUTION_MODES = {
    "fixture",
    "dry-run",
    "bounded",
    "bounded-local",
    "benchmark",
    "known-safe-benchmark",
    "human_approved",
    "approved-external",
}
APPROVAL_REQUIRED_MODES = {"human_approved", "approved-external"}


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    plan = outputs(payload).get("experiment_plan")
    if not isinstance(plan, dict):
        reasons.append("outputs.experiment_plan must be an object")
        return finish(payload, reasons, warnings, path=path)
    for field in ("variables", "metrics", "procedure", "expected_artifacts"):
        require_non_empty_list(plan.get(field), f"outputs.experiment_plan.{field}", reasons)
    execution_mode = str(plan.get("execution_mode") or payload.get("inputs", {}).get("execution_mode") or "")
    if not execution_mode:
        reasons.append("outputs.experiment_plan.execution_mode must be present")
    elif execution_mode not in SAFE_EXECUTION_MODES:
        reasons.append("experiment execution_mode must be fixture, dry-run, bounded-local, benchmark, or approved-external")
    if execution_mode in APPROVAL_REQUIRED_MODES and not plan.get("approval_required"):
        reasons.append(f"{execution_mode} execution mode requires approval_required=true")
    if not plan.get("baseline") and not plan.get("baseline_absence_reason"):
        reasons.append("outputs.experiment_plan must include baseline or baseline_absence_reason")
    require_non_empty_list(plan.get("success_criteria"), "outputs.experiment_plan.success_criteria", reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
