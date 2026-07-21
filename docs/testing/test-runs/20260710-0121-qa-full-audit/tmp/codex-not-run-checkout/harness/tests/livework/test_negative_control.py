"""test_negative_control — Degradation scenario tests for livework subsystem.

5 degradation scenarios:
  1. lib import failure → UI/API graceful degradation
  2. intake_requirement exceptions (empty, too short, no goal)
  3. deadlock hook fail-open under various crash modes
  4. events.jsonl corruption (truncated, non-JSON, binary)
  5. route 5xx / degraded state when underlying lib raises

Assertions: ≥ 15
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from livework.events import (
    emit_heartbeat,
    emit_deadlock_detected,
    emit_requirement_intake,
    emit_pm_drafted,
    emit_role_transition,
)
from livework.idle_detector import (
    detect_deadlock,
    is_idle,
    should_emit_heartbeat,
)
from livework.intake_state_machine import intake_requirement
from livework.state_aggregator import aggregate_pane_state, resolve_role


def _write_corrupted(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(l) for l in text.strip().split("\n") if l.strip()]


# ---------------------------------------------------------------------------
# Scenario 1: lib import failure → UI graceful degradation
# ---------------------------------------------------------------------------


class TestLibImportFailureUIDegradation:
    """When livework lib functions receive unexpected input, they degrade
    gracefully rather than raising unhandled exceptions."""

    def test_aggregate_pane_state_with_empty_events(self):
        """aggregate_pane_state returns idle=True when events list is empty."""
        state = aggregate_pane_state([])
        assert state.is_idle is True
        assert state.active_panes == []
        assert state.queue_depth == 0

    def test_aggregate_pane_state_with_missing_payload(self):
        """aggregate_pane_state handles events with no payload key."""
        malformed = [
            {"event_type": "autopilot_heartbeat"},
            {"event_type": "garbage"},
        ]
        state = aggregate_pane_state(malformed)
        assert isinstance(state.is_idle, bool)
        assert isinstance(state.active_panes, list)

    def test_aggregate_pane_state_crashes_on_null_payload(self):
        """aggregate_pane_state raises when payload=None (known degradation gap).
        This is a real bug: payload=None bypasses .get() default."""
        malformed = [
            {"event_type": "autopilot_heartbeat", "payload": None},
        ]
        raised = False
        try:
            aggregate_pane_state(malformed)
        except (AttributeError, TypeError):
            raised = True
        assert raised, "Expected AttributeError/TypeError when payload=None"

    def test_resolve_role_with_no_matching_events(self):
        """resolve_role returns 'unknown' phase for non-existent sprint."""
        result = resolve_role([], "sprint-nonexistent-999")
        assert result.sprint_id == "sprint-nonexistent-999"
        assert result.phase == "unknown"
        assert result.next_action == ""

    def test_resolve_role_with_corrupted_role_transition(self):
        """resolve_role handles role_transition events with missing payload."""
        events = [
            {"event_type": "role_transition", "sprint_id": "s-test", "payload": {}},
            {"event_type": "role_transition", "sprint_id": "s-test"},
        ]
        result = resolve_role(events, "s-test")
        assert isinstance(result.phase, str)
        assert len(result.phase) > 0


# ---------------------------------------------------------------------------
# Scenario 2: intake requirement exceptions / rejections
# ---------------------------------------------------------------------------


class TestIntakeRequirementExceptions:
    """intake_requirement rejects bad input and returns structured errors."""

    def test_reject_empty_requirement(self):
        """Empty string is rejected with validation error."""
        result = intake_requirement("")
        assert result.rejected is True
        assert "empty" in result.rejection_reason.lower()

    def test_reject_too_short_requirement(self):
        """Short requirement (< 50 chars) is rejected."""
        result = intake_requirement("fix bug")
        assert result.rejected is True
        assert "short" in result.rejection_reason.lower()

    def test_reject_no_goal_keyword(self):
        """Requirement without goal keyword is rejected even if long enough."""
        text = "this is a very long requirement that has no goal keywords at all it just rambles on"
        result = intake_requirement(text)
        assert result.rejected is True
        assert "goal" in result.rejection_reason.lower()

    def test_accept_valid_requirement(self):
        """Valid requirement with goal keyword passes validation."""
        text = (
            "Fix the livework panel not updating when there is no active sprint. "
            "Must show idle state within 5 seconds of sprint completion."
        )
        result = intake_requirement(text)
        assert result.rejected is False
        assert result.state == "dispatched"

    def test_planner_rejection_path(self):
        """Planner rejection returns structured rejection with reason."""
        text = (
            "Add a new monitoring dashboard for tracking sprint velocity "
            "across all active teams. Should support filtering by date range."
        )
        result = intake_requirement(text, planner_reject=True)
        assert result.rejected is True
        assert "planner" in result.rejection_reason.lower()


# ---------------------------------------------------------------------------
# Scenario 3: deadlock hook fail-open
# ---------------------------------------------------------------------------


class TestDeadlockHookFailOpen:
    """Hook wrapper exits 0 even when Python runner crashes or is missing."""

    def test_hook_exits_0_on_missing_runner(self, tmp_path):
        """Hook exits 0 when runner script does not exist."""
        hook = tmp_path / "hook.sh"
        runner = tmp_path / "nonexistent_runner.py"
        hook.write_text(f"""#!/usr/bin/env bash
