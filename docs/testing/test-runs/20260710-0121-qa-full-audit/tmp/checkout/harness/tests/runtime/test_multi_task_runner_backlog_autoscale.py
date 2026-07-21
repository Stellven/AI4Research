from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import multi_task_runner as mtr  # noqa: E402


def test_schedule_once_respects_profile_parallel_limit(monkeypatch, tmp_path):
    graph_path = tmp_path / "sprint-x.task_graph.json"
    graph = {"sprint_id": "sprint-x", "nodes": [{"id": "N1"}, {"id": "N2"}]}
    candidates = [{"id": "N1"}, {"id": "N2"}]
    launches: list[str] = []

    args = SimpleNamespace(
        max_workers=4,
        memory_reserve_gb=0,
        cooldown_sec=0,
        quota_backoff_sec=0,
        graph=[],
        profile="",
        model="",
        backend="",
        dry_run=False,
    )

    monkeypatch.setattr(mtr, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(mtr, "graph_files", lambda explicit: [graph_path])
    monkeypatch.setattr(mtr, "load_graph", lambda path: graph)
    monkeypatch.setattr(mtr, "ready_nodes", lambda payload: list(candidates))
    monkeypatch.setattr(mtr, "recover_quota_failed_nodes", lambda path, payload: 0)
    monkeypatch.setattr(mtr, "launch_guard", lambda *a, **k: {"ok": True, "reason": "ready"})
    monkeypatch.setattr(mtr, "active_tasks", lambda: [])
    monkeypatch.setattr(mtr, "scope_conflicts_with_active", lambda node: False)
    monkeypatch.setattr(
        mtr,
        "select_profile",
        lambda *a, **k: {"name": "builder", "role": "builder", "max_parallel": 1},
    )
    monkeypatch.setattr(
        mtr,
        "capability_for_profile",
        lambda profile: {"status": "ok", "profile": "builder", "model": "sonnet", "backend": "claude-cli", "evidence": "ok"},
    )
    monkeypatch.setattr(mtr, "status_summary_for_graph", lambda path: {"sid": "sprint-x", "ready": ["N1", "N2"]})
    monkeypatch.setattr(mtr, "list_harness_panes", lambda: [])
    monkeypatch.setattr(mtr, "recent_dispatch_rows", lambda: [])
    monkeypatch.setattr(mtr, "capability_summary", lambda rows=None: {"ok": 1, "warn": 0, "error": 0})
    monkeypatch.setattr(mtr, "cached_status_summaries_for_graphs", lambda paths: [])
    monkeypatch.setattr(mtr, "effective_scheduler_max_workers", lambda default: default)

    def _launch(graph_path_arg, graph_arg, node, args_arg, dry_run=False):
        launches.append(str(node["id"]))
        return {"id": f"task-{node['id']}", "node_id": node["id"]}

    monkeypatch.setattr(mtr, "launch_node", _launch)

    result = mtr.schedule_once(args)

    assert launches == ["N1"]
    assert len(result["launched"]) == 1
    assert any(item.get("reason") == "profile_parallel_limit_reached" and item.get("node") == "N2" for item in result["skipped"])


def test_status_snapshot_uses_effective_scheduler_max_workers(monkeypatch, tmp_path):
    args = SimpleNamespace(
        max_workers=4,
        memory_reserve_gb=0,
        cooldown_sec=0,
        quota_backoff_sec=0,
        graph=[],
    )

    monkeypatch.setattr(mtr, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(mtr, "effective_scheduler_max_workers", lambda default: 11)
    monkeypatch.setattr(mtr, "launch_guard", lambda max_workers, *a, **k: {"ok": True, "max_workers": max_workers})
    monkeypatch.setattr(mtr, "fresh_status_summaries_for_graphs", lambda paths: [])
    monkeypatch.setattr(mtr, "graph_files", lambda explicit: [])
    monkeypatch.setattr(mtr, "list_harness_panes", lambda: [])
    monkeypatch.setattr(mtr, "recent_dispatch_rows", lambda: [])
    monkeypatch.setattr(mtr, "capability_summary", lambda rows=None: {"ok": 1, "warn": 0, "error": 0})

    result = mtr.status_snapshot(args)

    assert result["guard"]["max_workers"] == 11
