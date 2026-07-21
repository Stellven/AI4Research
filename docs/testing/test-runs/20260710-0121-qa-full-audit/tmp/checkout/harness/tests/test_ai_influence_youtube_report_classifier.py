import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.classifier import group_classifier  # noqa: E402
from ai_influence_youtube_report.schema import GateDecision, TranscriptGrade  # noqa: E402


def _gate(grade: TranscriptGrade = TranscriptGrade.T1) -> GateDecision:
    return GateDecision("v1", grade, 0.8, 0.2, 0.6, [], "2026-05-29T00:00:00Z")


def test_group_classifier_outputs_closed_group_and_six_signals() -> None:
    decision = group_classifier(
        {"title": "Google I/O keynote: Gemini agent platform", "duration_min": 60, "slide_density": 0.5},
        _gate(),
    )

    assert decision.group_type in {"event", "conference", "keynote", "interview", "tutorial", "product_update", "other"}
    assert set(decision.signal_breakdown) == {"S1", "S2", "S3", "S4", "S5", "S6"}
    assert decision.fallback_used is False


def test_group_classifier_rejects_t3() -> None:
    import pytest

    with pytest.raises(ValueError, match="T3"):
        group_classifier({"title": "anything"}, _gate(TranscriptGrade.T3))
