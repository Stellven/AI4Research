"""Orchestration helpers for AI Influence YouTube report child sprints."""

from __future__ import annotations

from typing import Any


ROUTE_BY_PHASE = {
    "drafting": "planner",
    "prd_ready": "planner",
    "planning_complete": "builder_main",
    "reviewing": "evaluator",
    "completed": "done",
}


def normalize_route_role(phase: str) -> str:
    return ROUTE_BY_PHASE.get(str(phase or ""), "planner")


def activate_child_if_ready(child: dict[str, Any], upstream: dict[str, str]) -> dict[str, Any]:
    required = child.get("requires", [])
    missing = [sid for sid in required if upstream.get(sid) != "passed"]
    if missing:
        return {
            **child,
            "status": "queued",
            "blocked_by": missing,
            "blocked_reason": f"waiting_for:{','.join(missing)}",
            "route_role": "planner",
        }
    phase = str(child.get("phase") or "prd_ready")
    return {
        **child,
        "status": "active",
        "route_role": normalize_route_role(phase),
        "blocked_by": [],
        "blocked_reason": "",
    }
