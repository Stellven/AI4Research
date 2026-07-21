"""Solar Harness — Projection Engine.

Rebuilds sprint status from the session event log and writes a
legacy-compatible status.json projection cache.

Usage::

    engine = ProjectionEngine(sprint_id="sprint-xyz")
    state  = engine.project()          # ProjectedState dataclass
    engine.write_status_cache(state)   # update status.json on disk
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from session_log import SessionLog

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")

# Map of (last terminal event type) → legacy status value
_ACTIVITY_STATUS_MAP: Dict[str, str] = {
    "activity_succeeded": "passed",
    "activity_failed":    "error",
    "activity_cancelled": "cancelled",
    "activity_handoff":   "reviewing",
    "activity_started":   "active",
    "command_issued":     "queued",
}

# Ordered status progression for drift detection
_STATUS_RANK: Dict[str, int] = {
    "queued":             1,
    "drafting":           2,
    "planning":           3,
    "approved":           4,
    "active":             5,
    "building_parallel":  6,
    "architect_reviewing": 7,
    "reviewing":          8,
    "needs_human_review": 9,
    "passed":             10,
    "error":              11,
    "failed":             11,
    "failed_review":      11,
    "cancelled":          12,
    "superseded":         13,
    "interrupted":        14,
}


@dataclass
class ActivityState:
    activity_id: str
    sprint_id: Optional[str]
    status: str          # queued | active | reviewing | passed | error | cancelled
    last_event_type: str
    last_event_ts: str
    round: int = 0
    error_count: int = 0
    retry_count: int = 0
    correlation_id: Optional[str] = None


@dataclass
class ProjectedState:
    sprint_id: str
    status: str
    round: int
    activities: List[ActivityState] = field(default_factory=list)
    duplicate_commands: List[str] = field(default_factory=list)
    stale_activities: List[str] = field(default_factory=list)
    event_count: int = 0
    last_event_ts: Optional[str] = None
    drift_detected: bool = False
    drift_reason: str = ""


class ProjectionEngine:
    """Replay session events for one sprint and project a coherent state."""

    def __init__(
        self,
        sprint_id: str,
        *,
        harness_dir: Optional[str] = None,
        stale_threshold_minutes: int = 60,
    ) -> None:
        self.sprint_id = sprint_id
        self._harness_dir = harness_dir or HARNESS_DIR
        self._stale_secs = stale_threshold_minutes * 60
        self._log = SessionLog.for_sprint(sprint_id, harness_dir=harness_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def project(self) -> ProjectedState:
        """Replay events and return a ProjectedState."""
        activities: Dict[str, ActivityState] = {}
        seen_commands: Dict[str, str] = {}       # idem_key → activity_id
        duplicate_commands: List[str] = []
        overall_round = 0
        event_count = 0
        last_ts: Optional[str] = None
        last_state_status: Optional[str] = None

        for ev in self._log.replay(sprint_id=self.sprint_id):
            event_count += 1
            etype = ev.get("type", "")
            act_id = ev.get("activity_id") or ""
            ts = ev.get("ts", "")
            idem = ev.get("idempotency_key")

            if ts:
                last_ts = ts

            # Track duplicate commands via idempotency_key
            if etype == "command_issued" and idem:
                if idem in seen_commands:
                    duplicate_commands.append(idem)
                else:
                    seen_commands[idem] = act_id

            # Update activity state
            if act_id and etype in _ACTIVITY_STATUS_MAP:
                if act_id not in activities:
                    activities[act_id] = ActivityState(
                        activity_id=act_id,
                        sprint_id=self.sprint_id,
                        status=_ACTIVITY_STATUS_MAP[etype],
                        last_event_type=etype,
                        last_event_ts=ts,
                        correlation_id=ev.get("correlation_id"),
                    )
                else:
                    act = activities[act_id]
                    act.status = _ACTIVITY_STATUS_MAP[etype]
                    act.last_event_type = etype
                    act.last_event_ts = ts

                if etype == "activity_failed":
                    activities[act_id].error_count += 1

            # Counter updates for events outside status map
            if act_id and etype == "activity_retry_scheduled":
                if act_id in activities:
                    activities[act_id].retry_count += 1

            # Track handoff round from state_transition events
            if etype == "state_transition":
                payload = ev.get("payload") or {}
                r = payload.get("round", 0)
                if isinstance(r, int) and r > overall_round:
                    overall_round = r
                to_status = payload.get("to")
                if isinstance(to_status, str) and to_status:
                    last_state_status = to_status

        activity_list = list(activities.values())
        stale = self._find_stale(activity_list, last_ts, last_state_status)

        # Derive overall sprint status from activities
        sprint_status = self._derive_sprint_status(activity_list, last_state_status)

        # Drift check against on-disk status.json
        drift, drift_reason = self._check_drift(sprint_status)

        return ProjectedState(
            sprint_id=self.sprint_id,
            status=sprint_status,
            round=overall_round,
            activities=activity_list,
            duplicate_commands=duplicate_commands,
            stale_activities=stale,
            event_count=event_count,
            last_event_ts=last_ts,
            drift_detected=drift,
            drift_reason=drift_reason,
        )

    def write_status_cache(self, state: ProjectedState) -> None:
        """Write legacy-compatible status.json derived from projection."""
        path = os.path.join(self._harness_dir, "sprints", f"{self.sprint_id}.status.json")
        existing: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    existing = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass

        existing["status"] = state.status
        existing["round"] = state.round
        existing["event_count"] = state.event_count
        existing["last_event_ts"] = state.last_event_ts
        existing["projected_at"] = _now_ts()
        existing["sid"] = existing.get("sid", self.sprint_id)
        existing["id"] = existing.get("id", self.sprint_id)
        existing["sprint_id"] = self.sprint_id

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _derive_sprint_status(
        self,
        activities: List[ActivityState],
        state_status: Optional[str] = None,
    ) -> str:
        normalized_state = _normalize_status(state_status or "")
        if normalized_state:
            return normalized_state
        if not activities:
            return "queued"
        statuses = {a.status for a in activities}
        # Priority: error > cancelled > reviewing > active > passed > queued
        if "error" in statuses:
            return "error"
        if "reviewing" in statuses:
            return "reviewing"
        if "active" in statuses:
            return "active"
        if all(a.status == "passed" for a in activities):
            return "passed"
        if "cancelled" in statuses and all(
            a.status in ("passed", "cancelled") for a in activities
        ):
            return "cancelled"
        return "queued"

    def _find_stale(
        self,
        activities: List[ActivityState],
        now_ts: Optional[str],
        state_status: Optional[str] = None,
    ) -> List[str]:
        if not now_ts:
            return []
        normalized_state = _normalize_status(state_status or "")
        if normalized_state in {
            "passed", "error", "failed", "failed_review", "cancelled",
            "superseded", "interrupted",
        }:
            return []
        stale = []
        try:
            now_dt = datetime.strptime(now_ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return []
        for act in activities:
            if act.status not in ("active", "queued"):
                continue
            try:
                act_dt = datetime.strptime(
                    act.last_event_ts, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            age_secs = (now_dt - act_dt).total_seconds()
            if age_secs > self._stale_secs:
                stale.append(act.activity_id)
        return stale

    def _check_drift(self, projected_status: str) -> tuple[bool, str]:
        path = os.path.join(self._harness_dir, "sprints", f"{self.sprint_id}.status.json")
        if not os.path.exists(path):
            return False, ""
        try:
            with open(path, encoding="utf-8") as fh:
                disk = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return False, ""
        disk_status = disk.get("status", "")
        if disk_status and disk_status != projected_status:
            p_rank = _STATUS_RANK.get(projected_status, 0)
            d_rank = _STATUS_RANK.get(disk_status, 0)
            if d_rank and p_rank and abs(p_rank - d_rank) >= 2:
                return True, (
                    f"disk={disk_status!r} projected={projected_status!r} "
                    f"(rank gap {abs(p_rank - d_rank)})"
                )
        return False, ""


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_status(status: str) -> str:
    s = (status or "").strip().lower()
    aliases = {
        "done": "passed",
        "eval_pass": "passed",
        "eval_passed": "passed",
        "completed": "passed",
        "finalized": "passed",
        "failed": "error",
        "failed_review": "error",
        "running": "active",
        "implementation": "active",
        "awaiting_review": "reviewing",
        "canceled": "cancelled",
    }
    s = aliases.get(s, s)
    valid = {
        "queued", "drafting", "planning", "approved", "active",
        "building_parallel", "architect_reviewing", "reviewing",
        "needs_human_review", "passed", "error", "failed",
        "failed_review", "cancelled", "superseded", "interrupted",
    }
    if s in valid:
        return s
    # Legacy runtime_status/state-mapper events sometimes encode a compact
    # state identity like:
    #   sprint-id:passed:eval_passed:_:hash
    # The projection source of truth is the status token inside that identity,
    # not the entire composite string.
    for part in s.split(":"):
        token = aliases.get(part.strip(), part.strip())
        if token in valid:
            return token
    return ""


def main() -> None:
    import argparse
    import sys

    sys.path.insert(0, os.path.dirname(__file__))

    parser = argparse.ArgumentParser(description="Project sprint state from session events")
    parser.add_argument("sprint_id", help="Sprint ID to project")
    parser.add_argument("--write-cache", action="store_true",
                        help="Write result back to status.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    engine = ProjectionEngine(args.sprint_id)
    state = engine.project()

    if args.write_cache:
        engine.write_status_cache(state)

    out = {
        "sprint_id": state.sprint_id,
        "status": state.status,
        "round": state.round,
        "event_count": state.event_count,
        "last_event_ts": state.last_event_ts,
        "drift_detected": state.drift_detected,
        "drift_reason": state.drift_reason,
        "duplicate_commands": state.duplicate_commands,
        "stale_activities": state.stale_activities,
        "activities": [
            {
                "activity_id": a.activity_id,
                "status": a.status,
                "last_event_type": a.last_event_type,
                "last_event_ts": a.last_event_ts,
                "error_count": a.error_count,
                "retry_count": a.retry_count,
            }
            for a in state.activities
        ],
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Sprint: {state.sprint_id}")
        print(f"Status: {state.status}  Round: {state.round}  Events: {state.event_count}")
        if state.drift_detected:
            print(f"⚠ DRIFT: {state.drift_reason}")
        if state.duplicate_commands:
            print(f"⚠ Duplicate commands: {state.duplicate_commands}")
        if state.stale_activities:
            print(f"⚠ Stale activities: {state.stale_activities}")


if __name__ == "__main__":
    main()
