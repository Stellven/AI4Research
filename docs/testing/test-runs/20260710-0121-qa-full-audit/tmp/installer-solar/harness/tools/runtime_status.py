"""Solar Harness — runtime-backed status transitions.

This is the P1 adoption layer for coordinator state changes. It keeps the
legacy `sprints/<sid>.status.json` cache for compatibility, but every transition
also emits a v2 session-log state transition through ActivityRuntime.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import sys

sys.path.insert(0, os.path.dirname(__file__))

from activity_runtime import ActivityRuntime


STATUS_FIELDS: Dict[str, Dict[str, str]] = {
    "approved": {"phase": "plan_reviewed", "handoff_to": "builder", "target_role": "builder"},
    "reviewing": {"phase": "implementation_complete", "handoff_to": "evaluator", "target_role": "evaluator"},
    "passed": {"phase": "eval_passed", "handoff_to": "", "target_role": ""},
    "failed_review": {"phase": "eval_failed", "handoff_to": "builder", "target_role": "builder"},
    "drafting": {"phase": "spec", "handoff_to": "pm", "target_role": "pm"},
    # Bare active transitions must not imply a Builder route. Callers that pass
    # the Planner artifact gate must provide explicit builder status_fields.
    "active": {},
    "failed": {"phase": "failed", "handoff_to": "", "target_role": ""},
    "needs_human_review": {"phase": "needs_human", "handoff_to": "planner", "target_role": "planner"},
}

TERMINAL_GRAPH_FIELDS = {
    "passed": ("open_nodes", "failed_nodes"),
    "failed": ("open_nodes",),
}


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_extra(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw_extra": raw}


def _sid_from_status_path(path: Path) -> str:
    return path.name.removesuffix(".status.json")


def _harness_dir_from_status_path(path: Path) -> str:
    # ~/.solar/harness/sprints/<sid>.status.json -> ~/.solar/harness
    try:
        return str(path.parent.parent)
    except Exception:
        return os.path.expanduser("~/.solar/harness")


def transition_status(
    status_path: Path,
    new_status: str,
    event: str,
    actor: str,
    *,
    extra: Dict[str, Any] | None = None,
    bump_round: bool = False,
) -> Tuple[Dict[str, Any], str]:
    """Atomically update legacy status and append v2 runtime state transition."""
    extra = dict(extra or {})
    status_path = status_path.expanduser()
    if not status_path.exists():
        raise FileNotFoundError(f"sprint status not found: {status_path}")

    with status_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    sid = str(data.get("sprint_id") or data.get("id") or data.get("sid") or _sid_from_status_path(status_path))
    old_status = str(data.get("status", ""))
    old_round = int(data.get("round") or 0)
    new_round = old_round + 1 if bump_round else old_round
    now = _now_ts()

    status_fields = extra.pop("status_fields", None) or extra.pop("_status_fields", None) or {}
    if not isinstance(status_fields, dict):
        status_fields = {}

    data["status"] = new_status
    data.update(STATUS_FIELDS.get(new_status, {}))
    data.update(status_fields)
    for field in TERMINAL_GRAPH_FIELDS.get(new_status, ()):
        data.pop(field, None)
    if new_status in TERMINAL_GRAPH_FIELDS:
        data["active_node"] = None
    data["round"] = new_round
    data["updated_at"] = now
    data["runtime_state_source"] = "activity_runtime"

    hist: Dict[str, Any] = {"ts": now, "event": event, "by": actor}
    if bump_round:
        hist["round"] = new_round
    hist.update(extra)
    data.setdefault("history", []).append(hist)

    fd, tmp = tempfile.mkstemp(dir=str(status_path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, status_path)

    harness_dir = _harness_dir_from_status_path(status_path)
    rt = ActivityRuntime(sid, harness_dir=harness_dir)
    rt.state_transition(
        actor=actor,
        from_status=old_status,
        to_status=new_status,
        round_num=new_round,
        correlation_id=f"status:{sid}:{event}:{now}",
    )

    return data, (
        f"OK: {sid} {old_status} -> {new_status} "
        f"(round={old_round}->{new_round})" if bump_round else
        f"OK: {sid} {old_status} -> {new_status} (round={new_round})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Runtime-backed status transition")
    parser.add_argument("status_path")
    parser.add_argument("new_status")
    parser.add_argument("event")
    parser.add_argument("actor")
    parser.add_argument("extra_json", nargs="?", default="{}")
    parser.add_argument("--bump-round", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data, message = transition_status(
        Path(args.status_path),
        args.new_status,
        args.event,
        args.actor,
        extra=_safe_extra(args.extra_json),
        bump_round=args.bump_round,
    )
    if args.json:
        print(json.dumps({"ok": True, "message": message, "status": data}, ensure_ascii=False, indent=2))
    else:
        print(message)


if __name__ == "__main__":
    main()
