#!/usr/bin/env python3
"""Deterministically validate exact, safety-bounded experiment approval."""
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, outputs, run_cli, validate_schema


SCHEMA = "experiment_approval.v1"
SANDBOX_MODES = {"isolated", "container", "process_restricted"}


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    approval = outputs(payload).get("approval")
    if not isinstance(approval, dict):
        reasons.append("outputs.approval must be an object")
        return finish(payload, reasons, warnings, path=path)

    if payload.get("status") != "completed":
        reasons.append("experiment approval evidence must have completed status")
    if approval.get("decision") != "approved":
        reasons.append("outputs.approval.decision must be approved")
    if not str(approval.get("approval_ref") or "").strip():
        reasons.append("outputs.approval.approval_ref must be present")
    if "execute_experiment" not in set(approval.get("approved_capabilities") or []):
        reasons.append("outputs.approval.approved_capabilities must include execute_experiment")

    sandbox = approval.get("sandbox")
    if not isinstance(sandbox, dict):
        reasons.append("outputs.approval.sandbox must be an object")
    else:
        if str(sandbox.get("mode") or "") not in SANDBOX_MODES:
            reasons.append("outputs.approval.sandbox.mode must be isolated, container, or process_restricted")
        if sandbox.get("network") is not False:
            reasons.append("outputs.approval.sandbox.network must be false")
        write_scope = sandbox.get("write_scope")
        if not isinstance(write_scope, list) or not write_scope or not all(
            isinstance(item, str) and item.strip() for item in write_scope
        ):
            reasons.append("outputs.approval.sandbox.write_scope must contain at least one path")

    if approval.get("reasons"):
        reasons.append("approved experiment evidence must not retain rejection reasons")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
