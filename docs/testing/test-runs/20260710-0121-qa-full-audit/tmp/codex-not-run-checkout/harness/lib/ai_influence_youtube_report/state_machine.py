"""RunRecord state transitions for AI Influence YouTube report runs."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .schema import RunRecord, RunState


SUCCESS_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.CREATED: {RunState.GRADED, RunState.RUN_REJECTED_UPSTREAM_UNREACHABLE},
    RunState.GRADED: {RunState.GROUPED, RunState.RUN_REJECTED_T3_ONLY, RunState.RUN_REJECTED_UPSTREAM_DRIFT},
    RunState.GROUPED: {RunState.PLANNED, RunState.RUN_REJECTED_HIERARCHY},
    RunState.PLANNED: {RunState.CHAPTERED, RunState.RUN_REJECTED_MODEL_UNREACHABLE},
    RunState.CHAPTERED: {RunState.SYNTHESIZED, RunState.RUN_REJECTED_MODEL_UNREACHABLE},
    RunState.SYNTHESIZED: {RunState.VALIDATED, RunState.RUN_REJECTED_VALIDATOR},
    RunState.VALIDATED: {RunState.ARCHIVED, RunState.RUN_REJECTED_VALIDATOR, RunState.RUN_REJECTED_ARCHIVE_IO},
    RunState.ARCHIVED: set(),
}

TERMINAL_STATES = {
    RunState.ARCHIVED,
    RunState.RUN_REJECTED_T3_ONLY,
    RunState.RUN_REJECTED_VALIDATOR,
    RunState.RUN_REJECTED_MODEL_UNREACHABLE,
    RunState.RUN_REJECTED_UPSTREAM_UNREACHABLE,
    RunState.RUN_REJECTED_HIERARCHY,
    RunState.RUN_REJECTED_ARCHIVE_IO,
    RunState.RUN_REJECTED_UPSTREAM_DRIFT,
}


def transition_run(
    record: RunRecord,
    next_state: RunState,
    *,
    artifact_updates: dict[str, str] | None = None,
    log_entry: dict[str, Any] | None = None,
) -> RunRecord:
    if record.state in TERMINAL_STATES:
        raise ValueError(f"terminal run state cannot transition: {record.state.value}")
    allowed = SUCCESS_TRANSITIONS.get(record.state, set())
    if next_state not in allowed:
        raise ValueError(f"invalid run transition: {record.state.value} -> {next_state.value}")
    artifacts = dict(record.phase_artifacts)
    if artifact_updates:
        artifacts.update(artifact_updates)
    step_log = list(record.step_log)
    step_log.append(log_entry or {"from": record.state.value, "to": next_state.value})
    return replace(record, state=next_state, phase_artifacts=artifacts, step_log=step_log)
