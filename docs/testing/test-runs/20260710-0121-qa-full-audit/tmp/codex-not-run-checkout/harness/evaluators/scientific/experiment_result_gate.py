#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, has_any_evidence_ids, limitations, outputs, require_non_empty_list, run_cli, validate_schema

SCHEMA = "experiment_result.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    result = outputs(payload).get("result")
    if not isinstance(result, dict):
        reasons.append("outputs.result must be an object")
        return finish(payload, reasons, warnings, path=path)
    require_non_empty_list(result.get("metrics"), "outputs.result.metrics", reasons)
    if not str(result.get("execution_mode") or payload.get("inputs", {}).get("execution_mode") or "").strip():
        reasons.append("outputs.result.execution_mode must be present")
    if not str(result.get("command_run") or result.get("command") or "").strip():
        reasons.append("outputs.result.command_run must record the executed or simulated command")
    if not isinstance(result.get("logs"), list) or not result.get("logs"):
        reasons.append("outputs.result.logs must capture run logs or diagnostics")
    if not has_any_evidence_ids(result.get("evidence_ids")):
        reasons.append("outputs.result.evidence_ids must contain at least one id")
    if result.get("outcome") in {"failed", "inconclusive"} and not limitations(payload):
        reasons.append("failed or inconclusive outcomes require top-level limitations")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
