"""
Unit tests for operator_state_machine.py

Covers:
  1. State definitions — all 5 states exist and are correct
  2. Legal transitions — pending->running, running->success/partial/failed
  3. Illegal transitions — terminal states cannot transition, pending cannot skip
  4. Event log — JSON lines append + read round-trip
  5. State rebuild — rebuild_state reproduces correct state from event log
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from operator_state_machine import (
    EventLogError,
    IllegalTransitionError,
    OperatorRun,
    OperatorState,
    append_event_log,
    read_event_log,
    rebuild_state,
)


# --- Test 1: State definitions ---

class TestStateDefinitions:
    def test_five_states_exist(self):
        states = list(OperatorState)
        assert len(states) == 5

    def test_state_values(self):
        assert OperatorState.PENDING.value == "pending"
        assert OperatorState.RUNNING.value == "running"
        assert OperatorState.SUCCESS.value == "success"
        assert OperatorState.PARTIAL.value == "partial"
        assert OperatorState.FAILED.value == "failed"

    def test_states_are_string_enum(self):
        # str enum means they compare to strings directly
        assert OperatorState.PENDING == "pending"
        assert OperatorState.RUNNING == "running"

    def test_initial_state_is_pending(self):
        run = OperatorRun(run_id="r1", line="test_line")
        assert run.state == OperatorState.PENDING


# --- Test 2: Legal transitions ---

class TestLegalTransitions:
    def test_pending_to_running(self):
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        assert run.state == OperatorState.RUNNING

    def test_running_to_success(self):
        run = OperatorRun(run_id="r2", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.SUCCESS)
        assert run.state == OperatorState.SUCCESS

    def test_running_to_partial(self):
        run = OperatorRun(run_id="r3", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.PARTIAL)
        assert run.state == OperatorState.PARTIAL

    def test_running_to_failed(self):
        run = OperatorRun(run_id="r4", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.FAILED)
        assert run.state == OperatorState.FAILED

    def test_full_lifecycle_pending_running_success(self):
        run = OperatorRun(run_id="r5", line="github_trends")
        assert run.state == OperatorState.PENDING
        run.transition(OperatorState.RUNNING)
        assert run.state == OperatorState.RUNNING
        run.transition(OperatorState.SUCCESS)
        assert run.state == OperatorState.SUCCESS
        # 3 events: initial pending + running + success
        assert len(run.events) == 3

    def test_transition_with_metadata(self):
        run = OperatorRun(run_id="r6", line="test_line")
        run.transition(OperatorState.RUNNING, metadata={"reason": "manual"})
        events = run.events
        assert events[-1]["metadata"] == {"reason": "manual"}


# --- Test 3: Illegal transitions ---

class TestIllegalTransitions:
    def test_pending_to_success_raises(self):
        run = OperatorRun(run_id="r1", line="test_line")
        with pytest.raises(IllegalTransitionError, match="pending -> success"):
            run.transition(OperatorState.SUCCESS)

    def test_pending_to_partial_raises(self):
        run = OperatorRun(run_id="r1", line="test_line")
        with pytest.raises(IllegalTransitionError, match="pending -> partial"):
            run.transition(OperatorState.PARTIAL)

    def test_pending_to_failed_raises(self):
        run = OperatorRun(run_id="r1", line="test_line")
        with pytest.raises(IllegalTransitionError, match="pending -> failed"):
            run.transition(OperatorState.FAILED)

    def test_success_to_running_raises(self):
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.SUCCESS)
        with pytest.raises(IllegalTransitionError, match="success -> running"):
            run.transition(OperatorState.RUNNING)

    def test_failed_to_running_raises(self):
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.FAILED)
        with pytest.raises(IllegalTransitionError, match="failed -> running"):
            run.transition(OperatorState.RUNNING)

    def test_partial_is_terminal(self):
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.PARTIAL)
        with pytest.raises(IllegalTransitionError):
            run.transition(OperatorState.RUNNING)

    def test_running_to_pending_raises(self):
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        with pytest.raises(IllegalTransitionError, match="running -> pending"):
            run.transition(OperatorState.PENDING)


# --- Test 4: Event log append + read ---

class TestEventLog:
    def test_append_and_read_roundtrip(self, tmp_path):
        log_file = tmp_path / "events.jsonl"
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.SUCCESS)

        append_event_log(log_file, run.events)
        loaded = read_event_log(log_file)

        assert len(loaded) == 3
        assert loaded[0]["to_state"] == "pending"
        assert loaded[1]["to_state"] == "running"
        assert loaded[2]["to_state"] == "success"

    def test_append_multiple_runs(self, tmp_path):
        log_file = tmp_path / "events.jsonl"

        run1 = OperatorRun(run_id="r1", line="line_a")
        run1.transition(OperatorState.RUNNING)
        run1.transition(OperatorState.SUCCESS)
        append_event_log(log_file, run1.events)

        run2 = OperatorRun(run_id="r2", line="line_b")
        run2.transition(OperatorState.RUNNING)
        run2.transition(OperatorState.FAILED)
        append_event_log(log_file, run2.events)

        loaded = read_event_log(log_file)
        assert len(loaded) == 6  # 3 + 3

    def test_read_nonexistent_file(self, tmp_path):
        events = read_event_log(tmp_path / "no_such_file.jsonl")
        assert events == []

    def test_read_invalid_json_raises(self, tmp_path):
        log_file = tmp_path / "bad.jsonl"
        log_file.write_text('{"valid": true}\nnot json\n', encoding="utf-8")
        with pytest.raises(EventLogError, match="Invalid JSON on line 2"):
            read_event_log(log_file)

    def test_append_creates_parent_dirs(self, tmp_path):
        log_file = tmp_path / "sub" / "dir" / "events.jsonl"
        run = OperatorRun(run_id="r1", line="test_line")
        append_event_log(log_file, run.events)
        assert log_file.exists()

    def test_jsonl_format(self, tmp_path):
        """Each event is a single line of valid JSON."""
        log_file = tmp_path / "events.jsonl"
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        append_event_log(log_file, run.events)

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for raw_line in lines:
            parsed = json.loads(raw_line)
            assert "run_id" in parsed
            assert "to_state" in parsed


# --- Test 5: State rebuild from event log ---

class TestRebuildState:
    def test_rebuild_single_run(self, tmp_path):
        log_file = tmp_path / "events.jsonl"
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.SUCCESS)
        append_event_log(log_file, run.events)

        events = read_event_log(log_file)
        rebuilt = rebuild_state(events)

        assert "r1" in rebuilt
        assert rebuilt["r1"].state == OperatorState.SUCCESS
        assert rebuilt["r1"].line == "test_line"

    def test_rebuild_multiple_runs(self, tmp_path):
        log_file = tmp_path / "events.jsonl"

        run1 = OperatorRun(run_id="r1", line="line_a")
        run1.transition(OperatorState.RUNNING)
        run1.transition(OperatorState.SUCCESS)

        run2 = OperatorRun(run_id="r2", line="line_b")
        run2.transition(OperatorState.RUNNING)
        run2.transition(OperatorState.FAILED)

        append_event_log(log_file, run1.events + run2.events)
        events = read_event_log(log_file)
        rebuilt = rebuild_state(events)

        assert rebuilt["r1"].state == OperatorState.SUCCESS
        assert rebuilt["r2"].state == OperatorState.FAILED

    def test_rebuild_filter_by_run_id(self, tmp_path):
        log_file = tmp_path / "events.jsonl"

        run1 = OperatorRun(run_id="r1", line="line_a")
        run1.transition(OperatorState.RUNNING)
        run1.transition(OperatorState.SUCCESS)

        run2 = OperatorRun(run_id="r2", line="line_b")
        run2.transition(OperatorState.RUNNING)
        run2.transition(OperatorState.PARTIAL)

        append_event_log(log_file, run1.events + run2.events)
        events = read_event_log(log_file)
        rebuilt = rebuild_state(events, run_id="r2")

        assert "r1" not in rebuilt
        assert rebuilt["r2"].state == OperatorState.PARTIAL

    def test_rebuild_detects_illegal_transition(self):
        # Manually craft events with an illegal transition
        events = [
            {"run_id": "r1", "line": "test", "from_state": None, "to_state": "pending"},
            {"run_id": "r1", "line": "test", "from_state": "pending", "to_state": "success"},
        ]
        with pytest.raises(IllegalTransitionError, match="pending -> success"):
            rebuild_state(events)

    def test_rebuild_preserves_event_count(self, tmp_path):
        log_file = tmp_path / "events.jsonl"
        run = OperatorRun(run_id="r1", line="test_line")
        run.transition(OperatorState.RUNNING)
        run.transition(OperatorState.PARTIAL)
        append_event_log(log_file, run.events)

        events = read_event_log(log_file)
        rebuilt = rebuild_state(events)

        assert len(rebuilt["r1"].events) == 3
