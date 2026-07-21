"""Runtime-agnostic login recovery selection and report helpers."""
from __future__ import annotations

from typing import Any

from . import contracts
from .auth_policy import browser_auth_policy
from .executors.browser_use_dom_executor import executor_descriptor as browser_use_dom_descriptor
from .executors.playwright_cdp_executor import executor_descriptor as playwright_cdp_descriptor
from .executors.webwright_bridge import executor_descriptor as webwright_bridge_descriptor
from .login_detector import classify_login_state


def select_executor(
    *,
    runtime_owner: str,
    wrapper_kind: str | None = None,
    requires_precise_page_control: bool = False,
    task_operator: str | None = None,
) -> dict[str, object]:
    task_operator_text = str(task_operator or "").strip().lower()
    if task_operator_text == "webwright":
        return webwright_bridge_descriptor()
    if str(runtime_owner or "").strip().lower() == "browser_use" and requires_precise_page_control:
        return playwright_cdp_descriptor()
    if str(wrapper_kind or "").strip().lower() in {"gemini", "youtube", "diagram", "notebooklm"}:
        return playwright_cdp_descriptor()
    return browser_use_dom_descriptor()


def build_login_recovery_report(
    *,
    service: str,
    profile_ref: dict[str, Any] | str,
    runtime_owner: str,
    wrapper_kind: str | None = None,
    task_operator: str | None = None,
    error_text: str | None = None,
    page_state: dict[str, Any] | None = None,
    account_identifier: str | None = None,
    allowlist: list[str] | tuple[str, ...] | None = None,
    requires_precise_page_control: bool = False,
    lease_released: bool = False,
    logged_in_state_verified: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_profile_ref = contracts.browser_profile_ref(
        profile_ref,
        allowed_account_identifiers=allowlist,
    )
    detector = classify_login_state(service=service, error_text=error_text, page_state=page_state)
    executor = select_executor(
        runtime_owner=runtime_owner,
        wrapper_kind=wrapper_kind,
        requires_precise_page_control=requires_precise_page_control,
        task_operator=task_operator,
    )
    policy = browser_auth_policy(
        service=service,
        profile_id=normalized_profile_ref["profile_id"],
        allowed_accounts=allowlist or normalized_profile_ref.get("allowed_account_identifiers") or [],
    )
    report_details = dict(details or {})
    report_details.update(
        {
            "detector": detector,
            "executor": executor,
            "policy": policy,
        }
    )
    status = "success" if detector.get("success") else str(detector.get("state") or "failed")
    return contracts.login_recovery_report(
        profile_ref=normalized_profile_ref,
        status=status,
        logged_in_state_verified=logged_in_state_verified or bool(detector.get("success")),
        lease_released=lease_released,
        account_identifier=account_identifier,
        details=report_details,
    )
