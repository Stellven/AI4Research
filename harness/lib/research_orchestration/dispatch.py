"""Side-effect-free research node dispatch boundary."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Callable

from .result_validation import (
    ResearchResultValidationError,
    validate_node_request,
    validate_node_result,
    validate_request_artifact_scopes,
    validate_result_identity,
    validate_result_scopes,
)
from .transport import (
    DEFAULT_MAX_REQUEST_BYTES,
    ResearchTransportError,
    run_json_worker,
    sanitize_diagnostic_value,
    sanitize_text,
    sensitive_environment_values,
)


class ResearchDispatchError(ValueError):
    """Raised when a research node cannot be dispatched safely."""


def dispatch_research_node(
    node_request: dict,
    *,
    runner: Callable[[dict], dict],
    request_schema_path: Path,
    result_schema_path: Path,
    artifact_root: Path,
    operator_resolver: Callable[[str], Any] | None = None,
    trusted_test_bypass_operator_resolution: bool = False,
    secret_values: Iterable[str] = (),
) -> dict:
    """Validate a node request, call the injected runner, and validate result."""

    secrets = tuple(str(value) for value in secret_values if str(value))
    request_diagnostics = _request_body_diagnostic_values(node_request)
    request_for_runner = copy.deepcopy(node_request)
    validate_node_request(node_request, request_schema_path, secret_values=secrets)
    validate_request_artifact_scopes(node_request, artifact_root)
    _validate_operator_boundary(node_request)
    _validate_provider_authorization(node_request)
    _validate_physical_operator_resolution(
        node_request,
        operator_resolver,
        trusted_test_bypass=trusted_test_bypass_operator_resolution,
    )

    try:
        result = runner(request_for_runner)
    except Exception as exc:
        result = _failed_result_from_exception(node_request, exc, secret_values=secrets)

    if not isinstance(result, dict):
        result = _failed_result_from_exception(
            node_request,
            ResearchDispatchError("runner returned a non-dictionary result"),
            secret_values=secrets,
        )

    result = _sanitize_result_request_echo(result, request_diagnostics)
    validate_node_result(
        result,
        result_schema_path,
        secret_values=secrets,
        diagnostic_values=request_diagnostics,
    )
    validate_result_identity(node_request, result)
    validate_result_scopes(
        node_request,
        result,
        artifact_root,
        secret_values=secrets,
    )
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
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    secret_values: Iterable[str] = (),
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
            max_request_bytes=max_request_bytes,
            secret_values=secret_values,
        )

    return _runner


def operator_runtime_submit_adapter(
    *,
    submit: Callable[[dict], dict] | None = None,
    secret_values: Iterable[str] = (),
    env: Mapping[str, str] | None = None,
    env_allowlist: set[str] | None = None,
) -> Callable[[dict], dict]:
    """Return an adapter that submits to existing operator_runtime inboxes."""

    secrets = tuple(str(value) for value in secret_values if str(value))

    def _runner(node_request: dict) -> dict:
        submit_fn = submit
        if submit_fn is None:
            from operator_runtime import submit as submit_fn  # type: ignore

        request_values = _request_body_diagnostic_values(node_request)
        protected_env_values = sensitive_environment_values(
            env=env,
            env_allowlist=env_allowlist,
        )
        receipt = submit_fn(_operator_runtime_envelope(node_request))
        safe_receipt = _bounded_receipt(
            receipt,
            secret_values=(*secrets, *protected_env_values, *request_values),
        )
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
                    "receipt": safe_receipt,
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


def _validate_physical_operator_resolution(
    node_request: dict,
    resolver: Callable[[str], Any] | None,
    *,
    trusted_test_bypass: bool,
) -> None:
    if resolver is None:
        if trusted_test_bypass:
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                raise ResearchDispatchError("trusted operator resolver bypass is test-only")
            return
        raise ResearchDispatchError("physical operator resolver is required")
    if trusted_test_bypass:
        raise ResearchDispatchError("trusted test bypass cannot be combined with resolver")
    operator_id = str(node_request.get("physical_operator", {}).get("operator_id") or "")
    try:
        resolved = resolver(operator_id)
    except Exception:
        raise ResearchDispatchError("physical operator resolver failed") from None
    if resolved is None or resolved is False:
        raise ResearchDispatchError("physical operator is unknown or disabled")
    if isinstance(resolved, Mapping):
        resolved_id = str(resolved.get("operator_id") or resolved.get("id") or operator_id)
        if resolved_id != operator_id:
            raise ResearchDispatchError("physical operator resolver returned the wrong identity")
        if resolved.get("enabled") is False or resolved.get("active") is False:
            raise ResearchDispatchError("physical operator is disabled")
        if _resolver_record_is_disabled(resolved):
            raise ResearchDispatchError("physical operator runtime state is disabled")
    elif resolved is not True:
        raise ResearchDispatchError("physical operator resolver returned an unsupported record")


def _resolver_record_is_disabled(record: Mapping[str, Any]) -> bool:
    disabled_words = {"blocked", "disabled", "inactive", "retired", "unavailable"}

    def _disabled(value: Any) -> bool:
        if value is False:
            return True
        if isinstance(value, str):
            return value.strip().casefold() in disabled_words
        if isinstance(value, Mapping):
            return any(
                _disabled(value.get(key))
                for key in ("active", "availability", "enabled", "runtime_state", "status")
                if key in value
            )
        return False

    return any(
        _disabled(record.get(key))
        for key in ("availability", "runtime_state", "state")
        if key in record
    )


def _failed_result_from_exception(
    node_request: dict,
    exc: Exception,
    *,
    secret_values: Iterable[str] = (),
) -> dict:
    secrets = tuple(str(value) for value in secret_values if str(value))
    diagnostic_secrets = (*secrets, *_request_body_diagnostic_values(node_request))
    error_type = sanitize_text(
        str(getattr(exc, "error_type", type(exc).__name__)), diagnostic_secrets
    )
    message = str(getattr(exc, "message", exc))
    if isinstance(exc, ResearchTransportError):
        message = json.dumps(exc.to_dict(), sort_keys=True)
    message = sanitize_text(message, diagnostic_secrets)
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


def _bounded_receipt(receipt: Any, *, secret_values: Iterable[str]) -> Any:
    sanitized = sanitize_diagnostic_value(
        receipt,
        explicit_secret_values=secret_values,
        omit_request_bodies=True,
        max_depth=4,
        max_items=20,
        max_string_chars=512,
    )
    serialized = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, default=repr)
    if len(serialized.encode("utf-8")) <= 8_192:
        return sanitized
    summary = sanitize_text(serialized[:7_500], secret_values)
    return {"receipt_summary": f"{summary}...[TRUNCATED]"}


def _sanitize_result_request_echo(result: dict, request_values: Iterable[str]) -> dict:
    protected = tuple(
        sorted({str(value) for value in request_values if str(value)}, key=len, reverse=True)
    )
    if not protected:
        return copy.deepcopy(result)
    safe = copy.deepcopy(result)
    body_keys = {
        "body",
        "input",
        "inputs",
        "messages",
        "payload",
        "prompt",
        "request",
        "request_body",
        "research_node_request",
    }
    remaining_nodes = [10_000]

    def _walk(value: Any) -> Any:
        remaining_nodes[0] -= 1
        if remaining_nodes[0] < 0:
            raise ResearchDispatchError("result exceeds request-echo sanitization bound")
        if isinstance(value, Mapping):
            output: dict[str, Any] = {}
            for raw_key, nested in value.items():
                key = str(raw_key)
                normalized = key.casefold().replace("-", "_")
                output[key] = (
                    "[OMITTED_REQUEST_BODY]" if normalized in body_keys else _walk(nested)
                )
            return output
        if isinstance(value, list):
            return [_walk(nested) for nested in value]
        if isinstance(value, tuple):
            return [_walk(nested) for nested in value]
        if isinstance(value, str):
            scrubbed = value
            for protected_value in protected:
                scrubbed = scrubbed.replace(protected_value, "[OMITTED_REQUEST_BODY]")
            return scrubbed
        return value

    for field in ("errors", "evidence", "limitations", "model_provider_usage"):
        if field in safe:
            safe[field] = _walk(safe[field])
    return safe


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


def _request_body_diagnostic_values(node_request: dict) -> tuple[str, ...]:
    typed_inputs = node_request.get("typed_inputs") if isinstance(node_request, dict) else None
    payload = typed_inputs.get("payload") if isinstance(typed_inputs, dict) else None
    collected: set[str] = set()
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, Mapping):
            for raw_key, nested in value.items():
                if isinstance(raw_key, str) and len(raw_key) >= 4:
                    collected.add(raw_key)
                pending.append(nested)
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
        elif isinstance(value, str) and len(value) >= 4:
            collected.add(value)
    if payload is not None:
        try:
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=repr)
        except (TypeError, ValueError, RecursionError):
            raise ResearchDispatchError("typed input payload is not bounded JSON") from None
        if len(serialized.encode("utf-8")) > DEFAULT_MAX_REQUEST_BYTES:
            raise ResearchDispatchError("typed input payload exceeds diagnostic safety bound")
        collected.add(serialized)
    return tuple(sorted(collected, key=len, reverse=True))
