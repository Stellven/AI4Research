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
    require_non_empty_list,
    run_cli,
    validate_schema,
)

SCHEMA = "claim_verdict.v1"
ALLOWED_VERDICTS = {"supported", "partially_supported", "not_supported", "insufficient", "inconclusive"}
NON_SUPPORTING_EVIDENCE_OUTCOMES = {"inconclusive", "failed", "insufficient", "insufficient_evidence"}


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    verdicts = require_non_empty_list(outputs(payload).get("verdicts"), "outputs.verdicts", reasons)
    top_limitations = limitations(payload)
    for index, verdict in enumerate(verdicts):
        if not isinstance(verdict, dict):
            reasons.append(f"verdicts[{index}] must be an object")
            continue
        if verdict.get("verdict") not in ALLOWED_VERDICTS:
            reasons.append(f"verdicts[{index}].verdict is not allowed")
        evidence_ids = verdict.get("evidence_ids")
        if not has_any_evidence_ids(evidence_ids):
            reasons.append(f"verdicts[{index}].evidence_ids must contain at least one id")
            evidence_ids = []
        claim_id = str(verdict.get("claim_id") or "")
        if claim_id and isinstance(evidence_ids, list) and claim_id not in evidence_ids:
            reasons.append(f"verdicts[{index}].evidence_ids must include the claim_id")
        if isinstance(evidence_ids, list) and not any(isinstance(item, str) and item.strip() and item != claim_id for item in evidence_ids):
            reasons.append(f"verdicts[{index}].evidence_ids must include experiment, static, or code evidence in addition to the claim id")
        if not verdict.get("limitations") and not top_limitations:
            reasons.append(f"verdicts[{index}] requires limitations")
        verdict_label = str(verdict.get("verdict") or "").strip()
        evidence_outcome = str(verdict.get("evidence_outcome") or "").strip()
        if evidence_outcome in NON_SUPPORTING_EVIDENCE_OUTCOMES and verdict_label not in {"inconclusive", "insufficient"}:
            reasons.append(f"verdicts[{index}] cannot upgrade {evidence_outcome} evidence to {verdict.get('verdict')}")
        support_classification = str(verdict.get("support_classification") or "").strip()
        if support_classification == "insufficient_evidence" and verdict_label not in {"inconclusive", "insufficient"}:
            reasons.append(f"verdicts[{index}] cannot classify insufficient evidence as {verdict_label}")
        if verdict.get("overclaim_risks") and verdict_label == "supported":
            reasons.append(f"verdicts[{index}] cannot support an over-broad claim without resolving overclaim_risks")
        scope_comparison = verdict.get("scope_comparison")
        if isinstance(scope_comparison, dict):
            scope_status = str(scope_comparison.get("status") or "")
            if verdict_label == "supported" and scope_status in {"mismatch", "insufficient"}:
                reasons.append(
                    f"verdicts[{index}] cannot support claim with structured scope status {scope_status}"
                )
        confidence = verdict.get("confidence")
        if isinstance(confidence, (int, float)) and confidence < 0.8:
            if not verdict.get("limitations") and not top_limitations:
                reasons.append(f"verdicts[{index}] confidence below 0.8 requires limitations")
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
