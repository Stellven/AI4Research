"""Tests for browser login recovery and runtime control helpers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from browser import runtime_control  # noqa: E402
from browser.login_detector import classify_login_state  # noqa: E402
from browser.login_recovery import build_login_recovery_report, select_executor  # noqa: E402


def test_login_detector_flags_cloudflare_as_human_gate() -> None:
    result = classify_login_state(
        service="chatgpt",
        error_text="chatgpt_cloudflare_challenge_detected",
    )
    assert result["state"] == "human_gate_required"
    assert result["reason"] == "cloudflare"
    assert result["human_required"] is True


def test_login_recovery_selects_playwright_for_precise_control() -> None:
    executor = select_executor(
        runtime_owner="browser_use",
        wrapper_kind="gemini",
        requires_precise_page_control=True,
    )
    assert executor["kind"] == "playwright_cdp_executor"


def test_runtime_control_initializes_and_finalizes_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_PROFILE_REGISTRY_ROOT", str(tmp_path / "profiles"))
    monkeypatch.setenv("BROWSER_PROFILE_LEASE_DIR", str(tmp_path / "leases"))
    request_dir = tmp_path / "request"
    ctx = runtime_control.initialize_runtime_contract(
        request_dir=request_dir,
        service="chatgpt",
        runtime_owner="browser_use",
        wrapper_kind="chatgpt",
        profile_directory="Profile 7",
        user_data_dir=str(tmp_path / "chrome"),
        staged_user_data_dir=str(tmp_path / "staged"),
        account_identifier="alice@example.com",
        control_modes={
            "browser_use_session": True,
            "playwright_cdp_attach": False,
            "webwright_bridge": False,
        },
        task_id="task-123",
    )
    assert (request_dir / "browser-profile-ref.json").exists()
    assert (request_dir / "browser-session-contract.json").exists()
    runtime_control.update_runtime_endpoint(
        ctx,
        cdp_url="http://127.0.0.1:9222",
        browser_session_ref="browser-use-session://chatgpt/chatgpt/alice",
    )
    report = runtime_control.finalize_runtime_contract(
        ctx,
        success=True,
        page_state={"url": "https://chatgpt.com/"},
        logged_in_state_verified=True,
        details={"case": "unit"},
    )
    assert report is not None
    assert report["success"] is True
    assert (request_dir / "login-recovery-report.json").exists()


def test_login_recovery_report_contains_executor_and_policy() -> None:
    report = build_login_recovery_report(
        service="gemini",
        profile_ref="gemini/google-main",
        runtime_owner="browser_use",
        wrapper_kind="gemini",
        account_identifier="owner@example.com",
        allowlist=["owner@example.com"],
        requires_precise_page_control=True,
        lease_released=True,
        logged_in_state_verified=True,
    )
    assert report["success"] is True
    assert report["details"]["executor"]["kind"] == "playwright_cdp_executor"
    assert report["details"]["policy"]["service"] == "gemini"
