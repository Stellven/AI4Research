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


def test_status_surface_blocks_internal_field_leak() -> None:
    with pytest.raises(ValueError, match="video_id"):
        build_status_surface({"artifacts": [{"video_id": "abc"}]})
