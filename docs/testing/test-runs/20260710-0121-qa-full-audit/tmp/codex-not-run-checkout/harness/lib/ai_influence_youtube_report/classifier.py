"""Deterministic video grouping classifier for report planning."""

from __future__ import annotations

from typing import Any

from .schema import ClassificationDecision, GateDecision, TranscriptGrade


GROUP_TYPES = {"event", "conference", "keynote", "interview", "tutorial", "product_update", "other"}


def _text(metadata: dict[str, Any]) -> str:
    return " ".join(str(metadata.get(k, "")) for k in ("title", "description", "channel", "tags")).lower()


def group_classifier(video_metadata: dict[str, Any], gate_decision: GateDecision) -> ClassificationDecision:
    if gate_decision.grade == TranscriptGrade.T3:
        raise ValueError("T3 transcript cannot be grouped for report evidence")
    text = _text(video_metadata)
    duration = float(video_metadata.get("duration_min") or 0)
    speakers = int(video_metadata.get("speaker_count") or 1)
    has_qa = bool(video_metadata.get("has_qa"))
    slide_density = float(video_metadata.get("slide_density") or 0)
    title_has_release = any(w in text for w in ("launch", "release", "announc", "update", "introducing"))

    scores = {
        "event": 0.7 if any(w in text for w in ("summit", "event", "expo", "conference")) else 0.0,
        "conference": 0.8 if any(w in text for w in ("conference", "i/o", "keynote", "summit")) and duration >= 20 else 0.0,
        "keynote": 0.85 if "keynote" in text or ("opening" in text and duration >= 20) else 0.0,
        "interview": 0.8 if any(w in text for w in ("interview", "fireside", "conversation", "podcast")) or speakers >= 2 and has_qa else 0.0,
        "tutorial": 0.75 if any(w in text for w in ("tutorial", "build", "workshop", "hands-on", "demo")) or slide_density > 0.6 else 0.0,
        "product_update": 0.78 if title_has_release else 0.0,
        "other": 0.2,
    }
    group_type, confidence = max(scores.items(), key=lambda item: item[1])
    fallback_used = confidence < 0.5
    if fallback_used:
        group_type = "other"
        confidence = 0.2
    signal_breakdown = {
        "S1": 1.0 if any(w in text for w in ("i/o", "summit", "conference", "keynote")) else 0.0,
        "S2": min(duration / 120.0, 1.0),
        "S3": min(speakers / 4.0, 1.0),
        "S4": 1.0 if has_qa else 0.0,
        "S5": 1.0 if title_has_release else 0.0,
        "S6": max(0.0, min(slide_density, 1.0)),
    }
    return ClassificationDecision(
        video_id=gate_decision.video_id,
        group_type=group_type,
        confidence=confidence,
        signal_breakdown=signal_breakdown,
        fallback_used=fallback_used,
    )
