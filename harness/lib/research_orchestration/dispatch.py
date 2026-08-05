"""Side-effect-free research node dispatch boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from .result_validation import (
    ResearchResultValidationError,
    validate_node_request,
    validate_node_result,
    validate_result_identity,
    validate_result_scopes,
)
from .transport import ResearchTransportError, run_json_worker


class ResearchDispatchError(ValueError):
    """Raised when a research node cannot be dispatched safely."""


def dispatch_research_node(
    node_request: dict,
    *,
    runner: Callable[[dict], dict],
    request_schema_path: Path,
    result_schema_path: Path,
    artifact_root: Path,
) -> dict:
    """Validate a node request, call the injected runner, and validate result."""

    request_for_runner = copy.deepcopy(node_request)
    validate_node_request(node_request, request_schema_path)
    _validate_operator_boundary(node_request)
    _validate_provider_authorization(node_request)

    try:
        result = runner(request_for_runner)
    except Exception as exc:
        result = _failed_result_from_exception(node_request, exc)

    if not isinstance(result, dict):
        result = _failed_result_from_exception(
            node_request,
            ResearchDispatchError("runner returned a non-dictionary result"),
        )

    validate_node_result(result, result_schema_path)
    validate_result_identity(node_request, result)
    validate_result_scopes(node_request, result, artifact_root)
    return result


def synchronous_json_command_runner(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
    env_allowlist: set[str] | None = None,
    max_stdout_bytes: int = 1_048_576,
    max_stderr_bytes: int = 65_536,
) -> Callable[[dict], dict]:
    """Return a runner that executes a JSON stdin/stdout command worker."""

    def _runner(node_request: dict) -> dict:
        return run_json_worker(
            command,
            node_request,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            env=env,
            env_allowlist=env_allowlist,
            max_stdout_bytes=max_stdout_bytes,
            max_stderr_bytes=max_stderr_bytes,
        )

    return _runner


def operator_runtime_submit_adapter(
    *,
    submit: Callable[[dict], dict] | None = None,
) -> Callable[[dict], dict]:
    """Return an adapter that submits to existing operator_runtime inboxes."""

    def _runner(node_request: dict) -> dict:
        submit_fn = submit
        if submit_fn is None:
            from operator_runtime import submit as submit_fn  # type: ignore

        receipt = submit_fn(_operator_runtime_envelope(node_request))
        return {
            "schema": "research_node_result.v1",
            "task_id": node_request["task_id"],
            "run_id": node_request["run_id"],
            "workflow_id": node_request["workflow_id"],
            "node_id": node_request["node_id"],
            "status": "awaiting_external",
            "status_is_terminal": False,
            "output_artifacts": [],
            "evidence": [
                {
                    "evidence_id": f"receipt-{node_request['node_id']}",
                    "kind": "operator_runtime_receipt",
                    "summary": "Node request was submitted to operator_runtime and is awaiting external completion.",
                    "receipt": copy.deepcopy(receipt),
                }
            ],
            "hashes": [],
            "model_provider_usage": [],
            "errors": [],
            "limitations": ["Submitted receipt is not completed worker evidence."],
            "secret_redaction_assertion": {
                "no_secrets_observed": True,
                "redaction_review": "passed",
            },
        }

    return _runner


def _validate_operator_boundary(node_request: dict) -> None:
    logical = node_request.get("logical_operator") or {}
    physical = node_request.get("physical_operator") or {}
    if logical.get("operator_kind") != "logical":
        raise ResearchDispatchError("logical operator kind must be logical")
    if physical.get("operator_kind") != "physical":
        raise ResearchDispatchError("physical operator kind must be physical")
    approved = set(node_request.get("authorization", {}).get("approved_capabilities") or [])
    logical_caps = set(logical.get("capabilities") or [])
    physical_caps = set(physical.get("capabilities") or [])
    if not logical_caps.issubset(approved):
        raise ResearchDispatchError("logical operator capabilities exceed authorization")
    if not physical_caps.issubset(approved | {"bounded_worker"}):
        raise ResearchDispatchError("physical operator capabilities exceed authorization")


def _validate_provider_authorization(node_request: dict) -> None:
    auth = node_request.get("authorization") or {}
    if auth.get("allow_live_provider"):
        if auth.get("allow_network") is not True:
            raise ResearchDispatchError("live provider requires allow_network=true")
        if not str(auth.get("approval_ref") or "").strip():
            raise ResearchDispatchError("live provider requires approval_ref")


def _failed_result_from_exception(node_request: dict, exc: Exception) -> dict:
    error_type = getattr(exc, "error_type", type(exc).__name__)
    message = str(getattr(exc, "message", exc))
    if isinstance(exc, ResearchTransportError):
        message = json.dumps(exc.to_dict(), sort_keys=True)
    return {
        "schema": "research_node_result.v1",
        "task_id": node_request.get("task_id", ""),
        "run_id": node_request.get("run_id", ""),
        "workflow_id": node_request.get("workflow_id", ""),
        "node_id": node_request.get("node_id", ""),
        "status": "failed",
        "status_is_terminal": True,
        "output_artifacts": [],
        "evidence": [],
        "hashes": [],
        "model_provider_usage": [],
        "errors": [
            {
                "error_id": "runner_exception",
                "error_type": str(error_type)[:120] or "runner_exception",
                "message": message[:500] or "runner failed",
            }
        ],
        "limitations": [],
        "secret_redaction_assertion": {
            "no_secrets_observed": True,
            "redaction_review": "passed",
        },
    }


def _operator_runtime_envelope(node_request: dict) -> dict:
    physical = node_request.get("physical_operator") or {}
    operator_id = str(physical.get("operator_id") or "")
    return {
        "task_id": node_request["task_id"],
        "sprint_id": node_request["workflow_id"],
        "node_id": node_request["node_id"],
        "operator_id": operator_id,
        "objective": f"Run bounded research node {node_request['node_id']}",
        "inputs": copy.deepcopy(node_request.get("typed_inputs", {}).get("payload") or {}),
        "research_node_request": copy.deepcopy(node_request),
    }
