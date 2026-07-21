"""Runtime-agnostic browser auth policy normalization."""
from __future__ import annotations

from typing import Any


DEFAULT_SAFE_AUTO_STEPS = [
    "click_login",
    "click_continue_with_google",
    "select_allowed_account",
    "click_continue",
]

DEFAULT_HUMAN_GATES = [
    "password",
    "otp",
    "passkey",
    "cloudflare",
    "captcha",
]


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        value = [value]
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def browser_auth_policy(
    payload: dict[str, Any] | None = None,
    *,
    service: str | None = None,
    profile_id: str | None = None,
    allowed_accounts: list[str] | tuple[str, ...] | None = None,
    safe_auto_steps: list[str] | tuple[str, ...] | None = None,
    human_gate: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    data = dict(payload or {})
    normalized_service = str(service or data.get("service") or "").strip().lower()
    normalized_profile_id = str(profile_id or data.get("profile_id") or "").strip()
    if not normalized_service:
        raise ValueError("service is required")
    if not normalized_profile_id:
        raise ValueError("profile_id is required")
    return {
        "schema": "browser.auth_policy.v1",
        "service": normalized_service,
        "profile_id": normalized_profile_id,
        "allowed_accounts": _normalize_list(
            allowed_accounts if allowed_accounts is not None else data.get("allowed_accounts")
        ),
        "safe_auto_steps": _normalize_list(
            safe_auto_steps if safe_auto_steps is not None else data.get("safe_auto_steps")
        )
        or list(DEFAULT_SAFE_AUTO_STEPS),
        "human_gate": _normalize_list(
            human_gate if human_gate is not None else data.get("human_gate")
        )
        or list(DEFAULT_HUMAN_GATES),
    }
