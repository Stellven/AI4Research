"""Pydantic v2 configuration model for YouTube transcript acquisition.

5 sub-models + env_prefix='SOLAR_YOUTUBE_' for environment override.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TranscriptAcquisitionConfig(BaseModel):
    """Settings for the subtitle/caption acquisition pipeline."""
    default_language_priority: list[str] = Field(
        default=["en", "zh", "zh-Hans", "zh-Hant", "ja"],
        description="Language preference order for subtitle selection",
    )
    max_consecutive_failures: int = Field(default=8, ge=1)
    sleep_between_videos_seconds: float = Field(default=2.5, ge=0)
    timeout_seconds: int = Field(default=15, ge=1)
    user_agent: str = "Solar-YouTube-Transcript/1.0"


class SubtitleTracksConfig(BaseModel):
    """Settings for subtitle track storage."""
    table_name: str = "youtube_subtitle_tracks"
    migrations_table: str = "youtube_intelligence_migrations"
    db_path: Optional[str] = Field(default=None, description="SQLite DB path; defaults to ~/.solar/harness/state/youtube/transcripts.db")


class ASRRouteEntry(BaseModel):
    """Single row in the ASR routing table."""
    caption_status: str
    priority: str = "*"
    backend: str
    model_size: str = ""
    diarization: bool = False
    reason: str = ""


class ASRConfig(BaseModel):
    """Settings for ASR backend routing."""
    enabled: bool = True
    default_backend: str = "faster_whisper"
    whisper_model: str = "small"
    language: str = "zh"
    timeout_seconds: int = Field(default=7200, ge=60)
    yt_dlp_bin: str = "yt-dlp"
    ffmpeg_location: str = "/opt/homebrew/bin"
    max_per_run: int = Field(default=1, ge=0)
    keep_audio: bool = False

    routing_table: list[ASRRouteEntry] = Field(
        default_factory=lambda: [
            ASRRouteEntry(caption_status="standard", priority="*", backend="caption_skip", model_size="", diarization=False, reason="Subtitle exists; ASR skipped"),
            ASRRouteEntry(caption_status="asr", priority="*", backend="caption_asr", model_size="", diarization=False, reason="YouTube ASR caption preferred over local ASR"),
            ASRRouteEntry(caption_status="none", priority="P0", backend="whisperx_large_v3_diarization", model_size="large-v3", diarization=True, reason="P0 multi-speaker: WhisperX + diarization"),
            ASRRouteEntry(caption_status="none", priority="P0", backend="faster_whisper_large_v3", model_size="large-v3", diarization=False, reason="P0/P1 high-value: faster-whisper large-v3"),
            ASRRouteEntry(caption_status="none", priority="P1", backend="faster_whisper_large_v3", model_size="large-v3", diarization=False, reason="P1 high-value: faster-whisper large-v3"),
            ASRRouteEntry(caption_status="none", priority="P2", backend="faster_whisper_medium", model_size="medium", diarization=False, reason="P2: faster-whisper medium"),
        ],
        description="6-row routing table loaded from config YAML",
    )


class TranscriptQualityConfig(BaseModel):
    """Settings for transcript quality assessment."""
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    max_chars: int = Field(default=60000, ge=1000)
    min_words_per_minute: float = Field(default=20.0, ge=0)


class PremiumASRConfig(BaseModel):
    """Settings for premium ASR (external provider)."""
    enabled: bool = False
    backend: str = "premium"
    model_size: str = "large-v3"
    max_per_day: int = Field(default=5, ge=0)
    priority_threshold: str = "P1"
    cost_budget_per_video_cents: int = Field(default=50, ge=0)


class YoutubeConfig(BaseModel):
    """Root configuration for YouTube transcript acquisition pipeline.

    env_prefix='SOLAR_YOUTUBE_' allows overriding any field via environment variables,
    e.g. SOLAR_YOUTUBE_ASR_ENABLED=false.
    """
    model_config = {"env_prefix": "SOLAR_YOUTUBE_", "env_nested_delimiter": "__"}

    transcript_acquisition: TranscriptAcquisitionConfig = Field(default_factory=TranscriptAcquisitionConfig)
    subtitle_tracks: SubtitleTracksConfig = Field(default_factory=SubtitleTracksConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    transcript_quality: TranscriptQualityConfig = Field(default_factory=TranscriptQualityConfig)
    premium_asr: PremiumASRConfig = Field(default_factory=PremiumASRConfig)


def load_youtube_config(path: str | None = None, env_override: bool = True) -> YoutubeConfig:
    """Load YouTube configuration from YAML file + env overrides.

    Args:
        path: Path to YAML config file. If None, uses default paths.
        env_override: If True, allow SOLAR_YOUTUBE_* env vars to override file values.

    Returns:
        YoutubeConfig instance with merged values.
    """
    import json

    data: dict = {}

    if path and Path(path).is_file():
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    if env_override:
        env_data = _load_from_env()
        _deep_merge(data, env_data)

    return YoutubeConfig.model_validate(data)


def _load_from_env() -> dict:
    """Extract SOLAR_YOUTUBE_* env vars into nested dict."""
    result: dict = {}
    prefix = "SOLAR_YOUTUBE_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].lower().split("__")
        _set_nested(result, parts, value)
    return result


def _set_nested(d: dict, keys: list[str], value: str) -> None:
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base
