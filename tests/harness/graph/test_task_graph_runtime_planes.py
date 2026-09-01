#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HARNESS_LIB = (Path(__file__).resolve().parents[3] / 'harness') / "lib"
sys.path.insert(0, str(HARNESS_LIB))
GRAPH_SCHEDULER_PATH = HARNESS_LIB / "graph_scheduler.py"


def _load_local_graph_scheduler():
    spec = importlib.util.spec_from_file_location("test_graph_scheduler_local", GRAPH_SCHEDULER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_load_graph_prefers_state_plane_and_save_graph_projects_closure(tmp_path, monkeypatch):
    gs = _load_local_graph_scheduler()

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-runtime-planes"
    graph_path = sprints / f"{sid}.task_graph.json"
    state_path = sprints / f"{sid}.task_dag.state.json"
    closure_path = sprints / f"{sid}.closure.json"

    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "required_gates": ["G1"],
                "nodes": [
                    {"id": "N1", "goal": "Implement", "depends_on": [], "gate": "G1", "status": "pending"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    state_path.write_text(
        json.dumps(
            {
                "schema_version": "solar.task_graph_state.v1",
                "sprint_id": sid,
                "graph_ref": f"{sid}.task_graph.json",
                "node_results": {"N1": {"status": "passed", "updated_at": "2026-05-31T12:00:00Z"}},
                "gate_results": {"G1": {"status": "passed", "node": "N1"}},
                "leases": {},
                "dispatch_ids": {},
                "events": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    graph = gs.load_graph(graph_path)
    assert gs.node_status(graph, "N1") == "passed"
    assert graph["nodes"][0]["status"] == "passed"

    gs.set_node_status(graph, "N1", "reviewing")
    gs.save_graph(graph_path, graph)

    saved_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    saved_state = json.loads(state_path.read_text(encoding="utf-8"))
    saved_closure = json.loads(closure_path.read_text(encoding="utf-8"))

    assert "node_results" not in saved_graph
    assert "gate_results" not in saved_graph
    assert saved_state["node_results"]["N1"]["status"] == "reviewing"
    assert saved_closure["status"] == "pending"


def test_save_graph_keeps_node_runtime_fields_out_of_spec_plane(tmp_path, monkeypatch):
    gs = _load_local_graph_scheduler()

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-runtime-spec-clean"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": "N1",
                "goal": "Implement",
                "depends_on": [],
                "status": "assigned",
                "assigned_to": "pane-1",
                "dispatch_id": "dispatch-1",
                "closeout_receipt": {"schema": "solar.node_closeout.v1", "verdict": "passed"},
                "eval_json": "sprint-runtime-spec-clean.N1-eval.json",
                "updated_at": "2026-05-31T12:00:00Z",
            },
        ],
        "node_results": {
            "N1": {
                "status": "assigned",
                "assigned_to": "pane-1",
                "dispatch_id": "dispatch-1",
                "closeout_receipt": {"schema": "solar.node_closeout.v1", "verdict": "passed"},
                "eval_json": "sprint-runtime-spec-clean.N1-eval.json",
                "updated_at": "2026-05-31T12:00:00Z",
            }
        },
    }

    gs.save_graph(graph_path, graph)

    saved_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    saved_state = json.loads((sprints / f"{sid}.task_dag.state.json").read_text(encoding="utf-8"))

    node = saved_graph["nodes"][0]
    assert "status" not in node
    assert "assigned_to" not in node
    assert "dispatch_id" not in node
    assert "closeout_receipt" not in node
    assert "eval_json" not in node
    assert saved_state["node_results"]["N1"]["status"] == "assigned"
    assert saved_state["dispatch_ids"]["N1"] == "dispatch-1"
    loaded = gs.load_graph(graph_path)
    assert gs.node_status(loaded, "N1") == "assigned"
    assert loaded["nodes"][0]["closeout_receipt"] == {
        "schema": "solar.node_closeout.v1",
        "verdict": "passed",
    }
    assert loaded["nodes"][0]["eval_json"] == "sprint-runtime-spec-clean.N1-eval.json"


def test_load_graph_rehydrates_closeout_receipt_from_state_plane(tmp_path, monkeypatch):
    gs = _load_local_graph_scheduler()

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-runtime-closeout-receipt"
    graph_path = sprints / f"{sid}.task_graph.json"
    receipt = {
        "schema": "solar.node_closeout.v1",
        "sid": sid,
        "node_id": "N1",
        "verdict": "passed",
        "manifest": {"content_digest": "a" * 64},
        "publication": {"published_digest": "b" * 64},
    }
    graph = {
        "sprint_id": sid,
        "nodes": [{"id": "N1", "goal": "Publish", "depends_on": []}],
        "node_results": {
            "N1": {
                "status": "passed",
                "updated_at": "2026-05-31T12:00:00Z",
                "closeout_receipt": receipt,
            }
        },
    }

    gs.save_graph(graph_path, graph)

    saved_spec = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "closeout_receipt" not in saved_spec["nodes"][0]

    loaded = gs.load_graph(graph_path)
    assert loaded["nodes"][0]["closeout_receipt"] == receipt
    assert loaded["node_results"]["N1"]["closeout_receipt"] == receipt


def test_save_graph_marks_closure_closed_when_parent_ready(tmp_path, monkeypatch):
    gs = _load_local_graph_scheduler()

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-runtime-closure"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph = {
        "sprint_id": sid,
        "required_gates": ["G1"],
        "nodes": [
            {"id": "N1", "goal": "Implement", "depends_on": [], "gate": "G1", "status": "passed"},
        ],
        "node_results": {"N1": {"status": "passed", "updated_at": "2026-05-31T12:00:00Z"}},
        "gate_results": {"G1": {"status": "passed", "node": "N1"}},
    }

    gs.save_graph(graph_path, graph)

    closure = json.loads((sprints / f"{sid}.closure.json").read_text(encoding="utf-8"))
    assert closure["status"] == "closed"
    assert closure["all_nodes_passed"] is True
    assert closure["all_required_gates_passed"] is True
    # CLOSURE_TRACEABILITY_STALE: absence of a coverage projection is unknown,
    # not evidence that zero requirements were traced.
    assert closure["acceptance_traceability_coverage"] is None


def test_save_graph_marks_closure_failed_when_only_failed_nodes_remain(tmp_path, monkeypatch):
    gs = _load_local_graph_scheduler()

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-runtime-failed-closure"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph = {
        "sprint_id": sid,
        "required_gates": ["G1"],
        "nodes": [
            {"id": "N1", "goal": "Implement", "depends_on": [], "gate": "G1", "status": "passed"},
            {"id": "N2", "goal": "Evaluate", "depends_on": ["N1"], "gate": "G1", "status": "failed"},
        ],
        "node_results": {
            "N1": {"status": "passed", "updated_at": "2026-05-31T12:00:00Z"},
            "N2": {"status": "failed", "updated_at": "2026-05-31T12:01:00Z"},
        },
        "gate_results": {"G1": {"status": "blocked", "node": "N2"}},
    }

    gs.save_graph(graph_path, graph)

    closure = json.loads((sprints / f"{sid}.closure.json").read_text(encoding="utf-8"))
    assert closure["status"] == "failed"
    assert closure["all_nodes_passed"] is False
    assert closure["open_nodes"] == ["N2"]
    assert closure["failed_nodes"] == ["N2"]
    assert closure["failed_at"]


def test_typed_runtime_rejects_stale_revision_and_never_regresses(tmp_path, monkeypatch):
    gs = _load_local_graph_scheduler()

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-typed-revision"
    graph_path = sprints / f"{sid}.task_graph.json"
    state_path = sprints / f"{sid}.task_graph_state.json"
    graph_path.write_text(
        json.dumps({
            "schema_version": "solar.scheduler_runtime_projection.v1",
            "sprint_id": sid,
            "runtime_state_filename": state_path.name,
            "nodes": [{
                "id": "N1",
                "goal": "Run once",
                "depends_on": [],
                "write_scope": ["artifacts/N1"],
            }],
        }) + "\n",
        encoding="utf-8",
    )
    state_path.write_text(
        json.dumps({
            "schema_version": "solar.task_graph_state.v1",
            "sprint_id": sid,
            "revision": 0,
            "run_status": "queued",
            "nodes": {"N1": {"status": "pending", "attempt": 0, "blocked_by": []}},
            "node_results": {"N1": {"status": "pending"}},
        }) + "\n",
        encoding="utf-8",
    )

    first = gs.load_graph(graph_path)
    stale = gs.load_graph(graph_path)
    gs.set_node_status(first, "N1", "dispatched")
    gs.save_graph(graph_path, first)

    committed = json.loads(state_path.read_text(encoding="utf-8"))
    assert committed["revision"] == 1
    assert committed["nodes"]["N1"]["status"] == "dispatched"

    gs.set_node_status(stale, "N1", "reviewing")
    with pytest.raises(RuntimeError, match="stale scheduler state revision"):
        gs.save_graph(graph_path, stale)

    preserved = json.loads(state_path.read_text(encoding="utf-8"))
    assert preserved["revision"] == 1
    assert preserved["nodes"]["N1"]["status"] == "dispatched"

    gs.set_node_status(first, "N1", "reviewing")
    gs.save_graph(graph_path, first)
    advanced = json.loads(state_path.read_text(encoding="utf-8"))
    assert advanced["revision"] == 2
    assert advanced["nodes"]["N1"]["status"] == "reviewing"
