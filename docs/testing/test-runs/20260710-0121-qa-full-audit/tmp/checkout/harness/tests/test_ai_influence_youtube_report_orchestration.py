import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.orchestration import activate_child_if_ready, normalize_route_role  # noqa: E402


def test_child_activates_only_after_upstream_passed() -> None:
    child = {"id": "s04", "requires": ["s03"], "phase": "planning_complete"}

    blocked = activate_child_if_ready(child, {"s03": "queued"})
    active = activate_child_if_ready(child, {"s03": "passed"})

    assert blocked["status"] == "queued"
    assert blocked["blocked_by"] == ["s03"]
    assert blocked["blocked_reason"] == "waiting_for:s03"
    assert blocked["route_role"] == "planner"
    assert active["status"] == "active"
    assert active["route_role"] == "builder_main"
    assert active["blocked_by"] == []


def test_route_role_normalization() -> None:
    assert normalize_route_role("drafting") == "planner"
    assert normalize_route_role("prd_ready") == "planner"
    assert normalize_route_role("planning_complete") == "builder_main"
    assert normalize_route_role("reviewing") == "evaluator"
