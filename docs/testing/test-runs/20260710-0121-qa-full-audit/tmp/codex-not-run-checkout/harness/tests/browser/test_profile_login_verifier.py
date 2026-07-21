"""Tests for harness/lib/browser/verifiers/profile_login_verifier.py."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from browser import contracts  # noqa: E402
from browser.verifiers import profile_login_verifier as verifier  # noqa: E402


def test_profile_login_verifier_happy_path() -> None:
    profile_ref = contracts.browser_profile_ref(
        profile_id="alice",
        storage_state_ref="/tmp/alice-state.json",
        allowed_account_identifiers=["alice@example.com", "ops@example.com"],
    )
    report = contracts.login_recovery_report(
        profile_ref=profile_ref,
        status="success",
        logged_in_state_verified=True,
        lease_released=True,
        account_identifier="alice@example.com",
        details={"step": "login"},
    )
    result = verifier.verify_profile_login(
        profile_ref=profile_ref,
        login_recovery_report=report,
        account_identifier="alice@example.com",
    )
    assert result["ok"] is True
    assert result["checks"]["profile_ref_exists"] is True
    assert result["checks"]["allowlist_hit"] is True
    assert result["checks"]["no_plaintext_secrets"] is True
    assert result["checks"]["success_logged_in_verified"] is True
    assert result["checks"]["lease_released"] is True


def test_profile_login_verifier_blocked_by_allowlist() -> None:
    profile_ref = contracts.browser_profile_ref(
        profile_id="alice",
        allowed_account_identifiers=["alice@example.com"],
    )
    report = contracts.login_recovery_report(
        profile_ref=profile_ref,
        status="success",
        logged_in_state_verified=True,
        lease_released=True,
        account_identifier="bob@example.com",
    )
    result = verifier.verify_profile_login(
        profile_ref=profile_ref,
        login_recovery_report=report,
        account_identifier="bob@example.com",
    )
    assert result["ok"] is False
    assert "allowlist_miss" in result["errors"]


def test_profile_login_verifier_requires_no_plaintext_secrets() -> None:
    profile_ref = contracts.browser_profile_ref(
        profile_id="alice",
        allowed_account_identifiers=["alice@example.com"],
    )
    report = contracts.login_recovery_report(
        profile_ref=profile_ref,
        status="success",
        logged_in_state_verified=True,
        lease_released=True,
        account_identifier="alice@example.com",
        details={"password": "super-secret"},
    )
    result = verifier.verify_profile_login(
        profile_ref=profile_ref,
        login_recovery_report=report,
        account_identifier="alice@example.com",
    )
    assert result["ok"] is False
    assert any("plaintext_secret_detected" in item for item in result["errors"])


def test_profile_login_verifier_rejects_success_without_login_state_verified() -> None:
    profile_ref = contracts.browser_profile_ref(
        profile_id="alice",
        allowed_account_identifiers=["alice@example.com"],
    )
    report = contracts.login_recovery_report(
        profile_ref=profile_ref,
        status="success",
        logged_in_state_verified=False,
        lease_released=True,
        account_identifier="alice@example.com",
    )
    result = verifier.verify_profile_login(
        profile_ref=profile_ref,
        login_recovery_report=report,
        account_identifier="alice@example.com",
    )
    assert result["ok"] is False
    assert "logged_in_state_not_verified_on_success" in result["errors"]
