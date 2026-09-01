#!/usr/bin/env python3
"""Durable control-plane seam for the native Elastic Planner.

The planner worker owns only ``<sprint>/elastic-planner/{semantic,execution}``
and its result receipt.  This module is the deterministic publisher: it verifies
those artifacts, then either publishes one terminal direct answer or projects
the accepted frozen SchedulerInput into the existing runtime graph.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from elastic_planner import verify_frozen_execution_chain, verify_semantic_planning_chain
from planner_failure import read_planner_failure
from runtime_status import merge_status_fields, transition_status
from scheduler_input import prepare_runtime_graph
import file_lock_compat as fcntl


OWNER_SCHEMA = "solar.elastic_planner_owner.v1"
RESULT_SCHEMA = "solar.elastic_planner_operator_result.v1"
FINALIZATION_SCHEMA = "solar.elastic_planner_finalization.v1"
FAILURE_SCHEMA = "solar.elastic_planner_failure.v1"
RETRYABLE_FAILURE_STATUSES = frozenset(
    {
        "failed_backpressure",
        "failed_capacity",
        "failed_no_dispatchable_operator",
        "failed_operator_alternatives_exhausted",
        "failed_operator_busy",
    }
)


class ElasticPlannerRuntimeError(RuntimeError):
    """The Planner result cannot safely become runtime authority."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ElasticPlannerRuntimeError(f"JSON_UNREADABLE:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise ElasticPlannerRuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _validated_sprint_id(value: str) -> str:
    sprint_id = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,191}", sprint_id):
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_SPRINT_ID_INVALID")
    return sprint_id


def _confined(path: Path, root: Path, error: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ElasticPlannerRuntimeError(error) from exc
    return resolved


def elastic_planner_root(sprints_dir: Path, sprint_id: str) -> Path:
    return Path(sprints_dir) / _validated_sprint_id(sprint_id) / "elastic-planner"


def owner_path(sprints_dir: Path, sprint_id: str) -> Path:
    return elastic_planner_root(sprints_dir, sprint_id) / "owner.json"


def operator_result_path(sprints_dir: Path, sprint_id: str) -> Path:
    return elastic_planner_root(sprints_dir, sprint_id) / "planner_operator_result.json"


def planner_failure_retryable(status: str) -> bool:
    """Return true only for explicit capacity/backpressure failure states."""
    return str(status or "").strip().lower() in RETRYABLE_FAILURE_STATUSES


def _planner_failure_path(sprints_dir: Path, sprint_id: str, task_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,191}", str(task_id or "")):
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_TASK_ID_INVALID")
    return elastic_planner_root(sprints_dir, sprint_id) / f"failure-{task_id}.json"


def project_planner_failure(
    sprints_dir: Path,
    sprint_id: str,
    *,
    task_id: str,
    failure_status: str,
    failure_reason: str,
    record_path: Path | None = None,
    record_root: Path | None = None,
) -> dict[str, Any]:
    """Project one typed Planner failure under the finalization lock.

    Only the task currently named by the owner may change sprint state. A
    later retry therefore makes replays from an older task harmless.
    """
    sprint_id = _validated_sprint_id(sprint_id)
    sprints_dir = Path(sprints_dir).expanduser().resolve()
    lock_path = elastic_planner_root(sprints_dir, sprint_id) / "finalization.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        try:
            return _project_planner_failure_locked(
                sprints_dir,
                sprint_id,
                task_id=str(task_id or "").strip(),
                failure_status=str(failure_status or "failed").strip().lower(),
                failure_reason=str(failure_reason or failure_status or "failed").strip(),
                record_path=record_path,
                record_root=record_root,
            )
        finally:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)


