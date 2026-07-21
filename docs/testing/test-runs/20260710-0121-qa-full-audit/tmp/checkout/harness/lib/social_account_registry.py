"""Social account registry — handle normalisation and account-level helpers.

Provides:
  normalize_handle(raw)         → canonical handle (lowercase, @-stripped, URL-unwrapped)
  ensure_registry_columns(conn) → idempotent migration: adds missing columns to
                                   social_accounts when absent
  compute_snapshot_deltas(…)    → 1h/6h/24h engagement deltas + velocity_score
  SocialAccountRegistry         → CRUD wrapper with import_manual seam
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from typing import Any, Dict, List, Optional

# Matches https://x.com/<handle>  or  https://twitter.com/<handle>
# Also accepts optional www. prefix.
_X_URL_RE = re.compile(
    r"https?://(?:(?:www\.)?(?:twitter|x)\.com)/([A-Za-z0-9_]{1,50})(?:/|$|[?#])",
    re.I,
)


def normalize_handle(raw: str) -> str:
    """Return the canonical handle from any raw input.

    Normalisation rules (applied in order):
      1. Strip leading/trailing whitespace.
      2. If the string looks like an x.com or twitter.com profile URL, extract
         the path segment immediately after the domain.
      3. Strip a single leading '@'.
      4. Lowercase.

    Examples::
        normalize_handle("@Karpathy")                          → "karpathy"
        normalize_handle("https://x.com/Karpathy")            → "karpathy"
        normalize_handle("https://twitter.com/ylecun?lang=en") → "ylecun"
        normalize_handle("  LeCun  ")                          → "lecun"
    """
    s = (raw or "").strip()
    m = _X_URL_RE.match(s)
    if m:
        return m.group(1).lower()
    return s.lstrip("@").lower()


def ensure_registry_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add the 'status' column to social_accounts.

    'status' TEXT NOT NULL DEFAULT 'active'
    Valid values (by convention): 'active' | 'inactive' | 'suspended' | 'rate_limited'
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='social_accounts'"
    ).fetchone()
    if not exists:
        return
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(social_accounts)").fetchall()
    }
    if "status" not in existing:
        conn.execute(
            "ALTER TABLE social_accounts ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
        )
        conn.commit()


def compute_snapshot_deltas(
    conn: sqlite3.Connection,
    post_id: str,
    reply_count: int,
    repost_count: int,
    like_count: int,
    view_count: int | None,
    now_iso: str,
) -> tuple[int, int, int, float]:
    """Return (delta_1h, delta_6h, delta_24h, velocity_score) for a snapshot.

    Engagement proxy = reply + repost + like + floor(view * 0.05).
    Delta = max(0, current_engagement − historical_engagement_at_cutoff).
    velocity_score  = min(1.0, delta_1h * 3 / max(1, current_engagement)).
    """
    now_dt = dt.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))

    def _eng(r: int, rp: int, lk: int, vc: int | None) -> int:
        base = (r or 0) + (rp or 0) + (lk or 0)
        return base + (int((vc or 0) * 0.05) if vc is not None else 0)

    current = _eng(reply_count, repost_count, like_count, view_count)

    def _delta_for_hours(hours: float) -> int:
        # Find the OLDEST snapshot within the last `hours` to measure change over that window.
        window_start = (now_dt - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = conn.execute(
            "SELECT reply_count, repost_count, like_count, view_count "
            "FROM social_post_snapshots "
            "WHERE post_id=? AND snapshot_at >= ? "
            "ORDER BY snapshot_at ASC LIMIT 1",
            (post_id, window_start),
        ).fetchone()
        if row is None:
            return 0
        return max(0, current - _eng(row[0], row[1], row[2], row[3]))

    d1h = _delta_for_hours(1.0)
    d6h = _delta_for_hours(6.0)
    d24h = _delta_for_hours(24.0)
    velocity = round(min(1.0, d1h * 3.0 / max(1, current)), 4) if current > 0 else 0.0
    return d1h, d6h, d24h, velocity


# ---------------------------------------------------------------------------
# SocialAccountRegistry — CRUD wrapper with import_manual seam
# ---------------------------------------------------------------------------

_REGISTRY_COLUMNS = {
    "raw_handle": "TEXT NOT NULL DEFAULT ''",
    "account_id": "TEXT NOT NULL DEFAULT ''",
    "platform": "TEXT NOT NULL DEFAULT 'x'",
    "display_name": "TEXT NOT NULL DEFAULT ''",
    "category": "TEXT NOT NULL DEFAULT ''",
    "tier": "TEXT NOT NULL DEFAULT 'tier2'",
    "status": "TEXT NOT NULL DEFAULT 'active'",
    "enabled": "INTEGER NOT NULL DEFAULT 1",
    "weight": "REAL NOT NULL DEFAULT 1.0",
    "role_profile_json": "TEXT NOT NULL DEFAULT '{}'",
    "scan_policy_json": "TEXT NOT NULL DEFAULT '{}'",
    "collection_backend": "TEXT NOT NULL DEFAULT 'rss'",
    "last_success_at": "TEXT",
    "last_error": "TEXT NOT NULL DEFAULT ''",
    "failure_count": "INTEGER NOT NULL DEFAULT 0",
    "last_scanned_at": "TEXT",
    "imported_at": "TEXT NOT NULL DEFAULT ''",
}

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS social_accounts (
    handle            TEXT PRIMARY KEY,
    raw_handle        TEXT NOT NULL DEFAULT '',
    account_id        TEXT NOT NULL DEFAULT '',
    platform          TEXT NOT NULL DEFAULT 'x',
    display_name      TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT '',
    tier              TEXT NOT NULL DEFAULT 'tier2',
    enabled           INTEGER NOT NULL DEFAULT 1,
    status            TEXT NOT NULL DEFAULT 'active',
    weight            REAL NOT NULL DEFAULT 1.0,
    role_profile_json TEXT NOT NULL DEFAULT '{}',
    scan_policy_json  TEXT NOT NULL DEFAULT '{}',
    collection_backend TEXT NOT NULL DEFAULT 'rss',
    last_success_at   TEXT,
    last_error        TEXT NOT NULL DEFAULT '',
    failure_count     INTEGER NOT NULL DEFAULT 0,
    last_scanned_at   TEXT,
    imported_at       TEXT NOT NULL DEFAULT ''
);
"""