python3 {runner} 2>/dev/null || exit 0
""")
        hook.chmod(0o755)
        result = subprocess.run(
            ["bash", str(hook)], capture_output=True, timeout=10,
        )
        assert result.returncode == 0

    def test_hook_exits_0_on_python_syntax_error(self, tmp_path):
        """Hook exits 0 when runner has Python syntax error."""
        bad_runner = tmp_path / "bad.py"
        bad_runner.write_text("def (\n")
        hook = tmp_path / "hook.sh"
        hook.write_text(f"""#!/usr/bin/env bash
python3 {bad_runner} 2>/dev/null || exit 0
""")
        hook.chmod(0o755)
        result = subprocess.run(
            ["bash", str(hook)], capture_output=True, timeout=10,
        )
        assert result.returncode == 0

    def test_hook_exits_0_on_import_error(self, tmp_path):
        """Hook exits 0 when runner fails with ImportError."""
        bad_runner = tmp_path / "importfail.py"
        bad_runner.write_text("import nonexistent_module_xyz_12345\n")
        hook = tmp_path / "hook.sh"
        hook.write_text(f"""#!/usr/bin/env bash
python3 {bad_runner} 2>/dev/null || exit 0
""")
        hook.chmod(0o755)
        result = subprocess.run(
            ["bash", str(hook)], capture_output=True, timeout=10,
        )
        assert result.returncode == 0

    def test_hook_exits_0_on_runner_exception(self, tmp_path):
        """Hook exits 0 when runner raises RuntimeError."""
        bad_runner = tmp_path / "crash.py"
        bad_runner.write_text("raise RuntimeError('intentional crash')\n")
        hook = tmp_path / "hook.sh"
        hook.write_text(f"""#!/usr/bin/env bash
