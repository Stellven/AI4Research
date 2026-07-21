"""Subtitle track discovery via yt-dlp --list-subs --skip-download.

Uses real network when available; falls back to
tests/fixtures/yt-dlp-list-subs.json when SOLAR_YOUTUBE_OFFLINE=1.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SubtitleTrack:
    """Single discovered subtitle/caption track."""
    video_id: str
    source_backend: str  # yt_dlp | player_caption | browser_capture | youtube_api
    language: str  # BCP-47
    language_name: str
    track_kind: str  # standard | asr | translation
    format: str  # srv1, vtt, json3, etc.
    is_auto_generated: bool
    is_translatable: bool
    confidence: float = 0.0
    url: str = ""
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def track_id(self) -> str:
        return f"{self.video_id}:{self.source_backend}:{self.language}:{self.track_kind}"


_OFFLINE_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "yt-dlp-list-subs.json"


def discover_subtitle_tracks(
    video_id: str,
    language_priority: list[str] | None = None,
    backend_order: list[str] | None = None,
    yt_dlp_bin: str = "yt-dlp",
    timeout: int = 15,
) -> list[SubtitleTrack]:
    """Discover available subtitle/caption tracks for a video.

    When SOLAR_YOUTUBE_OFFLINE=1, reads from the mock fixture instead of
    calling yt-dlp over the network.

    Args:
        video_id: YouTube video ID.
        language_priority: Preferred language order for sorting results.
        backend_order: Preferred source_backend order.
        yt_dlp_bin: Path to yt-dlp binary.
        timeout: Network timeout in seconds.

    Returns:
        List of SubtitleTrack sorted by language_priority then backend_order.
    """
    if language_priority is None:
        language_priority = ["en", "zh", "zh-Hans", "zh-Hant", "ja"]

    if backend_order is None:
        backend_order = ["yt_dlp"]

    raw = _fetch_list_subs(video_id, yt_dlp_bin, timeout)
    return _parse_tracks(video_id, raw, language_priority, backend_order)


def _fetch_list_subs(video_id: str, yt_dlp_bin: str, timeout: int) -> dict:
    """Fetch subtitle listing; use fixture when offline."""
    if os.environ.get("SOLAR_YOUTUBE_OFFLINE", "").strip() in ("1", "true", "yes"):
        return _load_fixture(video_id)

    try:
        result = subprocess.run(
            [yt_dlp_bin, "--skip-download", "--dump-single-json",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass

    # Production must not silently invent tracks from a fixture.  The fixture is
    # only valid when tests explicitly opt into SOLAR_YOUTUBE_OFFLINE.
    return {"id": video_id, "subtitles": {}, "automatic_captions": {}}


def _load_fixture(video_id: str) -> dict:
    """Load mock fixture for offline testing."""
    if not _OFFLINE_FIXTURE.is_file():
        return {"id": video_id, "subtitles": {}, "automatic_captions": {}}
    with open(_OFFLINE_FIXTURE) as f:
        data = json.load(f)
    data["id"] = video_id
    return data


def _parse_tracks(
    video_id: str,
    raw: dict,
    language_priority: list[str],
    backend_order: list[str],
) -> list[SubtitleTrack]:
    """Parse yt-dlp JSON output into SubtitleTrack list."""
    tracks: list[SubtitleTrack] = []
    lang_order = {lang: i for i, lang in enumerate(language_priority)}

    for lang_code, entries in raw.get("subtitles", {}).items():
        if str(lang_code).lower() in {"live_chat", "comments"}:
            continue
        for entry in entries:
            tracks.append(SubtitleTrack(
                video_id=video_id,
                source_backend="yt_dlp",
                language=lang_code,
                language_name=entry.get("name", lang_code),
                track_kind="standard",
                format=entry.get("ext", "unknown"),
                is_auto_generated=False,
                is_translatable=True,
                confidence=1.0,
                url=entry.get("url", ""),
            ))

    for lang_code, entries in raw.get("automatic_captions", {}).items():
        if str(lang_code).lower() in {"live_chat", "comments"}:
            continue
        for entry in entries:
            tracks.append(SubtitleTrack(
                video_id=video_id,
                source_backend="yt_dlp",
                language=lang_code,
                language_name=entry.get("name", lang_code),
                track_kind="asr",
                format=entry.get("ext", "unknown"),
                is_auto_generated=True,
                is_translatable=True,
                confidence=0.75,
                url=entry.get("url", ""),
            ))

    def sort_key(t: SubtitleTrack) -> tuple:
        lang_idx = lang_order.get(t.language, 999)
        kind_idx = 0 if t.track_kind == "standard" else 1
        return (lang_idx, kind_idx)

    tracks.sort(key=sort_key)
    return tracks
