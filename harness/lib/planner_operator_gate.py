#!/usr/bin/env python3
"""Solar-owned completion gate for bounded role-stage artifacts.

Role-stage files are only candidates while the bounded model invocation is
still running. This module binds downstream consumption to the durable
operator result so partially written artifacts cannot be consumed.
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


def operator_task_state(
    harness_dir: Path,
    sid: str,
    node_id: str = "N0",
    *,
    role: str = "planner",
    closeout_kind: str = "",
) -> dict[str, Any]:
    """Return the durable completion state for a bounded role-stage task.

    ``unmanaged`` preserves the legacy pane path.  Once a PM/operator-pool
    record exists, only an explicit successful result unlocks certification.
    """
    harness = Path(harness_dir)
    sprints_root = Path(
        os.environ.get("HARNESS_SPRINTS_DIR")
        or os.environ.get("SOLAR_SPRINTS_DIR")
        or harness / "sprints"
    ).expanduser()
    elastic_root = sprints_root / sid / "elastic-planner"
    elastic_owner = _read_json(elastic_root / "owner.json")
    elastic_finalization = _read_json(elastic_root / "finalization.json")
    elastic_result = _read_json(elastic_root / "planner_operator_result.json")
    if (
        elastic_owner.get("state") == "finalized"
        and elastic_finalization.get("schema_version")
        == "solar.elastic_planner_finalization.v1"
        and elastic_finalization.get("sprint_id") == sid
        and elastic_result.get("status") == "accepted"
        and elastic_result.get("sprint_id") == sid
    ):
        # Finalized Elastic Planner ownership is absorbing for the legacy
        # coordinator.  A later closeout/reporting failure must not launch an
        # N0 Planner that can overwrite the already frozen graph.
        return {
            "state": "completed",
            "ready_for_compile": False,
            "sid": sid,
            "node_id": "elastic-planner",
            "task_id": str(elastic_result.get("task_id") or ""),
            "reason": "elastic_planner_already_finalized",
            "finalization_path": str(elastic_root / "finalization.json"),
        }
    # Legacy Planner tasks use node ``N0`` while the native Elastic Planner
    # uses the explicit ``elastic-planner`` node/role.  Both are bounded
    # Planner operator tasks and must hold the same coordinator gate while
    # their durable result is pending.  Filtering only the legacy filename
    # made the native task look unmanaged, so the coordinator incorrectly
    # rolled an actively compiling sprint back to ``missing PRD``.
    prefix = f"pm-{sid}-"
    inbox_root = harness / "run" / "pm-inbox"
    records: list[tuple[float, str, Path, dict[str, Any]]] = []
    expected_role = str(role).strip().lower().replace("_", "-")
    expected_closeout = str(closeout_kind).strip().lower().replace("_", "-")
    for path in inbox_root.glob(f"{prefix}*.json"):
        payload = _read_json(path)
        task_id = str(payload.get("task_id") or path.stem)
        requested_role = str(payload.get("requested_role") or "planner").strip().lower().replace("_", "-")
        record_node_id = str(payload.get("node_id") or "").strip().lower().replace("_", "-")
        record_closeout = str(payload.get("closeout_kind") or "").strip().lower().replace("_", "-")
        normalized_task_id = task_id.lower().replace("_", "-")
        is_legacy_planner = requested_role == "planner" and (
            record_node_id == str(node_id).lower()
            or f"-{str(node_id).lower()}-" in normalized_task_id
        )
        is_elastic_planner = (
            requested_role == "elastic-planner"
            or record_node_id == "elastic-planner"
            or record_closeout == "elastic-planner"
        )
        role_matches = (
            is_legacy_planner or is_elastic_planner
            if expected_role == "planner"
            else requested_role == expected_role
        )
        if not role_matches:
            continue
        if expected_closeout and record_closeout != expected_closeout:
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
            "reason": f"no_operator_pool_{closeout_kind or role}_task",
        }

    status = _read_json(sprints_root / f"{sid}.status.json")
    claim = status.get("planner_dispatch_claim") if role == "planner" else None
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
            "reason": f"{closeout_kind or role}_submission_failed_before_lease",
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
            f"{closeout_kind or role}_operator_still_running"
            if active
            else f"{closeout_kind or role}_operator_claim_abandoned"
            if abandoned
            else f"{closeout_kind or role}_operator_result_pending"
        ),
        "runtime_state": runtime_state,
        "heartbeat_age_seconds": age_seconds,
        "inbox_status": inbox_status,
        "inbox_path": str(inbox_path),
        "result_path": "",
    }


def planner_operator_state(harness_dir: Path, sid: str, node_id: str = "N0") -> dict[str, Any]:
    """Backward-compatible Planner wrapper used by existing callers/tests."""
    return operator_task_state(harness_dir, sid, node_id, role="planner")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", choices=["state"])
    parser.add_argument("sid")
    parser.add_argument("--harness-dir", required=True)
    parser.add_argument("--node-id", default="N0")
    parser.add_argument("--role", default="planner")
    parser.add_argument("--closeout-kind", default="")
    parser.add_argument("--field", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = operator_task_state(
        Path(args.harness_dir),
        args.sid,
        args.node_id,
        role=args.role,
        closeout_kind=args.closeout_kind,
    )
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
