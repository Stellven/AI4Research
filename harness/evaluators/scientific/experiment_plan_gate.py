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
    # Only an explicit version/profile discriminator opts into the complete
    # readiness contract. Incidental legacy metadata must remain compatible.
    preflight_claim = plan.get("approval_preflight")
    readiness_asserted = plan.get("execution_ready") is True or (
        isinstance(preflight_claim, dict) and preflight_claim.get("status") in {"ready", "not_required"}
    )
    contract_declared = (
        plan.get("verification_contract_version") is not None
        or plan.get("readiness_profile") is not None
        or readiness_asserted
    )
    if contract_declared:
        if plan.get("verification_contract_version") != "1":
            reasons.append("outputs.experiment_plan.verification_contract_version must be 1")
        profile = str(plan.get("readiness_profile") or "")
        if profile not in {"deterministic_local_fixture", "human_approved_local"}:
            reasons.append("outputs.experiment_plan.readiness_profile is unsupported")
        if profile == "deterministic_local_fixture" and (execution_mode != "fixture" or plan.get("approval_required") is not False):
            reasons.append("deterministic_local_fixture requires execution_mode=fixture and approval_required=false")
        if profile == "human_approved_local" and (execution_mode != "human_approved" or plan.get("approval_required") is not True):
            reasons.append("human_approved_local requires execution_mode=human_approved and approval_required=true")
        if not str(plan.get("workspace_root") or "").strip():
            reasons.append("outputs.experiment_plan.workspace_root must be present")
        runner = plan.get("runner")
        if not isinstance(runner, dict) or not str(runner.get("path") or "").strip():
            reasons.append("outputs.experiment_plan.runner.path must be present")
        if plan.get("network_access") != "denied":
            reasons.append("outputs.experiment_plan.network_access must be denied")
        require_non_empty_list(plan.get("write_scope"), "outputs.experiment_plan.write_scope", reasons)
        dataset = plan.get("dataset")
        if not isinstance(dataset, dict) or not all(str(dataset.get(key) or "").strip() for key in ("path", "format", "role")):
            reasons.append("outputs.experiment_plan.dataset must identify path, format, and role")
        variants = plan.get("variants")
        if not isinstance(variants, list) or len(variants) < 2 or not all(
            isinstance(item, dict) and item.get("name") and item.get("description") for item in variants
        ):
            reasons.append("outputs.experiment_plan.variants must define at least baseline and treatment variants")
        thresholds = plan.get("thresholds")
        if not isinstance(thresholds, list) or not thresholds or not all(
            isinstance(item, dict) and item.get("metric") and item.get("operator") and "value" in item
            for item in thresholds
        ):
            reasons.append("outputs.experiment_plan.thresholds must define measurable acceptance thresholds")
        if not isinstance(plan.get("random_seed"), int):
            reasons.append("outputs.experiment_plan.random_seed must be an integer")
        require_non_empty_list(plan.get("stopping_conditions"), "outputs.experiment_plan.stopping_conditions", reasons)
        require_non_empty_list(plan.get("command_argv"), "outputs.experiment_plan.command_argv", reasons)
        preflight = plan.get("approval_preflight")
        if not isinstance(preflight, dict):
            reasons.append("outputs.experiment_plan.approval_preflight must be an object")
        if plan.get("execution_ready") is True and (
            not isinstance(preflight, dict)
            or preflight.get("status") not in ({"ready"} if profile == "human_approved_local" else {"not_required"})
            or preflight.get("command_authorized") is not True
            or preflight.get("before_state_ready") is not True
        ):
            reasons.append("execution_ready=true requires a ready approval preflight for the exact command and before-state")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
