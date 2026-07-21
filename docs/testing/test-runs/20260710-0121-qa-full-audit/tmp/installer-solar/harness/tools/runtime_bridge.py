"""Solar Harness — Runtime adoption bridge.

Bridges legacy sprint artifacts into the Managed Agent Runtime event model.

This module is intentionally conservative:
- legacy status/events remain on disk for compatibility;
- v2 session events are append-only and idempotent;
- projection caches can be regenerated from the v2 log when requested.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

sys.path.insert(0, os.path.dirname(__file__))

from activity_runtime import ActivityRuntime
from projection_engine import ProjectionEngine
from session_log import DuplicateEventError, SessionLog

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", os.path.expanduser("~/.solar/harness"))).expanduser()
SPRINTS_DIR = HARNESS_DIR / "sprints"


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_json(value: str) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": value}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _fingerprint(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


def _activity_id(event: str, payload: Dict[str, Any]) -> str:
    to = payload.get("to") or payload.get("target") or payload.get("pane") or payload.get("owner") or "runtime"
    task = payload.get("task") or payload.get("stage") or payload.get("slice") or payload.get("node") or event
    round_num = payload.get("round")
    parts = [str(event), str(to), str(task)]
    if round_num is not None:
        parts.append(f"r{round_num}")
    raw = ":".join(p.replace("/", "_").replace(" ", "_") for p in parts)
    return raw[:96]


def _status_activity_events(status: str) -> Iterable[str]:
    normalized = (status or "").strip().lower()
    if normalized in ("passed", "done", "eval_pass", "eval_passed", "completed", "finalized"):
        return ("command_issued", "activity_started", "activity_succeeded")
    if normalized in ("failed", "error", "failed_review"):
        return ("command_issued", "activity_started", "activity_failed")
    if normalized in ("reviewing", "awaiting_review"):
        return ("command_issued", "activity_started", "activity_handoff")
    if normalized in ("active", "planning", "approved", "implementation", "running"):
        return ("command_issued", "activity_started")
    if normalized in ("cancelled", "canceled"):
        return ("command_issued", "activity_started", "activity_cancelled")
    return ("command_issued",)


def record_legacy_event(
    sprint_id: str,
    event: str,
    actor: str = "coordinator",
    payload: Optional[Dict[str, Any]] = None,
    *,
    harness_dir: Path = HARNESS_DIR,
) -> Dict[str, Any]:
    """Dual-write one legacy event into the v2 session log.

    The legacy event is always preserved as a log_message. Dispatch-like events
    also create command/activity lifecycle events so ProjectionEngine can infer
    state without reading status.json.
    """
    if not sprint_id:
        return {"ok": False, "reason": "empty_sprint_id"}

    payload = dict(payload or {})
    log = SessionLog.for_sprint(sprint_id, harness_dir=str(harness_dir))
    fp = _fingerprint({"event": event, "actor": actor, "payload": payload})
    appended = []

    try:
        eid = log.append(
            "log_message",
            actor=actor or "coordinator",
            source="legacy_runtime_bridge",
            sprint_id=sprint_id,
            idempotency_key=f"legacy-log:{sprint_id}:{fp}",
            payload={"legacy_event": event, **payload},
        )
        if eid:
            appended.append("log_message")
    except DuplicateEventError:
        pass

    rt = ActivityRuntime(sprint_id, harness_dir=str(harness_dir))
    act_id = _activity_id(event, payload)
    round_num = int(payload.get("round") or 1)

    def add(kind: str, fn, *args, **kwargs) -> None:
        try:
            eid = fn(*args, **kwargs)
            if eid:
                appended.append(kind)
        except DuplicateEventError:
            pass

    if event in {
        "dispatch_queued",
        "dispatched",
        "round_dispatched",
        "slice_dispatched",
        "mixture_dispatched",
        "graph_nodes_dispatched",
        "planner_notified",
    }:
        add(
            "command_issued",
            rt.command_issued,
            act_id,
            actor=actor or "coordinator",
            target=str(payload.get("to") or payload.get("target") or payload.get("pane") or ""),
            round_num=round_num,
            payload={"legacy_event": event, **payload},
        )
    elif event in {"dispatch_failed", "graph_dispatch_failed", "graph_eval_dispatch_failed"}:
        add(
            "activity_failed",
            rt.activity_failed,
            act_id,
            actor=actor or "coordinator",
            error=str(payload.get("reason") or payload.get("error") or event),
            payload={"legacy_event": event, **payload},
        )
    elif event in {"state_changed", "phase_transition"}:
        to_status = str(payload.get("to") or payload.get("status") or "")
        from_status = str(payload.get("from") or "")
        if to_status:
            add(
                "state_transition",
                rt.state_transition,
                actor=actor or "coordinator",
                from_status=from_status,
                to_status=to_status,
                round_num=round_num,
            )
    elif event in {"handle_passed_completed", "parallel_integrated", "mixture_merged", "graph_parent_ready_passed"}:
        add(
            "activity_succeeded",
            rt.activity_succeeded,
            act_id,
            actor=actor or "coordinator",
            payload={"legacy_event": event, **payload},
        )

    return {"ok": True, "sprint_id": sprint_id, "appended": appended}


def adopt_sprint(
    sprint_id: str,
    *,
    harness_dir: Path = HARNESS_DIR,
    write_cache: bool = False,
) -> Dict[str, Any]:
    """Adopt one legacy sprint into the v2 runtime log."""
    sprints_dir = harness_dir / "sprints"
    status_path = sprints_dir / f"{sprint_id}.status.json"
    events_path = sprints_dir / f"{sprint_id}.events.jsonl"
    status = _read_json(status_path)

    log = SessionLog.for_sprint(sprint_id, harness_dir=str(harness_dir))
    appended = 0

    try:
        if log.append(
            "session_started",
            actor="runtime_bridge",
            source="legacy_runtime_bridge",
            sprint_id=sprint_id,
            idempotency_key=f"bridge:session_started:{sprint_id}",
            payload={"adopted_at": _now_ts()},
        ):
            appended += 1
    except DuplicateEventError:
        pass

    if events_path.exists():
        with events_path.open(encoding="utf-8") as fh:
            for idx, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    ev = {"raw": line}
                fp = _fingerprint({"idx": idx, "event": ev})
                try:
                    if log.append(
                        "log_message",
                        actor=str(ev.get("by") or ev.get("actor") or "legacy"),
                        source="legacy_events_jsonl",
                        sprint_id=sprint_id,
                        idempotency_key=f"bridge:legacy-event:{sprint_id}:{fp}",
                        payload={"legacy_event": ev},
                    ):
                        appended += 1
                except DuplicateEventError:
                    pass

    if status:
        current = str(status.get("status") or "queued")
        phase = str(status.get("phase") or "")
        round_num = int(status.get("round") or 0)
        activity_id = "legacy-status"
        for kind in _status_activity_events(current):
            try:
                if kind == "command_issued":
                    eid = log.append(
                        "command_issued",
                        actor="runtime_bridge",
                        source="legacy_status_snapshot",
                        sprint_id=sprint_id,
                        activity_id=activity_id,
                        idempotency_key=f"bridge:status:{sprint_id}:command",
                        payload={"status": current, "phase": phase, "round": round_num},
                    )
                else:
                    eid = log.append(
                        kind,
                        actor="runtime_bridge",
                        source="legacy_status_snapshot",
                        sprint_id=sprint_id,
                        activity_id=activity_id,
                        idempotency_key=f"bridge:status:{sprint_id}:{kind}:{current}:{round_num}",
                        payload={"status": current, "phase": phase, "round": round_num},
                    )
                if eid:
                    appended += 1
            except DuplicateEventError:
                pass
        try:
            if log.append(
                "state_transition",
                actor="runtime_bridge",
                source="legacy_status_snapshot",
                sprint_id=sprint_id,
                idempotency_key=f"bridge:status-transition:{sprint_id}:{current}:{round_num}",
                payload={"from": "", "to": current, "phase": phase, "round": round_num},
            ):
                appended += 1
        except DuplicateEventError:
            pass

    projected = None
    if write_cache:
        engine = ProjectionEngine(sprint_id, harness_dir=str(harness_dir))
        projected = engine.project()
        engine.write_status_cache(projected)

    return {
        "ok": True,
        "sprint_id": sprint_id,
        "appended": appended,
        "status_path": str(status_path),
        "legacy_events_path": str(events_path),
        "session_events_path": SessionLog.log_path(sprint_id, harness_dir=str(harness_dir)),
        "projected_status": getattr(projected, "status", None),
        "projected_events": getattr(projected, "event_count", None),
    }


def adopt_all(*, harness_dir: Path = HARNESS_DIR, write_cache: bool = False) -> Dict[str, Any]:
    results = []
    for status_path in sorted((harness_dir / "sprints").glob("sprint-*.status.json")):
        sid = status_path.name.removesuffix(".status.json")
        results.append(adopt_sprint(sid, harness_dir=harness_dir, write_cache=write_cache))
    return {"ok": True, "count": len(results), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge legacy sprint state into session-log v2")
    sub = parser.add_subparsers(dest="cmd")

    adopt = sub.add_parser("adopt", help="Adopt one sprint, or --all")
    adopt.add_argument("sprint_id", nargs="?")
    adopt.add_argument("--all", action="store_true")
    adopt.add_argument("--write-cache", action="store_true")
    adopt.add_argument("--json", action="store_true")
    adopt.add_argument("--quiet", action="store_true")

    event = sub.add_parser("event", help="Dual-write one legacy event")
    event.add_argument("sprint_id")
    event.add_argument("event")
    event.add_argument("actor", nargs="?", default="coordinator")
    event.add_argument("payload", nargs="?", default="{}")
    event.add_argument("--json", action="store_true")
    event.add_argument("--quiet", action="store_true")

    args = parser.parse_args()

    # Backward-friendly CLI: runtime_bridge.py <sid> [--write-cache]
    if args.cmd is None and len(sys.argv) > 1:
        sid = sys.argv[1]
        write_cache = "--write-cache" in sys.argv
        quiet = "--quiet" in sys.argv
        result = adopt_sprint(sid, write_cache=write_cache)
        if not quiet:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.cmd == "adopt":
        if args.all:
            result = adopt_all(write_cache=args.write_cache)
        elif args.sprint_id:
            result = adopt_sprint(args.sprint_id, write_cache=args.write_cache)
        else:
            parser.error("adopt requires sprint_id or --all")
    elif args.cmd == "event":
        result = record_legacy_event(
            args.sprint_id,
            args.event,
            args.actor,
            _safe_json(args.payload),
        )
    else:
        parser.print_help()
        return

    if not getattr(args, "quiet", False):
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"ok {result}")


if __name__ == "__main__":
    main()
