"""Typed worker boundary for direct physical-operator execution.

The worker owns ``node_envelope.json``.  Operators own only their domain
artifacts and return ``research_node_result.v1`` values; this wrapper records
attempt identity and typed failures without interpreting stdout or log text.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


_RESULT_STATUSES = {
    "completed",
    "failed",
    "blocked",
    "cancelled",
    "awaiting_human",
    "awaiting_external",
}
_FORBIDDEN_OPERATOR_ARTIFACTS = {
    "artifact_manifest.json",
    "dispatch_record.json",
    "evidence_ir.json",
    "gate_ledger.json",
    "lease_record.json",
    "node_envelope.json",
    "operator_state_log.json",
}
_TRANSIENT_ERROR_TYPES = {
    "external_dependency_pending",
    "provider_environment_failure",
    "provider_unavailable",
    "rate_limit",
    "timeout",
    "transient_provider_failure",
}


class WorkerBoundaryError(ValueError):
    """A typed error found before or after the operator call."""

    def __init__(self, message: str, *, error_type: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


def run_physical_operator(
    node_request: dict[str, Any],
    *,
    operator_id: str,
    runner: Callable[[dict[str, Any]], dict[str, Any]],
    envelope_path: str | Path,
    attempt: int,
    lease_id: str,
    run_contract_ref: Mapping[str, Any],
    clock: Callable[[], str] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Execute one explicitly selected operator and write its typed envelope."""

    started = monotonic()
    request = node_request if isinstance(node_request, dict) else {}
    result: dict[str, Any] | None = None
    boundary_error: WorkerBoundaryError | None = None
    try:
        _validate_request(request, operator_id=operator_id, runner=runner, attempt=attempt, lease_id=lease_id)
        raw = runner(copy.deepcopy(request))
        result = _validate_result(raw, request)
        _reject_forbidden_artifacts(result)
    except Exception as exc:  # the worker must always leave a typed receipt
        boundary_error = _typed_boundary_error(exc)

    envelope = _build_envelope(
        request,
        operator_id=operator_id,
        result=result,
        boundary_error=boundary_error,
        attempt=attempt,
        lease_id=lease_id,
        run_contract_ref=run_contract_ref,
        completed_at=(clock or _utc_now)(),
        duration_s=max(0.0, round(monotonic() - started, 6)),
    )
    _write_json(Path(envelope_path), envelope)
    return envelope


def _validate_request(
    request: dict[str, Any],
    *,
    operator_id: str,
    runner: Callable[[dict[str, Any]], dict[str, Any]],
    attempt: int,
    lease_id: str,
) -> None:
    if not callable(runner):
        raise WorkerBoundaryError("runner must be callable", error_type="invalid_input")
    if not str(operator_id).strip() or not str(lease_id).strip() or not isinstance(attempt, int) or attempt < 1:
        raise WorkerBoundaryError("operator_id, lease_id and positive attempt are required", error_type="invalid_input")
    for field in ("task_id", "run_id", "workflow_id", "node_id"):
        if not str(request.get(field) or "").strip():
            raise WorkerBoundaryError(f"missing request identity: {field}", error_type="missing_input")
    if not isinstance(request.get("typed_inputs"), dict):
        raise WorkerBoundaryError("typed_inputs must be an object", error_type="invalid_input")
    physical = request.get("physical_operator")
    if not isinstance(physical, dict) or physical.get("operator_kind") != "physical":
        raise WorkerBoundaryError("physical_operator must be a physical operator object", error_type="invalid_input")
    if str(physical.get("operator_id") or "") != str(operator_id):
        raise WorkerBoundaryError("selected operator identity does not match the request", error_type="operator_identity_mismatch")


