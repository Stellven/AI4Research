"""O4_status_surface — status lists ready child nodes, quota blocker, no stale cache."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".." / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from multi_task_runner import (
    epic_child_status_lines,
    _quota_blocker_text,
    invalidate_graph_summary_cache,
    load_graph_summary_cache,
    save_graph_summary_cache,
    GRAPH_SUMMARY_CACHE_PATH,
    status_summary_for_graph,
    render_plain,
    screen_view_model,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _graph_summary(ok=True, sid="sprint-test-s03", ready=None, counts=None):
    return {
        "ok": ok,
        "sid": sid,
        "description": "test sprint",
        "counts": counts or {"passed": 2, "pending": 1, "reviewing": 0},
        "ready": ready or ["N1_build"],
        "graph_updated_at": "2026-05-28T12:00:00Z",
    }


# ── AC1: status lists ready child nodes ───────────────────────────────


class TestEpicChildStatusLines:
    def test_returns_rows_for_ok_graphs(self):
        graphs = [
            _graph_summary(sid="sprint-epic-s02", ready=["O1"]),
            _graph_summary(sid="sprint-epic-s03", ready=["N1", "N2"]),
        ]
        rows = epic_child_status_lines(graphs)
        assert len(rows) == 2
        assert rows[0]["sid"] == "sprint-epic-s02"
        assert rows[0]["ready_nodes"] == ["O1"]
        assert rows[1]["ready_nodes"] == ["N1", "N2"]

    def test_skips_error_graphs(self):
        graphs = [
            _graph_summary(ok=False),
            _graph_summary(ok=True, sid="sprint-ok"),
        ]
        rows = epic_child_status_lines(graphs)
        assert len(rows) == 1
        assert rows[0]["sid"] == "sprint-ok"

    def test_empty_graphs(self):
        rows = epic_child_status_lines([])
        assert rows == []

    def test_node_counts_populated(self):
        graphs = [_graph_summary(counts={"passed": 3, "pending": 2})]
        rows = epic_child_status_lines(graphs)
        assert rows[0]["node_counts"] == {"passed": 3, "pending": 2}


class TestRenderPlainShowsChildren:
    def test_render_includes_child_table(self, capsys):
        graphs = [
            _graph_summary(sid="sprint-test-s02", ready=["O1"]),
            _graph_summary(sid="sprint-test-s03", ready=["N1"]),
        ]
        result = {
            "guard": {"ok": True},
            "panes": [],
            "graphs": graphs,
            "dispatches": [],
            "capability": {},
            "refresh_mode": "fresh",
            "observed_at": "2026-05-28T12:00:00Z",
        }
        render_plain(result, no_clear=True)
        out = capsys.readouterr().out
        assert "sprint-test-s02" in out
        assert "sprint-test-s03" in out
        assert "O1" in out
        assert "N1" in out


class TestScreenViewModelChildren:
    def test_dag_includes_children(self):
        import argparse
        graphs = [_graph_summary(sid="sprint-epic-s02", ready=["O1"])]
        vm = screen_view_model(
            {"guard": {"ok": True}, "panes": [], "graphs": graphs, "dispatches": [], "capability": {}},
            argparse.Namespace(),
            120,
        )
        dag = vm["dag"]
        assert len(dag["children"]) == 1
        assert dag["children"][0]["ready_nodes"] == ["O1"]


# ── AC2: status displays quota blocker ────────────────────────────────


class TestQuotaBlockerText:
    def test_no_blocker_when_ok(self):
        text = _quota_blocker_text([], {"ok": True})
        assert text == ""

    def test_quota_blocked(self):
        guard = {"ok": False, "reason": "recent_quota_or_rate_limit", "hits": [{"task": "t1"}]}
        text = _quota_blocker_text([], guard)
        assert "quota_blocked" in text
        assert "1 tasks" in text

    def test_quota_blocked_no_hits(self):
        guard = {"ok": False, "reason": "recent_quota_or_rate_limit"}
        text = _quota_blocker_text([], guard)
        assert text == "quota_blocked"

    def test_other_blocker(self):
        guard = {"ok": False, "reason": "low_memory"}
        text = _quota_blocker_text([], guard)
        assert "low_memory" in text


class TestRenderPlainShowsQuotaBlocker:
    def test_quota_row_in_status_table(self, capsys):
        graphs = [_graph_summary()]
        guard = {"ok": False, "reason": "recent_quota_or_rate_limit", "hits": [{"task": "t1"}]}
        result = {
            "guard": guard,
            "panes": [],
            "graphs": graphs,
            "dispatches": [],
            "capability": {},
            "refresh_mode": "fresh",
            "observed_at": "2026-05-28T12:00:00Z",
        }
        render_plain(result, no_clear=True)
        out = capsys.readouterr().out
        assert "quota_blocker" in out
        assert "quota_blocked" in out


class TestScreenViewModelQuotaBlocker:
    def test_dag_includes_quota_blocker(self):
        import argparse
        graphs = [_graph_summary()]
        guard = {"ok": False, "reason": "recent_quota_or_rate_limit", "hits": [{"task": "t1"}]}
        vm = screen_view_model(
            {"guard": guard, "panes": [], "graphs": graphs, "dispatches": [], "capability": {}},
            argparse.Namespace(),
            120,
        )
        assert "quota_blocked" in vm["dag"]["quota_blocker"]


# ── AC3: no stale cache after graph edit ──────────────────────────────


class TestInvalidateGraphSummaryCache:
    def test_invalidate_specific_path(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "graph_summary_cache.json"
        monkeypatch.setattr("multi_task_runner.GRAPH_SUMMARY_CACHE_PATH", cache_path)
        monkeypatch.setattr("multi_task_runner.RUN_DIR", tmp_path)

        # Seed cache
        key = "/fake/graph.task_graph.json"
        cache = {"version": 1, "entries": {key: {"mtime_ns": 1, "size": 100, "summary": {"ok": True}}}}
        save_graph_summary_cache(cache)

        # Invalidate
        removed = invalidate_graph_summary_cache(Path(key))
        assert removed == 1

        # Verify entry gone
        after = load_graph_summary_cache()
        assert key not in after["entries"]

    def test_invalidate_all(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "graph_summary_cache.json"
        monkeypatch.setattr("multi_task_runner.GRAPH_SUMMARY_CACHE_PATH", cache_path)
        monkeypatch.setattr("multi_task_runner.RUN_DIR", tmp_path)

        cache = {"version": 1, "entries": {
            "/a": {"mtime_ns": 1, "size": 100, "summary": {"ok": True}},
            "/b": {"mtime_ns": 2, "size": 200, "summary": {"ok": True}},
        }}
        save_graph_summary_cache(cache)

        removed = invalidate_graph_summary_cache()
        assert removed == 2
        after = load_graph_summary_cache()
        assert len(after["entries"]) == 0

    def test_invalidate_nonexistent_key(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "graph_summary_cache.json"
        monkeypatch.setattr("multi_task_runner.GRAPH_SUMMARY_CACHE_PATH", cache_path)
        monkeypatch.setattr("multi_task_runner.RUN_DIR", tmp_path)

        save_graph_summary_cache({"version": 1, "entries": {}})
        removed = invalidate_graph_summary_cache(Path("/nonexistent"))
        assert removed == 0
