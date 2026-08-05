"""Validation helpers for research node request and result envelopes."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import jsonschema


class ResearchResultValidationError(ValueError):
    """Raised when a research node envelope violates the dispatch contract."""


TERMINAL_STATUSES = {"completed", "failed", "blocked", "cancelled"}
NONTERMINAL_STATUSES = {"pending", "ready", "running", "awaiting_human", "awaiting_external"}
_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")


def validate_node_request(request: dict, schema_path: Path) -> None:
    original = copy.deepcopy(request)
    _validate_schema(request, schema_path)
    if request.get("logical_operator", {}).get("operator_kind") != "logical":
        raise ResearchResultValidationError("logical_operator must have operator_kind=logical")
    if request.get("physical_operator", {}).get("operator_kind") != "physical":
        raise ResearchResultValidationError("physical_operator must have operator_kind=physical")
    _validate_authorization(request)
    if request != original:
        raise ResearchResultValidationError("validate_node_request mutated input")


def validate_node_result(result: dict, schema_path: Path) -> None:
    original = copy.deepcopy(result)
    _validate_schema(result, schema_path)
    status = str(result.get("status") or "")
    terminal = bool(result.get("status_is_terminal"))
    if status in TERMINAL_STATUSES and not terminal:
        raise ResearchResultValidationError("terminal status must set status_is_terminal=true")
    if status in NONTERMINAL_STATUSES and terminal:
        raise ResearchResultValidationError("nonterminal status must set status_is_terminal=false")
    if status == "completed":
        if not result.get("evidence"):
            raise ResearchResultValidationError("completed result must include evidence")
        if result.get("errors"):
            raise ResearchResultValidationError("completed result must not include errors")
    if status == "failed" and not result.get("errors"):
        raise ResearchResultValidationError("failed result must include errors")
    for artifact in result.get("output_artifacts") or []:
        _validate_optional_sha256(artifact.get("sha256"), "output_artifacts.sha256")
    for record in result.get("hashes") or []:
        if record.get("algorithm") != "sha256":
            raise ResearchResultValidationError("hash algorithm must be sha256")
        _validate_optional_sha256(record.get("value"), "hashes.value")
    assertion = result.get("secret_redaction_assertion")
    if not isinstance(assertion, dict) or assertion.get("no_secrets_observed") is not True:
        raise ResearchResultValidationError("secret redaction assertion is required")
    if result != original:
        raise ResearchResultValidationError("validate_node_result mutated input")


def validate_result_identity(request: dict, result: dict) -> None:
    for key in ("task_id", "run_id", "workflow_id", "node_id"):
        if request.get(key) != result.get(key):
            raise ResearchResultValidationError(f"result {key} does not match request")


def validate_result_scopes(request: dict, result: dict, artifact_root: Path) -> None:
    root = Path(artifact_root).resolve()
    write_scopes = list(request.get("write_scope") or [])
    read_scopes = list(request.get("read_scope") or [])
    approved = set(request.get("authorization", {}).get("approved_capabilities") or [])
    requested_physical = set(request.get("physical_operator", {}).get("capabilities") or [])
    requested_logical = set(request.get("logical_operator", {}).get("capabilities") or [])

    if not requested_logical.issubset(approved):
        raise ResearchResultValidationError("logical operator capabilities exceed authorization")
    if not requested_physical.issubset(approved | {"bounded_worker"}):
        raise ResearchResultValidationError("physical operator capabilities exceed authorization")

    allowed_write_paths = [_resolve_declared_path(root, scope) for scope in write_scopes]
    if not allowed_write_paths:
        raise ResearchResultValidationError("request must declare at least one write scope")

    for artifact in result.get("output_artifacts") or []:
        artifact_path = _resolve_declared_path(root, artifact.get("path"))
        if not _is_under_or_equal(artifact_path, root):
            raise ResearchResultValidationError("artifact path escapes artifact_root")
        if not any(_is_under_or_equal(artifact_path, scope) for scope in allowed_write_paths):
            raise ResearchResultValidationError("artifact path escapes write_scope")

    for scope in [*write_scopes, *read_scopes]:
        resolved = _resolve_declared_path(root, scope)
        if not _is_under_or_equal(resolved, root):
            raise ResearchResultValidationError("declared scope escapes artifact_root")


def _validate_schema(instance: dict, schema_path: Path) -> None:
    if not isinstance(instance, dict):
        raise ResearchResultValidationError("instance must be a dictionary")
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(instance)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.path)
        prefix = f"{location}: " if location else ""
        raise ResearchResultValidationError(f"{prefix}{exc.message}") from exc


def _validate_authorization(request: dict) -> None:
    authorization = request.get("authorization") or {}
    if authorization.get("allow_live_provider"):
        if authorization.get("allow_network") is not True:
            raise ResearchResultValidationError("live provider requires allow_network=true")
        if not str(authorization.get("approval_ref") or "").strip():
            raise ResearchResultValidationError("live provider requires approval_ref")
    if any(not str(item).strip() for item in request.get("read_scope") or []):
        raise ResearchResultValidationError("read_scope entries must be non-empty")
    if any(not str(item).strip() for item in request.get("write_scope") or []):
        raise ResearchResultValidationError("write_scope entries must be non-empty")


def _validate_optional_sha256(value: Any, field: str) -> None:
    if value is not None and not _SHA256_RE.match(str(value)):
        raise ResearchResultValidationError(f"{field} must be a sha256 hex digest")


def _resolve_declared_path(root: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ResearchResultValidationError("path must be a non-empty string")
    text = raw.strip().replace("\\", "/")
    if "\x00" in text:
        raise ResearchResultValidationError("path must not contain NUL")
    if _looks_windows_absolute(text):
        path = Path(PureWindowsPath(text))
    elif PurePosixPath(text).is_absolute():
        path = Path(text)
    else:
        path = root / text
    return path.resolve(strict=False)


def _looks_windows_absolute(text: str) -> bool:
    return PureWindowsPath(text).is_absolute() or bool(re.match(r"^[A-Za-z]:/", text))


def _is_under_or_equal(path: Path, parent: Path) -> bool:
    path_text = _casefold_path(path)
    parent_text = _casefold_path(parent)
    if path_text == parent_text:
        return True
    separator = "\\" if "\\" in parent_text else "/"
    if not parent_text.endswith(("/", "\\")):
        parent_text = parent_text + separator
    return path_text.startswith(parent_text)


def _casefold_path(path: Path) -> str:
    text = str(path.resolve(strict=False)).replace("\\", "/")
    return text.casefold()
