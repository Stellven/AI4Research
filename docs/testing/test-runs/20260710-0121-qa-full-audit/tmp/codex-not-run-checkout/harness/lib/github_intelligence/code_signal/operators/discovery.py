"""G1 — GitHubCandidateDiscoveryOperator (L0 Discovery).

Discovers candidate repos from trending, search, tracked watch list,
and external mention seeds. Emits RepoSnapshot[] with discovery_provenance.
"""
from __future__ import annotations

from typing import Any

from ..models import RepoSnapshot, _gen_id, _json_dump, utc_now_iso


class GitHubCandidateDiscoveryOperator:
    """Discovers repos from multiple sources and emits RepoSnapshot batch."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def run(
        self,
        trending: list[dict[str, Any]] | None = None,
        search_results: list[dict[str, Any]] | None = None,
        tracked: list[dict[str, Any]] | None = None,
        mention_seeds: list[dict[str, Any]] | None = None,
    ) -> list[RepoSnapshot]:
        snapshots: list[RepoSnapshot] = []
        seen_keys: set[str] = set()

        for source_name, items in [
            ("trending", trending or []),
            ("search", search_results or []),
            ("tracked", tracked or []),
            ("social_mention", mention_seeds or []),
        ]:
            for item in items:
                key = item.get("full_name", "")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                snapshots.append(self._item_to_snapshot(key, source_name, item))

        return snapshots

    def _item_to_snapshot(
        self, repo_key: str, source: str, item: dict[str, Any]
    ) -> RepoSnapshot:
        return RepoSnapshot(
            snapshot_id=_gen_id("snap-"),
            repo_key=repo_key,
            observed_at=item.get("observed_at", utc_now_iso()),
            source=source,
            stars=item.get("stars"),
            forks=item.get("forks"),
            watchers=item.get("watchers"),
            open_issues=item.get("open_issues"),
            language=item.get("language"),
            topics_json=_json_dump(item.get("topics", [])),
            description=item.get("description"),
            pushed_at=item.get("pushed_at"),
            archived=item.get("archived", False),
            discovery_provenance_json=_json_dump({"source": source}),
        )
