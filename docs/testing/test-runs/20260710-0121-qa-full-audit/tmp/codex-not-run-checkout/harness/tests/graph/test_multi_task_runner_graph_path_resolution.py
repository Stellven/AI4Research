from __future__ import annotations

import json
import sys
from pathlib import Path


HARNESS_LIB = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import multi_task_runner  # noqa: E402


def test_relative_sprints_graph_path_aligns_finished_task(monkeypatch, tmp_path):
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sprints.mkdir(parents=True)
    graph = sprints / "sprint-relative.task_graph.json"
    graph.write_text(
        json.dumps(
            {
                "sprint_id": "sprint-relative",
                "nodes": [{"id": "N1", "status": "passed", "depends_on": []}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(multi_task_runner, "HARNESS_DIR", harness)
    monkeypatch.setattr(multi_task_runner, "SPRINTS_DIR", sprints)
    row = {
        "status": "running",
        "graph": "sprints/sprint-relative.task_graph.json",
        "node_id": "N1",
    }

    row["graph_status"] = multi_task_runner.graph_node_status_for_task(row)

    assert row["graph_status"] == "passed"
    assert multi_task_runner.effective_task_status(row) == "completed_aligned"


def test_worker_activity_projection_treats_live_idle_session_as_ok():
    projection = multi_task_runner.worker_activity_projection(
        True,
        {"live": 0},
        0,
        True,
    )

    assert projection["ok"] is True
    assert projection["data_source"] == "idle:no_active_workers"
    assert projection["active_workers"] == "0 live / 0 active"


def test_worker_activity_projection_flags_missing_session_history():
    projection = multi_task_runner.worker_activity_projection(
        False,
        {"live": 0},
        0,
        True,
    )

    assert projection["ok"] is False
    assert projection["data_source"] == "history:no_multi_task_session"


def test_monitor_summary_reports_idle_ready_graph_inside_status_snapshot(monkeypatch):
    monkeypatch.setattr(multi_task_runner, "tmux_session_exists", lambda: True)
    monkeypatch.setattr(multi_task_runner, "task_inventory", lambda tasks: {
        "total": 0,
        "active": 0,
        "live": 0,
        "historical": 0,
        "stale": 0,
        "classes": {},
        "statuses": {},
        "latest": None,
        "latest_age": "N/A",
    })
    result = {
        "guard": {"ok": True, "reason": "ready"},
        "panes": [],
        "dispatches": [],
        "graphs": [{"sid": "sprint-ready", "ready": ["B1"]}],
        "capability": {"ok": 1, "warn": 0, "error": 0},
    }

    summary = multi_task_runner.monitor_summary(result, [])

    assert summary["status"] == "warn"
    assert summary["data_source"] == "idle:no_active_workers"
    assert any(item["type"] == "ready_graph_idle" for item in summary["findings"])
