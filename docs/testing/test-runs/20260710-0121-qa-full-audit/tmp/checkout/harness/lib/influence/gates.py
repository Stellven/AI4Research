"""Quality gates for the influence plane (contract: 5 required gates).

Each gate is a pure function ``(...) -> GateResult``. ``fail_reasons`` are stable
string codes so S2/S3 tests can assert that every documented fail path is
reachable. Thresholds come from ``config/influence/gate_thresholds.yaml`` and are
passed in as a plain dict (no file I/O inside the gate functions).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import LOCAL_SCORE_KEYS, Statement, Thesis

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "statement_min_chars": 12,
    "thesis_min_confidence": 0.3,
    "thesis_min_claim_chars": 20,
    "evidence_min_local_scores": len(LOCAL_SCORE_KEYS),
    "transcript_min_quality": "low",
}

_TRANSCRIPT_QUALITY_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass
class GateResult:
    gate: str
    passed: bool
    fail_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"gate": self.gate, "passed": self.passed, "fail_reasons": list(self.fail_reasons)}


def _thr(thresholds: dict[str, Any] | None, key: str) -> Any:
    if thresholds and key in thresholds:
        return thresholds[key]
    return DEFAULT_THRESHOLDS[key]


def statement_gate(stmt: Statement, thresholds: dict[str, Any] | None = None) -> GateResult:
    reasons: list[str] = []
    if not stmt.text or len(stmt.text.strip()) < _thr(thresholds, "statement_min_chars"):
        reasons.append("text_too_short")
    if stmt.quality_flags.is_joke_or_meme:
        reasons.append("joke_or_meme")
    if stmt.quality_flags.is_marketing:
        reasons.append("marketing_content")
    if not stmt.author.handle:
        reasons.append("missing_author")
    return GateResult("statement", not reasons, reasons)


def transcript_gate(stmt: Statement, thresholds: dict[str, Any] | None = None) -> GateResult:
    reasons: list[str] = []
    tq = stmt.quality_flags.transcript_quality
    if tq is None:
        # Non-transcript statement: gate is N/A and passes trivially.
        return GateResult("transcript", True, [])
    min_q = _thr(thresholds, "transcript_min_quality")
    if tq not in _TRANSCRIPT_QUALITY_ORDER:
        reasons.append("unknown_transcript_quality")
    elif _TRANSCRIPT_QUALITY_ORDER[tq] < _TRANSCRIPT_QUALITY_ORDER.get(min_q, 0):
        reasons.append("transcript_quality_too_low")
    return GateResult("transcript", not reasons, reasons)


def thesis_gate(thesis: Thesis, thresholds: dict[str, Any] | None = None) -> GateResult:
    reasons: list[str] = []
    if not thesis.claim or len(thesis.claim.strip()) < _thr(thresholds, "thesis_min_claim_chars"):
        reasons.append("claim_too_short")
    if thesis.confidence < _thr(thresholds, "thesis_min_confidence"):
        reasons.append("confidence_too_low")
    if not thesis.derived_from_statements:
        reasons.append("no_source_statements")
    return GateResult("thesis", not reasons, reasons)


def evidence_mapping_gate(packet: dict[str, Any], thresholds: dict[str, Any] | None = None) -> GateResult:
    reasons: list[str] = []
    local_scores = packet.get("local_scores", {})
    missing = [k for k in LOCAL_SCORE_KEYS if k not in local_scores]
    if missing:
        reasons.append("incomplete_local_scores")
    if "mapped_evidence" not in packet:
        reasons.append("missing_mapped_evidence")
    if not packet.get("questions_for_high_model"):
        reasons.append("no_questions_for_high_model")
    return GateResult("evidence_mapping", not reasons, reasons)


def compliance_gate(packet: dict[str, Any]) -> GateResult:
    """Enforce the contract invariants on what reaches a high model.

    - high model may only consume a packet (must carry questions_for_high_model)
    - the Thesis layer must not be bypassed (packet must reference a thesis)
    - raw post lists must not be smuggled into the high-model payload
    """
    reasons: list[str] = []
    if not packet.get("thesis_id"):
        reasons.append("thesis_layer_bypassed")
    if not packet.get("questions_for_high_model"):
        reasons.append("no_high_model_questions")
    if "raw_posts" in packet or "raw_metadata" in packet:
        reasons.append("raw_post_leak_to_high_model")
    return GateResult("compliance", not reasons, reasons)
