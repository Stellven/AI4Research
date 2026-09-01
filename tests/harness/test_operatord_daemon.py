#!/usr/bin/env python3
"""Tests for operatord daemon mode (N3 acceptance criteria).

Covers:
- Unit tests for operator_runtime utility functions added in N3
- Integration test: submit a task → daemon --once processes it end-to-end
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

HARNESS_ROOT = (Path(__file__).resolve().parents[2] / 'harness')
LIB_DIR = HARNESS_ROOT / "lib"
TOOLS_DIR = HARNESS_ROOT / "tools"
REAL_PERSONAS_DIR = HARNESS_ROOT / "personas"

sys.path.insert(0, str(LIB_DIR))
sys.path.insert(0, str(TOOLS_DIR))

import operator_runtime as _rt  # noqa: E402 — after path setup
import operatord as _od  # noqa: E402 — after path setup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_REGISTRY = {
    "version": 1,
    "operators": {
        "test-local-builder": {
            "display_name": "Test Local Builder (N3 test operator)",
            "role": "builder",
            "persona": "builder",
            "backend": "local",
            "model": "local",
            "enabled": True,
        }
    },
}

_COMMAND_REGISTRY = {
    "version": 1,
    "operators": {
        "test-command-builder": {
            "display_name": "Test Command Builder",
            "role": "builder",
            "persona": "builder",
            "backend": "command",
            "model": "local-command",
            "enabled": True,
        }
    },
}

_TASK_ENVELOPE = {
    "task_id": "T-n3-test-001",
    "sprint_id": "sprint-test-n3",
    "node_id": "N3",
    "operator_id": "test-local-builder",
    "task_type": "dummy",
    "objective": "Verify operatord daemon end-to-end lifecycle.",
}


def _command_text(args: list[str]) -> str:
    return json.dumps(args)


def _signal_capable_python() -> str:
    if os.name == "nt":
        return str(getattr(sys, "_base_executable", sys.executable))
    return sys.executable


def _worker_python() -> str:
    if os.name == "nt":
        return str(getattr(sys, "_base_executable", sys.executable))
    return sys.executable


def _request_daemon_shutdown(proc: subprocess.Popen, env: dict) -> None:
    if os.name == "nt":
        shutdown_path = Path(env["SOLAR_OPERATORD_SHUTDOWN_FILE"])
        shutdown_path.parent.mkdir(parents=True, exist_ok=True)
        shutdown_path.write_text("shutdown\n", encoding="utf-8")
    else:
        proc.send_signal(signal.SIGTERM)


def _setup_harness(tmp_path: Path) -> dict:
    """Create a minimal harness directory and return the env dict."""
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "personas").mkdir(parents=True)

    # Registry
    (tmp_path / "config" / "physical-operators.json").write_text(
        json.dumps(_MINIMAL_REGISTRY, indent=2)
    )

    # Persona file — copy real one if available, else write minimal content
    real_persona = REAL_PERSONAS_DIR / "builder.md"
    dest_persona = tmp_path / "personas" / "builder.md"
    if real_persona.exists():
        shutil.copy(real_persona, dest_persona)
    else:
        dest_persona.write_text("# Builder\nYou are a builder.")

    env = {
        **os.environ,
        "HARNESS_DIR": str(tmp_path),
        # This suite exercises the explicit ``submit -> daemon --once``
        # lifecycle.  Product submissions auto-kick operatord by default and
        # have separate real-path coverage; leaving that enabled here races a
        # second daemon against the one the test intentionally starts.
        "SOLAR_OPERATORD_AUTO_KICK": "0",
        "SOLAR_OPERATORD_SHUTDOWN_FILE": str(tmp_path / "run" / "operatord-shutdown.request"),
    }
    return env


def _setup_command_harness(tmp_path: Path) -> dict:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "personas").mkdir(parents=True)
    (tmp_path / "tools").mkdir(parents=True)

    (tmp_path / "config" / "physical-operators.json").write_text(
        json.dumps(_COMMAND_REGISTRY, indent=2)
    )

    real_persona = REAL_PERSONAS_DIR / "builder.md"
    dest_persona = tmp_path / "personas" / "builder.md"
    if real_persona.exists():
        shutil.copy(real_persona, dest_persona)
    else:
        dest_persona.write_text("# Builder\nYou are a builder.")

    writer = tmp_path / "tools" / "write_handoff_from_dispatch.py"
    writer.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path

dispatch = Path(os.environ["SOLAR_MULTI_TASK_DISPATCH_FILE"]).read_text(encoding="utf-8")
handoff = Path(os.environ["HANDOFF"])
handoff.parent.mkdir(parents=True, exist_ok=True)
handoff.write_text("# Handoff\\n\\n" + dispatch, encoding="utf-8")
result_path = os.environ.get("RESULT_PATH") or os.environ.get("PM_RESULT_PATH") or ""
if result_path:
    result = Path(result_path)
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text("# PM Task Result\\n\\n## 已完成\\n- command backend wrote result\\n", encoding="utf-8")
print("dispatch_seen=" + str(Path(os.environ["SOLAR_MULTI_TASK_DISPATCH_FILE"]).exists()))
print("handoff_written=" + str(handoff))
""",
        encoding="utf-8",
    )
    writer.chmod(0o755)

    pm_dispatch = tmp_path / "tools" / "pm_dispatch.py"
    pm_dispatch.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

if len(sys.argv) >= 4 and sys.argv[1] == "complete" and sys.argv[2] == "--task-id":
    task_id = sys.argv[3]
    log = Path(os.environ["HARNESS_DIR"]) / "run" / "pm-complete.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"task_id": task_id}, ensure_ascii=False), encoding="utf-8")
    print(f"task {task_id} marked completed")
    raise SystemExit(0)
