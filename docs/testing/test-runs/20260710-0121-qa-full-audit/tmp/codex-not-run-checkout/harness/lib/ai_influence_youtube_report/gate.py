"""Transcript quality gate for AI Influence YouTube report evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .compat import compat_adapter_v1
from .schema import GateDecision, TranscriptGrade


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _grade_from_metrics(row: dict[str, Any]) -> TranscriptGrade:
    upstream_grade = str(row.get("quality_tier") or "").upper()
    if upstream_grade in TranscriptGrade.__members__:
        return TranscriptGrade[upstream_grade]
    recall = float(row["entity_recall"])
    wer = float(row["wer"])
    density = float(row["segment_density"])
    if recall >= 0.85 and wer <= 0.15 and density >= 0.6:
        return TranscriptGrade.T0
    if recall >= 0.70 and wer <= 0.25 and density >= 0.4:
        return TranscriptGrade.T1
    if recall >= 0.50 and wer <= 0.40 and density >= 0.2:
        return TranscriptGrade.T2
    return TranscriptGrade.T3


def transcript_gate(video_id: str, transcript_status_row: dict[str, Any]) -> GateDecision:
    normalized = compat_adapter_v1({**transcript_status_row, "video_id": video_id or transcript_status_row.get("video_id")})
    grade = _grade_from_metrics(normalized)
    notes = [
        f"entity_recall={normalized['entity_recall']:.3f}",
        f"wer={normalized['wer']:.3f}",
        f"segment_density={normalized['segment_density']:.3f}",
    ]
    if grade == TranscriptGrade.T3:
        notes.append("excluded_from_core_evidence")
    elif grade == TranscriptGrade.T2:
        notes.append("weak_evidence_only")
    else:
        notes.append("core_evidence_allowed")
    return GateDecision(
        video_id=normalized["video_id"],
        grade=grade,
        entity_recall=normalized["entity_recall"],
        wer=normalized["wer"],
        segment_density=normalized["segment_density"],
        evidence_notes=notes,
        gated_at=_now(),
    )
