"""Tests for task_graph_state_io — spec/state/closure three-face I/O (R1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(LIB_DIR))

import task_graph_state_io as sio


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(sio, "SPRINTS_DIR", tmp_path)
    return tmp_path


SAMPLE_LEGACY_GRAPH = {
    "sprint_id": "test-sprint-001",
    "required_gates": ["G1", "G2"],
    "nodes": [
        {"id": "N1", "goal": "Do A", "depends_on": [], "gate": "G1",
         "status": "passed", "updated_at": "2026-01-01T00:00:00Z",
         "assigned_to": "builder_main", "dispatch_id": "d-001"},
        {"id": "N2", "goal": "Do B", "depends_on": ["N1"], "gate": "G2",
         "status": "reviewing", "updated_at": "2026-01-02T00:00:00Z"},
        {"id": "N3", "goal": "Do C", "depends_on": ["N2"], "gate": "G2"},
    ],
    "node_results": {
        "N1": {"status": "passed", "updated_at": "2026-01-01T00:00:00Z"}
    },
    "gate_results": {
        "G1": {"status": "passed", "updated_at": "2026-01-01T00:00:00Z"}
    },
}


SAMPLE_CLOSED_GRAPH = {
    "sprint_id": "closed-sprint",
    "required_gates": ["G1"],
    "nodes": [
        {"id": "N1", "goal": "Done", "depends_on": [], "gate": "G1",
         "status": "passed", "updated_at": "2026-01-01T00:00:00Z"},
    ],
    "node_results": {
        "N1": {"status": "passed", "updated_at": "2026-01-01T00:00:00Z"}
    },
    "gate_results": {
        "G1": {"status": "passed", "updated_at": "2026-01-01T00:00:00Z"}
    },
}


# ── path resolution ──────────────────────────────────────────────────────────

def test_state_path(tmp_path):
    p = sio.state_path_for_sprint("my-sprint", tmp_path)
    assert p == tmp_path / "my-sprint.task_dag.state.json"


def test_closure_path(tmp_path):
    p = sio.closure_path_for_sprint("my-sprint", tmp_path)
    assert p == tmp_path / "my-sprint.task_dag.closure.json"


def test_spec_path(tmp_path):
    p = sio.spec_path_for_sprint("my-sprint", tmp_path)
    assert p == tmp_path / "my-sprint.task_graph.json"


# ── empty skeleton creators ──────────────────────────────────────────────────

def test_make_empty_state():
    state = sio.make_empty_state("s-001")
    assert state["schema_version"] == sio.SCHEMA_VERSION_STATE
    assert state["sprint_id"] == "s-001"
    assert state["node_results"] == {}
    assert state["gate_results"] == {}
    assert state["leases"] == {}
    assert state["dispatch_ids"] == {}
    assert len(state["events"]) == 1
    assert state["events"][0]["event"] == "state_initialized"


def test_make_empty_closure():
    cl = sio.make_empty_closure("s-001")
    assert cl["schema_version"] == sio.SCHEMA_VERSION_CLOSURE
    assert cl["sprint_id"] == "s-001"
    assert cl["all_nodes_passed"] is False
    assert cl["all_required_gates_passed"] is False
    assert cl["closed_at"] is None
    assert cl["tests"] == []


# ── state I/O ────────────────────────────────────────────────────────────────

def test_save_and_load_state(tmp_path):
    sid = "test-sprint-001"
    state = sio.make_empty_state(sid)
    state["node_results"]["N1"] = {"status": "passed"}
    path = sio.save_state(sid, state, tmp_path)
    assert path.is_file()

    loaded = sio.load_state(sid, tmp_path)
    assert loaded is not None
    assert loaded["node_results"]["N1"]["status"] == "passed"
    assert "updated_at" in loaded


def test_load_state_missing_returns_none(tmp_path):
    assert sio.load_state("nonexistent", tmp_path) is None


def test_atomic_write_no_tmp_leftover(tmp_path):
    sid = "test-sprint-001"
    sio.save_state(sid, sio.make_empty_state(sid), tmp_path)
    state_p = sio.state_path_for_sprint(sid, tmp_path)
    tmp_p = state_p.with_suffix(state_p.suffix + ".tmp")
    assert not tmp_p.exists()


# ── closure I/O ──────────────────────────────────────────────────────────────

def test_save_and_load_closure(tmp_path):
    sid = "test-sprint-001"
    cl = sio.make_empty_closure(sid)
    cl["all_nodes_passed"] = True
    path = sio.save_closure(sid, cl, tmp_path)
    assert path.is_file()

    loaded = sio.load_closure(sid, tmp_path)
    assert loaded is not None
    assert loaded["all_nodes_passed"] is True


def test_load_closure_missing_returns_none(tmp_path):
    assert sio.load_closure("nonexistent", tmp_path) is None


# ── legacy backfill: state ────────────────────────────────────────────────────

def test_backfill_state_from_legacy(tmp_path):
    state = sio.backfill_state_from_legacy(
        SAMPLE_LEGACY_GRAPH, sprints_dir=tmp_path
    )
    # N1 comes from node_results (passed)
    assert state["node_results"]["N1"]["status"] == "passed"
    # N2 comes from inline status (reviewing)
    assert state["node_results"]["N2"]["status"] == "reviewing"
    # N3 has no status → should NOT be in node_results (pending is skipped)
    assert "N3" not in state["node_results"]
    # dispatch_id extracted
    assert state["dispatch_ids"]["N1"] == "d-001"
    # assigned_to preserved
    assert state["node_results"]["N1"]["assigned_to"] == "builder_main"
    # gate_results extracted
    assert state["gate_results"]["G1"]["status"] == "passed"
    # backfill event recorded
    assert any(e["event"] == "legacy_backfill" for e in state["events"])
    # file written to disk
    assert sio.state_path_for_sprint("test-sprint-001", tmp_path).is_file()


def test_backfill_state_does_not_overwrite(tmp_path):
    sid = "test-sprint-001"
    # Pre-create state
    existing = sio.make_empty_state(sid)
    existing["node_results"]["N1"] = {"status": "in_progress"}
    sio.save_state(sid, existing, tmp_path)

    # Backfill should NOT overwrite
    result = sio.backfill_state_from_legacy(
        SAMPLE_LEGACY_GRAPH, sprints_dir=tmp_path
    )
    assert result["node_results"]["N1"]["status"] == "in_progress"


def test_backfill_state_force_overwrites(tmp_path):
    sid = "test-sprint-001"
    existing = sio.make_empty_state(sid)
    existing["node_results"]["N1"] = {"status": "in_progress"}
    sio.save_state(sid, existing, tmp_path)

    result = sio.backfill_state_from_legacy(
        SAMPLE_LEGACY_GRAPH, sprints_dir=tmp_path, force=True
    )
    assert result["node_results"]["N1"]["status"] == "passed"


def test_backfill_state_raises_on_missing_sprint_id(tmp_path):
    with pytest.raises(ValueError, match="sprint_id missing"):
        sio.backfill_state_from_legacy({"nodes": []}, sprints_dir=tmp_path)


# ── legacy backfill: closure ──────────────────────────────────────────────────

def test_backfill_closure_from_legacy_not_closed(tmp_path):
    cl = sio.backfill_closure_from_legacy(
        SAMPLE_LEGACY_GRAPH, sprints_dir=tmp_path
    )
    # Not all nodes passed (N2 is reviewing, N3 is pending)
    assert cl["all_nodes_passed"] is False
    # Not all gates passed (G2 missing)
    assert cl["all_required_gates_passed"] is False
    assert cl["closed_at"] is None


def test_backfill_closure_from_legacy_closed(tmp_path):
    cl = sio.backfill_closure_from_legacy(
        SAMPLE_CLOSED_GRAPH, sprints_dir=tmp_path
    )
    assert cl["all_nodes_passed"] is True
    assert cl["all_required_gates_passed"] is True
    assert cl["closed_at"] is not None


def test_backfill_closure_does_not_overwrite(tmp_path):
    sid = "closed-sprint"
    existing = sio.make_empty_closure(sid)
    existing["residual_risks"] = ["some risk"]
    sio.save_closure(sid, existing, tmp_path)

    result = sio.backfill_closure_from_legacy(
        SAMPLE_CLOSED_GRAPH, sprints_dir=tmp_path
    )
    assert result["residual_risks"] == ["some risk"]


def test_backfill_closure_force_overwrites(tmp_path):
    sid = "closed-sprint"
    existing = sio.make_empty_closure(sid)
    existing["residual_risks"] = ["some risk"]
    sio.save_closure(sid, existing, tmp_path)

    result = sio.backfill_closure_from_legacy(
        SAMPLE_CLOSED_GRAPH, sprints_dir=tmp_path, force=True
    )
    assert result["residual_risks"] == []


# ── load_three_face ──────────────────────────────────────────────────────────

def test_load_three_face_with_backfill(tmp_path):
    sid = "test-sprint-001"
    # Write spec (legacy task_graph.json)
    spec_p = tmp_path / f"{sid}.task_graph.json"
    spec_p.write_text(json.dumps(SAMPLE_LEGACY_GRAPH), encoding="utf-8")

    result = sio.load_three_face(sid, tmp_path, auto_backfill=True)
    assert result["sprint_id"] == sid
    assert result["spec"] is not None
    assert result["state"] is not None
    assert result["closure"] is not None
    assert "state_backfilled_from_legacy" in result["degraded"]
    assert "closure_backfilled_from_legacy" in result["degraded"]


def test_load_three_face_no_spec(tmp_path):
    result = sio.load_three_face("nonexistent", tmp_path)
    assert result["spec"] is None
    assert result["state"] is None
    assert "spec_missing" in result["degraded"]


def test_load_three_face_preexisting_state(tmp_path):
    sid = "test-sprint-001"
    spec_p = tmp_path / f"{sid}.task_graph.json"
    spec_p.write_text(json.dumps(SAMPLE_LEGACY_GRAPH), encoding="utf-8")
    # Pre-create state
    state = sio.make_empty_state(sid)
    state["node_results"]["N1"] = {"status": "in_progress"}
    sio.save_state(sid, state, tmp_path)

    result = sio.load_three_face(sid, tmp_path)
    # State should NOT be backfilled (already exists)
    assert "state_backfilled_from_legacy" not in result["degraded"]
    assert result["state"]["node_results"]["N1"]["status"] == "in_progress"


# ── mutation helpers ──────────────────────────────────────────────────────────

def test_record_event():
    state = sio.make_empty_state("s-001")
    initial_count = len(state["events"])
    sio.record_event(state, "test_event", "unit_test", "hello")
    assert len(state["events"]) == initial_count + 1
    assert state["events"][-1]["event"] == "test_event"
    assert state["events"][-1]["by"] == "unit_test"
    assert state["events"][-1]["note"] == "hello"
    assert state["event_cursor"] == len(state["events"])


def test_set_node_result():
    state = sio.make_empty_state("s-001")
    sio.set_node_result(state, "N1", "passed", note="looks good",
                        assigned_to="bob", dispatch_id="d-99")
    assert state["node_results"]["N1"]["status"] == "passed"
    assert state["node_results"]["N1"]["note"] == "looks good"
    assert state["node_results"]["N1"]["assigned_to"] == "bob"
    assert state["dispatch_ids"]["N1"] == "d-99"


def test_set_gate_result():
    state = sio.make_empty_state("s-001")
    sio.set_gate_result(state, "G1", "passed", node_id="N1")
    assert state["gate_results"]["G1"]["status"] == "passed"
    assert state["gate_results"]["G1"]["node"] == "N1"


# ── spec never written by state operations ────────────────────────────────────

def test_state_operations_do_not_touch_spec(tmp_path):
    sid = "test-sprint-001"
    spec_p = tmp_path / f"{sid}.task_graph.json"
    spec_data = dict(SAMPLE_LEGACY_GRAPH)
    spec_p.write_text(json.dumps(spec_data), encoding="utf-8")
    spec_mtime = spec_p.stat().st_mtime

    # Perform state operations
    state = sio.make_empty_state(sid)
    sio.set_node_result(state, "N1", "passed")
    sio.set_gate_result(state, "G1", "passed")
    sio.record_event(state, "test", "unit")
    sio.save_state(sid, state, tmp_path)

    # Spec should not be modified
    assert spec_p.stat().st_mtime == spec_mtime
    loaded_spec = json.loads(spec_p.read_text())
    assert loaded_spec == spec_data


# ── sprint_id extraction ──────────────────────────────────────────────────────

def test_sprint_id_from_graph_field():
    assert sio._sprint_id_from_graph({"sprint_id": "s-001"}) == "s-001"


def test_sprint_id_from_id_field():
    assert sio._sprint_id_from_graph({"id": "s-002"}) == "s-002"


def test_sprint_id_from_path():
    assert sio._sprint_id_from_graph(
        {}, "/foo/bar/my-sprint.task_graph.json"
    ) == "my-sprint"
