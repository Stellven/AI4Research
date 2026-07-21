"""Priority scoring module (R5).

Computes transcript_priority_score using 6-factor formula.
Per D5: thresholds P0≥0.80 / P1≥0.60 / P2≥0.35 / P3<0.35 hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PriorityScore:
    video_id: str
    score: float
    priority: str
    components: dict


# 6-factor weights (per D5)
_WEIGHTS = {
    "channel_weight": 0.25,
    "recency": 0.20,
    "report_candidate": 0.20,
    "cross_source": 0.15,
    "view_velocity": 0.10,
    "duration_value": 0.10,
}

# Hardcoded thresholds (per D5)
_THRESHOLDS = [
    (0.80, "P0"),
    (0.60, "P1"),
    (0.35, "P2"),
]


def compute_priority_score(
    video_id: str,
    channel_weight: float,
    recency: float,
    report_candidate: float,
    cross_source: float,
    view_velocity: float,
    duration_value: float,
) -> PriorityScore:
    """Compute priority score using 6-factor weighted formula.

    All inputs should be in [0.0, 1.0].
    """
    components = {
        "channel_weight": channel_weight,
        "recency": recency,
        "report_candidate": report_candidate,
        "cross_source": cross_source,
        "view_velocity": view_velocity,
        "duration_value": duration_value,
    }

    score = (
        _WEIGHTS["channel_weight"] * channel_weight
        + _WEIGHTS["recency"] * recency
        + _WEIGHTS["report_candidate"] * report_candidate
        + _WEIGHTS["cross_source"] * cross_source
        + _WEIGHTS["view_velocity"] * view_velocity
        + _WEIGHTS["duration_value"] * duration_value
    )

    priority = _classify(score)

    return PriorityScore(
        video_id=video_id,
        score=round(score, 4),
        priority=priority,
        components=components,
    )


def _classify(score: float) -> str:
    """Classify score into priority tier."""
    for threshold, tier in _THRESHOLDS:
        if score >= threshold:
            return tier
    return "P3"
