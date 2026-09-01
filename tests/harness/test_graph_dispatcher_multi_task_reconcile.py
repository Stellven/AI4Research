import json
from pathlib import Path

from harness.lib import graph_node_dispatcher as dispatcher


def test_reconcile_ignores_active_multi_task_status_without_task_identity(tmp_path, monkeypatch):
    run_dir = tmp_path / "run" / "multi-task"
    task_dir = run_dir / "anonymous"
    task_dir.mkdir(parents=True)
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "status": "running",
                "sprint_id": "sprint-anonymous",
                "node_id": "N1",
                "operator_id": "test-discovery",
                "updated_at": "2026-05-26T14:35:26Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dispatcher, "MULTI_TASK_RUN_DIR", run_dir)
    monkeypatch.setattr(dispatcher, "SPRINTS_DIR", tmp_path / "sprints")
    graph = {
        "sprint_id": "sprint-anonymous",
        "nodes": [{"id": "N1", "status": "pending", "goal": "do work", "depends_on": []}],
    }

    repaired = dispatcher._reconcile_existing_dispatches(
        graph,
        tmp_path / "sprint-anonymous.task_graph.json",
    )

    assert repaired == []
    assert graph["nodes"][0]["status"] == "pending"
    assert "execution_attempt" not in graph["nodes"][0]


def test_reconcile_preserves_active_multi_task_worker(tmp_path, monkeypatch):
    run_dir = tmp_path / "run" / "multi-task"
    task_dir = run_dir / "mt-test-sprint-N1"
    task_dir.mkdir(parents=True)
    result_path = tmp_path / "run" / "operator-results" / "test-discovery" / "mt-test-sprint-N1" / "result.json"
    status_path = task_dir / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "id": "mt-test-sprint-N1",
                "status": "running",
                "sprint_id": "sprint-test-multi-task-reconcile",
                "node_id": "N1",
                "operator_id": "test-discovery",
                "submit_mode": "operatord",
                "result_path": str(result_path),
                "window": "mt-test-window",
                "updated_at": "2026-05-26T14:35:26Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dispatcher, "MULTI_TASK_RUN_DIR", run_dir)
    monkeypatch.setattr(dispatcher, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(dispatcher, "HARNESS_DIR", tmp_path)

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
    assert graph["nodes"][0]["execution_attempt"] == {
        "schema_version": "solar.node_attempt.v1",
        "phase": "execution",
        "sequence": 1,
        "repair_generation": 0,
        "task_id": "mt-test-sprint-N1",
        "dispatch_id": "mt-test-sprint-N1",
        "operator_id": "test-discovery",
        "source": "multi_task_operatord",
        "logical_role": "builder",
        "status": "running",
        "requires_operator_result": True,
        "sprint_id": "sprint-test-multi-task-reconcile",
        "node_id": "N1",
        "result_path": str(result_path),
        "activated_at": "2026-05-26T14:35:26Z",
        "updated_at": "2026-05-26T14:35:26Z",
    }
    assert repaired == [
        {
            "node": "N1",
            "pane": "multi-task:mt-test-window",
            "dispatch_id": "mt-test-sprint-N1",
            "status": "dispatched",
            "reason": "active_multi_task_status_exists",
        }
    ]

    # An ordinary scheduler tick while the same operatord task is still
    # active is an exact no-op.  In particular it must not add legacy node
    # fields or replace the frozen runtime result mirror.
    active_snapshot = json.loads(json.dumps(graph))
    repeated_active = dispatcher._reconcile_existing_dispatches(
        graph,
        tmp_path / "sprint-test.task_graph.json",
    )
    assert repeated_active == []
    assert graph == active_snapshot

    # The recovered exact task completes and publishes its handoff.  Reconcile
    # must advance to review rather than treating the synthetic multi-task pane
    # as an expired lease and making the node dispatchable again.
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "task_id": "mt-test-sprint-N1",
                "sprint_id": "sprint-test-multi-task-reconcile",
                "node_id": "N1",
                "operator_id": "test-discovery",
                "status": "completed",
                "exit_code": 0,
                "finished_at": "2026-05-26T14:36:00Z",
            }
        ),
        encoding="utf-8",
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update({"status": "completed", "exit_code": 0, "updated_at": "2026-05-26T14:36:00Z"})
    status_path.write_text(json.dumps(status), encoding="utf-8")
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    handoff = sprints / "sprint-test-multi-task-reconcile.N1-handoff.md"
    handoff.write_text("# completed discovery\n", encoding="utf-8")

    completed = dispatcher._reconcile_existing_dispatches(
        graph,
        tmp_path / "sprint-test.task_graph.json",
    )
    assert graph["nodes"][0]["status"] == "reviewing"
    assert "assigned_to" not in graph["nodes"][0]
    assert "dispatch_id" not in graph["nodes"][0]
    assert graph["nodes"][0]["execution_attempt"]["task_id"] == "mt-test-sprint-N1"
    assert completed == [
        {
            "node": "N1",
            "status": "reviewing",
            "reason": "handoff_file_exists",
            "handoff": str(handoff),
        }
    ]

    repeated = dispatcher._reconcile_existing_dispatches(
        graph,
        tmp_path / "sprint-test.task_graph.json",
    )
    assert graph["nodes"][0]["status"] == "reviewing"
    assert graph["nodes"][0]["execution_attempt"]["sequence"] == 1
    assert repeated == []
