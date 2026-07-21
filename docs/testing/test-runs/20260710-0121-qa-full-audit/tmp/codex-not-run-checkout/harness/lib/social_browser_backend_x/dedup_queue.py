"""DedupQueue — 24h sliding-window dedup with canonical URL + sha256 fallback (S03 C3).

Per S02 A2 + OQ-04 + S03 design §C3:
  - Window: 24 hours rolling, anchored on the post's `created_at` (or
    insert time if `created_at` is missing — extractor placeholder
    "N/A" maps to insert-time semantics).
  - Primary key: canonical URL `https://<x_host>/<handle>/status/<id>`.
  - Fallback: `sha256(handle + "\\x1f" + normalised_text + "\\x1f" + time_bucket)`
    when the canonical URL is unavailable.
  - URL conflict policy (OQ-04): if a record's sha256 matches an existing
    key but the URL differs, *sha256 wins* (the sha256 record is treated
    as the canonical entry); however, the URL field is **updated to the
    latest seen URL** so downstream readers always have the freshest
    permalink.

The dedup queue is intentionally separate from the dataclass-level
table helpers in `dedup_keys_table.py`: that module owns the table
schema and per-row SQL; this module owns the policy.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from .dedup_keys_table import (
    DedupKeyRecord,
    ensure_dedup_keys_table,
    lookup_dedup_key,
)
from .schema import PostRecord

logger = logging.getLogger(__name__)

# 24h dedup window per A-C3-3.
DEFAULT_WINDOW_HOURS = 24
DEFAULT_WINDOW = timedelta(hours=DEFAULT_WINDOW_HOURS)

# Field separator for sha256 fallback — ASCII unit-separator so it can
# never appear in handle / text / timestamps.
_FS = "\x1f"

_WHITESPACE_RX = re.compile(r"\s+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value or value == "N/A":
        return None
    raw = value.strip()
    # Handle the common 'Z' suffix.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bucket_seconds(dt: datetime, window: timedelta) -> str:
    """Stable bucket id for a timestamp inside a window.

    We floor the timestamp to the start of the window so two records
    posted within the same 24h window land in the same bucket.
    """
    epoch_s = int(dt.timestamp())
    window_s = max(int(window.total_seconds()), 1)
    floor = (epoch_s // window_s) * window_s
    return str(floor)


@dataclass(frozen=True)
class DedupVerdict:
    """Result of `DedupQueue.check`."""

    key: str
    key_kind: str  # "url" | "sha256"
    is_duplicate: bool
    existing_record: Optional[DedupKeyRecord]
    canonical_url: Optional[str]


@dataclass(frozen=True)
class DedupKeys:
    """Derived dedup keys for a record."""

    url_key: Optional[str]
    sha256_key: str

    @property
    def primary_key(self) -> str:
        return self.url_key or self.sha256_key

    @property
    def primary_kind(self) -> str:
        return "url" if self.url_key else "sha256"


def _normalised_text(text: str) -> str:
    return _WHITESPACE_RX.sub(" ", text or "").strip().lower()


def canonical_url(record: PostRecord, x_host: str = "x.com") -> Optional[str]:
    """Return the canonical post URL if both id+handle present, else None.

    Trailing slashes, query strings, and tracking params are stripped.
    """
    if not record.post_id or record.post_id == "N/A":
        return None
    if not record.author_handle or record.author_handle == "N/A":
        return None
    return f"https://{x_host}/{record.author_handle}/status/{record.post_id}"


def sha256_fallback_key(
    record: PostRecord,
    *,
    now: Optional[datetime] = None,
    window: timedelta = DEFAULT_WINDOW,
) -> str:
    """sha256(handle + text + time_bucket) per OQ-04 + A-C3-4.

    `time_bucket` is derived from the record's `created_at` (24h floor);
    if missing, the current wall-clock UTC is used.
    """
    handle = (record.author_handle or "").lstrip("@")
    text = _normalised_text(record.text or "")
    posted = _parse_iso(record.created_at) or (now or _utc_now())
    bucket = _bucket_seconds(posted, window)
    blob = f"{handle}{_FS}{text}{_FS}{bucket}".encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def derive_keys(
    record: PostRecord,
    *,
    x_host: str = "x.com",
    now: Optional[datetime] = None,
    window: timedelta = DEFAULT_WINDOW,
) -> DedupKeys:
    return DedupKeys(
        url_key=canonical_url(record, x_host=x_host),
        sha256_key=sha256_fallback_key(record, now=now, window=window),
    )


class DedupQueue:
    """Persistent dedup queue backed by `social_post_dedup_keys`.

    Constructor parameters:
        conn: sqlite3.Connection (the same connection used for
              `social_posts`); the constructor will ensure the
              `social_post_dedup_keys` table exists.
        window: dedup sliding window (default 24h).
        x_host: host used to build canonical URLs (default `x.com`).
        clock: zero-arg callable returning a `datetime` (UTC) — for tests.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        window: timedelta = DEFAULT_WINDOW,
        x_host: str = "x.com",
        clock=_utc_now,
    ) -> None:
        self._conn = conn
        self._window = window
        self._x_host = x_host
        self._clock = clock
        ensure_dedup_keys_table(conn)

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def check(self, record: PostRecord) -> DedupVerdict:
        """Look up `record` against the table without writing.

        Per OQ-04: canonical URL is consulted first. If the URL is
        absent, the sha256 fallback is consulted. If the URL is present
        AND a sha256 collision exists with a *different* URL, the
        sha256 verdict wins and the existing record is returned (callers
        will later refresh the URL via `record_seen`).
        """
        keys = derive_keys(
            record,
            x_host=self._x_host,
            now=self._clock(),
            window=self._window,
        )

        if keys.url_key is not None:
            existing = lookup_dedup_key(self._conn, keys.url_key)
            if existing and self._inside_window(existing):
                return DedupVerdict(
                    key=keys.url_key,
                    key_kind="url",
                    is_duplicate=True,
                    existing_record=existing,
                    canonical_url=keys.url_key,
                )

        # Either no URL key OR url miss → check sha256 fallback.
        sha_existing = lookup_dedup_key(self._conn, keys.sha256_key)
        if sha_existing and self._inside_window(sha_existing):
            return DedupVerdict(
                key=keys.sha256_key,
                key_kind="sha256",
                is_duplicate=True,
                existing_record=sha_existing,
                canonical_url=keys.url_key,
            )

        return DedupVerdict(
            key=keys.primary_key,
            key_kind=keys.primary_kind,
            is_duplicate=False,
            existing_record=None,
            canonical_url=keys.url_key,
        )

    def record_seen(
        self,
        record: PostRecord,
        post_pk: int,
    ) -> Tuple[DedupVerdict, DedupKeyRecord]:
        """Register `record` against `post_pk` and return (verdict, stored_record).

        Idempotent: calling twice with the same `record` returns
        `is_duplicate=True` on the second call but only stores the key
        once. The stored row's `last_seen_at` is bumped on every call.

        OQ-04 URL conflict policy: if sha256 already exists with a
        different canonical URL, the sha256 row is retained as the
        canonical key (we do NOT also insert the new URL key); the
        verdict's `key_kind` reflects this.
        """
        verdict = self.check(record)
        keys = derive_keys(
            record,
            x_host=self._x_host,
            now=self._clock(),
            window=self._window,
        )

        if verdict.is_duplicate:
            # Bump last_seen_at on the winning key. Per OQ-04 the URL
            # field gets updated to the latest URL we have — we do this
            # by also upserting the URL key as an alias when present.
            stored = self._upsert(verdict.key, post_pk)
            if (
                verdict.key_kind == "sha256"
                and keys.url_key is not None
                and keys.url_key != verdict.key
            ):
                # Alias row so a later URL-keyed lookup still hits.
                self._upsert(keys.url_key, post_pk)
            return verdict, stored

        primary_key = keys.primary_key
        stored = self._upsert(primary_key, post_pk)
        # If both url + sha256 keys exist, register both so future
        # lookups by either route find the same post.
        if keys.url_key and keys.sha256_key and keys.url_key != keys.sha256_key:
            other = keys.sha256_key if primary_key == keys.url_key else keys.url_key
            self._upsert(other, post_pk)
        return verdict, stored

    def prune(self, *, before: Optional[datetime] = None) -> int:
        """Delete dedup rows whose `last_seen_at` is older than `before`.

        Returns the number of rows deleted. If `before` is None, uses
        `clock() - window`.
        """
        cutoff = (before or (self._clock() - self._window)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM social_post_dedup_keys WHERE last_seen_at < ?",
            (cutoff,),
        )
        return cur.rowcount or 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _upsert(self, key: str, post_pk: int) -> DedupKeyRecord:
        """Clock-aware upsert — uses `self._clock()` for first/last_seen_at.

        Mirrors `dedup_keys_table.upsert_dedup_key` but honours the
        injected clock so dedup-window tests are deterministic.
        """
        now = self._clock().isoformat()
        existing = self._conn.execute(
            "SELECT key, first_seen_at, last_seen_at, post_pk "
            "FROM social_post_dedup_keys WHERE key = ?",
            (key,),
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE social_post_dedup_keys SET last_seen_at = ?, post_pk = ? "
                "WHERE key = ?",
                (now, post_pk, key),
            )
            return DedupKeyRecord(
                key=key, first_seen_at=existing[1], last_seen_at=now, post_pk=post_pk
            )
        self._conn.execute(
            "INSERT INTO social_post_dedup_keys (key, first_seen_at, last_seen_at, post_pk) "
            "VALUES (?, ?, ?, ?)",
            (key, now, now, post_pk),
        )
        return DedupKeyRecord(key=key, first_seen_at=now, last_seen_at=now, post_pk=post_pk)

    def _inside_window(self, record: DedupKeyRecord) -> bool:
        last = _parse_iso(record.last_seen_at)
        if last is None:
            return True
        return (self._clock() - last) <= self._window

    @property
    def window(self) -> timedelta:
        return self._window

    @property
    def x_host(self) -> str:
        return self._x_host
