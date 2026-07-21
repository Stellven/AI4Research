"""Six observability metrics for the Code-as-Harness Runtime.

S04 N4: sprint-20260519-solar-harness-vnext-code-as-harness-runtime-s04-orchestration-ui

Inputs are event records (parsed JSONL or EventLedger.replay() output) and
sprint status.json files. All functions are pure: same input → same output.
Empty inputs return safe defaults (no exceptions).

Public API:
    broker_coverage_pct(events)       -> float  (percentage, 0.0-100.0)
    policy_denied_rate(events)        -> float  (percentage, 0.0-100.0)
    approval_pending_count(events)    -> int
    event_ledger_lag_sec(events, now) -> float  (seconds)
    dispatcher_dead_letter(events)    -> int
    sprint_blocked_count(status_dir)  -> int

Plus:
    iter_events_from_jsonl(path)      -> generator[dict]
    ALARM_THRESHOLDS                  -> dict[str, dict]  (threshold table)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Union

# ---------------------------------------------------------------------------
# Alarm threshold registry (S04 design.md §6.3, S02 observability.md §1).
# Each entry: {"op": "<"|">", "threshold": <value>, "severity": "ALARM"|"CRITICAL"}
# The CLI/status renderer (N6) consumes this to color-code values.
# ---------------------------------------------------------------------------
ALARM_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "broker_coverage_pct":    {"op": "<", "threshold": 95.0, "severity": "CRITICAL"},
    "policy_denied_rate":     {"op": ">", "threshold": 10.0, "severity": "ALARM"},
    "approval_pending_count": {"op": ">", "threshold": 5,    "severity": "ALARM"},
    "event_ledger_lag_sec":   {"op": ">", "threshold": 60.0, "severity": "ALARM"},
    "dispatcher_dead_letter": {"op": ">", "threshold": 0,    "severity": "CRITICAL"},
    "sprint_blocked_count":   {"op": ">", "threshold": 3,    "severity": "ALARM"},
}


# ---------------------------------------------------------------------------
# Event shape helpers — events.jsonl entries may use {"event_type": ...}
# (sqlite-backed ledger) or {"type": ...} (legacy bridge); payload may be a
# dict or a JSON string. These helpers normalize without mutating the input.
# ---------------------------------------------------------------------------
def _event_type(ev: Dict[str, Any]) -> str:
    return str(ev.get("event_type") or ev.get("type") or "")


def _payload(ev: Dict[str, Any]) -> Dict[str, Any]:
    p = ev.get("payload")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except (json.JSONDecodeError, TypeError):
            return {}
    return p if isinstance(p, dict) else {}


def _parse_iso_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    s = ts
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def iter_events_from_jsonl(path: Union[str, os.PathLike]) -> Iterator[Dict[str, Any]]:
    """Yield event dicts from a JSONL file. Missing file → empty iterator."""
    p = Path(path)
    if not p.exists():
        return
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ---------------------------------------------------------------------------
# Metric 1 — broker_coverage_pct
#   contracted_actions / total_actions * 100
#   total_actions      = distinct action.proposed action_ids
#   contracted_actions = action_ids that received a policy.verdict == PASS
#   Empty / no actions → 100.0 (no gap means no coverage problem)
# ---------------------------------------------------------------------------
def broker_coverage_pct(events: Iterable[Dict[str, Any]]) -> float:
    proposed: Set[str] = set()
    contracted: Set[str] = set()
    for ev in events:
        et = _event_type(ev)
        pl = _payload(ev)
        aid = pl.get("action_id")
        if not aid:
            continue
        if et == "action.proposed":
            proposed.add(aid)
        elif et == "policy.verdict":
            verdict = str(pl.get("verdict") or "").upper()
            if verdict == "PASS":
                contracted.add(aid)
    total = len(proposed)
    if total == 0:
        return 100.0
    pct = (len(contracted & proposed) / total) * 100.0
    if pct > 100.0:
        pct = 100.0
    return round(pct, 4)


# ---------------------------------------------------------------------------
# Metric 2 — policy_denied_rate
#   FAIL policy.verdicts / total policy.verdicts * 100
#   Empty → 0.0 (no policy traffic → no denial rate)
# ---------------------------------------------------------------------------
def policy_denied_rate(events: Iterable[Dict[str, Any]]) -> float:
    total = 0
    denied = 0
    for ev in events:
        if _event_type(ev) != "policy.verdict":
            continue
        total += 1
        verdict = str(_payload(ev).get("verdict") or "").upper()
        if verdict == "FAIL":
            denied += 1
    if total == 0:
        return 0.0
    return round((denied / total) * 100.0, 4)


# ---------------------------------------------------------------------------
# Metric 3 — approval_pending_count
#   Count of policy.verdict FAIL with reason indicating human approval, where
#   the same action_id has NOT yet seen a subsequent verdict (PASS) or an
#   action.executed/failed event (i.e. still pending).
#   Empty → 0
# ---------------------------------------------------------------------------
_APPROVAL_REASON_TOKENS = (
    "HUMAN_APPROVAL_REQUIRED",
    "approval_pending",
    "approval_required",
    "needs_approval",
)


def _is_approval_pending_verdict(pl: Dict[str, Any]) -> bool:
    verdict = str(pl.get("verdict") or "").upper()
    if verdict != "FAIL":
        return False
    haystack = " ".join(
        str(pl.get(k) or "") for k in ("reason", "detail", "policy", "message")
    )
    if not haystack:
        return False
    upper = haystack.upper()
    return any(tok.upper() in upper for tok in _APPROVAL_REASON_TOKENS)


def approval_pending_count(events: Iterable[Dict[str, Any]]) -> int:
    pending: Set[str] = set()
    resolved: Set[str] = set()
    for ev in events:
        et = _event_type(ev)
        pl = _payload(ev)
        aid = pl.get("action_id")
        if not aid:
            continue
        if et == "policy.verdict":
            if _is_approval_pending_verdict(pl):
                pending.add(aid)
            elif str(pl.get("verdict") or "").upper() == "PASS":
                resolved.add(aid)
        elif et in {"action.executed", "action.failed", "action.cancelled"}:
            resolved.add(aid)
    return len(pending - resolved)


# ---------------------------------------------------------------------------
# Metric 4 — event_ledger_lag_sec
#   Seconds between the most recent event's created_at and `now`.
#   Empty → 0.0 (no lag if there are no events to lag behind)
# ---------------------------------------------------------------------------
def event_ledger_lag_sec(
    events: Iterable[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> float:
    latest: Optional[datetime] = None
    for ev in events:
        ts = _parse_iso_ts(ev.get("created_at") or ev.get("ts"))
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        return 0.0
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max((reference - latest).total_seconds(), 0.0)


# ---------------------------------------------------------------------------
# Metric 5 — dispatcher_dead_letter
#   Count events whose type indicates a dispatcher dead-letter, OR whose
#   payload carries dead_letter=true, OR (failure_handler classification)
#   payload.classification == "EXECUTION_FAILED" with dispatcher origin.
#   Empty → 0
# ---------------------------------------------------------------------------
_DEAD_LETTER_TYPES = frozenset({
    "dispatcher.dead_letter",
    "node.dispatch.dead_letter",
    "dispatch.dead_letter",
    "dispatch.failed",
    "dispatcher.failed_send",
})


def dispatcher_dead_letter(events: Iterable[Dict[str, Any]]) -> int:
    count = 0
    for ev in events:
        et = _event_type(ev)
        if et in _DEAD_LETTER_TYPES:
            count += 1
            continue
        pl = _payload(ev)
        if pl.get("dead_letter") is True:
            count += 1
            continue
        if et == "failure.classified" and str(pl.get("origin") or "") == "dispatcher":
            count += 1
    return count


# ---------------------------------------------------------------------------
# Metric 6 — sprint_blocked_count
#   Scan a directory of *.status.json files; count those in a blocked-shaped
#   state. A sprint is blocked when its status field is "blocked", or its
#   phase is "blocked", or it carries a non-empty blocked_by list AND its
#   top-level status is not a terminal state (passed/failed/superseded/cancelled).
#   Empty / missing dir → 0
# ---------------------------------------------------------------------------
_BLOCKED_STATUS_TOKENS = frozenset({"blocked", "blocked_by_dependency", "waiting"})
_TERMINAL_STATES = frozenset({"passed", "failed", "superseded", "cancelled"})


def _is_blocked_status(doc: Dict[str, Any]) -> bool:
    status = str(doc.get("status") or "").lower()
    phase = str(doc.get("phase") or "").lower()
    if status in _TERMINAL_STATES:
        return False
    if status in _BLOCKED_STATUS_TOKENS or phase in _BLOCKED_STATUS_TOKENS:
        return True
    blocked_by = doc.get("blocked_by")
    if isinstance(blocked_by, list) and len(blocked_by) > 0:
        return True
    return False


def sprint_blocked_count(status_source: Union[str, os.PathLike, Iterable[Dict[str, Any]]]) -> int:
    if isinstance(status_source, (str, os.PathLike)):
        d = Path(status_source)
        if not d.exists() or not d.is_dir():
            return 0
        docs: List[Dict[str, Any]] = []
        for p in d.glob("*.status.json"):
            try:
                with open(p, encoding="utf-8") as fh:
                    docs.append(json.load(fh))
            except (OSError, json.JSONDecodeError):
                continue
    else:
        docs = [d for d in status_source if isinstance(d, dict)]
    return sum(1 for d in docs if _is_blocked_status(d))