def _project_planner_failure_locked(
    sprints_dir: Path,
    sprint_id: str,
    *,
    task_id: str,
    failure_status: str,
    failure_reason: str,
    record_path: Path | None,
    record_root: Path | None,
) -> dict[str, Any]:
    owner_file = owner_path(sprints_dir, sprint_id)
    owner = _read_object(owner_file)
    if owner.get("schema_version") != OWNER_SCHEMA or owner.get("sprint_id") != sprint_id:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_OWNER_INVALID")
    current_task_id = str(owner.get("planner_task_id") or "").strip()
    if current_task_id != task_id:
        return {
            "schema_version": FAILURE_SCHEMA,
            "sprint_id": sprint_id,
            "task_id": task_id,
            "projected": False,
            "reason": "stale_planner_attempt",
            "current_task_id": current_task_id,
        }
    finalization_path = elastic_planner_root(sprints_dir, sprint_id) / "finalization.json"
    if finalization_path.exists() or owner.get("state") == "finalized":
        return {
            "schema_version": FAILURE_SCHEMA,
            "sprint_id": sprint_id,
            "task_id": task_id,
            "projected": False,
            "reason": "success_already_finalized",
        }
    retryable = planner_failure_retryable(failure_status)
    record_ref: dict[str, str] | None = None
    if record_path is not None:
        if record_root is None:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_FAILURE_RECORD_ROOT_REQUIRED")
        resolved_record = _confined(
            Path(record_path),
            Path(record_root),
            "ELASTIC_PLANNER_FAILURE_RECORD_OUTSIDE_ROOT",
        )
        if resolved_record.name != f"{task_id}.json":
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_FAILURE_RECORD_NAME_MISMATCH")
        if not resolved_record.is_file():
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_FAILURE_RECORD_MISSING")
        persisted_record = _read_object(resolved_record)
        if (
            str(persisted_record.get("task_id") or "") != task_id
            or str(persisted_record.get("sprint_id") or "") != sprint_id
            or str(persisted_record.get("status") or "").strip().lower()
            != failure_status
            or str(persisted_record.get("closeout_kind") or "") != "elastic_planner"
        ):
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_FAILURE_RECORD_IDENTITY_MISMATCH")
        record_ref = {"path": str(resolved_record), "sha256": _sha256(resolved_record)}
    receipt_path = _planner_failure_path(sprints_dir, sprint_id, task_id)
    failed_at = str((owner.get("failure") or {}).get("failed_at") or _now())
    error: dict[str, Any] = {
        "code": failure_status,
        "detail": failure_reason[:2000],
        "stage": "pm_dispatch",
        "retry_safe": retryable,
        "node_id": None,
        "before_execution": True,
    }
    typed = read_planner_failure(elastic_planner_root(sprints_dir, sprint_id))
    if typed is not None:
        error.update(
            {
                "code": str(typed.get("code") or failure_status),
                "detail": str(typed.get("detail") or failure_reason)[:2000],
                "stage": str(typed.get("stage") or "unknown"),
                "retry_safe": bool(typed.get("retry_safe", False)) or retryable,
                "node_id": typed.get("node_id"),
                "receipt_ref": typed.get("receipt_ref"),
            }
        )
        # PM closeout may only know the generic terminal word ``failed``.
        # The stage-local typed receipt is the authoritative source for
        # whether a retry is safe (for example a provider-capacity refusal
        # before execution).  Preserve that distinction in control-plane
        # state instead of making a safe Planner retry permanently terminal.
        retryable = retryable or bool(error.get("retry_safe"))
    failure = {
        "task_id": task_id,
        "status": failure_status,
        "error": error,
        "record_ref": record_ref,
        "retryable": retryable,
        "failed_at": failed_at,
    }
    receipt = {
        "schema_version": FAILURE_SCHEMA,
        "artifact_role": "control_plane_receipt",
        "sprint_id": sprint_id,
        "task_id": task_id,
        "projected": True,
        "failure": failure,
    }
    if receipt_path.exists():
        existing = _read_object(receipt_path)
        if existing != receipt:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_FAILURE_RECEIPT_CONFLICT")
    else:
        _atomic_json(receipt_path, receipt)

    status_path = sprints_dir / f"{sprint_id}.status.json"
    if not status_path.exists():
        initialize_status(sprints_dir, sprint_id, str(owner.get("intent_id") or ""))
    if not retryable:
        current_status = _read_object(status_path)
        already_failed = bool(
            str(current_status.get("status") or "").lower() == "failed"
            and str(current_status.get("phase") or "") == "elastic_planner_failed"
            and str((current_status.get("elastic_planner_failure") or {}).get("task_id") or "")
            == task_id
        )
        if not already_failed:
            transition_status(
                status_path,
                "failed",
                "elastic_planner_failed",
                "pm_dispatch",
                extra={
                    "status_fields": {
                        "phase": "elastic_planner_failed",
                        "handoff_to": "",
                        "target_role": "",
                    }
                },
            )
    merge_status_fields(
        status_path,
        {
            "elastic_planner_failure": failure,
            "elastic_planner_failure_ref": {
                "path": str(receipt_path),
                "sha256": _sha256(receipt_path),
            },
        },
    )
    owner.update(
        {
            "state": "retryable_failure" if retryable else "failed",
            "failure": failure,
            "failure_ref": {"path": str(receipt_path), "sha256": _sha256(receipt_path)},
            "updated_at": _now(),
        }
    )
    _atomic_json(owner_file, owner)
    return receipt


