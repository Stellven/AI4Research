#!/usr/bin/env python3
"""Canonical lifecycle contract for one dispatched multi-task attempt.

Graph-node states and physical-operator states are deliberately separate state
machines.  This module owns only the durable task-attempt vocabulary shared by
``multi_task_runner`` and ``route_proof`` and the exact-result correlation used
when operatord closes an attempt.
"""
from __future__ import annotations

import datetime
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


ACTIVE_TASK_STATUSES = frozenset(
    {
        "assigned",
        "dispatched",
        "in_progress",
        "leased",
        "pending",
        "processing",
        "queued",
        "result_timeout",
        "running",
        "started",
        "submitted",
        "submitted_fallback",
    }
)

TERMINAL_TASK_STATUSES = frozenset(
    {
        "cancelled",
        "completed",
        "error",
        "failed",
        "failed_contract_closeout",
        "failed_launch",
        "failed_missing_handoff",
        "failed_stale_handoff",
        "submit_rejected",
    }
)

EFFECTIVE_TERMINAL_TASK_STATUSES = frozenset(
    {*TERMINAL_TASK_STATUSES, "completed_aligned", "failed_aligned"}
)

NODE_ATTEMPT_SCHEMA_VERSION = "solar.node_attempt.v1"
NODE_ATTEMPT_ERROR_SCHEMA_VERSION = "solar.node_attempt_error.v1"
NODE_ATTEMPT_HISTORY_LIMIT = 20


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def execution_attempt_validation_error(node: dict[str, Any]) -> str:
    """Return why a declared canonical attempt is unusable, or ``""``."""
    activation_error = node.get("execution_attempt_error")
    if activation_error:
        if not isinstance(activation_error, dict):
            return "execution_attempt_error_not_object"
        return str(activation_error.get("reason") or "execution_attempt_activation_failed")
    if "execution_attempt" not in node:
        return ""
    attempt = node.get("execution_attempt")
    if not isinstance(attempt, dict):
        return "execution_attempt_not_object"
    if str(attempt.get("schema_version") or "") != NODE_ATTEMPT_SCHEMA_VERSION:
        return "execution_attempt_schema_invalid"
    if str(attempt.get("phase") or "") != "execution":
        return "execution_attempt_phase_invalid"
    if not str(attempt.get("task_id") or "").strip():
        return "execution_attempt_task_id_missing"
    return ""


def current_execution_attempt(node: dict[str, Any]) -> dict[str, Any] | None:
    """Return the node's canonical execution attempt, if it is well formed.

    Evaluation assignments have their own generation-fenced lifecycle and are
    intentionally not represented here.  Keeping the execution attempt
    separate prevents an evaluator success from excusing a failed builder.
    """
    if execution_attempt_validation_error(node):
        return None
    return node.get("execution_attempt")


def _attempt_sequence(node: dict[str, Any]) -> int:
    observed: list[int] = []
    current = current_execution_attempt(node)
    candidates = [current] if current is not None else []
    history = node.get("execution_attempt_history")
    if isinstance(history, list):
        candidates.extend(item for item in history if isinstance(item, dict))
    for item in candidates:
        try:
            observed.append(int(item.get("sequence") or 0))
        except (TypeError, ValueError):
            continue
    return max(observed, default=0) + 1


def _mirror_current_attempt(node: dict[str, Any], attempt: dict[str, Any]) -> None:
    """Keep legacy fields as compatibility mirrors, never authorities."""
    source = str(attempt.get("source") or "").strip()
    task_id = str(attempt.get("task_id") or "").strip()
    dispatch_id = str(attempt.get("dispatch_id") or task_id).strip()
    operator_id = str(attempt.get("operator_id") or "").strip()
    node["dispatched_via"] = source
    if dispatch_id:
        node["dispatch_id"] = dispatch_id
    else:
        node.pop("dispatch_id", None)
    if operator_id:
        node["operator_id"] = operator_id
    else:
        node.pop("operator_id", None)
    if bool(attempt.get("requires_operator_result")) and task_id:
        node["pm_task_id"] = task_id
    else:
        node.pop("pm_task_id", None)


