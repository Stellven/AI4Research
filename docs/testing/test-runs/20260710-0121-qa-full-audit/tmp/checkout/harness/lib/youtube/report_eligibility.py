"""Report eligibility gate for transcript-derived evidence packs."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvidencePack:
    transcript_id: str
    video_id: str
    quality_tier: str
    segment_refs: list[str]
    source_strength: str = "strong"
    transcript_status: str = "success"
    transcript_clean_present: bool = True
    planned_citations_retained: bool = True
    raw_evidence_strength: str = "strong"


@dataclass
class EligibilityDecision:
    eligible: bool
    reject_codes: list[str] = field(default_factory=list)


def build_evidence_pack(
    *,
    transcript_id: str,
    video_id: str,
    quality_tier: str,
    segment_refs: list[str],
    **kwargs,
) -> EvidencePack:
    return EvidencePack(
        transcript_id=transcript_id,
        video_id=video_id,
        quality_tier=quality_tier,
        segment_refs=segment_refs,
        **kwargs,
    )


def evaluate_report_eligibility(pack: EvidencePack) -> EligibilityDecision:
    reject_codes: list[str] = []
    if pack.quality_tier == "T3" and pack.raw_evidence_strength != "weak":
        reject_codes.append("T3_in_core")
    if pack.transcript_status == "missing" and pack.transcript_clean_present:
        reject_codes.append("missing_but_clean_present")
    if pack.source_strength == "low" and pack.raw_evidence_strength != "weak":
        reject_codes.append("source_quality_low_not_weak")
    if not pack.planned_citations_retained:
        reject_codes.append("planned_citation_lost")
    if not pack.segment_refs:
        reject_codes.append("segment_refs_missing")
    return EligibilityDecision(eligible=not reject_codes, reject_codes=reject_codes)
