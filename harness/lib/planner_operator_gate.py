#!/usr/bin/env python3
"""Solar-owned completion gate for Planner operator artifacts.

Planner files are only a candidate plan while the bounded model invocation is
still running.  This module binds plan certification to the durable operator
result so a partially written design/plan/task graph cannot be certified.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Any


SUCCESS_STATUSES = {"completed", "succeeded", "success", "passed"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _durable_result(harness: Path, task_id: str) -> tuple[Path | None, dict[str, Any]]:
    candidates = sorted(
        (harness / "run" / "operator-results").glob(f"*/{task_id}/result.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        reverse=True,
    )
    if not candidates:
        return None, {}
    return candidates[0], _read_json(candidates[0])


def _result_succeeded(result: dict[str, Any]) -> bool:
    result_status = str(result.get("status") or "").strip().lower()
    try:
        exit_code = int(result.get("exit_code"))
    except (TypeError, ValueError):
        exit_code = None
    return result_status in SUCCESS_STATUSES and exit_code == 0


def planner_operator_state(harness_dir: Path, sid: str, node_id: str = "N0") -> dict[str, Any]:
    """Return the durable completion state for the current Planner task.

    ``unmanaged`` preserves the legacy pane path.  Once a PM/operator-pool
    record exists, only an explicit successful result unlocks certification.
    """
    harness = Path(harness_dir)
    prefix = f"pm-{sid}-{node_id}-"
    inbox_root = harness / "run" / "pm-inbox"
    records: list[tuple[float, str, Path, dict[str, Any]]] = []
    for path in inbox_root.glob(f"{prefix}*.json"):
        payload = _read_json(path)
        task_id = str(payload.get("task_id") or path.stem)
        if str(payload.get("requested_role") or "planner") != "planner":
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        records.append((mtime, task_id, path, payload))

    if not records:
        return {
            "state": "unmanaged",
            "ready_for_compile": True,
            "sid": sid,
            "node_id": node_id,
            "task_id": "",
            "reason": "no_operator_pool_planner_task",
        }

    status = _read_json(harness / "sprints" / f"{sid}.status.json")
    claim = status.get("planner_dispatch_claim")
    claimed_task = str(claim.get("task_id") or "") if isinstance(claim, dict) else ""
    selected = next((row for row in records if row[1] == claimed_task), None)
    if selected is None:
        selected = max(records, key=lambda row: row[0])
    else:
        # A claim pins the intended Planner invocation while it is live.  Once
        # that invocation has a durable unsuccessful result, however, Solar may
        # submit a newer bounded retry.  Do not keep selecting the dead claimed
        # task forever merely because its claim metadata survived a restart.
        newest = max(records, key=lambda row: row[0])
        if newest[1] != selected[1]:
            _claimed_result_path, claimed_result = _durable_result(harness, selected[1])
            if claimed_result and not _result_succeeded(claimed_result):
                selected = newest
    _mtime, task_id, inbox_path, inbox = selected

    result_path, result = _durable_result(harness, task_id)

    if result:
        result_status = str(result.get("status") or "").strip().lower()
        try:
            exit_code = int(result.get("exit_code"))
        except (TypeError, ValueError):
            exit_code = None
        succeeded = _result_succeeded(result)
        return {
            "state": "completed" if succeeded else "failed",
            "ready_for_compile": succeeded,
            "sid": sid,
            "node_id": node_id,
            "task_id": task_id,
            "reason": "durable_operator_result_succeeded" if succeeded else "durable_operator_result_failed",
            "result_status": result_status,
            "exit_code": exit_code,
            "inbox_path": str(inbox_path),
            "result_path": str(result_path),
        }

    inbox_status = str(inbox.get("status") or "").strip().lower()
    if inbox_status.startswith("failed") or inbox_status == "cancelled":
        # Selection/submit failures happen before an operatord process exists,
        # so there will never be a durable operator result to release the
        # claim. Treat the durable PM inbox terminal state as immediate retry
        # authority instead of waiting for the full claim TTL.
        return {
            "state": "failed",
            "ready_for_compile": False,
            "sid": sid,
            "node_id": node_id,
            "task_id": task_id,
            "reason": "planner_submission_failed_before_lease",
            "inbox_status": inbox_status,
            "inbox_path": str(inbox_path),
            "result_path": "",
        }

    runtime_state = ""
    heartbeat_at = ""
    for path in (harness / "run" / "operator-status").glob("*.json"):
        payload = _read_json(path)
        current_task = str(payload.get("current_task_id") or payload.get("task_id") or "")
        if current_task == task_id:
            runtime_state = str(payload.get("runtime_state") or payload.get("state") or "").lower()
            heartbeat_at = str(payload.get("heartbeat_at") or payload.get("updated_at") or "")
            break
    try:
        heartbeat = datetime.datetime.fromisoformat(heartbeat_at.replace("Z", "+00:00"))
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=datetime.timezone.utc)
        age_seconds = (datetime.datetime.now(datetime.timezone.utc) - heartbeat).total_seconds()
    except (TypeError, ValueError):
        age_seconds = None
    try:
        stale_seconds = max(15, int(os.environ.get("SOLAR_PM_OPERATOR_HEARTBEAT_STALE_SEC", "90")))
    except (TypeError, ValueError):
        stale_seconds = 90
    active = (
        runtime_state in {"leased", "running", "draining", "busy"}
        and age_seconds is not None
        and age_seconds <= stale_seconds
    )
    claim_expired = False
    if isinstance(claim, dict):
        try:
            expires = datetime.datetime.fromisoformat(str(claim.get("expires_at") or "").replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            claim_expired = expires <= datetime.datetime.now(datetime.timezone.utc)
        except (TypeError, ValueError):
            claim_expired = False
    abandoned = not active and claim_expired
    return {
        "state": "running" if active else "abandoned" if abandoned else "pending",
        "ready_for_compile": False,
        "sid": sid,
        "node_id": node_id,
        "task_id": task_id,
        "reason": (
            "planner_operator_still_running"
            if active
            else "planner_operator_claim_abandoned"
            if abandoned
            else "planner_operator_result_pending"
        ),
        "runtime_state": runtime_state,
        "heartbeat_age_seconds": age_seconds,
        "inbox_status": inbox_status,
        "inbox_path": str(inbox_path),
        "result_path": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", choices=["state"])
    parser.add_argument("sid")
    parser.add_argument("--harness-dir", required=True)
    parser.add_argument("--node-id", default="N0")
    parser.add_argument("--field", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = planner_operator_state(Path(args.harness_dir), args.sid, args.node_id)
    if args.field:
        value: Any = payload
        for part in args.field.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        print("" if value is None else str(value).lower() if isinstance(value, bool) else value)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.json else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
