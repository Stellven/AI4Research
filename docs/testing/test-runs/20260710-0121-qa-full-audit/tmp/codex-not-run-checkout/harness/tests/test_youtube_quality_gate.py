import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))

from youtube.quality_gate import evaluate_quality, persist_quality_check
from youtube_002_transcripts import up as m002
from youtube_008_quality_checks import up as m008


def test_quality_gate_applies_phase2_for_non_t3():
    result = evaluate_quality(
        text="KV cache and continuous batching improve serving quality.",
        corrected_text="KV cache and continuous batching improve serving quality.",
        coverage_ratio=0.9,
        hallucination_risk=0.1,
        source_reliability=0.9,
        vocab_terms=["KV cache", "continuous batching"],
    )
    assert result.phase2_applied is True
    assert result.technical_term_hit_rate == 1.0
    assert result.final_tier in {"T0", "T1"}


def test_quality_gate_skips_phase2_for_t3():
    result = evaluate_quality(
        text="bad",
        coverage_ratio=0.1,
        hallucination_risk=0.9,
        source_reliability=0.1,
        vocab_terms=["KV cache"],
    )
    assert result.preliminary_tier == "T3"
    assert result.phase2_applied is False
    assert result.technical_term_hit_rate is None


def test_persist_quality_check():
    conn = sqlite3.connect(":memory:")
    m002(conn)
    m008(conn)
    conn.execute(
        """INSERT INTO youtube_transcripts
           (transcript_id, video_id, source) VALUES ('t1', 'v1', 'premium')"""
    )
    result = evaluate_quality(
        text="good transcript with KV cache",
        corrected_text="good transcript with KV cache",
        coverage_ratio=0.85,
        hallucination_risk=0.1,
        source_reliability=0.8,
        vocab_terms=["KV cache"],
    )
    check_id = persist_quality_check(conn, transcript_id="t1", result=result)
    row = conn.execute("SELECT quality_tier FROM quality_checks WHERE check_id = ?", (check_id,)).fetchone()
    assert row[0] == result.final_tier