def frozen_scheduler_authority(sprints_dir: Path, sprint_id: str) -> dict[str, Any]:
    """Return the exact verified Elastic-owned scheduler authority, if any."""
    errors: list[str] = []
    try:
        sprint_id = _validated_sprint_id(sprint_id)
        sprints_dir = Path(sprints_dir).expanduser().resolve()
        root = elastic_planner_root(sprints_dir, sprint_id)
        expected_owner = owner_path(sprints_dir, sprint_id).resolve()
        expected_result = operator_result_path(sprints_dir, sprint_id).resolve()
        expected_finalization = (root / "finalization.json").resolve()
        expected_graph = (sprints_dir / f"{sprint_id}.task_graph.json").resolve()
        status_path = sprints_dir / f"{sprint_id}.status.json"
        owner = _read_object(expected_owner)
        status = _read_object(status_path)
        finalization = _read_object(expected_finalization)
        result = _read_object(expected_result)
        if (
            owner.get("schema_version") != OWNER_SCHEMA
            or owner.get("sprint_id") != sprint_id
            or owner.get("state") != "finalized"
            or str(owner.get("finalization_ref") or "") != str(expected_finalization)
        ):
            errors.append("ELASTIC_PLANNER_OWNER_NOT_FINALIZED")
        if (
            finalization.get("schema_version") != FINALIZATION_SCHEMA
            or finalization.get("sprint_id") != sprint_id
            or (finalization.get("published") or {}).get("kind") != "accepted"
            or str((finalization.get("published") or {}).get("graph") or "")
            != str(expected_graph)
            or finalization.get("operator_result_ref")
            != {"path": str(expected_result), "sha256": _sha256(expected_result)}
        ):
            errors.append("ELASTIC_PLANNER_FINALIZATION_NOT_ACCEPTED")
        requirement_path = Path(
            str((owner.get("requirement_ir_ref") or {}).get("path") or "")
        ).expanduser().resolve()
        if requirement_path != (sprints_dir / f"{sprint_id}.requirement_ir.json").resolve():
            errors.append("ELASTIC_PLANNER_REQUIREMENT_PATH_NOT_CANONICAL")
        _verify_operator_result(
            expected_result,
            sprint_id=sprint_id,
            requirement_ir_path=requirement_path,
            output_root=root,
        )
        if result.get("status") != "accepted":
            errors.append("ELASTIC_PLANNER_RESULT_NOT_ACCEPTED")
        chain_errors = verify_frozen_execution_chain(root / "semantic", root / "execution")
        errors.extend(f"ELASTIC_PLANNER_CHAIN:{item}" for item in chain_errors)
        if (
            status.get("execution_mode") != "frozen_scheduler_input"
            or str(status.get("task_graph_ref") or "") != str(expected_graph)
            or str(status.get("elastic_planner_owner_ref") or "") != str(expected_owner)
            or str(status.get("phase") or "") not in {"planning_complete", "graph_dispatch_active"}
        ):
            errors.append("ELASTIC_PLANNER_STATUS_NOT_FROZEN_SCHEDULER")
        from scheduler_input import verify_runtime_pair

        pair = verify_runtime_pair(expected_graph)
        errors.extend(str(item) for item in pair.get("errors") or [])
    except (ElasticPlannerRuntimeError, OSError, ValueError) as exc:
        errors.append(str(exc))
        pair = {}
        expected_graph = Path(sprints_dir) / f"{sprint_id}.task_graph.json"
    return {
        "ok": not errors,
        "errors": errors,
        "sprint_id": sprint_id,
        "graph_path": str(expected_graph),
        "state_path": str(pair.get("state_path") or ""),
    }


