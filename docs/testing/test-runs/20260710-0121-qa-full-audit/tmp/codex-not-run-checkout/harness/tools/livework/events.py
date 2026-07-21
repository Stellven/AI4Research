"""Livework event emitters — append-only writers for events.jsonl.

5 emit functions, one per new event type from S02 architecture Schema B.
Each appends a single JSON line to the target file using real file I/O.
No network calls, no external dependencies beyond stdlib.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from .schemas import (
        AutopilotHeartbeatPayload,
        EventV2,
        EventV2Type,
        PaneDeadlockPayload,
        PaneStateEntry,
        PmDraftedPayload,
        RequirementIntakePayload,
        RoleTransitionPayload,
    )
except ImportError:  # pragma: no cover - direct script/sys.path fallback
    from livework.schemas import (
        AutopilotHeartbeatPayload,
        EventV2,
        EventV2Type,
        PaneDeadlockPayload,
        PaneStateEntry,
        PmDraftedPayload,
        RequirementIntakePayload,
        RoleTransitionPayload,
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_event(path: Path, event: EventV2) -> dict:
    """Append one event as JSON line. Returns the written dict."""
    line = json.dumps(event.__dict__, default=str, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return event.__dict__


def emit_heartbeat(
    path: Path,
    *,
    idle: bool = True,
    active_dispatches: int = 0,
    queue_depth: int = 0,
    pane_states: Optional[dict[str, PaneStateEntry]] = None,
    sprint_id: Optional[str] = None,
    actor: Optional[str] = None,
    seq: int = 0,
) -> dict:
    payload = AutopilotHeartbeatPayload(
        idle=idle,
        active_dispatches=active_dispatches,
        queue_depth=queue_depth,
        pane_states=pane_states or {},
    )
    event = EventV2(
        schema_version="1.0.0",
        event_type=EventV2Type.AUTOMATIC_HEARTBEAT.value,
        timestamp=_utcnow(),
        sprint_id=sprint_id,
        actor=actor,
        seq=seq,
        payload=payload.__dict__,
    )
    return _append_event(path, event)


def emit_deadlock_detected(
    path: Path,
    *,
    pane_id: str,
    dispatch_id: str,
    sprint_id: str,
    node_id: str,
    dispatch_sent_at: str,
    session_started_at: Optional[str] = None,
    elapsed_seconds: int = 0,
    deadline_seconds: int = 600,
    action: str = "alert",
    auto_recover: bool = False,
    actor: Optional[str] = None,
    seq: int = 0,
) -> dict:
    payload = PaneDeadlockPayload(
        pane_id=pane_id,
        dispatch_id=dispatch_id,
        sprint_id=sprint_id,
        node_id=node_id,
        dispatch_sent_at=dispatch_sent_at,
        session_started_at=session_started_at,
        elapsed_seconds=elapsed_seconds,
        deadline_seconds=deadline_seconds,
        action=action,
        auto_recover=auto_recover,
    )
    event = EventV2(
        schema_version="1.0.0",
        event_type=EventV2Type.PAN_DEADLOCK.value,
        timestamp=_utcnow(),
        sprint_id=sprint_id,
        actor=actor,
        seq=seq,
        payload=payload.__dict__,
    )
    return _append_event(path, event)


def emit_requirement_intake(
    path: Path,
    *,
    requirement_id: str,
    raw_requirement: str,
    sprint_id: str = "",
    submitted_by: str = "user",
    source: str = "chat",
    status: str = "pm_analysis",
    validation_error_code: Optional[str] = None,
    validation_error_message: Optional[str] = None,
    validation_hint: Optional[str] = None,
    actor: Optional[str] = None,
    seq: int = 0,
) -> dict:
    payload = RequirementIntakePayload(
        requirement_id=requirement_id,
        raw_requirement=raw_requirement,
        submitted_by=submitted_by,
        source=source,
        sprint_id=sprint_id,
        status=status,
        validation_error_code=validation_error_code,
        validation_error_message=validation_error_message,
        validation_hint=validation_hint,
    )
    event = EventV2(
        schema_version="1.0.0",
        event_type=EventV2Type.REQUIREMENT_INTAKE.value,
        timestamp=_utcnow(),
        sprint_id=sprint_id or None,
        actor=actor,
        seq=seq,
        payload=payload.__dict__,
    )
    return _append_event(path, event)


def emit_pm_drafted(
    path: Path,
    *,
    sprint_id: str,
    phase: str = "pm_analysis",
    prd_ready: bool = True,
    outcome_count: int = 0,
    next_step: str = "planner_review",
    actor: Optional[str] = None,
    seq: int = 0,
) -> dict:
    payload = PmDraftedPayload(
        sprint_id=sprint_id,
        phase=phase,
        prd_ready=prd_ready,
        outcome_count=outcome_count,
        next_step=next_step,
    )
    event = EventV2(
        schema_version="1.0.0",
        event_type=EventV2Type.PM_DRAFTED.value,
        timestamp=_utcnow(),
        sprint_id=sprint_id,
        actor=actor,
        seq=seq,
        payload=payload.__dict__,
    )
    return _append_event(path, event)


def emit_role_transition(
    path: Path,
    *,
    sprint_id: str,
    from_phase: str,
    to_phase: str,
    actor: str = "",
    reason: Optional[str] = None,
    node_id: Optional[str] = None,
    seq: int = 0,
) -> dict:
    payload = RoleTransitionPayload(
        sprint_id=sprint_id,
        from_phase=from_phase,
        to_phase=to_phase,
        actor=actor,
        reason=reason,
        node_id=node_id,
    )
    event = EventV2(
        schema_version="1.0.0",
        event_type=EventV2Type.ROLE_TRANSITION.value,
        timestamp=_utcnow(),
        sprint_id=sprint_id,
        actor=actor or None,
        seq=seq,
        payload=payload.__dict__,
    )
    return _append_event(path, event)
