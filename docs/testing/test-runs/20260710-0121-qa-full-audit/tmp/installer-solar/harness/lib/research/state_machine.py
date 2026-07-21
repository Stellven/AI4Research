"""DeepResearch Data Plane state machine.

Implements S02-STATEMACHINE §4 — tracks the lifecycle of a single
DeepResearch execution run.  Every transition appends one line to
``model_usage.jsonl`` so the full history is recoverable via
``replay_from_jsonl()``.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DataPlaneState(Enum):
    INIT = "init"
    SEARCHING = "searching"
    SEARCH_SKIP = "search_skip"
    DRAFTING = "drafting"
    METERING = "metering"
    RENDERING = "rendering"
    FINALIZED = "finalized"
    FAILED = "failed"


_VALID_TRANSITIONS: dict[DataPlaneState, set[DataPlaneState]] = {
    DataPlaneState.INIT: {DataPlaneState.SEARCHING, DataPlaneState.SEARCH_SKIP},
    DataPlaneState.SEARCHING: {DataPlaneState.DRAFTING, DataPlaneState.SEARCH_SKIP, DataPlaneState.FAILED},
    DataPlaneState.SEARCH_SKIP: {DataPlaneState.RENDERING, DataPlaneState.FAILED},
    DataPlaneState.DRAFTING: {DataPlaneState.METERING, DataPlaneState.FAILED},
    DataPlaneState.METERING: {DataPlaneState.RENDERING, DataPlaneState.FAILED},
    DataPlaneState.RENDERING: {DataPlaneState.FINALIZED, DataPlaneState.FAILED},
    DataPlaneState.FINALIZED: set(),
    DataPlaneState.FAILED: set(),
}


@dataclass
class StateTransitionEvent:
    ts: str
    from_state: str
    to_state: str
    stage: str = ""
    fallback_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class InvalidTransition(RuntimeError):
    """Raised when a state transition is not in the allowed set."""


class ResearchStateMachine:
    """Finite state machine for a single DeepResearch run.

    Each call to :meth:`transition` appends a JSONL record to
    ``model_usage.jsonl`` (via the provided *jsonl_path*) so that
    the machine can be rebuilt from the log.
    """

    def __init__(
        self,
        jsonl_path: str | Path | None = None,
        *,
        initial_state: DataPlaneState = DataPlaneState.INIT,
    ) -> None:
        self._state = initial_state
        self._history: list[StateTransitionEvent] = []
        self._jsonl_path = Path(jsonl_path) if jsonl_path else None

    @property
    def state(self) -> DataPlaneState:
        return self._state

    def transition(
        self,
        to: DataPlaneState,
        *,
        stage: str = "",
        fallback_reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> StateTransitionEvent:
        """Transition to *to* and append a record to the JSONL log.

        Raises :class:`InvalidTransition` if the move is not allowed.
        """
        allowed = _VALID_TRANSITIONS.get(self._state, set())
        if to not in allowed:
            raise InvalidTransition(
                f"invalid transition: {self._state.value} -> {to.value}"
            )
        event = StateTransitionEvent(
            ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            from_state=self._state.value,
            to_state=to.value,
            stage=stage,
            fallback_reason=fallback_reason,
            extra=extra or {},
        )
        self._history.append(event)
        self._state = to
        self._append_to_jsonl(event)
        return event

    def history(self) -> list[StateTransitionEvent]:
        """Return a copy of the transition history."""
        return list(self._history)

    @classmethod
    def replay_from_jsonl(cls, path: str | Path) -> ResearchStateMachine:
        """Rebuild state machine by replaying a JSONL log."""
        machine = cls()
        target = Path(path)
        if not target.exists():
            return machine
        with target.open("r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if not stripped:
                    continue
                record = json.loads(stripped)
                to_state = DataPlaneState(record["to_state"])
                event = StateTransitionEvent(
                    ts=record.get("ts", ""),
                    from_state=record.get("from_state", ""),
                    to_state=to_state.value,
                    stage=record.get("stage", ""),
                    fallback_reason=record.get("fallback_reason"),
                    extra=record.get("extra", {}),
                )
                machine._history.append(event)
                machine._state = to_state
        return machine

    def _append_to_jsonl(self, event: StateTransitionEvent) -> None:
        if self._jsonl_path is None:
            return
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(event), ensure_ascii=False, sort_keys=True)
        with self._jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
