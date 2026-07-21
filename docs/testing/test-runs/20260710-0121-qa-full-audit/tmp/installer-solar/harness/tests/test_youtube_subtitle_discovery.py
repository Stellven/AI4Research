"""Tests for subtitle_discovery module."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.youtube.subtitle_discovery import (
    SubtitleTrack, discover_subtitle_tracks,
)

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "yt-dlp-list-subs.json"


@pytest.fixture(autouse=True)
def force_offline(monkeypatch):
    monkeypatch.setenv("SOLAR_YOUTUBE_OFFLINE", "1")


def test_discover_returns_tracks():
    tracks = discover_subtitle_tracks("dQw4w9WgXcQ")
    assert len(tracks) > 0
    assert all(isinstance(t, SubtitleTrack) for t in tracks)


def test_standard_tracks_found():
    tracks = discover_subtitle_tracks("dQw4w9WgXcQ")
    standard = [t for t in tracks if t.track_kind == "standard"]
    assert len(standard) >= 2  # en + zh-Hans


def test_asr_tracks_found():
    tracks = discover_subtitle_tracks("dQw4w9WgXcQ")
    asr = [t for t in tracks if t.track_kind == "asr"]
    assert len(asr) >= 2  # en + ja


def test_track_id_format():
    tracks = discover_subtitle_tracks("dQw4w9WgXcQ")
    for t in tracks:
        parts = t.track_id.split(":")
        assert len(parts) == 4  # video_id:backend:lang:kind


def test_language_priority_sorting():
    tracks = discover_subtitle_tracks("dQw4w9WgXcQ")
    langs = [t.language for t in tracks]
    # en should come before zh-Hans (in default priority)
    if "en" in langs and "zh-Hans" in langs:
        assert langs.index("en") < langs.index("zh-Hans")


def test_standard_before_asr():
    tracks = discover_subtitle_tracks("dQw4w9WgXcQ")
    kinds = [t.track_kind for t in tracks]
    if "standard" in kinds and "asr" in kinds:
        assert kinds.index("standard") < kinds.index("asr")


def test_offline_fixture_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("SOLAR_YOUTUBE_OFFLINE", "1")
    # Temporarily point fixture to non-existent path
    import lib.youtube.subtitle_discovery as mod
    original = mod._OFFLINE_FIXTURE
    mod._OFFLINE_FIXTURE = tmp_path / "nonexistent.json"
    try:
        tracks = discover_subtitle_tracks("fake_video_id")
        assert tracks == []  # empty result, no crash
    finally:
        mod._OFFLINE_FIXTURE = original
