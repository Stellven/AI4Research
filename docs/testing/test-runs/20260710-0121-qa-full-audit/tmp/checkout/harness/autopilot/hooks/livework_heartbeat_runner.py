#!/usr/bin/env python3
"""Livework heartbeat runner — called by livework_heartbeat_hook.sh.

Reads harness state via idle_detector + state_aggregator, decides whether
to emit a heartbeat or deadlock event, and appends to events.jsonl.

Exit codes: 0 = success (or no-op), 1 = error (hook will catch and exit 0).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar" / "harness"))
EVENTS_JSONL = Path(os.environ.get("LIVEWORK_EVENTS_JSONL", HARNESS_DIR / "run" / "livework-events.jsonl"))
HEARTBEAT_INTERVAL = float(os.environ.get("LIVEWORK_HEARTBEAT_INTERVAL", "300"))
DEADLOCK_TIMEOUT = float(os.environ.get("LIVEWORK_DEADLOCK_TIMEOUT", "600"))

sys.path.insert(0, str(HARNESS_DIR / "lib"))

from livework.idle_detector import is_idle, should_emit_heartbeat, detect_deadlock
from livework.events import emit_heartbeat, emit_deadlock_detected
from livework.state_aggregator import aggregate_pane_state


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_recent_events(path: Path, max_lines: int = 100) -> list[dict]:
    """Read last N lines from events JSONL."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        return [json.loads(l) for l in lines[-max_lines:]]
    except Exception:
        return []


def _last_heartbeat_ts(events: list[dict]) -> str:
    """Find timestamp of most recent heartbeat event."""
    for e in reversed(events):
        if e.get("event_type") == "autopilot_heartbeat":
            return e.get("timestamp", "")
    return ""


def _load_dispatch_log(sprints_dir: Path) -> list[dict]:
    """Load dispatch entries from status files for deadlock detection."""
    entries = []
    if not sprints_dir.exists():
        return entries
    for sf in sprints_dir.glob("sprint-*.status.json"):
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            if data.get("status") not in ("active", "drafting", "building", "reviewing"):
                continue
            sid = data.get("id", "")
            for node in data.get("nodes", []):
                if node.get("status") in ("in_progress", "dispatched"):
                    entries.append({
                        "pane": node.get("assigned_to", ""),
                        "sprint_id": sid,
                        "node_id": node.get("id", ""),
                        "dispatched_at": node.get("dispatched_at", ""),
                        "last_heartbeat": node.get("last_heartbeat", ""),
                    })
        except Exception:
            continue
    return entries


def run() -> int:
    now = _now()

    # Ensure events file directory exists
    EVENTS_JSONL.parent.mkdir(parents=True, exist_ok=True)

    # Read recent events for state aggregation
    events = _read_recent_events(EVENTS_JSONL)

    # Aggregate pane state
    pane_state_data = aggregate_pane_state(events)
    pane_state = {
        "is_idle": pane_state_data.is_idle,
        "active_panes": pane_state_data.active_panes,
        "queue_depth": pane_state_data.queue_depth,
    }

    # Check if heartbeat should be emitted
    last_hb = _last_heartbeat_ts(events)
    if should_emit_heartbeat(last_hb, now, HEARTBEAT_INTERVAL):
        emit_heartbeat(
            EVENTS_JSONL,
            idle=is_idle(pane_state, now),
            active_dispatches=len(pane_state_data.active_panes),
            queue_depth=pane_state_data.queue_depth,
            pane_states={
                k: {"lease_active": v.lease_active, "last_activity": v.last_activity}
                for k, v in pane_state_data.pane_details.items()
            },
            actor="livework_heartbeat_runner",
        )

    # Deadlock detection
    sprints_dir = HARNESS_DIR / "sprints"
    dispatch_log = _load_dispatch_log(sprints_dir)
    alerts = detect_deadlock(dispatch_log, now, DEADLOCK_TIMEOUT)
    for alert in alerts:
        emit_deadlock_detected(
            EVENTS_JSONL,
            pane_id=alert.pane,
            dispatch_id="",
            sprint_id=alert.sprint_id,
            node_id=alert.node_id,
            dispatch_sent_at="",
            elapsed_seconds=int(alert.silence_seconds),
            deadline_seconds=int(alert.threshold_seconds),
            actor="livework_heartbeat_runner",
        )

    return 0


if __name__ == "__main__":
    sys.exit(run())
