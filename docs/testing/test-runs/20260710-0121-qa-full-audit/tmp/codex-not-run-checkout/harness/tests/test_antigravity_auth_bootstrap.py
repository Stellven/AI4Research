"""Regression tests for Antigravity auth/bootstrap failure surface and degradation.

Covers:
- Silent auth failure (empty stdout + auth pattern in log) → exit 76
- Live log auth detection → exit 76 with recovery message
- Live log auth detection via process exit → exit 76 with recovery message
- No active conversation bootstrap failure → exit 77 (after --continue retry also fails)
- No active conversation: first attempt triggers --continue retry
- Pre-flight operator block check: auth_expired blocks dispatch early
- Pre-flight: unblocked operator proceeds normally
- classify_failure_state: auth > cooldown > bootstrap_failed precedence
- format_auth_blocker_message: includes operator id, state, recovery instructions
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HARNESS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_DIR / "tools"))
sys.path.insert(0, str(HARNESS_DIR / "lib"))

import antigravity_multimodal_agent as agy
import operator_flow_control as ofc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dispatch(tmp_path: Path) -> Path:
    d = tmp_path / "dispatch.md"
    d.write_text("## Goal\nDo work\n## Acceptance\n- pass\n", encoding="utf-8")
    return d


def _fake_env(tmp_path: Path, monkeypatch, *, handoff: Path | None = None, operator_id: str = ""):
    dispatch = _make_dispatch(tmp_path)
    hf = handoff or (tmp_path / "handoff.md")
    monkeypatch.setenv("SOLAR_MULTI_TASK_DISPATCH_FILE", str(dispatch))
    monkeypatch.setenv("TASK_DIR", str(tmp_path))
    monkeypatch.setenv("HANDOFF", str(hf))
    monkeypatch.setenv("AGY_BIN", "agy")
    if operator_id:
        monkeypatch.setenv("SOLAR_OPERATOR_ID", operator_id)
    else:
        monkeypatch.delenv("SOLAR_OPERATOR_ID", raising=False)
    monkeypatch.setattr(agy.sys, "argv", ["antigravity_multimodal_agent.py"])
    return dispatch, hf


# ---------------------------------------------------------------------------
# Unit: regex coverage
# ---------------------------------------------------------------------------

class TestRegexPatterns:
    def test_auth_re_matches_not_logged_in(self):
        assert agy.AUTH_RE.search("You are not logged into Antigravity")

    def test_auth_re_matches_you_are_not_logged(self):
        assert agy.AUTH_RE.search("Error: You are not logged in")

    def test_auth_re_matches_login_required(self):
        assert agy.AUTH_RE.search("login required to continue")

    def test_auth_re_no_false_positive_on_quota(self):
        assert not agy.AUTH_RE.search("RESOURCE_EXHAUSTED Individual quota reached")

    def test_no_active_conversation_re_matches(self):
        assert agy.NO_ACTIVE_CONVERSATION_RE.search("Error: failed to send message: no active conversation")

    def test_no_active_conversation_re_no_false_positive(self):
        assert not agy.NO_ACTIVE_CONVERSATION_RE.search("active session started successfully")


# ---------------------------------------------------------------------------
# Unit: operator_flow_control classify_failure_state
# ---------------------------------------------------------------------------

class TestClassifyFailureState:
    def test_auth_takes_priority_over_bootstrap(self):
        text = "You are not logged in\nno active conversation"
        assert ofc.classify_failure_state(text) == "auth_expired"

    def test_bootstrap_failed_when_no_auth(self):
        assert ofc.classify_failure_state("Error: failed to send message: no active conversation") == "bootstrap_failed"

    def test_cooldown_detected(self):
        assert ofc.classify_failure_state("RESOURCE_EXHAUSTED: quota exhausted") == "cooldown"

    def test_empty_text_returns_empty(self):
        assert ofc.classify_failure_state("") == ""

    def test_none_text_returns_empty(self):
        assert ofc.classify_failure_state(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Unit: format_auth_blocker_message
# ---------------------------------------------------------------------------

class TestFormatAuthBlockerMessage:
    def test_auth_expired_includes_recovery_cmd(self):
        msg = ofc.format_auth_blocker_message("my-op", "auth_expired")
        assert "my-op" in msg
        assert "agy login" in msg
        assert "clear-override" in msg

    def test_bootstrap_failed_message(self):
        msg = ofc.format_auth_blocker_message("my-op", "bootstrap_failed")
        assert "bootstrap" in msg.lower()
        assert "new conversation" in msg.lower()

    def test_includes_expires_at(self):
        msg = ofc.format_auth_blocker_message("op", "auth_expired", expires_at="2026-06-01T00:00:00Z")
        assert "2026-06-01" in msg

    def test_custom_recovery_cmd(self):
        msg = ofc.format_auth_blocker_message("op", "auth_expired", recovery_cmd="agy auth refresh")
        assert "agy auth refresh" in msg


# ---------------------------------------------------------------------------
# Integration: run_agy_command — live log AUTH_RE detection
# ---------------------------------------------------------------------------

class TestRunAgyCommandAuthDetection:
    def test_live_log_auth_exits_76(self, tmp_path):
        log_file = tmp_path / "agy.log"

        class FakeProc:
            def poll(self):
                log_file.write_text("You are not logged into Antigravity", encoding="utf-8")
                return None
            def terminate(self):
                pass
            def communicate(self, timeout=None):
                return "", ""

        with patch.object(agy.subprocess, "Popen", return_value=FakeProc()):
            result = agy.run_agy_command(["agy", "--print", "x"], log_file)

        assert result.returncode == agy.EXIT_AUTH_EXPIRED
        assert "agy login" in result.stderr

    def test_process_exit_with_auth_text_exits_76(self, tmp_path):
        log_file = tmp_path / "agy.log"

        class FakeProc:
            def poll(self):
                return 1
            def communicate(self, timeout=None):
                return "", "Error: You are not logged in\n"

        with patch.object(agy.subprocess, "Popen", return_value=FakeProc()):
            result = agy.run_agy_command(["agy", "--print", "x"], log_file)

        assert result.returncode == agy.EXIT_AUTH_EXPIRED
        assert "agy login" in result.stderr


# ---------------------------------------------------------------------------
# Integration: run_agy_command — bootstrap failure after --continue retry
# ---------------------------------------------------------------------------

class TestBootstrapFailAfterContinue:
    def test_no_active_conversation_retries_then_bootstrap_failed(self, tmp_path):
        log_file = tmp_path / "agy.log"
        calls: list[list[str]] = []

        class FakeProc:
            def __init__(self, stderr_text: str):
                self.stderr_text = stderr_text
            def poll(self):
                return 1
            def communicate(self, timeout=None):
                return "", self.stderr_text

        procs = [
            FakeProc("Error: failed to send message: no active conversation\n"),
            FakeProc("Error: failed to send message: no active conversation\n"),
        ]

        def fake_popen(cmd, **kwargs):
            calls.append(list(cmd))
            return procs.pop(0)

        with patch.object(agy.subprocess, "Popen", fake_popen):
            result = agy.run_agy_command(["agy", "--print", "x"], log_file)

        # First call should retry with --continue; second still fails → EXIT_BOOTSTRAP_FAILED
        assert len(calls) == 2
        assert "--continue" in calls[1]
        assert result.returncode == agy.EXIT_BOOTSTRAP_FAILED
        assert "bootstrap failed" in result.stderr.lower()
        assert "new conversation" in result.stderr.lower()

    def test_no_active_conversation_succeeds_on_continue_retry(self, tmp_path):
        log_file = tmp_path / "agy.log"
        calls: list[list[str]] = []

        class FakeProc:
            def __init__(self, stderr_text: str, rc: int = 0):
                self.stderr_text = stderr_text
                self.rc = rc
            def poll(self):
                return self.rc
            def communicate(self, timeout=None):
                return "## completed\nDone.\n", self.stderr_text

        procs = [
            FakeProc("Error: failed to send message: no active conversation\n", rc=1),
            FakeProc("", rc=0),
        ]

        def fake_popen(cmd, **kwargs):
            calls.append(list(cmd))
            return procs.pop(0)

        with patch.object(agy.subprocess, "Popen", fake_popen):
            result = agy.run_agy_command(["agy", "--print", "x"], log_file)

        assert len(calls) == 2
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Integration: main() — silent auth (empty stdout + auth in log)
# ---------------------------------------------------------------------------

class TestMainSilentAuth:
    def test_empty_stdout_with_auth_log_exits_76(self, tmp_path, monkeypatch, capsys):
        _fake_env(tmp_path, monkeypatch)
        log_file = tmp_path / "antigravity.log"
        log_file.write_text("You are not logged into Antigravity", encoding="utf-8")

        def fake_run(cmd, lf):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(agy, "run_agy_command", fake_run)
        assert agy.main() == agy.EXIT_AUTH_EXPIRED
        err = capsys.readouterr().err
        assert "auth expired" in err.lower() or "not logged in" in err.lower()
        assert "agy login" in err

    def test_empty_stdout_with_no_active_conversation_log_exits_77(self, tmp_path, monkeypatch, capsys):
        _fake_env(tmp_path, monkeypatch)
        log_file = tmp_path / "antigravity.log"
        log_file.write_text("Error: failed to send message: no active conversation", encoding="utf-8")

        def fake_run(cmd, lf):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(agy, "run_agy_command", fake_run)
        assert agy.main() == agy.EXIT_BOOTSTRAP_FAILED
        err = capsys.readouterr().err
        assert "bootstrap failed" in err.lower()


# ---------------------------------------------------------------------------
# Integration: main() — pre-flight operator check
# ---------------------------------------------------------------------------

class TestPreflightOperatorCheck:
    def test_blocked_auth_expired_operator_exits_76_early(self, tmp_path, monkeypatch, capsys):
        _fake_env(tmp_path, monkeypatch, operator_id="test-op")

        # Patch _preflight_operator_check to simulate auth_expired block.
        monkeypatch.setattr(agy, "_preflight_operator_check", lambda op_id: agy.EXIT_AUTH_EXPIRED)
        # run_agy_command should NOT be called at all.
        called = []
        monkeypatch.setattr(agy, "run_agy_command", lambda *a, **kw: called.append(1))

        rc = agy.main()
        assert rc == agy.EXIT_AUTH_EXPIRED
        assert not called, "run_agy_command must not be called when pre-flight blocks"

    def test_unblocked_operator_proceeds(self, tmp_path, monkeypatch):
        _fake_env(tmp_path, monkeypatch, operator_id="test-op")
        monkeypatch.setattr(agy, "_preflight_operator_check", lambda op_id: None)

        def fake_run(cmd, lf):
            return subprocess.CompletedProcess(cmd, 0, stdout="## completed\nAll done.\n", stderr="")

        monkeypatch.setattr(agy, "run_agy_command", fake_run)
        rc = agy.main()
        assert rc == 0

    def test_preflight_check_no_operator_id_skips_check(self, tmp_path, monkeypatch):
        """When SOLAR_OPERATOR_ID is unset, pre-flight check is skipped entirely."""
        _fake_env(tmp_path, monkeypatch, operator_id="")
        called = []
        original = agy._preflight_operator_check

        def tracking_check(op_id):
            called.append(op_id)
            return original(op_id)

        monkeypatch.setattr(agy, "_preflight_operator_check", tracking_check)

        def fake_run(cmd, lf):
            return subprocess.CompletedProcess(cmd, 0, stdout="## completed\nDone.\n", stderr="")

        monkeypatch.setattr(agy, "run_agy_command", fake_run)
        rc = agy.main()
        assert rc == 0
        assert not called, "pre-flight check must not run when SOLAR_OPERATOR_ID is unset"
