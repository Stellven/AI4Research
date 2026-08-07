"""Integration replay test: exercises full livework pipeline with real events.jsonl.

Replays a realistic event sequence through all livework modules:
  schemas → events (write) → idle_detector → state_aggregator → intake_state_machine
Uses tmp_path for real file I/O. Zero mocks.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

_BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(_BASE / "harness" / "lib"))

from harness.lib.livework.events import (
    emit_heartbeat,
    emit_deadlock_detected,
    emit_requirement_intake,
    emit_pm_drafted,
    emit_role_transition,
)
from harness.lib.livework.idle_detector import is_idle, detect_deadlock
from harness.lib.livework.intake_state_machine import (
    IntakeFSM,
    IntakeState,
    IntakeTrigger,
    intake_requirement,
)
from harness.lib.livework.state_aggregator import (
    aggregate_pane_state,
    resolve_role,
)


SPRINT_ID = "sprint-integration-test-001"
PANE_ID = "solar-harness-lab:0.3"


@pytest.fixture
def events_file(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


def _read_events(path: Path) -> list[dict]:
    events = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


class TestFullReplay:
    """Replay a complete sprint lifecycle through all modules."""

    def test_replay_idle_to_active_to_idle(self, events_file: Path):
        # Phase 1: Idle harness — emit heartbeat with all panes idle
        emit_heartbeat(
            events_file,
            idle=True,
            active_dispatches=0,
            queue_depth=0,
            pane_states={},
            seq=1,
        )

        # Phase 2: Requirement submitted
        emit_requirement_intake(
            events_file,
            requirement_id="req-001",
            raw_requirement="Fix the status page to show idle state when no sprint is active",
            sprint_id=SPRINT_ID,
            status="pm_analysis",
            seq=2,
        )

        # Phase 3: PM drafts
        emit_pm_drafted(
            events_file,
            sprint_id=SPRINT_ID,
            phase="pm_analysis",
            prd_ready=True,
            outcome_count=5,
            seq=3,
        )

        # Phase 4: Role transition to drafting
        emit_role_transition(
            events_file,
            sprint_id=SPRINT_ID,
            from_phase="pm_analysis",
            to_phase="drafting",
            actor="planner",
            seq=4,
        )

        # Phase 5: Role transition to building
        emit_role_transition(
            events_file,
            sprint_id=SPRINT_ID,
            from_phase="drafting",
            to_phase="building",
            actor="coordinator",
            seq=5,
        )

        # Phase 6: Active heartbeat (builder working)
        emit_heartbeat(
            events_file,
            idle=False,
            active_dispatches=1,
            queue_depth=0,
            pane_states={PANE_ID: {"lease_active": True, "last_activity": "2026-05-14T15:10:00Z"}},
            seq=6,
        )

        # Phase 7: Sprint complete, back to idle
        emit_role_transition(
            events_file,
            sprint_id=SPRINT_ID,
            from_phase="building",
            to_phase="completed",
            actor="evaluator",
            seq=7,
        )

        emit_heartbeat(
            events_file,
            idle=True,
            active_dispatches=0,
            queue_depth=0,
            pane_states={PANE_ID: {"lease_active": False, "last_activity": "2026-05-14T15:30:00Z"}},
            seq=8,
        )

        events = _read_events(events_file)

        # Assertion 1: 8 events written
        assert len(events) == 8

        # Assertion 2: Event types are correct
        types = [e["event_type"] for e in events]
        assert "autopilot_heartbeat" in types
        assert "requirement_intake" in types
        assert "pm_drafted" in types
        assert "role_transition" in types

        # Assertion 3: aggregate_pane_state returns idle at end
        pane_state = aggregate_pane_state(events)
        assert pane_state.is_idle is True

        # Assertion 4: resolve_role shows completed phase
        role = resolve_role(events, SPRINT_ID)
        assert role.phase == "completed"

        # Assertion 5: intake_requirement accepts the requirement
        result = intake_requirement(
            "Fix the status page to show idle state when no sprint is active "
            "and all panes are idle — must display No Active Work",
            sprint_id=SPRINT_ID,
        )
        assert result.rejected is False

        # Assertion 6: is_idle on final heartbeat event
        idle = is_idle(pane_state.pane_details, "2026-05-14T15:30:00Z")
        assert idle is True

        # Assertion 7: Events have valid schema_version
        for e in events:
            assert "schema_version" in e
            assert e["schema_version"] == "1.0.0"

        # Assertion 8: Role transition sequence is ordered
        transitions = [e for e in events if e["event_type"] == "role_transition"]
        phases = [t["payload"]["to_phase"] for t in transitions]
        assert phases == ["drafting", "building", "completed"]

    def test_replay_with_deadlock(self, events_file: Path):
        """Replay a scenario where a pane deadlocks."""
        emit_heartbeat(
            events_file,
            idle=False,
            active_dispatches=1,
            queue_depth=0,
            pane_states={PANE_ID: {"lease_active": True}},
            seq=1,
        )

        emit_deadlock_detected(
            events_file,
            pane_id=PANE_ID,
            dispatch_id="graph-xxx-N1",
            sprint_id=SPRINT_ID,
            node_id="N1",
            dispatch_sent_at="2026-05-14T15:00:00Z",
            elapsed_seconds=600,
            deadline_seconds=600,
            seq=2,
        )

        events = _read_events(events_file)

        # Assertion 9: Deadlock event present
        deadlock_events = [e for e in events if e["event_type"] == "pane_deadlock"]
        assert len(deadlock_events) == 1

        # Assertion 10: Deadlock has correct pane_id
        assert deadlock_events[0]["payload"]["pane_id"] == PANE_ID

        # Assertion 11: aggregate_pane_state shows not idle (deadlock pane active)
        pane_state = aggregate_pane_state(events)
        assert pane_state.is_idle is False

    def test_replay_intake_rejection(self):
        """Replay a rejected requirement through intake FSM."""
        result = intake_requirement("fix bug", sprint_id="sprint-rejected-001")
        assert result.rejected is True
        assert result.state == "rejected"

        # Assertion 12: FSM history is empty for intake_requirement (single function call)
        # But direct FSM can be tested:
        fsm = IntakeFSM()
        fsm.transition(IntakeTrigger.SUBMIT)
        fsm.transition(IntakeTrigger.VALIDATE_FAIL)
        assert fsm.state == IntakeState.REJECTED
        assert len(fsm.history) == 2