def retire_execution_attempt_for_human_resume(
    node: dict[str, Any],
    *,
    human_review_generation: int,
    actor: str,
    reason: str,
    now: str = "",
) -> dict[str, Any] | None:
    """Retire the failed/stuck authority acknowledged by a human resume.

    Leaving the old attempt current would make the next reconcile observe its
    same terminal failure and immediately requeue/escalate the node again.
    Retirement preserves the attempt verbatim in bounded history while
    removing all legacy identity mirrors; the next real dispatch must activate
    a new canonical attempt.
    """
    actor = str(actor or "").strip()
    reason = str(reason or "").strip()
    if not actor:
        raise ValueError("human_resume_actor_required")
    if not reason:
        raise ValueError("human_resume_reason_required")
    try:
        generation = int(human_review_generation)
    except (TypeError, ValueError) as exc:
        raise ValueError("human_resume_generation_invalid") from exc
    if generation <= 0:
        raise ValueError("human_resume_generation_invalid")

    timestamp = str(now or _utc_now())
    validation_error = execution_attempt_validation_error(node)
    current = current_execution_attempt(node)
    archived: dict[str, Any] | None = None
    if current is not None:
        archived = deepcopy(current)
    elif "execution_attempt" in node or "execution_attempt_error" in node:
        raw_attempt = node.get("execution_attempt")
        archived = deepcopy(raw_attempt) if isinstance(raw_attempt, dict) else {
            "raw_value": repr(raw_attempt),
        }
        if validation_error:
            archived["validation_error"] = validation_error

    if archived is not None:
        archived.update(
            {
                "retired": True,
                "retired_at": timestamp,
                "retired_reason": "explicit_human_resume",
                "human_review_generation": generation,
                "human_actor": actor,
                "human_reason": reason,
            }
        )
        history = node.get("execution_attempt_history")
        if not isinstance(history, list):
            history = []
        history = [deepcopy(item) for item in history if isinstance(item, dict)]
        history.append(archived)
        node["execution_attempt_history"] = history[-NODE_ATTEMPT_HISTORY_LIMIT:]

    for key in (
        "execution_attempt",
        "execution_attempt_error",
        "dispatched_via",
        "dispatch_id",
        "operator_id",
        "pm_task_id",
        "last_operator_closeout_failure",
    ):
        node.pop(key, None)
    return deepcopy(archived) if archived is not None else None