def _validate_result(raw: Any, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise WorkerBoundaryError("operator returned a non-object result", error_type="malformed_operator_response")
    required = {
        "schema",
        "task_id",
        "run_id",
        "workflow_id",
        "node_id",
        "status",
        "status_is_terminal",
        "output_artifacts",
        "evidence",
        "hashes",
        "model_provider_usage",
        "errors",
        "limitations",
        "secret_redaction_assertion",
    }
    if required - set(raw):
        raise WorkerBoundaryError("operator result is missing required fields", error_type="malformed_operator_response")
    if raw.get("schema") != "research_node_result.v1" or raw.get("status") not in _RESULT_STATUSES:
        raise WorkerBoundaryError("operator result has an invalid schema or status", error_type="malformed_operator_response")
    for field in ("task_id", "run_id", "workflow_id", "node_id"):
        if raw.get(field) != request.get(field):
            raise WorkerBoundaryError(f"operator result {field} does not match request", error_type="operator_identity_mismatch")
    for field in ("output_artifacts", "evidence", "hashes", "model_provider_usage", "errors", "limitations"):
        if not isinstance(raw.get(field), list):
            raise WorkerBoundaryError(f"operator result {field} must be a list", error_type="malformed_operator_response")
    assertion = raw.get("secret_redaction_assertion")
    if not isinstance(assertion, dict) or assertion.get("no_secrets_observed") is not True:
        raise WorkerBoundaryError("operator result lacks a verified redaction assertion", error_type="malformed_operator_response")
    if raw["status"] == "completed" and (raw["errors"] or not raw["evidence"]):
        raise WorkerBoundaryError("completed result requires evidence and no errors", error_type="malformed_operator_response")
    if raw["status"] == "failed" and not raw["errors"]:
        raise WorkerBoundaryError("failed result requires a typed error", error_type="malformed_operator_response")
    return copy.deepcopy(raw)


def _reject_forbidden_artifacts(result: dict[str, Any]) -> None:
    for artifact in result.get("output_artifacts") or []:
        if not isinstance(artifact, dict):
            raise WorkerBoundaryError("operator artifact reference must be an object", error_type="malformed_operator_response")
        name = Path(str(artifact.get("path") or "").replace("\\", "/")).name
        artifact_id = str(artifact.get("artifact_id") or "")
        if name in _FORBIDDEN_OPERATOR_ARTIFACTS or f"{artifact_id}.json" in _FORBIDDEN_OPERATOR_ARTIFACTS:
            raise WorkerBoundaryError(
                f"operator attempted to author non-operator artifact: {name or artifact_id}",
                error_type="forbidden_artifact_owner",
            )
        digest = str(artifact.get("sha256") or "")
        if len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
            raise WorkerBoundaryError("operator artifact is missing a valid sha256", error_type="malformed_operator_response")


def _typed_boundary_error(exc: Exception) -> WorkerBoundaryError:
    if isinstance(exc, WorkerBoundaryError):
        return exc
    declared = str(getattr(exc, "error_type", "") or "").strip()
    if declared:
        return WorkerBoundaryError(
            str(exc)[:500] or declared,
            error_type=declared,
            retryable=bool(getattr(exc, "retryable", declared in _TRANSIENT_ERROR_TYPES)),
        )
    if isinstance(exc, TimeoutError):
        return WorkerBoundaryError(str(exc)[:500] or "operator timed out", error_type="timeout", retryable=True)
    if isinstance(exc, ConnectionError):
        return WorkerBoundaryError(
            str(exc)[:500] or "provider unavailable",
            error_type="transient_provider_failure",
            retryable=True,
        )
    if isinstance(exc, NotImplementedError):
        return WorkerBoundaryError(str(exc)[:500] or "request unsupported", error_type="unsupported_request")
    if isinstance(exc, (TypeError, ValueError)):
        return WorkerBoundaryError(str(exc)[:500] or "invalid input", error_type="invalid_input")
    return WorkerBoundaryError(
        f"{type(exc).__name__}: {str(exc)}"[:500],
        error_type="operator_internal_error",
    )


def _result_error(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None or result.get("status") == "completed":
        return None
    errors = result.get("errors") or []
    if errors and isinstance(errors[0], dict):
        error_type = str(errors[0].get("error_type") or "operator_failure")
        return {
            "type": error_type,
            "detail": str(errors[0].get("message") or error_type)[:500],
            "retryable": error_type in _TRANSIENT_ERROR_TYPES,
        }
    if result.get("status") == "awaiting_external":
        return {
            "type": "external_dependency_pending",
            "detail": "Operator is awaiting an explicitly authorized external dependency.",
            "retryable": True,
        }
    return {
        "type": "operator_blocked",
        "detail": f"Operator returned status {result.get('status')} without an error record.",
        "retryable": False,
    }


def _build_envelope(
    request: dict[str, Any],
    *,
    operator_id: str,
    result: dict[str, Any] | None,
    boundary_error: WorkerBoundaryError | None,
    attempt: int,
    lease_id: str,
    run_contract_ref: Mapping[str, Any],
    completed_at: str,
    duration_s: float,
) -> dict[str, Any]:
    if boundary_error is not None:
        status = "failed"
        error = {
            "type": boundary_error.error_type,
            "detail": str(boundary_error)[:500],
            "retryable": boundary_error.retryable,
        }
        artifacts: list[dict[str, Any]] = []
        self_reported: dict[str, Any] = {}
    else:
        assert result is not None
        status = str(result["status"])
        error = _result_error(result)
        artifacts = copy.deepcopy(result["output_artifacts"])
        self_reported = {
            "schema": result["schema"],
            "status_is_terminal": result["status_is_terminal"],
            "evidence": copy.deepcopy(result["evidence"]),
            "hashes": copy.deepcopy(result["hashes"]),
            "model_provider_usage": copy.deepcopy(result["model_provider_usage"]),
            "limitations": copy.deepcopy(result["limitations"]),
            "secret_redaction_assertion": copy.deepcopy(result["secret_redaction_assertion"]),
        }
    return {
        "schema_version": "solar.node_envelope.v1",
        "artifact_role": "runtime_worker_receipt",
        "run_contract_ref": {
            "run_contract_id": str(run_contract_ref.get("run_contract_id") or ""),
            "sha256": str(run_contract_ref.get("sha256") or ""),
        },
        "task_id": str(request.get("task_id") or ""),
        "run_id": str(request.get("run_id") or ""),
        "workflow_id": str(request.get("workflow_id") or ""),
        "node": str(request.get("node_id") or ""),
        "operator_id": str(operator_id),
        "attempt": attempt,
        "lease_id": str(lease_id),
        "status": status,
        "error": error,
        "artifacts": artifacts,
        "self_reported": self_reported,
        "completed_at": completed_at,
        "duration_s": duration_s,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["WorkerBoundaryError", "run_physical_operator"]
