"""
Operator State Machine — state definitions, transition rules, event log, state rebuild.

Part of Solar Harness AI Influence operator consolidation (S03 N3).
Depends on: operator_registry_loader (N1).

States: pending, running, success, partial, failed
Legal transitions:
  pending  -> running
  running  -> success | partial | failed
All other transitions are illegal and raise IllegalTransitionError.
"""

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any


class OperatorState(str, Enum):
    """Valid operator execution states."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


# Transition table: from_state -> set of legal target states
_TRANSITIONS: dict[OperatorState, set[OperatorState]] = {
    OperatorState.PENDING: {OperatorState.RUNNING},
    OperatorState.RUNNING: {OperatorState.SUCCESS, OperatorState.PARTIAL, OperatorState.FAILED},
    OperatorState.SUCCESS: set(),
    OperatorState.PARTIAL: set(),
    OperatorState.FAILED: set(),
}


class IllegalTransitionError(Exception):
    """Raised when a state transition violates the transition table."""


class EventLogError(Exception):
    """Raised when event log operations fail."""


def _make_event(
    run_id: str,
    line: str,
    from_state: OperatorState | None,
    to_state: OperatorState,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an event dict for the log."""
    event: dict[str, Any] = {
        "ts": time.time(),
        "run_id": run_id,
        "line": line,
        "from_state": from_state.value if from_state else None,
        "to_state": to_state.value,
    }
    if metadata:
        event["metadata"] = metadata
    return event


class OperatorRun:
    """
    Tracks the state of a single operator run through legal transitions.

    Usage:
        run = OperatorRun(run_id="abc", line="github_trends")
        assert run.state == OperatorState.PENDING
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.SUCCESS)
    """

    def __init__(self, run_id: str, line: str) -> None:
        self.run_id = run_id
        self.line = line
        self._state = OperatorState.PENDING
        self._events: list[dict[str, Any]] = [
            _make_event(run_id, line, None, OperatorState.PENDING)
        ]

    @property
    def state(self) -> OperatorState:
        return self._state

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def transition(
        self,
        to_state: OperatorState,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Transition to a new state.

        Args:
            to_state: Target state.
            metadata: Optional metadata to attach to the event.

        Raises:
            IllegalTransitionError: If the transition is not allowed.
        """
        allowed = _TRANSITIONS.get(self._state, set())
        if to_state not in allowed:
            raise IllegalTransitionError(
                f"Transition {self._state.value} -> {to_state.value} is not allowed. "
                f"Legal targets from {self._state.value}: "
                f"{sorted(s.value for s in allowed) if allowed else '(terminal state)'}"
            )

        event = _make_event(self.run_id, self.line, self._state, to_state, metadata)
        self._events.append(event)
        self._state = to_state


def append_event_log(
    log_path: str | Path,
    events: list[dict[str, Any]],
) -> None:
    """
    Append events to a JSON-lines event log file.

    Each event is written as a single JSON line.

    Args:
        log_path: Path to the event log file.
        events: List of event dicts to append.

    Raises:
        EventLogError: If file write fails.
    """
    path = Path(log_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as e:
        raise EventLogError(f"Failed to append to event log {path}: {e}") from e


def read_event_log(log_path: str | Path) -> list[dict[str, Any]]:
    """
    Read all events from a JSON-lines event log file.

    Args:
        log_path: Path to the event log file.

    Returns:
        List of event dicts.

    Raises:
        EventLogError: If file read or JSON parse fails.
    """
    path = Path(log_path)
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for lineno, raw_line in enumerate(f, 1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    events.append(json.loads(stripped))
                except json.JSONDecodeError as e:
                    raise EventLogError(
                        f"Invalid JSON on line {lineno} of {path}: {e}"
                    ) from e
    except OSError as e:
        raise EventLogError(f"Failed to read event log {path}: {e}") from e

    return events


def rebuild_state(
    events: list[dict[str, Any]],
    run_id: str | None = None,
) -> dict[str, OperatorRun]:
    """
    Rebuild OperatorRun objects from a sequence of events.

    Args:
        events: List of event dicts (as read from event log).
        run_id: If provided, only rebuild this specific run.

    Returns:
        Dict mapping run_id -> OperatorRun with replayed state.

    Raises:
        IllegalTransitionError: If events contain an illegal transition.
        KeyError: If an event is missing required fields.
    """
    runs: dict[str, OperatorRun] = {}

    for event in events:
        eid = event["run_id"]
        if run_id is not None and eid != run_id:
            continue

        to_state = OperatorState(event["to_state"])

        if eid not in runs:
            # First event for this run — should be the initial pending event
            run = OperatorRun.__new__(OperatorRun)
            run.run_id = eid
            run.line = event["line"]
            run._state = to_state
            run._events = [event]
            runs[eid] = run
        else:
            run = runs[eid]
            # Validate transition
            allowed = _TRANSITIONS.get(run._state, set())
            if to_state not in allowed:
                raise IllegalTransitionError(
                    f"Replay error for run {eid}: "
                    f"{run._state.value} -> {to_state.value} is illegal"
                )
            run._state = to_state
            run._events.append(event)

    return runs
