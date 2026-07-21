"""L4 InfluenceEvidencePacketCompiler — build the high-model-facing packet.

The packet is the ONLY object a high model is allowed to consume (contract
invariant). It carries all 7 ``local_scores``, the mapped evidence block, and the
``questions_for_high_model`` that frame the downstream reasoning. Scores are
deterministic heuristics in [0, 1]; a real scorer can replace ``_score_*`` without
changing the packet contract.
"""
from __future__ import annotations

from typing import Any

from .models import (
    LOCAL_SCORE_KEYS,
    InfluenceEvidencePacket,
    Statement,
    Thesis,
    empty_mapped_evidence,
)
from .thesis_mapper import has_any_evidence


def _clamp(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 3)


def compute_local_scores(
    thesis: Thesis,
    statements: list[Statement],
    mapped_evidence: dict[str, Any],
) -> dict[str, float]:
    n = len(statements) or 1
    distinct_sources = len({s.source for s in statements})
    has_evidence = has_any_evidence(mapped_evidence)
    avg_len = sum(len(s.text or "") for s in statements) / n
    scores = {
        "novelty": _clamp(0.5 + 0.1 * (1 if thesis.viewpoint_cluster != "general" else 0)),
        "signal_strength": _clamp(0.3 + 0.15 * n),
        "source_credibility": _clamp(0.4 + 0.1 * distinct_sources),
        "cross_source_resonance": _clamp(0.2 + 0.25 * (distinct_sources - 1)),
        "timeliness": _clamp(0.6 + 0.1 * (1 if any(s.timestamp for s in statements) else 0)),
        "actionability": _clamp(0.3 + (0.3 if has_evidence else 0.0)),
        "contrarian_score": _clamp(0.5 if avg_len > 80 else 0.3),
    }
    # Guarantee every contracted key is present.
    return {k: scores.get(k, 0.0) for k in LOCAL_SCORE_KEYS}


def build_questions(thesis: Thesis, mapped_evidence: dict[str, Any]) -> list[str]:
    questions = [
        f"What independent evidence supports or contradicts: {thesis.claim}",
        "Which concrete benchmarks, releases, or events would validate this thesis?",
    ]
    if mapped_evidence.get("coverage_gap"):
        gaps = ", ".join(mapped_evidence["coverage_gap"])
        questions.append(f"Coverage gaps to resolve before acting: {gaps}")
    return questions


def compile_packet(
    thesis: Thesis,
    statements: list[Statement],
    mapped_evidence: dict[str, Any] | None = None,
    generated_at: str = "",
) -> InfluenceEvidencePacket:
    mapped_evidence = mapped_evidence if mapped_evidence is not None else empty_mapped_evidence()
    return InfluenceEvidencePacket(
        packet_id=f"pkt-{thesis.thesis_id}",
        thesis_id=thesis.thesis_id,
        thesis_claim=thesis.claim,
        local_scores=compute_local_scores(thesis, statements, mapped_evidence),
        mapped_evidence=mapped_evidence,
        questions_for_high_model=build_questions(thesis, mapped_evidence),
        source_statements=[s.statement_id for s in statements],
        generated_at=generated_at,
    )
