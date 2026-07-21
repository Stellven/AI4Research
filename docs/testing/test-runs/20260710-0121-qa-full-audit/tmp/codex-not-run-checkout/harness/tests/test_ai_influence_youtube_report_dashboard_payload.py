import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.status_surface import build_status_surface  # noqa: E402


def test_dashboard_payload_covers_blocked_passed_partial() -> None:
    for state in ["blocked", "validated", "chaptered"]:
        payload = build_status_surface({"run_id": "r", "state": state, "blocked_reason": "x" if state == "blocked" else ""})
        assert payload["state"] == state
        assert "artifacts" in payload
