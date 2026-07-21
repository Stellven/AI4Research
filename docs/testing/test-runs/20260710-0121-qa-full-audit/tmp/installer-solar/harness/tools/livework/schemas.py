"""Livework schemas for Solar-Harness visibility and auto-progression.

Implements the 4-schema data model defined in S02 architecture:
  - StatusExt (Schema A): status.json idle-state extension
  - EventV2 (Schema B): events.jsonl new event types
  - RequirementIntake (Schema C): requirement capture storage
  - RoleResolverView (Schema D): derived role-aware sprint view
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional


# ---------------------------------------------------------------------------
# Schema A: status.json Extension
# ---------------------------------------------------------------------------

@dataclass
class LastCompletedSprint:
    sprint_id: str
    status: Literal["passed", "failed"]
    completed_at: str  # ISO 8601 UTC


@dataclass
class ActiveSprint:
    sprint_id: str
    phase: str
    started_at: str  # ISO 8601 UTC


@dataclass
class StatusExt:
    """Extension fields for status.json providing idle-state visibility."""

    schema_version: str = "1.0.0"
    is_idle: bool = True
    last_completed_sprint: Optional[LastCompletedSprint] = None
    total_completed_sprints: int = 0
    active_panes: list[str] = field(default_factory=list)
    queue_depth: int = 0
    idle_since: Optional[str] = None  # ISO 8601 UTC, present when is_idle
    active_sprint: Optional[ActiveSprint] = None  # present when not idle


# ---------------------------------------------------------------------------
# Schema B: events.jsonl New Event Types
# ---------------------------------------------------------------------------

class EventV2Type(str, enum.Enum):
    AUTOMATIC_HEARTBEAT = "autopilot_heartbeat"
    PAN_DEADLOCK = "pane_deadlock"
    REQUIREMENT_INTAKE = "requirement_intake"
    PM_DRAFTED = "pm_drafted"
    ROLE_TRANSITION = "role_transition"


@dataclass
class PaneStateEntry:
    lease_active: bool = False
    last_activity: str = ""  # ISO 8601 UTC


@dataclass
class EventV2:
    """Base event for all new structured events in events.jsonl."""

    schema_version: str = "1.0.0"
    event_type: str = ""
    timestamp: str = ""  # ISO 8601 UTC
    sprint_id: Optional[str] = None
    actor: Optional[str] = None
    seq: int = 0
    payload: dict = field(default_factory=dict)


@dataclass
class AutopilotHeartbeatPayload:
    idle: bool = True
    active_dispatches: int = 0
    queue_depth: int = 0
    pane_states: dict[str, PaneStateEntry] = field(default_factory=dict)


@dataclass
class PaneDeadlockPayload:
    pane_id: str = ""
    dispatch_id: str = ""
    sprint_id: str = ""
    node_id: str = ""
    dispatch_sent_at: str = ""  # ISO 8601 UTC
    session_started_at: Optional[str] = None
    elapsed_seconds: int = 0
    deadline_seconds: int = 600
    action: str = "alert"
    auto_recover: bool = False


@dataclass
class RequirementIntakePayload:
    requirement_id: str = ""
    raw_requirement: str = ""
    submitted_by: str = "user"
    source: str = "chat"
    sprint_id: str = ""
    status: str = "pm_analysis"
    validation_error_code: Optional[str] = None
    validation_error_message: Optional[str] = None
    validation_hint: Optional[str] = None


@dataclass
class PmDraftedPayload:
    sprint_id: str = ""
    phase: str = "pm_analysis"
    prd_ready: bool = True
    outcome_count: int = 0
    next_step: str = "planner_review"


@dataclass
class RoleTransitionPayload:
    sprint_id: str = ""
    from_phase: str = ""
    to_phase: str = ""
    actor: str = ""
    reason: Optional[str] = None
    node_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Schema C: requirement_intake.json
# ---------------------------------------------------------------------------

@dataclass
class RejectionInfo:
    error_code: str = ""
    error_message: str = ""
    hint: Optional[str] = None


@dataclass
class RequirementIntake:
    """Persistent storage for user-submitted requirements."""

    schema_version: str = "1.0.0"
    requirement_id: str = ""
    sprint_id: str = ""
    raw_requirement: str = ""
    submitted_by: str = "user"
    source: str = "chat"
    status: str = "pm_analysis"
    created_at: str = ""  # ISO 8601 UTC
    updated_at: str = ""  # ISO 8601 UTC
    active_sprint_id: Optional[str] = None
    rejection: Optional[RejectionInfo] = None


# ---------------------------------------------------------------------------
# Schema D: role_resolver_view (Derived)
# ---------------------------------------------------------------------------

@dataclass
class NodeSummary:
    id: str = ""
    status: str = "pending"
    goal: str = ""
    assigned_to: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)


@dataclass
class GateStatus:
    pass  # dynamic keys; use dict for access


@dataclass
class RoleResolverView:
    """Read-only derived view: what is each role doing right now?"""

    schema_version: str = "1.0.0"
    sprint_id: str = ""
    phase: str = ""
    derived_at: str = ""  # ISO 8601 UTC
    nodes: list[NodeSummary] = field(default_factory=list)
    next_action: str = ""
    blocked_by: list[str] = field(default_factory=list)
    gate_status: dict[str, str] = field(default_factory=dict)
