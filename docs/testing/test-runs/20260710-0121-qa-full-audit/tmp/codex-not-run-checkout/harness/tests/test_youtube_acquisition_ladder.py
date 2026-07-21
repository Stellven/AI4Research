"""Tests for acquisition_ladder module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.youtube.subtitle_discovery import SubtitleTrack
from lib.youtube.acquisition_ladder import (
    LadderDecision, LadderLevel, advance_ladder, decide_ladder_path,
)


def _make_track(kind="standard", language="en") -> SubtitleTrack:
    return SubtitleTrack(
        video_id="test_vid", source_backend="yt_dlp",
        language=language, language_name=language,
        track_kind=kind, format="vtt",
        is_auto_generated=(kind == "asr"),
        is_translatable=True, confidence=1.0,
    )


def test_l0_standard_caption():
    tracks = [_make_track("standard", "en")]
    result = decide_ladder_path("test_vid", tracks)
    assert result.resolved_level == LadderLevel.L0.value
    assert result.caption_available is True
    assert result.asr_route_needed is False
    assert result.subtitle_track is not None


def test_l1_auto_caption():
    tracks = [_make_track("auto", "en")]
    result = decide_ladder_path("test_vid", tracks)
    assert result.resolved_level == LadderLevel.L1.value
    assert result.caption_available is True
    assert result.asr_route_needed is False
    assert result.metadata["track_count"] == 1


def test_browser_capture_when_no_tracks():
    result = decide_ladder_path("test_vid", [])
    assert result.resolved_level == LadderLevel.L2.value
    assert result.caption_available is False
    assert result.asr_route_needed is False
    assert result.ladder_state == "browser_capture_needed"


def test_browser_capture_when_no_tracks_p2():
    result = decide_ladder_path("test_vid", [], priority="P2")
    assert result.resolved_level == LadderLevel.L2.value
    assert result.asr_route_needed is False


def test_standard_preferred_over_auto_caption():
    tracks = [_make_track("auto", "en"), _make_track("standard", "en")]
    result = decide_ladder_path("test_vid", tracks)
    assert result.resolved_level == LadderLevel.L0.value


def test_advance_ladder_l0_to_l1():
    initial = decide_ladder_path("test_vid", [_make_track("standard", "en")])
    advanced = advance_ladder("test_vid", initial, failure_reason="download_failed")
    assert advanced.resolved_level == LadderLevel.L1.value


def test_advance_ladder_l1_to_browser_capture():
    initial = decide_ladder_path("test_vid", [_make_track("auto", "en")])
    advanced = advance_ladder("test_vid", initial, failure_reason="bad_content")
    assert advanced.resolved_level == LadderLevel.L2.value
    assert advanced.asr_route_needed is False


def test_advance_ladder_l2_to_metadata_only():
    initial = decide_ladder_path("test_vid", [])
    advanced = advance_ladder("test_vid", initial)
    assert advanced.resolved_level == LadderLevel.L5.value


def test_advance_ladder_l5_stays():
    l5 = LadderDecision("vid", LadderLevel.L5.value, False, False, "state")
    advanced = advance_ladder("vid", l5)
    assert advanced.resolved_level == LadderLevel.L5.value


def test_metadata_contains_failure_reason():
    initial = decide_ladder_path("test_vid", [_make_track("standard", "en")])
    advanced = advance_ladder("test_vid", initial, failure_reason="test_reason")
    assert advanced.metadata.get("failure_reason") == "test_reason"
