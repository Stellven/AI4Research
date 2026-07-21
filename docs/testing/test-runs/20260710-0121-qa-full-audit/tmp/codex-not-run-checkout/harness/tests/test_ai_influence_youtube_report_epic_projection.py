import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.epic_projection import project_epic_status  # noqa: E402


def test_parent_not_closable_when_child_blocked() -> None:
    projection = project_epic_status([
        {"id": "s03", "status": "passed"},
        {"id": "s04", "status": "queued", "blocked_reason": "waiting_for:s03"},
    ])

    assert projection["closable"] is False
    assert projection["blocked"][0]["id"] == "s04"


def test_completed_children_count_as_passed_for_epic_close() -> None:
    projection = project_epic_status([
        {"id": "s03", "status": "completed", "blocked_reason": ""},
        {"id": "s04", "status": "eval_passed", "blocked_reason": ""},
    ])

    assert projection["passed_count"] == 2
    assert projection["closable"] is True
