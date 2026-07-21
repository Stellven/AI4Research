"""Sprint status projection — rebuild from event ledger.

S03 N8: sprint-20260519-solar-harness-vnext-code-as-harness-runtime-s03-core-runtime
Upstream: S02 state-machines.md §3, event_ledger.py

Projection is the derived view from the append-only event ledger.
Source of truth is events, not status.json.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from harness.lib.event_ledger import EventLedger

TERMINAL_STATES = frozenset({"passed", "failed", "superseded", "cancelled"})
INITIAL_STATE = "drafting"
VALID_STATES = frozenset({
    "drafting", "planning", "ready", "dispatching",
    "running", "reviewing",
    "passed", "failed", "superseded", "cancelled",
})

_STATUS_ALIASES = {
    "done": "passed", "eval_pass": "passed", "eval_passed": "passed",
    "completed": "passed", "finalized": "passed",
    "error": "failed", "failed_review": "failed",
    "awaiting_review": "reviewing", "canceled": "cancelled",
}


class DivergentError(Exception):
    """Raised when replay detects a projection divergence."""


def _normalize_status(status: str) -> str:
    s = (status or "").strip().lower()
    s = _STATUS_ALIASES.get(s, s)
    if ":" in s:
        for part in s.split(":"):
            token = _STATUS_ALIASES.get(part.strip(), part.strip())
            if token in VALID_STATES:
                return token
        return ""
    return s if s in VALID_STATES else ""


def replay_projection(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pure-function replay of events into a sprint status dict.

    Idempotent: calling with the same event list N times produces the same
    result. Duplicate event_ids are skipped.

    Deterministic: same (state, events) always produces the same output.

    Monotonic: terminal states (passed/failed/superseded/cancelled) cannot
    be reversed.

    Returns dict with: status, round, event_count, node_statuses,
    last_event_id, last_event_ts, state_hash.
    """
    state = INITIAL_STATE
    round_num = 0
    seen: Set[str] = set()
    node_statuses: Dict[str, str] = {}
    event_count = 0
    last_event_id: Optional[str] = None
    last_event_ts: Optional[str] = None

    for ev in events:
        eid = ev.get("event_id", "")

        # Rule 1: idempotent — skip duplicates
        if eid and eid in seen:
            continue
        if eid:
            seen.add(eid)

        event_count += 1
        last_event_id = eid
        ts = ev.get("created_at")
        if ts:
            last_event_ts = ts

        event_type = ev.get("event_type", "")
        payload = ev.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}

        if event_type == "state_transition":
            to_status = _normalize_status(payload.get("to", ""))
            if to_status:
                if state in TERMINAL_STATES and to_status != state:
                    raise DivergentError(
                        f"terminal '{state}' cannot transition to '{to_status}' "
                        f"(event_id={eid})"
                    )
                if to_status in VALID_STATES:
                    state = to_status

            r = payload.get("round")
            if isinstance(r, int) and r > round_num:
                round_num = r

        node_id = ev.get("node_id")
        if node_id and event_type == "state_transition":
            node_to = payload.get("to", "")
            if node_to:
                node_statuses[node_id] = node_to

    state_hash = _compute_state_hash(state, round_num, node_statuses)

    return {
        "status": state,
        "round": round_num,
        "event_count": event_count,
        "node_statuses": dict(node_statuses),
        "last_event_id": last_event_id,
        "last_event_ts": last_event_ts,
        "state_hash": state_hash,
    }


def build_sprint_status(
    sprint_id: str,
    *,
    ledger: Optional[EventLedger] = None,
    base_dir: Optional[str] = None,
    last_event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build sprint status from event ledger.

    Args:
        sprint_id: Sprint identifier.
        ledger: Optional EventLedger instance.
        base_dir: Optional base dir for EventLedger.
        last_event_id: If provided, only replay events after this ID
                       for incremental rebuild support.

    Returns:
        Dict compatible with legacy status.json fields.
    """
    if ledger is None:
        ledger = EventLedger(base_dir=base_dir)

    events = ledger.replay(sprint_id)

    if last_event_id is not None:
        events = _filter_after_event_id(events, last_event_id)

    projection = replay_projection(events)
    projection["sprint_id"] = sprint_id
    projection["projected_at"] = _now_ts()
    projection["id"] = sprint_id

    return projection


def incremental_rebuild(
    sprint_id: str,
    cached_projection: Dict[str, Any],
    *,
    ledger: Optional[EventLedger] = None,
    base_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Incrementally rebuild projection from cached state + new events.

    If no new events exist after cached_projection['last_event_id'],
    returns the cached projection with an updated projected_at timestamp.

    Otherwise rebuilds from the full event stream to maintain invariant
    checks (monotonic terminal, hash consistency).
    """
    last_eid = cached_projection.get("last_event_id")
    if not last_eid:
        return build_sprint_status(sprint_id, ledger=ledger, base_dir=base_dir)

    if ledger is None:
        ledger = EventLedger(base_dir=base_dir)

    new_events = _get_events_after(ledger, sprint_id, last_eid)

    if not new_events:
        cached_projection["projected_at"] = _now_ts()
        return cached_projection

    all_events = ledger.replay(sprint_id)
    projection = replay_projection(all_events)
    projection["sprint_id"] = sprint_id
    projection["projected_at"] = _now_ts()
    projection["id"] = sprint_id
    return projection


def dual_write_status_json(
    projection: Dict[str, Any],
    status_json_path: str,
) -> None:
    """Write projection to status.json with legacy field compatibility.

    Reads existing status.json, merges projection fields, writes atomically.
    Only adds/updates fields — never removes existing legacy fields.
    """
    existing: Dict[str, Any] = {}
    if os.path.exists(status_json_path):
        try:
            with open(status_json_path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass

    existing["status"] = projection["status"]
    existing["round"] = projection["round"]
    existing["event_count"] = projection["event_count"]
    existing["last_event_ts"] = projection.get("last_event_ts")
    existing["projected_at"] = projection.get("projected_at")
    existing["sid"] = existing.get("sid", projection.get("sprint_id", ""))
    existing["id"] = existing.get("id", projection.get("sprint_id", ""))
    existing["sprint_id"] = existing.get("sprint_id", projection.get("sprint_id", ""))
    existing["node_statuses"] = projection.get("node_statuses", {})
    existing["state_hash"] = projection.get("state_hash", "")

    tmp = status_json_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, status_json_path)


# -- internal helpers --

def _filter_after_event_id(
    events: List[Dict[str, Any]], last_event_id: str
) -> List[Dict[str, Any]]:
    found = False
    result = []
    for ev in events:
        if found:
            result.append(ev)
        elif ev.get("event_id") == last_event_id:
            found = True
    return result


def _get_events_after(
    ledger: EventLedger, sprint_id: str, last_event_id: str
) -> List[Dict[str, Any]]:
    return _filter_after_event_id(ledger.replay(sprint_id), last_event_id)


def _compute_state_hash(
    state: str, round_num: int, node_statuses: Dict[str, str]
) -> str:
    h = hashlib.sha256()
    h.update(state.encode("utf-8"))
    h.update(str(round_num).encode("utf-8"))
    for nid in sorted(node_statuses):
        h.update(nid.encode("utf-8"))
        h.update(node_statuses[nid].encode("utf-8"))
    return h.hexdigest()[:16]


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
