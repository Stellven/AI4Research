"""base.py — Discovery adapter protocol, candidate dataclass, dedup queue."""
from __future__ import annotations

import dataclasses
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class DiscoveryCandidate:
    """A single discovered repo candidate."""

    full_name: str
    source_type: str  # topic | trending | tracked | social_mention | youtube_mention
    discovered_at: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@runtime_checkable
class DiscoveryAdapter(Protocol):
    """Protocol for discovery adapters."""

    def run(self, since: str | None = None) -> list[DiscoveryCandidate]:
        """Run discovery and return candidates.

        Parameters
        ----------
        since : str, optional
            ISO timestamp; only discover items newer than this.

        Returns
        -------
        list[DiscoveryCandidate]
        """
        ...


class DedupQueue:
    """Dedup queue backed by repo_master table.

    Checks (full_name, source_type) uniqueness within a configurable window.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        dedup_window_hours: int = 24,
    ) -> None:
        self._conn = conn
        self._dedup_window_hours = dedup_window_hours

    def enqueue(self, candidates: list[DiscoveryCandidate]) -> list[str]:
        """Enqueue candidates, returning only new full_names.

        For each candidate:
        - If full_name not in repo_master → INSERT with tracking_status='candidate'
        - If full_name exists but source_type is new within window → record discovery
        - If (full_name, source_type) seen within window → skip (dedup)

        Returns
        -------
        list[str]
            Full names of newly enqueued candidates.
        """
        if not candidates:
            return []

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cutoff = (
            datetime.now(timezone.utc)
            - __import__("datetime").timedelta(hours=self._dedup_window_hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_names: list[str] = []

        for candidate in candidates:
            full_name = candidate.full_name
            source_type = candidate.source_type

            # Check if repo exists in repo_master
            existing_tables = [
                row[0]
                for row in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]

            repo_table = None
            for t in ("github_repo_master", "repo_master"):
                if t in existing_tables:
                    repo_table = t
                    break

            if repo_table is None:
                # No repo table — create a simple one
                self._conn.execute(
                    """CREATE TABLE IF NOT EXISTS repo_master (
                        full_name TEXT PRIMARY KEY,
                        tracking_status TEXT NOT NULL DEFAULT 'candidate',
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL
                    )"""
                )
                repo_table = "repo_master"

            # Check dedup: has this (full_name, source_type) been seen within window?
            dedup_tables = [
                row[0]
                for row in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='discovery_events'"
                ).fetchall()
            ]
            if "discovery_events" not in dedup_tables:
                self._conn.execute(
                    """CREATE TABLE IF NOT EXISTS discovery_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        full_name TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        discovered_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    )"""
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_de_dedup ON discovery_events(full_name, source_type, discovered_at)"
                )

            # Check dedup
            row = self._conn.execute(
                """SELECT 1 FROM discovery_events
                   WHERE full_name = ? AND source_type = ? AND discovered_at >= ?
                   LIMIT 1""",
                (full_name, source_type, cutoff),
            ).fetchone()

            if row:
                # Duplicate within window — skip
                continue

            # Not a duplicate — record it
            import json

            self._conn.execute(
                """INSERT INTO discovery_events (full_name, source_type, discovered_at, metadata_json)
                   VALUES (?, ?, ?, ?)""",
                (full_name, source_type, candidate.discovered_at,
                 json.dumps(candidate.metadata, default=str)),
            )

            # Upsert into repo_master
            existing = self._conn.execute(
                f"SELECT full_name FROM {repo_table} WHERE full_name = ?",
                (full_name,),
            ).fetchone()

            if existing:
                self._conn.execute(
                    f"UPDATE {repo_table} SET last_seen_at = ? WHERE full_name = ?",
                    (now, full_name),
                )
            else:
                self._conn.execute(
                    f"""INSERT INTO {repo_table} (full_name, tracking_status, first_seen_at, last_seen_at)
                        VALUES (?, 'candidate', ?, ?)""",
                    (full_name, now, now),
                )
                new_names.append(full_name)

        self._conn.commit()
        return new_names
