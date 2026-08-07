#!/usr/bin/env python3
"""P3 live run 4 — the frozen parent projection (fixture
p3-sprint-20260708-145523-...-projection-wedge-20260708T152500Z).

Run 4 was a perfect graph run: D1-D6 all passed, closure closed, 14 route
records, verdicts x6, zero reopens — and the wrapper still timed out (exit
124) because sprint status.json froze at status=active/open_nodes=["D6"],
last written 3s BEFORE D6 passed. parent_ready_check on the frozen graph
returns ready:true and sync_status_cache_from_graph flips the projection
instantly when invoked — the machinery works; NOTHING INVOKED IT.

Root cause: two reconcile loops race to consume the final node's eval. The
multi-task auto-advance loop syncs the projection but only `if reconciled`;
the coordinator's dispatch-ready tick reconciles but never synced. When the
coordinator tick wins the race (run 4: it consumed D6's sidecar), the other
loop's reconcile comes back empty, the sync is skipped forever, and the
coordinator keeps running the ACTIVE handler (handle_reviewing — the branch
that advances the sprint — only runs at status=reviewing): a projection
deadlock. P2 passed because the syncing loop happened to win that race.

Fix: projection convergence must not depend on WHICH loop reconciles —
dispatch_ready syncs the parent projection every non-dry tick (idempotent:
already_synced / parent_not_ready short-circuit), and the multi-task loop's
sync is un-gated from `if reconciled`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import workflow_contract as wc  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"
SID = "p3-proj-conv"


@pytest.fixture()
def frozen_sprint(tmp_path, monkeypatch):
    """The run-4 shape: contracted graph fully passed, status.json still active."""
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "WORKFLOWS_DIR", WORKFLOWS_DIR, raising=False)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    contract = wc.find_contract("research.deepdive.rsi_demo", WORKFLOWS_DIR)
    graph = wc.instantiate(contract, {
        "sprint_id": SID, "sid": SID, "workspace_root": str(tmp_path / "ws"),
    })
    for node in graph["nodes"]:
        node["status"] = "passed"
    graph_path = sprints / f"{SID}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    status_path = sprints / f"{SID}.status.json"
    status_path.write_text(json.dumps({
        "sprint_id": SID,
        "status": "active",
        "stage": "graph_in_progress",
        "active_node": "D6",
        "open_nodes": ["D6"],
        "task_graph_status": "active",
    }), encoding="utf-8")
    return graph_path, status_path


def test_dispatch_tick_converges_the_parent_projection(frozen_sprint):
    graph_path, status_path = frozen_sprint
    result = gnd.dispatch_ready(str(graph_path))
    assert result.get("ok"), result
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status.get("status") == "passed", (
        "dispatch tick left the parent projection frozen at "
        f"{status.get('status')!r} with a fully-passed graph (run-4 wedge)"
    )
    assert status.get("stage") == "completed"
    assert not status.get("active_node")


def test_projection_sync_is_idempotent_across_ticks(frozen_sprint):
    graph_path, status_path = frozen_sprint
    gnd.dispatch_ready(str(graph_path))
    first = json.loads(status_path.read_text(encoding="utf-8"))
    gnd.dispatch_ready(str(graph_path))
    second = json.loads(status_path.read_text(encoding="utf-8"))
    assert second.get("status") == "passed"
    assert second.get("stage") == first.get("stage") == "completed"


def test_inflight_graph_projection_stays_active(frozen_sprint):
    """Parity: a graph with open nodes must NOT be flipped by the tick sync."""
    graph_path, status_path = frozen_sprint
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    next(n for n in graph["nodes"] if n["id"] == "D6")["status"] = "reviewing"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    gnd.dispatch_ready(str(graph_path))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status.get("status") == "active"
