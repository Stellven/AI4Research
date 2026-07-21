#!/usr/bin/env python3
"""Regression tests for multi-task pane pool classification in status-server."""

import importlib.util
import json
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


def test_multi_task_panes_info_distinguishes_reusable_and_historical_active(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    run_dir = harness / "run" / "multi-task"
    task_a = run_dir / "task-a"
    task_b = run_dir / "task-b"
    task_a.mkdir(parents=True)
    task_b.mkdir(parents=True)
    (task_a / "status.json").write_text(json.dumps({
        "id": "task-a",
        "window": "mt-active-shell",
        "status": "completed",
        "sprint_id": "sprint-a",
        "updated_at": "2026-05-23T23:00:00Z",
    }), encoding="utf-8")
    (task_b / "status.json").write_text(json.dumps({
        "id": "task-b",
        "window": "mt-idle-shell",
        "status": "completed",
        "sprint_id": "sprint-b",
        "updated_at": "2026-05-23T23:01:00Z",
    }), encoding="utf-8")

    monkeypatch.setattr(status_server, "HARNESS_DIR", harness)
    def fake_tmux(cmd, **_kwargs):
        target = cmd[3]
        if target == "solar-harness-lab":
            return ""
        if target == "solar-harness-multi-task":
            return "\n".join([
                "0\tmt-active-shell\t1\t0\tzsh\tactive-title\t1\t%1",
                "1\tmt-idle-shell\t0\t0\tzsh\tidle-title\t1\t%2",
                "2\tmt-running\t0\t0\tclaude\trunning-title\t1\t%3",
            ])
        return ""

    monkeypatch.setattr(status_server, "_run_tmux", fake_tmux)

    panes = status_server._multi_task_panes_info()
    pool = status_server._multi_task_pane_pool_summary(panes)

    statuses = {pane["window_name"]: pane["status"] for pane in panes}
    assert statuses["mt-active-shell"] == "historical_active"
    assert statuses["mt-idle-shell"] == "reusable_idle"
    assert statuses["mt-running"] == "running"
    assert pool["historical_active"] == 1
    assert pool["reusable_idle"] == 1
    assert pool["running"] == 1


def test_multi_task_panes_info_includes_builder_lab_pool(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    run_dir = harness / "run" / "multi-task"
    task_dir = run_dir / "task-a"
    task_dir.mkdir(parents=True)
    (task_dir / "status.json").write_text(json.dumps({
        "id": "task-a",
        "window": "mt-idle-shell",
        "status": "completed",
        "sprint_id": "sprint-a",
        "updated_at": "2026-05-23T23:01:00Z",
    }), encoding="utf-8")

    def fake_tmux(cmd, **_kwargs):
        target = cmd[3]
        if target == "solar-harness-lab":
            return "\n".join([
                "0\tBuilder Lab\t1\t0\tbash\tBuilder 1 | 状态:idle/no active sprint\t1\t%1",
                "0\tBuilder Lab\t1\t1\tbash\tBuilder 2 | 状态:idle/no active sprint\t0\t%2",
                "0\tBuilder Lab\t1\t2\tbash\tBuilder 3 | 状态:idle/no active sprint\t0\t%3",
                "0\tBuilder Lab\t1\t3\tbash\tBuilder 4 | 状态:idle/no active sprint\t0\t%4",
            ])
        if target == "solar-harness-multi-task":
            return "1\tmt-idle-shell\t0\t0\tzsh\tidle-title\t1\t%5"
        return ""

    monkeypatch.setattr(status_server, "HARNESS_DIR", harness)
    monkeypatch.setattr(status_server, "_run_tmux", fake_tmux)

    panes = status_server._multi_task_panes_info()
    pool = status_server._multi_task_pane_pool_summary(panes)

    assert len(panes) == 5
    assert sum(1 for pane in panes if pane["pool"] == "builder-lab") == 4
    assert sum(1 for pane in panes if pane["pool"] == "multi-task") == 1
    assert pool["total"] == 5
    assert pool["idle"] == 4
    assert pool["reusable_idle"] == 1