def activate_execution_attempt(
    node: dict[str, Any],
    *,
    task_id: str,
    dispatch_id: str = "",
    operator_id: str = "",
    source: str,
    logical_role: str = "builder",
    status: str = "submitted",
    requires_operator_result: bool = False,
    sprint_id: str = "",
    node_id: str = "",
    result_path: str = "",
    now: str = "",
) -> dict[str, Any]:
    """Activate one execution attempt and supersede the prior authority.

    Repeating the same activation is idempotent.  A genuinely different task
    archives the former current attempt with a ``superseded_by`` edge.  Repair
    generation is a snapshot only; the monotonic execution ``sequence`` is a
    distinct counter so retries never corrupt evaluator freshness semantics.
    """
    task_id = str(task_id or "").strip()
    if not task_id:
        raise ValueError("execution attempt requires task_id")
    source = str(source or "").strip()
    if not source:
        raise ValueError("execution attempt requires source")
    # A later identified replacement is the only automatic recovery from an
    # identity-less submission.  The error itself remains in bounded history.
    node.pop("execution_attempt_error", None)
    timestamp = str(now or _utc_now())
    operator_id = str(operator_id or "").strip()
    dispatch_id = str(dispatch_id or task_id).strip()
    node_id = str(node_id or node.get("id") or "").strip()
    invalid_current = execution_attempt_validation_error(node)
    current = current_execution_attempt(node)

    if current is not None and str(current.get("task_id") or "") == task_id:
        expected_operator = str(current.get("operator_id") or "").strip()
        if expected_operator and operator_id and expected_operator != operator_id:
            raise ValueError("same task_id cannot change operator_id")
        expected_source = str(current.get("source") or "").strip()
        if expected_source and source != expected_source:
            raise ValueError("same task_id cannot change source")
        expected_role = str(current.get("logical_role") or "").strip()
        incoming_role = str(logical_role or expected_role or "builder").strip()
        if expected_role and incoming_role != expected_role:
            raise ValueError("same task_id cannot change logical_role")
        if bool(requires_operator_result) != bool(current.get("requires_operator_result")):
            raise ValueError("same task_id cannot change requires_operator_result")
        for key, incoming in (
            ("sprint_id", str(sprint_id or "").strip()),
            ("node_id", node_id),
        ):
            expected = str(current.get(key) or "").strip()
            if expected and incoming and incoming != expected:
                raise ValueError(f"same task_id cannot change {key}")
        current_status = str(current.get("status") or "").strip().lower()
        incoming_status = str(status or current_status or "submitted").strip().lower()
        if current_status in TERMINAL_TASK_STATUSES:
            incoming_status = current_status
        current.update(
            {
                "dispatch_id": dispatch_id,
                "operator_id": operator_id or expected_operator,
                "source": expected_source or source,
                "logical_role": expected_role or incoming_role,
                "status": incoming_status,
                "requires_operator_result": bool(current.get("requires_operator_result")),
                "sprint_id": str(sprint_id or current.get("sprint_id") or ""),
                "node_id": node_id,
                "updated_at": timestamp,
            }
        )
        if result_path:
            current["result_path"] = str(result_path)
        _mirror_current_attempt(node, current)
        return current

    if current is not None or invalid_current:
        if current is not None:
            archived = deepcopy(current)
        else:
            raw_attempt = node.get("execution_attempt")
            archived = deepcopy(raw_attempt) if isinstance(raw_attempt, dict) else {
                "raw_value": repr(raw_attempt),
            }
            archived["status"] = "invalid"
            archived["validation_error"] = invalid_current
        if "last_operator_closeout_failure" in node and "closeout_failure" not in archived:
            archived["closeout_failure"] = deepcopy(node["last_operator_closeout_failure"])
        archived["superseded"] = True
        archived["superseded_at"] = timestamp
        archived["superseded_by"] = task_id
        prior_status = str(archived.get("status") or "").strip().lower()
        if prior_status in ACTIVE_TASK_STATUSES or not prior_status:
            archived["previous_status"] = prior_status
            archived["status"] = "superseded"
        history = node.get("execution_attempt_history")
        if not isinstance(history, list):
            history = []
        history = [deepcopy(item) for item in history if isinstance(item, dict)]
        history.append(archived)
        node["execution_attempt_history"] = history[-NODE_ATTEMPT_HISTORY_LIMIT:]

    try:
        repair_generation = int(node.get("repair_attempts") or 0)
    except (TypeError, ValueError):
        repair_generation = 0
    attempt: dict[str, Any] = {
        "schema_version": NODE_ATTEMPT_SCHEMA_VERSION,
        "phase": "execution",
        "sequence": _attempt_sequence(node),
        "repair_generation": repair_generation,
        "task_id": task_id,
        "dispatch_id": dispatch_id,
        "operator_id": operator_id,
        "source": source,
        "logical_role": str(logical_role or "builder"),
        "status": str(status or "submitted").strip().lower(),
        "requires_operator_result": bool(requires_operator_result),
        "sprint_id": str(sprint_id or ""),
        "node_id": node_id,
        "activated_at": timestamp,
        "updated_at": timestamp,
    }
    if result_path:
        attempt["result_path"] = str(result_path)
    node["execution_attempt"] = attempt
    node.pop("last_operator_closeout_failure", None)
    node.pop("dispatch_retry_reason", None)
    _mirror_current_attempt(node, attempt)
    return attempt


