"""State aggregation pure functions for Solar-Harness live-work visibility.

Two pure functions that derive structured state from event streams:
  - aggregate_pane_state(events) -> PaneState
  - resolve_role(events, sprint_id) -> RoleNextStep

No IO, no clock, no global state. Deterministic for same input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    from .schemas import (
        NodeSummary,
        PaneStateEntry,
    )
except ImportError:  # pragma: no cover - direct script/sys.path fallback
    from livework.schemas import (
        NodeSummary,
        PaneStateEntry,
    )


@dataclass
class PaneState:
    """Aggregate pane/harness state derived from event stream."""

    is_idle: bool = True
    active_panes: list[str] = field(default_factory=list)
    queue_depth: int = 0
    pane_details: dict[str, PaneStateEntry] = field(default_factory=dict)
    last_heartbeat_ts: Optional[str] = None


@dataclass
class RoleNextStep:
    """Role-aware next-step view for a specific sprint."""

    sprint_id: str = ""
    phase: str = ""
    next_action: str = ""
    nodes: list[NodeSummary] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    gate_status: dict[str, str] = field(default_factory=dict)


def aggregate_pane_state(events: list[dict]) -> PaneState:
    """Derive aggregate pane state from event stream.

    Scans events for autopilot_heartbeat entries, extracts pane states,
    and determines idle/active status from the latest heartbeat.

    Pure: no IO, no clock dependency.
    """
    heartbeats = [
        e for e in events
        if e.get("event_type") == "autopilot_heartbeat"
    ]

    if not heartbeats:
        return PaneState(is_idle=True, active_panes=[], queue_depth=0)

    latest = heartbeats[-1]
    payload = latest.get("payload", {})

    idle = payload.get("idle", True)
    queue_depth = payload.get("queue_depth", 0)
    raw_pane_states = payload.get("pane_states", {})

    pane_details: dict[str, PaneStateEntry] = {}
    active_panes: list[str] = []

    for pane_id, state in raw_pane_states.items():
        entry = PaneStateEntry(
            lease_active=state.get("lease_active", False),
            last_activity=state.get("last_activity", ""),
        )
        pane_details[pane_id] = entry
        if entry.lease_active:
            active_panes.append(pane_id)

    is_idle = idle and len(active_panes) == 0 and queue_depth == 0

    return PaneState(
        is_idle=is_idle,
        active_panes=active_panes,
        queue_depth=queue_depth,
        pane_details=pane_details,
        last_heartbeat_ts=latest.get("timestamp"),
    )


def resolve_role(events: list[dict], sprint_id: str) -> RoleNextStep:
    """Derive role-aware next-step view for a specific sprint.

    Filters events by sprint_id, finds the latest phase transition,
    builds node summaries, and derives the next action.

    Pure: no IO, no clock dependency.
    """
    sprint_events = [
        e for e in events
        if e.get("sprint_id") == sprint_id
        or e.get("payload", {}).get("sprint_id") == sprint_id
    ]

    if not sprint_events:
        return RoleNextStep(sprint_id=sprint_id, phase="unknown")

    # Find latest phase from role_transition events
    transitions = [
        e for e in sprint_events
        if e.get("event_type") == "role_transition"
    ]

    phase = "queued"
    if transitions:
        latest_t = transitions[-1]
        phase = latest_t.get("payload", {}).get("to_phase", "queued")

    # Check pm_drafted events for PM phase info
    pm_events = [
        e for e in sprint_events
        if e.get("event_type") == "pm_drafted"
    ]
    if pm_events and phase in ("queued", "pm_analysis"):
        phase = "pm_analysis"

    # Build node summaries from task_graph events
    nodes: list[NodeSummary] = []
    node_events = [
        e for e in sprint_events
        if e.get("event_type") in ("node_status_change", "task_graph_generated")
    ]
    seen_node_ids: set[str] = set()
    for ne in node_events:
        payload = ne.get("payload", {})
        node_list = payload.get("nodes", [])
        for n in node_list:
            nid = n.get("id", "")
            if nid and nid not in seen_node_ids:
                seen_node_ids.add(nid)
                nodes.append(NodeSummary(
                    id=nid,
                    status=n.get("status", "pending"),
                    goal=n.get("goal", ""),
                    assigned_to=n.get("assigned_to"),
                    depends_on=n.get("depends_on", []),
                ))

    # Derive blocked_by from pending nodes whose dependencies aren't met
    passed_ids = {n.id for n in nodes if n.status in ("passed", "reviewing")}
    blocked_by: list[str] = []
    for n in nodes:
        if n.status == "pending" and n.depends_on:
            unmet = [d for d in n.depends_on if d not in passed_ids]
            if unmet:
                blocked_by.extend(unmet)

    # Derive next_action from phase + node statuses
    next_action = _derive_next_action(phase, nodes, blocked_by)

    # Derive gate_status from node statuses
    gate_status: dict[str, str] = {}
    for n in nodes:
        gate_key = f"{n.id}-gate"
        gate_status[gate_key] = n.status

    return RoleNextStep(
        sprint_id=sprint_id,
        phase=phase,
        next_action=next_action,
        nodes=nodes,
        blocked_by=sorted(set(blocked_by)),
        gate_status=gate_status,
    )


def _derive_next_action(
    phase: str,
    nodes: list[NodeSummary],
    blocked_by: list[str],
) -> str:
    """Derive human-readable next action from phase and node state."""
    if phase == "queued":
        return "Awaiting PM analysis"
    if phase in ("pm_analysis", "pm_drafting"):
        return "PM drafting PRD"
    if phase == "planning":
        return "Planner designing task graph"

    in_progress = [n for n in nodes if n.status == "in_progress"]
    reviewing = [n for n in nodes if n.status == "reviewing"]
    pending = [n for n in nodes if n.status == "pending"]
    passed = [n for n in nodes if n.status == "passed"]
    failed = [n for n in nodes if n.status == "failed"]

    if failed:
        return f"Node(s) {', '.join(n.id for n in failed)} failed"

    if reviewing:
        ids = ", ".join(n.id for n in reviewing)
        return f"Awaiting evaluator review on {ids}"

    if in_progress:
        ids = ", ".join(n.id for n in in_progress)
        return f"Builder working on {ids}"

    if pending and blocked_by:
        return f"Waiting for {', '.join(blocked_by)} to complete"

    if pending:
        return f"Ready to dispatch {', '.join(n.id for n in pending)}"

    if all(n.status == "passed" for n in nodes) and nodes:
        return "All nodes passed. Sprint complete."

    return "No actionable next step"
