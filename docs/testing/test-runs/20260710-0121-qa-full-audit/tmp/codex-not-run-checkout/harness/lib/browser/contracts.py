"""Schema helpers for browser profile/session/login contracts.

These helper functions are intentionally minimal and deterministic: they produce
normalized dictionaries that can be passed between operators, leases and verifiers
without requiring dataclass dependencies.
"""
from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_profile_id(profile_id: Any) -> str:
    value = str(profile_id or "").strip()
    if not value:
        raise ValueError("profile_id is required")
    return value


def _normalise_list(value: Any) -> list[str]:
    if not value:
        return []
    if not isinstance(value, (list, tuple)):
        value = [value]
    normalized: list[str] = []
    for item in value:
        val = str(item or "").strip()
        if val and val not in normalized:
            normalized.append(val)
    return normalized


def _normalise_path(value: Any) -> str | None:
    val = str(value or "").strip()
    if not val:
        return None
    return str(Path(val))


def _normalise_status(value: Any, *, default: str) -> str:
    text = str(value or "").strip().lower()
    return text or default


def browser_profile_ref(
    profile_ref: dict[str, Any] | str | None = None,
    *,
    profile_id: str | None = None,
    storage_state_ref: str | None = None,
    allowed_account_identifiers: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Build a normalized browser_profile_ref object."""
    data: dict[str, Any] = {}
    if isinstance(profile_ref, dict):
        data = dict(profile_ref)
    elif isinstance(profile_ref, str):
        profile_id = profile_id or str(profile_ref)

    resolved_profile_id = (
        profile_id
        or str(data.get("profile_id") or "").strip()
    )
    normalized_profile_id = _normalise_profile_id(resolved_profile_id)

    normalized: dict[str, Any] = {
        "schema": "browser.profile_ref.v1",
        "profile_id": normalized_profile_id,
        "storage_state_ref": _normalise_path(
            storage_state_ref
            if storage_state_ref is not None
            else data.get("storage_state_ref")
        ),
        "allowed_account_identifiers": _normalise_list(
            allowed_account_identifiers
            if allowed_account_identifiers is not None
            else data.get("allowed_account_identifiers")
        ),
    }
    if data.get("metadata") is not None:
        normalized["metadata"] = dict(data["metadata"])
    return normalized


def browser_session_contract(
    session_contract: dict[str, Any] | None = None,
    *,
    profile_ref: dict[str, Any] | str | None = None,
    runtime: str = "default",
    mode: str = "default",
    status: str = "active",
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build / normalize a browser session contract object."""
    data = dict(session_contract or {})
    normalized_profile_ref = (
        browser_profile_ref(data.get("profile_ref"))
        if data.get("profile_ref") is not None
        else None
    )
    if isinstance(profile_ref, dict):
        normalized_profile_ref = browser_profile_ref(profile_ref)
    elif isinstance(profile_ref, str):
        normalized_profile_ref = browser_profile_ref(profile_id=profile_ref)
    elif profile_ref is not None:
        normalized_profile_ref = browser_profile_ref(profile_id=str(profile_ref))

    if normalized_profile_ref is None:
        raise ValueError("profile_ref is required for browser session contract")

    resolved_session_id = (
        session_id
        or data.get("session_id")
        or f"{normalized_profile_ref['profile_id']}:{uuid.uuid4().hex}"
    )
    normalized = {
        "schema": "browser.session_contract.v1",
        "session_id": str(resolved_session_id).strip(),
        "status": _normalise_status(status or data.get("status"), default="active"),
        "runtime": str(runtime or data.get("runtime") or "default").strip() or "default",
        "mode": str(mode or data.get("mode") or "default").strip() or "default",
        "acquired_at": data.get("acquired_at") or _now_iso(),
        "profile_ref": normalized_profile_ref,
        "metadata": dict(metadata or data.get("metadata") or {}),
    }

    if data.get("created_at") is not None:
        normalized["created_at"] = data["created_at"]
    else:
        normalized["created_at"] = _now_iso()

    return normalized


def login_recovery_report(
    login_recovery_report: dict[str, Any] | None = None,
    *,
    profile_ref: dict[str, Any] | str | None = None,
    status: str = "success",
    logged_in_state_verified: bool = False,
    lease_released: bool = False,
    account_identifier: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build / normalize a login recovery report object."""
    data = dict(login_recovery_report or {})
    resolved_profile_ref = (
        browser_profile_ref(data.get("profile_ref"))
        if data.get("profile_ref") is not None
        else None
    )
    if isinstance(profile_ref, dict):
        resolved_profile_ref = browser_profile_ref(profile_ref)
    elif isinstance(profile_ref, str):
        resolved_profile_ref = browser_profile_ref(profile_id=profile_ref)
    elif profile_ref is not None:
        resolved_profile_ref = browser_profile_ref(profile_id=str(profile_ref))

    resolved_status = _normalise_status(
        status or data.get("status"),
        default="failed",
    )
    success = bool(data.get("success", resolved_status == "success"))

    normalized: dict[str, Any] = {
        "schema": "browser.login_recovery_report.v1",
        "status": resolved_status,
        "success": bool(success),
        "logged_in_state_verified": bool(data.get("logged_in_state_verified", logged_in_state_verified)),
        "lease_released": bool(data.get("lease_released", lease_released)),
        "account_identifier": str(account_identifier or data.get("account_identifier") or "").strip() or None,
        "profile_ref": resolved_profile_ref,
        "created_at": data.get("created_at") or _now_iso(),
        "details": dict(details or data.get("details") or {}),
    }
    return normalized
