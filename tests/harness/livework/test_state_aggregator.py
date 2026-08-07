"""Tests for state_aggregator.py pure functions.

All tests use real dataclass instances and dict inputs — zero mocks.
Property test: same events → same result on repeated calls.
"""

from __future__ import annotations

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from harness.lib.livework.state_aggregator import (
    PaneState,
    RoleNextStep,
    aggregate_pane_state,
    resolve_role,
)


# ── Fixtures ──────────────────────────────────────────────────

HEARTBEAT_IDLE = {
    "event_type": "autopilot_heartbeat",
    "timestamp": "2026-05-14T15:00:00Z",
    "payload": {
        "idle": True,
        "active_dispatches": 0,
        "queue_depth": 0,
        "pane_states": {
            "solar-harness-lab:0.3": {
                "lease_active": False,
                "last_activity": "2026-05-14T14:00:00Z",
            },
            "solar-harness-lab:0.4": {
                "lease_active": False,
                "last_activity": "2026-05-14T13:00:00Z",
            },
        },
    },
}

HEARTBEAT_ACTIVE = {
    "event_type": "autopilot_heartbeat",
    "timestamp": "2026-05-14T15:05:00Z",
    "payload": {
        "idle": False,
        "active_dispatches": 1,
        "queue_depth": 2,
        "pane_states": {
            "solar-harness-lab:0.3": {
                "lease_active": True,
                "last_activity": "2026-05-14T15:04:00Z",
            },
            "solar-harness-lab:0.4": {
                "lease_active": False,
                "last_activity": "2026-05-14T14:30:00Z",
            },
        },
    },
}

ROLE_TRANSITION_DRAFTING = {
    "event_type": "role_transition",
    "sprint_id": "sprint-test-001",
    "timestamp": "2026-05-14T15:00:00Z",
    "payload": {
        "sprint_id": "sprint-test-001",
        "from_phase": "pm_analysis",
        "to_phase": "drafting",
        "actor": "planner",
    },
}

ROLE_TRANSITION_BUILDING = {
    "event_type": "role_transition",
    "sprint_id": "sprint-test-001",
    "timestamp": "2026-05-14T15:10:00Z",
    "payload": {
        "sprint_id": "sprint-test-001",
        "from_phase": "drafting",
        "to_phase": "building",
        "actor": "coordinator",
    },
}

TASK_GRAPH_EVENT = {
    "event_type": "task_graph_generated",
    "sprint_id": "sprint-test-001",
    "timestamp": "2026-05-14T15:05:00Z",
    "payload": {
        "sprint_id": "sprint-test-001",
        "nodes": [
            {"id": "N1", "status": "passed", "goal": "Write schemas"},
            {"id": "N2", "status": "in_progress", "goal": "Write aggregator"},
            {"id": "N3", "status": "pending", "goal": "Write tests", "depends_on": ["N1", "N2"]},
        ],
    },
}

PM_DRAFTED_EVENT = {
    "event_type": "pm_drafted",
    "sprint_id": "sprint-test-001",
    "timestamp": "2026-05-14T14:55:00Z",
    "payload": {
        "sprint_id": "sprint-test-001",
        "phase": "pm_analysis",
        "prd_ready": True,
        "next_step": "planner_review",
    },
}

IRRELEVANT_EVENT = {
    "event_type": "something_else",
    "timestamp": "2026-05-14T14:00:00Z",
    "payload": {},
}


# ── aggregate_pane_state tests ────────────────────────────────

class TestAggregatePaneStateIdle:
    def test_empty_events_returns_idle(self):
        result = aggregate_pane_state([])
        assert result.is_idle is True
        assert result.active_panes == []
        assert result.queue_depth == 0

    def test_idle_heartbeat_no_active_panes(self):
        result = aggregate_pane_state([HEARTBEAT_IDLE])
        assert result.is_idle is True
        assert result.active_panes == []
        assert result.queue_depth == 0
        assert result.last_heartbeat_ts == "2026-05-14T15:00:00Z"

    def test_idle_heartbeat_pane_details_populated(self):
        result = aggregate_pane_state([HEARTBEAT_IDLE])
        assert len(result.pane_details) == 2
        assert "solar-harness-lab:0.3" in result.pane_details
        assert result.pane_details["solar-harness-lab:0.3"].lease_active is False