def record_execution_attempt_activation_error(
    node: dict[str, Any],
    *,
    reason: str,
    dispatch_id: str,
    source: str,
    operator_id: str = "",
    sprint_id: str = "",
    node_id: str = "",
    now: str = "",
) -> dict[str, Any]:
    """Quarantine a submitted task whose durable identity is unavailable.

    Once a submit command succeeds, retrying through another worker is unsafe:
    the first process may already be running.  Without its task id, however,
    no result can be correlated.  Archive any prior authority, remove all
    legacy identity mirrors, and persist an explicit fail-closed marker until
    a later identified replacement is deliberately activated.
    """
    reason = str(reason or "").strip()
    dispatch_id = str(dispatch_id or "").strip()
    source = str(source or "").strip()
    if not reason:
        raise ValueError("execution attempt activation error requires reason")
    if not dispatch_id:
        raise ValueError("execution attempt activation error requires dispatch_id")
    if not source:
        raise ValueError("execution attempt activation error requires source")
    timestamp = str(now or _utc_now())

    history = node.get("execution_attempt_history")
    if not isinstance(history, list):
        history = []
    history = [deepcopy(item) for item in history if isinstance(item, dict)]

    current = current_execution_attempt(node)
    if current is not None:
        archived = deepcopy(current)
        archived["superseded"] = True
        archived["superseded_at"] = timestamp
        archived["superseded_by_dispatch"] = dispatch_id
        prior_status = str(archived.get("status") or "").strip().lower()
        if prior_status in ACTIVE_TASK_STATUSES or not prior_status:
            archived["previous_status"] = prior_status
            archived["status"] = "superseded_untracked"
        history.append(archived)
    elif "execution_attempt" in node:
        raw_attempt = node.get("execution_attempt")
        archived = deepcopy(raw_attempt) if isinstance(raw_attempt, dict) else {
            "raw_value": repr(raw_attempt),
        }
        archived["status"] = "invalid"
        archived["validation_error"] = execution_attempt_validation_error(node)
        archived["superseded"] = True
        archived["superseded_at"] = timestamp
        archived["superseded_by_dispatch"] = dispatch_id
        history.append(archived)

    node.pop("execution_attempt", None)
    node.pop("execution_attempt_error", None)
    error: dict[str, Any] = {
        "schema_version": NODE_ATTEMPT_ERROR_SCHEMA_VERSION,
        "phase": "execution",
        "sequence": _attempt_sequence({"execution_attempt_history": history}),
        "reason": reason,
        "dispatch_id": dispatch_id,
        "operator_id": str(operator_id or "").strip(),
        "source": source,
        "sprint_id": str(sprint_id or ""),
        "node_id": str(node_id or node.get("id") or ""),
        "status": "activation_failed",
        "recorded_at": timestamp,
    }
    history.append(deepcopy(error))
    node["execution_attempt_history"] = history[-NODE_ATTEMPT_HISTORY_LIMIT:]
    node["execution_attempt_error"] = error
    for key in ("pm_task_id", "operator_id", "dispatched_via"):
        node.pop(key, None)
    node.pop("last_operator_closeout_failure", None)
    node.pop("dispatch_retry_reason", None)
    return error


def converge_execution_attempt_result(
    node: dict[str, Any],
    result_payload: dict[str, Any],
    *,
    result_path: str | Path = "",
    now: str = "",
) -> dict[str, Any]:
    """Converge a terminal result only when it matches the current attempt."""
    attempt = current_execution_attempt(node)
    if attempt is None:
        return {"matched": False, "reason": "current_attempt_missing"}
    expected_task = str(attempt.get("task_id") or "").strip()
    if str(result_payload.get("task_id") or "").strip() != expected_task:
        return {"matched": False, "reason": "task_id_mismatch"}
    for key in ("operator_id", "sprint_id", "node_id"):
        expected = str(attempt.get(key) or "").strip()
        observed = str(result_payload.get(key) or "").strip()
        if expected and observed != expected:
            return {"matched": False, "reason": f"{key}_mismatch"}
    status = str(result_payload.get("status") or "").strip().lower()
    if status not in TERMINAL_TASK_STATUSES:
        return {"matched": False, "reason": "result_not_terminal"}
    timestamp = str(
        result_payload.get("finished_at")
        or result_payload.get("updated_at")
        or now
        or _utc_now()
    )
    try:
        exit_code = int(result_payload.get("exit_code"))
    except (TypeError, ValueError):
        exit_code = None
    ok = status == "completed" and exit_code == 0
    current_status = str(attempt.get("status") or "").strip().lower()
    if current_status in TERMINAL_TASK_STATUSES:
        current_exit = attempt.get("exit_code")
        if current_status == status and current_exit == exit_code:
            return {
                "matched": True,
                "ok": bool(attempt.get("result_ok")),
                "status": current_status,
                "task_id": expected_task,
                "idempotent": True,
            }
        return {
            "matched": False,
            "reason": "attempt_already_terminal",
            "status": current_status,
            "task_id": expected_task,
        }
    attempt["status"] = status
    attempt["exit_code"] = exit_code
    attempt["result_ok"] = ok
    attempt["finished_at"] = timestamp
    attempt["updated_at"] = timestamp
    if result_path:
        attempt["result_path"] = str(result_path)
    if ok:
        for key in (
            "last_operator_closeout_failure",
            "dispatch_retry_reason",
            "dispatch_failure_streak",
            "last_dispatch_failure_reason",
            "last_dispatch_failure_at",
            "dispatch_blocked_reason",
        ):
            node.pop(key, None)
    return {"matched": True, "ok": ok, "status": status, "task_id": expected_task}


