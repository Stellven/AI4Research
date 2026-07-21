"""test_events — Verify livework/events.py emit_* functions with real file I/O."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from livework.events import (
    emit_deadlock_detected,
    emit_heartbeat,
    emit_pm_drafted,
    emit_requirement_intake,
    emit_role_transition,
)


def _read_events(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    return [json.loads(line) for line in lines if line.strip()]


class TestEmitHeartbeat:
    def test_appends_one_line(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_heartbeat(f, idle=True, queue_depth=0)
        events = _read_events(f)
        assert len(events) == 1
        assert events[0]["event_type"] == "autopilot_heartbeat"

    def test_payload_fields(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_heartbeat(f, idle=False, active_dispatches=3, queue_depth=1)
        events = _read_events(f)
        assert events[0]["payload"]["idle"] is False
        assert events[0]["payload"]["active_dispatches"] == 3
        assert events[0]["payload"]["queue_depth"] == 1


class TestEmitDeadlockDetected:
    def test_appends_deadlock_event(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_deadlock_detected(
            f, pane_id="pane0.1", dispatch_id="did-123", sprint_id="s-1",
            node_id="N2", dispatch_sent_at="2026-05-14T12:00:00Z",
            elapsed_seconds=900,
        )
        events = _read_events(f)
        assert len(events) == 1
        assert events[0]["event_type"] == "pane_deadlock"
        assert events[0]["payload"]["pane_id"] == "pane0.1"
        assert events[0]["payload"]["elapsed_seconds"] == 900

    def test_deadlock_timestamp_present(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_deadlock_detected(
            f, pane_id="p1", dispatch_id="d1", sprint_id="s1",
            node_id="N1", dispatch_sent_at="2026-01-01T00:00:00Z",
        )
        events = _read_events(f)
        assert events[0]["timestamp"] != ""
        assert "T" in events[0]["timestamp"]


class TestEmitRequirementIntake:
    def test_appends_intake_event(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_requirement_intake(
            f, requirement_id="req-001", raw_requirement="Fix idle display",
        )
        events = _read_events(f)
        assert len(events) == 1
        assert events[0]["event_type"] == "requirement_intake"
        assert events[0]["payload"]["raw_requirement"] == "Fix idle display"

    def test_validation_error_fields(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_requirement_intake(
            f, requirement_id="req-002", raw_requirement="too short",
            validation_error_code="E001",
            validation_error_message="Requirement too vague",
            validation_hint="Provide at least 50 characters",
        )
        events = _read_events(f)
        assert events[0]["payload"]["validation_error_code"] == "E001"
        assert events[0]["payload"]["validation_error_message"] == "Requirement too vague"


class TestEmitPmDrafted:
    def test_appends_pm_drafted_event(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_pm_drafted(f, sprint_id="s-1", outcome_count=5)
        events = _read_events(f)
        assert events[0]["event_type"] == "pm_drafted"
        assert events[0]["payload"]["outcome_count"] == 5
        assert events[0]["payload"]["prd_ready"] is True


class TestEmitRoleTransition:
    def test_appends_role_transition(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_role_transition(
            f, sprint_id="s-1", from_phase="pm_analysis",
            to_phase="planner_design", actor="coordinator", reason="prd_ready",
        )
        events = _read_events(f)
        assert events[0]["event_type"] == "role_transition"
        assert events[0]["payload"]["from_phase"] == "pm_analysis"
        assert events[0]["payload"]["to_phase"] == "planner_design"
        assert events[0]["payload"]["reason"] == "prd_ready"


class TestAppendOnly:
    def test_multiple_emits_append(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_heartbeat(f, idle=True)
        emit_heartbeat(f, idle=False, active_dispatches=1)
        emit_deadlock_detected(
            f, pane_id="p1", dispatch_id="d1", sprint_id="s1",
            node_id="N1", dispatch_sent_at="2026-01-01T00:00:00Z",
        )
        events = _read_events(f)
        assert len(events) == 3
        assert events[0]["event_type"] == "autopilot_heartbeat"
        assert events[1]["payload"]["active_dispatches"] == 1
        assert events[2]["event_type"] == "pane_deadlock"

    def test_schema_version_present(self, tmp_path):
        f = tmp_path / "events.jsonl"
        emit_heartbeat(f, idle=True)
        events = _read_events(f)
        assert events[0]["schema_version"] == "1.0.0"


class TestNoMock:
    def test_no_mock_patch_in_file(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-rc", "@mock\\.patch|from unittest\\.mock|import mock",
             str(Path(__file__).resolve())],
            capture_output=True, text=True,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l and not l.endswith(":0")]
        assert lines == [], f"Mock usage found: {lines}"
