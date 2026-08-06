"""Validation helpers for research node request and result envelopes."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import jsonschema

from .transport import (
    DEFAULT_MAX_REQUEST_BYTES,
    ResearchRequestBoundaryError,
    collect_bounded_request_body_strings,
    contains_sensitive_diagnostic,
    sanitize_text,
)


class ResearchResultValidationError(ValueError):
    """Raised when a research node envelope violates the dispatch contract."""


TERMINAL_STATUSES = {"completed", "failed", "blocked", "cancelled"}
NONTERMINAL_STATUSES = {"pending", "ready", "running", "awaiting_human", "awaiting_external"}
_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")


def _fs_path(path: Path) -> str:
    resolved = str(Path(path).resolve(strict=False))
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def _exists(path: Path) -> bool:
    return os.path.exists(_fs_path(path))


def _is_file(path: Path) -> bool:
    return os.path.isfile(_fs_path(path))


def _is_dir(path: Path) -> bool:
    return os.path.isdir(_fs_path(path))


def validate_node_request(
    request: dict,
    schema_path: Path,
    *,
    secret_values: Iterable[str] = (),
) -> None:
    original = copy.deepcopy(request)
    schema_secrets = _request_body_diagnostic_values(request, secret_values)
    _validate_schema(request, schema_path, secret_values=schema_secrets)
    if request.get("logical_operator", {}).get("operator_kind") != "logical":
        raise ResearchResultValidationError("logical_operator must have operator_kind=logical")
    if request.get("physical_operator", {}).get("operator_kind") != "physical":
        raise ResearchResultValidationError("physical_operator must have operator_kind=physical")
    _validate_authorization(request)
    if request != original:
        raise ResearchResultValidationError("validate_node_request mutated input")


def validate_node_result(
    result: dict,
    schema_path: Path,
    *,
    secret_values: Iterable[str] = (),
    diagnostic_values: Iterable[str] = (),
) -> None:
    original = copy.deepcopy(result)
    _validate_schema(
        result,
        schema_path,
        secret_values=(*secret_values, *diagnostic_values),
    )
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
    if contains_sensitive_diagnostic(result, explicit_secret_values=secret_values):
        raise ResearchResultValidationError("result contains unredacted sensitive diagnostics")
    if result != original:
        raise ResearchResultValidationError("validate_node_result mutated input")


def validate_result_identity(request: dict, result: dict) -> None:
    for key in ("task_id", "run_id", "workflow_id", "node_id"):
        if request.get(key) != result.get(key):
            raise ResearchResultValidationError(f"result {key} does not match request")


def validate_request_artifact_scopes(request: dict, artifact_root: Path) -> None:
    """Validate declared read scopes and all concrete input artifact files."""

    root = _existing_artifact_root(artifact_root)
    raw_read_scopes = list(request.get("read_scope") or [])
    input_refs = list(request.get("input_artifact_refs") or [])
    if input_refs and not raw_read_scopes:
        raise ResearchResultValidationError("input artifacts require declared read_scope")

    read_scopes: list[Path] = []
    for raw_scope in raw_read_scopes:
        raw_path = _declared_path_without_resolution(root, raw_scope)
        resolved = raw_path.resolve(strict=False)
        if not _is_under_or_equal(resolved, root):
            raise ResearchResultValidationError("declared read_scope escapes artifact_root")
        if not _exists(resolved):
            raise ResearchResultValidationError("declared read_scope does not exist")
        _reject_reparse_escape(root, raw_path, [resolved])
        read_scopes.append(resolved)

    seen_ids: set[str] = set()
    for artifact in input_refs:
        artifact_id = str(artifact.get("artifact_id") or "")
        if artifact_id in seen_ids:
            raise ResearchResultValidationError("duplicate input artifact_id")
        seen_ids.add(artifact_id)
        raw_path = _declared_path_without_resolution(root, artifact.get("path"))
        resolved = raw_path.resolve(strict=False)
        if not _is_under_or_equal(resolved, root):
            raise ResearchResultValidationError("input artifact path escapes artifact_root")
        if not any(_is_under_or_equal(resolved, scope) for scope in read_scopes):
            raise ResearchResultValidationError("input artifact path escapes read_scope")
        _reject_reparse_escape(root, raw_path, read_scopes)
        if not _exists(resolved) or not _is_file(resolved):
            raise ResearchResultValidationError("declared input artifact file does not exist")
        declared_hash = artifact.get("sha256")
        if declared_hash is not None and str(declared_hash).casefold() != _sha256_file(resolved):
            raise ResearchResultValidationError("declared input artifact sha256 does not match file")


def validate_result_scopes(
    request: dict,
    result: dict,
    artifact_root: Path,
    *,
    secret_values: Iterable[str] = (),
) -> None:
    root = _existing_artifact_root(artifact_root)
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

    artifacts_by_id: dict[str, tuple[Path, str]] = {}
    for artifact in result.get("output_artifacts") or []:
        raw_artifact_path = _declared_path_without_resolution(root, artifact.get("path"))
        artifact_path = raw_artifact_path.resolve(strict=False)
        if not _is_under_or_equal(artifact_path, root):
            raise ResearchResultValidationError("artifact path escapes artifact_root")
        if not any(_is_under_or_equal(artifact_path, scope) for scope in allowed_write_paths):
            raise ResearchResultValidationError("artifact path escapes write_scope")
        _reject_reparse_escape(root, raw_artifact_path, allowed_write_paths)
        if not _exists(artifact_path) or not _is_file(artifact_path):
            raise ResearchResultValidationError("declared output artifact file does not exist")
        actual_hash = _sha256_file(artifact_path)
        declared_hash = artifact.get("sha256")
        if declared_hash is not None and str(declared_hash).casefold() != actual_hash:
            raise ResearchResultValidationError("declared output artifact sha256 does not match file")
        artifact_id = str(artifact.get("artifact_id") or "")
        if artifact_id in artifacts_by_id:
            raise ResearchResultValidationError("duplicate output artifact_id")
        artifacts_by_id[artifact_id] = (artifact_path, actual_hash)

    seen_hash_ids: set[str] = set()
    for record in result.get("hashes") or []:
        hash_id = str(record.get("hash_id") or "")
        if hash_id in seen_hash_ids:
            raise ResearchResultValidationError("duplicate artifact hash record")
        seen_hash_ids.add(hash_id)
        if hash_id not in artifacts_by_id:
            raise ResearchResultValidationError("orphan hash record has no output artifact")
        actual_hash = artifacts_by_id[hash_id][1]
        if str(record.get("value") or "").casefold() != actual_hash:
            raise ResearchResultValidationError("artifact hash record does not match file")

    for evidence in result.get("evidence") or []:
        artifact_id = evidence.get("artifact_id")
        if artifact_id is not None and str(artifact_id) not in artifacts_by_id:
            raise ResearchResultValidationError("evidence references an unknown output artifact")

    for scope in [*write_scopes, *read_scopes]:
        resolved = _resolve_declared_path(root, scope)
        if not _is_under_or_equal(resolved, root):
            raise ResearchResultValidationError("declared scope escapes artifact_root")


def _validate_schema(
    instance: dict,
    schema_path: Path,
    *,
    secret_values: Iterable[str] = (),
) -> None:
    if not isinstance(instance, dict):
        raise ResearchResultValidationError("instance must be a dictionary")
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(instance)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.path)
        prefix = f"{location}: " if location else ""
        safe_message = sanitize_text(f"{prefix}{exc.message}", secret_values)
        raise ResearchResultValidationError(safe_message[:500]) from exc


def _existing_artifact_root(artifact_root: Path) -> Path:
    root = Path(artifact_root).resolve(strict=False)
    if not _is_dir(root):
        raise ResearchResultValidationError("artifact_root must be an existing directory")
    return root


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
    return _declared_path_without_resolution(root, raw).resolve(strict=False)


def _declared_path_without_resolution(root: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ResearchResultValidationError("path must be a non-empty string")
    text = raw.strip().replace("\\", "/")
    if "\x00" in text:
        raise ResearchResultValidationError("path must not contain NUL")
    if _looks_windows_absolute(text):
        if os.name != "nt":
            raise ResearchResultValidationError("Windows absolute path is invalid on this platform")
        path = Path(PureWindowsPath(text))
    elif PurePosixPath(text).is_absolute():
        path = Path(text)
    else:
        path = root / text
    return path


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
    return text.casefold() if os.name == "nt" else text


def _reject_reparse_escape(root: Path, artifact_path: Path, scopes: list[Path]) -> None:
    """Resolve every existing reparse/symlink component and reject escapes."""

    try:
        relative = artifact_path.relative_to(root)
    except ValueError as exc:
        raise ResearchResultValidationError("artifact path escapes artifact_root") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if not _exists(current) and not current.is_symlink():
            continue
        if _is_reparse_point(current):
            resolved = current.resolve(strict=True)
            if not _is_under_or_equal(resolved, root):
                raise ResearchResultValidationError("artifact reparse point escapes artifact_root")
            if not any(_is_under_or_equal(resolved, scope) for scope in scopes):
                raise ResearchResultValidationError("artifact reparse point escapes write_scope")


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        stat_result = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat_result, "st_file_attributes", 0)
    return bool(reparse_flag & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(_fs_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_body_diagnostic_values(
    request: dict,
    explicit_secret_values: Iterable[str],
) -> tuple[str, ...]:
    collected = {str(item) for item in explicit_secret_values if str(item)}
    try:
        collected.update(
            collect_bounded_request_body_strings(
                request,
                max_request_bytes=DEFAULT_MAX_REQUEST_BYTES,
            )
        )
    except ResearchRequestBoundaryError as exc:
        raise ResearchResultValidationError(exc.message) from None
    return tuple(sorted(collected, key=len, reverse=True))
