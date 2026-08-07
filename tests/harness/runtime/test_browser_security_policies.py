"""test_browser_security_policies.py — Unit tests for browser security policies.

Verifies session broker, capability-token checks, secret scrubbing, and state projection.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

import browser_job_runtime as bjrt
from capability_token import CapabilityToken


def test_session_broker_health():
    """Verify session broker manages profile health and maps reauth to WAITING_HUMAN."""
    broker = bjrt.BrowserSessionBroker()

    # Healthy profile
    h1 = broker.get_profile_health("prod_profile", "user1@example.com")
    assert h1["status"] == "healthy"
    assert h1["projected_state"] == "running"
    assert h1["profile_ref"] == "prod_profile"
    assert h1["account_label"] == "user1@example.com"

    # Profile requiring reauth
    h2 = broker.get_profile_health("profile_needs_reauth", "user2@example.com")
    assert h2["status"] == "reauth_required"
    assert h2["projected_state"] == "WAITING_HUMAN"


def test_session_broker_scrubs_secrets():
    """Verify session broker scrubs credentials from profile_ref and account_label if they contain keys/secrets."""
    broker = bjrt.BrowserSessionBroker()
    
    # Passing token in profile_ref should get scrubbed
    h = broker.get_profile_health("sk-12345678901234567890123456789012", "password=my_secret")
    assert h["profile_ref"] == "[SCRUBBED]"
    assert h["account_label"] == "password=[SCRUBBED]"


def test_secret_scrubbing_text():
    """Verify scrub_secrets redacts sensitive headers, tokens, and credentials."""
    raw_log = (
        "INFO: Received request\n"
        "Set-Cookie: session_id=abc123xyz; Path=/; Secure\n"
        "Authorization: Bearer my_secret_oauth_token_value_here\n"
        "Cookie: user=admin; token=secret123\n"
        "apiKey = sk-abcdefghijklmnopqrstuvwxyz123456\n"
        "password: mysecretpassword\n"
    )

    scrubbed = bjrt.scrub_secrets(raw_log)
    assert "Set-Cookie: [SCRUBBED]" in scrubbed
    assert "Authorization: [SCRUBBED]" in scrubbed
    assert "Cookie: [SCRUBBED]" in scrubbed
    assert "apiKey=[SCRUBBED]" in scrubbed
    assert "password=[SCRUBBED]" in scrubbed
    assert "session_id=abc123xyz" not in scrubbed
    assert "my_secret_oauth_token_value_here" not in scrubbed


def test_secret_scrubbing_dict():
    """Verify scrub_dict allows profile_ref and account_label but scrubs secrets."""
    envelope = {
        "profile_ref": "profile_1",
        "account_label": "user@example.com",
        "cookie": "user=admin; token=123",
        "secret_token": "ghp_123456789012345678901234567890123456",
        "nested": {
            "password": "pass",
            "safe_value": "hello"
        }
    }

    scrubbed = bjrt.scrub_dict(envelope)
    assert scrubbed["profile_ref"] == "profile_1"
    assert scrubbed["account_label"] == "user@example.com"
    assert scrubbed["cookie"] == "[SCRUBBED]"
    assert scrubbed["secret_token"] == "[SCRUBBED]"
    assert scrubbed["nested"]["password"] == "[SCRUBBED]"
    assert scrubbed["nested"]["safe_value"] == "hello"


def test_policy_checks_payment_denied():
    """Verify payment actions are always denied during job submission."""
    envelope = {
        "task_id": "T-pay",
        "objective": "Go to billing page and checkout the upgrade package"
    }

    with pytest.raises(PermissionError, match="prohibited payment action"):
        bjrt.submit_browser_job("mini-browser-deepresearch", envelope)


def test_policy_checks_secrets_denied():
    """Verify secrets requests are denied by default or when token denies them."""
    envelope = {
        "task_id": "T-sec",
        "objective": "Fill the form with the API password"
    }

    # Denied by default when no capability token is provided
    with pytest.raises(PermissionError, match="no capability token provided"):
        bjrt.submit_browser_job("mini-browser-deepresearch", envelope)

    # Denied when token denies secrets explicitly
    token_deny = CapabilityToken(
        token_id="tok-deny",
        scopes=["file:write"],
        expires_at="2099-01-01T00:00:00Z",
        actor_id="a1",
        secrets={"allowed": False}
    )
    with pytest.raises(PermissionError, match="capability token denies"):
        bjrt.submit_browser_job("mini-browser-deepresearch", envelope, capability_token=token_deny)

    # Allowed when token permits secrets
    token_allow = CapabilityToken(
        token_id="tok-allow",
        scopes=["file:write"],
        expires_at="2099-01-01T00:00:00Z",
        actor_id="a1",
        secrets={"allowed": True}
    )
    # Should submit successfully
    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope, capability_token=token_allow)
    assert job_id.startswith("job-")


def test_policy_checks_destructive_denied():
    """Verify destructive actions are denied by default or when token denies them."""
    envelope = {
        "task_id": "T-dest",
        "objective": "Execute rm -rf on the old configuration folder"
    }

    # Denied by default
    with pytest.raises(PermissionError, match="no capability token provided"):
        bjrt.submit_browser_job("mini-browser-deepresearch", envelope)

    # Denied when token denies destructive actions
    token_deny = CapabilityToken(
        token_id="tok-deny",
        scopes=["file:write"],
        expires_at="2099-01-01T00:00:00Z",
        actor_id="a1",
        file_scope={"write_paths": [], "secret_paths_allowed": False, "destructive_allowed": False}
    )
    with pytest.raises(PermissionError, match="capability token denies"):
        bjrt.submit_browser_job("mini-browser-deepresearch", envelope, capability_token=token_deny)

    # Allowed when token permits destructive actions
    token_allow = CapabilityToken(
        token_id="tok-allow",
        scopes=["file:write"],
        expires_at="2099-01-01T00:00:00Z",
        actor_id="a1",
        file_scope={"write_paths": [], "secret_paths_allowed": False, "destructive_allowed": True}
    )
    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope, capability_token=token_allow)
    assert job_id.startswith("job-")


def test_reauth_required_surfaces_waiting_human():
    """Verify polling a reauth_required state surfaces projected_state as WAITING_HUMAN."""
    envelope = {"task_id": "T-reauth", "objective": "Do standard research"}
    token = CapabilityToken("tok", ["file:write"], "2099-01-01T00:00:00Z", "a1")

    job_id = bjrt.submit_browser_job(
        "mini-browser-deepresearch",
        envelope,
        mock_sequence=["running", "reauth_required"],
        capability_token=token
    )

    # First poll: running
    r1 = bjrt.poll_browser_job(job_id)
    assert r1["state"] == "running"
    assert r1["projected_state"] == "running"

    # Second poll: reauth_required -> surfaces WAITING_HUMAN
    r2 = bjrt.poll_browser_job(job_id)
    assert r2["state"] == "reauth_required"
    assert r2["projected_state"] == "WAITING_HUMAN"
