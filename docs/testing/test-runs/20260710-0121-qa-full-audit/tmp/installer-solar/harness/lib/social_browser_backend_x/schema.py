"""PostRecord dataclass and DDL for social_posts extensions.

Per S02 A2 design:
  - 11 fields: post_id / author_handle / text / created_at / post_url /
    metrics_{reply,repost,like,view} / urls / dom_hash / screenshot_path /
    collection_backend
  - Migration adds 4 columns to existing social_posts: dom_hash,
    screenshot_path, collection_backend, dedup_key
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from typing import List, Optional

# Backend enum values — matches S02 A1 §1 BackendSelector order
BACKEND_BROWSER_AGENT = "browser_agent"
BACKEND_RSS_PUBLIC = "rss_public"
BACKEND_MANUAL_CURATED = "manual_curated"
BACKEND_X_API = "x_api"
VALID_BACKENDS = frozenset(
    {BACKEND_BROWSER_AGENT, BACKEND_RSS_PUBLIC, BACKEND_MANUAL_CURATED, BACKEND_X_API}
)


@dataclass
class PostRecord:
    """A social post collected via any backend.

    Fields map to the social_posts table plus 4 new columns
    (dom_hash, screenshot_path, collection_backend, dedup_key).
    """

    post_id: str
    author_handle: str
    text: str
    created_at: Optional[str]
    post_url: str
    reply_count: int = 0
    repost_count: int = 0
    like_count: int = 0
    view_count: Optional[int] = None
    urls: str = ""
    dom_hash: Optional[str] = None
    screenshot_path: Optional[str] = None
    collection_backend: str = "unknown"

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> PostRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in row.items() if k in known}
        return cls(**filtered)

    def validate_backend(self) -> None:
        if self.collection_backend not in VALID_BACKENDS and self.collection_backend != "unknown":
            raise ValueError(
                f"Invalid collection_backend: {self.collection_backend!r}. "
                f"Expected one of {sorted(VALID_BACKENDS)}"
            )


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create / migrate social_posts extensions.

    Idempotent — safe to call multiple times.

    New columns added with safe defaults so legacy X API rows
    are unaffected.
    """
    conn.executescript("""
        -- dom_hash: sha256 of raw DOM for dedup / integrity
        ALTER TABLE social_posts ADD COLUMN dom_hash TEXT;

        -- screenshot_path: local path to screenshot on parse failure
        ALTER TABLE social_posts ADD COLUMN screenshot_path TEXT;

        -- collection_backend: which backend collected this post
        ALTER TABLE social_posts ADD COLUMN collection_backend TEXT NOT NULL DEFAULT 'unknown';

        -- dedup_key: FK to social_post_dedup_keys for canonical dedup
        ALTER TABLE social_posts ADD COLUMN dedup_key TEXT REFERENCES social_post_dedup_keys(key);
    """)


def ensure_schema_safe(conn: sqlite3.Connection) -> None:
    """Idempotent wrapper — silently skips columns that already exist."""
    cur = conn.execute("PRAGMA table_info(social_posts)")
    existing = {row[1] for row in cur.fetchall()}

    migrations: List[str] = []
    if "dom_hash" not in existing:
        migrations.append("ALTER TABLE social_posts ADD COLUMN dom_hash TEXT;")
    if "screenshot_path" not in existing:
        migrations.append(
            "ALTER TABLE social_posts ADD COLUMN screenshot_path TEXT;"
        )
    if "collection_backend" not in existing:
        migrations.append(
            "ALTER TABLE social_posts ADD COLUMN collection_backend "
            "TEXT NOT NULL DEFAULT 'unknown';"
        )
    if "dedup_key" not in existing:
        migrations.append(
            "ALTER TABLE social_posts ADD COLUMN dedup_key TEXT "
            "REFERENCES social_post_dedup_keys(key);"
        )
    if migrations:
        conn.executescript("\n".join(migrations))