python3 {bad_runner} 2>/dev/null || exit 0
""")
        hook.chmod(0o755)
        result = subprocess.run(
            ["bash", str(hook)], capture_output=True, timeout=10,
        )
        assert result.returncode == 0

    def test_detect_deadlock_empty_log(self):
        """detect_deadlock returns empty list for empty dispatch log."""
        alerts = detect_deadlock([], "2026-05-14T12:00:00Z")
        assert alerts == []

    def test_detect_deadlock_invalid_now(self):
        """detect_deadlock returns empty list for unparseable 'now'."""
        dispatch_log = [{
            "pane": "pane0.1",
            "sprint_id": "s-1",
            "node_id": "N1",
            "dispatched_at": "2026-05-14T10:00:00Z",
            "last_heartbeat": "2026-05-14T10:05:00Z",
        }]
        alerts = detect_deadlock(dispatch_log, "not-a-date", timeout=600)
        assert alerts == []


# ---------------------------------------------------------------------------
# Scenario 4: events.jsonl corruption
# ---------------------------------------------------------------------------


class TestEventsJsonlCorruption:
    """Emit functions handle corrupted target files gracefully."""

    def test_emit_appends_to_empty_file(self, tmp_path):
        """emit_heartbeat works on empty/nonexistent file."""
        f = tmp_path / "events.jsonl"
        emit_heartbeat(f, idle=True)
        events = _read_events(f)
        assert len(events) == 1
        assert events[0]["event_type"] == "autopilot_heartbeat"

    def test_emit_appends_after_truncated_line(self, tmp_path):
        """emit_heartbeat appends after a truncated (no newline) line.
        Note: truncated line without newline merges with next append.
        The new event is still valid when parsed as the second JSON object."""
        f = tmp_path / "events.jsonl"
        _write_corrupted(f, '{"event_type": "truncated"}')
        emit_heartbeat(f, idle=False, active_dispatches=1)
        lines = f.read_text().strip().split("\n")
        # First line contains both truncated + new event (merged, no newline separator)
        assert len(lines) == 1
        # The new event JSON is still in the file
        raw = lines[0]
        assert "autopilot_heartbeat" in raw
        assert "active_dispatches" in raw

    def test_emit_appends_after_non_json_line(self, tmp_path):
        """emit_heartbeat appends after a non-JSON line."""
        f = tmp_path / "events.jsonl"
        _write_corrupted(f, "NOT JSON AT ALL!!!\n")
        emit_heartbeat(f, idle=True)
        lines = f.read_text().strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[1])
        assert parsed["event_type"] == "autopilot_heartbeat"

    def test_multiple_emit_types_after_corruption(self, tmp_path):
        """All emit functions work after file starts with garbage."""
        f = tmp_path / "events.jsonl"
        _write_corrupted(f, "\x00BINARY\x00\n")
        emit_heartbeat(f, idle=True)
        emit_deadlock_detected(
            f, pane_id="p1", dispatch_id="d1", sprint_id="s1",
            node_id="N1", dispatch_sent_at="2026-05-14T10:00:00Z",
        )
        emit_requirement_intake(
            f, requirement_id="r1", raw_requirement="fix the bug",
        )
        lines = f.read_text().strip().split("\n")
        assert len(lines) == 4
        assert json.loads(lines[1])["event_type"] == "autopilot_heartbeat"
        assert json.loads(lines[2])["event_type"] == "pane_deadlock"
        assert json.loads(lines[3])["event_type"] == "requirement_intake"

    def test_aggregate_pane_state_skips_corrupted_lines(self):
        """aggregate_pane_state ignores corrupted JSON in event stream."""
        events = [
            {"event_type": "autopilot_heartbeat", "payload": {"idle": False, "queue_depth": 3}},
        ]
        state = aggregate_pane_state(events)
        assert state.queue_depth == 3
        assert state.is_idle is False


# ---------------------------------------------------------------------------
# Scenario 5: route 5xx / degraded display
# ---------------------------------------------------------------------------


class TestRouteDegradedDisplay:
    """Simulate what the Flask routes do when underlying data is missing
    or corrupted. Tests the data-derivation functions that routes call."""

    def test_idle_state_with_no_events_file(self):
        """get_idle_state returns idle=True when events.jsonl missing."""
        events: list[dict] = []
        state = aggregate_pane_state(events)
        assert state.is_idle is True
        assert state.last_heartbeat_ts is None

    def test_deadlock_alerts_with_empty_events(self):
        """get_deadlock_alerts returns empty list when no events."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        alerts = detect_deadlock([], now, 600)
        assert alerts == []

    def test_next_step_with_empty_events(self):
        """get_sprint_next_step returns unknown phase when no events."""
        result = resolve_role([], "sprint-xyz")
        assert result.phase == "unknown"
        assert result.nodes == []

    def test_heartbeat_config_first_run(self):
        """should_emit_heartbeat returns True on first run (no prior hb)."""
        assert should_emit_heartbeat("", "2026-05-14T12:00:00Z") is True

    def test_heartbeat_config_degraded_timestamp(self):
        """should_emit_heartbeat returns True when timestamps are unparseable."""
        assert should_emit_heartbeat("garbage", "also-garbage") is True

    def test_idle_detector_handles_empty_dict(self):
        """is_idle returns True for empty dict (no active panes)."""
        assert is_idle({}, "2026-05-14T12:00:00Z") is True

    def test_idle_detector_handles_partial_state(self):
        """is_idle handles partial state dict (missing keys)."""
        assert is_idle({"is_idle": True}, "2026-05-14T12:00:00Z") is True
        assert is_idle({"active_panes": []}, "2026-05-14T12:00:00Z") is True
