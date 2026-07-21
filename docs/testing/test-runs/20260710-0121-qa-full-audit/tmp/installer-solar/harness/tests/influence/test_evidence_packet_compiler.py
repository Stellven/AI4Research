"""EvidencePacket compiler: 7 scores, questions, mapping + invariants."""
from lib.influence.evidence_packet_compiler import compile_packet, compute_local_scores
from lib.influence.models import LOCAL_SCORE_KEYS, Author, Statement, Thesis, empty_mapped_evidence
from lib.influence.thesis_mapper import map_thesis


def _members():
    return [
        Statement(statement_id="s1", source="x_backend", text="A" * 100,
                  author=Author("x", "@u", "U"), timestamp="2026-05-28T00:00:00Z"),
        Statement(statement_id="s2", source="youtube_transcript", text="B" * 100,
                  author=Author("youtube", "@v", "V"), timestamp="2026-05-28T00:00:00Z"),
    ]


def _thesis():
    return Thesis(thesis_id="t1", claim="X" * 40, derived_from_statements=["s1", "s2"],
                  viewpoint_cluster="gpt-5", confidence=0.8)


def test_all_seven_local_scores_present():
    scores = compute_local_scores(_thesis(), _members(), empty_mapped_evidence())
    assert set(scores) == set(LOCAL_SCORE_KEYS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_cross_source_resonance_rewards_distinct_sources():
    two = compute_local_scores(_thesis(), _members(), empty_mapped_evidence())
    one = compute_local_scores(_thesis(), _members()[:1], empty_mapped_evidence())
    assert two["cross_source_resonance"] > one["cross_source_resonance"]


def test_compile_packet_shape_and_invariant():
    packet = compile_packet(_thesis(), _members(), map_thesis(_thesis()))
    d = packet.to_dict()
    assert d["packet_id"] == "pkt-t1"
    assert d["thesis_id"] == "t1"
    assert len(d["questions_for_high_model"]) >= 1
    assert d["source_statements"] == ["s1", "s2"]
    # coverage_gap recorded because no connectors supplied
    assert d["mapped_evidence"]["coverage_gap"]


def test_connector_supplies_evidence():
    mapped = map_thesis(_thesis(), connectors={"github_repos": lambda t: [{"repo": "x/y"}]})
    assert mapped["github_repos"] == [{"repo": "x/y"}]
    packet = compile_packet(_thesis(), _members(), mapped)
    assert packet.local_scores["actionability"] >= 0.6
