"""Tests for workflow_guard with triface (spec/state/closure) support."""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(LIB_DIR))

import task_graph_io as tgio
import workflow_guard as wg


SAMPLE_SPEC = {
    "sprint_id": "wg-test-sprint",
    "required_gates": ["G1"],
    "nodes": [
        {"id": "N1", "goal": "Implement thing", "depends_on": [], "gate": "G1"},
    ],
}


@pytest.fixture(autouse=True)
def patch_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(tgio, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(wg, "SPRINTS_DIR", tmp_path)
    return tmp_path


def _write_prd(tmp_path: Path, sid: str) -> None:
    (tmp_path / f"{sid}.prd.md").write_text("# PRD\nSome content\n")


def _write_status(tmp_path: Path, sid: str, *, status: str = "active", phase: str = "planning_complete",
                  handoff_to: str = "builder_main", target_role: str = "builder_main") -> None:
    (tmp_path / f"{sid}.status.json").write_text(json.dumps({
        "id": sid, "sprint_id": sid, "status": status, "phase": phase,
        "handoff_to": handoff_to, "target_role": target_role,
    }))


def _write_design(tmp_path: Path, sid: str) -> None:
    (tmp_path / f"{sid}.design.md").write_text("# Design\n")


def _write_plan(tmp_path: Path, sid: str) -> None:
    (tmp_path / f"{sid}.plan.md").write_text("# Plan\n")


def _write_legacy_graph(tmp_path: Path, sid: str, nodes_status: str = "pending") -> None:
    graph = {
        "sprint_id": sid,
        "required_gates": ["G1"],
        "nodes": [{"id": "N1", "goal": "Do A", "depends_on": [], "status": nodes_status, "gate": "G1"}],
        "node_results": {"N1": {"status": nodes_status}},
        "gate_results": {},
    }
    (tmp_path / f"{sid}.task_graph.json").write_text(json.dumps(graph))


def test_route_builder_via_spec(tmp_path):
    """workflow_guard accepts spec-validated graph for builder route."""
    sid = "wg-test-sprint"
    _write_prd(tmp_path, sid)
    _write_design(tmp_path, sid)
    _write_plan(tmp_path, sid)
    _write_status(tmp_path, sid)
    tgio.save_spec(sid, dict(SAMPLE_SPEC))

    result = wg.route(sid)
    assert result["route_role"] == "builder_main"
    assert result["ok"] is True


def test_route_done_via_closure(tmp_path):
    """workflow_guard detects parent-ready via closure.json."""
    sid = "wg-test-sprint"
    _write_prd(tmp_path, sid)
    _write_design(tmp_path, sid)
    _write_plan(tmp_path, sid)
    _write_status(tmp_path, sid, status="active")
    _write_legacy_graph(tmp_path, sid, "passed")
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    tgio.save_closure(sid, {"all_nodes_passed": True, "all_required_gates_passed": True})

    result = wg.route(sid)
    assert result["route_role"] == "none"
    assert result["stage"] == "done"


def test_route_fallback_to_legacy_when_no_spec(tmp_path):
    """workflow_guard falls back to legacy task_graph.json when spec missing."""
    sid = "wg-test-sprint"
    _write_prd(tmp_path, sid)
    _write_design(tmp_path, sid)
    _write_plan(tmp_path, sid)
    _write_status(tmp_path, sid)
    _write_legacy_graph(tmp_path, sid)  # no spec file

    result = wg.route(sid)
    assert result["route_role"] == "builder_main"


def test_triface_graph_valid_spec_ok(tmp_path):
    sid = "wg-test-sprint"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    ok, reason = wg._triface_graph_valid(sid)
    assert ok is True


def test_triface_graph_valid_spec_missing(tmp_path):
    ok, reason = wg._triface_graph_valid("no-sprint")
    assert ok is None  # type: ignore[comparison-overlap]
    assert reason == "spec_missing"


def test_triface_parent_ready_via_closure(tmp_path):
    sid = "wg-test-sprint"
    tgio.save_closure(sid, {"all_nodes_passed": True, "all_required_gates_passed": True})
    assert wg._triface_parent_ready(sid) is True


def test_triface_parent_ready_false(tmp_path):
    sid = "wg-test-sprint"
    tgio.save_spec(sid, dict(SAMPLE_SPEC))
    # No state yet — N1 is open
    assert wg._triface_parent_ready(sid) is False
