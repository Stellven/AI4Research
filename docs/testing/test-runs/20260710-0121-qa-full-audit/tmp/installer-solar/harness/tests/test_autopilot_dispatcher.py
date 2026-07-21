"""
Tests for autopilot_operator_dispatcher — S04 N2.

Cases:
  1. Normal dispatch — due line found, dispatch succeeds, metadata written.
  2. No due line — tick at a time with no matching cron returns empty.
  3. Dispatch failure — primary + fallback fail, state transitions to FAILED.
  4. Dual-run dispatch — github_trends dispatches with control, metadata collected.
  5. Cron parsing — various cron expressions correctly matched.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure lib/ is on sys.path
_LIB = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from operator_router import ControlComparisonResult, DispatchResult, NoFallbackError
from operator_state_machine import OperatorState

from autopilot_operator_dispatcher import (
    ScheduleLoadError,
    cron_matches,
    dispatch_line,
    find_due_lines,
    tick,
)

# --- fixtures ---

_SCHEDULES: dict[str, Any] = {
    "schema_version": "solar.operator_schedules.v1",
    "generated_at": "2026-05-30T23:55:19Z",
    "bindings": {
        "x_social": {
            "line": "x_social",
            "primary": "scripts/ai_influence_daily.py",
            "source_schedule": "daily",
            "type": "cron",
            "cron": "0 8 * * *",
        },
        "github_trends": {
            "line": "github_trends",
            "primary": "scripts/github_trends_digest.py",
            "source_schedule": "daily",
            "type": "cron",
            "cron": "30 8 * * *",
            "dual_run": {"enabled": True, "comparison_view": True},
        },
        "hf_papers": {
            "line": "hf_papers",
            "primary": "scripts/tech_hotspot_radar.py",
            "source_schedule": "daily",
            "type": "cron",
            "cron": "0 9 * * *",
        },
        "gemini_research": {
            "line": "gemini_research",
            "primary": "tools/gemini_deep_research_operator.py",
            "source_schedule": "on_demand",
            "type": "manual",
            "cron": None,
        },
        "youtube": {
            "line": "youtube",
            "primary": "scripts/youtube_influence_digest.py",
            "source_schedule": "daily",
            "type": "cron",
            "cron": "30 9 * * *",
        },
    },
}


def _make_dispatch_result(
    line: str = "x_social",
    run_id: str = "test-run-1",
    role: str = "primary",
    script: str = "scripts/ai_influence_daily.py",
    success: bool = True,
    returncode: int = 0,
) -> DispatchResult:
    return DispatchResult(
        line=line,
        run_id=run_id,
        role=role,
        script=script,
        returncode=returncode,
        stdout="ok",
        stderr="",
        success=success,
        duration_s=1.5,
    )


def _make_control_result(
    line: str = "github_trends",
    run_id: str = "test-run-2",
    primary_success: bool = True,
    control_success: bool = True,
) -> ControlComparisonResult:
    primary = _make_dispatch_result(
        line=line, run_id=run_id, role="primary",
        script="scripts/github_trends_digest.py", success=primary_success,
        returncode=0 if primary_success else 1,
    )
    control = _make_dispatch_result(
        line=line, run_id=run_id, role="control",
        script="tools/github_intelligence/pipeline.py", success=control_success,
        returncode=0 if control_success else 1,
    )
    return ControlComparisonResult(
        line=line,
        run_id=run_id,
        primary=primary,
        control=control,
        both_succeeded=primary_success and control_success,
    )


# --- Case 1: cron matching ---


class TestCronMatches:
    """Verify cron expression parsing and matching."""

    def test_exact_match(self):
        dt = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)  # Friday
        assert cron_matches("0 8 * * *", dt) is True

    def test_no_match_wrong_minute(self):
        dt = datetime(2026, 5, 30, 8, 15, tzinfo=timezone.utc)
        assert cron_matches("0 8 * * *", dt) is False

    def test_no_match_wrong_hour(self):
        dt = datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc)
        assert cron_matches("0 8 * * *", dt) is False

    def test_wildcard_dow(self):
        # Should match any day of week
        for day in range(25, 32):  # May 25 (Sun) through May 31 (Sat)
            try:
                dt = datetime(2026, 5, day, 8, 0, tzinfo=timezone.utc)
                assert cron_matches("0 8 * * *", dt) is True
            except ValueError:
                pass  # May doesn't have 32

    def test_specific_dow_sunday(self):
        # May 31 2026 is a Sunday; cron dow 0 = Sunday
        dt = datetime(2026, 5, 31, 8, 0, tzinfo=timezone.utc)
        assert cron_matches("0 8 * * 0", dt) is True
        assert cron_matches("0 8 * * 1", dt) is False  # Monday

    def test_specific_dow_monday(self):
        # May 25 2026 is a Monday; cron dow 1 = Monday
        dt = datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc)
        assert cron_matches("0 8 * * 1", dt) is True

    def test_step_expression(self):
        dt = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
        assert cron_matches("*/30 8 * * *", dt) is True  # 0 matches */30
        dt2 = datetime(2026, 5, 30, 8, 30, tzinfo=timezone.utc)
        assert cron_matches("*/30 8 * * *", dt2) is True
        dt3 = datetime(2026, 5, 30, 8, 15, tzinfo=timezone.utc)
        assert cron_matches("*/30 8 * * *", dt3) is False

    def test_range_expression(self):
        dt = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
        assert cron_matches("0 7-9 * * *", dt) is True
        dt2 = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)
        assert cron_matches("0 7-9 * * *", dt2) is False

    def test_invalid_field_count(self):
        dt = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
        assert cron_matches("0 8 * *", dt) is False  # only 4 fields


# --- Case 2: due-line detection ---


class TestFindDueLines:
    """Verify due-line detection from schedules."""

    def test_finds_due_at_0800(self):
        now = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
        due = find_due_lines(schedules=_SCHEDULES, now=now)
        assert "x_social" in due

    def test_finds_due_at_0830(self):
        now = datetime(2026, 5, 30, 8, 30, tzinfo=timezone.utc)
        due = find_due_lines(schedules=_SCHEDULES, now=now)
        assert "github_trends" in due

    def test_no_due_at_1200(self):
        now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        due = find_due_lines(schedules=_SCHEDULES, now=now)
        assert len(due) == 0

    def test_manual_never_due(self):
        # Even at any time, gemini_research (manual) should not appear
        for hour in range(24):
            for minute in (0, 30):
                now = datetime(2026, 5, 30, hour, minute, tzinfo=timezone.utc)
                due = find_due_lines(schedules=_SCHEDULES, now=now)
                assert "gemini_research" not in due


# --- Case 3: normal dispatch ---


class TestDispatchLineNormal:
    """Case 1: successful single dispatch writes metadata and logs events."""

    @patch("autopilot_operator_dispatcher.operator_router")
    @patch("autopilot_operator_dispatcher.append_event_log")
    def test_dispatch_success(self, mock_log, mock_router, tmp_path):
        mock_router.dispatch.return_value = _make_dispatch_result()

        result = dispatch_line(
            line="x_social",
            schedules=_SCHEDULES,
            harness_root=str(tmp_path),
            event_log_path=tmp_path / "events.jsonl",
        )

        assert result["line"] == "x_social"
        assert result["state"] == "success"
        assert result["dual_run"] is False
        assert "metadata_path" in result

        # Metadata file was written
        meta_path = Path(result["metadata_path"])
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["mode"] == "single"
        assert meta["line"] == "x_social"
        assert meta["primary"]["success"] is True

        # Event log was called
        mock_log.assert_called_once()


# --- Case 4: dispatch failure ---


class TestDispatchLineFailure:
    """Case 3: dispatch failure transitions to FAILED state."""

    @patch("autopilot_operator_dispatcher.operator_router")
    @patch("autopilot_operator_dispatcher.append_event_log")
    def test_no_fallback_error_handled(self, mock_log, mock_router, tmp_path):
        mock_router.dispatch.side_effect = NoFallbackError("primary failed, no fallback")
        mock_router.NoFallbackError = NoFallbackError

        result = dispatch_line(
            line="x_social",
            schedules=_SCHEDULES,
            harness_root=str(tmp_path),
            event_log_path=tmp_path / "events.jsonl",
        )

        assert result["state"] == "failed"
        meta = json.loads(Path(result["metadata_path"]).read_text())
        assert meta["mode"] == "error"
        assert "primary failed" in meta["error"]


# --- Case 5: dual-run dispatch ---


class TestDispatchLineDualRun:
    """Case 4: github_trends dual-run dispatches with control."""

    @patch("autopilot_operator_dispatcher.operator_router")
    @patch("autopilot_operator_dispatcher.append_event_log")
    def test_dual_run_both_succeed(self, mock_log, mock_router, tmp_path):
        mock_router.dispatch_with_control.return_value = _make_control_result()

        result = dispatch_line(
            line="github_trends",
            schedules=_SCHEDULES,
            harness_root=str(tmp_path),
            event_log_path=tmp_path / "events.jsonl",
        )

        assert result["dual_run"] is True
        assert result["state"] == "success"
        meta = json.loads(Path(result["metadata_path"]).read_text())
        assert meta["mode"] == "dual_run"
        assert meta["both_succeeded"] is True
        assert "primary" in meta
        assert "control" in meta

    @patch("autopilot_operator_dispatcher.operator_router")
    @patch("autopilot_operator_dispatcher.append_event_log")
    def test_dual_run_partial(self, mock_log, mock_router, tmp_path):
        mock_router.dispatch_with_control.return_value = _make_control_result(
            primary_success=True, control_success=False,
        )

        result = dispatch_line(
            line="github_trends",
            schedules=_SCHEDULES,
            harness_root=str(tmp_path),
            event_log_path=tmp_path / "events.jsonl",
        )

        assert result["state"] == "partial"

    @patch("autopilot_operator_dispatcher.operator_router")
    @patch("autopilot_operator_dispatcher.append_event_log")
    def test_dual_run_both_fail(self, mock_log, mock_router, tmp_path):
        mock_router.dispatch_with_control.return_value = _make_control_result(
            primary_success=False, control_success=False,
        )

        result = dispatch_line(
            line="github_trends",
            schedules=_SCHEDULES,
            harness_root=str(tmp_path),
            event_log_path=tmp_path / "events.jsonl",
        )

        assert result["state"] == "failed"


# --- Case 6: tick orchestration ---


class TestTick:
    """Tick dispatches all due lines and returns summary."""

    @patch("autopilot_operator_dispatcher.operator_router")
    @patch("autopilot_operator_dispatcher.append_event_log")
    def test_tick_dispatches_due_lines(self, mock_log, mock_router, tmp_path):
        mock_router.dispatch.return_value = _make_dispatch_result()

        now = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
        result = tick(
            schedules=_SCHEDULES,
            now=now,
            harness_root=str(tmp_path),
            event_log_path=tmp_path / "events.jsonl",
        )

        assert result["ok"] is True
        assert result["due_count"] == 1
        assert "x_social" in result["due_lines"]
        assert len(result["dispatched"]) == 1
        assert result["dispatched"][0]["state"] == "success"

    @patch("autopilot_operator_dispatcher.operator_router")
    @patch("autopilot_operator_dispatcher.append_event_log")
    def test_tick_no_due_lines(self, mock_log, mock_router, tmp_path):
        now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        result = tick(
            schedules=_SCHEDULES,
            now=now,
            harness_root=str(tmp_path),
            event_log_path=tmp_path / "events.jsonl",
        )

        assert result["ok"] is True
        assert result["due_count"] == 0
        assert result["dispatched"] == []
        mock_router.dispatch.assert_not_called()


# --- Case 7: schedule loading errors ---


class TestScheduleLoadError:
    """ScheduleLoadError on missing or invalid file."""

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ScheduleLoadError, match="not found"):
            find_due_lines(schedules_path=tmp_path / "nope.json")

    def test_binding_not_found_raises(self, tmp_path):
        with pytest.raises(KeyError, match="no_such_line"):
            dispatch_line(
                line="no_such_line",
                schedules=_SCHEDULES,
                harness_root=str(tmp_path),
            )
