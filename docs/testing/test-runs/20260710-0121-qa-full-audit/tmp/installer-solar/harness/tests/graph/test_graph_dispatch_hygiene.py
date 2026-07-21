#!/usr/bin/env python3
"""Regression tests for graph-dispatch pane hygiene gating."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_node_dispatcher as gnd  # noqa: E402


def _write_hygiene(path: Path, pane: str, state: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"panes": {pane: {"state": state}}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_dirty_pane_is_unavailable_before_dispatch(tmp_path, monkeypatch):
    hygiene = tmp_path / "pane-hygiene.json"
    _write_hygiene(hygiene, "solar-harness-lab:0.2", "dirty")
    monkeypatch.setattr(gnd, "_pane_hygiene_file", lambda: hygiene)

    assert gnd._pane_hygiene_unavailable_reason("solar-harness-lab:0.2") == "pane_hygiene_dirty"


def test_needs_respawn_pane_is_not_auto_recovered(tmp_path, monkeypatch):
    hygiene = tmp_path / "pane-hygiene.json"
    _write_hygiene(hygiene, "solar-harness-lab:0.2", "needs_respawn")
    monkeypatch.setattr(gnd, "_pane_hygiene_file", lambda: hygiene)
    monkeypatch.setattr(gnd, "_recover_pane_hygiene_if_idle", lambda pane, state: (_ for _ in ()).throw(AssertionError("must not recover needs_respawn")))

    assert gnd._pane_hygiene_unavailable_reason("solar-harness-lab:0.2") == "pane_hygiene_needs_respawn"


def test_assigned_pane_guard_checks_hygiene_before_tui_busy(tmp_path, monkeypatch):
    hygiene = tmp_path / "pane-hygiene.json"
    pane = "solar-harness-lab:0.2"
    _write_hygiene(hygiene, pane, "dirty")
    monkeypatch.setattr(gnd, "_pane_hygiene_file", lambda: hygiene)
    monkeypatch.setattr(gnd, "_pane_title", lambda _pane: "Builder")
    monkeypatch.setattr(gnd, "_pane_health", lambda _pane: {})
    monkeypatch.setattr(gnd, "_models_for_pane", lambda _pane, _title="": ["glm-5.1"])
    monkeypatch.setattr(gnd, "_pane_tail", lambda _pane: "")
    monkeypatch.setattr(gnd, "_quota_exhausted_models", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda _pane: "")
    monkeypatch.setattr(gnd, "_multi_task_direct_dispatch_unavailable_reason", lambda _pane, **_kwargs: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda _pane: (_ for _ in ()).throw(AssertionError("hygiene should short-circuit before TUI busy probe")))

    assert gnd._assigned_pane_unavailable_reason(pane) == "pane_hygiene_dirty"


def test_feedback_survey_prompt_is_recoverable_dispatch_prompt():
    tail = """
● How is Claude doing this session?
  (optional)
  1: Bad   2: Fine   3: Good  0: Dismiss
"""

    assert gnd._pane_dispatch_prompt_reason(tail) == "feedback_survey_prompt"
    assert "feedback_survey_prompt" in gnd.RECOVERABLE_DISPATCH_PROMPT_REASONS


def test_rewind_prompt_is_recoverable_dispatch_prompt():
    tail = """
  Rewind
  Restore the code and/or conversation to the point before…
  Enter to continue · Esc to exit
"""

    assert gnd._pane_dispatch_prompt_reason(tail) == "rewind_prompt_blocked"
    assert "rewind_prompt_blocked" in gnd.RECOVERABLE_DISPATCH_PROMPT_REASONS


def test_dispatch_ready_marks_graph_active_panes_busy(tmp_path, monkeypatch):
    graph_path = tmp_path / "graph.json"
    graph = {
        "sprint_id": "sid",
        "nodes": [
            {"id": "A1", "status": "dispatched", "assigned_to": "pane-a"},
            {"id": "A2", "status": "pending"},
        ],
        "node_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    captured = {}

    monkeypatch.setattr(gnd, "_no_dispatch_enabled", lambda: False)
    monkeypatch.setattr(gnd, "_reconcile_existing_dispatches", lambda graph, path: [])
    monkeypatch.setattr(gnd, "_discover_workers", lambda dry_run=False: [
        {"pane": "pane-a", "busy": False, "unavailable_reason": ""},
        {"pane": "pane-b", "busy": False, "unavailable_reason": ""},
    ])

    def fake_enqueue_ready(graph, graph_path_arg, workers, **kwargs):
        captured["workers"] = workers
        return {"ok": True, "enqueued": [], "queued": []}

    monkeypatch.setattr(gnd, "enqueue_ready", fake_enqueue_ready)
    monkeypatch.setattr(gnd, "drain_queue", lambda *args, **kwargs: {"ok": True, "processed": 0, "results": []})
    monkeypatch.setattr(gnd, "load_graph", lambda path: json.loads(graph_path.read_text(encoding="utf-8")))
    monkeypatch.setattr(gnd, "save_graph", lambda path, graph: None)

    result = gnd.dispatch_ready(str(graph_path))

    assert result["ok"] is True
    workers_by_pane = {item["pane"]: item for item in captured["workers"]}
    assert workers_by_pane["pane-a"]["busy"] is True
    assert workers_by_pane["pane-a"]["unavailable_reason"] == "graph_active_assignment"
    assert workers_by_pane["pane-b"]["busy"] is False
