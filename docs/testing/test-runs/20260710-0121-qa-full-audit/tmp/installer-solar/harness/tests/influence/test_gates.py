"""Each gate's documented fail path must be reachable (S1-design §7)."""
from lib.influence.gates import (
    compliance_gate,
    evidence_mapping_gate,
    statement_gate,
    thesis_gate,
    transcript_gate,
)
from lib.influence.models import Author, QualityFlags, Statement, Thesis


def _stmt(**kw):
    base = dict(statement_id="s1", source="x_backend",
                text="A sufficiently long and substantive statement about scaling.",
                author=Author("x", "@u", "U"))
    base.update(kw)
    return Statement(**base)


def test_statement_gate_pass():
    assert statement_gate(_stmt()).passed


def test_statement_gate_text_too_short():
    r = statement_gate(_stmt(text="short"))
    assert not r.passed and "text_too_short" in r.fail_reasons


def test_statement_gate_marketing_and_joke():
    r = statement_gate(_stmt(quality_flags=QualityFlags(is_marketing=True, is_joke_or_meme=True)))
    assert "marketing_content" in r.fail_reasons
    assert "joke_or_meme" in r.fail_reasons


def test_statement_gate_missing_author():
    r = statement_gate(_stmt(author=Author("x", "", "")))
    assert "missing_author" in r.fail_reasons


def test_transcript_gate_na_when_no_transcript():
    assert transcript_gate(_stmt()).passed


def test_transcript_gate_too_low():
    r = transcript_gate(_stmt(quality_flags=QualityFlags(transcript_quality="low")),
                        thresholds={"transcript_min_quality": "high"})
    assert not r.passed and "transcript_quality_too_low" in r.fail_reasons


def test_thesis_gate_paths():
    good = Thesis(thesis_id="t1", claim="A" * 30, derived_from_statements=["s1"], confidence=0.8)
    assert thesis_gate(good).passed
    bad = Thesis(thesis_id="t2", claim="short", derived_from_statements=[], confidence=0.1)
    r = thesis_gate(bad)
    assert "claim_too_short" in r.fail_reasons
    assert "confidence_too_low" in r.fail_reasons
    assert "no_source_statements" in r.fail_reasons


def test_evidence_mapping_gate(sample_packet_dict):
    assert evidence_mapping_gate(sample_packet_dict).passed
    broken = dict(sample_packet_dict)
    broken["local_scores"] = {"novelty": 0.1}
    r = evidence_mapping_gate(broken)
    assert "incomplete_local_scores" in r.fail_reasons


def test_compliance_gate_blocks_raw_leak(sample_packet_dict):
    assert compliance_gate(sample_packet_dict).passed
    leak = dict(sample_packet_dict)
    leak["raw_posts"] = [{"text": "raw"}]
    r = compliance_gate(leak)
    assert "raw_post_leak_to_high_model" in r.fail_reasons
    bypass = dict(sample_packet_dict)
    bypass["thesis_id"] = ""
    assert "thesis_layer_bypassed" in compliance_gate(bypass).fail_reasons
