"""Unit tests for state_machine.py — normal + search_skip + failed + replay.

Covers ResearchStateMachine transitions, invalid transition rejection,
and replay_from_jsonl round-trip fidelity.
"""

import json
import tempfile
from pathlib import Path

import pytest

from harness.lib.research.state_machine import (
    DataPlaneState,
    InvalidTransition,
    ResearchStateMachine,
)


class TestNormalFlow:
    """Happy path: init -> searching -> drafting -> metering -> rendering -> finalized."""

    def test_full_normal_flow(self, tmp_path):
        jsonl = tmp_path / "usage.jsonl"
        sm = ResearchStateMachine(jsonl_path=jsonl)
        assert sm.state is DataPlaneState.INIT

        sm.transition(DataPlaneState.SEARCHING, stage="serper")
        assert sm.state is DataPlaneState.SEARCHING

        sm.transition(DataPlaneState.DRAFTING, stage="writer")
        assert sm.state is DataPlaneState.DRAFTING

        sm.transition(DataPlaneState.METERING, stage="chief_editor")
        assert sm.state is DataPlaneState.METERING

        sm.transition(DataPlaneState.RENDERING, stage="report_metrics")
        assert sm.state is DataPlaneState.RENDERING

        sm.transition(DataPlaneState.FINALIZED, stage="final")
        assert sm.state is DataPlaneState.FINALIZED

        lines = jsonl.read_text().strip().split("\n")
        assert len(lines) == 5
        assert json.loads(lines[-1])["to_state"] == "finalized"

    def test_history_records_all_transitions(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCHING)
        sm.transition(DataPlaneState.DRAFTING)
        assert len(sm.history()) == 2
        assert sm.history()[0].from_state == "init"
        assert sm.history()[1].to_state == "drafting"


class TestSearchSkipFlow:
    """search_skip branch: init -> search_skip -> rendering -> finalized."""

    def test_search_skip_from_init(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCH_SKIP, fallback_reason="serper_key_missing")
        assert sm.state is DataPlaneState.SEARCH_SKIP

        sm.transition(DataPlaneState.RENDERING, stage="report_metrics")
        sm.transition(DataPlaneState.FINALIZED)
        assert sm.state is DataPlaneState.FINALIZED

    def test_search_skip_from_searching(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCHING)
        sm.transition(DataPlaneState.SEARCH_SKIP, fallback_reason="serper_429")
        assert sm.state is DataPlaneState.SEARCH_SKIP

    def test_skip_records_fallback_reason(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCH_SKIP, fallback_reason="serper_quota")
        assert sm.history()[0].fallback_reason == "serper_quota"


class TestFailedTransitions:
    """Any active state can transition to FAILED."""

    def test_fail_from_searching(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCHING)
        sm.transition(DataPlaneState.FAILED, fallback_reason="crash")
        assert sm.state is DataPlaneState.FAILED

    def test_fail_from_metering(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCHING)
        sm.transition(DataPlaneState.DRAFTING)
        sm.transition(DataPlaneState.METERING)
        sm.transition(DataPlaneState.FAILED)
        assert sm.state is DataPlaneState.FAILED

    def test_terminal_states_reject_transition(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCH_SKIP)
        sm.transition(DataPlaneState.RENDERING)
        sm.transition(DataPlaneState.FINALIZED)
        with pytest.raises(InvalidTransition):
            sm.transition(DataPlaneState.INIT)


class TestInvalidTransitions:
    """Disallowed transitions raise InvalidTransition."""

    def test_init_to_drafting_invalid(self):
        sm = ResearchStateMachine()
        with pytest.raises(InvalidTransition, match="invalid transition"):
            sm.transition(DataPlaneState.DRAFTING)

    def test_finalized_to_any_invalid(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCH_SKIP)
        sm.transition(DataPlaneState.RENDERING)
        sm.transition(DataPlaneState.FINALIZED)
        with pytest.raises(InvalidTransition):
            sm.transition(DataPlaneState.RENDERING)

    def test_failed_to_any_invalid(self):
        sm = ResearchStateMachine()
        sm.transition(DataPlaneState.SEARCHING)
        sm.transition(DataPlaneState.FAILED)
        with pytest.raises(InvalidTransition):
            sm.transition(DataPlaneState.INIT)


class TestReplayFromJsonl:
    """replay_from_jsonl rebuilds state machine from log file."""

    def test_replay_full_flow(self, tmp_path):
        jsonl = tmp_path / "usage.jsonl"
        sm = ResearchStateMachine(jsonl_path=jsonl)
        sm.transition(DataPlaneState.SEARCHING, stage="serper")
        sm.transition(DataPlaneState.DRAFTING, stage="writer")
        sm.transition(DataPlaneState.METERING, stage="editor")
        sm.transition(DataPlaneState.RENDERING, stage="render")
        sm.transition(DataPlaneState.FINALIZED, stage="done")

        replayed = ResearchStateMachine.replay_from_jsonl(jsonl)
        assert replayed.state is DataPlaneState.FINALIZED
        assert len(replayed.history()) == 5

    def test_replay_nonexistent_file(self, tmp_path):
        replayed = ResearchStateMachine.replay_from_jsonl(tmp_path / "absent.jsonl")
        assert replayed.state is DataPlaneState.INIT
        assert len(replayed.history()) == 0

    def test_replay_preserves_extra(self, tmp_path):
        jsonl = tmp_path / "usage.jsonl"
        sm = ResearchStateMachine(jsonl_path=jsonl)
        sm.transition(DataPlaneState.SEARCHING, extra={"serper_query": "test"})
        sm.transition(DataPlaneState.DRAFTING)

        replayed = ResearchStateMachine.replay_from_jsonl(jsonl)
        assert replayed.history()[0].extra["serper_query"] == "test"
