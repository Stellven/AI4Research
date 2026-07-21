#!/usr/bin/env python3
"""test_operator_runtime.py — S6 Control Plane: Unit tests for operator runtime and leases."""

import os
import sys
import tempfile
import time
import json
import pytest
from pathlib import Path

# Insert lib path so we can import operator_runtime
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import operator_runtime as optime


_ENABLED_OPERATOR = "mini-claude-sonnet-builder"
_DISABLED_OPERATOR = "mini-antigravity-gemini35-flash-high"
_TEST_REGISTRY = {
    "version": 1,
    "operators": {
        _ENABLED_OPERATOR: {
            "display_name": "Mac mini Claude Sonnet builder",
            "role": "builder",
            "persona": "builder",
            "backend": "command",
            "model": "test-command",
            "enabled": True,
        },
        _DISABLED_OPERATOR: {
            "display_name": "Disabled test builder",
            "role": "builder",
            "persona": "builder",
            "backend": "command",
            "model": "test-command",
            "enabled": False,
        },
    },
}


@pytest.fixture(autouse=True)
def setup_teardown_env(monkeypatch):
    """Own the complete runtime boundary used by these unit tests.

    Product operator availability changes with the deployed machine and must
    not change a unit-test outcome.  Submissions in this file also assert the
    pre-daemon lease/inbox state, so they intentionally disable the product's
    separately-tested operatord auto-kick.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        registry_path = tmp_path / "config" / "physical-operators.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(json.dumps(_TEST_REGISTRY), encoding="utf-8")

        monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
        monkeypatch.setenv("SOLAR_HARNESS_DIR", str(tmp_path))
        monkeypatch.setenv("SOLAR_OPERATORD_AUTO_KICK", "0")
        monkeypatch.delenv("HARNESS_SPRINTS_DIR", raising=False)
        monkeypatch.setattr(optime, "HARNESS_DIR", tmp_path)
        monkeypatch.setattr(optime, "OPERATOR_LEASE_DIR", tmp_path / "run" / "operator-leases")
        monkeypatch.setattr(optime, "OPERATOR_STATUS_DIR", tmp_path / "run" / "operator-status")
        monkeypatch.setattr(optime, "OPERATOR_INBOX_DIR", tmp_path / "run" / "operator-inbox")
        monkeypatch.setattr(optime, "OPERATOR_RESULTS_DIR", tmp_path / "run" / "operator-results")
        monkeypatch.setattr(optime, "OPERATOR_PERSONAS_DIR", ROOT / "personas")
        monkeypatch.setattr(optime, "PHYSICAL_OPERATORS_PATH", registry_path)

        yield


def test_operator_config_loading():
    """Verify registry loading works for known operators."""
    config = optime.get_operator_config("mini-claude-sonnet-builder")
    assert config is not None
    assert config["display_name"] == "Mac mini Claude Sonnet builder"
    assert config["enabled"] is True

    # Test unknown operator
    assert optime.get_operator_config("nonexistent-operator") is None


def test_operator_lease_lifecycle():
    """Test lease acquisition, update state, and release."""
    operator_id = "mini-claude-sonnet-builder"
    
    # 1. Ensure initially idle
    assert optime.get_operator_runtime_state(operator_id) == "idle"
    assert optime.get_operator_lease(operator_id) is None
    
    # 2. Acquire lease
    lease = optime.acquire_operator_lease(
        operator_id=operator_id,
        task_id="T001",
        sprint_id="sprint-test",
        node_id="N2",
        ttl_seconds=60,
        initial_state="leased"
    )
    
    assert lease["operator_id"] == operator_id
    assert lease["task_id"] == "T001"
    assert lease["state"] == "leased"
    
    # Check runtime state classified as leased
    assert optime.get_operator_runtime_state(operator_id) == "leased"
    
    # 3. Duplicate acquisition should fail
    with pytest.raises(RuntimeError, match="Duplicate active lease"):
        optime.acquire_operator_lease(
            operator_id=operator_id,
            task_id="T002",
            sprint_id="sprint-test",
            node_id="N2",
            ttl_seconds=60
        )
        
    # 4. Update lease state
    updated_lease = optime.update_operator_lease_state(operator_id, "running")
    assert updated_lease["state"] == "running"
    assert optime.get_operator_runtime_state(operator_id) == "running"
    
    # 5. Release lease
    released = optime.release_operator_lease(operator_id)
    assert released is True
    assert optime.get_operator_lease(operator_id) is None
    assert optime.get_operator_runtime_state(operator_id) == "idle"


def test_lease_expiration():
    """Verify expired leases are treated as inactive."""
    operator_id = "mini-claude-sonnet-builder"
    
    # Acquire a lease with negative TTL to immediately expire it
    lease = optime.acquire_operator_lease(
        operator_id=operator_id,
        task_id="T001",
        sprint_id="sprint-test",
        node_id="N2",
        ttl_seconds=-10
    )
    
    assert optime.get_operator_lease(operator_id) is None
    assert optime.get_operator_runtime_state(operator_id) == "idle"
    
    # Acquire should succeed since the previous lease is expired
    new_lease = optime.acquire_operator_lease(
        operator_id=operator_id,
        task_id="T002",
        sprint_id="sprint-test",
        node_id="N2",
        ttl_seconds=60
    )
    assert new_lease["task_id"] == "T002"
    assert optime.get_operator_runtime_state(operator_id) == "leased"


def test_running_lease_with_dead_recorded_process_is_recovered(monkeypatch):
    """Selectors must not treat dead-PID leases as busy forever."""
    operator_id = "mini-claude-sonnet-builder"
    optime.acquire_operator_lease(
        operator_id=operator_id,
        task_id="T-stale-run",
        sprint_id="sprint-test",
        node_id="N2",
        ttl_seconds=600,
        initial_state="running",
    )
    lease_path = optime.OPERATOR_LEASE_DIR / f"{operator_id}.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["worker_pid"] = 999_991
    lease["daemon_pid"] = 999_992
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    monkeypatch.setattr(optime, "_pid_exists", lambda pid: False)

    assert optime.get_operator_runtime_state(operator_id) == "idle"
    assert optime.get_operator_lease(operator_id) is None


def test_running_status_with_dead_recorded_process_is_recovered(monkeypatch):
    """A stale heartbeat/status file must not block a later dispatch."""
    operator_id = "mini-claude-sonnet-builder"
    optime.set_operator_status(operator_id, "running")
    status_path = optime.OPERATOR_STATUS_DIR / f"{operator_id}.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["worker_pid"] = 999_993
    status_path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setattr(optime, "_pid_exists", lambda pid: False)

    assert optime.get_operator_runtime_state(operator_id) == "idle"
    assert optime.get_operator_status(operator_id) is None


def test_stale_running_status_without_pid_is_recovered(monkeypatch):
    """Interrupted once-mode workers can leave active status without pid evidence."""
    operator_id = "mini-claude-sonnet-builder"
    optime.set_operator_status(operator_id, "running")
    status_path = optime.OPERATOR_STATUS_DIR / f"{operator_id}.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.pop("updated_at", None)
    status["heartbeat_at"] = "2026-01-01T00:00:00Z"
    status_path.write_text(json.dumps(status), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ACTIVE_STATUS_STALE_SECONDS", "60")

    assert optime.get_operator_runtime_state(operator_id) == "idle"
    assert optime.get_operator_status(operator_id) is None


def test_fresh_running_status_without_pid_remains_active(monkeypatch):
    """Fresh no-pid active status is tolerated briefly while daemon metadata catches up."""
    operator_id = "mini-claude-sonnet-builder"
    optime.set_operator_status(operator_id, "running")
    monkeypatch.setenv("SOLAR_OPERATOR_ACTIVE_STATUS_STALE_SECONDS", "3600")

    assert optime.get_operator_runtime_state(operator_id) == "running"


def test_status_override_states():
    """Test dynamic status overrides (cooldown, quota_exhausted, auth_expired)."""
    operator_id = "mini-claude-sonnet-builder"
    
    # Verify idle initially
    assert optime.get_operator_runtime_state(operator_id) == "idle"
    
    # Set quota_exhausted
    optime.set_operator_status(operator_id, "quota_exhausted")
    assert optime.get_operator_runtime_state(operator_id) == "quota_exhausted"
    
    # Set auth_expired
    optime.set_operator_status(operator_id, "auth_expired")
    assert optime.get_operator_runtime_state(operator_id) == "auth_expired"
    
    # Set cooldown
    optime.set_operator_status(operator_id, "cooldown", ttl_seconds=30)
    assert optime.get_operator_runtime_state(operator_id) == "cooldown"
    
    # Clear status override
    optime.clear_operator_status(operator_id)
    assert optime.get_operator_runtime_state(operator_id) == "idle"


def test_heartbeat_preserves_blocking_override():
    """Daemon heartbeats must not clear cooldown/auth/quota overrides."""
    operator_id = "mini-claude-sonnet-builder"

    optime.set_operator_status(operator_id, "cooldown", ttl_seconds=30)
    optime.write_heartbeat(operator_id, "idle", resolved_persona="builder")

    status_path = optime.OPERATOR_STATUS_DIR / f"{operator_id}.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["runtime_state"] == "cooldown"
    assert status["state"] == "idle"
    assert "expires_at" in status


def test_registry_disabled_state():
    """Verify that disabled operators in registry are classified as disabled."""
    operator_id = "mini-antigravity-gemini35-flash-high"
    
    # In registry, mini-antigravity-gemini35-flash-high is enabled: false
    assert optime.get_operator_runtime_state(operator_id) == "disabled"
    
    # Attempting to lease a disabled operator should fail
    with pytest.raises(RuntimeError, match="Cannot lease disabled operator"):
        optime.acquire_operator_lease(
            operator_id=operator_id,
            task_id="T001",
            sprint_id="sprint-test",
            node_id="N2",
            ttl_seconds=60
        )


# ── submit() tests ─────────────────────────────────────────────────────────────

def _make_envelope(operator_id="mini-claude-sonnet-builder", task_id="T-submit-001"):
    return {
        "task_id": task_id,
        "sprint_id": "sprint-test",
        "node_id": "N2",
        "operator_id": operator_id,
        "task_type": "CODE_IMPL",
        "objective": "Implement the submit function.",
    }


def test_submit_success_writes_inbox():
    """Happy path: idle operator with valid persona → envelope written to inbox."""
    envelope = _make_envelope()
    result = optime.submit(envelope)

    assert result["status"] == "submitted"
    assert result["operator_id"] == "mini-claude-sonnet-builder"
    assert result["task_id"] == "T-submit-001"
    assert result["lease_id"].startswith("mini-claude-sonnet-builder:T-submit-001:")

    inbox_file = Path(result["inbox_path"])
    assert inbox_file.exists(), "Inbox file was not written"

    written = json.loads(inbox_file.read_text(encoding="utf-8"))
    assert written["task_id"] == "T-submit-001"
    assert written["operator_id"] == "mini-claude-sonnet-builder"
    assert "submitted_at" in written
    assert "lease_expires_at" in written

    # Lease should be active after submit
    assert optime.get_operator_runtime_state("mini-claude-sonnet-builder") == "leased"


def test_submit_rejects_unknown_operator():
    """Unknown operator_id raises ValueError."""
    envelope = _make_envelope(operator_id="no-such-operator")
    with pytest.raises(ValueError, match="Unknown operator"):
        optime.submit(envelope)


def test_submit_rejects_disabled_operator():
    """Disabled operator raises RuntimeError."""
    envelope = _make_envelope(operator_id="mini-antigravity-gemini35-flash-high")
    with pytest.raises(RuntimeError, match="not dispatchable.*disabled"):
        optime.submit(envelope)


def test_submit_rejects_leased_operator(monkeypatch):
    """Operator already leased raises a machine-classifiable busy rejection."""
    operator_id = "mini-claude-sonnet-builder"
    monkeypatch.setattr(
        optime,
        "get_operator_config",
        lambda _operator_id: {
            "operator_id": operator_id,
            "enabled": True,
            "role": "builder",
            "persona": "builder",
        },
    )
    optime.acquire_operator_lease(
        operator_id=operator_id,
        task_id="T-pre-lease",
        sprint_id="sprint-test",
        node_id="N1",
        ttl_seconds=60,
    )
    envelope = _make_envelope(operator_id=operator_id)
    with pytest.raises(optime.OperatorSubmitRejected, match="not dispatchable.*leased") as raised:
        optime.submit(envelope)
    assert raised.value.reason == "operator_busy"
    assert raised.value.state == "leased"


def test_submit_rejects_running_operator(monkeypatch):
    """Operator in running state raises a machine-classifiable busy rejection."""
    operator_id = "mini-claude-sonnet-builder"
    monkeypatch.setattr(
        optime,
        "get_operator_config",
        lambda _operator_id: {
            "operator_id": operator_id,
            "enabled": True,
            "role": "builder",
            "persona": "builder",
        },
    )
    optime.acquire_operator_lease(
        operator_id=operator_id,
        task_id="T-pre-run",
        sprint_id="sprint-test",
        node_id="N1",
        ttl_seconds=60,
    )
    optime.update_operator_lease_state(operator_id, "running")
    envelope = _make_envelope(operator_id=operator_id)
    with pytest.raises(optime.OperatorSubmitRejected, match="not dispatchable.*running") as raised:
        optime.submit(envelope)
    assert raised.value.reason == "operator_busy"
    assert raised.value.state == "running"


def test_submit_rejects_draining_operator(monkeypatch):
    """A draining operator cannot accept a new envelope."""
    operator_id = "mini-claude-sonnet-builder"
    monkeypatch.setattr(
        optime,
        "get_operator_config",
        lambda _operator_id: {
            "operator_id": operator_id,
            "enabled": True,
            "role": "builder",
            "persona": "builder",
        },
    )
    monkeypatch.setattr(optime, "get_operator_runtime_state", lambda _operator_id: "draining")

    with pytest.raises(optime.OperatorSubmitRejected, match="not dispatchable.*draining") as raised:
        optime.submit(_make_envelope(operator_id=operator_id))
    assert raised.value.reason == "operator_busy"
    assert raised.value.state == "draining"


def test_submit_rejects_quota_exhausted_operator():
    """Operator with quota_exhausted status override raises RuntimeError."""
    operator_id = "mini-claude-sonnet-builder"
    optime.set_operator_status(operator_id, "quota_exhausted")
    envelope = _make_envelope(operator_id=operator_id)
    with pytest.raises(RuntimeError, match="not dispatchable.*quota_exhausted"):
        optime.submit(envelope)


def test_submit_rejects_auth_expired_operator():
    """Operator with auth_expired status override raises RuntimeError."""
    operator_id = "mini-claude-sonnet-builder"
    optime.set_operator_status(operator_id, "auth_expired")
    envelope = _make_envelope(operator_id=operator_id)
    with pytest.raises(RuntimeError, match="not dispatchable.*auth_expired"):
        optime.submit(envelope)


def test_submit_rejects_cooldown_operator():
    """Operator with cooldown status override raises RuntimeError."""
    operator_id = "mini-claude-sonnet-builder"
    optime.set_operator_status(operator_id, "cooldown", ttl_seconds=30)
    envelope = _make_envelope(operator_id=operator_id)
    with pytest.raises(RuntimeError, match="not dispatchable.*cooldown"):
        optime.submit(envelope)


def test_submit_rejects_missing_required_keys():
    """Envelope missing required keys raises ValueError."""
    bad_envelope = {"task_id": "T001", "operator_id": "mini-claude-sonnet-builder"}
    with pytest.raises(ValueError, match="missing required keys"):
        optime.submit(bad_envelope)


def test_submit_rejects_missing_persona_binding(tmp_path, monkeypatch):
    """Operator with non-existent persona file raises RuntimeError."""
    # Point personas dir to empty directory so no persona files exist
    empty_personas = tmp_path / "personas"
    empty_personas.mkdir()
    monkeypatch.setattr(optime, "OPERATOR_PERSONAS_DIR", empty_personas)

    envelope = _make_envelope(operator_id="mini-claude-sonnet-builder")
    with pytest.raises(RuntimeError, match="persona file missing"):
        optime.submit(envelope)


def test_submit_persona_field_wins_over_role(monkeypatch, tmp_path):
    """submit() uses the ``persona`` field, not ``role``, when they differ.

    Only evaluator.md is present; if the runtime fell back to role='builder'
    it would fail.  Success proves persona='evaluator' was used.
    """
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "evaluator.md").write_text("# Evaluator\n", encoding="utf-8")
    monkeypatch.setattr(optime, "OPERATOR_PERSONAS_DIR", personas_dir)

    def _mock_config(op_id):
        if op_id == "mini-claude-sonnet-builder":
            cfg = {
                "enabled": True,
                "persona": "evaluator",
                "role": "builder",
                "display_name": "test",
            }
            return cfg
        return None

    monkeypatch.setattr(optime, "get_operator_config", _mock_config)

    envelope = _make_envelope(operator_id="mini-claude-sonnet-builder")
    result = optime.submit(envelope)
    assert result["status"] == "submitted"


def test_submit_falls_back_to_role_when_persona_absent(monkeypatch, tmp_path):
    """submit() falls back to ``role`` when ``persona`` field is not in config."""
    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "builder.md").write_text("# Builder\n", encoding="utf-8")
    monkeypatch.setattr(optime, "OPERATOR_PERSONAS_DIR", personas_dir)

    def _mock_config(op_id):
        if op_id == "mini-claude-sonnet-builder":
            # Explicitly omit the persona field
            return {"enabled": True, "role": "builder", "display_name": "test"}
        return None

    monkeypatch.setattr(optime, "get_operator_config", _mock_config)

    envelope = _make_envelope(operator_id="mini-claude-sonnet-builder")
    result = optime.submit(envelope)
    assert result["status"] == "submitted"


def test_submit_uses_custom_lease_ttl():
    """Envelope lease_ttl_seconds is respected."""
    envelope = _make_envelope()
    envelope["lease_ttl_seconds"] = 7200
    result = optime.submit(envelope)

    assert result["status"] == "submitted"
    lease = optime.get_operator_lease("mini-claude-sonnet-builder")
    assert lease is not None
    # Verify lease expiry is ~2h from now (within a 5-second window)
    import datetime
    expires = datetime.datetime.strptime(lease["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = (expires - now).total_seconds()
    assert 7190 <= delta <= 7210
