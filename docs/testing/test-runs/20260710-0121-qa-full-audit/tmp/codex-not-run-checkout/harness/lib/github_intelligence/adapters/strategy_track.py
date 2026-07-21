"""Strategy-track discovery adapter backed by the shared strategy_tracks table."""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Callable

if __package__ is None or __package__ == "":
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from schema import DiscoveryCandidate, utc_now_iso
    from strategy import load_strategy_tracks, load_strategy_tracks_from_db
else:
    from ..schema import DiscoveryCandidate, utc_now_iso
    from ..strategy import load_strategy_tracks, load_strategy_tracks_from_db


FetchFn = Callable[[str, dict[str, str]], dict[str, Any]]

_GH_SEARCH_URL = "https://api.github.com/search/repositories"


class StrategyTrackAdapter:
    """Discover repos from tech-hotspot-radar strategy tracks.

    Tracks are loaded from the existing SQLite `strategy_tracks` table when a
    connection is supplied, or from the existing tracks YAML when config_path is
    supplied. Returned candidates carry `strategy_track` metadata so downstream
    scoring/dossier stages do not need a second track system.
    """

    source_type = "strategy_track"

    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        config_path: str | Path | None = None,
        per_track_limit: int = 10,
        github_token: str | None = None,
        fetch_fn: FetchFn | None = None,
    ) -> None:
        self.conn = conn
        self.config_path = config_path
        self.per_track_limit = per_track_limit
        self.github_token = github_token
        self.fetch_fn = fetch_fn

    def _tracks(self) -> list[dict[str, Any]]:
        if self.conn is not None:
            return load_strategy_tracks_from_db(self.conn)
        if self.config_path is not None:
            return load_strategy_tracks(self.config_path)
        return []

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def run(self, since: Any = None, fetch_fn: FetchFn | None = None) -> list[DiscoveryCandidate]:
        fn = fetch_fn or self.fetch_fn
        if fn is None:
            return []
        now = utc_now_iso()
        seen: set[str] = set()
        candidates: list[DiscoveryCandidate] = []
        for track in self._tracks():
            query = _query_for_track(track)
            if not query:
                continue
            url = (
                f"{_GH_SEARCH_URL}?q={urllib.parse.quote(query)}"
                f"&sort=stars&order=desc&per_page={self.per_track_limit}"
            )
            try:
                data = fn(url, self._headers())
            except Exception:
                continue
            for item in data.get("items") or []:
                full_name = str(item.get("full_name") or "")
                if not full_name or full_name in seen:
                    continue
                seen.add(full_name)
                candidates.append(
                    DiscoveryCandidate(
                        full_name=full_name,
                        source_type=self.source_type,
                        discovered_at=now,
                        metadata={
                            "strategy_track": track.get("name"),
                            "strategy_track_query": query,
                            "strategy_track_config": {
                                "github_topics": track.get("github_topics") or [],
                                "languages": track.get("languages") or [],
                                "internal_capabilities": track.get("internal_capabilities") or [],
                                "alert_threshold": track.get("alert_threshold"),
                            },
                            "stars": item.get("stargazers_count"),
                            "language": item.get("language"),
                            "topics": item.get("topics") or [],
                            "raw": json.dumps({"id": item.get("id")}, sort_keys=True),
                        },
                    )
                )
        return candidates


def _query_for_track(track: dict[str, Any]) -> str:
    topics = [str(t).strip() for t in track.get("github_topics") or [] if str(t).strip()]
    keywords = [str(k).strip() for k in track.get("keywords") or [] if str(k).strip()]
    languages = [str(lang).strip() for lang in track.get("languages") or [] if str(lang).strip()]
    parts: list[str] = []
    if topics:
        parts.append("(" + " OR ".join(f"topic:{topic}" for topic in topics[:4]) + ")")
    elif keywords:
        parts.append(" ".join(keywords[:2]))
    if languages:
        parts.append("(" + " OR ".join(f"language:{lang}" for lang in languages[:3]) + ")")
    return " ".join(parts)


__all__ = ["StrategyTrackAdapter"]