def converge_execution_attempt_status(
    node: dict[str, Any],
    status_payload: dict[str, Any],
) -> dict[str, Any]:
    """Converge a terminal legacy multi-task status for its exact attempt."""
    attempt = current_execution_attempt(node)
    if attempt is None:
        return {"matched": False, "reason": "current_attempt_missing"}
    if str(attempt.get("source") or "") != "multi_task_tmux":
        return {"matched": False, "reason": "status_not_authoritative_for_source"}
    status = str(status_payload.get("effective_status") or status_payload.get("status") or "").strip().lower()
    if status not in EFFECTIVE_TERMINAL_TASK_STATUSES:
        return {"matched": False, "reason": "status_not_terminal"}
    normalized_status = {
        "completed_aligned": "completed",
        "failed_aligned": "failed",
    }.get(status, status)
    result = dict(status_payload)
    result["task_id"] = str(result.get("task_id") or result.get("id") or "")
    result["status"] = normalized_status
    return converge_execution_attempt_result(node, result)


def record_execution_attempt_closeout_failure(
    node: dict[str, Any],
    closeout: dict[str, Any],
    *,
    now: str = "",
) -> bool:
    """Attach a reconciler-observed failure to the current execution attempt."""
    attempt = current_execution_attempt(node)
    if attempt is None:
        return False
    timestamp = str(now or _utc_now())
    status = str(closeout.get("operator_status") or "failed").strip().lower()
    if status not in TERMINAL_TASK_STATUSES:
        status = "failed"
    attempt["status"] = status
    attempt["result_ok"] = False
    attempt["closeout_failure"] = deepcopy(closeout)
    attempt["finished_at"] = timestamp
    attempt["updated_at"] = timestamp
    return True


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def correlated_terminal_result(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return the exact terminal result for ``row``, never a neighboring task.

    The task id is mandatory.  Operator, sprint, and node identities are also
    compared whenever both sides carry them.  This keeps an unrelated result
    file from freeing a worker slot or deciding which attempt is canonical.
    """
    result_path = str(row.get("result_path") or "").strip()
    task_id = str(row.get("id") or row.get("task_id") or "").strip()
    if not result_path or not task_id:
        return None
    result = _read_json_object(Path(result_path).expanduser())
    if str(result.get("task_id") or "").strip() != task_id:
        return None
    for row_key, result_key in (
        ("operator_id", "operator_id"),
        ("sprint_id", "sprint_id"),
        ("node_id", "node_id"),
    ):
        expected = str(row.get(row_key) or "").strip()
        observed = str(result.get(result_key) or "").strip()
        if expected and observed and expected != observed:
            return None
    status = str(result.get("status") or "").strip().lower()
    if status not in TERMINAL_TASK_STATUSES:
        return None
    return result


def converge_status_payload(
    status_payload: dict[str, Any],
    result_payload: dict[str, Any],
    *,
    result_path: Path,
) -> dict[str, Any] | None:
    """Return a converged status payload when identities match exactly."""
    probe = dict(status_payload)
    probe["result_path"] = str(result_path)
    # Correlate against the supplied payload without trusting a second disk read.
    task_id = str(probe.get("id") or probe.get("task_id") or "").strip()
    if not task_id or str(result_payload.get("task_id") or "").strip() != task_id:
        return None
    for key in ("operator_id", "sprint_id", "node_id"):
        expected = str(probe.get(key) or "").strip()
        observed = str(result_payload.get(key) or "").strip()
        if expected and observed and expected != observed:
            return None
    result_status = str(result_payload.get("status") or "").strip().lower()
    if result_status not in TERMINAL_TASK_STATUSES:
        return None

    converged = dict(status_payload)
    converged["status"] = result_status
    converged["exit_code"] = result_payload.get("exit_code")
    converged["result_path"] = str(result_path)
    converged["operator_result"] = dict(result_payload)
    converged["result_converged"] = True
    converged["updated_at"] = str(
        result_payload.get("finished_at")
        or result_payload.get("updated_at")
        or converged.get("updated_at")
        or ""
    )
    return converged


def converge_status_file(
    status_path: Path,
    result_payload: dict[str, Any],
    *,
    result_path: Path,
) -> bool:
    """Atomically converge an existing multi-task status file from its result."""
    status = _read_json_object(status_path)
    if not status:
        return False
    converged = converge_status_payload(status, result_payload, result_path=result_path)
    if converged is None:
        return False
    temporary = status_path.with_suffix(status_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(converged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, status_path)
    return True
