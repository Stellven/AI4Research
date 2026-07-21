import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.gate import transcript_gate  # noqa: E402


def test_transcript_gate_accepts_t1_core_evidence() -> None:
    decision = transcript_gate(
        "video-1",
        {
            "quality_tier": "T1",
            "entity_recall": 0.76,
            "wer": 0.21,
            "segment_density": 0.55,
        },
    )

    assert decision.grade == "T1"
    assert "core_evidence_allowed" in decision.evidence_notes


def test_transcript_gate_marks_t2_weak_evidence_only() -> None:
    decision = transcript_gate(
        "video-2",
        {
            "quality_tier": "T2",
            "entity_recall": 0.6,
            "wer": 0.35,
            "segment_density": 0.25,
        },
    )

    assert decision.grade == "T2"
    assert "weak_evidence_only" in decision.evidence_notes


def test_transcript_gate_marks_t3_excluded() -> None:
    decision = transcript_gate(
        "video-3",
        {
            "quality_tier": "T3",
            "entity_recall": 0.1,
            "wer": 0.8,
            "segment_density": 0.05,
        },
    )

    assert decision.grade == "T3"
    assert "excluded_from_core_evidence" in decision.evidence_notes
