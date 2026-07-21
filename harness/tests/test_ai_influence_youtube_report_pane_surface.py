import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.pane_surface import build_pane_surface  # noqa: E402


def test_pane_surface_shows_phase_blocker_and_artifacts() -> None:
    surface = build_pane_surface({"state": "planned", "blocked_reason": "none", "artifacts": [{"type": "plan"}]})

    assert surface["active_phase"] == "planned"
    assert surface["artifact_summary"][0]["type"] == "plan"
