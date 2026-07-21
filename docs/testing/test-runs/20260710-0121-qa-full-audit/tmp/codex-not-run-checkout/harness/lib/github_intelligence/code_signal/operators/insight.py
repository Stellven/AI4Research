"""G5 — GitHubHotspotInsightOperator (L4 output).

Consumes ONLY GitHubEvidencePacket. Produces 7 output asset types.
Invariant: raises TypeError if input is not GitHubEvidencePacket.
"""
from __future__ import annotations

from typing import Any

from ..models import (
    ASSET_TYPES,
    GitHubEvidencePacket,
    OutputAsset,
    _gen_id,
    _json_dump,
    utc_now_iso,
)


class GitHubHotspotInsightOperator:
    """Produces 7 output assets from evidence packets.

    Enforces: input must be GitHubEvidencePacket. Raw repo lists are rejected.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def run(self, packets: list[GitHubEvidencePacket]) -> list[OutputAsset]:
        for pkt in packets:
            if not isinstance(pkt, GitHubEvidencePacket):
                raise TypeError(
                    f"GitHubHotspotInsightOperator only accepts "
                    f"GitHubEvidencePacket, got {type(pkt).__name__}"
                )

        assets: list[OutputAsset] = []
        for pkt in packets:
            assets.extend(self._produce_all_assets(pkt))
        return assets

    def _produce_all_assets(self, pkt: GitHubEvidencePacket) -> list[OutputAsset]:
        return [
            self._hotspot_card(pkt),
            self._direction_brief(pkt),
            self._intervention_plan(pkt),
            self._open_source_brief(pkt),
            self._ai_influence_topic(pkt),
            self._deep_research_seed(pkt),
            self._action_queue(pkt),
        ]

    def _hotspot_card(self, pkt: GitHubEvidencePacket) -> OutputAsset:
        return OutputAsset(
            asset_type="github_hotspot_card",
            repo_key=pkt.repo_key,
            generated_at=utc_now_iso(),
            evidence_refs_json=pkt.evidence_refs_json,
            content_json=_json_dump({
                "title": f"Hotspot: {pkt.repo_key}",
                "resonance_level": pkt.resonance_level,
                "signal_summary": pkt.signal_summary_json,
            }),
        )

    def _direction_brief(self, pkt: GitHubEvidencePacket) -> OutputAsset:
        return OutputAsset(
            asset_type="direction_brief",
            repo_key=pkt.repo_key,
            generated_at=utc_now_iso(),
            evidence_refs_json=pkt.evidence_refs_json,
            content_json=_json_dump({
                "direction": f"Strategic direction for {pkt.repo_key}",
                "resonance_level": pkt.resonance_level,
                "questions": pkt.questions_for_high_model_json,
            }),
        )

    def _intervention_plan(self, pkt: GitHubEvidencePacket) -> OutputAsset:
        return OutputAsset(
            asset_type="community_intervention_plan",
            repo_key=pkt.repo_key,
            generated_at=utc_now_iso(),
            evidence_refs_json=pkt.evidence_refs_json,
            content_json=_json_dump({
                "plan": f"Community intervention for {pkt.repo_key}",
            }),
        )

    def _open_source_brief(self, pkt: GitHubEvidencePacket) -> OutputAsset:
        return OutputAsset(
            asset_type="open_source_project_brief",
            repo_key=pkt.repo_key,
            generated_at=utc_now_iso(),
            evidence_refs_json=pkt.evidence_refs_json,
            content_json=_json_dump({
                "brief": f"Open-source opportunity for {pkt.repo_key}",
            }),
        )

    def _ai_influence_topic(self, pkt: GitHubEvidencePacket) -> OutputAsset:
        return OutputAsset(
            asset_type="ai_influence_topic",
            repo_key=pkt.repo_key,
            generated_at=utc_now_iso(),
            evidence_refs_json=pkt.evidence_refs_json,
            content_json=_json_dump({
                "topic": f"AI influence signal from {pkt.repo_key}",
            }),
        )

    def _deep_research_seed(self, pkt: GitHubEvidencePacket) -> OutputAsset:
        return OutputAsset(
            asset_type="deep_research_seed_pack",
            repo_key=pkt.repo_key,
            generated_at=utc_now_iso(),
            evidence_refs_json=pkt.evidence_refs_json,
            content_json=_json_dump({
                "seed": f"Deep research seed for {pkt.repo_key}",
                "questions": pkt.questions_for_high_model_json,
            }),
        )

    def _action_queue(self, pkt: GitHubEvidencePacket) -> OutputAsset:
        return OutputAsset(
            asset_type="action_queue",
            repo_key=pkt.repo_key,
            generated_at=utc_now_iso(),
            evidence_refs_json=pkt.evidence_refs_json,
            content_json=_json_dump({
                "actions": [f"Review {pkt.repo_key}"],
            }),
        )
