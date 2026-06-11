import pytest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.status_surface import build_status_surface  # noqa: E402


def test_status_surface_has_required_categories() -> None:
    surface = build_status_surface({
        "run_id": "run-1",
        "state": "validated",
        "gate_decisions": [{"grade": "T1"}, {"grade": "T2"}],
        "groups": [{"group_type": "keynote"}],
        "validator": {"overall": "PASS"},
        "archive": {"status": "ready"},
        "artifacts": [{"type": "html"}],
    })

    assert surface["gate_counts"]["T1"] == 1
    assert surface["group_counts"]["keynote"] == 1
    assert "validator" in surface
    assert "archive" in surface
    assert surface["chapter_state"] == {}


def test_status_surface_blocks_internal_field_leak() -> None:
    with pytest.raises(ValueError, match="video_id"):
        build_status_surface({"artifacts": [{"video_id": "abc"}]})


def test_status_surface_exposes_quality_and_repair_sidecars() -> None:
    surface = build_status_surface({
        "run_id": "run-2",
        "state": "blocked",
        "blocked_reasons": ["ch_01:grounded_claim_ratio_below_target"],
        "chapter_state": {"ch_01": "failed"},
        "quality": {"grade": "C", "publish_decision": "internal_only"},
        "repair_summaries": [{"chapter_ref": "ch_01", "attempt": 1}],
        "sidecar_refs": ["validation/quality-score.json"],
    })

    assert surface["blocked_reasons"] == ["ch_01:grounded_claim_ratio_below_target"]
    assert surface["chapter_state"]["ch_01"] == "failed"
    assert surface["quality"]["publish_decision"] == "internal_only"
    assert surface["sidecar_refs"] == ["validation/quality-score.json"]
