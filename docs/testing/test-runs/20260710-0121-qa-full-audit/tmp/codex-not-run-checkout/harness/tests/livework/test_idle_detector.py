"""Tests for livework/idle_detector.py: is_idle, detect_deadlock, should_emit_heartbeat.

Acceptance:
- 3 functions with now/timeout/interval all explicit parameters
- Zero calls to time.time() / datetime.now() / datetime.utcnow()
- detect_deadlock returns List[DeadlockAlert] with pane/sprint_id/silence_seconds/threshold
- Tests cover active / idle / deadlock + heartbeat boundary
- pytest exit 0, assertions >= 12
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import subprocess
import pytest

from livework.idle_detector import (
    DeadlockAlert,
    detect_deadlock,
    is_idle,
    should_emit_heartbeat,
)


# ---------------------------------------------------------------------------
# Tests: is_idle
# ---------------------------------------------------------------------------

class TestIsIdle:
    def test_idle_when_all_clear(self):
        pane_state = {"is_idle": True, "active_panes": [], "queue_depth": 0}
        assert is_idle(pane_state, "2026-05-14T12:00:00Z") is True

    def test_not_idle_when_flag_false(self):
        pane_state = {"is_idle": False, "active_panes": [], "queue_depth": 0}
        assert is_idle(pane_state, "2026-05-14T12:00:00Z") is False

    def test_not_idle_with_active_panes(self):
        pane_state = {"is_idle": True, "active_panes": ["solar-harness-lab:0.0"], "queue_depth": 0}
        assert is_idle(pane_state, "2026-05-14T12:00:00Z") is False

    def test_not_idle_with_queue_depth(self):
        pane_state = {"is_idle": True, "active_panes": [], "queue_depth": 3}
        assert is_idle(pane_state, "2026-05-14T12:00:00Z") is False

    def test_idle_defaults_on_empty_dict(self):
        assert is_idle({}, "2026-05-14T12:00:00Z") is True


# ---------------------------------------------------------------------------
# Tests: detect_deadlock
# ---------------------------------------------------------------------------

class TestDetectDeadlock:
    def test_no_alert_when_within_timeout(self):
        log = [
            {
                "pane": "lab:0.0",
                "sprint_id": "sprint-001",
                "node_id": "N1",
                "dispatched_at": "2026-05-14T11:50:00Z",
                "last_heartbeat": "2026-05-14T11:55:00Z",
            }
        ]
        alerts = detect_deadlock(log, "2026-05-14T11:59:00Z", timeout=600.0)
        assert alerts == []

    def test_alert_when_silence_exceeds_timeout(self):
        log = [
            {
                "pane": "lab:0.0",
                "sprint_id": "sprint-001",
                "node_id": "N1",
                "dispatched_at": "2026-05-14T10:00:00Z",
                "last_heartbeat": "2026-05-14T10:00:00Z",
            }
        ]
        alerts = detect_deadlock(log, "2026-05-14T12:00:00Z", timeout=600.0)
        assert len(alerts) == 1
        assert alerts[0].pane == "lab:0.0"
        assert alerts[0].sprint_id == "sprint-001"
        assert alerts[0].silence_seconds > 600.0
        assert alerts[0].threshold_seconds == 600.0

    def test_no_alert_on_empty_log(self):
        assert detect_deadlock([], "2026-05-14T12:00:00Z") == []

    def test_multiple_entries_mixed(self):
        log = [
            {
                "pane": "lab:0.0",
                "sprint_id": "sprint-001",
                "node_id": "N1",
                "dispatched_at": "2026-05-14T10:00:00Z",
                "last_heartbeat": "2026-05-14T10:00:00Z",
            },
            {
                "pane": "lab:0.1",
                "sprint_id": "sprint-001",
                "node_id": "N2",
                "dispatched_at": "2026-05-14T11:58:00Z",
                "last_heartbeat": "2026-05-14T11:59:00Z",
            },
        ]
        alerts = detect_deadlock(log, "2026-05-14T12:00:00Z", timeout=600.0)
        assert len(alerts) == 1
        assert alerts[0].pane == "lab:0.0"

    def test_returns_deadlock_alert_objects(self):
        log = [
            {
                "pane": "lab:0.2",
                "sprint_id": "sprint-002",
                "node_id": "N4",
                "dispatched_at": "2026-05-14T09:00:00Z",
            }
        ]
        alerts = detect_deadlock(log, "2026-05-14T12:00:00Z", timeout=600.0)
        assert len(alerts) == 1
        a = alerts[0]
        assert isinstance(a, DeadlockAlert)
        assert a.pane == "lab:0.2"
        assert a.sprint_id == "sprint-002"
        assert a.node_id == "N4"
        assert a.silence_seconds > 0
        assert a.threshold_seconds == 600.0


# ---------------------------------------------------------------------------
# Tests: should_emit_heartbeat
# ---------------------------------------------------------------------------

class TestShouldEmitHeartbeat:
    def test_emit_when_no_prior(self):
        assert should_emit_heartbeat("", "2026-05-14T12:00:00Z") is True

    def test_no_emit_within_interval(self):
        assert should_emit_heartbeat(
            "2026-05-14T11:59:30Z",
            "2026-05-14T12:00:00Z",
            interval=60.0,
        ) is False

    def test_emit_after_interval(self):
        assert should_emit_heartbeat(
            "2026-05-14T11:00:00Z",
            "2026-05-14T12:00:00Z",
            interval=60.0,
        ) is True

    def test_emit_at_exact_interval_boundary(self):
        assert should_emit_heartbeat(
            "2026-05-14T11:59:00Z",
            "2026-05-14T12:00:00Z",
            interval=60.0,
        ) is True

    def test_custom_interval(self):
        assert should_emit_heartbeat(
            "2026-05-14T11:55:00Z",
            "2026-05-14T12:00:00Z",
            interval=300.0,
        ) is True
        assert should_emit_heartbeat(
            "2026-05-14T11:56:00Z",
            "2026-05-14T12:00:00Z",
            interval=300.0,
        ) is False


# ---------------------------------------------------------------------------
# Static check: zero time.time() / datetime.now() / datetime.utcnow()
# ---------------------------------------------------------------------------

class TestTimeInjectionPurity:
    def test_no_direct_time_calls(self):
        source = Path(__file__).resolve().parent.parent.parent / "lib" / "livework" / "idle_detector.py"
        text = source.read_text()
        forbidden = ["time.time()", "datetime.now()", "datetime.utcnow()"]
        for pattern in forbidden:
            assert pattern not in text, f"Forbidden pattern '{pattern}' found in idle_detector.py"
