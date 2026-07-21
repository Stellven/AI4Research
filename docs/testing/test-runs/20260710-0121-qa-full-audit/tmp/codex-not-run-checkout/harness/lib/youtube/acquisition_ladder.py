"""Acquisition ladder decision module (R1).

Implements L0-L5 transcript acquisition strategy per D1 decision:
acquisition_ladder as independent module, pure function interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .subtitle_discovery import SubtitleTrack


class LadderLevel(str, Enum):
    L0 = "L0_standard_caption"
    L1 = "L1_asr_caption"
    L2 = "L2_browser_capture"
    L5 = "L5_metadata_only"
    ACCEPTED = "ACCEPTED"


@dataclass
class LadderDecision:
    video_id: str
    resolved_level: str
    caption_available: bool
    asr_route_needed: bool
    ladder_state: str
    subtitle_track: Optional[SubtitleTrack] = None
    metadata: dict = field(default_factory=dict)


# Priority matrix: 10-row ordering per PRD §1
_LANGUAGE_PRIORITY = [
    "en", "en-US", "en-GB",
    "zh", "zh-Hans", "zh-Hant",
    "original", "any",
]


def decide_ladder_path(
    video_id: str,
    available_tracks: list[SubtitleTrack],
    priority: str = "P2",
) -> LadderDecision:
    """Decide the acquisition path for a video.

    Pure function — no IO. Input comes from subtitle_discovery results.
    Returns LadderDecision with resolved level and next action.
    """
    # L0: standard caption available?
    standard_tracks = [t for t in available_tracks if t.track_kind == "standard"]
    if standard_tracks:
        best = _pick_best_track(standard_tracks)
        return LadderDecision(
            video_id=video_id,
            resolved_level=LadderLevel.L0.value,
            caption_available=True,
            asr_route_needed=False,
            ladder_state="L0_standard_caption",
            subtitle_track=best,
            metadata={"track_count": len(standard_tracks)},
        )

    # L1: YouTube automatic caption available?
    auto_tracks = [t for t in available_tracks if t.track_kind in {"auto", "asr"}]
    if auto_tracks:
        best = _pick_best_track(auto_tracks)
        return LadderDecision(
            video_id=video_id,
            resolved_level=LadderLevel.L1.value,
            caption_available=True,
            asr_route_needed=False,
            ladder_state="L1_auto_caption",
            subtitle_track=best,
            metadata={"track_count": len(auto_tracks)},
        )

    # No caption available — route to Browser Agent capture, never local ASR.
    return LadderDecision(
        video_id=video_id,
        resolved_level=LadderLevel.L2.value,
        caption_available=False,
        asr_route_needed=False,
        ladder_state="browser_capture_needed",
        metadata={"track_count": 0},
    )


def advance_ladder(
    video_id: str,
    current_decision: LadderDecision,
    failure_reason: str | None = None,
) -> LadderDecision:
    """Advance ladder to next level after failure.

    Maps current level to next fallback level.
    """
    _LEVEL_ADVANCE = {
        LadderLevel.L0.value: LadderLevel.L1.value,
        LadderLevel.L1.value: LadderLevel.L2.value,
        LadderLevel.L2.value: LadderLevel.L5.value,
    }

    current = current_decision.resolved_level
    next_level = _LEVEL_ADVANCE.get(current, LadderLevel.L5.value)

    return LadderDecision(
        video_id=video_id,
        resolved_level=next_level,
        caption_available=False,
        asr_route_needed=False,
        ladder_state=f"{current}_failed",
        metadata={
            "previous_level": current,
            "failure_reason": failure_reason,
        },
    )


def _pick_best_track(tracks: list[SubtitleTrack]) -> SubtitleTrack:
    """Pick best track by language priority, then confidence."""
    lang_order = {lang: i for i, lang in enumerate(_LANGUAGE_PRIORITY)}

    def sort_key(t: SubtitleTrack) -> tuple:
        lang_idx = lang_order.get(t.language, 999)
        return (lang_idx, -t.confidence)

    return sorted(tracks, key=sort_key)[0]
