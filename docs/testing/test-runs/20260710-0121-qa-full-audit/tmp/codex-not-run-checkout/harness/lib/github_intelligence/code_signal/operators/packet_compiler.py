"""G4 — GitHubEvidencePacketCompiler (L4 input).

Compiles RepoSnapshot+Canonical+Enrichment+Signal into GitHubEvidencePacket.
High-model invariant: only this packet type reaches the LLM.
"""
from __future__ import annotations

from typing import Any

from ..models import (
    GitHubEvidencePacket,
    RepoCanonical,
    RepoEnrichment,
    RepoSignal,
    RepoSnapshot,
    _gen_id,
    _json_dump,
    utc_now_iso,
)


class GitHubEvidencePacketCompiler:
    """Compiles unified objects into a single GitHubEvidencePacket per repo."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def run(
        self,
        snapshot: RepoSnapshot,
        canonical: RepoCanonical | None = None,
        enrichment: RepoEnrichment | None = None,
        signal: RepoSignal | None = None,
        cross_source_refs: dict[str, Any] | None = None,
    ) -> GitHubEvidencePacket:
        snap_summary = {
            "stars": snapshot.stars,
            "forks": snapshot.forks,
            "language": snapshot.language,
            "description": snapshot.description,
            "stars_delta_24h": snapshot.stars_delta_24h,
            "stars_delta_7d": snapshot.stars_delta_7d,
        }
        enr_summary: dict[str, Any] = {}
        if enrichment:
            enr_summary = {
                "readme_tags": _json_load(enrichment.readme_top_tags_json),
                "latest_release": enrichment.latest_release_tag,
                "contributors": _json_load(enrichment.contributors_summary_json),
            }
        sig_summary: dict[str, Any] = {}
        if signal:
            sig_summary = {
                "github_hotspot": signal.github_hotspot,
                "technical_substance": signal.technical_substance,
                "community_health": signal.community_health,
                "noise_risk": signal.noise_risk,
                "signal_class": signal.signal_class,
            }

        ev_refs: list[str] = []
        if enrichment:
            ev_refs = _json_load(enrichment.evidence_ids_json)
        if signal:
            ev_refs += _json_load(signal.evidence_ids_json)

        questions = self._generate_questions(snapshot, signal)

        return GitHubEvidencePacket(
            packet_id=_gen_id("gep-"),
            repo_key=snapshot.repo_key,
            built_at=utc_now_iso(),
            snapshot_summary_json=_json_dump(snap_summary),
            enrichment_summary_json=_json_dump(enr_summary),
            signal_summary_json=_json_dump(sig_summary),
            evidence_refs_json=_json_dump(ev_refs),
            cross_source_refs_json=_json_dump(cross_source_refs or {}),
            local_scores_json=_json_dump(sig_summary),
            questions_for_high_model_json=_json_dump(questions),
        )

    def _generate_questions(
        self,
        snapshot: RepoSnapshot,
        signal: RepoSignal | None,
    ) -> list[str]:
        questions: list[str] = []
        if snapshot.description:
            questions.append(f"What is the core innovation of {snapshot.repo_key}?")
        if signal and signal.noise_risk >= 0.6:
            questions.append(
                f"Is {snapshot.repo_key} genuinely trending or hype-driven?"
            )
        if not questions:
            questions.append(f"What opportunities does {snapshot.repo_key} present?")
        return questions


def _json_load(value: str) -> Any:
    import json
    if not value:
        return []
    return json.loads(value)
