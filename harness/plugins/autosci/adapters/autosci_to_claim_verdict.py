"""Convert AutoSci verdict-like data to `claim_verdict.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


OUTCOME_TO_VERDICT = {
    "supports": "supported",
    "partially_supports": "partially_supported",
    "refutes": "not_supported",
    "insufficient": "insufficient",
    "insufficient_evidence": "insufficient",
    "inconclusive": "inconclusive",
    "failed": "inconclusive",
}


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    outcome = str(raw.get("evidence_outcome") or raw.get("outcome") or "inconclusive")
    verdict_label = str(raw.get("verdict") or OUTCOME_TO_VERDICT.get(outcome, "inconclusive"))
    limitations = list(raw.get("limitations") or ["fixture-mode verdict; not a real scientific claim verification"])
    verdict = {
        "claim_id": str(raw.get("claim_id") or "claim-001"),
        "verdict": verdict_label,
        "confidence": float(raw.get("confidence", 0.35 if verdict_label == "insufficient" else (0.5 if verdict_label == "inconclusive" else 0.8))),
        "basis": str(raw.get("basis") or "Fixture experiment result is linked for adapter smoke validation."),
        "evidence_ids": list(raw.get("evidence_ids") or ["evidence:autosci-fixture"]),
        "limitations": limitations,
        "evidence_outcome": outcome,
        "claim_evidence_ids": list(raw.get("claim_evidence_ids") or []),
        "experiment_evidence_ids": list(raw.get("experiment_evidence_ids") or []),
        "code_evidence_ids": list(raw.get("code_evidence_ids") or []),
    }
    for key in ("experiment_id", "review_llm", "metrics", "support_classification", "overclaim_risks", "classification_reason"):
        if raw.get(key) is not None:
            verdict[key] = raw[key]
    return evidence_base(
        "claim_verdict.v1",
        envelope,
        {"verdicts": [verdict]},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=limitations,
    )
