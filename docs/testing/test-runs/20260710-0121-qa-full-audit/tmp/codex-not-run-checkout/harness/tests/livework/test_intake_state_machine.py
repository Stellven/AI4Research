"""Tests for intake_state_machine.py FSM.

Covers: happy path, rejected paths, illegal transition rejection.
No mocks — all tests use real FSM instances and pure functions.
"""

from __future__ import annotations

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from harness.lib.livework.intake_state_machine import (
    IntakeFSM,
    IntakeResult,
    IntakeState,
    IntakeTrigger,
    intake_requirement,
)


# ── Happy path tests ──────────────────────────────────────────

class TestHappyPath:
    def test_full_happy_path(self):
        result = intake_requirement(
            "Fix the status page to show idle state when no sprint is active "
            "and all panes are idle — must display No Active Work",
            sprint_id="sprint-happy-001",
        )
        assert result.state == "dispatched"
        assert result.rejected is False
        assert result.sprint_id == "sprint-happy-001"

    def test_fsm_walks_all_states(self):
        fsm = IntakeFSM()
        assert fsm.state == IntakeState.RECEIVED
        fsm.transition(IntakeTrigger.SUBMIT)
        assert fsm.state == IntakeState.VALIDATING
        fsm.transition(IntakeTrigger.VALIDATE_PASS)
        assert fsm.state == IntakeState.PM_DRAFTING
        fsm.transition(IntakeTrigger.PM_COMPLETE)
        assert fsm.state == IntakeState.PLANNER_PENDING
        fsm.transition(IntakeTrigger.PLANNER_ACCEPT)
        assert fsm.state == IntakeState.DISPATCHED
        assert fsm.is_terminal()

    def test_history_records_all_transitions(self):
        fsm = IntakeFSM()
        fsm.transition(IntakeTrigger.SUBMIT)
        fsm.transition(IntakeTrigger.VALIDATE_PASS)
        fsm.transition(IntakeTrigger.PM_COMPLETE)
        fsm.transition(IntakeTrigger.PLANNER_ACCEPT)
        assert len(fsm.history) == 4
        assert fsm.history[0][2] == IntakeState.VALIDATING
        assert fsm.history[-1][2] == IntakeState.DISPATCHED


# ── Rejected path tests ───────────────────────────────────────

class TestRejectedPaths:
    def test_rejected_empty_text(self):
        result = intake_requirement("")
        assert result.rejected is True
        assert result.state == "rejected"
        assert "empty" in result.rejection_reason.lower()

    def test_rejected_too_short(self):
        result = intake_requirement("fix bug")
        assert result.rejected is True
        assert result.state == "rejected"
        assert "too short" in result.rejection_reason.lower()

    def test_rejected_no_goal(self):
        result = intake_requirement(
            "x" * 60  # long enough but no goal/acceptance keywords
        )
        assert result.rejected is True
        assert result.state == "rejected"
        assert "goal" in result.rejection_reason.lower()

    def test_rejected_planner_reject(self):
        result = intake_requirement(
            "Implement the feature that must display all sprint phases "
            "on the status page with next step information",
            planner_reject=True,
        )
        assert result.rejected is True
        assert result.state == "rejected"
        assert "planner" in result.rejection_reason.lower()

    def test_rejected_via_pm_fail(self):
        fsm = IntakeFSM()
        fsm.transition(IntakeTrigger.SUBMIT)
        fsm.transition(IntakeTrigger.VALIDATE_PASS)
        fsm.transition(IntakeTrigger.PM_FAIL)
        assert fsm.state == IntakeState.REJECTED
        assert fsm.is_terminal()

    def test_rejected_via_dispatch_fail(self):
        fsm = IntakeFSM()
        fsm.transition(IntakeTrigger.SUBMIT)
        fsm.transition(IntakeTrigger.VALIDATE_PASS)
        fsm.transition(IntakeTrigger.PM_COMPLETE)
        fsm.transition(IntakeTrigger.PLANNER_ACCEPT)
        fsm.transition(IntakeTrigger.DISPATCH_FAIL)
        assert fsm.state == IntakeState.REJECTED


# ── Illegal transition tests ──────────────────────────────────

class TestIllegalTransitions:
    def test_cannot_jump_from_received_to_dispatched(self):
        fsm = IntakeFSM()
        with pytest.raises(ValueError, match="Illegal transition"):
            fsm.transition(IntakeTrigger.PLANNER_ACCEPT)

    def test_cannot_transition_from_rejected(self):
        fsm = IntakeFSM()
        fsm.transition(IntakeTrigger.SUBMIT)
        fsm.transition(IntakeTrigger.VALIDATE_FAIL)
        assert fsm.state == IntakeState.REJECTED
        with pytest.raises(ValueError, match="Illegal transition"):
            fsm.transition(IntakeTrigger.SUBMIT)

    def test_cannot_validate_pass_after_dispatched(self):
        fsm = IntakeFSM()
        fsm.transition(IntakeTrigger.SUBMIT)
        fsm.transition(IntakeTrigger.VALIDATE_PASS)
        fsm.transition(IntakeTrigger.PM_COMPLETE)
        fsm.transition(IntakeTrigger.PLANNER_ACCEPT)
        with pytest.raises(ValueError, match="Illegal transition"):
            fsm.transition(IntakeTrigger.VALIDATE_PASS)

    def test_cannot_double_submit(self):
        fsm = IntakeFSM()
        fsm.transition(IntakeTrigger.SUBMIT)
        with pytest.raises(ValueError, match="Illegal transition"):
            fsm.transition(IntakeTrigger.SUBMIT)


# ── IntakeResult structure tests ──────────────────────────────

class TestIntakeResult:
    def test_result_is_dataclass(self):
        result = intake_requirement(
            "Add a new endpoint that must return the idle state",
            sprint_id="sprint-struct-001",
        )
        assert hasattr(result, "sprint_id")
        assert hasattr(result, "state")
        assert hasattr(result, "rejected")
        assert hasattr(result, "rejection_reason")
        assert hasattr(result, "validation_errors")

    def test_rejected_result_has_validation_errors(self):
        result = intake_requirement("short")
        assert len(result.validation_errors) > 0
