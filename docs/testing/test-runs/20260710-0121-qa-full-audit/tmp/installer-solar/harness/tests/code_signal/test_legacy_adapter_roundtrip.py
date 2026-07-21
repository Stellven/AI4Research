"""Test legacy adapter round-trip — legacy ↔ unified conversion."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.legacy_adapter import (
    analysis_to_card_asset,
    analysis_to_signal,
    discovery_to_snapshot,
    enrichment_to_reasoning,
    planning_to_brief_asset,
    reasoning_to_enrichment,
    signal_to_analysis,
    snapshot_to_discovery,
)
from github_intelligence.code_signal.models import (
    RepoEnrichment, RepoSignal, RepoSnapshot,
)


# Stubs mimicking legacy dataclass interface

class _DiscoveryCandidate:
    def __init__(self, full_name, source_type, discovered_at, metadata=None):
        self.full_name = full_name
        self.source_type = source_type
        self.discovered_at = discovered_at
        self.metadata = metadata or {}


class _ReasoningPacket:
    def __init__(self, packet_id, full_name, created_at, local_project_brief=None,
                 growth_evidence=None, readme_evidence=None, metrics=None):
        self.packet_id = packet_id
        self.full_name = full_name
        self.created_at = created_at
        self.local_project_brief = local_project_brief
        self.growth_evidence = growth_evidence or []
        self.readme_evidence = readme_evidence or []
        self.release_evidence = []
        self.social_evidence = []
        self.youtube_evidence = []
        self.metrics = metrics or {}


class _AnalysisCard:
    def __init__(self, analysis_id, full_name, analysis_date, heat_score=None,
                 technical_depth_score=None, community_health_score=None,
                 strategic_relevance_score=None, evidence_ids=None,
                 project_positioning=None, what_it_does=None):
        self.analysis_id = analysis_id
        self.full_name = full_name
        self.analysis_date = analysis_date
        self.heat_score = heat_score
        self.technical_depth_score = technical_depth_score
        self.community_health_score = community_health_score
        self.strategic_relevance_score = strategic_relevance_score
        self.evidence_ids = evidence_ids or []
        self.project_positioning = project_positioning
        self.what_it_does = what_it_does
        self.core_technical_idea = None
        self.why_it_is_hot = None
        self.potential_score = None
        self.trend_implication = None
        self.research_questions = []
        self.risks = []
        self.model_used = None


class _PlanningBrief:
    def __init__(self, brief_id, full_name, analysis_id, opportunity_summary=None,
                 next_steps=None):
        self.brief_id = brief_id
        self.full_name = full_name
        self.analysis_id = analysis_id
        self.opportunity_summary = opportunity_summary
        self.user_pain_points = []
        self.target_personas = []
        self.proposed_product = None
        self.mvp_scope = None
        self.technical_architecture = None
        self.risks = []
        self.validation_metrics = []
        self.next_steps = next_steps or []


def test_discovery_roundtrip():
    dc = _DiscoveryCandidate("owner/repo", "trending", "2026-01-01T00:00:00Z")
    snap = discovery_to_snapshot(dc)
    assert snap.repo_key == "owner/repo"
    assert snap.source == "trending"
    back = snapshot_to_discovery(snap)
    assert back["full_name"] == "owner/repo"
    assert back["source_type"] == "trending"


def test_reasoning_roundtrip():
    rp = _ReasoningPacket("pkt-1", "owner/repo", "2026-01-01T00:00:00Z",
                          local_project_brief="A project",
                          growth_evidence=["ev-1"])
    enr = reasoning_to_enrichment(rp)
    assert enr.repo_key == "owner/repo"
    assert enr.readme_compressed == "A project"
    back = enrichment_to_reasoning(enr)
    assert back["full_name"] == "owner/repo"
    assert back["local_project_brief"] == "A project"


def test_analysis_roundtrip():
    card = _AnalysisCard("card-1", "owner/repo", "2026-01-01",
                         heat_score=0.8, technical_depth_score=0.6,
                         evidence_ids=["ev-1", "ev-2", "ev-3"],
                         project_positioning="A hot project")
    sig = analysis_to_signal(card)
    assert sig.repo_key == "owner/repo"
    assert sig.github_hotspot == 0.8
    back = signal_to_analysis(sig)
    assert back["full_name"] == "owner/repo"
    assert back["heat_score"] == 0.8


def test_analysis_to_card_asset():
    card = _AnalysisCard("card-1", "owner/repo", "2026-01-01",
                         evidence_ids=["ev-1"])
    asset = analysis_to_card_asset(card)
    assert asset.asset_type == "github_hotspot_card"
    assert asset.repo_key == "owner/repo"


def test_planning_to_brief_asset():
    brief = _PlanningBrief("brief-1", "owner/repo", "card-1",
                           opportunity_summary="Great opportunity",
                           next_steps=["Step 1"])
    asset = planning_to_brief_asset(brief)
    assert asset.asset_type == "direction_brief"
    assert asset.repo_key == "owner/repo"
