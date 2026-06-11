import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.pane_surface import build_pane_surface  # noqa: E402


def test_pane_surface_shows_phase_blocker_and_artifacts() -> None:
    surface = build_pane_surface({"state": "planned", "blocked_reason": "none", "artifacts": [{"type": "plan"}]})

    assert surface["active_phase"] == "planned"
    assert surface["artifact_summary"][0]["type"] == "plan"


def test_pane_surface_shows_validation_sidecars() -> None:
    surface = build_pane_surface({
        "state": "blocked",
        "blocked_reasons": ["quality_gate:C:internal_only"],
        "chapter_state": {"ch_01": "passed"},
        "quality": {"grade": "C", "publish_decision": "internal_only"},
        "repair_summaries": [{"chapter_ref": "ch_01", "attempt": 1}],
        "sidecar_refs": ["validation/pane-surface.json"],
    })

    assert surface["blocked_reasons"] == ["quality_gate:C:internal_only"]
    assert surface["chapter_state"] == {"ch_01": "passed"}
    assert surface["quality"]["grade"] == "C"
    assert surface["sidecar_refs"] == ["validation/pane-surface.json"]
