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
    limitations,
    outputs,
    run_cli,
    validate_schema,
)

SCHEMA = "artifact_review.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    out = outputs(payload)
    review = out.get("review")
    findings = out.get("findings")
    if not isinstance(review, dict):
        reasons.append("outputs.review must be an object")
        review = {}
    if not isinstance(findings, list):
        reasons.append("outputs.findings must be a list")
        findings = []

    mode = str(review.get("review_mode") or "")
    review_llm = review.get("review_llm") if isinstance(review.get("review_llm"), dict) else {}
    if mode == "local_surrogate" and review.get("review_available") is not False:
        reasons.append("local_surrogate review must set review_available=false")
    if mode == "review_llm" and review.get("review_available") is not True:
        reasons.append("review_llm review must set review_available=true")
    if mode == "local_surrogate" and str(review_llm.get("status") or "") not in {"unavailable", "invalid"}:
        reasons.append("local_surrogate review must include review_llm.status unavailable or invalid")
    if mode == "review_llm" and str(review_llm.get("status") or "") != "completed":
        reasons.append("review_llm review must include review_llm.status completed")
    if not has_any_evidence_ids(review.get("evidence_ids")):
        reasons.append("outputs.review.evidence_ids must contain at least one id")
    if mode == "local_surrogate" and review.get("recommendation") == "pass_with_review_required":
        if not limitations(payload):
            reasons.append("local surrogate pass requires limitations explaining final Review LLM requirement")
    if mode == "local_surrogate" and not any("Review LLM" in item for item in limitations(payload)):
        reasons.append("local surrogate review must disclose missing Review LLM evidence")

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            reasons.append(f"findings[{index}] must be an object")
            continue
        if finding.get("severity") == "high" and review.get("recommendation") == "pass_with_review_required":
            reasons.append("high-severity findings cannot pass")
        if not finding.get("suggestion"):
            reasons.append(f"findings[{index}].suggestion must be present")

    if payload.get("status") == "completed":
        check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
