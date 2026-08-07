"""Round-trip + invariant tests for the canonical influence models."""
from lib.influence.models import (
    LOCAL_SCORE_KEYS,
    InfluenceEvidencePacket,
    InfluencerProfile,
    Statement,
    Thesis,
    empty_mapped_evidence,
)


def test_statement_roundtrip(sample_statement_dict):
    stmt = Statement.from_dict(sample_statement_dict)
    assert stmt.statement_id == "stmt-fixture-001"
    assert stmt.author.handle == "@fixture_user"
    out = stmt.to_dict()
    assert out["schema_version"] == "influence.statement.v1"
    assert out["entities"] == ["GPT-5", "scaling law"]
    assert out["quality_flags"]["transcript_quality"] is None


def test_thesis_roundtrip(sample_thesis_dict):
    thesis = Thesis.from_dict(sample_thesis_dict)
    assert thesis.confidence == 0.8
    assert thesis.derived_from_statements == ["stmt-fixture-001"]
    assert Thesis.from_dict(thesis.to_dict()).claim == thesis.claim


def test_packet_roundtrip_has_all_scores(sample_packet_dict):
    packet = InfluenceEvidencePacket.from_dict(sample_packet_dict)
    for key in LOCAL_SCORE_KEYS:
        assert key in packet.local_scores
    out = packet.to_dict()
    assert out["mapped_evidence"]["coverage_gap"] == ["hf_paper_connector_missing"]


def test_empty_mapped_evidence_shape():
    block = empty_mapped_evidence()
    assert block["coverage_gap"] == []
    assert set(block) == {
        "papers", "github_repos", "hf_assets", "conference_events",
        "company_releases", "financial_events", "major_news", "coverage_gap",
    }


def test_influencer_profile_defaults():
    p = InfluencerProfile(influencer_id="inf-x", display_name="X")
    d = p.to_dict()
    assert d["schema_version"] == "influence.influencer_profile.v1"
    assert d["tier"] == "T3"
    assert InfluencerProfile.from_dict(d).influencer_id == "inf-x"
