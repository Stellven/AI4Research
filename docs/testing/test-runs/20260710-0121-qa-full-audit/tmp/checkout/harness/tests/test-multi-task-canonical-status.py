#!/usr/bin/env python3
"""Regression: task_graph-only sprints get coordinator-visible status.json."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import multi_task_runner as mtr  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_status(path: Path, status: str, phase: str, handoff_to: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == status, data
    assert data["phase"] == phase, data
    assert data["handoff_to"] == handoff_to, data
    assert data["history"][0]["event"] == "status_auto_created_from_task_graph", data
    assert Path(data["artifacts"]["task_graph"]).exists(), data


with tempfile.TemporaryDirectory() as tmp:
    sprints = Path(tmp) / "sprints"
    sprints.mkdir()

    active_sid = "sprint-test-active"
    active_graph = sprints / f"{active_sid}.task_graph.json"
    write_json(active_graph, {
        "sprint_id": active_sid,
        "title": "Active DAG",
        "nodes": [{"id": "S1", "status": "pending", "depends_on": []}],
    })
    (sprints / f"{active_sid}.contract.md").write_text("# Contract\n", encoding="utf-8")
    summary = mtr.status_summary_for_graph(active_graph)
    assert summary["ok"] is True, summary
    assert_status(sprints / f"{active_sid}.status.json", "active", "planning_complete", "builder_main")

    done_sid = "sprint-test-done"
    done_graph = sprints / f"{done_sid}.task_graph.json"
    write_json(done_graph, {
        "sprint_id": done_sid,
        "title": "Done DAG",
        "nodes": [{"id": "S1", "status": "passed", "depends_on": []}],
    })
    summary = mtr.status_summary_for_graph(done_graph)
    assert summary["ok"] is True, summary
    assert_status(sprints / f"{done_sid}.status.json", "reviewing", "implementation_complete", "evaluator")

print("PASS: multi-task creates canonical sprint status for task_graph-only sprints")
