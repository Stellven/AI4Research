"""GitHub API budget, queue and conditional request controls.

The classes here are deliberately transport-agnostic. Production callers pass a
real fetch function; tests pass a local stub. This keeps rate-budget decisions,
ETag headers and backoff behavior inside the real GHPI call chain without
embedding credentials or network assumptions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .schema import apply_schema, utc_now_iso


FetchFn = Callable[[str, str, dict[str, str] | None], tuple[int, dict[str, str], Any]]


@dataclass
class GitHubRequest:
    url: str
    method: str = "GET"
    queue_name: str = "default"
    cost_units: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


class GitHubApiBudget:
    """SQLite-backed per-day request budget gate."""

    def __init__(self, conn: sqlite3.Connection, *, daily_cost_limit: int = 5000) -> None:
        if daily_cost_limit <= 0:
            raise ValueError("daily_cost_limit must be positive")
        self.conn = conn
        self.daily_cost_limit = daily_cost_limit
        apply_schema(conn)

    def used_today(self, *, day: str | None = None, queue_name: str | None = None) -> int:
        day = day or utc_now_iso()[:10]
        sql = "SELECT COALESCE(SUM(cost_units), 0) FROM github_api_request_log WHERE substr(created_at,1,10)=?"
        params: list[Any] = [day]
        if queue_name:
            sql += " AND queue_name=?"
            params.append(queue_name)
        return int(self.conn.execute(sql, params).fetchone()[0] or 0)

    def can_spend(self, cost_units: int, *, day: str | None = None) -> bool:
        return self.used_today(day=day) + max(0, cost_units) <= self.daily_cost_limit


class ConditionalRequestCache:
    """Persist and apply ETag/Last-Modified headers for conditional requests."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        apply_schema(conn)

    @staticmethod
    def cache_key(method: str, url: str) -> str:
        raw = f"{method.upper()} {url}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def headers_for(self, method: str, url: str) -> dict[str, str]:
        row = self.conn.execute(
            "SELECT etag, last_modified FROM github_api_etag_cache WHERE cache_key=?",
            (self.cache_key(method, url),),
        ).fetchone()
        if not row:
            return {}
        headers: dict[str, str] = {}
        if row[0]:
            headers["If-None-Match"] = row[0]
        if row[1]:
            headers["If-Modified-Since"] = row[1]
        return headers

    def update(self, method: str, url: str, response_headers: dict[str, str], status_code: int) -> None:
        etag = response_headers.get("ETag") or response_headers.get("etag")
        last_modified = response_headers.get("Last-Modified") or response_headers.get("last-modified")
        if not etag and not last_modified:
            return
        self.conn.execute(
            """INSERT OR REPLACE INTO github_api_etag_cache
               (cache_key, etag, last_modified, status_code, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (self.cache_key(method, url), etag or "", last_modified, status_code, utc_now_iso()),
        )
        self.conn.commit()


class GitHubRequestQueue:
    """Queue seam that enforces budget, backoff and conditional headers."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        fetch_fn: FetchFn,
        daily_cost_limit: int = 5000,
        default_backoff_seconds: int = 60,
    ) -> None:
        self.conn = conn
        self.fetch_fn = fetch_fn
        self.budget = GitHubApiBudget(conn, daily_cost_limit=daily_cost_limit)
        self.cache = ConditionalRequestCache(conn)
        self.default_backoff_seconds = default_backoff_seconds

    def dispatch(self, request: GitHubRequest) -> dict[str, Any]:
        if not self.budget.can_spend(request.cost_units):
            self._log(request, status_code=None, metadata={"blocked": "budget_exhausted"})
            return {"status": "budget_exhausted", "body": None, "headers": {}}

        headers = self.cache.headers_for(request.method, request.url)
        status_code, response_headers, body = self.fetch_fn(request.method, request.url, headers)
        self.cache.update(request.method, request.url, response_headers, status_code)

        backoff_until = None
        if status_code in {403, 429}:
            retry_after = int(response_headers.get("Retry-After") or self.default_backoff_seconds)
            backoff_until = (
                datetime.now(timezone.utc) + timedelta(seconds=max(1, retry_after))
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._log(
            request,
            status_code=status_code,
            response_headers=response_headers,
            backoff_until=backoff_until,
        )
        if status_code == 304:
            return {"status": "not_modified", "body": None, "headers": response_headers}
        if backoff_until:
            return {"status": "backoff", "body": body, "headers": response_headers, "backoff_until": backoff_until}
        return {"status": "ok", "body": body, "headers": response_headers}

    def _log(
        self,
        request: GitHubRequest,
        *,
        status_code: int | None,
        response_headers: dict[str, str] | None = None,
        backoff_until: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        response_headers = response_headers or {}
        created_at = utc_now_iso()
        request_id = hashlib.sha256(
            f"{request.method} {request.url} {created_at} {request.queue_name} {uuid.uuid4().hex}".encode("utf-8")
        ).hexdigest()[:24]
        merged_metadata = dict(request.metadata)
        if metadata:
            merged_metadata.update(metadata)
        self.conn.execute(
            """INSERT INTO github_api_request_log
               (request_id, queue_name, method, url, status_code, cost_units,
                rate_remaining, etag, backoff_until, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                request_id,
                request.queue_name,
                request.method.upper(),
                request.url,
                status_code,
                request.cost_units,
                _int_or_none(response_headers.get("X-RateLimit-Remaining")),
                response_headers.get("ETag") or response_headers.get("etag"),
                backoff_until,
                created_at,
                json.dumps(merged_metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        self.conn.commit()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ConditionalRequestCache",
    "GitHubApiBudget",
    "GitHubRequest",
    "GitHubRequestQueue",
]
