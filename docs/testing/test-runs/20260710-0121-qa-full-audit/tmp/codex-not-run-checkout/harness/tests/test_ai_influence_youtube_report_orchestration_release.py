import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.orchestration import activate_child_if_ready  # noqa: E402
from ai_influence_youtube_report.status_surface import build_status_surface  # noqa: E402


def test_orchestration_release_minimal_regression() -> None:
    child = activate_child_if_ready({"id": "s05", "requires": ["s04"], "phase": "prd_ready"}, {"s04": "passed"})
    surface = build_status_surface({"run_id": "r", "state": "created"})

    assert child["status"] == "active"
    assert child["route_role"] == "planner"
    assert surface["schema_version"] == "youtube_report_status_surface.v1"
