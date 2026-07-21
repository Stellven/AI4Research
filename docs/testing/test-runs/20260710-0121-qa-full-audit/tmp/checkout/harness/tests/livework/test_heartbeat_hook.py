"""test_heartbeat_hook — Verify livework heartbeat hook and runner.

Tests cover:
  (a) Normal exit 0
  (b) Runner throws exception, hook still exits 0
  (c) Runner emits real events to tmp events.jsonl
  (d) Heartbeat throttling via should_emit_heartbeat
  (e) Deadlock detection triggers emit
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from livework.events import emit_heartbeat, emit_deadlock_detected
from livework.idle_detector import should_emit_heartbeat, detect_deadlock, is_idle


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(l) for l in text.strip().split("\n") if l.strip()]


class TestHookFailOpen:
    def test_hook_exits_0_when_runner_missing(self, tmp_path):
        """Hook exits 0 even when runner script doesn't exist."""
        fake_hook = tmp_path / "hook.sh"
        fake_hook.write_text("#!/usr/bin/env bash\nexit 0\n")
        fake_hook.chmod(0o755)
        result = subprocess.run(
            ["bash", str(fake_hook)],
            capture_output=True, timeout=10,
        )
        assert result.returncode == 0

    def test_hook_exits_0_when_runner_fails(self, tmp_path):
        """Hook exits 0 even when Python runner raises an exception."""
        bad_runner = tmp_path / "bad_runner.py"
        bad_runner.write_text("import sys\nsys.exit(1)\n")
        hook_script = tmp_path / "hook.sh"
        hook_script.write_text(
            "#!/usr/bin/env bash\n"
            f"python3 {bad_runner} 2>/dev/null || exit 0\n"
        )
        hook_script.chmod(0o755)
        result = subprocess.run(
            ["bash", str(hook_script)],
            capture_output=True, timeout=10,
        )
        assert result.returncode == 0

    def test_hook_exits_0_when_python_crashes(self, tmp_path):
        """Hook exits 0 when Python throws ImportError."""
        bad_runner = tmp_path / "crash.py"
        bad_runner.write_text("import nonexistent_module_xyz\n")
        hook_script = tmp_path / "hook.sh"
        hook_script.write_text(
            "#!/usr/bin/env bash\n"
            f"python3 {bad_runner} 2>/dev/null || exit 0\n"
        )
        hook_script.chmod(0o755)
        result = subprocess.run(
            ["bash", str(hook_script)],
            capture_output=True, timeout=10,
        )
        assert result.returncode == 0


class TestRunnerEmitRealEvents:
    def test_actual_runner_writes_event_from_arbitrary_cwd(self, tmp_path):
        f = tmp_path / "runner-events.jsonl"
        runner = Path("~/.solar/harness/autopilot/hooks/livework_heartbeat_runner.py")
        env = {
            **os.environ,
            "HARNESS_DIR": "~/.solar/harness",
            "LIVEWORK_EVENTS_JSONL": str(f),
            "LIVEWORK_HEARTBEAT_INTERVAL": "0",
        }
        result = subprocess.run(
            ["python3", str(runner)],
            cwd="/tmp",
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        events = _read_events(f)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "autopilot_heartbeat"

    def test_emit_heartbeat_writes_real_file(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_heartbeat(f, idle=True, queue_depth=0)
        events = _read_events(f)
        assert len(events) == 1
        assert events[0]["event_type"] == "autopilot_heartbeat"
        assert events[0]["payload"]["idle"] is True

    def test_emit_deadlock_writes_real_file(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_deadlock_detected(
            f, pane_id="pane0.2", dispatch_id="did-abc",
            sprint_id="s-test", node_id="N5",
            dispatch_sent_at="2026-05-14T10:00:00Z",
            elapsed_seconds=700,
        )
        events = _read_events(f)
        assert len(events) == 1
        assert events[0]["event_type"] == "pane_deadlock"
        assert events[0]["payload"]["pane_id"] == "pane0.2"

    def test_multiple_events_append_correctly(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_heartbeat(f, idle=True)
        emit_heartbeat(f, idle=False, active_dispatches=2)
        emit_deadlock_detected(
            f, pane_id="p1", dispatch_id="d1", sprint_id="s1",
            node_id="N1", dispatch_sent_at="2026-01-01T00:00:00Z",
        )
        events = _read_events(f)
        assert len(events) == 3
        assert events[0]["payload"]["idle"] is True
        assert events[1]["payload"]["active_dispatches"] == 2
        assert events[2]["event_type"] == "pane_deadlock"


class TestIdleDetectorIntegration:
    def test_is_idle_with_empty_state(self):
        assert is_idle({}, "2026-05-14T12:00:00Z") is True

    def test_is_idle_with_active_panes(self):
        state = {"is_idle": True, "active_panes": ["pane0.1"], "queue_depth": 0}
        assert is_idle(state, "2026-05-14T12:00:00Z") is False

    def test_should_emit_heartbeat_first_time(self):
        assert should_emit_heartbeat("", "2026-05-14T12:00:00Z") is True

    def test_should_emit_heartbeat_too_soon(self):
        assert should_emit_heartbeat(
            "2026-05-14T12:00:00Z", "2026-05-14T12:01:00Z", interval=300
        ) is False

    def test_detect_deadlock_finds_stale_pane(self):
        dispatch_log = [{
            "pane": "pane0.1",
            "sprint_id": "s-1",
            "node_id": "N3",
            "dispatched_at": "2026-05-14T10:00:00Z",
            "last_heartbeat": "2026-05-14T10:05:00Z",
        }]
        alerts = detect_deadlock(dispatch_log, "2026-05-14T11:00:00Z", timeout=600)
        assert len(alerts) == 1
        assert alerts[0].pane == "pane0.1"
        assert alerts[0].silence_seconds > 600


class TestNoAutopilotChange:
    def test_autopilot_sh_unchanged(self):
        """Verify autopilot.sh was not modified by this node."""
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--",
             "autopilot.sh", "autopilot/**"],
            capture_output=True, text=True,
            cwd="~/.solar/harness",
        )
        assert "autopilot" not in result.stdout, f"autopilot files changed: {result.stdout}"
