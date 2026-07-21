"""G2 — RepoEnrichmentOperator (L1 Snapshot+Canonicalization, L2 Enrichment).

Consumes RepoSnapshot batch, produces filled snapshots, RepoCanonical,
RepoEnrichment with compressed structure, and evidence atoms.
"""
from __future__ import annotations

from typing import Any

from ..models import (
    RepoCanonical,
    RepoEnrichment,
    RepoSnapshot,
    _gen_id,
    _json_dump,
    utc_now_iso,
)


class RepoEnrichmentOperator:
    """Enriches discovered repos with README, releases, issues, contributors."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def run(
        self,
        snapshots: list[RepoSnapshot],
        repo_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, list[Any]]:
        """Returns {canonicals: list, enrichments: list, filled_snapshots: list}."""
        metadata = repo_metadata or {}
        canonicals: list[RepoCanonical] = []
        enrichments: list[RepoEnrichment] = []
        filled: list[RepoSnapshot] = []

        for snap in snapshots:
            meta = metadata.get(snap.repo_key, {})

            # Build canonical
            owner = snap.repo_key.split("/")[0] if "/" in snap.repo_key else ""
            canonicals.append(RepoCanonical(
                repo_key=snap.repo_key,
                canonical_name=meta.get("name", snap.repo_key),
                owner=owner,
                owner_type=meta.get("owner_type", ""),
                first_seen_at=snap.observed_at,
                last_seen_at=snap.observed_at,
                seen_sources_json=_json_dump([snap.source]),
            ))

            # Build enrichment
            ev_ids: list[str] = []
            if meta.get("readme"):
                ev_ids.append(_gen_id("ev-"))
            if meta.get("latest_release"):
                ev_ids.append(_gen_id("ev-"))

            enrichments.append(RepoEnrichment(
                enrichment_id=_gen_id("enr-"),
                repo_key=snap.repo_key,
                observed_at=utc_now_iso(),
                readme_compressed=meta.get("readme", None),
                readme_top_tags_json=_json_dump(meta.get("readme_tags", [])),
                latest_release_tag=meta.get("latest_release_tag"),
                latest_release_notes_compressed=meta.get("release_notes"),
                latest_release_at=meta.get("latest_release_at"),
                evidence_ids_json=_json_dump(ev_ids),
            ))

            # Fill snapshot with metadata
            filled_snap = RepoSnapshot(
                snapshot_id=snap.snapshot_id,
                repo_key=snap.repo_key,
                observed_at=snap.observed_at,
                source=snap.source,
                stars=meta.get("stars", snap.stars),
                forks=meta.get("forks", snap.forks),
                watchers=meta.get("watchers", snap.watchers),
                open_issues=meta.get("open_issues", snap.open_issues),
                language=meta.get("language", snap.language),
                topics_json=_json_dump(meta.get("topics", _json_load(snap.topics_json))),
                description=meta.get("description", snap.description),
                pushed_at=meta.get("pushed_at", snap.pushed_at),
            )
            filled.append(filled_snap)

        return {
            "canonicals": canonicals,
            "enrichments": enrichments,
            "filled_snapshots": filled,
        }


def _json_load(value: str) -> Any:
    import json
    if not value:
        return []
    return json.loads(value)
