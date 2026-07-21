import json
from pathlib import Path

from harness.lib import graph_node_dispatcher as dispatcher


def test_reconcile_preserves_active_multi_task_worker(tmp_path, monkeypatch):
    run_dir = tmp_path / "run" / "multi-task"
    task_dir = run_dir / "mt-test-sprint-N1"
    task_dir.mkdir(parents=True)
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "id": "mt-test-sprint-N1",
                "status": "running",
                "sprint_id": "sprint-test-multi-task-reconcile",
                "node_id": "N1",
                "window": "mt-test-window",
                "updated_at": "2026-05-26T14:35:26Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dispatcher, "MULTI_TASK_RUN_DIR", run_dir)
    monkeypatch.setattr(dispatcher, "SPRINTS_DIR", tmp_path / "sprints")

    graph = {
        "sprint_id": "sprint-test-multi-task-reconcile",
        "nodes": [
            {
                "id": "N1",
                "status": "pending",
                "goal": "do work",
                "depends_on": [],
            }
        ],
    }

    repaired = dispatcher._reconcile_existing_dispatches(graph, tmp_path / "sprint-test.task_graph.json")

    assert graph["nodes"][0]["status"] == "dispatched"
    assert graph["nodes"][0]["dispatch_id"] == "mt-test-sprint-N1"
    assert graph["nodes"][0]["assigned_to"] == "multi-task:mt-test-window"
    assert repaired == [
        {
            "node": "N1",
            "pane": "multi-task:mt-test-window",
            "dispatch_id": "mt-test-sprint-N1",
            "status": "dispatched",
            "reason": "active_multi_task_status_exists",
        }
    ]
