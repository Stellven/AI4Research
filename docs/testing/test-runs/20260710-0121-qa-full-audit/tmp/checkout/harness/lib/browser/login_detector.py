"""Login-wall and human-gate detection for browser wrappers."""
from __future__ import annotations

from typing import Any


def classify_login_state(
    *,
    service: str,
    error_text: str | None = None,
    page_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sample = "\n".join(
        [
            str(service or ""),
            str(error_text or ""),
            str((page_state or {}).get("title") or ""),
            str((page_state or {}).get("url") or ""),
            str((page_state or {}).get("login_wall") or ""),
            str((page_state or {}).get("challenge_wall") or ""),
            str((page_state or {}).get("text_excerpt") or ""),
        ]
    ).lower()

    reason = "healthy"
    state = "healthy"
    human_required = False

    if "cloudflare" in sample or "turnstile" in sample or "challenge" in sample:
        state = "human_gate_required"
        reason = "cloudflare"
        human_required = True
    elif "captcha" in sample:
        state = "human_gate_required"
        reason = "captcha"
        human_required = True
    elif "otp" in sample or "2fa" in sample or "two-factor" in sample:
        state = "human_gate_required"
        reason = "otp"
        human_required = True
    elif "passkey" in sample:
        state = "human_gate_required"
        reason = "passkey"
        human_required = True
    elif "password" in sample:
        state = "human_gate_required"
        reason = "password"
        human_required = True
    elif "login_wall" in sample or "reauth" in sample or "sign in" in sample or "log in" in sample:
        state = "reauth_required"
        reason = "login_wall"

    return {
        "service": str(service or "").strip().lower(),
        "state": state,
        "reason": reason,
        "human_required": human_required,
        "success": state == "healthy",
    }
