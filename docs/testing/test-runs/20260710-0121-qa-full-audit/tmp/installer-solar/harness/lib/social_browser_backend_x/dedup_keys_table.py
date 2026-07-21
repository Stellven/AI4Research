"""Dedup key table for social post canonical URL / sha256 dedup.

Per S02 A2 design:
  - Table: social_post_dedup_keys
  - Columns: key TEXT PRIMARY KEY, first_seen_at TEXT, last_seen_at TEXT,
    post_pk INTEGER FK -> social_posts(rowid)
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DedupKeyRecord:
    """A dedup key mapping a canonical URL or sha256 hash to a post."""

    key: str
    first_seen_at: str
    last_seen_at: str
    post_pk: Optional[int] = None

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> DedupKeyRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in row.items() if k in known}
        return cls(**filtered)


_DDL = """
CREATE TABLE IF NOT EXISTS social_post_dedup_keys (
    key          TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    post_pk      INTEGER REFERENCES social_posts(rowid)
);
CREATE INDEX IF NOT EXISTS idx_dk_post_pk
    ON social_post_dedup_keys(post_pk);
"""


def ensure_dedup_keys_table(conn: sqlite3.Connection) -> None:
    """Create social_post_dedup_keys if not exists. Idempotent."""
    conn.executescript(_DDL)


def upsert_dedup_key(
    conn: sqlite3.Connection,
    key: str,
    post_pk: int,
) -> DedupKeyRecord:
    """Insert or update a dedup key, returning the record."""
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT key, first_seen_at, last_seen_at, post_pk "
        "FROM social_post_dedup_keys WHERE key = ?",
        (key,),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE social_post_dedup_keys SET last_seen_at = ?, post_pk = ? "
            "WHERE key = ?",
            (now, post_pk, key),
        )
        return DedupKeyRecord(key=key, first_seen_at=existing[1], last_seen_at=now, post_pk=post_pk)

    conn.execute(
        "INSERT INTO social_post_dedup_keys (key, first_seen_at, last_seen_at, post_pk) "
        "VALUES (?, ?, ?, ?)",
        (key, now, now, post_pk),
    )
    return DedupKeyRecord(key=key, first_seen_at=now, last_seen_at=now, post_pk=post_pk)


def lookup_dedup_key(
    conn: sqlite3.Connection, key: str
) -> Optional[DedupKeyRecord]:
    """Return the dedup key record or None."""
    row = conn.execute(
        "SELECT key, first_seen_at, last_seen_at, post_pk "
        "FROM social_post_dedup_keys WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return DedupKeyRecord(key=row[0], first_seen_at=row[1], last_seen_at=row[2], post_pk=row[3])
