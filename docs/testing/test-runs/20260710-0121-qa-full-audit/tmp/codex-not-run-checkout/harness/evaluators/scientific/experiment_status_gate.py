#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    finish,
    has_any_evidence_ids,
    limitations,
    outputs,
    require_non_empty_list,
    run_cli,
    validate_schema,
)

SCHEMA = "experiment_status.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    report = outputs(payload).get("status_report")
    if not isinstance(report, dict):
        reasons.append("outputs.status_report must be an object")
        return finish(payload, reasons, warnings, path=path)
    require_non_empty_list(report.get("observations"), "outputs.status_report.observations", reasons)
    require_non_empty_list(report.get("next_actions"), "outputs.status_report.next_actions", reasons)
    if not has_any_evidence_ids(report.get("evidence_ids")):
        reasons.append("outputs.status_report.evidence_ids must contain at least one id")
    state = str(report.get("state") or "")
    if state in {"blocked", "unknown"} and not limitations(payload):
        reasons.append("blocked or unknown status requires top-level limitations")
    if state == "completed" and not has_any_evidence_ids(report.get("evidence_ids")):
        reasons.append("completed status requires result or run evidence ids")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
