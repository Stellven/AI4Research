"""Tests for task_graph_io — three-face spec/state/closure IO layer."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest

# Point to real lib
LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(LIB_DIR))

import task_graph_io as tgio


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_sprints_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tgio, "SPRINTS_DIR", tmp_path)
    return tmp_path


SAMPLE_SPEC = {
    "sprint_id": "test-sprint-001",
    "required_gates": ["G1", "G2"],
    "nodes": [
        {"id": "N1", "goal": "Do thing A", "depends_on": [], "gate": "G1"},
        {"id": "N2", "goal": "Do thing B", "depends_on": ["N1"], "gate": "G2"},
    ],
}

SAMPLE_LEGACY_GRAPH = {
    "sprint_id": "test-sprint-001",
    "required_gates": ["G1"],
    "node_results": {"N1": {"status": "passed", "updated_at": "2026-01-01T00:00:00Z"}},
    "gate_results": {"G1": {"status": "passed", "updated_at": "2026-01-01T00:00:00Z"}},
    "nodes": [
        {"id": "N1", "goal": "Do thing A", "depends_on": [], "status": "passed", "gate": "G1"},
    ],
}


# ── spec face tests ───────────────────────────────────────────────────────────

def test_save_and_load_spec(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    loaded = tgio.load_spec(sid)
    assert loaded["sprint_id"] == sid
    assert len(loaded["nodes"]) == 2


def test_spec_valid_ok(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    ok, reason = tgio.spec_valid(sid)
    assert ok is True
    assert reason == "ok"


def test_spec_valid_missing(tmp_path):
    ok, reason = tgio.spec_valid("nonexistent-sprint")
    assert ok is False
    assert reason == "missing"


def test_spec_valid_duplicate_node(tmp_path):
    sid = "dup-sprint"
    bad_spec = {
        "sprint_id": sid,
        "nodes": [
            {"id": "N1", "goal": "A", "depends_on": []},
            {"id": "N1", "goal": "B", "depends_on": []},
        ],
    }
    tgio.save_spec(sid, bad_spec)
    ok, reason = tgio.spec_valid(sid)
    assert ok is False
    assert "duplicate" in reason


def test_spec_valid_missing_goal(tmp_path):
    sid = "no-goal-sprint"
    bad_spec = {"sprint_id": sid, "nodes": [{"id": "N1", "depends_on": []}]}
    tgio.save_spec(sid, bad_spec)
    ok, reason = tgio.spec_valid(sid)
    assert ok is False
    assert "missing_goal" in reason


# ── state face tests ──────────────────────────────────────────────────────────

def test_save_and_load_state(tmp_path):
    sid = "test-sprint-001"
    state = {"node_results": {"N1": {"status": "passed"}}, "gate_results": {}}
    tgio.save_state(sid, state)
    loaded = tgio.load_state(sid)
    assert loaded["node_results"]["N1"]["status"] == "passed"
    assert "updated_at" in loaded


def test_load_state_missing_returns_empty(tmp_path):
    assert tgio.load_state("nope") == {}


def test_set_node_result_in_state(tmp_path):
    sid = "test-sprint-001"
    tgio.set_node_result_in_state(sid, "N1", {"status": "passed"})
    state = tgio.load_state(sid)
    assert state["node_results"]["N1"]["status"] == "passed"


def test_set_gate_result_in_state(tmp_path):
    sid = "test-sprint-001"
    tgio.set_gate_result_in_state(sid, "G1", {"status": "passed"})
    state = tgio.load_state(sid)
    assert state["gate_results"]["G1"]["status"] == "passed"


def test_patch_state(tmp_path):
    sid = "test-sprint-001"
    tgio.save_state(sid, {"node_results": {}})
    tgio.patch_state(sid, {"event_cursor": 5})
    assert tgio.load_state(sid)["event_cursor"] == 5


# ── closure face tests ────────────────────────────────────────────────────────

def test_save_and_load_closure(tmp_path):
    sid = "test-sprint-001"
    cl = {
        "all_nodes_passed": True,
        "all_required_gates_passed": True,
        "tests": ["pytest -x"],
        "residual_risks": [],
    }
    tgio.save_closure(sid, cl)
    loaded = tgio.load_closure(sid)
    assert loaded["all_nodes_passed"] is True
    assert "closed_at" in loaded


def test_closure_complete_true(tmp_path):
    sid = "test-sprint-001"
    tgio.save_closure(sid, {"all_nodes_passed": True, "all_required_gates_passed": True})
    assert tgio.closure_complete(sid) is True


def test_closure_complete_false(tmp_path):
    sid = "test-sprint-001"
    tgio.save_closure(sid, {"all_nodes_passed": False, "all_required_gates_passed": True})
    assert tgio.closure_complete(sid) is False


def test_closure_complete_missing(tmp_path):
    assert tgio.closure_complete("nope") is False


# ── legacy backfill tests ─────────────────────────────────────────────────────

def test_backfill_state_from_legacy(tmp_path):
    sid = "test-sprint-001"
    state = tgio.backfill_state_from_legacy(sid, SAMPLE_LEGACY_GRAPH)
    assert state["node_results"]["N1"]["status"] == "passed"
    assert state["backfilled_from_legacy"] is True
    # Verify it was written
    assert tgio.state_path(sid).is_file()


def test_backfill_state_does_not_overwrite(tmp_path):
    sid = "test-sprint-001"
    tgio.save_state(sid, {"node_results": {"N1": {"status": "in_progress"}}})
    tgio.backfill_state_from_legacy(sid, SAMPLE_LEGACY_GRAPH)
    # Should NOT overwrite
    assert tgio.load_state(sid)["node_results"]["N1"]["status"] == "in_progress"


def test_backfill_spec_from_legacy(tmp_path):
    sid = "test-sprint-001"
    spec = tgio.backfill_spec_from_legacy(sid, SAMPLE_LEGACY_GRAPH)
    assert "node_results" not in spec
    assert spec["nodes"][0]["id"] == "N1"
    # Runtime fields stripped from nodes
    assert "status" not in spec["nodes"][0]


def test_backfill_spec_does_not_overwrite(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, {"sprint_id": sid, "nodes": [{"id": "X", "goal": "existing", "depends_on": []}]})
    tgio.backfill_spec_from_legacy(sid, SAMPLE_LEGACY_GRAPH)
    assert tgio.load_spec(sid)["nodes"][0]["id"] == "X"


# ── mirror compiler tests ─────────────────────────────────────────────────────

def test_compile_mirror_merges_spec_and_state(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    tgio.set_node_result_in_state(sid, "N1", {"status": "passed"})
    mirror = tgio.compile_mirror(sid)
    n1 = next(n for n in mirror["nodes"] if n["id"] == "N1")
    assert n1["status"] == "passed"
    n2 = next(n for n in mirror["nodes"] if n["id"] == "N2")
    assert n2["status"] == "pending"
    assert mirror["_mirror_source"] == "spec+state"


def test_compile_mirror_empty_when_no_spec(tmp_path):
    assert tgio.compile_mirror("no-such-sprint") == {}


def test_write_mirror_creates_file(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    path = tgio.write_mirror(sid)
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["sprint_id"] == sid


# ── triface parent ready tests ────────────────────────────────────────────────

def test_triface_parent_ready_via_closure(tmp_path):
    sid = "test-sprint-001"
    tgio.save_closure(sid, {"all_nodes_passed": True, "all_required_gates_passed": True})
    result = tgio.triface_parent_ready(sid)
    assert result["ready"] is True
    assert result["source"] == "closure"


def test_triface_parent_ready_via_state(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    # Both nodes passed, both gates passed
    tgio.set_node_result_in_state(sid, "N1", {"status": "passed"})
    tgio.set_node_result_in_state(sid, "N2", {"status": "passed"})
    tgio.set_gate_result_in_state(sid, "G1", {"status": "passed"})
    tgio.set_gate_result_in_state(sid, "G2", {"status": "passed"})
    result = tgio.triface_parent_ready(sid)
    assert result["ready"] is True
    assert result["source"] == "spec+state"


def test_triface_parent_ready_false_open_node(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    tgio.set_node_result_in_state(sid, "N1", {"status": "passed"})
    # N2 still pending
    result = tgio.triface_parent_ready(sid)
    assert result["ready"] is False
    assert "N2" in result["open_nodes"]


def test_triface_parent_ready_no_spec(tmp_path):
    result = tgio.triface_parent_ready("ghost-sprint")
    assert result["ready"] is False


# ── atomic write safety test ──────────────────────────────────────────────────

def test_atomic_write_no_tmp_leftover(tmp_path):
    sid = "test-sprint-001"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    tmp = tgio.spec_path(sid).with_suffix(".json.tmp")
    assert not tmp.exists()
