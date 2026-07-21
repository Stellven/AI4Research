"""Append-only Event Ledger — SQLite WAL + JSONL mirror dual-write.

S03 N2: sprint-20260519-solar-harness-vnext-code-as-harness-runtime-s03-core-runtime
Upstream: S02 policy-decisions.md §1 (option C), state-machines.md §3
"""

import fcntl
import json
import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "run")


class EventLedgerError(Exception):
    """Raised when a ledger write fails at the sqlite level."""


def _validate_event(event: Dict[str, Any]) -> None:
    required = ("event_type", "sprint_id", "actor")
    missing = [f for f in required if f not in event]
    if missing:
        raise ValueError(f"event missing required fields: {missing}")


class EventLedger:
    """Append-only event ledger with SQLite WAL + JSONL mirror.

    Write order: validate -> sqlite -> jsonl.
    If sqlite fails, jsonl is NOT written (source-of-truth protection).
    If jsonl fails, a warning is logged but the write succeeds (jsonl is a mirror).
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base = Path(base_dir or _DEFAULT_BASE)
        self._base.mkdir(parents=True, exist_ok=True)
        self._db_path = self._base / "events.db"
        self._jsonl_path = self._base / "events.jsonl"
        self._init_db()

    # -- public API ----------------------------------------------------------

    def append(self, event: Dict[str, Any]) -> str:
        """Append an event. Returns the event_id.

        Order: validate -> sqlite INSERT -> jsonl append.
        Sqlite failure raises EventLedgerError and does NOT write jsonl.
        """
        _validate_event(event)
        event_id = event.get("event_id") or str(uuid.uuid4())
        event["event_id"] = event_id

        if "created_at" not in event:
            from datetime import datetime, timezone
            event["created_at"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        if "schema_version" not in event:
            event["schema_version"] = "v1"

        row = (
            event_id,
            event["event_type"],
            event["sprint_id"],
            event.get("node_id"),
            event["actor"],
            json.dumps(event.get("payload", {}), ensure_ascii=False),
            event["created_at"],
            event["schema_version"],
        )

        # Step 1: sqlite INSERT (source of truth)
        try:
            self._insert(row)
        except sqlite3.IntegrityError as exc:
            raise EventLedgerError(f"duplicate event_id: {event_id}") from exc
        except sqlite3.Error as exc:
            raise EventLedgerError(f"sqlite write failed: {exc}") from exc

        # Step 2: jsonl mirror (best-effort)
        try:
            self._append_jsonl(event)
        except OSError as exc:
            logger.warning("jsonl mirror write failed for %s: %s", event_id, exc)

        return event_id

    def replay(self, sprint_id: str) -> List[Dict[str, Any]]:
        """Replay all events for a sprint, ordered by created_at.

        Idempotent: calling replay multiple times returns the same list
        (no side effects, pure read).
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT event_id, event_type, sprint_id, node_id, actor, "
                "       payload, created_at, schema_version "
                "FROM events WHERE sprint_id = ? ORDER BY created_at",
                (sprint_id,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_last_event_id(self) -> Optional[str]:
        """Return the event_id of the most recent event, or None if empty."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT event_id FROM events ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    # -- internal ------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                "  event_id    TEXT NOT NULL PRIMARY KEY, "
                "  event_type  TEXT NOT NULL, "
                "  sprint_id   TEXT NOT NULL, "
                "  node_id     TEXT, "
                "  actor       TEXT NOT NULL, "
                "  payload     TEXT NOT NULL DEFAULT '{}', "
                "  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), "
                "  schema_version TEXT NOT NULL DEFAULT 'v1'"
                ")"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_id "
                "ON events(event_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_sprint_id "
                "ON events(sprint_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_event_type "
                "ON events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_created_at "
                "ON events(created_at)"
            )
            conn.commit()
        finally:
            conn.close()

    def _insert(self, row: tuple) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO events "
                "(event_id, event_type, sprint_id, node_id, actor, "
                " payload, created_at, schema_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            conn.commit()
        finally:
            conn.close()

    def _append_jsonl(self, event: Dict[str, Any]) -> None:
        fd = os.open(
            str(self._jsonl_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        return d
