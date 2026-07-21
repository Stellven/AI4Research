"""Idle detection and deadlock alerting for Solar-Harness live-work visibility.

Three pure functions with explicit time injection (all timestamps passed
as parameters, no hidden clock calls):

  - is_idle(pane_state, now) -> bool
  - detect_deadlock(dispatch_log, now, timeout) -> list[DeadlockAlert]
  - should_emit_heartbeat(last_hb, now, interval) -> bool

Spec: sprint-20260514-p0-…-s02-architecture.interfaces.md §N4
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeadlockAlert:
    pane: str = ""
    sprint_id: str = ""
    node_id: str = ""
    silence_seconds: float = 0.0
    threshold_seconds: float = 600.0


def is_idle(
    pane_state: dict[str, Any],
    now: str,
) -> bool:
    """Determine if the harness is idle given aggregated pane state.

    Args:
        pane_state: Aggregated state dict with keys:
            - is_idle (bool): reported idle flag
            - active_panes (list[str]): panes with active leases
            - queue_depth (int): items in dispatch queue
        now: ISO 8601 UTC timestamp, explicitly injected.

    Returns:
        True if no active panes, no queue items, and idle flag is set.
    """
    if not pane_state.get("is_idle", True):
        return False
    active = pane_state.get("active_panes", [])
    if isinstance(active, list) and len(active) > 0:
        return False
    depth = pane_state.get("queue_depth", 0)
    if isinstance(depth, (int, float)) and depth > 0:
        return False
    return True


def _parse_iso(ts: str) -> float:
    """Parse ISO 8601 to epoch seconds. Returns 0.0 for unparseable."""
    if not ts:
        return 0.0
    try:
        from datetime import datetime, timezone
        cleaned = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.timestamp()
    except Exception:
        return 0.0


def detect_deadlock(
    dispatch_log: list[dict[str, Any]],
    now: str,
    timeout: float = 600.0,
) -> list[DeadlockAlert]:
    """Scan dispatch log entries for panes that have been silent too long.

    Args:
        dispatch_log: List of dispatch entries, each with keys:
            - pane (str): pane identifier
            - sprint_id (str): owning sprint
            - node_id (str): assigned node
            - dispatched_at (str): ISO 8601 dispatch timestamp
            - last_heartbeat (str): ISO 8601 last observed activity
        now: ISO 8601 UTC timestamp, explicitly injected.
        timeout: Seconds of silence before alerting.

    Returns:
        List of DeadlockAlert for panes exceeding silence threshold.
    """
    now_epoch = _parse_iso(now)
    if now_epoch <= 0:
        return []

    alerts: list[DeadlockAlert] = []
    for entry in dispatch_log:
        last_activity = entry.get("last_heartbeat") or entry.get("dispatched_at", "")
        last_epoch = _parse_iso(last_activity)
        if last_epoch <= 0:
            continue
        silence = now_epoch - last_epoch
        if silence > timeout:
            alerts.append(DeadlockAlert(
                pane=entry.get("pane", ""),
                sprint_id=entry.get("sprint_id", ""),
                node_id=entry.get("node_id", ""),
                silence_seconds=round(silence, 1),
                threshold_seconds=timeout,
            ))
    return alerts


def should_emit_heartbeat(
    last_hb: str,
    now: str,
    interval: float = 60.0,
) -> bool:
    """Decide whether a heartbeat event should be emitted.

    Args:
        last_hb: ISO 8601 UTC of the last emitted heartbeat. Empty string
                 means never emitted.
        now: ISO 8601 UTC timestamp, explicitly injected.
        interval: Minimum seconds between heartbeats.

    Returns:
        True if no prior heartbeat or interval has elapsed.
    """
    if not last_hb:
        return True
    now_epoch = _parse_iso(now)
    last_epoch = _parse_iso(last_hb)
    if now_epoch <= 0 or last_epoch <= 0:
        return True
    elapsed = now_epoch - last_epoch
    return elapsed >= interval