class SocialAccountRegistry:
    """CRUD wrapper for social_accounts with import_manual seam.

    Usage::
        reg = SocialAccountRegistry(conn)
        reg.ensure_schema()
        reg.upsert("karpathy", category="research", tier="tier1", weight=2.0)
        reg.import_manual(["ylecun", "@sama", "https://x.com/jeffdean"])
        account = reg.get("karpathy")
        enabled = reg.list_enabled()
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create social_accounts table if absent; add missing columns idempotently."""
        self._conn.executescript(_CREATE_TABLE_SQL)
        existing = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(social_accounts)").fetchall()
        }
        for col, ddl in _REGISTRY_COLUMNS.items():
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE social_accounts ADD COLUMN {col} {ddl}"
                )
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert(
        self,
        raw: str,
        *,
        account_id: str = "",
        platform: str = "x",
        display_name: str = "",
        category: str = "",
        tier: str = "tier2",
        status: str = "active",
        enabled: bool = True,
        weight: float = 1.0,
        role_profile: Optional[Dict[str, Any]] = None,
        scan_policy: Optional[Dict[str, Any]] = None,
        collection_backend: str = "rss",
        imported_at: Optional[str] = None,
    ) -> str:
        """Insert or replace an account.  Returns the normalised handle."""
        handle = normalize_handle(raw)
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            "INSERT INTO social_accounts "
            "(handle, raw_handle, account_id, platform, display_name, category, tier, "
            "status, enabled, weight, role_profile_json, scan_policy_json, "
            "collection_backend, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(handle) DO UPDATE SET "
            "raw_handle=excluded.raw_handle, account_id=excluded.account_id, "
            "platform=excluded.platform, display_name=excluded.display_name, "
            "category=excluded.category, tier=excluded.tier, status=excluded.status, "
            "enabled=excluded.enabled, weight=excluded.weight, "
            "role_profile_json=excluded.role_profile_json, "
            "scan_policy_json=excluded.scan_policy_json, "
            "collection_backend=excluded.collection_backend",
            (
                handle,
                raw,
                account_id,
                platform,
                display_name,
                category,
                tier,
                status,
                1 if enabled else 0,
                weight,
                json.dumps(role_profile or {}, ensure_ascii=False),
                json.dumps(scan_policy or {}, ensure_ascii=False),
                collection_backend,
                imported_at or now,
            ),
        )
        self._conn.commit()
        return handle

    def get(self, raw: str) -> Optional[Dict[str, Any]]:
        """Return the account row as a dict, or None if not found."""
        handle = normalize_handle(raw)
        row = self._conn.execute(
            "SELECT * FROM social_accounts WHERE handle=?", (handle,)
        ).fetchone()
        if row is None:
            return None
        desc = self._conn.execute("PRAGMA table_info(social_accounts)").fetchall()
        cols = [r[1] for r in desc]
        return dict(zip(cols, row))

    def list_enabled(
        self,
        tier: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all enabled accounts, optionally filtered by tier/category."""
        q = "SELECT * FROM social_accounts WHERE enabled=1"
        params: List[Any] = []
        if tier:
            q += " AND tier=?"
            params.append(tier)
        if category:
            q += " AND category=?"
            params.append(category)
        q += " ORDER BY tier, weight DESC, handle"
        rows = self._conn.execute(q, params).fetchall()
        desc = self._conn.execute("PRAGMA table_info(social_accounts)").fetchall()
        cols = [r[1] for r in desc]
        return [dict(zip(cols, r)) for r in rows]

    def set_status(self, raw: str, status: str) -> None:
        """Update the status field of an account."""
        handle = normalize_handle(raw)
        self._conn.execute(
            "UPDATE social_accounts SET status=? WHERE handle=?", (status, handle)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # import_manual seam
    # ------------------------------------------------------------------

    def import_manual(
        self,
        handles: List[Any],
        *,
        category: str = "",
        tier: str = "tier2",
        weight: float = 1.0,
        collection_backend: str = "manual_curated",
        scan_policy: Optional[Dict[str, Any]] = None,
        imported_at: Optional[str] = None,
    ) -> List[str]:
        """Bulk-import accounts from a list of raw handles or dicts.

        Each entry may be:
          - a plain string (raw handle / URL) → upserted with supplied defaults
          - a dict with a 'handle' key plus optional overrides

        Returns the list of normalised handles that were imported.
        """
        now = imported_at or dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        result: List[str] = []
        for entry in handles:
            if isinstance(entry, str):
                h = self.upsert(
                    entry,
                    category=category,
                    tier=tier,
                    weight=weight,
                    collection_backend=collection_backend,
                    scan_policy=scan_policy,
                    imported_at=now,
                )
            elif isinstance(entry, dict):
                raw = entry.get("handle") or entry.get("raw_handle") or ""
                h = self.upsert(
                    raw,
                    account_id=entry.get("account_id", ""),
                    platform=entry.get("platform", "x"),
                    display_name=entry.get("display_name", ""),
                    category=entry.get("category", category),
                    tier=entry.get("tier", tier),
                    status=entry.get("status", "active"),
                    enabled=entry.get("enabled", True),
                    weight=float(entry.get("weight", weight)),
                    role_profile=entry.get("role_profile"),
                    scan_policy=entry.get("scan_policy", scan_policy),
                    collection_backend=entry.get("collection_backend", collection_backend),
                    imported_at=now,
                )
            else:
                continue
            result.append(h)
        return result
