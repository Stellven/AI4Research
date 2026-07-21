"""Compatibility adapters for upstream transcript-status rows."""

from __future__ import annotations

from typing import Any


class TranscriptStatusDriftError(ValueError):
    """Raised when transcript-status input no longer matches the expected shape."""


ALIASES = {
    "video_id": ("video_id", "id", "youtube_video_id"),
    "quality_tier": ("quality_tier", "tier", "transcript_quality_tier", "grade"),
    "entity_recall": ("entity_recall", "technical_term_hit_rate"),
    "wer": ("wer", "word_error_rate"),
    "segment_density": ("segment_density", "segments_per_minute"),
}


def _pick(row: dict[str, Any], canonical: str) -> Any:
    for key in ALIASES[canonical]:
        if key in row and row[key] not in (None, ""):
            return row[key]
    raise TranscriptStatusDriftError(f"missing transcript-status field: {canonical}")


def compat_adapter_v1(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a transcript-status row without silent fallback.

    The adapter accepts legacy aliases, but every canonical field must resolve.
    Missing metrics indicate upstream drift and must block planning rather than
    silently producing false confidence.
    """

    return {
        "schema_version": "transcript_status_compat.v1",
        "video_id": str(_pick(row, "video_id")),
        "quality_tier": str(_pick(row, "quality_tier")),
        "entity_recall": float(_pick(row, "entity_recall")),
        "wer": float(_pick(row, "wer")),
        "segment_density": float(_pick(row, "segment_density")),
        "source_schema_version": str(row.get("schema_version") or row.get("version") or "unknown"),
    }