if len(sys.argv) >= 4 and sys.argv[1] == "fail" and sys.argv[2] == "--task-id":
    task_id = sys.argv[3]
    log = Path(os.environ["HARNESS_DIR"]) / "run" / "pm-fail.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"task_id": task_id, "args": sys.argv[1:]}, ensure_ascii=False), encoding="utf-8")
    print(f"task {task_id} marked failed")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    pm_dispatch.chmod(0o755)

    env = {
        **os.environ,
        "HARNESS_DIR": str(tmp_path),
        # Keep the command-backend fixtures on the same explicit daemon
        # lifecycle as the local-backend fixtures above.
        "SOLAR_OPERATORD_AUTO_KICK": "0",
        "SOLAR_OPERATORD_SHUTDOWN_FILE": str(tmp_path / "run" / "operatord-shutdown.request"),
    }
    env["COMMAND_AGENT"] = _command_text([_worker_python(), str(writer)])
    return env


# ---------------------------------------------------------------------------
# Unit tests: scrub_secrets
# ---------------------------------------------------------------------------

class TestScrubSecrets:
    def test_scrubs_openai_key(self):
        text = "Using key sk-abcdefghijklmnopqrstuvwxyzABCDEFGH in request"
        out = _rt.scrub_secrets(text)
        assert "sk-" not in out
        assert "[SCRUBBED]" in out

    def test_scrubs_github_pat(self):
        text = "export TOKEN=ghp_" + "a" * 36
        out = _rt.scrub_secrets(text)
        assert "ghp_" not in out
        assert "[SCRUBBED]" in out

    def test_scrubs_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        out = _rt.scrub_secrets(text)
        assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" not in out

    def test_passthrough_plain_text(self):
        text = "No secrets here, just a normal log line."
        assert _rt.scrub_secrets(text) == text


# ---------------------------------------------------------------------------
# Unit tests: list_inbox_tasks
# ---------------------------------------------------------------------------

class TestListInboxTasks:
    def test_empty_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_rt, "OPERATOR_INBOX_DIR", tmp_path / "inbox")
        result = _rt.list_inbox_tasks("no-such-operator")
        assert result == []

    def test_returns_tasks(self, tmp_path, monkeypatch):
        inbox = tmp_path / "inbox" / "my-op"
        inbox.mkdir(parents=True)
        env = {"task_id": "T-001", "sprint_id": "s1", "node_id": "N1",
               "operator_id": "my-op", "task_type": "dummy", "objective": "test"}
        (inbox / "T-001.json").write_text(json.dumps(env))

        monkeypatch.setattr(_rt, "OPERATOR_INBOX_DIR", tmp_path / "inbox")
        tasks = _rt.list_inbox_tasks("my-op")
        assert len(tasks) == 1
        tid, envelope, path = tasks[0]
        assert tid == "T-001"
        assert envelope["task_id"] == "T-001"
        assert path.name == "T-001.json"


# ---------------------------------------------------------------------------
# Unit tests: write_heartbeat
# ---------------------------------------------------------------------------

