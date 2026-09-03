#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    check_artifact_paths,
    finish,
    has_any_evidence_ids,
    outputs,
    run_cli,
    validate_schema,
)

SCHEMA = "scientific_report_plan_review.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    out = outputs(payload)
    review = out.get("review") if isinstance(out.get("review"), dict) else {}
    findings = out.get("findings") if isinstance(out.get("findings"), list) else []
    artifact = out.get("artifact") if isinstance(out.get("artifact"), dict) else {}

    if review.get("review_stage") != "pre_draft_plan":
        reasons.append("report-plan review_stage must be pre_draft_plan")
    if review.get("target_schema") != "scientific_report_plan.v1":
        reasons.append("report-plan review target_schema must be scientific_report_plan.v1")
    if review.get("review_mode") != "review_llm" or review.get("review_available") is not True:
        reasons.append("report-plan review requires one completed Review LLM invocation")
    if not has_any_evidence_ids(review.get("evidence_ids")):
        reasons.append("report-plan review evidence_ids must contain at least one id")
    if artifact.get("schema") != "scientific_report_plan.v1":
        reasons.append("reviewed artifact schema must be scientific_report_plan.v1")
    if artifact.get("sha256") != review.get("reviewed_artifact_sha256"):
        reasons.append("reviewed artifact hash must match the review binding")
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            reasons.append(f"findings[{index}] must be an object")
            continue
        if not str(finding.get("suggestion") or "").strip():
            reasons.append(f"findings[{index}].suggestion must be present")

    # A pre-draft review is a diagnostic input to the drafter. High-severity
    # findings remain visible and do not become a second, implicit repair loop.
    if payload.get("status") == "completed":
        check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
