from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from report_validation import build_quality_score, run_chapter_verifier, write_validation_sidecars  # noqa: E402


def _pack() -> dict:
    return {
        "chapter_id": "ch_01",
        "chapter": {"deep_writer_required": True},
        "must_use_evidence_ids": ["V001", "V002"],
        "core_evidence": [{"video_ref": "V001"}, {"video_ref": "V002"}],
        "counter_evidence": [{"id": "ce1", "summary": "adoption remains uncertain"}],
    }


def test_chapter_verifier_requires_evidence_and_deep_proof() -> None:
    markdown = (
        "## Runtime Shift\n\n"
        "判断：V001 显示 agent runtime 正在从演示走向可执行工作流。"
        "这意味着团队下一步应优先观察调度、权限和失败恢复。"
        "V002 提供了另一个证据点，但仍存在不确定性。"
    )

    missing_proof = run_chapter_verifier({"chapter_id": "ch_01", "deep_writer_required": True}, markdown, _pack())
    assert missing_proof["status"] == "failed"
    assert "deep_proof_present_if_required" in missing_proof["repair_reasons"]

    passed = run_chapter_verifier(
        {"chapter_id": "ch_01", "deep_writer_required": True},
        markdown,
        _pack(),
        {"deep_proof_path": "proof/ch_01.deep.proof.json"},
    )
    assert passed["status"] == "passed"
    assert passed["checks"]["uses_required_evidence"] is True
    assert passed["checks"]["grounded_claim_ratio"] >= 0.9


def test_chapter_verifier_flags_internal_field_leaks_and_ungrounded_claims() -> None:
    markdown = (
        "## Bad Chapter\n\n"
        "判断：这个方向已经证明会彻底改变市场。"
        "内部字段 video_id raw-secret transcript_status fetched 不应该出现。"
    )

    result = run_chapter_verifier({"chapter_id": "ch_bad"}, markdown, _pack())
    assert result["status"] == "failed"
    assert "no_internal_field_leak" in result["repair_reasons"]
    assert "grounded_claim_ratio_below_target" in result["repair_reasons"]


def test_quality_score_blocks_failed_chapters_and_writes_sidecars(tmp_path: Path) -> None:
    passed = {
        "chapter_id": "ch_01",
        "status": "passed",
        "checks": {"grounded_claim_ratio": 1.0, "has_counter_evidence": True},
    }
    failed = {
        "chapter_id": "ch_02",
        "status": "failed",
        "checks": {"grounded_claim_ratio": 0.0, "has_counter_evidence": False},
    }

    score = build_quality_score({"report_id": "r1"}, [passed, failed])
    assert score["grade"] in {"C", "D"}
    assert score["publish_decision"] != "publish"

    written = write_validation_sidecars(tmp_path, {"report_id": "r1"}, [passed, failed])
    assert written["publish_decision"] != "publish"
    assert (tmp_path / "validation" / "quality-score.json").exists()
    assert (tmp_path / "validation" / "claim-verification.json").exists()
