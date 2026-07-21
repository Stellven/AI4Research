#!/usr/bin/env python3
"""test_parent_ready_closeout.py — N3 tests: parent_ready_check closeout.

Tests verify:
  - parent sprint status is passed ONLY when parent_ready_check returns ready
  - _mark_parent_sprint_passed_if_ready is the single closeout path
  - node_verdict correctly delegates to parent_ready_check
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add harness lib to path
HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_harness(tmp_path, monkeypatch):
    """Create a minimal harness directory structure."""
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    run_dir = tmp_path / "run" / "queue"
    run_dir.mkdir(parents=True)

    sid = "test-parent-ready"
    graph = {
        "sprint_id": sid,
        "required_gates": ["gate-1"],
        "nodes": [
            {
                "id": "N1",
                "goal": "Test",
                "depends_on": [],
                "write_scope": ["/tmp/test"],
                "acceptance": ["test"],
                "status": "reviewing",
                "gate": "gate-1",
            },
        ],
        "node_results": {},
        "gate_results": {},
    }
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph) + "\n")

    # Create status file
    status = {
        "id": sid,
        "status": "active",
        "phase": "graph_dispatch_active",
    }
    (sprints / f"{sid}.status.json").write_text(json.dumps(status) + "\n")

    monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
    import graph_node_dispatcher as gnd
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)

    return tmp_path, sprints, sid, graph


# ---------------------------------------------------------------------------
# Test: parent sprint passed only when parent_ready_check is ready
# ---------------------------------------------------------------------------

class TestParentReadyCloseout:
    """D7: parent sprint is passed only via parent_ready_check."""

    def test_parent_not_passed_when_nodes_still_open(self, tmp_harness):
        """_mark_parent_sprint_passed_if_ready does NOT pass when nodes are open."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        # N1 is still reviewing (open), so parent_ready_check returns ready=False
        parent = {"ready": False, "node_count": 1, "open_nodes": ["N1"]}
        result = gnd._mark_parent_sprint_passed_if_ready(sid, parent, dry_run=False)
        assert result is False

        # Verify status was NOT changed to passed
        status = json.loads((sprints / f"{sid}.status.json").read_text())
        assert status["status"] != "passed"

    def test_parent_passed_when_all_nodes_done(self, tmp_harness):
        """_mark_parent_sprint_passed_if_ready DOES pass when ready=True."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        # All nodes passed
        parent = {
            "ready": True,
            "node_count": 1,
            "open_nodes": [],
            "required_gates": ["gate-1"],
            "missing_gates": [],
        }
        result = gnd._mark_parent_sprint_passed_if_ready(sid, parent, dry_run=False)
        assert result is True

        # Verify status was changed to passed
        status = json.loads((sprints / f"{sid}.status.json").read_text())
        assert status["status"] == "passed"
        assert status["phase"] == "completed"
        assert "graph_parent_ready_passed" in str(status.get("history", []))

    def test_parent_not_passed_in_dry_run(self, tmp_harness):
        """Dry run never marks parent as passed."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        parent = {"ready": True, "node_count": 1, "open_nodes": []}
        result = gnd._mark_parent_sprint_passed_if_ready(sid, parent, dry_run=True)
        assert result is False

    def test_parent_not_passed_when_gates_missing(self, tmp_harness):
        """Parent not passed when required gates haven't all passed."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        parent = {
            "ready": False,
            "node_count": 1,
            "open_nodes": [],
            "required_gates": ["gate-1"],
            "missing_gates": ["gate-1"],
        }
        result = gnd._mark_parent_sprint_passed_if_ready(sid, parent, dry_run=False)
        assert result is False

    def test_node_verdict_delegates_to_parent_ready_check(self, tmp_harness, monkeypatch):
        """node_verdict calls _mark_parent_sprint_passed_if_ready."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        # Set N1 as passed in node_results
        graph["node_results"]["N1"] = {"status": "passed"}
        graph["gate_results"]["gate-1"] = {"status": "passed", "node": "N1"}
        graph["nodes"][0]["status"] = "reviewing"
        graph["nodes"][0]["eval_assigned_to"] = "eval:0.3"
        graph["nodes"][0]["eval_dispatch_id"] = "eval-dispatch-123"

        # Mock all the things
        monkeypatch.setattr(gnd, "load_graph", lambda p: graph)
        monkeypatch.setattr(gnd, "save_graph", lambda p, g: None)

        from graph_scheduler import mark_node_result
        monkeypatch.setattr(gnd, "mark_node_result", mark_node_result)

        monkeypatch.setattr(gnd, "release_lease", lambda *a, **kw: {"released": True})
        monkeypatch.setattr(gnd, "dispatch_ready", lambda *a, **kw: {"ok": True})

        parent_passed_calls = []
        def mock_mark_parent(sid, parent, dry_run):
            parent_passed_calls.append({"sid": sid, "parent": parent, "dry_run": dry_run})
            return False
        monkeypatch.setattr(gnd, "_mark_parent_sprint_passed_if_ready", mock_mark_parent)

        eval_json_path = str(sprints / f"{sid}.N1-eval.json")
        Path(eval_json_path).write_text(json.dumps({"verdict": "PASS"}) + "\n", encoding="utf-8")
        result = gnd.node_verdict(
            str(sprints / f"{sid}.task_graph.json"),
            "N1",
            "pass",
            eval_json=eval_json_path,
            dry_run=False,
            dispatch_downstream=False,
        )

        assert result["ok"] is True
        assert result["status"] == "passed"
        # Verify _mark_parent_sprint_passed_if_ready was called
        assert len(parent_passed_calls) == 1
        assert parent_passed_calls[0]["dry_run"] is False

    def test_events_appended_on_parent_pass(self, tmp_harness):
        """Events file records graph_parent_ready_passed event."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        parent = {
            "ready": True,
            "node_count": 1,
            "open_nodes": [],
            "required_gates": ["gate-1"],
        }
        result = gnd._mark_parent_sprint_passed_if_ready(sid, parent, dry_run=False)
        assert result is True

        events_file = sprints / f"{sid}.events.jsonl"
        if events_file.exists():
            lines = events_file.read_text().strip().splitlines()
            assert any("graph_parent_ready_passed" in line for line in lines)


class TestParentReadyCheckIntegration:
    """Integration test: graph_scheduler.parent_ready_check is the source of truth."""

    def test_shared_gate_does_not_pass_until_all_gate_nodes_pass(self):
        from graph_scheduler import mark_node_result

        graph = {
            "sprint_id": "shared-gate",
            "required_gates": ["gate-shared"],
            "nodes": [
                {"id": "N1", "depends_on": [], "status": "reviewing", "gate": "gate-shared"},
                {"id": "N2", "depends_on": [], "status": "failed", "gate": "gate-shared"},
            ],
            "node_results": {"N2": {"status": "failed", "updated_at": "2026-05-19T00:00:00Z"}},
            "gate_results": {},
        }

        parent = mark_node_result(graph, "N1", "passed", gate_status="passed")

        assert parent["ready"] is False
        assert graph["gate_results"]["gate-shared"]["status"] == "blocked"
        assert graph["gate_results"]["gate-shared"]["open_nodes"] == ["N2"]

    def test_standard_graph_auto_assigns_default_gates_for_closeout(self):
        from graph_scheduler import mark_node_result, parent_ready_check

        graph = {
            "sprint_id": "standard-auto-gates",
            "dag_variant": "standard",
            "required_gates": ["G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"],
            "nodes": [
                {"id": "S1", "depends_on": [], "status": "reviewing"},
                {"id": "S2", "depends_on": ["S1"], "status": "pending"},
                {"id": "S3", "depends_on": ["S2"], "status": "pending"},
                {"id": "S4", "depends_on": ["S3"], "status": "pending"},
                {"id": "S5", "depends_on": ["S4"], "status": "pending"},
            ],
            "node_results": {},
            "gate_results": {},
        }

        mark_node_result(graph, "S1", "passed")
        mark_node_result(graph, "S2", "passed")
        mark_node_result(graph, "S3", "passed")
        mark_node_result(graph, "S4", "passed")
        mark_node_result(graph, "S5", "passed")

        by_id = {node["id"]: node for node in graph["nodes"]}
        assert by_id["S1"]["gate"] == "G_PLAN"
        assert by_id["S2"]["gate"] == "G_IMPL"
        assert by_id["S3"]["gate"] == "G_VERIFY"
        assert by_id["S4"]["gate"] == "G_REVIEW"
        assert by_id["S5"]["gate"] == "G_REVIEW"
        assert graph["gate_results"]["G_REVIEW"]["status"] == "passed"
        assert parent_ready_check(graph)["ready"] is True

    def test_all_passed_means_ready(self, tmp_harness):
        """When all nodes and gates pass, parent_ready_check returns ready."""
        from graph_scheduler import parent_ready_check

        _, sprints, sid, graph = tmp_harness

        # Mark all nodes as passed
        graph["nodes"][0]["status"] = "passed"
        graph["node_results"] = {"N1": {"status": "passed"}}
        graph["gate_results"] = {"gate-1": {"status": "passed", "node": "N1"}}

        result = parent_ready_check(graph)
        assert result["ready"] is True
        assert result["open_nodes"] == []

    def test_open_nodes_means_not_ready(self, tmp_harness):
        """When nodes are still open, parent_ready_check returns not ready."""
        from graph_scheduler import parent_ready_check

        _, sprints, sid, graph = tmp_harness

        result = parent_ready_check(graph)
        assert result["ready"] is False
        assert "N1" in result["open_nodes"]

    def test_failed_node_means_not_ready(self, tmp_harness):
        """When a node is failed, parent_ready_check returns not ready."""
        from graph_scheduler import parent_ready_check

        _, sprints, sid, graph = tmp_harness

        graph["nodes"][0]["status"] = "failed"
        graph["node_results"] = {"N1": {"status": "failed"}}

        result = parent_ready_check(graph)
        assert result["ready"] is False
        assert "N1" in result["failed_nodes"]

    def test_newer_inline_passed_overrides_stale_node_result_reviewing(self, tmp_harness):
        """A stale node_results row must not keep a passed node open forever."""
        from graph_scheduler import node_status, parent_ready_check

        _, sprints, sid, graph = tmp_harness

        graph["nodes"][0]["status"] = "passed"
        graph["nodes"][0]["updated_at"] = "2026-05-14T07:24:00Z"
        graph["node_results"] = {
            "N1": {"status": "reviewing", "updated_at": "2026-05-14T07:23:00Z"}
        }
        graph["gate_results"] = {"gate-1": {"status": "passed", "node": "N1"}}

        assert node_status(graph, "N1") == "passed"
        result = parent_ready_check(graph)
        assert result["ready"] is True
        assert result["open_nodes"] == []

    def test_passed_gate_closes_stale_reviewing_node(self, tmp_harness):
        """A passed required gate is the durable closeout signal for a node."""
        from graph_scheduler import node_status, parent_ready_check

        _, sprints, sid, graph = tmp_harness

        graph["nodes"][0]["status"] = "reviewing"
        graph["nodes"][0]["updated_at"] = "2026-05-14T07:24:00Z"
        graph["node_results"] = {
            "N1": {"status": "reviewing", "updated_at": "2026-05-14T07:24:00Z"}
        }
        graph["gate_results"] = {"gate-1": {"status": "passed", "node": "N1"}}

        assert node_status(graph, "N1") == "passed"
        result = parent_ready_check(graph)
        assert result["ready"] is True
        assert result["open_nodes"] == []

    def test_doctor_repairs_stale_node_result_reviewing(self, tmp_harness):
        """graph doctor repairs the exact stale-reviewing dead-end."""
        from graph_scheduler import doctor_graph, node_status, parent_ready_check

        _, sprints, sid, graph = tmp_harness

        graph["nodes"][0]["status"] = "passed"
        graph["nodes"][0]["updated_at"] = "2026-05-14T07:24:00Z"
        graph["node_results"] = {
            "N1": {"status": "reviewing", "updated_at": "2026-05-14T07:23:00Z"}
        }
        graph["gate_results"] = {"gate-1": {"status": "passed", "node": "N1"}}

        result = doctor_graph(graph, repair=True)
        assert result["repaired"] is True
        assert graph["node_results"]["N1"]["status"] == "passed"
        assert node_status(graph, "N1") == "passed"
        assert parent_ready_check(graph)["ready"] is True


class TestGraphStatusProjection:
    """Regression tests for task_graph -> status.json closeout drift."""

    def test_graph_scheduler_mark_syncs_legacy_status_when_parent_ready(self, tmp_path):
        sid = "projection-closeout"
        sprints = tmp_path / "sprints"
        sprints.mkdir()
        graph_path = sprints / f"{sid}.task_graph.json"
        status_path = sprints / f"{sid}.status.json"
        graph = {
            "sprint_id": sid,
            "required_gates": [],
            "nodes": [
                {"id": "N1", "depends_on": [], "status": "passed", "updated_at": "2026-05-22T00:00:00Z"},
                {"id": "N2", "depends_on": ["N1"], "status": "reviewing"},
            ],
            "node_results": {"N1": {"status": "passed", "updated_at": "2026-05-22T00:00:00Z"}},
            "gate_results": {},
        }
        graph_path.write_text(json.dumps(graph) + "\n", encoding="utf-8")
        status_path.write_text(json.dumps({
            "id": sid,
            "sprint_id": sid,
            "status": "dispatched",
            "stage": "N1",
            "active_node": "N1",
            "round": 0,
            "history": [],
        }) + "\n", encoding="utf-8")

        script = Path(__file__).resolve().parent.parent.parent / "lib" / "graph_scheduler.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "mark",
                "--graph",
                str(graph_path),
                "--node",
                "N2",
                "--status",
                "passed",
                "--in-place",
            ],
            cwd=str(tmp_path),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        payload = json.loads(proc.stdout)
        assert payload["ready"] is True
        assert payload["status_sync"]["updated"] is True
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["status"] == "passed"
        assert status["phase"] == "completed"
        assert status["stage"] == "completed"
        assert status["active_node"] is None
        assert status["graph_parent_ready"]["ready"] is True

    def test_epic_child_status_falls_back_to_passed_child_graph(self, tmp_path, monkeypatch):
        import epic_decomposer as epic

        sid = "child-graph-passed-status-stale"
        sprints = tmp_path / "sprints"
        sprints.mkdir()
        monkeypatch.setattr(epic, "SPRINTS_DIR", sprints)

        (sprints / f"{sid}.status.json").write_text(json.dumps({
            "id": sid,
            "sprint_id": sid,
            "status": "dispatched",
            "active_node": "N1",
            "round": 0,
            "history": [],
        }) + "\n", encoding="utf-8")
        (sprints / f"{sid}.task_graph.json").write_text(json.dumps({
            "sprint_id": sid,
            "required_gates": [],
            "nodes": [
                {"id": "N1", "depends_on": [], "status": "passed"},
            ],
            "node_results": {"N1": {"status": "passed"}},
            "gate_results": {},
        }) + "\n", encoding="utf-8")

        status = epic.child_status(sid)

        assert status["status"] == "passed"
        assert status["graph_parent_ready"]["ready"] is True
        assert epic.child_passed(sid) is True


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
