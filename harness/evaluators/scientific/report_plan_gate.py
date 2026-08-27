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
    outputs,
    require_non_empty_list,
    run_cli,
    validate_schema,
)

SCHEMA = "scientific_report_plan.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    plan = outputs(payload).get("report_plan")
    if not isinstance(plan, dict):
        reasons.append("outputs.report_plan must be an object")
        return finish(payload, reasons, warnings, path=path)
    if not has_any_evidence_ids(plan.get("evidence_ids")):
        reasons.append("outputs.report_plan.evidence_ids must contain at least one id")
    sections = require_non_empty_list(
        plan.get("sections"), "outputs.report_plan.sections", reasons
    )
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            reasons.append(f"outputs.report_plan.sections[{index}] must be an object")
            continue
        if not has_any_evidence_ids(section.get("evidence_ids")):
            reasons.append(
                f"outputs.report_plan.sections[{index}].evidence_ids must contain at least one id"
            )
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
