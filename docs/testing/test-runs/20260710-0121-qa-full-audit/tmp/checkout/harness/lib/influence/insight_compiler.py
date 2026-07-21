"""L5 InfluenceInsightCompiler — render the 8 unified output assets.

From one ``InfluenceEvidencePacket`` produce the 8 asset types defined by the ADR
"输出资产统一面" and the contract ``required_output_assets``:

    1. Influencer Insight Card      5. Deep Research Seed Pack
    2. Thesis Brief                 6. Open-source Project Brief
    3. Cross-source Resonance Seed  7. Finance / Event Watch
    4. AI Influence Topic           8. Action Queue

Each asset is a plain dict carrying its own ``schema_version`` and ``asset_type``
so it can be validated against schemas/influence/output_assets/*.schema.json.
"""
from __future__ import annotations

from typing import Any

from .models import InfluenceEvidencePacket

ASSET_TYPES = (
    "influencer_insight_card",
    "thesis_brief",
    "cross_source_resonance_seed",
    "ai_influence_topic",
    "deep_research_seed_pack",
    "open_source_project_brief",
    "finance_event_watch",
    "action_queue",
)


def _base(asset_type: str, packet: InfluenceEvidencePacket) -> dict[str, Any]:
    return {
        "schema_version": f"influence.output.{asset_type}.v1",
        "asset_type": asset_type,
        "packet_id": packet.packet_id,
        "thesis_id": packet.thesis_id,
    }


def build_assets(packet: InfluenceEvidencePacket) -> dict[str, dict[str, Any]]:
    """Return a dict of asset_type -> asset payload (all 8 types present)."""
    scores = packet.local_scores
    evidence = packet.mapped_evidence
    assets: dict[str, dict[str, Any]] = {}

    card = _base("influencer_insight_card", packet)
    card.update({"headline": packet.thesis_claim, "signal_strength": scores.get("signal_strength", 0.0)})
    assets["influencer_insight_card"] = card

    brief = _base("thesis_brief", packet)
    brief.update({"claim": packet.thesis_claim, "questions": packet.questions_for_high_model})
    assets["thesis_brief"] = brief

    resonance = _base("cross_source_resonance_seed", packet)
    resonance.update({"resonance_score": scores.get("cross_source_resonance", 0.0),
                      "source_statements": packet.source_statements})
    assets["cross_source_resonance_seed"] = resonance

    topic = _base("ai_influence_topic", packet)
    topic.update({"topic": packet.thesis_claim[:80], "novelty": scores.get("novelty", 0.0)})
    assets["ai_influence_topic"] = topic

    seed_pack = _base("deep_research_seed_pack", packet)
    seed_pack.update({"questions": packet.questions_for_high_model,
                      "coverage_gap": evidence.get("coverage_gap", [])})
    assets["deep_research_seed_pack"] = seed_pack

    project = _base("open_source_project_brief", packet)
    project.update({"github_repos": evidence.get("github_repos", []),
                    "hf_assets": evidence.get("hf_assets", [])})
    assets["open_source_project_brief"] = project

    finance = _base("finance_event_watch", packet)
    finance.update({"financial_events": evidence.get("financial_events", []),
                    "company_releases": evidence.get("company_releases", [])})
    assets["finance_event_watch"] = finance

    action = _base("action_queue", packet)
    action.update({"actionability": scores.get("actionability", 0.0),
                   "next_actions": packet.questions_for_high_model[:1]})
    assets["action_queue"] = action

    return assets