def dispatch_frozen_scheduler_graph(
    sprints_dir: Path,
    sprint_id: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Hand an admitted frozen graph to the existing graph dispatcher."""
    authority = frozen_scheduler_authority(sprints_dir, sprint_id)
    if not authority.get("ok"):
        raise ElasticPlannerRuntimeError(
            "ELASTIC_PLANNER_SCHEDULER_AUTHORITY_INVALID:"
            + ",".join(str(item) for item in authority.get("errors") or [])
        )
    import graph_node_dispatcher

    dispatch = graph_node_dispatcher.dispatch_ready(
        str(authority["graph_path"]),
        dry_run=dry_run,
        ttl=900,
    )
    return {"authority": authority, "dispatch": dispatch}


def claim_owner(
    sprints_dir: Path,
    sprint_id: str,
    intent_id: str,
    requirement_ir_path: Path,
    *,
    workspace_authority_path: Path | None = None,
    workspace_binding_harness_dir: Path | None = None,
) -> dict[str, Any]:
    """Atomically claim a sprint before any legacy compiler can publish a graph."""
    sprint_id = _validated_sprint_id(sprint_id)
    sprints_dir = Path(sprints_dir).expanduser().resolve()
    requirement_ir_path = _confined(
        requirement_ir_path,
        sprints_dir,
        "ELASTIC_PLANNER_REQUIREMENT_PATH_OUTSIDE_SPRINTS",
    )
    canonical_requirement = (sprints_dir / f"{sprint_id}.requirement_ir.json").resolve()
    if requirement_ir_path != canonical_requirement:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_REQUIREMENT_PATH_NOT_CANONICAL")
    workspace_authority_ref: dict[str, Any] | None = None
    if workspace_authority_path is not None:
        if workspace_binding_harness_dir is None:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_WORKSPACE_BINDING_HARNESS_MISSING")
        from workspace_binding import verify_sprint_workspace_authority

        canonical_authority = (sprints_dir / f"{sprint_id}.workspace_authority.json").resolve()
        authority_path = _confined(
            workspace_authority_path,
            sprints_dir,
            "ELASTIC_PLANNER_WORKSPACE_AUTHORITY_OUTSIDE_SPRINTS",
        )
        if authority_path != canonical_authority:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_WORKSPACE_AUTHORITY_NOT_CANONICAL")
        authority = verify_sprint_workspace_authority(
            authority_path,
            sprints_dir=sprints_dir,
            harness_dir=workspace_binding_harness_dir,
            require_active_binding=False,
        )
        workspace_authority_ref = {
            "path": str(authority_path),
            "sha256": _sha256(authority_path),
            "workspace_root": str(authority.get("workspace_root") or ""),
            "binding_harness_dir": str(Path(workspace_binding_harness_dir).expanduser().resolve()),
        }
    expected = {
        "schema_version": OWNER_SCHEMA,
        "artifact_role": "control_plane_receipt",
        "sprint_id": sprint_id,
        "intent_id": intent_id,
        "requirement_ir_ref": {
            "path": str(requirement_ir_path),
            "sha256": _sha256(requirement_ir_path),
        },
        "workspace_authority_ref": workspace_authority_ref,
        "state": "claimed",
        "created_at": _now(),
        "planner_task_id": None,
    }
    path = owner_path(sprints_dir, sprint_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = _read_object(path)
        stable = {
            "schema_version": existing.get("schema_version"),
            "sprint_id": existing.get("sprint_id"),
            "intent_id": existing.get("intent_id"),
            "requirement_ir_ref": existing.get("requirement_ir_ref"),
            "workspace_authority_ref": existing.get("workspace_authority_ref"),
        }
        wanted = {
            "schema_version": expected["schema_version"],
            "sprint_id": sprint_id,
            "intent_id": intent_id,
            "requirement_ir_ref": expected["requirement_ir_ref"],
            "workspace_authority_ref": expected["workspace_authority_ref"],
        }
        if stable != wanted:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_OWNER_CONFLICT")
        return existing
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(expected, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return expected


def update_owner(sprints_dir: Path, sprint_id: str, **fields: Any) -> dict[str, Any]:
    path = owner_path(sprints_dir, sprint_id)
    value = _read_object(path)
    value.update(fields)
    value["updated_at"] = _now()
    _atomic_json(path, value)
    return value


def initialize_status(
    sprints_dir: Path,
    sprint_id: str,
    intent_id: str,
    *,
    title: str = "",
) -> Path:
    """Create the minimum dashboard-visible status without a provisional DAG."""
    path = Path(sprints_dir) / f"{sprint_id}.status.json"
    if path.exists():
        current = _read_object(path)
        if str(current.get("elastic_planner_owner_ref") or "") != str(owner_path(sprints_dir, sprint_id)):
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_STATUS_OWNER_CONFLICT")
        return path
    now = _now()
    _atomic_json(
        path,
        {
            "id": sprint_id,
            "sprint_id": sprint_id,
            "title": (str(title or "").strip() or "Planning request")[:120],
            "summary": "Elastic Planner is selecting a direct answer or a frozen execution plan.",
            "created_at": now,
            "updated_at": now,
            "round": 0,
            "status": "active",
            "phase": "elastic_planning",
            "handoff_to": "elastic_planner",
            "target_role": "elastic_planner",
            "intent_id": intent_id,
            "execution_mode": "elastic_planner",
            "elastic_planner_owner_ref": str(owner_path(sprints_dir, sprint_id)),
            "history": [{"ts": now, "event": "elastic_planner_claimed", "by": "intent_consumer"}],
        },
    )
    return path


def _verify_operator_result(
    result_path: Path,
    *,
    sprint_id: str,
    requirement_ir_path: Path,
    output_root: Path,
    workspace_authority_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _read_object(result_path)
    if result.get("schema_version") != RESULT_SCHEMA:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_RESULT_SCHEMA_INVALID")
    if str(result.get("sprint_id") or "") != sprint_id:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_RESULT_SPRINT_MISMATCH")
    requirement_ref = result.get("requirement_ir_ref") if isinstance(result.get("requirement_ir_ref"), dict) else {}
    if requirement_ref != {"path": str(requirement_ir_path.resolve()), "sha256": _sha256(requirement_ir_path)}:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_RESULT_REQUIREMENT_MISMATCH")
    if str(result.get("output_root") or "") != str(output_root.resolve()):
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_RESULT_ROOT_MISMATCH")
    if result.get("verification_errors"):
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_RESULT_REPORTED_VERIFICATION_ERRORS")
    if workspace_authority_ref is not None:
        expected = {
            "path": str(workspace_authority_ref["path"]),
            "sha256": str(workspace_authority_ref["sha256"]),
            "workspace_root": str(workspace_authority_ref["workspace_root"]),
        }
        if result.get("workspace_authority_ref") != expected:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_RESULT_WORKSPACE_AUTHORITY_MISMATCH")
    return result


def finalize_planner_result(
    sprints_dir: Path,
    sprint_id: str,
    *,
    result_path: Path | None = None,
) -> dict[str, Any]:
    """Serialize verification and publication for one sprint."""
    sprint_id = _validated_sprint_id(sprint_id)
    sprints_dir = Path(sprints_dir).expanduser().resolve()
    lock_path = elastic_planner_root(sprints_dir, sprint_id) / "finalization.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        try:
            return _finalize_planner_result_locked(
                sprints_dir,
                sprint_id,
                result_path=result_path,
            )
        finally:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)


def _finalize_planner_result_locked(
    sprints_dir: Path,
    sprint_id: str,
    *,
    result_path: Path | None = None,
) -> dict[str, Any]:
    """Verify and publish a Planner result. Repeating this call is safe."""
    sprint_id = _validated_sprint_id(sprint_id)
    sprints_dir = Path(sprints_dir).expanduser().resolve()
    owner = _read_object(owner_path(sprints_dir, sprint_id))
    if owner.get("schema_version") != OWNER_SCHEMA or owner.get("sprint_id") != sprint_id:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_OWNER_INVALID")
    if owner.get("state") in {"failed", "retryable_failure"}:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_RESULT_AFTER_FAILURE")
    requirement_ir_path = _confined(
        Path(str((owner.get("requirement_ir_ref") or {}).get("path") or "")),
        sprints_dir,
        "ELASTIC_PLANNER_REQUIREMENT_PATH_OUTSIDE_SPRINTS",
    )
    canonical_requirement = (sprints_dir / f"{sprint_id}.requirement_ir.json").resolve()
    if requirement_ir_path != canonical_requirement:
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_REQUIREMENT_PATH_NOT_CANONICAL")
    if not requirement_ir_path.is_file() or _sha256(requirement_ir_path) != str((owner.get("requirement_ir_ref") or {}).get("sha256") or ""):
        raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_OWNER_REQUIREMENT_CHANGED")
    workspace_authority_ref = (
        owner.get("workspace_authority_ref")
        if isinstance(owner.get("workspace_authority_ref"), dict)
        else None
    )
    if workspace_authority_ref is not None:
        from workspace_binding import verify_sprint_workspace_authority

        authority_path = _confined(
            Path(str(workspace_authority_ref.get("path") or "")),
            sprints_dir,
            "ELASTIC_PLANNER_WORKSPACE_AUTHORITY_OUTSIDE_SPRINTS",
        )
        if authority_path != (sprints_dir / f"{sprint_id}.workspace_authority.json").resolve():
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_WORKSPACE_AUTHORITY_NOT_CANONICAL")
        if _sha256(authority_path) != str(workspace_authority_ref.get("sha256") or ""):
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_OWNER_WORKSPACE_AUTHORITY_CHANGED")
        try:
            verified_authority = verify_sprint_workspace_authority(
                authority_path,
                sprints_dir=sprints_dir,
                harness_dir=Path(str(workspace_authority_ref.get("binding_harness_dir") or "")),
                require_active_binding=False,
            )
        except ValueError as exc:
            raise ElasticPlannerRuntimeError(
                f"ELASTIC_PLANNER_OWNER_WORKSPACE_AUTHORITY_INVALID:{exc}"
            ) from exc
        if str(verified_authority.get("workspace_root") or "") != str(
            workspace_authority_ref.get("workspace_root") or ""
        ):
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_OWNER_WORKSPACE_ROOT_CHANGED")
    output_root = elastic_planner_root(sprints_dir, sprint_id)
    result_file = _confined(
        result_path or operator_result_path(sprints_dir, sprint_id),
        output_root,
        "ELASTIC_PLANNER_RESULT_PATH_OUTSIDE_OUTPUT_ROOT",
    )
    result = _verify_operator_result(
        result_file,
        sprint_id=sprint_id,
        requirement_ir_path=requirement_ir_path,
        output_root=output_root,
        workspace_authority_ref=workspace_authority_ref,
    )
    finalization_path = output_root / "finalization.json"
    status_path = sprints_dir / f"{sprint_id}.status.json"
    kind = str(result.get("status") or "")

    # A completed receipt is the idempotence boundary. Verify its immutable
    # input reference before returning; do not append duplicate status history
    # or recreate a runtime ledger on a repeated closeout/reconcile call.
    if finalization_path.exists():
        existing = _read_object(finalization_path)
        if (
            existing.get("schema_version") != FINALIZATION_SCHEMA
            or existing.get("sprint_id") != sprint_id
            or existing.get("operator_result_ref")
            != {"path": str(result_file), "sha256": _sha256(result_file)}
        ):
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_FINALIZATION_CONFLICT")
        return existing

    if kind == "direct_response":
        errors = verify_semantic_planning_chain(output_root / "semantic")
        if errors:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_DIRECT_CHAIN_INVALID:" + ",".join(errors))
        acceptance = _read_object(output_root / "semantic" / "plan_acceptance.json")
        response = _read_object(output_root / "semantic" / "direct_response.json")
        if acceptance.get("decision") != "direct_response" or acceptance.get("runtime_handoff_allowed") is not False:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_DIRECT_ACCEPTANCE_INVALID")
        answer = str(response.get("answer") or "").strip()
        if not answer:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_DIRECT_ANSWER_EMPTY")
        report_path = sprints_dir / f"{sprint_id}.direct-response-report.md"
        if report_path.exists() and report_path.read_text(encoding="utf-8") != answer + "\n":
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_DIRECT_REPORT_CONFLICT")
        _atomic_text(report_path, answer + "\n")
        if not status_path.exists():
            initialize_status(sprints_dir, sprint_id, str(owner.get("intent_id") or ""))
        current_status = _read_object(status_path)
        direct_already_transitioned = bool(
            str(current_status.get("status") or "").lower() in {"passed", "completed", "done"}
            and str(current_status.get("phase") or "") == "direct_response_complete"
        )
        if not direct_already_transitioned:
            transition_status(
                status_path,
                "passed",
                "elastic_planner_direct_response_published",
                "pm_dispatch",
                extra={
                    "status_fields": {"phase": "direct_response_complete", "handoff_to": "", "target_role": ""},
                },
            )
        merge_status_fields(
            status_path,
            {
                "execution_mode": "direct_response",
                "direct_response_ref": {"path": str(report_path), "sha256": _sha256(report_path)},
                "elastic_planner_result_ref": str(result_file),
            },
        )
        published = {"kind": kind, "report": str(report_path), "graph": None}
    elif kind == "accepted":
        errors = verify_frozen_execution_chain(output_root / "semantic", output_root / "execution")
        if errors:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_FROZEN_CHAIN_INVALID:" + ",".join(errors))
        acceptance = _read_object(output_root / "execution" / "plan_acceptance.json")
        if acceptance.get("decision") != "accepted" or acceptance.get("runtime_handoff_allowed") is not True:
            raise ElasticPlannerRuntimeError("ELASTIC_PLANNER_EXECUTION_ACCEPTANCE_INVALID")
        graph_path = prepare_runtime_graph(
            output_root / "execution" / "scheduler_input.json",
            sprints_dir,
            run_contract_path=output_root / "execution" / "run_contract.frozen.json",
            # ``requirement_ir.v1`` is the stable controller artifact identity
            # used by PlanIR/capsules.  The document's schema_version remains
            # independently validated inside the bound JSON document.
            artifact_bindings={"requirement_ir.v1": str(requirement_ir_path)},
        )
        if not status_path.exists():
            initialize_status(sprints_dir, sprint_id, str(owner.get("intent_id") or ""))
        current_status = _read_object(status_path)
        graph_already_transitioned = bool(
            str(current_status.get("status") or "").lower() == "active"
            and str(current_status.get("phase") or "") == "planning_complete"
            and str(current_status.get("handoff_to") or "") == "builder_main"
        )
        if not graph_already_transitioned:
            transition_status(
                status_path,
                "active",
                "elastic_planner_execution_published",
                "pm_dispatch",
                extra={
                    "status_fields": {"phase": "planning_complete", "handoff_to": "builder_main", "target_role": "builder_main"},
                },
            )
        merge_status_fields(
            status_path,
            {
                "execution_mode": "frozen_scheduler_input",
                "task_graph_ref": str(graph_path),
                "elastic_planner_result_ref": str(result_file),
            },
        )
        published = {"kind": kind, "report": None, "graph": str(graph_path)}
    else:
        raise ElasticPlannerRuntimeError(f"ELASTIC_PLANNER_RESULT_NOT_ADMITTED:{kind or 'missing'}")

    published_status = _read_object(status_path)
    publication_event = (
        "elastic_planner_direct_response_published"
        if kind == "direct_response"
        else "elastic_planner_execution_published"
    )
    finalized_at = next(
        (
            str(row.get("ts") or "")
            for row in reversed(published_status.get("history") or [])
            if isinstance(row, dict) and row.get("event") == publication_event
        ),
        "",
    ) or str(result.get("completed_at") or owner.get("updated_at") or _now())
    receipt = {
        "schema_version": FINALIZATION_SCHEMA,
        "artifact_role": "control_plane_receipt",
        "sprint_id": sprint_id,
        "operator_result_ref": {"path": str(result_file), "sha256": _sha256(result_file)},
        "published": published,
        "finalized_at": finalized_at,
    }
    _atomic_json(finalization_path, receipt)
    update_owner(sprints_dir, sprint_id, state="finalized", finalization_ref=str(finalization_path))
    return receipt
