"""Verifier for browser profile login recovery evidence.

Checks included:
  - browser_profile_ref exists / includes profile_id
  - requested account hits profile allowlist (if allowlist is configured)
  - no plaintext secret fields (password/otp/cookie) are recorded
  - success path requires logged_in_state_verified=True
  - lease_released must be true
"""
from __future__ import annotations

from typing import Any

from .. import contracts


_SECRET_KEYS = {"password", "passwd", "otp", "cookie"}
_REDACTED_LIKE = {"redacted", "<redacted>", "[redacted]", "n/a", "na", "none", "null"}


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _looks_redacted(value: str) -> bool:
    clean = value.strip().lower()
    if not clean:
        return True
    if clean in _REDACTED_LIKE:
        return True
    if set(clean) <= {"*", "x", "*", "#"}:
        return True
    return False


def _iter_strings(payload: Any):
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key, value
            if isinstance(value, (dict, list, tuple)):
                for child_key, child_value in _iter_strings(value):
                    yield child_key, child_value
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            for key, value in _iter_strings(item):
                yield key, value


def _has_plain_secret(payload: Any) -> tuple[bool, str | None]:
    for key, value in _iter_strings(payload):
        if not isinstance(key, str):
            continue
        lowered = key.lower()
        if not any(secret in lowered for secret in _SECRET_KEYS):
            continue
        if not isinstance(value, str):
            continue
        v = _normalize_string(value)
        if not _looks_redacted(v):
            return True, key
    return False, None


def _normalize_report(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    return contracts.login_recovery_report(payload)


def verify_profile_login(
    *,
    profile_ref: dict[str, Any] | str | None = None,
    login_recovery_report: dict[str, Any] | None = None,
    account_identifier: str | None = None,
) -> dict[str, Any]:
    """Run minimal invariants for browser profile login recovery evidence."""
    result = {
        "ok": True,
        "checks": {
            "profile_ref_exists": False,
            "allowlist_hit": False,
            "no_plaintext_secrets": False,
            "success_logged_in_verified": False,
            "lease_released": False,
        },
        "errors": [],
    }

    normalized_profile_ref = None
    if profile_ref is not None:
        try:
            normalized_profile_ref = contracts.browser_profile_ref(profile_ref)
        except ValueError:
            result["ok"] = False
            result["errors"].append("profile_ref_invalid")

    if normalized_profile_ref is None:
        result["ok"] = False
        result["errors"].append("profile_ref_missing")
    else:
        result["checks"]["profile_ref_exists"] = bool(normalized_profile_ref.get("profile_id"))
        if not result["checks"]["profile_ref_exists"]:
            result["ok"] = False
            result["errors"].append("profile_ref_missing")

    normalized_report = _normalize_report(login_recovery_report)
    if not isinstance(login_recovery_report, dict):
        result["ok"] = False
        result["errors"].append("login_recovery_report_missing")

    if normalized_profile_ref is None and isinstance(normalized_report.get("profile_ref"), dict):
        try:
            normalized_profile_ref = contracts.browser_profile_ref(normalized_report.get("profile_ref"))
        except ValueError:
            result["ok"] = False
            result["errors"].append("profile_ref_invalid")

    allowlist = (normalized_profile_ref or {}).get("allowed_account_identifiers") or []
    requested_account = _normalize_string(
        account_identifier or normalized_report.get("account_identifier") or ""
    )
    if allowlist:
        if requested_account and requested_account.lower() in {str(i).lower() for i in allowlist}:
            result["checks"]["allowlist_hit"] = True
        else:
            result["ok"] = False
            result["errors"].append("allowlist_miss")
    else:
        result["checks"]["allowlist_hit"] = True

    has_secret, secret_key = _has_plain_secret(normalized_report)
    result["checks"]["no_plaintext_secrets"] = not has_secret
    if has_secret:
        result["ok"] = False
        result["errors"].append(f"plaintext_secret_detected:{secret_key}")

    success = bool(normalized_report.get("success"))
    if success:
        if bool(normalized_report.get("logged_in_state_verified")):
            result["checks"]["success_logged_in_verified"] = True
        else:
            result["ok"] = False
            result["errors"].append("logged_in_state_not_verified_on_success")

    if bool(normalized_report.get("lease_released")):
        result["checks"]["lease_released"] = True
    else:
        result["ok"] = False
        result["errors"].append("lease_not_released")

    if result["checks"]["profile_ref_exists"] and result["checks"]["allowlist_hit"] and result["checks"]["no_plaintext_secrets"] and result["checks"]["lease_released"]:
        if success:
            result["checks"]["success_logged_in_verified"] = True

    return result
