#!/usr/bin/env python3
"""Solar-owned dispatcher for bounded Planner repair attempts.

The plan validator owns the bounce counter and terminal budget.  This module
turns a non-terminal rejection into exactly one new Planner operator task for
that bounce generation.  The Planner may repair candidate artifacts, but it
cannot certify the graph or mutate sprint lifecycle state.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


TASK_ID_RE = re.compile(r"task_id\s*=\s*(\S+)")
RETRY_COOLDOWN_SECONDS = 30


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _timestamp(value: dt.datetime | None = None) -> str:
    return (value or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _update_planner_claim(harness_dir: Path, sid: str, task_id: str, bounce_count: int) -> None:
    status_path = harness_dir / "sprints" / f"{sid}.status.json"
    status = _read_json(status_path)
    existing = status.get("planner_dispatch_claim")
    claim = dict(existing) if isinstance(existing, dict) else {}
    now = _now()
    claim.update(
        {
            "owner": "operator_pool",
            "source": "solar_plan_validator_bounce",
            "state": "submitted",
            "task_id": task_id,
            "planner_bounce_count": bounce_count,
            "submitted_at": _timestamp(now),
            "updated_at": _timestamp(now),
            "expires_at": _timestamp(now + dt.timedelta(minutes=30)),
        }
    )
    fields = {"planner_dispatch_claim": claim, "updated_at": _timestamp(now)}
    try:
        sys.path.insert(0, str(harness_dir / "lib"))
        from runtime_status import merge_status_fields  # type: ignore

        merge_status_fields(status_path, fields)
    except (ImportError, OSError, ValueError):
        # runtime_status uses fcntl on Unix.  Keep unit tests and exotic
        # filesystems functional while production takes the locked path.
        status.update(fields)
        _atomic_write_json(status_path, status)


def _existing_task_for_bounce(harness_dir: Path, sid: str, bounce_count: int) -> str:
    token = f"[Solar planner bounce {bounce_count}]"
    inbox = harness_dir / "run" / "pm-inbox"
    for path in inbox.glob(f"pm-{sid}-N0-*.json"):
        payload = _read_json(path)
        if token in str(payload.get("objective") or ""):
            return str(payload.get("task_id") or path.stem)
    return ""


def _claim_marker(marker: Path, sid: str, bounce_count: int, graph_hash: str) -> tuple[bool, dict[str, Any]]:
    marker.parent.mkdir(parents=True, exist_ok=True)
    prior = _read_json(marker)
    if prior:
        state = str(prior.get("state") or "")
        if state in {"submitting", "submitted"}:
            return False, prior
        if state == "failed":
            try:
                retry_at = dt.datetime.fromisoformat(str(prior.get("retry_at") or "").replace("Z", "+00:00"))
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=dt.timezone.utc)
                if retry_at > _now():
                    return False, prior
            except (TypeError, ValueError):
                pass
    claim = {
        "sid": sid,
        "bounce_count": bounce_count,
        "graph_hash": graph_hash,
        "state": "submitting",
        "claimed_at": _timestamp(),
    }
    _atomic_write_json(marker, claim)
    return True, claim


def dispatch_planner_bounce(harness_dir: Path, sid: str) -> dict[str, Any]:
    harness = Path(harness_dir)
    errors_path = harness / "sprints" / f"{sid}.plan-compile-errors.json"
    errors = _read_json(errors_path)
    bounce_count = int(errors.get("bounce_count") or 0)
    if bounce_count < 1 or bool(errors.get("exhausted")) or bool(errors.get("terminal")):
        return {
            "ok": False,
            "state": "refused",
            "reason": "planner_bounce_not_available",
            "bounce_count": bounce_count,
        }

    graph_hash = str(errors.get("graph_hash") or "")
    marker = harness / "run" / "planner-bounces" / f"{sid}.bounce-{bounce_count}.json"
    dispatch_lock = marker.with_name(marker.name + ".dispatch.lock")
    dispatch_lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(dispatch_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            lock_age = (_now().timestamp() - dispatch_lock.stat().st_mtime)
        except OSError:
            lock_age = 0
        if lock_age > 120:
            try:
                dispatch_lock.unlink()
            except OSError:
                pass
        return {
            "ok": True,
            "sid": sid,
            "bounce_count": bounce_count,
            "state": "submitting",
            "task_id": "",
            "dispatch": "concurrent_dispatch_inflight",
        }
    else:
        os.close(lock_fd)

    try:
        existing_task = _existing_task_for_bounce(harness, sid, bounce_count)
        if existing_task:
            _update_planner_claim(harness, sid, existing_task, bounce_count)
            payload = {
                "sid": sid,
                "bounce_count": bounce_count,
                "graph_hash": graph_hash,
                "state": "submitted",
                "task_id": existing_task,
                "recovered_at": _timestamp(),
            }
            _atomic_write_json(marker, payload)
            return {"ok": True, **payload, "dispatch": "recovered"}

        owned, prior = _claim_marker(marker, sid, bounce_count, graph_hash)
        if not owned:
            state = str(prior.get("state") or "")
            return {
                "ok": state in {"submitting", "submitted"},
                "sid": sid,
                "bounce_count": bounce_count,
                "state": state,
                "task_id": str(prior.get("task_id") or ""),
                "dispatch": "already_claimed",
                "retry_at": str(prior.get("retry_at") or ""),
            }

        objective = (
            f"[Solar planner bounce {bounce_count}] Solar plan validator rejected the candidate plan for {sid}. "
            f"Act only as the bounded Planner repair node. Read {errors_path}, the requirement IR, contract, "
            "PRD, design, plan, and task_graph for this Sprint. Repair only the reported validation errors. "
            "Preserve Solar-owned locked AutoSci topology and every locked node field exactly as compiled from "
            "the requirement IR. Do not run the plan compiler, do not create or alter a plan certificate, do not "
            "modify status.json or the Solar ledger, do not dispatch Builder or Evaluator, and do not perform the "
            "research task. Finish after writing the corrected design.md, plan.md, and task_graph.json candidates."
        )
        context = (
            f"source=solar_coordinator planner_bounce_count={bounce_count} "
            f"plan_compile_errors={errors_path} graph_hash={graph_hash}"
        )
        cmd = [
            sys.executable,
            str(harness / "tools" / "pm_dispatch.py"),
            "submit",
            "--role",
            "planner",
            "--objective",
            objective,
            "--sprint",
            sid,
            "--node",
            "N0",
            "--task-type",
            "planning",
            "--context",
            context,
        ]
        env = dict(os.environ)
        env.update(
            {
                "HARNESS_DIR": str(harness),
                "SOLAR_HARNESS_DIR": str(harness),
                "SOLAR_HARNESS_SPRINTS_DIR": str(harness / "sprints"),
                "SOLAR_PM_DISPATCH_ALLOW_DIRECT": "1",
            }
        )
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, env=env)
        except Exception as exc:
            proc = None
            failure = str(exc)
        else:
            failure = (proc.stderr or proc.stdout or "planner bounce dispatch failed")[-2000:]

        match = TASK_ID_RE.search(proc.stdout or "") if proc is not None else None
        if proc is None or proc.returncode != 0 or match is None:
            retry_at = _now() + dt.timedelta(seconds=RETRY_COOLDOWN_SECONDS)
            payload = {
                "sid": sid,
                "bounce_count": bounce_count,
                "graph_hash": graph_hash,
                "state": "failed",
                "failed_at": _timestamp(),
                "retry_at": _timestamp(retry_at),
                "reason": failure,
            }
            _atomic_write_json(marker, payload)
            return {"ok": False, **payload}

        task_id = match.group(1)
        payload = {
            "sid": sid,
            "bounce_count": bounce_count,
            "graph_hash": graph_hash,
            "state": "submitted",
            "task_id": task_id,
            "submitted_at": _timestamp(),
        }
        _atomic_write_json(marker, payload)
        _update_planner_claim(harness, sid, task_id, bounce_count)
        return {"ok": True, **payload, "dispatch": "new"}
    finally:
        try:
            dispatch_lock.unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dispatch", choices=["dispatch"])
    parser.add_argument("sid")
    parser.add_argument("--harness-dir", required=True)
    args = parser.parse_args()
    result = dispatch_planner_bounce(Path(args.harness_dir), args.sid)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