class TestAggregatePaneStateActive:
    def test_active_heartbeat_not_idle(self):
        result = aggregate_pane_state([HEARTBEAT_ACTIVE])
        assert result.is_idle is False
        assert "solar-harness-lab:0.3" in result.active_panes
        assert result.queue_depth == 2

    def test_multiple_heartbeats_uses_latest(self):
        result = aggregate_pane_state([HEARTBEAT_IDLE, HEARTBEAT_ACTIVE])
        assert result.is_idle is False
        assert result.last_heartbeat_ts == "2026-05-14T15:05:00Z"


class TestAggregatePaneStateMixed:
    def test_irrelevant_events_ignored(self):
        result = aggregate_pane_state([IRRELEVANT_EVENT, HEARTBEAT_IDLE])
        assert result.is_idle is True
        assert result.last_heartbeat_ts == "2026-05-14T15:00:00Z"


# ── resolve_role tests ────────────────────────────────────────

class TestResolveRole:
    def test_empty_events_returns_unknown_phase(self):
        result = resolve_role([], "sprint-test-001")
        assert result.phase == "unknown"
        assert result.sprint_id == "sprint-test-001"

    def test_no_matching_sprint_returns_unknown(self):
        result = resolve_role([ROLE_TRANSITION_DRAFTING], "nonexistent-sprint")
        assert result.phase == "unknown"

    def test_latest_transition_determines_phase(self):
        events = [ROLE_TRANSITION_DRAFTING, ROLE_TRANSITION_BUILDING]
        result = resolve_role(events, "sprint-test-001")
        assert result.phase == "building"

    def test_pm_drafted_sets_pm_analysis_phase(self):
        result = resolve_role([PM_DRAFTED_EVENT], "sprint-test-001")
        assert result.phase == "pm_analysis"

    def test_nodes_from_task_graph(self):
        events = [TASK_GRAPH_EVENT]
        result = resolve_role(events, "sprint-test-001")
        assert len(result.nodes) == 3
        assert result.nodes[0].id == "N1"
        assert result.nodes[0].status == "passed"
        assert result.nodes[2].depends_on == ["N1", "N2"]

    def test_next_action_builder_working(self):
        events = [ROLE_TRANSITION_BUILDING, TASK_GRAPH_EVENT]
        result = resolve_role(events, "sprint-test-001")
        assert "N2" in result.next_action

    def test_next_action_all_passed(self):
        graph = {
            "event_type": "task_graph_generated",
            "sprint_id": "sprint-test-001",
            "timestamp": "2026-05-14T16:00:00Z",
            "payload": {
                "sprint_id": "sprint-test-001",
                "nodes": [
                    {"id": "N1", "status": "passed", "goal": "Done"},
                ],
            },
        }
        events = [ROLE_TRANSITION_BUILDING, graph]
        result = resolve_role(events, "sprint-test-001")
        assert "complete" in result.next_action.lower()


# ── Property test: determinism ────────────────────────────────

class TestDeterminism:
    def test_aggregate_pane_state_idempotent(self):
        events = [HEARTBEAT_IDLE, HEARTBEAT_ACTIVE, IRRELEVANT_EVENT]
        r1 = aggregate_pane_state(events)
        r2 = aggregate_pane_state(events)
        assert r1 == r2

    def test_resolve_role_idempotent(self):
        events = [
            PM_DRAFTED_EVENT,
            ROLE_TRANSITION_DRAFTING,
            ROLE_TRANSITION_BUILDING,
            TASK_GRAPH_EVENT,
        ]
        r1 = resolve_role(events, "sprint-test-001")
        r2 = resolve_role(events, "sprint-test-001")
        assert r1 == r2

    def test_aggregate_pane_state_deterministic_order(self):
        """Property: same events in same order always produce same result."""
        events = [HEARTBEAT_IDLE, HEARTBEAT_ACTIVE]
        results = [aggregate_pane_state(events) for _ in range(10)]
        first = results[0]
        for r in results[1:]:
            assert r == first

    def test_resolve_role_deterministic_order(self):
        """Property: same events in same order always produce same result."""
        events = [TASK_GRAPH_EVENT, ROLE_TRANSITION_BUILDING]
        results = [resolve_role(events, "sprint-test-001") for _ in range(10)]
        first = results[0]
        for r in results[1:]:
            assert r == first
