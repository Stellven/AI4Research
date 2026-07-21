"""Tests for projections.py — event → status projection.

S03 N8 acceptance:
  1. projections.py contains build_sprint_status(sprint_id) -> dict
  2. replay_projection(events) -> status idempotent (N replays same result)
  3. Incremental rebuild support (based on last_event_id)
  4. New ledger and old status.json dual-write consistency test PASS
  5. pytest tests/test_projections.py all PASS
  6. py_compile projections.py passes
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pytest

from harness.lib.event_ledger import EventLedger
from harness.lib.projections import (
    DivergentError,
    build_sprint_status,
    dual_write_status_json,
    incremental_rebuild,
    replay_projection,
)

LIB_DIR = Path(__file__).resolve().parent.parent / "lib"


def _make_event(
    event_type="state_transition",
    sprint_id="sprint-test",
    actor="coordinator",
    payload=None,
    **kw,
):
    base = {
        "event_type": event_type,
        "sprint_id": sprint_id,
        "actor": actor,
        "payload": payload or {},
    }
    base.update(kw)
    return base


def _append_transition(ledger, to_state, sprint_id="sprint-test", **kw):
    return ledger.append(
        _make_event(
            payload={"to": to_state, "round": 1},
            sprint_id=sprint_id,
            **kw,
        )
    )


@pytest.fixture
def tmp_ledger(tmp_path):
    return EventLedger(base_dir=str(tmp_path / "run"))


@pytest.fixture
def status_json_path(tmp_path):
    return str(tmp_path / "sprint-test.status.json")


# ---------------------------------------------------------------------------
# AC1: build_sprint_status(sprint_id) -> dict
# ---------------------------------------------------------------------------


class TestBuildSprintStatus:
    def test_returns_dict_with_status(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        result = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "planning"

    def test_returns_initial_state_when_no_events(self, tmp_ledger):
        result = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert result["status"] == "drafting"

    def test_full_lifecycle(self, tmp_ledger):
        for state in ("planning", "ready", "dispatching", "running", "reviewing", "passed"):
            _append_transition(tmp_ledger, state)
        result = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert result["status"] == "passed"
        assert result["event_count"] == 6

    def test_includes_legacy_fields(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        result = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert "sprint_id" in result
        assert "id" in result
        assert "projected_at" in result
        assert result["sprint_id"] == "sprint-test"
        assert result["id"] == "sprint-test"

    def test_tracks_node_statuses(self, tmp_ledger):
        tmp_ledger.append(
            _make_event(node_id="N1", payload={"to": "running"})
        )
        tmp_ledger.append(
            _make_event(node_id="N2", payload={"to": "passed"})
        )
        result = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert "node_statuses" in result
        assert result["node_statuses"]["N1"] == "running"
        assert result["node_statuses"]["N2"] == "passed"

    def test_includes_state_hash(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        result = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert "state_hash" in result
        assert len(result["state_hash"]) == 16

    def test_filters_by_sprint_id(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning", sprint_id="sprint-A")
        _append_transition(tmp_ledger, "running", sprint_id="sprint-B")
        result = build_sprint_status("sprint-A", ledger=tmp_ledger)
        assert result["status"] == "planning"
        assert result["event_count"] == 1


# ---------------------------------------------------------------------------
# AC2: replay_projection idempotent (N replays same result)
# ---------------------------------------------------------------------------


class TestReplayIdempotency:
    def test_replay_n_times_same_result(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        _append_transition(tmp_ledger, "running")
        events = tmp_ledger.replay("sprint-test")

        r1 = replay_projection(events)
        r2 = replay_projection(events)
        r3 = replay_projection(events)

        assert r1 == r2 == r3

    def test_replay_with_duplicate_event_ids_idempotent(self):
        events = [
            {"event_id": "e1", "event_type": "state_transition",
             "payload": {"to": "planning"}, "created_at": "2026-01-01T00:00:00Z"},
            {"event_id": "e1", "event_type": "state_transition",
             "payload": {"to": "running"}, "created_at": "2026-01-01T00:01:00Z"},
            {"event_id": "e2", "event_type": "state_transition",
             "payload": {"to": "passed"}, "created_at": "2026-01-01T00:02:00Z"},
        ]
        result = replay_projection(events)
        assert result["status"] == "passed"
        assert result["event_count"] == 2

    def test_replay_is_pure_function(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        events = tmp_ledger.replay("sprint-test")
        r1 = replay_projection(events)
        r2 = replay_projection(events)
        assert r1["state_hash"] == r2["state_hash"]

    def test_state_hash_deterministic(self):
        events = [
            {"event_id": "a", "event_type": "state_transition",
             "payload": {"to": "running"}, "created_at": "2026-01-01T00:00:00Z"},
        ]
        r1 = replay_projection(events)
        r2 = replay_projection(events)
        assert r1["state_hash"] == r2["state_hash"]

    def test_no_side_effects_on_input(self):
        events = [
            {"event_id": "x", "event_type": "state_transition",
             "payload": {"to": "planning"}, "created_at": "2026-01-01T00:00:00Z"},
        ]
        orig_len = len(events)
        replay_projection(events)
        assert len(events) == orig_len


# ---------------------------------------------------------------------------
# AC3: incremental rebuild (based on last_event_id)
# ---------------------------------------------------------------------------


class TestIncrementalRebuild:
    def test_incremental_with_last_event_id(self, tmp_ledger):
        e1 = _append_transition(tmp_ledger, "planning")
        _append_transition(tmp_ledger, "running")

        full = build_sprint_status("sprint-test", ledger=tmp_ledger)
        incremental = build_sprint_status(
            "sprint-test", ledger=tmp_ledger, last_event_id=e1
        )
        assert incremental["status"] == "running"
        assert incremental["event_count"] == 1

    def test_incremental_no_new_events_returns_cached(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        cached = build_sprint_status("sprint-test", ledger=tmp_ledger)

        rebuilt = incremental_rebuild(
            "sprint-test", cached, ledger=tmp_ledger
        )
        assert rebuilt["status"] == cached["status"]
        assert rebuilt["state_hash"] == cached["state_hash"]

    def test_incremental_with_new_events_rebuilds(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        cached = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert cached["status"] == "planning"

        _append_transition(tmp_ledger, "running")
        rebuilt = incremental_rebuild(
            "sprint-test", cached, ledger=tmp_ledger
        )
        assert rebuilt["status"] == "running"

    def test_incremental_no_last_event_id_full_rebuild(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        cached = {"status": "drafting", "event_count": 0}
        result = incremental_rebuild(
            "sprint-test", cached, ledger=tmp_ledger
        )
        assert result["status"] == "planning"

    def test_incremental_matches_full_replay(self, tmp_ledger):
        _append_transition(tmp_ledger, "planning")
        _append_transition(tmp_ledger, "running")
        cached = build_sprint_status("sprint-test", ledger=tmp_ledger)

        _append_transition(tmp_ledger, "reviewing")
        _append_transition(tmp_ledger, "passed")

        rebuilt = incremental_rebuild(
            "sprint-test", cached, ledger=tmp_ledger
        )
        full = build_sprint_status("sprint-test", ledger=tmp_ledger)
        assert rebuilt["status"] == full["status"]
        assert rebuilt["state_hash"] == full["state_hash"]
        assert rebuilt["event_count"] == full["event_count"]


# ---------------------------------------------------------------------------
# AC4: new ledger and old status.json dual-write consistency
# ---------------------------------------------------------------------------


class TestDualWriteConsistency:
    def test_dual_write_creates_status_json(self, tmp_ledger, status_json_path):
        _append_transition(tmp_ledger, "running")
        projection = build_sprint_status("sprint-test", ledger=tmp_ledger)
        dual_write_status_json(projection, status_json_path)

        assert os.path.exists(status_json_path)
        with open(status_json_path) as f:
            disk = json.load(f)
        assert disk["status"] == "running"
        assert disk["sprint_id"] == "sprint-test"
        assert disk["round"] == projection["round"]
        assert disk["event_count"] == projection["event_count"]

    def test_dual_write_preserves_legacy_fields(self, tmp_ledger, status_json_path):
        legacy = {
            "id": "sprint-test",
            "title": "Test Sprint",
            "priority": "P1",
            "lane": "core",
            "custom_field": "preserved",
        }
        with open(status_json_path, "w") as f:
            json.dump(legacy, f)

        _append_transition(tmp_ledger, "passed")
        projection = build_sprint_status("sprint-test", ledger=tmp_ledger)
        dual_write_status_json(projection, status_json_path)

        with open(status_json_path) as f:
            disk = json.load(f)
        assert disk["title"] == "Test Sprint"
        assert disk["priority"] == "P1"
        assert disk["custom_field"] == "preserved"
        assert disk["status"] == "passed"

    def test_dual_write_never_removes_fields(self, tmp_ledger, status_json_path):
        legacy = {
            "id": "sprint-test",
            "handoff_to": "done",
            "created_at": "2026-01-01T00:00:00Z",
        }
        with open(status_json_path, "w") as f:
            json.dump(legacy, f)

        _append_transition(tmp_ledger, "planning")
        projection = build_sprint_status("sprint-test", ledger=tmp_ledger)
        dual_write_status_json(projection, status_json_path)

        with open(status_json_path) as f:
            disk = json.load(f)
        assert "handoff_to" in disk
        assert disk["handoff_to"] == "done"
        assert disk["created_at"] == "2026-01-01T00:00:00Z"

    def test_projection_matches_legacy_status_json(self, tmp_ledger, status_json_path):
        for state in ("planning", "ready", "running", "reviewing", "passed"):
            _append_transition(tmp_ledger, state)

        projection = build_sprint_status("sprint-test", ledger=tmp_ledger)
        dual_write_status_json(projection, status_json_path)

        with open(status_json_path) as f:
            disk = json.load(f)

        assert disk["status"] == projection["status"]
        assert disk["round"] == projection["round"]
        assert disk["event_count"] == projection["event_count"]
        assert disk["state_hash"] == projection["state_hash"]
        assert disk["node_statuses"] == projection["node_statuses"]

    def test_dual_write_atomic(self, tmp_ledger, status_json_path):
        _append_transition(tmp_ledger, "running")
        projection = build_sprint_status("sprint-test", ledger=tmp_ledger)
        dual_write_status_json(projection, status_json_path)
        assert not os.path.exists(status_json_path + ".tmp")


# ---------------------------------------------------------------------------
# Monotonic terminal state enforcement
# ---------------------------------------------------------------------------


class TestMonotonicTerminal:
    def test_terminal_cannot_be_reversed(self):
        events = [
            {"event_id": "e1", "event_type": "state_transition",
             "payload": {"to": "passed"}, "created_at": "2026-01-01T00:00:00Z"},
            {"event_id": "e2", "event_type": "state_transition",
             "payload": {"to": "running"}, "created_at": "2026-01-01T00:01:00Z"},
        ]
        with pytest.raises(DivergentError, match="terminal"):
            replay_projection(events)

    def test_failed_terminal_cannot_transition(self):
        events = [
            {"event_id": "e1", "event_type": "state_transition",
             "payload": {"to": "failed"}, "created_at": "2026-01-01T00:00:00Z"},
            {"event_id": "e2", "event_type": "state_transition",
             "payload": {"to": "running"}, "created_at": "2026-01-01T00:01:00Z"},
        ]
        with pytest.raises(DivergentError, match="terminal"):
            replay_projection(events)

    def test_same_terminal_state_allowed(self):
        events = [
            {"event_id": "e1", "event_type": "state_transition",
             "payload": {"to": "passed"}, "created_at": "2026-01-01T00:00:00Z"},
            {"event_id": "e2", "event_type": "state_transition",
             "payload": {"to": "passed"}, "created_at": "2026-01-01T00:01:00Z"},
        ]
        result = replay_projection(events)
        assert result["status"] == "passed"


# ---------------------------------------------------------------------------
# AC6: py_compile
# ---------------------------------------------------------------------------


class TestCompile:
    def test_py_compile_projections(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(LIB_DIR / "projections.py")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
