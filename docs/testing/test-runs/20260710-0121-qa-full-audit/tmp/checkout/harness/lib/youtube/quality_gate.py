"""Two-phase transcript quality gate for YouTube transcripts.

Phase 1 computes six baseline sub-scores without technical-term correction.
Phase 2 reruns only for T0/T1/T2 candidates with vocab-assisted term matching.
"""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Any


TIER_THRESHOLDS = {
    "T0": 0.85,
    "T1": 0.70,
    "T2": 0.50,
}


@dataclass
class QualityGateResult:
    preliminary_score: float
    preliminary_tier: str
    final_score: float
    final_tier: str
    phase2_applied: bool
    technical_term_hit_rate: float | None
    sub_scores: dict[str, float]
    trigger_source: str
    corrected_terms: list[str]


def score_to_tier(score: float) -> str:
    if score >= TIER_THRESHOLDS["T0"]:
        return "T0"
    if score >= TIER_THRESHOLDS["T1"]:
        return "T1"
    if score >= TIER_THRESHOLDS["T2"]:
        return "T2"
    return "T3"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _length_score(text: str) -> float:
    token_count = len(re.findall(r"\w+", text))
    if token_count == 0:
        return 0.0
    return _clamp(token_count / 80.0)


def _punctuation_score(text: str) -> float:
    if not text.strip():
        return 0.0
    sentence_endings = len(re.findall(r"[.!?。！？]", text))
    line_breaks = text.count("\n")
    return _clamp((sentence_endings + line_breaks + 1) / 8.0)


def _ascii_ratio_score(text: str) -> float:
    if not text:
        return 0.0
    useful = sum(1 for ch in text if ch.isalnum())
    if useful == 0:
        return 0.0
    printable = sum(1 for ch in text if ch.isprintable() and not ch.isspace())
    return _clamp(printable / max(useful, 1))


def _term_hit_rate(text: str, vocab_terms: list[str]) -> tuple[float, list[str]]:
    normalized = text.lower()
    hits: list[str] = []
    for term in vocab_terms:
        if term and term.lower() in normalized:
            hits.append(term)
    if not vocab_terms:
        return 0.0, []
    return _clamp(len(set(hits)) / len({term for term in vocab_terms if term})), sorted(set(hits))


def evaluate_quality(
    *,
    text: str,
    coverage_ratio: float,
    hallucination_risk: float,
    source_reliability: float = 0.8,
    vocab_terms: list[str] | None = None,
    corrected_text: str | None = None,
    trigger_source: str = "primary",
) -> QualityGateResult:
    """Run the two-phase quality gate."""
    base_scores = {
        "coverage_ratio": _clamp(coverage_ratio),
        "inverse_hallucination": 1.0 - _clamp(hallucination_risk),
        "source_reliability": _clamp(source_reliability),
        "length_score": _length_score(text),
        "punctuation_score": _punctuation_score(text),
        "ascii_ratio_score": _ascii_ratio_score(text),
    }
    preliminary_score = round(sum(base_scores.values()) / len(base_scores), 4)
    preliminary_tier = score_to_tier(preliminary_score)

    phase2_applied = preliminary_tier != "T3"
    technical_term_hit_rate: float | None = None
    corrected_terms: list[str] = []
    final_score = preliminary_score
    final_tier = preliminary_tier

    if phase2_applied:
        technical_term_hit_rate, corrected_terms = _term_hit_rate(corrected_text or text, vocab_terms or [])
        final_score = round(
            ((preliminary_score * len(base_scores)) + technical_term_hit_rate) / (len(base_scores) + 1),
            4,
        )
        final_tier = score_to_tier(final_score)

    return QualityGateResult(
        preliminary_score=preliminary_score,
        preliminary_tier=preliminary_tier,
        final_score=final_score,
        final_tier=final_tier,
        phase2_applied=phase2_applied,
        technical_term_hit_rate=technical_term_hit_rate,
        sub_scores=base_scores,
        trigger_source=trigger_source,
        corrected_terms=corrected_terms,
    )


def persist_quality_check(
    conn: sqlite3.Connection,
    *,
    transcript_id: str,
    result: QualityGateResult,
    issues: list[str] | None = None,
    check_version: str = "youtube_quality_gate_v1",
    commit: bool = True,
) -> str:
    """Persist a quality check record into `quality_checks`."""
    digest = hashlib.sha256(
        f"{transcript_id}:{check_version}:{result.final_score}:{result.final_tier}".encode("utf-8")
    ).hexdigest()[:12]
    check_id = f"qc-{transcript_id}-{digest}"
    conn.execute(
        """INSERT OR REPLACE INTO quality_checks
           (check_id, transcript_id, check_version, quality_score, quality_tier,
            coverage_ratio, hallucination_risk, issues_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            check_id,
            transcript_id,
            check_version,
            result.final_score,
            result.final_tier,
            result.sub_scores.get("coverage_ratio"),
            1.0 - result.sub_scores.get("inverse_hallucination", 1.0),
            str(issues or []),
        ),
    )
    if commit:
        conn.commit()
    return check_id