class TestWriteHeartbeat:
    def _patch_dirs(self, monkeypatch, tmp_path):
        status_dir = tmp_path / "run" / "operator-status"
        monkeypatch.setattr(_rt, "OPERATOR_STATUS_DIR", status_dir)
        monkeypatch.setattr(_rt, "OPERATOR_LEASE_DIR", tmp_path / "run" / "operator-leases")
        return status_dir

    def test_writes_heartbeat_file(self, tmp_path, monkeypatch):
        status_dir = self._patch_dirs(monkeypatch, tmp_path)
        _rt.write_heartbeat("op1", "idle", resolved_persona="builder")

        hb = json.loads((status_dir / "op1.json").read_text())
        assert hb["runtime_state"] == "idle"
        assert hb["state"] == "idle"
        assert "heartbeat_at" in hb
        assert hb["resolved_persona"] == "builder"

    def test_includes_current_task(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        _rt.write_heartbeat("op1", "running", current_task_id="T-abc")

        hb_path = tmp_path / "run" / "operator-status" / "op1.json"
        hb = json.loads(hb_path.read_text())
        assert hb["current_task_id"] == "T-abc"


# ---------------------------------------------------------------------------
# Unit tests: write_result
# ---------------------------------------------------------------------------

class TestWriteResult:
    def _patch_dirs(self, monkeypatch, tmp_path):
        results_dir = tmp_path / "run" / "operator-results"
        monkeypatch.setattr(_rt, "OPERATOR_RESULTS_DIR", results_dir)
        return results_dir

    def test_writes_result_json(self, tmp_path, monkeypatch):
        results_dir = self._patch_dirs(monkeypatch, tmp_path)
        path = _rt.write_result(
            operator_id="op1",
            task_id="T-001",
            sprint_id="sprint-1",
            node_id="N1",
            status="completed",
            exit_code=0,
            started_at="2026-05-22T00:00:00Z",
            finished_at="2026-05-22T00:00:05Z",
            log_tail="task=T-001\ncompleted",
        )
        assert path.exists()
        result = json.loads(path.read_text())
        assert result["task_id"] == "T-001"
        assert result["operator_id"] == "op1"
        assert result["status"] == "completed"
        assert result["exit_code"] == 0
        assert result["started_at"] == "2026-05-22T00:00:00Z"
        assert result["finished_at"] == "2026-05-22T00:00:05Z"
        assert "log_tail" in result

    def test_exact_result_converges_multi_task_status(self, tmp_path, monkeypatch):
        """The durable result writer must close the matching submitted task row."""
        self._patch_dirs(monkeypatch, tmp_path)
        monkeypatch.setattr(_rt, "HARNESS_DIR", tmp_path)
        status_path = tmp_path / "run" / "multi-task" / "T-converge" / "status.json"
        status_path.parent.mkdir(parents=True)
        status_path.write_text(
            json.dumps(
                {
                    "id": "T-converge",
                    "operator_id": "op1",
                    "sprint_id": "sprint-1",
                    "node_id": "N1",
                    "status": "submitted",
                }
            ),
            encoding="utf-8",
        )

        result_path = _rt.write_result(
            operator_id="op1",
            task_id="T-converge",
            sprint_id="sprint-1",
            node_id="N1",
            status="completed",
            exit_code=0,
            started_at="2026-05-22T00:00:00Z",
            finished_at="2026-05-22T00:00:05Z",
            log_tail="ok",
        )

        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["status"] == "completed"
        assert status["exit_code"] == 0
        assert status["result_path"] == str(result_path)
        assert status["result_converged"] is True

    def test_writes_model_route_fields(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        path = _rt.write_result(
            operator_id="op-glm",
            task_id="T-glm",
            sprint_id="sprint-1",
            node_id="N1",
            status="completed",
            exit_code=0,
            started_at="2026-05-22T00:00:00Z",
            finished_at="2026-05-22T00:00:05Z",
            log_tail="ok",
            model_route={
                "requested_model": "glm-5.1",
                "routing_model": "opus",
                "effective_provider": "zhipu",
                "effective_model": "glm-5.1",
            },
        )
        result = json.loads(path.read_text())
        assert result["requested_model"] == "glm-5.1"
        assert result["routing_model"] == "opus"
        assert result["effective_provider"] == "zhipu"
        assert result["effective_model"] == "glm-5.1"
        assert result["model_route"]["effective_model"] == "glm-5.1"

    def test_scrubs_secrets_in_log_tail(self, tmp_path, monkeypatch):
        self._patch_dirs(monkeypatch, tmp_path)
        _rt.write_result(
            operator_id="op1",
            task_id="T-002",
            sprint_id="s1",
            node_id="N1",
            status="completed",
            exit_code=0,
            started_at="2026-05-22T00:00:00Z",
            finished_at="2026-05-22T00:00:01Z",
            log_tail="sk-secretkeyABCDEFGHIJKLMNOPQRSTUVWXYZ logged",
        )
        result_path = tmp_path / "run" / "operator-results" / "op1" / "T-002" / "result.json"
        result = json.loads(result_path.read_text())
        assert "sk-secret" not in result["log_tail"]
        assert "[SCRUBBED]" in result["log_tail"]


# ---------------------------------------------------------------------------
# Integration test: full daemon --once end-to-end
# ---------------------------------------------------------------------------

class TestDaemonOnce:
    """Run the full operatord daemon --once via subprocess with a temp HARNESS_DIR."""

    OPERATOR_ID = "test-local-builder"
    TASK_ID = "T-n3-test-001"

    def _run_submit(self, env: dict, envelope_path: Path) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "..") + "/lib/operator_runtime.py",
                "submit",
                "--envelope",
                str(envelope_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"submit failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        return json.loads(result.stdout)

    def _run_daemon_once(self, env: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                _signal_capable_python(),
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                self.OPERATOR_ID,
                "--once",
                "--poll-interval",
                "0.2",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_end_to_end(self, tmp_path):
        env = _setup_harness(tmp_path)

        # Write task envelope file
        envelope_path = tmp_path / "envelope.json"
        envelope = dict(_TASK_ENVELOPE)
        envelope_path.write_text(json.dumps(envelope))

        # Submit task via operator_runtime CLI
        submit_out = self._run_submit(env, envelope_path)
        assert submit_out["status"] == "submitted"
        assert submit_out["task_id"] == self.TASK_ID

        # Verify inbox was populated
        inbox_file = (
            tmp_path
            / "run"
            / "operator-inbox"
            / self.OPERATOR_ID
            / f"{self.TASK_ID}.json"
        )
        assert inbox_file.exists(), "Inbox file should be created by submit()"

        # Run daemon --once
        daemon_proc = self._run_daemon_once(env)
        assert daemon_proc.returncode == 0, (
            f"daemon --once failed:\nstdout={daemon_proc.stdout}\nstderr={daemon_proc.stderr}"
        )

        # ── Verify result artifact ────────────────────────────────────────────
        result_json = (
            tmp_path
            / "run"
            / "operator-results"
            / self.OPERATOR_ID
            / self.TASK_ID
            / "result.json"
        )
        assert result_json.exists(), (
            f"result.json not found at {result_json}\n"
            f"daemon stdout:\n{daemon_proc.stdout}\n"
            f"daemon stderr:\n{daemon_proc.stderr}"
        )
        result = json.loads(result_json.read_text())

        # Acceptance: result artifact must contain these fields
        assert result["task_id"] == self.TASK_ID
        assert result["operator_id"] == self.OPERATOR_ID
        assert result["status"] == "completed"
        assert "started_at" in result
        assert "finished_at" in result
        assert "log_tail" in result
        assert result["exit_code"] == 0

        # ── Verify status transitions via heartbeat file ───────────────────────
        hb_file = (
            tmp_path
            / "run"
            / "operator-status"
            / f"{self.OPERATOR_ID}.json"
        )
        assert hb_file.exists(), "Heartbeat status file should be written"
        hb = json.loads(hb_file.read_text())
        # After --once completes, daemon resets to idle
        assert hb["runtime_state"] == "idle"
        assert "heartbeat_at" in hb

        # ── Verify inbox is cleaned up ────────────────────────────────────────
        assert not inbox_file.exists(), (
            "Task envelope should be removed from inbox after processing"
        )

        # ── Verify lease is released ──────────────────────────────────────────
        lease_file = (
            tmp_path
            / "run"
            / "operator-leases"
            / f"{self.OPERATOR_ID}.json"
        )
        assert not lease_file.exists(), (
            "Lease file should be removed after task completion"
        )

    def test_output_log_written(self, tmp_path):
        env = _setup_harness(tmp_path)
        envelope_path = tmp_path / "envelope2.json"
        envelope = dict(_TASK_ENVELOPE)
        envelope["task_id"] = "T-n3-test-002"
        envelope_path.write_text(json.dumps(envelope))

        self._run_submit(env, envelope_path)

        daemon_proc = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                self.OPERATOR_ID,
                "--once",
                "--poll-interval",
                "0.2",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert daemon_proc.returncode == 0

        output_log = (
            tmp_path
            / "run"
            / "operator-results"
            / self.OPERATOR_ID
            / "T-n3-test-002"
            / "output.log"
        )
        assert output_log.exists(), "output.log should be written alongside result.json"
        log_content = output_log.read_text()
        assert "T-n3-test-002" in log_content or "operatord" in log_content

    def test_recovers_expired_lease_and_processes_task(self, tmp_path):
        env = _setup_harness(tmp_path)
        envelope_path = tmp_path / "expired-lease-envelope.json"
        envelope = dict(_TASK_ENVELOPE)
        envelope["task_id"] = "T-expired-lease-001"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

        submit_out = self._run_submit(env, envelope_path)
        assert submit_out["status"] == "submitted"

        lease_file = (
            tmp_path
            / "run"
            / "operator-leases"
            / f"{self.OPERATOR_ID}.json"
        )
        lease = json.loads(lease_file.read_text(encoding="utf-8"))
        lease["expires_at"] = "2000-01-01T00:00:00Z"
        lease_file.write_text(json.dumps(lease, indent=2), encoding="utf-8")

        daemon_proc = self._run_daemon_once(env)
        assert daemon_proc.returncode == 0, daemon_proc.stderr

        result_json = (
            tmp_path
            / "run"
            / "operator-results"
            / self.OPERATOR_ID
            / "T-expired-lease-001"
            / "result.json"
        )
        assert result_json.exists()
        result = json.loads(result_json.read_text(encoding="utf-8"))
        assert result["status"] == "completed"

    def test_command_backend_uses_materialized_dispatch_file(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        envelope = {
            "task_id": "T-command-001",
            "sprint_id": "sprint-command",
            "node_id": "N1",
            "operator_id": "test-command-builder",
            "task_type": "dummy",
            "objective": "Verify command backend",
            "dispatch_text": "# dispatch\\n\\nhello command backend\\n",
            "handoff_path": str(tmp_path / "sprints" / "sprint-command.N1-handoff.md"),
            "command": "$COMMAND_AGENT",
        }
        envelope_path = tmp_path / "command-envelope.json"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

        submit_out = self._run_submit(env, envelope_path)
        assert submit_out["status"] == "submitted"

        daemon_proc = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                "test-command-builder",
                "--once",
                "--poll-interval",
                "0.2",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert daemon_proc.returncode == 0, daemon_proc.stderr

        result_json = (
            tmp_path
            / "run"
            / "operator-results"
            / "test-command-builder"
            / "T-command-001"
            / "result.json"
        )
        assert result_json.exists()
        result = json.loads(result_json.read_text())
        assert result["status"] == "completed"
        dispatch_md = result_json.parent / "dispatch.md"
        envelope_json = result_json.parent / "envelope.json"
        assert dispatch_md.exists()
        assert envelope_json.exists()
        assert "hello command backend" in dispatch_md.read_text(encoding="utf-8")
        handoff = tmp_path / "sprints" / "sprint-command.N1-handoff.md"
        assert handoff.exists()

    def test_pm_dispatch_result_path_and_complete_hook(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        dispatch_dir = tmp_path / "run" / "pm-dispatch-files"
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        dispatch_file = dispatch_dir / "pm-T-command-002.md"
        dispatch_file.write_text("# Solar PM Dispatch\\n\\nhello pm dispatch\\n", encoding="utf-8")

        envelope = {
            "task_id": "pm-T-command-002",
            "sprint_id": "sprint-command",
            "node_id": "N1",
            "operator_id": "test-command-builder",
            "task_type": "planning",
            "objective": "Verify PM dispatch completion path",
            "dispatch_file": str(dispatch_file),
            "result_path": str(tmp_path / "sprints" / "sprint-command.N1.pm-result.md"),
            "handoff_path": str(tmp_path / "sprints" / "sprint-command.N1-handoff.md"),
            "command": "$COMMAND_AGENT",
        }
        envelope_path = tmp_path / "pm-envelope.json"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

        submit_out = self._run_submit(env, envelope_path)
        assert submit_out["status"] == "submitted"

        daemon_proc = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                "test-command-builder",
                "--once",
                "--poll-interval",
                "0.2",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert daemon_proc.returncode == 0, daemon_proc.stderr

        result_json = (
            tmp_path
            / "run"
            / "operator-results"
            / "test-command-builder"
            / "pm-T-command-002"
            / "result.json"
        )
        result = json.loads(result_json.read_text())
        assert result["status"] == "completed"

        pm_result = tmp_path / "sprints" / "sprint-command.N1.pm-result.md"
        assert pm_result.exists()
        assert "command backend wrote result" in pm_result.read_text(encoding="utf-8")

        complete_log = tmp_path / "run" / "pm-complete.json"
        assert complete_log.exists()
        assert json.loads(complete_log.read_text(encoding="utf-8"))["task_id"] == "pm-T-command-002"

    def test_pm_result_file_exists_when_restricted_operator_starts(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        checker = tmp_path / "tools" / "require_precreated_pm_result.py"
        checker.write_text(
            """#!/usr/bin/env python3
import os
from pathlib import Path

result = Path(os.environ["PM_RESULT_PATH"])
if not result.is_file():
    raise SystemExit("PM result must be pre-created by Solar")
result.write_text("# PM Task Result\\n\\npre-created exact output was writable\\n", encoding="utf-8")
""",
            encoding="utf-8",
        )
        checker.chmod(0o755)
        env["COMMAND_AGENT"] = _command_text([_worker_python(), str(checker)])

        dispatch_dir = tmp_path / "run" / "pm-dispatch-files"
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        dispatch_file = dispatch_dir / "pm-T-precreated-result.md"
        dispatch_file.write_text("# Solar PM Dispatch\n", encoding="utf-8")
        pm_result = tmp_path / "sprints" / "sprint-command.N0.pm-result.md"
        pm_result.parent.mkdir(parents=True, exist_ok=True)
        pm_result.write_text("stale content", encoding="utf-8")
        envelope = {
            "task_id": "pm-T-precreated-result",
            "sprint_id": "sprint-command",
            "node_id": "N0",
            "operator_id": "test-command-builder",
            "task_type": "planning",
            "objective": "Verify Solar pre-creates the exact PM result output",
            "dispatch_file": str(dispatch_file),
            "result_path": str(pm_result),
            "command": "$COMMAND_AGENT",
        }
        envelope_path = tmp_path / "pm-envelope-precreated-result.json"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

        submit_out = self._run_submit(env, envelope_path)
        assert submit_out["status"] == "submitted"
        daemon_proc = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                "test-command-builder",
                "--once",
                "--poll-interval",
                "0.2",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert daemon_proc.returncode == 0, daemon_proc.stderr
        assert "stale content" not in pm_result.read_text(encoding="utf-8")
        assert "pre-created exact output was writable" in pm_result.read_text(encoding="utf-8")
        result_json = (
            tmp_path
            / "run"
            / "operator-results"
            / "test-command-builder"
            / "pm-T-precreated-result"
            / "result.json"
        )
        assert json.loads(result_json.read_text(encoding="utf-8"))["status"] == "completed"

    def test_signal_leaves_final_status(self, tmp_path):
        """SIGTERM while idle should leave a final idle status file."""
        env = _setup_harness(tmp_path)

        # Start daemon with no task submitted (will poll and wait)
        proc = subprocess.Popen(
            [
                _signal_capable_python(),
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                self.OPERATOR_ID,
                "--poll-interval",
                "0.1",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Wait until at least one heartbeat is written
        hb_file = (
            tmp_path
            / "run"
            / "operator-status"
            / f"{self.OPERATOR_ID}.json"
        )
        deadline = time.time() + 5.0
        while not hb_file.exists() and time.time() < deadline:
            time.sleep(0.1)

        assert hb_file.exists(), "Heartbeat should be written within 5s of daemon start"

        # Send SIGTERM
        _request_daemon_shutdown(proc, env)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        # Final status should be idle
        hb = json.loads(hb_file.read_text())
        assert hb["runtime_state"] == "idle", (
            f"Final heartbeat after SIGTERM should be idle, got {hb['runtime_state']}"
        )

    def test_signal_during_pm_task_records_terminal_failure(self, tmp_path):
        """An interrupted PM task must close as failed, never as draining."""
        env = _setup_command_harness(tmp_path)
        slow_agent = tmp_path / "tools" / "slow_command.py"
        slow_agent.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        env["COMMAND_AGENT"] = _command_text([_worker_python(), str(slow_agent)])

        dispatch_dir = tmp_path / "run" / "pm-dispatch-files"
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        dispatch_file = dispatch_dir / "pm-T-command-interrupted.md"
        dispatch_file.write_text("# Solar PM Dispatch\n", encoding="utf-8")
        envelope = {
            "task_id": "pm-T-command-interrupted",
            "sprint_id": "sprint-command",
            "node_id": "N0",
            "operator_id": "test-command-builder",
            "task_type": "planning",
            "objective": "Verify interrupted PM closeout",
            "dispatch_file": str(dispatch_file),
            "result_path": str(tmp_path / "sprints" / "sprint-command.N0.pm-result.md"),
            "handoff_path": str(tmp_path / "sprints" / "sprint-command.N0-handoff.md"),
            "command": "$COMMAND_AGENT",
        }
        envelope_path = tmp_path / "pm-envelope-interrupted.json"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        self._run_submit(env, envelope_path)

        proc = subprocess.Popen(
            [
                _signal_capable_python(),
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                "test-command-builder",
                "--once",
                "--poll-interval",
                "0.1",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result_path = (
            tmp_path
            / "run"
            / "operator-results"
            / "test-command-builder"
            / "pm-T-command-interrupted"
            / "result.json"
        )
        heartbeat_path = tmp_path / "run" / "operator-status" / "test-command-builder.json"
        deadline = time.time() + 5.0
        running = False
        while time.time() < deadline:
            if heartbeat_path.exists():
                heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
                running = heartbeat.get("runtime_state") == "running"
                if running:
                    break
            time.sleep(0.05)
        assert running, "PM task should enter running before SIGTERM"

        _request_daemon_shutdown(proc, env)
        proc.wait(timeout=10)

        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["status"] == "failed_interrupted"
        assert result["exit_code"] != 0
        failure = json.loads((tmp_path / "run" / "pm-fail.json").read_text(encoding="utf-8"))
        assert failure["task_id"] == "pm-T-command-interrupted"
        assert "failed_interrupted" in failure["args"]


class TestBuildCommand:
    def test_missing_command_environment_indirection_fails_closed(self, monkeypatch):
        monkeypatch.delenv("SOLAR_TEST_MISSING_COMMAND", raising=False)
        cmd = _od._build_command(
            {"backend": "command"},
            {"command": "$SOLAR_TEST_MISSING_COMMAND"},
        )

        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)

        assert completed.returncode == 127
        assert "SOLAR_TEST_MISSING_COMMAND is not set" in completed.stderr

    def test_claude_cli_backend_uses_print_command(self):
        cmd = _od._build_command(
            {"backend": "claude-cli", "model": "claude-opus-4-8"},
            {"task_id": "pm-sample", "dispatch_file": "/tmp/dispatch.md"},
        )
        joined = " ".join(cmd)
        assert cmd[:2] == ["bash", "-lc"]
        assert "claude --dangerously-skip-permissions" in joined
        assert "local-stub" not in joined
        assert 'cat "$DISPATCH_FILE"' in joined

    def test_glm_claude_cli_backend_uses_zhipu_opus_route(self):
        cmd = _od._build_command(
            {"backend": "claude-cli", "provider": "glm", "model": "glm-5.1"},
            {"task_id": "pm-glm", "dispatch_file": "/tmp/dispatch.md"},
        )
        joined = " ".join(cmd)
        assert cmd[:2] == ["bash", "-lc"]
        assert "ANTHROPIC_BASE_URL" in joined
        assert "ANTHROPIC_API_KEY" in joined
        assert "ANTHROPIC_DEFAULT_OPUS_MODEL" in joined
        assert "--model opus" in joined
        assert "--model glm-5.1" not in joined

    def test_glm_model_route_metadata_exposes_effective_model(self):
        route = _od._model_route_metadata(
            {"backend": "claude-cli", "provider": "glm", "model": "glm-5.1"}
        )
        assert route == {
            "requested_model": "glm-5.1",
            "routing_model": "opus",
            "effective_provider": "zhipu",
            "effective_model": "glm-5.1",
        }

    def test_command_backend_uses_registry_command_when_envelope_missing_command(self):
        cmd = _od._build_command(
            {"backend": "command", "command": "python3 /tmp/agent.py"},
            {"task_id": "pm-sample"},
        )
        assert cmd == ["bash", "-lc", "python3 /tmp/agent.py"]

    def test_empty_envelope_command_does_not_shadow_registry_command(self):
        cmd = _od._build_command(
            {"backend": "command", "command": "python3 /tmp/agent.py"},
            {"task_id": "pm-sample", "command": ""},
        )
        assert cmd == ["bash", "-lc", "python3 /tmp/agent.py"]

    def test_command_backend_can_use_shell_free_registry_argv(self):
        cmd = _od._build_command(
            {
                "backend": "command",
                "launch_cmd": "python3 /tmp/ignored.py",
                "launch_argv": [sys.executable, "C:\\fixture worker.py"],
            },
            {"task_id": "pm-native-argv"},
        )

        assert cmd == [sys.executable, "C:\\fixture worker.py"]

    def test_windows_codex_command_uses_native_python_wrapper(self, monkeypatch):
        monkeypatch.setattr(_od.os, "name", "nt")
        cmd = _od._build_command(
            {
                "backend": "command",
                "provider": "openai",
                "model": "gpt-5.5",
                "model_config": "Codex CLI;gpt-5.5;reasoning=high",
                "command": "CODEX_MODEL=gpt-5.5 python3 $HARNESS_DIR/tools/codex_operator.py",
                "command_path": "/opt/homebrew/bin/codex",
            },
            {"task_id": "pm-windows-codex"},
        )

        assert cmd == [
            sys.executable,
            str(_od.HARNESS_DIR / "tools" / "codex_operator.py"),
        ]

    def test_windows_codex_envelope_command_still_uses_native_python_wrapper(self, monkeypatch):
        monkeypatch.setattr(_od.os, "name", "nt")
        config = {
            "backend": "command",
            "provider": "openai",
            "model": "gpt-5.3-codex-spark",
            "model_config": "Codex CLI;gpt-5.3-codex-spark;reasoning=medium",
            "command": 'CODEX_MODEL=gpt-5.3-codex-spark python3 "$HARNESS_DIR/tools/codex_operator.py"',
        }

        cmd = _od._build_command(config, {"task_id": "scheduler-task", "command": config["command"]})

        assert cmd == [
            sys.executable,
            str(_od.HARNESS_DIR / "tools" / "codex_operator.py"),
        ]

    def test_windows_fixed_research_worker_uses_native_python_adapter(self, monkeypatch):
        monkeypatch.setattr(_od.os, "name", "nt")
        cmd = _od._build_command(
            {
                "backend": "command",
                "command": 'python3 "$HARNESS_DIR/plugins/autosci/bin/fixed_research_node_adapter.py" --envelope "$SOLAR_OPERATOR_ENVELOPE_JSON"',
            },
            {"task_id": "fixed-research-a4"},
            {"SOLAR_OPERATOR_ENVELOPE_JSON": r"C:\run\operator-envelope.json"},
        )

        assert cmd == [
            sys.executable,
            str(_od.HARNESS_DIR / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"),
            "--envelope",
            r"C:\run\operator-envelope.json",
        ]

    def test_windows_autosci_bridge_worker_uses_native_python_adapter(self, monkeypatch):
        monkeypatch.setattr(_od.os, "name", "nt")
        config = {
            "backend": "command",
            "command": 'python3 "$HARNESS_DIR/plugins/autosci/bin/autosci_bridge.py" run --action discover_literature --envelope "$SOLAR_OPERATOR_ENVELOPE_JSON"',
        }

        cmd = _od._build_command(
            config,
            {"task_id": "scheduler-discovery", "command": config["command"]},
            {"SOLAR_OPERATOR_ENVELOPE_JSON": r"C:\run\operator-envelope.json"},
        )

        assert cmd == [
            sys.executable,
            str(_od.HARNESS_DIR / "plugins" / "autosci" / "bin" / "autosci_bridge.py"),
            "run",
            "--action",
            "discover_literature",
            "--envelope",
            r"C:\run\operator-envelope.json",
        ]

    def test_codex_command_environment_is_platform_neutral(self):
        env = _od._command_operator_environment(
            {
                "backend": "command",
                "provider": "openai",
                "model": "gpt-5.5",
                "model_config": "Codex CLI;gpt-5.5;reasoning=high;evaluator",
            }
        )

        assert env == {
            "CODEX_MODEL": "gpt-5.5",
            "CODEX_REASONING_EFFORT": "high",
            "PYTHONUTF8": "1",
        }


class TestFailureFlowControl:
    def test_terminal_provider_rate_limit_exception_is_not_treated_as_local(self):
        assert (
            _od._failure_runtime_override_skip_reason(
                "request failed\nRuntimeError: HTTP 429 too many requests"
            )
            == ""
        )

    def test_typed_provider_environment_failure_overrides_earlier_429_warning(self):
        failure = "\n".join(
            [
                "Semantic Scholar returned HTTP 429 before a fallback provider ran.",
                json.dumps(
                    {
                        "ok": False,
                        "receipt": {
                            "status": "awaiting_external",
                            "error": {
                                "type": "provider_environment_failure",
                                "detail": "Authoritative coverage remained incomplete.",
                                "retryable": True,
                            },
                        },
                    }
                ),
            ]
        )

        assert _od._failure_runtime_override_skip_reason(failure) == (
            "typed_non_flow_control:provider_environment_failure"
        )

    def _submit_command_task(
        self,
        tmp_path: Path,
        env: dict,
        *,
        task_id: str,
        command: str,
        envelope_updates: dict | None = None,
    ) -> None:
        envelope = {
            "task_id": task_id,
            "sprint_id": "sprint-command",
            "node_id": "N1",
            "operator_id": "test-command-builder",
            "task_type": "dummy",
            "objective": "exercise failure flow control",
            "command": command,
        }
        envelope.update(envelope_updates or {})
        envelope_path = tmp_path / f"{task_id}.json"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "..") + "/lib/operator_runtime.py",
                "submit",
                "--envelope",
                str(envelope_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"submit failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )

    def _run_command_daemon_once(self, env: dict) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                _signal_capable_python(),
                str(TOOLS_DIR / "operatord.py"),
                "daemon",
                "--operator",
                "test-command-builder",
                "--once",
                "--poll-interval",
                "0.2",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_failed_quota_task_sets_cooldown(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        self._submit_command_task(
            tmp_path,
            env,
            task_id="T-cooldown-001",
            command=_command_text(
                [_worker_python(), "-c", "print(\"You've hit your limit; resets soon\", flush=True); raise SystemExit(1)"]
            ),
        )
        daemon_proc = self._run_command_daemon_once(env)
        assert daemon_proc.returncode == 0, daemon_proc.stderr

        status_path = tmp_path / "run" / "operator-status" / "test-command-builder.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["runtime_state"] == "cooldown"
        result_path = tmp_path / "run" / "operator-results" / "test-command-builder" / "T-cooldown-001" / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["status"] == "failed"
        assert "'int' object has no attribute 'seek'" not in result["log_tail"]

    def test_provider_admission_refusal_persists_typed_ids_and_zero_effects(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        work_dir = tmp_path / "sprints" / "sprint-command" / "workdir"
        work_dir.mkdir(parents=True)
        declared_output = work_dir / "report.md"
        worker = (
            "import json,os,pathlib; "
            "ids={'task_id':os.environ['TASK_ID'],'dispatch_id':os.environ['DISPATCH_ID'],"
            "'attempt_id':os.environ['ATTEMPT_ID'],'correlation_id':os.environ['CORRELATION_ID'],"
            "'graph_dispatch_id':os.environ['GRAPH_DISPATCH_ID'],"
            "'scheduler_input_sha256':os.environ['SCHEDULER_INPUT_SHA256'],"
            "'frozen_candidate_ids':json.loads(os.environ['FROZEN_CANDIDATE_IDS_JSON'])}; "
            "receipt={'schema_version':'solar.provider_invocation_receipt.v1','provider':'openai',"
            "'invocation_id':'inv-test','status':'failed','exit_code':1,'identifiers':ids,"
            "'provider_admission_refusal':True,"
            "'structured_stream':{'complete':True,'provider_admission_refusal':True,"
            "'terminal_failed':True,'turn_completed':False,'agent_message_observed':False,"
            "'tool_or_external_event_observed':False,'terminal_error_message':\"You've hit your usage limit\"},"
            "'final_assistant_message':{'present':False,'sha256':''},"
            "'tool_evidence':{'observed':False,'complete':True,'basis':'provider_refusal_before_final_assistant_message'},"
            "'error':{'type':'provider_quota','phase':'admission','retryable':True,"
            "'retry_scope':'frozen_operator_alternative'},"
            "'failure_flow_control':{'runtime_state':'cooldown','reason':'rate_limit'}}; "
            "pathlib.Path(os.environ['TASK_DIR'],'provider-invocation-receipt.json').write_text(json.dumps(receipt)); "
            "print(\"You've hit your usage limit\", flush=True); raise SystemExit(1)"
        )
        self._submit_command_task(
            tmp_path,
            env,
            task_id="T-typed-provider-refusal",
            command=_command_text([_worker_python(), "-c", worker]),
            envelope_updates={
                "dispatch_id": "dispatch-T-typed-provider-refusal",
                "attempt_id": "3",
                "correlation_id": "sprint-command:N1",
                "graph_dispatch_id": "graph-sprint-command-N1-rank2",
                "scheduler_input_sha256": "a" * 64,
                "frozen_candidate_ids": ["op.rank1", "test-command-builder", "op.rank3"],
                "work_dir": str(work_dir),
                "expected_artifacts": [str(declared_output)],
            },
        )

        daemon_proc = self._run_command_daemon_once(env)
        assert daemon_proc.returncode == 0, daemon_proc.stderr
        result_path = (
            tmp_path
            / "run"
            / "operator-results"
            / "test-command-builder"
            / "T-typed-provider-refusal"
            / "result.json"
        )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["error"] == {
            "type": "provider_quota",
            "phase": "admission",
            "retryable": True,
            "retry_scope": "frozen_operator_alternative",
        }
        assert result["failure_flow_control"]["runtime_state"] == "cooldown"
        assert result["dispatch_id"] == "dispatch-T-typed-provider-refusal"
        assert result["attempt_id"] == "3"
        assert result["correlation_id"] == "sprint-command:N1"
        assert result["graph_dispatch_id"] == "graph-sprint-command-N1-rank2"
        assert result["scheduler_input_sha256"] == "a" * 64
        assert result["frozen_candidate_ids"] == [
            "op.rank1",
            "test-command-builder",
            "op.rank3",
        ]
        assert result["effects_receipt"]["complete"] is True
        assert result["effects_receipt"]["effects_started"] is False
        assert result["effects_receipt"]["changed_path_count"] == 0
        assert result["effects_receipt"]["outputs_published"] is False
        assert result["effects_receipt"]["publish_attempted"] is False

    def test_fast_failed_quota_task_drains_trailing_error_before_classification(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        self._submit_command_task(
            tmp_path,
            env,
            task_id="T-cooldown-fast-output",
            command=_command_text(
                [
                    _worker_python(),
                    "-c",
                    (
                        "print('\\n'.join(['dispatch preamble'] * 200), flush=True); "
                        "print(\"You've hit your usage limit for GPT-5.3-Codex-Spark\", flush=True); "
                        "raise SystemExit(1)"
                    ),
                ]
            ),
        )

        daemon_proc = self._run_command_daemon_once(env)
        assert daemon_proc.returncode == 0, daemon_proc.stderr

        status_path = tmp_path / "run" / "operator-status" / "test-command-builder.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["runtime_state"] == "cooldown"
        result_path = (
            tmp_path
            / "run"
            / "operator-results"
            / "test-command-builder"
            / "T-cooldown-fast-output"
            / "result.json"
        )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert "usage limit for GPT-5.3-Codex-Spark" in result["log_tail"]
        assert "[flow-control] runtime_state=cooldown" in result["log_tail"]

    def test_terminal_local_failure_does_not_cooldown_operator_after_earlier_429(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        self._submit_command_task(
            tmp_path,
            env,
            task_id="T-local-path-after-429",
            command=_command_text(
                [
                    _worker_python(),
                    "-c",
                    (
                        "print('HTTP 429 from an earlier recoverable provider request', flush=True); "
                        "open('definitely-missing-local-artifact.json', encoding='utf-8')"
                    ),
                ]
            ),
        )

        daemon_proc = self._run_command_daemon_once(env)
        assert daemon_proc.returncode == 0, daemon_proc.stderr

        status_path = tmp_path / "run" / "operator-status" / "test-command-builder.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["runtime_state"] == "idle"
        result_path = (
            tmp_path
            / "run"
            / "operator-results"
            / "test-command-builder"
            / "T-local-path-after-429"
            / "result.json"
        )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["status"] == "failed"
        assert "FileNotFoundError:" in result["log_tail"]
        assert "[flow-control] skipped=terminal_local_failure" in result["log_tail"]
        assert "[flow-control] runtime_state=cooldown" not in result["log_tail"]

    def test_failed_auth_task_sets_auth_expired(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        self._submit_command_task(
            tmp_path,
            env,
            task_id="T-auth-001",
            command=_command_text(
                [_worker_python(), "-c", "print('You are not logged in', flush=True); raise SystemExit(1)"]
            ),
        )
        daemon_proc = self._run_command_daemon_once(env)
        assert daemon_proc.returncode == 0, daemon_proc.stderr

        status_path = tmp_path / "run" / "operator-status" / "test-command-builder.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["runtime_state"] == "auth_expired"
        result_path = tmp_path / "run" / "operator-results" / "test-command-builder" / "T-auth-001" / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["status"] == "failed"
        assert "'int' object has no attribute 'seek'" not in result["log_tail"]

    def test_timeout_records_terminal_result(self, tmp_path):
        env = _setup_command_harness(tmp_path)
        env["SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS"] = "1"
        self._submit_command_task(
            tmp_path,
            env,
            task_id="T-timeout-001",
            command=_command_text([_worker_python(), "-c", "import time; time.sleep(30)"]),
        )

        daemon_proc = self._run_command_daemon_once(env)
        assert daemon_proc.returncode == 0, daemon_proc.stderr
        result_path = tmp_path / "run" / "operator-results" / "test-command-builder" / "T-timeout-001" / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["status"] == "failed_timeout"
        assert result["exit_code"] == 124
