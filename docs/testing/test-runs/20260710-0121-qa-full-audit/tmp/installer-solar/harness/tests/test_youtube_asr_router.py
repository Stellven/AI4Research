"""Tests for asr_router module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.youtube.asr_router import ASRBackendSpec, route_asr

DEFAULT_TABLE = [
    {"caption_status": "standard", "priority": "*", "backend": "caption_skip", "model_size": "", "diarization": False, "reason": "subtitle exists"},
    {"caption_status": "asr", "priority": "*", "backend": "caption_asr", "model_size": "", "diarization": False, "reason": "yt asr caption"},
    {"caption_status": "none", "priority": "P0", "backend": "whisperx_large_v3", "model_size": "large-v3", "diarization": True, "reason": "P0 whisperx"},
    {"caption_status": "none", "priority": "P1", "backend": "faster_whisper_large_v3", "model_size": "large-v3", "diarization": False, "reason": "P1 fw"},
    {"caption_status": "none", "priority": "P2", "backend": "faster_whisper_medium", "model_size": "medium", "diarization": False, "reason": "P2 medium"},
]


def test_standard_caption_skips_asr():
    result = route_asr("P0", "en", 300, DEFAULT_TABLE, caption_status="standard")
    assert result.backend == "caption_skip"


def test_asr_caption_uses_caption():
    result = route_asr("P1", "en", 300, DEFAULT_TABLE, caption_status="asr")
    assert result.backend == "caption_asr"


def test_p0_gets_whisperx():
    result = route_asr("P0", "en", 300, DEFAULT_TABLE, caption_status="none")
    assert result.backend == "whisperx_large_v3"
    assert result.diarization is True
    assert result.model_size == "large-v3"


def test_p1_gets_faster_whisper_large():
    result = route_asr("P1", "en", 300, DEFAULT_TABLE, caption_status="none")
    assert result.backend == "faster_whisper_large_v3"
    assert result.model_size == "large-v3"


def test_p2_gets_medium():
    result = route_asr("P2", "zh", 300, DEFAULT_TABLE, caption_status="none")
    assert result.backend == "faster_whisper_medium"
    assert result.model_size == "medium"


def test_p3_falls_to_default():
    result = route_asr("P3", "en", 300, DEFAULT_TABLE, caption_status="none")
    assert result.backend == "faster_whisper"  # default fallback


def test_empty_table_uses_default():
    result = route_asr("P0", "en", 300, [], caption_status="none")
    assert result.backend == "faster_whisper"
    assert "fallback" in result.reason


def test_wildcard_priority_matches_any():
    for p in ("P0", "P1", "P2", "P3"):
        result = route_asr(p, "en", 300, DEFAULT_TABLE, caption_status="standard")
        assert result.backend == "caption_skip"
