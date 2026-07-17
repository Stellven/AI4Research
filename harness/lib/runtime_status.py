"""Solar Harness — runtime-backed status transitions.

This is the P1 adoption layer for coordinator state changes. It keeps the
legacy `sprints/<sid>.status.json` cache for compatibility, but every transition
also emits a v2 session-log state transition through ActivityRuntime.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

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
TERMINAL_SPRINT_STATUSES = {"passed", "completed", "eval_passed", "failed", "cancelled", "archived", "skipped", "superseded"}


def _is_epic_child(data: Dict[str, Any]) -> bool:
    return bool(data.get("epic_id")) or str(data.get("dependency_policy") or "") == "activated_by_epic_dag"


def _canonicalize_transition(
    data: Dict[str, Any],
    new_status: str,
    status_fields: Dict[str, Any],
) -> tuple[str, Dict[str, Any]]:
    """Normalize legacy status writes into the current workflow semantics.

    The main legacy hazard is planner-ready epic children being written as
    `drafting + prd_ready + planner`, which makes the epic DAG repeatedly
    "activate" the same child and starves real planner throughput.
    """
    normalized_status = str(new_status or "")
    normalized_fields = dict(status_fields or {})
    phase = str(normalized_fields.get("phase") or data.get("phase") or "")
    handoff_to = str(normalized_fields.get("handoff_to") or data.get("handoff_to") or "")
    target_role = str(normalized_fields.get("target_role") or data.get("target_role") or "")

    if (
        normalized_status == "drafting"
        and phase == "prd_ready"
        and (handoff_to == "planner" or target_role == "planner")
        and _is_epic_child(data)
    ):
        normalized_status = "active"

    return normalized_status, normalized_fields


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_terminal_sprint_status(status: str) -> bool:
    return str(status or "").lower() in TERMINAL_SPRINT_STATUSES


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
        return os.path.expanduser(
            os.environ.get("HARNESS_DIR")
            or os.environ.get("SOLAR_HARNESS_DIR")
            or "~/.solar/harness"
        )


@contextlib.contextmanager
def status_write_lock(status_path: Path) -> Iterator[None]:
    """Serialize read-modify-write cycles on <sid>.status.json.

    Both status writers take this lock (transition_status here, the
    plan-compile bounce mirror in plan_validator — G2b review finding 4:
    the bounce mirror's full-object write could revert a transition that
    landed between its read and its write). The sidecar lock file survives
    os.replace of the status file itself, which the file's own inode would
    not. Degrades to unlocked (legacy behavior) if the lock file cannot be
    created or flocked, so a read-only or exotic filesystem never blocks a
    status write.
    """
    lock_path = Path(status_path).expanduser()
    lock_path = lock_path.with_name(lock_path.name + ".lock")
    handle = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "w", encoding="utf-8")
        fcntl.flock(handle, fcntl.LOCK_EX)
    except Exception:
        if handle is not None:
            with contextlib.suppress(Exception):
                handle.close()
        handle = None
    try:
        yield
    finally:
        if handle is not None:
            with contextlib.suppress(Exception):
                fcntl.flock(handle, fcntl.LOCK_UN)
            with contextlib.suppress(Exception):
                handle.close()


def merge_status_fields(status_path: Path, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Locked metadata merge: set the given top-level keys on the FRESHEST
    status object without touching status/phase/routing. This is the write
    path for bookkeeping mirrors (e.g. plan_compile_bounces) that must never
    clobber a concurrent transition with a stale full-object write."""
    status_path = Path(status_path).expanduser()
    with status_write_lock(status_path):
        with status_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"sprint status is not an object: {status_path}")
        data.update(fields)
        fd, tmp = tempfile.mkstemp(dir=str(status_path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, status_path)
        return data


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

    with status_write_lock(status_path):
        return _transition_status_locked(
            status_path, new_status, event, actor, extra=extra, bump_round=bump_round
        )


def _transition_status_locked(
    status_path: Path,
    new_status: str,
    event: str,
    actor: str,
    *,
    extra: Dict[str, Any],
    bump_round: bool,
) -> Tuple[Dict[str, Any], str]:
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

    new_status, status_fields = _canonicalize_transition(data, new_status, status_fields)
    allow_reopen = bool(extra.pop("allow_reopen", False))
    sticky_terminal = _is_terminal_sprint_status(old_status) and not _is_terminal_sprint_status(new_status)
    if sticky_terminal and not allow_reopen:
        hist: Dict[str, Any] = {
            "ts": now,
            "event": event,
            "by": actor,
            "note": "terminal_status_sticky: attempted downgrade ignored",
            "attempted_status": new_status,
        }
        if bump_round:
            hist["round"] = new_round
        hist.update(extra)
        data["updated_at"] = now
        data["runtime_state_source"] = "activity_runtime"
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
            to_status=old_status,
            round_num=new_round,
            correlation_id=f"status:{sid}:{event}:{now}",
        )
        return data, (
            f"OK: {sid} preserved terminal status {old_status}; "
            f"ignored attempted downgrade to {new_status} (round={new_round})"
        )

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
