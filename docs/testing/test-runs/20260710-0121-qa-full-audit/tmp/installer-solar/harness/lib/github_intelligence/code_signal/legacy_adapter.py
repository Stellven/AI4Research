"""Legacy adapter — converts old github_intelligence types to unified models.

Maps four legacy types into the five unified models:
  DiscoveryCandidate  → RepoSnapshot (discovery fields)
  ReasoningPacket     → RepoEnrichment (evidence fields)
  AnalysisCard        → RepoSignal + OutputAsset (scoring + card)
  PlanningBrief       → OutputAsset (brief asset)
"""
from __future__ import annotations

from typing import Any

from .models import (
    GitHubEvidencePacket,
    OutputAsset,
    RepoCanonical,
    RepoEnrichment,
    RepoSignal,
    RepoSnapshot,
    _gen_id,
    _json_dump,
    utc_now_iso,
)


def discovery_to_snapshot(dc: Any) -> RepoSnapshot:
    """Convert legacy DiscoveryCandidate → unified RepoSnapshot."""
    metadata = getattr(dc, "metadata", {}) or {}
    return RepoSnapshot(
        snapshot_id=_gen_id("snap-"),
        repo_key=dc.full_name,
        observed_at=dc.discovered_at,
        source=dc.source_type,
        discovery_provenance_json=_json_dump(metadata),
    )


def reasoning_to_enrichment(rp: Any) -> RepoEnrichment:
    """Convert legacy ReasoningPacket → unified RepoEnrichment."""
    evidence_ids = (
        (rp.growth_evidence or [])
        + (rp.readme_evidence or [])
        + (rp.release_evidence or [])
        + (rp.social_evidence or [])
        + (rp.youtube_evidence or [])
    )
    return RepoEnrichment(
        enrichment_id=rp.packet_id,
        repo_key=rp.full_name,
        observed_at=rp.created_at,
        readme_compressed=getattr(rp, "local_project_brief", None),
        evidence_ids_json=_json_dump(evidence_ids),
        contributors_summary_json=_json_dump(rp.metrics or {}),
    )


def analysis_to_signal(card: Any) -> RepoSignal:
    """Convert legacy AnalysisCard → unified RepoSignal."""
    return RepoSignal(
        signal_id=_gen_id("sig-"),
        repo_key=card.full_name,
        scored_at=card.analysis_date,
        github_hotspot=card.heat_score or 0.0,
        technical_substance=card.technical_depth_score or 0.0,
        community_health=card.community_health_score or 0.0,
        strategic_fit=card.strategic_relevance_score or 0.0,
        signal_class="rising",
        evidence_ids_json=_json_dump(card.evidence_ids or []),
    )


def analysis_to_card_asset(card: Any) -> OutputAsset:
    """Convert legacy AnalysisCard → OutputAsset (github_hotspot_card)."""
    content = {
        "project_positioning": card.project_positioning,
        "what_it_does": card.what_it_does,
        "core_technical_idea": card.core_technical_idea,
        "why_it_is_hot": card.why_it_is_hot,
        "potential_score": card.potential_score,
        "trend_implication": card.trend_implication,
        "research_questions": card.research_questions or [],
        "risks": card.risks or [],
        "model_used": card.model_used,
    }
    return OutputAsset(
        asset_id=card.analysis_id,
        asset_type="github_hotspot_card",
        repo_key=card.full_name,
        generated_at=card.analysis_date,
        evidence_refs_json=_json_dump(card.evidence_ids or []),
        content_json=_json_dump(content),
    )


def planning_to_brief_asset(brief: Any) -> OutputAsset:
    """Convert legacy PlanningBrief → OutputAsset (direction_brief)."""
    content = {
        "opportunity_summary": brief.opportunity_summary,
        "user_pain_points": brief.user_pain_points or [],
        "target_personas": brief.target_personas or [],
        "proposed_product": brief.proposed_product,
        "mvp_scope": brief.mvp_scope,
        "technical_architecture": brief.technical_architecture,
        "risks": brief.risks or [],
        "next_steps": brief.next_steps or [],
    }
    return OutputAsset(
        asset_id=brief.brief_id,
        asset_type="direction_brief",
        repo_key=brief.full_name,
        generated_at=utc_now_iso(),
        content_json=_json_dump(content),
    )


# Reverse conversions (unified → legacy) for round-trip tests


def snapshot_to_discovery(snap: RepoSnapshot) -> dict[str, Any]:
    """Convert unified RepoSnapshot → legacy DiscoveryCandidate dict."""
    return {
        "full_name": snap.repo_key,
        "source_type": snap.source,
        "discovered_at": snap.observed_at,
        "metadata": {},
    }


def enrichment_to_reasoning(enr: RepoEnrichment) -> dict[str, Any]:
    """Convert unified RepoEnrichment → legacy ReasoningPacket dict."""
    return {
        "packet_id": enr.enrichment_id,
        "full_name": enr.repo_key,
        "created_at": enr.observed_at,
        "local_project_brief": enr.readme_compressed,
    }


def signal_to_analysis(sig: RepoSignal) -> dict[str, Any]:
    """Convert unified RepoSignal → legacy AnalysisCard dict."""
    return {
        "analysis_id": sig.signal_id,
        "full_name": sig.repo_key,
        "analysis_date": sig.scored_at,
        "heat_score": sig.github_hotspot,
        "technical_depth_score": sig.technical_substance,
        "community_health_score": sig.community_health,
        "strategic_relevance_score": sig.strategic_fit,
    }
