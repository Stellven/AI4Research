"""StateMachine — pipeline lifecycle FSM + event-sourced rebuild seam.

Per contract: "state changes rebuildable from metadata or events".
Each state transition emits an event that can be replayed to reconstruct
the current state of any paper entity.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PaperLifecycle(str, Enum):
    collected = "collected"
    canonicalized = "canonicalized"
    enriching = "enriching"
    enriched = "enriched"
    classifying = "classifying"
    classified = "classified"
    scoring = "scoring"
    scored = "scored"
    packet_built = "packet_built"
    resonating = "resonating"
    resonated = "resonated"
    reasoning = "reasoning"
    compiled = "compiled"
    stored = "stored"


LEGAL_TRANSITIONS: dict[PaperLifecycle, set[PaperLifecycle]] = {
    PaperLifecycle.collected: {PaperLifecycle.canonicalized},
    PaperLifecycle.canonicalized: {PaperLifecycle.enriching},
    PaperLifecycle.enriching: {PaperLifecycle.enriched},
    PaperLifecycle.enriched: {PaperLifecycle.classifying},
    PaperLifecycle.classifying: {PaperLifecycle.classified},
    PaperLifecycle.classified: {PaperLifecycle.scoring},
    PaperLifecycle.scoring: {PaperLifecycle.scored},
    PaperLifecycle.scored: {PaperLifecycle.packet_built},
    PaperLifecycle.packet_built: {PaperLifecycle.resonating},
    PaperLifecycle.resonating: {PaperLifecycle.resonated},
    PaperLifecycle.resonated: {PaperLifecycle.reasoning},
    PaperLifecycle.reasoning: {PaperLifecycle.compiled},
    PaperLifecycle.compiled: {PaperLifecycle.stored},
}


class IllegalTransitionError(ValueError):
    def __init__(self, paper_id: str, from_state: str, to_state: str) -> None:
        self.paper_id = paper_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal transition for {paper_id}: {from_state} -> {to_state}"
        )


@dataclass
class TransitionEvent:
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    paper_id: str = ""
    from_state: str = ""
    to_state: str = ""
    trigger: str = ""
    metadata_json: str = "{}"
    occurred_at: str = ""

    def __post_init__(self) -> None:
        if not self.occurred_at:
            self.occurred_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )


@dataclass
class PaperStateRecord:
    paper_id: str
    current_state: PaperLifecycle
    transition_count: int = 0
    last_transition_at: str = ""
    last_trigger: str = ""
    event_log_json: str = "[]"


class PaperStateMachine:
    """FSM for paper pipeline lifecycle with event sourcing."""

    def __init__(self) -> None:
        self._states: dict[str, PaperStateRecord] = {}

    def initialize(self, paper_id: str) -> PaperStateRecord:
        record = PaperStateRecord(
            paper_id=paper_id,
            current_state=PaperLifecycle.collected,
            last_transition_at=datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            last_trigger="initialize",
        )
        self._states[paper_id] = record
        self._append_event(record, "", record.current_state.value, "initialize")
        return record

    def transition(
        self,
        paper_id: str,
        to_state: PaperLifecycle,
        *,
        trigger: str = "",
        metadata: Optional[dict] = None,
    ) -> PaperStateRecord:
        record = self._states.get(paper_id)
        if record is None:
            raise KeyError(f"Paper not initialized: {paper_id}")

        from_state = record.current_state
        if to_state not in LEGAL_TRANSITIONS.get(from_state, set()):
            raise IllegalTransitionError(paper_id, from_state.value, to_state.value)

        record.current_state = to_state
        record.transition_count += 1
        record.last_transition_at = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        record.last_trigger = trigger or "transition"

        meta_json = json.dumps(metadata) if metadata else "{}"
        self._append_event(record, from_state.value, to_state.value, trigger, meta_json)
        return record

    def get_state(self, paper_id: str) -> Optional[PaperStateRecord]:
        return self._states.get(paper_id)

    def rebuild_from_events(self, paper_id: str, events: list[dict]) -> PaperStateRecord:
        """Rebuild state by replaying transition events."""
        if not events:
            raise ValueError(f"No events to replay for {paper_id}")

        first = events[0]
        record = PaperStateRecord(
            paper_id=paper_id,
            current_state=PaperLifecycle(first["to_state"]),
            transition_count=1,
            last_transition_at=first.get("occurred_at", ""),
            last_trigger=first.get("trigger", "replay"),
        )
        record.event_log_json = json.dumps(events[:1])

        for evt in events[1:]:
            to_state = PaperLifecycle(evt["to_state"])
            record.current_state = to_state
            record.transition_count += 1
            record.last_transition_at = evt.get("occurred_at", "")
            record.last_trigger = evt.get("trigger", "replay")
            existing = json.loads(record.event_log_json)
            existing.append(evt)
            record.event_log_json = json.dumps(existing)

        self._states[paper_id] = record
        return record

    def _append_event(
        self,
        record: PaperStateRecord,
        from_state: str,
        to_state: str,
        trigger: str,
        metadata_json: str = "{}",
    ) -> None:
        event = TransitionEvent(
            paper_id=record.paper_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            metadata_json=metadata_json,
        )
        events = json.loads(record.event_log_json)
        events.append(asdict(event))
        record.event_log_json = json.dumps(events)
