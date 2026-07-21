"""End-to-end run_pipeline integration: Statement -> gates -> Thesis -> packet -> assets."""
from lib.influence import run_pipeline
from lib.influence.models import Author, Statement


def _statements():
    return [
        Statement(statement_id="s1", source="x_backend",
                  text="GPT-5 capability jump is underestimated by current scaling-law forecasts.",
                  author=Author("x", "@a", "A"), timestamp="2026-05-28T00:00:00Z", entities=["GPT-5"]),
        Statement(statement_id="s2", source="youtube_transcript",
                  text="GPT-5 will clearly exceed the conservative 2024 scaling predictions.",
                  author=Author("youtube", "@b", "B"), timestamp="2026-05-28T00:00:00Z", entities=["GPT-5"]),
    ]


def test_pipeline_produces_packets_and_assets():
    result = run_pipeline(_statements())
    assert result["packets"], "pipeline produced no packets"
    for packet in result["packets"]:
        # invariant: high-model payload framed as questions, no raw posts
        assert packet["questions_for_high_model"]
        assert "raw_posts" not in packet
    # every surviving packet renders 8 assets
    for assets in result["assets"].values():
        assert len(assets) == 8


def test_pipeline_drops_marketing_statements():
    spam = Statement(statement_id="s3", source="x_backend",
                     text="Sign up now for a discount! link in bio promo giveaway",
                     author=Author("x", "@c", "C"))
    result = run_pipeline([spam])
    kept_ids = [s["statement_id"] for s in result["statements"]]
    assert "s3" not in kept_ids


def test_pipeline_gate_log_records_stages():
    result = run_pipeline(_statements())
    kinds = set()
    for entry in result["gate_log"]:
        kinds.update(k for k in entry if k.endswith("_gate"))
    assert "statement_gate" in kinds
    assert "compliance_gate" in kinds
