"""G4 UI-rung run 3 — builder dispatch starvation must escalate, never loop.

Evidence: p5-g4-ui-rung-20260710T204856Z (sprint ...-2948f828). S2's repair
re-dispatch entered a perfect ping-pong: the dispatcher assigned the node
(~1s), the reconcile reset it to pending 10-12s later
(`stale_submit_ack_without_live_lease` — submit recorded, no live lease
because the only builder operator sat in its 900s contract-closeout
cooldown), and the dispatcher assigned again. 122 ledger rows, 632 seconds
with zero meaningful progress before the operator stopped the run — the
exact invisible-infinite-retry class the campaign exists to kill.

The EVAL side already has the cure (Run D fix): count consecutive
capacity-class dispatch failures and, past a bounded cap, escalate to a
durable `needs_human_review` instead of retrying silently forever. The
BUILDER dispatch path had no counter at all.

Fix under test: _account_dispatch_retry — every reconcile reset that stamps
a dispatch_retry_reason increments the node's dispatch_failure_streak; at
GRAPH_NODE_DISPATCH_MAX_FAILURES (default 8, env-tunable, 0 = legacy
unlimited) the node escalates to durable needs_human_review (direct write,
ledger transition, event, next_action) exactly like the eval escalation.
The streak clears on real progress (submit ack observed / handoff
reconciled), so slow-but-alive dispatch is never punished.
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

import graph_scheduler as gs  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    harness = tmp_path / "harness"
    (harness / "sprints" / "graph-acks").mkdir(parents=True)
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    return sprints, harness


def _graph(sid: str, node: dict) -> dict:
    return {
        "sprint_id": sid,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1",
        "plan_certificate": {"algo": "sha256", "hash": "test"},
        "plan_compile_required": True,
        "nodes": [node],
        "node_results": {node["id"]: {"status": str(node.get("status") or "")}},
        "gate_results": {},
    }


def _assigned_node(streak: int = 0) -> dict:
    node = {
        "id": "S2",
        "status": "assigned",
        "depends_on": [],
        "assigned_to": "operator-pool:builder.0",
        "dispatch_id": "graph-S2-dispatch-xyz",
    }
    if streak:
        node["dispatch_failure_streak"] = streak
    return node


def _write(sprints: Path, sid: str, graph: dict) -> str:
    path = sprints / f"{sid}.task_graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    return str(path)


class TestDispatchRetryAccounting:
    def test_reconcile_reset_increments_the_streak(self, sandbox):
        sprints, _ = sandbox
        sid = "sprint-g4r3-streak"
        node = _assigned_node()
        graph = _graph(sid, node)
        graph_path = _write(sprints, sid, graph)

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {i["node"]: i for i in repaired}
        assert entries["S2"]["reason"] == "stale_submit_ack_without_live_lease", repaired
        assert node.get("dispatch_failure_streak") == 1, node
        assert node.get("last_dispatch_failure_reason") == "stale_submit_ack_without_live_lease"

    def test_threshold_escalates_to_durable_needs_human_review(self, sandbox):
        """The run-3 loop replay: the streak is one below the cap; the next
        reset must escalate instead of returning to pending — killing the
        assign/reset ping-pong."""
        sprints, _ = sandbox
        sid = "sprint-g4r3-escalate"
        node = _assigned_node(streak=gnd.GRAPH_NODE_DISPATCH_MAX_FAILURES - 1)
        graph = _graph(sid, node)
        graph_path = _write(sprints, sid, graph)

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        assert gs.node_status(graph, "S2") == "needs_human_review", (
            repaired, graph.get("node_results"))
        assert "dispatch" in str(node.get("next_action") or "").lower() or node.get("next_action"), node
        ledger = (sprints / f"{sid}.gate-ledger.jsonl").read_text(encoding="utf-8")
        assert "needs_human_review" in ledger

    def test_escalated_node_is_not_reassigned(self, sandbox):
        """Durability: further reconciles leave the escalated node alone."""
        sprints, _ = sandbox
        sid = "sprint-g4r3-durable"
        node = _assigned_node(streak=gnd.GRAPH_NODE_DISPATCH_MAX_FAILURES - 1)
        graph = _graph(sid, node)
        graph_path = _write(sprints, sid, graph)
        gnd._reconcile_existing_dispatches(graph, graph_path)
        assert gs.node_status(graph, "S2") == "needs_human_review"

        again = gnd._reconcile_existing_dispatches(graph, graph_path)

        assert gs.node_status(graph, "S2") == "needs_human_review", again

    def test_streak_clears_on_live_submit_ack(self, sandbox):
        """Real progress resets the counter: a live ack marks the node
        dispatched and clears the streak (slow dispatch is never punished)."""
        sprints, harness = sandbox
        sid = "sprint-g4r3-clear"
        node = _assigned_node(streak=3)
        graph = _graph(sid, node)
        graph_path = _write(sprints, sid, graph)
        ack = harness / "sprints" / "graph-acks" / f"{sid}.S2-submit-ack.json"
        ack.write_text(json.dumps({
            "dispatch_id": "graph-S2-dispatch-xyz",
            "submitted_at": gnd._utc_now(),
        }), encoding="utf-8")

        gnd._reconcile_existing_dispatches(graph, graph_path)

        assert gs.node_status(graph, "S2") == "dispatched", graph.get("node_results")
        assert int(node.get("dispatch_failure_streak") or 0) == 0, node

    def test_zero_cap_keeps_legacy_unlimited_retry(self, sandbox, monkeypatch):
        sprints, _ = sandbox
        monkeypatch.setattr(gnd, "GRAPH_NODE_DISPATCH_MAX_FAILURES", 0)
        sid = "sprint-g4r3-legacy"
        node = _assigned_node(streak=50)
        graph = _graph(sid, node)
        graph_path = _write(sprints, sid, graph)

        gnd._reconcile_existing_dispatches(graph, graph_path)

        assert gs.node_status(graph, "S2") != "needs_human_review"
        assert int(node.get("dispatch_failure_streak") or 0) == 51
