#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
                "updated_at": "2026-05-31T12:00:00Z",
            },
        ],
        "node_results": {
            "N1": {
                "status": "assigned",
                "assigned_to": "pane-1",
                "dispatch_id": "dispatch-1",
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
    assert saved_state["node_results"]["N1"]["status"] == "assigned"
    assert saved_state["dispatch_ids"]["N1"] == "dispatch-1"
    assert gs.node_status(gs.load_graph(graph_path), "N1") == "assigned"


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
