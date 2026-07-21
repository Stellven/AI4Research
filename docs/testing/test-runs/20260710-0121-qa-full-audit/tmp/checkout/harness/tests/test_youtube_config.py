"""B1 tests — youtube_config: 5 sub-models + env_prefix='SOLAR_YOUTUBE_' (D13)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from youtube_config import (
    ASRConfig,
    ASRRouteEntry,
    PremiumASRConfig,
    SubtitleTracksConfig,
    TranscriptAcquisitionConfig,
    TranscriptQualityConfig,
    YoutubeConfig,
    load_youtube_config,
)


def test_root_config_has_five_subsections():
    cfg = YoutubeConfig()
    assert isinstance(cfg.transcript_acquisition, TranscriptAcquisitionConfig)
    assert isinstance(cfg.subtitle_tracks, SubtitleTracksConfig)
    assert isinstance(cfg.asr, ASRConfig)
    assert isinstance(cfg.transcript_quality, TranscriptQualityConfig)
    assert isinstance(cfg.premium_asr, PremiumASRConfig)


def test_env_prefix_is_solar_youtube():
    """Per D13: env_prefix='SOLAR_YOUTUBE_'."""
    cfg = YoutubeConfig()
    assert cfg.model_config.get("env_prefix") == "SOLAR_YOUTUBE_"


def test_routing_table_default_six_rows():
    cfg = YoutubeConfig()
    assert len(cfg.asr.routing_table) == 6


def test_routing_table_first_row_standard_skip():
    cfg = YoutubeConfig()
    first = cfg.asr.routing_table[0]
    assert first.caption_status == "standard"
    assert first.backend == "caption_skip"


def test_routing_table_second_row_asr_caption():
    cfg = YoutubeConfig()
    assert cfg.asr.routing_table[1].caption_status == "asr"
    assert cfg.asr.routing_table[1].backend == "caption_asr"


def test_premium_asr_default_disabled():
    cfg = YoutubeConfig()
    assert cfg.premium_asr.enabled is False


def test_transcript_acquisition_defaults():
    cfg = YoutubeConfig()
    ta = cfg.transcript_acquisition
    assert ta.timeout_seconds == 15
    assert ta.max_consecutive_failures == 8
    assert "en" in ta.default_language_priority
    assert "zh" in ta.default_language_priority


def test_subtitle_tracks_table_name_default():
    cfg = YoutubeConfig()
    assert cfg.subtitle_tracks.table_name == "youtube_subtitle_tracks"
    assert cfg.subtitle_tracks.migrations_table == "youtube_intelligence_migrations"


def test_transcript_quality_defaults():
    cfg = YoutubeConfig()
    assert cfg.transcript_quality.min_confidence == 0.5
    assert cfg.transcript_quality.max_chars == 60000


def test_asr_route_entry_validation():
    entry = ASRRouteEntry(
        caption_status="standard",
        priority="*",
        backend="caption_skip",
    )
    assert entry.diarization is False  # default


def test_load_youtube_config_no_path_returns_defaults():
    cfg = load_youtube_config(path=None, env_override=False)
    assert isinstance(cfg, YoutubeConfig)
    assert len(cfg.asr.routing_table) == 6


def test_load_youtube_config_env_override(monkeypatch):
    """env vars with SOLAR_YOUTUBE_ prefix should override defaults."""
    monkeypatch.setenv("SOLAR_YOUTUBE_TRANSCRIPT_ACQUISITION__TIMEOUT_SECONDS", "99")
    cfg = load_youtube_config(path=None, env_override=True)
    assert cfg.transcript_acquisition.timeout_seconds == 99


def test_pydantic_v2_strict_field_validation():
    """Bad value should raise ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TranscriptAcquisitionConfig(max_consecutive_failures=0)  # ge=1
