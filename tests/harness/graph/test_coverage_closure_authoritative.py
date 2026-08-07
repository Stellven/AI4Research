#!/usr/bin/env python3
"""Regression: once a sprint has terminally closed, the coverage view defers to the
authoritative closure and reports PASS even if task_graph.json node statuses still
lag (Defect C2).

Without this, the parent acceptance_verdict can stick at IN_PROGRESS after a clean
close (the coverage trace reads a stale `reviewing` node status), and an epic parent
would conclude the child is unfinished. The override fires only when closure already
says the sprint passed, so it cannot manufacture a pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = (Path(__file__).resolve().parents[3] / 'harness') / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import requirement_coverage as rc


def _setup(tmp_path, node_status: str):
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    sid = "sprint-c2"
    graph = {
        "sprint_id": sid,
        "nodes": [
            {"id": "N1", "goal": "slice", "depends_on": [], "acceptance": ["x"],
             "status": node_status, "requirement_ids": ["REQ-001"]},
        ],
        "node_results": {},
        "gate_results": {},
    }
    (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{sid}.requirement_ir.json").write_text(
        json.dumps(
            {"id": "req-test", "requirements": [
                {"id": "REQ-001", "source_text": "deliver", "success_criteria": ["done"],
                 "verification_method": "task_graph_closeout"}]}
        ),
        encoding="utf-8",
    )
    return sprints, sid


def test_open_graph_is_not_pass(tmp_path):
    # No closure -> an incomplete graph is non-PASS (IN_PROGRESS), unchanged behavior.
    sprints, sid = _setup(tmp_path, "reviewing")
    bundle = rc.evaluate_sid(sid, sprints_dir=sprints, write=False)
    assert bundle["acceptance_verdict"]["verdict"] != "PASS"


def test_terminally_closed_overrides_stale_status_to_pass(tmp_path):
    # Node status still lags as 'reviewing', but closure is authoritative -> PASS.
    sprints, sid = _setup(tmp_path, "reviewing")
    (sprints / f"{sid}.closure.json").write_text(
        json.dumps({"status": "closed", "all_nodes_passed": True}), encoding="utf-8")
    bundle = rc.evaluate_sid(sid, sprints_dir=sprints, write=False)
    av = bundle["acceptance_verdict"]
    assert av["verdict"] == "PASS"
    assert av["reasons"] == []
    assert bundle["coverage_report"]["summary"]["graph_complete"] is True


def test_written_coverage_refreshes_terminal_closure_traceability(tmp_path):
    """CLOSURE_TRACEABILITY_STALE: closure must reflect canonical coverage."""
    sprints, sid = _setup(tmp_path, "reviewing")
    closure_path = sprints / f"{sid}.closure.json"
    closure_path.write_text(
        json.dumps(
            {
                "status": "closed",
                "all_nodes_passed": True,
                "all_required_gates_passed": True,
                "acceptance_traceability_coverage": 0,
            }
        ),
        encoding="utf-8",
    )

    bundle = rc.evaluate_sid(sid, sprints_dir=sprints, write=True)
    closure = json.loads(closure_path.read_text(encoding="utf-8"))

    assert bundle["acceptance_verdict"]["verdict"] == "PASS"
    assert bundle["coverage_report"]["summary"]["coverage_ratio"] == 1.0
    assert closure["acceptance_traceability_coverage"] == 1.0
