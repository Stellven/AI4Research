"""Outcome-level orchestration state machine (GeminiDRController owns this).

INPUT -> OPTIMIZE -> SUBMIT -> CONFIRM -> MONITOR -> {DONE | RETRY | FAIL}
RETRY loops back to SUBMIT (re-attempt). Browser async states (running/
waiting_human/...) are owned by the operator and surfaced via DRRunHandle;
this machine layers outcome states on top (A1 state ownership split).
"""

from __future__ import annotations

from enum import Enum


class ControllerState(str, Enum):
    INPUT = "input"        # O1: ResearchRequest accepted
    OPTIMIZE = "optimize"  # O2: producing OptimizedPrompt
    SUBMIT = "submit"      # O3: submitted to DR, planning
    CONFIRM = "confirm"    # O4: plan confirmed, planning->running
    MONITOR = "monitor"    # O5: polling running job
    DONE = "done"          # O5/O6 success terminal
    RETRY = "retry"        # transient failure -> will re-submit
    FAIL = "fail"          # fatal / exhausted terminal


class InvalidTransition(RuntimeError):
    pass


# Allowed transitions. RETRY is a transient hub that re-enters SUBMIT.
_TRANSITIONS: dict[ControllerState, set[ControllerState]] = {
    ControllerState.INPUT: {ControllerState.OPTIMIZE, ControllerState.FAIL},
    ControllerState.OPTIMIZE: {ControllerState.SUBMIT, ControllerState.FAIL},
    ControllerState.SUBMIT: {ControllerState.CONFIRM, ControllerState.RETRY, ControllerState.FAIL},
    ControllerState.CONFIRM: {ControllerState.MONITOR, ControllerState.RETRY, ControllerState.FAIL},
    ControllerState.MONITOR: {
        ControllerState.DONE,
        ControllerState.RETRY,
        ControllerState.FAIL,
        ControllerState.MONITOR,  # repeated poll
    },
    ControllerState.RETRY: {ControllerState.SUBMIT, ControllerState.FAIL},
    ControllerState.DONE: set(),
    ControllerState.FAIL: set(),
}

TERMINAL_STATES = {ControllerState.DONE, ControllerState.FAIL}


def can_transition(src: ControllerState, dst: ControllerState) -> bool:
    return dst in _TRANSITIONS.get(src, set())


def assert_transition(src: ControllerState, dst: ControllerState) -> None:
    if not can_transition(src, dst):
        raise InvalidTransition(f"illegal transition {src.value} -> {dst.value}")


def all_states() -> set[ControllerState]:
    return set(ControllerState)
