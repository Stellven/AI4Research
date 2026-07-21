from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[2] / "lib" / "multi_task_runner.py"
spec = importlib.util.spec_from_file_location("multi_task_runner", MODULE)
multi_task_runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(multi_task_runner)


def _graph(tmp_path: Path, statuses: list[str]) -> Path:
    graph = tmp_path / "sprint-stale.task_graph.json"
    graph.write_text(
        multi_task_runner.json.dumps(
            {
                "sprint_id": "sprint-stale",
                "nodes": [{"id": f"N{i+1}", "status": status} for i, status in enumerate(statuses)],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return graph


def test_all_graphs_terminal_accepts_only_terminal_states(tmp_path):
    graph = _graph(tmp_path, ["passed", "failed", "skipped"])

    assert multi_task_runner._all_graphs_terminal([str(graph)]) is True


def test_all_graphs_terminal_rejects_reviewing_and_pending(tmp_path):
    graph = _graph(tmp_path, ["passed", "reviewing", "pending"])

    assert multi_task_runner._all_graphs_terminal([str(graph)]) is False


def test_detect_stale_scheduler_runners_reports_required_fields(monkeypatch, tmp_path):
    graph = _graph(tmp_path, ["passed"])
    sched_dir = tmp_path / "run" / "multi-task" / "schedulers"
    monkeypatch.setattr(multi_task_runner, "SCHEDULER_PID_DIR", sched_dir)
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", tmp_path / "run" / "multi-task")
    multi_task_runner.json_write(
        sched_dir / "scheduler-123.json",
        {
            "pid": 123,
            "started_at": "2026-05-28T00:00:00Z",
            "graphs": [str(graph)],
            "log": str(sched_dir / "scheduler-123.log"),
        },
    )
    monkeypatch.setattr(
        multi_task_runner,
        "_scheduler_process_rows",
        lambda: [{"pid": 123, "elapsed": "03:21", "rss_kb": 2048, "command": f"python3 multi_task_runner.py start --graph {graph}"}],
    )

    rows = multi_task_runner.detect_stale_scheduler_runners()

    assert len(rows) == 1
    row = rows[0]
    assert row["pid"] == 123
    assert row["graph"] == str(graph)
    assert row["sprint_id"] == "sprint-stale"
    assert row["elapsed"] == "03:21"
    assert row["rss_mb"] == 2.0
    assert row["log"].endswith("scheduler-123.log")
    assert row["reason"] == "completed_graph_runner"
    assert row["stale"] is True


def test_detect_stale_scheduler_runners_apply_only_kills_exact_stale(monkeypatch, tmp_path):
    stale_graph = _graph(tmp_path, ["passed"])
    active_graph = tmp_path / "sprint-active.task_graph.json"
    active_graph.write_text(
        multi_task_runner.json.dumps({"sprint_id": "sprint-active", "nodes": [{"id": "N1", "status": "reviewing"}]}) + "\n",
        encoding="utf-8",
    )
    sched_dir = tmp_path / "run" / "multi-task" / "schedulers"
    monkeypatch.setattr(multi_task_runner, "SCHEDULER_PID_DIR", sched_dir)
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", tmp_path / "run" / "multi-task")
    multi_task_runner.json_write(sched_dir / "scheduler-111.json", {"pid": 111, "graphs": [str(stale_graph)], "log": str(sched_dir / "111.log")})
    multi_task_runner.json_write(sched_dir / "scheduler-222.json", {"pid": 222, "graphs": [str(active_graph)], "log": str(sched_dir / "222.log")})
    monkeypatch.setattr(
        multi_task_runner,
        "_scheduler_process_rows",
        lambda: [
            {"pid": 111, "elapsed": "00:10", "rss_kb": 1024, "command": f"python3 multi_task_runner.py start --graph {stale_graph}"},
            {"pid": 222, "elapsed": "00:20", "rss_kb": 1024, "command": f"python3 multi_task_runner.py start --graph {active_graph}"},
        ],
    )
    monkeypatch.setattr(multi_task_runner, "_pid_is_alive", lambda pid: True)
    killed: list[int] = []
    monkeypatch.setattr(multi_task_runner.os, "kill", lambda pid, sig: killed.append(pid))

    rows = multi_task_runner.detect_stale_scheduler_runners(apply_cleanup=True)

    assert killed == [111]
    assert any(row["pid"] == 111 and row["action"] == "sigterm" for row in rows)
    assert any(row["pid"] == 222 and row["action"] == "keep" and row["stale"] is False for row in rows)


def test_render_plain_surfaces_work_column(monkeypatch):
    monkeypatch.setattr(multi_task_runner, "free_memory_gb", lambda: None)
    monkeypatch.setattr(multi_task_runner, "tmux_session_exists", lambda: True)
    monkeypatch.setattr(multi_task_runner, "list_harness_panes", lambda: [])
    monkeypatch.setattr(multi_task_runner, "recent_dispatch_rows", lambda limit=12: [])
    monkeypatch.setattr(
        multi_task_runner,
        "list_task_rows",
        lambda: [
            {"id": "mt-a", "status": "running", "effective_status": "running", "work": "ACTIVE", "data_class": "live", "pane_type": "multi-task/builder", "operator_id": "N/A", "operator_vendor": "N/A", "operator_pane": "N/A", "tmux_status": "live", "sprint_id": "s", "node_id": "N1", "age": "1m", "updated_at": "2026-05-28T00:00:00Z"},
            {"id": "mt-b", "status": "completed", "effective_status": "completed", "work": "hist", "data_class": "historical", "pane_type": "multi-task/builder", "operator_id": "N/A", "operator_vendor": "N/A", "operator_pane": "N/A", "tmux_status": "dead", "sprint_id": "s", "node_id": "N2", "age": "2m", "updated_at": "2026-05-28T00:00:00Z"},
        ],
    )
    monkeypatch.setattr(
        multi_task_runner,
        "cached_status_summaries_for_graphs",
        lambda paths: [],
    )

    lines = multi_task_runner.render_to_lines(
        {
            "guard": {"ok": True, "reason": "ready"},
            "panes": [],
            "dispatches": [],
            "graphs": [],
            "capability": {"ok": 1, "warn": 0, "error": 0},
        }
    )

    rendered = "\n".join(lines)
    assert "work" in rendered
    assert "ACTIVE" in rendered
    assert "hist" in rendered


def test_start_loop_exits_when_explicit_graphs_terminal(monkeypatch, tmp_path):
    graph = _graph(tmp_path, ["passed"])
    register_calls: list[list[str]] = []
    unregister_calls: list[bool] = []
    schedule_calls: list[bool] = []
    monkeypatch.setattr(multi_task_runner, "_register_scheduler_pid", lambda graphs: register_calls.append(list(graphs)))
    monkeypatch.setattr(multi_task_runner, "_unregister_scheduler_pid", lambda: unregister_calls.append(True))
    monkeypatch.setattr(multi_task_runner, "schedule_once", lambda args: schedule_calls.append(True) or {"guard": {"ok": True, "reason": "ready"}, "panes": [], "dispatches": [], "graphs": [], "capability": {"ok": 1, "warn": 0, "error": 0}})
    monkeypatch.setattr(multi_task_runner, "render_result", lambda result, args: None)
    monkeypatch.setattr(multi_task_runner, "_all_graphs_terminal", lambda graphs: True)
    monkeypatch.setattr(multi_task_runner, "active_tasks", lambda: [])
    monkeypatch.setattr(multi_task_runner.time, "sleep", lambda seconds: None)

    rc = multi_task_runner.main(["start", "--graph", str(graph), "--interval", "1"])

    assert rc == 0
    assert register_calls == [[str(graph)]]
    assert unregister_calls == [True]
    assert schedule_calls == [True]


def test_parser_exposes_stale_schedulers_subcommand():
    parser = multi_task_runner.build_parser()
    subs = parser._subparsers._group_actions[0].choices

    assert "stale-schedulers" in subs
