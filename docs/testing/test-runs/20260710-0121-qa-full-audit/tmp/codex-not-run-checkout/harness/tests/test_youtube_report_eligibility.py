import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from youtube.report_eligibility import build_evidence_pack, evaluate_report_eligibility


def test_report_eligibility_passes_for_t1_pack():
    pack = build_evidence_pack(
        transcript_id="t1",
        video_id="v1",
        quality_tier="T1",
        segment_refs=["seg-1"],
    )
    decision = evaluate_report_eligibility(pack)
    assert decision.eligible is True


def test_report_eligibility_rejects_low_quality_and_missing_segment_refs():
    pack = build_evidence_pack(
        transcript_id="t2",
        video_id="v2",
        quality_tier="T3",
        segment_refs=[],
        raw_evidence_strength="strong",
    )
    decision = evaluate_report_eligibility(pack)
    assert decision.eligible is False
    assert "T3_in_core" in decision.reject_codes
    assert "segment_refs_missing" in decision.reject_codes
