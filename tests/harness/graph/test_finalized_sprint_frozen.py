#!/usr/bin/env python3
"""Regression: a finalized sprint is terminal and frozen (Defect C).

A post-close graph scan must not reopen a closed sprint:
  * `_reconcile_existing_dispatches` must early-return when `.finalized` exists, so a
    lingering per-node handoff file cannot "repair" (revert) a node back to reviewing.
  * `_graph_terminally_closed` recognizes a closed graph so the coverage refresh keeps
    `.finalized` sticky instead of stripping it on a stale non-PASS coverage verdict.

Observed bug: after a clean close+finalize, a reconcile reset S2 passed->reviewing from
its leftover handoff file and the coverage refresh stripped `.finalized`, reopening the
sprint ~90s later.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = (Path(__file__).resolve().parents[3] / 'harness') / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_node_dispatcher as gnd


def _write_json(p: Path, obj) -> None:
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_graph_terminally_closed(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    sid = "sprint-x"
    assert gnd._graph_terminally_closed(sid) is False  # no closure file
    _write_json(sprints / f"{sid}.closure.json", {"status": "pending"})
    assert gnd._graph_terminally_closed(sid) is False
    _write_json(sprints / f"{sid}.closure.json", {"status": "closed"})
    assert gnd._graph_terminally_closed(sid) is True
    _write_json(sprints / f"{sid}.closure.json", {"status": "pending", "all_nodes_passed": True})
    assert gnd._graph_terminally_closed(sid) is True


def test_reconcile_freezes_finalized_sprint(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    sid = "sprint-frozen"
    graph_path = sprints / f"{sid}.task_graph.json"
    # a lingering per-node handoff file a reconcile would otherwise act on
    (sprints / f"{sid}.S2-handoff.md").write_text("# handoff", encoding="utf-8")

    # finalize the sprint, then reconcile: a 'dispatched' node + handoff would normally
    # be repaired to 'reviewing' — the guard must freeze it instead.
    (sprints / f"{sid}.finalized").write_text("", encoding="utf-8")
    graph = {"sprint_id": sid, "nodes": [{"id": "S2", "status": "dispatched"}]}
    _write_json(graph_path, graph)

    repaired = gnd._reconcile_existing_dispatches(graph, str(graph_path))

    assert repaired == []  # frozen: no repairs on a finalized sprint
    assert graph["nodes"][0]["status"] == "dispatched"  # node left untouched
    assert (sprints / f"{sid}.finalized").exists()  # terminal marker intact
