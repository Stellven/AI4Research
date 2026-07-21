"""Discovery expansion adapters for GitHub Intelligence.

Adds organization/maintainer discovery, similar-repo expansion and a GH Archive
compatibility seam without requiring BigQuery at runtime.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable

if __package__ is None or __package__ == "":
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from schema import (
        DiscoveryCandidate,
        GHArchiveBackfillCursor,
        RepoEvent,
        SimilarRepoExpansion,
        insert_row,
        utc_now_iso,
    )
else:
    from ..schema import (
        DiscoveryCandidate,
        GHArchiveBackfillCursor,
        RepoEvent,
        SimilarRepoExpansion,
        insert_row,
        utc_now_iso,
    )


FetchFn = Callable[[str, dict[str, str]], dict[str, Any] | list[dict[str, Any]]]


def _default_fetch(url: str, headers: dict[str, str]) -> dict[str, Any] | list[dict[str, Any]]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _headers(github_token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def _repo_name(item: dict[str, Any]) -> str:
    return str(item.get("full_name") or "")


class OrganizationExpansionAdapter:
    """Discover repos owned by organizations observed in seed repo names."""

    source_type = "organization"

    def __init__(
        self,
        github_token: str | None = None,
        fetch_fn: FetchFn | None = None,
        per_page: int = 30,
    ) -> None:
        self.github_token = github_token
        self._fetch = fetch_fn or _default_fetch
        self.per_page = per_page

    def run(self, seed_repos: list[str], since: datetime | None = None) -> list[DiscoveryCandidate]:
        now = utc_now_iso()
        seen: set[str] = set(seed_repos)
        results: list[DiscoveryCandidate] = []
        for owner in sorted({repo.split("/", 1)[0] for repo in seed_repos if "/" in repo}):
            url = f"https://api.github.com/orgs/{urllib.parse.quote(owner)}/repos?per_page={self.per_page}&sort=pushed"
            try:
                data = self._fetch(url, _headers(self.github_token))
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                full_name = _repo_name(item)
                if not full_name or full_name in seen:
                    continue
                seen.add(full_name)
                results.append(DiscoveryCandidate(
                    full_name=full_name,
                    source_type=self.source_type,
                    discovered_at=now,
                    metadata={
                        "expansion_type": "organization",
                        "seed_owner": owner,
                        "organization": owner,
                        "stars": item.get("stargazers_count"),
                        "forks": item.get("forks_count"),
                        "pushed_at": item.get("pushed_at"),
                        "language": item.get("language"),
                        "topics": item.get("topics") or [],
                    },
                ))
        return results


class MaintainerExpansionAdapter:
    """Discover repos owned by maintainers/contributors of seed repos."""

    source_type = "maintainer"

    def __init__(
        self,
        github_token: str | None = None,
        fetch_fn: FetchFn | None = None,
        per_page: int = 30,
        max_maintainers_per_repo: int = 5,
    ) -> None:
        self.github_token = github_token
        self._fetch = fetch_fn or _default_fetch
        self.per_page = per_page
        self.max_maintainers_per_repo = max_maintainers_per_repo

    def run(self, seed_repos: list[str], since: datetime | None = None) -> list[DiscoveryCandidate]:
        now = utc_now_iso()
        seen: set[str] = set(seed_repos)
        results: list[DiscoveryCandidate] = []
        for seed_repo in seed_repos:
            contributors_url = f"https://api.github.com/repos/{urllib.parse.quote(seed_repo)}/contributors?per_page={self.max_maintainers_per_repo}"
            try:
                contributors = self._fetch(contributors_url, _headers(self.github_token))
            except Exception:
                continue
            if not isinstance(contributors, list):
                continue
            for contributor in contributors[: self.max_maintainers_per_repo]:
                login = contributor.get("login")
                if not login:
                    continue
                repos_url = f"https://api.github.com/users/{urllib.parse.quote(str(login))}/repos?per_page={self.per_page}&sort=pushed"
                try:
                    repos = self._fetch(repos_url, _headers(self.github_token))
                except Exception:
                    continue
                if not isinstance(repos, list):
                    continue
                for item in repos:
                    full_name = _repo_name(item)
                    if not full_name or full_name in seen:
                        continue
                    seen.add(full_name)
                    results.append(DiscoveryCandidate(
                        full_name=full_name,
                        source_type=self.source_type,
                        discovered_at=now,
                        metadata={
                            "expansion_type": "maintainer",
                            "seed_repo": seed_repo,
                            "maintainer_login": login,
                            "contributions": contributor.get("contributions"),
                            "stars": item.get("stargazers_count"),
                            "forks": item.get("forks_count"),
                            "pushed_at": item.get("pushed_at"),
                            "language": item.get("language"),
                            "topics": item.get("topics") or [],
                        },
                    ))
        return results


class SimilarRepoExpansionAdapter:
    """Find similar repos from seed metadata using GitHub Search API."""

    source_type = "similar_repo"

    def __init__(
        self,
        github_token: str | None = None,
        fetch_fn: FetchFn | None = None,
        per_page: int = 10,
    ) -> None:
        self.github_token = github_token
        self._fetch = fetch_fn or _default_fetch
        self.per_page = per_page

    def run(
        self,
        seed_repos: list[dict[str, Any]],
        since: datetime | None = None,
    ) -> tuple[list[DiscoveryCandidate], list[SimilarRepoExpansion]]:
        now = utc_now_iso()
        candidates: list[DiscoveryCandidate] = []
        edges: list[SimilarRepoExpansion] = []
        seen: set[tuple[str, str]] = set()
        for seed in seed_repos:
            seed_repo = str(seed.get("full_name") or "")
            if "/" not in seed_repo:
                continue
            topics = [str(t) for t in (seed.get("topics") or []) if t]
            language = seed.get("language")
            terms = [f"topic:{t}" for t in topics[:3]]
            if language:
                terms.append(f"language:{language}")
            if not terms:
                continue
            query = " ".join(terms)
            url = (
                "https://api.github.com/search/repositories?"
                f"q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={self.per_page}"
            )
            try:
                data = self._fetch(url, _headers(self.github_token))
            except Exception:
                continue
            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                continue
            for item in items:
                full_name = _repo_name(item)
                if not full_name or full_name == seed_repo or (seed_repo, full_name) in seen:
                    continue
                seen.add((seed_repo, full_name))
                item_topics = set(item.get("topics") or [])
                shared_topics = sorted(set(topics) & item_topics)
                score = self._score(topics, item.get("topics") or [], language, item.get("language"))
                reason = self._reason(shared_topics, language, item.get("language"))
                edge = SimilarRepoExpansion(
                    seed_repo=seed_repo,
                    similar_repo=full_name,
                    similarity_reason=reason,
                    similarity_score=score,
                    discovered_at=now,
                    metadata={
                        "query": query,
                        "seed_topics": topics,
                        "similar_topics": item.get("topics") or [],
                        "shared_topics": shared_topics,
                        "seed_language": language,
                        "similar_language": item.get("language"),
                    },
                )
                edges.append(edge)
                candidates.append(DiscoveryCandidate(
                    full_name=full_name,
                    source_type=self.source_type,
                    discovered_at=now,
                    metadata={
                        "seed_repo": edge.seed_repo,
                        "similar_repo": edge.similar_repo,
                        "similarity_reason": edge.similarity_reason,
                        "similarity_score": edge.similarity_score,
                        "stars": item.get("stargazers_count"),
                        "forks": item.get("forks_count"),
                        "language": item.get("language"),
                        "topics": item.get("topics") or [],
                    },
                ))
        return candidates, edges

    @staticmethod
    def _score(seed_topics: list[str], item_topics: list[str], seed_language: Any, item_language: Any) -> float:
        seed_set = set(seed_topics)
        item_set = set(item_topics)
        topic_score = len(seed_set & item_set) / max(len(seed_set | item_set), 1)
        language_score = 0.25 if seed_language and seed_language == item_language else 0.0
        return round(min(1.0, topic_score + language_score), 4)

    @staticmethod
    def _reason(shared_topics: list[str], seed_language: Any, item_language: Any) -> str:
        parts: list[str] = []
        if shared_topics:
            parts.append("shared topics: " + ", ".join(shared_topics))
        if seed_language and seed_language == item_language:
            parts.append(f"same language: {seed_language}")
        return "; ".join(parts) or "GitHub search similarity query match"


class GHArchiveCompatibilityAdapter:
    """Interface seam for GH Archive backfills.

    The default backend records a cursor and returns no events; callers can inject
    `backfill_fn` to stream real GH Archive/BigQuery rows without changing pipeline
    code later.
    """

    def __init__(
        self,
        backfill_fn: Callable[[str, str, str, tuple[str, ...]], list[RepoEvent]] | None = None,
        backend: str = "compatibility_seam",
    ) -> None:
        self._backfill = backfill_fn
        self.backend = backend

    def backfill(
        self,
        full_name: str,
        start_at: str,
        end_at: str,
        conn: Any | None = None,
        event_types: tuple[str, ...] = RepoEvent.EVENT_TYPES,
    ) -> list[RepoEvent]:
        cursor = GHArchiveBackfillCursor(
            cursor_id=self._cursor_id(full_name, start_at, end_at),
            full_name=full_name,
            start_at=start_at,
            end_at=end_at,
            status="running" if self._backfill else "pending",
            backend=self.backend,
            metadata={"event_types": list(event_types)},
        )
        if conn is not None:
            insert_row(conn, GHArchiveBackfillCursor.TABLE, cursor.to_row())

        events = self._backfill(full_name, start_at, end_at, event_types) if self._backfill else []
        if conn is not None:
            for event in events:
                _insert_repo_event_append_only(conn, event)
            cursor.status = "complete" if self._backfill else "pending"
            cursor.last_event_at = max((event.event_at for event in events), default=None)
            cursor.updated_at = utc_now_iso()
            insert_row(conn, GHArchiveBackfillCursor.TABLE, cursor.to_row())
            conn.commit()
        return events

    @staticmethod
    def _cursor_id(full_name: str, start_at: str, end_at: str) -> str:
        digest = hashlib.sha256(f"{full_name}\0{start_at}\0{end_at}".encode()).hexdigest()[:18]
        return f"gha-{digest}"


def _insert_repo_event_append_only(conn: Any, event: RepoEvent) -> None:
    row = event.to_row()
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT OR IGNORE INTO {RepoEvent.TABLE}({','.join(cols)}) VALUES ({placeholders})",
        [row[col] for col in cols],
    )
