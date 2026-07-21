"""Parent/child status projection for the YouTube report epic."""

from __future__ import annotations

from typing import Any


def project_epic_status(children: list[dict[str, Any]]) -> dict[str, Any]:
    passed_statuses = {"passed", "completed", "eval_passed"}
    blocked = [c for c in children if c.get("blocked_reason")]
    passed = [c for c in children if c.get("status") in passed_statuses]
    closable = len(passed) == len(children) and not blocked
    return {
        "schema_version": "youtube_report_epic_projection.v1",
        "child_count": len(children),
        "passed_count": len(passed),
        "blocked": [{"id": c.get("id"), "reason": c.get("blocked_reason")} for c in blocked],
        "closable": closable,
    }
