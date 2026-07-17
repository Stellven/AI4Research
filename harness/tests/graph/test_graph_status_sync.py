#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))


def test_sync_status_cache_creates_missing_inflight_status(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-orphan-graph"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph = {
        "sprint_id": sid,
        "title": "Orphan graph",
        "created_at": "2026-05-25T21:16:39Z",
        "required_gates": ["G1"],
        "nodes": [
            {"id": "N1", "status": "passed", "depends_on": [], "gate": "G1"},
            {"id": "N2", "status": "pending", "depends_on": ["N1"], "gate": "G1"},
        ],
        "node_results": {"N1": {"status": "passed"}},
        "gate_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="graph_mark_N1_passed")

    status_path = sprints / f"{sid}.status.json"
    assert result["ok"] is True
    assert result["created"] is True
    assert result["updated"] is True
    assert result["reason"] == "parent_projection_refreshed"
    assert status_path.exists()

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "active"
    assert status["phase"] == "graph_in_progress"
    assert status["task_graph"] == str(graph_path)
    assert status["active_node"] == "N2"
    assert status["open_nodes"] == ["N2"]


def test_sync_status_cache_repairs_stale_task_graph_status_for_passed_parent(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-stale-task-graph-status"
    graph_path = sprints / f"{sid}.task_graph.json"
    status_path = sprints / f"{sid}.status.json"
    graph = {
        "sprint_id": sid,
        "title": "Completed graph",
        "created_at": "2026-05-28T10:00:00Z",
        "required_gates": ["G1"],
        "nodes": [
            {"id": "N1", "status": "passed", "depends_on": [], "gate": "G1"},
            {"id": "N2", "status": "passed", "depends_on": ["N1"], "gate": "G1"},
        ],
        "node_results": {
            "N1": {"status": "passed"},
            "N2": {"status": "passed"},
        },
        "gate_results": {"G1": {"status": "passed"}},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    stale_status = {
        "sprint_id": sid,
        "status": "passed",
        "phase": "completed",
        "stage": "completed",
        "active_node": None,
        "graph_parent_ready": {"ready": True, "open_nodes": [], "failed_nodes": []},
        "task_graph_status": "active",
        "task_graph": str(graph_path),
        "history": [],
    }
    status_path.write_text(json.dumps(stale_status), encoding="utf-8")

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="graph_parent_ready_passed")

    assert result["ok"] is True
    assert result["updated"] is True
    updated = json.loads(status_path.read_text(encoding="utf-8"))
    assert updated["status"] == "passed"
    assert updated["task_graph_status"] == "passed"
    assert updated["active_node"] is None


def test_sync_status_cache_revokes_passed_status_when_graph_parent_not_ready(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-false-positive-pass"
    graph_path = sprints / f"{sid}.task_graph.json"
    status_path = sprints / f"{sid}.status.json"
    graph = {
        "sprint_id": sid,
        "title": "Blocked graph",
        "required_gates": ["G_PLAN"],
        "nodes": [
            {"id": "S1", "status": "worker_blocked", "depends_on": [], "gate": "G_PLAN"},
            {"id": "S2", "status": "pending", "depends_on": ["S1"], "gate": "G_IMPL"},
        ],
        "node_results": {"S1": {"status": "worker_blocked"}},
        "gate_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    status_path.write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "status": "passed",
                "phase": "completed",
                "stage": "completed",
                "active_node": None,
                "task_graph": str(graph_path),
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    (sprints / f"{sid}.eval.md").write_text("## Verdict\nPASS\n", encoding="utf-8")
    (sprints / f"{sid}.handoff.md").write_text("handoff exists\n", encoding="utf-8")
    (sprints / f"{sid}.closure.json").write_text(
        json.dumps(
            {
                "all_nodes_passed": False,
                "all_required_gates_passed": False,
                "open_nodes": ["S1", "S2"],
                "missing_gates": ["G_PLAN", "G_IMPL"],
            }
        ),
        encoding="utf-8",
    )

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="legacy_pass_guard")

    assert result["ok"] is True
    assert result["reason"] == "parent_reopened"
    updated = json.loads(status_path.read_text(encoding="utf-8"))
    assert updated["status"] == "active"
    assert updated["phase"] == "graph_in_progress"
    assert updated["task_graph_status"] == "active"
    assert updated["active_node"] == "S1"
    assert updated["graph_parent_ready"]["ready"] is False
    assert updated["graph_parent_ready"]["open_nodes"] == ["S1", "S2"]


def test_sync_status_cache_reopens_failed_parent_when_repair_is_active(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-repair-reopen"
    graph_path = sprints / f"{sid}.task_graph.json"
    status_path = sprints / f"{sid}.status.json"
    graph = {
        "sprint_id": sid,
        "title": "Repairing graph",
        "nodes": [
            {
                "id": "S1",
                "status": "reviewing",
                "depends_on": [],
                "repair_attempts": 1,
                "repair_context": {
                    "attempt": 1,
                    "max_attempts": 1,
                    "created_at": "2026-07-01T19:00:44Z",
                },
            },
            {"id": "S2", "status": "pending", "depends_on": ["S1"]},
        ],
        "node_results": {"S1": {"status": "failed", "updated_at": "2026-07-01T19:00:58Z"}},
        "gate_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    status_path.write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "status": "failed",
                "phase": "failed",
                "stage": "failed",
                "active_node": None,
                "task_graph": str(graph_path),
                "task_graph_status": "failed",
                "history": [],
            }
        ),
        encoding="utf-8",
    )

    parent = gs.parent_ready_check(graph)
    assert parent["ready"] is False
    assert parent["failed_nodes"] == []
    assert parent["open_nodes"] == ["S1", "S2"]

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="repair_projection")

    assert result["ok"] is True
    assert result["reason"] == "parent_reopened_for_repair"
    updated = json.loads(status_path.read_text(encoding="utf-8"))
    assert updated["status"] == "active"
    assert updated["phase"] == "graph_in_progress"
    assert updated["task_graph_status"] == "active"
    assert updated["active_node"] == "S1"
    assert updated["graph_parent_ready"]["failed_nodes"] == []
    assert updated["graph_parent_ready"]["open_nodes"] == ["S1", "S2"]


def test_sync_status_cache_projects_human_review_as_terminal_blocker(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-parent-human-review"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph = {
        "sprint_id": sid,
        "title": "Human intervention required",
        "nodes": [
            {"id": "N1", "status": "needs_human_review", "depends_on": []},
            {"id": "N2", "status": "skipped", "depends_on": ["N1"]},
        ],
        "gate_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="human_blocker")

    assert result["ok"] is True
    assert result["reason"] == "parent_needs_human_review"
    parent = result["parent"]
    assert parent["terminal_status"] == "needs_human_review"
    assert parent["human_review_nodes"] == ["N1"]

    status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "needs_human_review"
    assert status["task_graph_status"] == "needs_human_review"
    assert status["active_node"] is None

    closure_path = sprints / f"{sid}.closure.json"
    gs._save_closure_projection(closure_path, graph, {"graph_ref": str(graph_path)})
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    assert closure["status"] == "needs_human_review"
    assert closure["human_review_nodes"] == ["N1"]


def test_sync_status_cache_fails_mixed_failed_and_human_terminal_graph(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-mixed-terminal-blockers"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph = {
        "sprint_id": sid,
        "title": "No runnable work remains",
        "nodes": [
            {"id": "N1", "status": "failed", "depends_on": []},
            {"id": "N2", "status": "needs_human_review", "depends_on": []},
            {"id": "N3", "status": "skipped", "depends_on": ["N1", "N2"]},
        ],
        "gate_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="mixed_blockers")

    assert result["ok"] is True
    assert result["reason"] == "parent_failed"
    assert result["parent"]["terminal_status"] == "failed"
    assert result["parent"]["failed_nodes"] == ["N1"]
    assert result["parent"]["human_review_nodes"] == ["N2"]

    status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["task_graph_status"] == "failed"
    assert status["active_node"] is None


def test_sync_status_cache_reopens_parent_after_explicit_human_resume(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-parent-human-resumed"
    graph_path = sprints / f"{sid}.task_graph.json"
    status_path = sprints / f"{sid}.status.json"
    graph = {
        "sprint_id": sid,
        "title": "Human resumed node",
        "nodes": [{"id": "N1", "status": "pending", "depends_on": []}],
        "gate_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    status_path.write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "status": "needs_human_review",
                "phase": "needs_human",
                "stage": "needs_human_review",
                "active_node": None,
                "task_graph": str(graph_path),
                "task_graph_status": "needs_human_review",
                "history": [],
            }
        ),
        encoding="utf-8",
    )

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="human_resumed")

    assert result["ok"] is True
    assert result["reason"] == "parent_reopened_after_human_resume"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "active"
    assert status["task_graph_status"] == "active"
    assert status["active_node"] == "N1"


def test_sync_status_cache_replaces_stale_failed_parent_with_human_review(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    sid = "sprint-test-stale-failed-now-human"
    graph_path = sprints / f"{sid}.task_graph.json"
    status_path = sprints / f"{sid}.status.json"
    graph = {
        "sprint_id": sid,
        "title": "Repair exhausted into human review",
        "nodes": [{"id": "N1", "status": "needs_human_review", "depends_on": []}],
        "gate_results": {},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    status_path.write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "status": "failed",
                "phase": "failed",
                "stage": "failed",
                "active_node": None,
                "task_graph": str(graph_path),
                "task_graph_status": "failed",
                "history": [],
            }
        ),
        encoding="utf-8",
    )

    result = gs.sync_status_cache_from_graph(graph, graph_path, actor="test", event="human_escalated")

    assert result["ok"] is True
    assert result["reason"] == "parent_needs_human_review"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "needs_human_review"
    assert status["task_graph_status"] == "needs_human_review"
    assert status["active_node"] is None


def test_parent_ready_check_self_heals_stale_blocked_gate(tmp_path, monkeypatch):
    import graph_scheduler as gs

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)

    graph = {
        "sprint_id": "sprint-test-stale-gate",
        "required_gates": ["G_PASS"],
        "nodes": [
            {"id": "N1", "status": "passed", "gate": "G_PASS", "depends_on": []},
            {"id": "N2", "status": "passed", "gate": "G_PASS", "depends_on": ["N1"]},
        ],
        "gate_results": {
            "G_PASS": {
                "status": "blocked",
                "node": "N1",
                "reason": "waiting_for_shared_gate_nodes",
                "open_nodes": ["N1"],
            }
        },
    }

    result = gs.parent_ready_check(graph)

    assert result["ready"] is True
    assert result["missing_gates"] == []
    assert graph["gate_results"]["G_PASS"]["status"] == "passed"
    assert graph["gate_results"]["G_PASS"]["reason"] == "parent_ready_self_heal"


# ---------------------------------------------------------------------------
# O1_child_sprint_activation acceptance — epic-level dependency gates
# ---------------------------------------------------------------------------


def _epic_graph(s02="passed", s03="pending", s04="pending", s05="pending"):
    """Build a minimal S01→S02→{S03,S04}→S05 epic graph for tests."""
    return {
        "schema_version": "solar.epic.task_graph.v1",
        "epic_id": "epic-test",
        "nodes": [
            {"id": "S01_requirements", "status": "passed", "depends_on": []},
            {"id": "S02_architecture", "status": s02, "depends_on": ["S01_requirements"]},
            {"id": "S03_core_runtime", "status": s03, "depends_on": ["S02_architecture"]},
            {"id": "S04_orchestration_ui", "status": s04, "depends_on": ["S02_architecture"]},
            {
                "id": "S05_verification_release",
                "status": s05,
                "depends_on": ["S03_core_runtime", "S04_orchestration_ui"],
            },
        ],
    }


def test_epic_s02_passed_activates_s03_and_s04_only():
    """Acceptance: S02 passed activates S03/S04 only (S05 stays blocked)."""
    import graph_scheduler as gs

    result = gs.epic_child_activation(_epic_graph())
    ready_ids = sorted(r["child_id"] for r in result["ready"])
    blocked_ids = sorted(b["child_id"] for b in result["blocked"])
    assert ready_ids == ["S03_core_runtime", "S04_orchestration_ui"], ready_ids
    assert blocked_ids == ["S05_verification_release"], blocked_ids
    unmet_for_s05 = next(b for b in result["blocked"] if b["child_id"] == "S05_verification_release")["unmet"]
    assert sorted(unmet_for_s05) == ["S03_core_runtime", "S04_orchestration_ui"]
    assert result["can_close"] is False
    assert result["epic_done"] is False
    # S01/S02 already passed → counted as done
    assert "S01_requirements" in result["done"] and "S02_architecture" in result["done"]


def test_epic_s05_requires_both_s03_and_s04():
    """Acceptance: S05 waits for S03 AND S04, not either one alone."""
    import graph_scheduler as gs

    # Case A: only S03 passed → S05 still blocked, S04 ready
    result_a = gs.epic_child_activation(_epic_graph(s03="passed"))
    ready_a = sorted(r["child_id"] for r in result_a["ready"])
    assert ready_a == ["S04_orchestration_ui"], ready_a
    blocked_a = {b["child_id"]: b["unmet"] for b in result_a["blocked"]}
    assert "S05_verification_release" in blocked_a
    assert blocked_a["S05_verification_release"] == ["S04_orchestration_ui"]

    # Case B: only S04 passed → S05 still blocked, S03 ready
    result_b = gs.epic_child_activation(_epic_graph(s04="passed"))
    ready_b = sorted(r["child_id"] for r in result_b["ready"])
    assert ready_b == ["S03_core_runtime"], ready_b
    blocked_b = {b["child_id"]: b["unmet"] for b in result_b["blocked"]}
    assert blocked_b["S05_verification_release"] == ["S03_core_runtime"]

    # Case C: both passed → S05 ready, nothing blocked
    result_c = gs.epic_child_activation(_epic_graph(s03="passed", s04="passed"))
    ready_c = sorted(r["child_id"] for r in result_c["ready"])
    assert ready_c == ["S05_verification_release"], ready_c
    assert result_c["blocked"] == []
    # epic is not yet closed because S05 hasn't passed
    assert result_c["can_close"] is False


def test_epic_parent_cannot_close_while_any_child_open_or_failed():
    """Acceptance: parent epic cannot close early."""
    import graph_scheduler as gs

    # While any child still active/pending, can_close must be False
    mid = gs.epic_child_activation(_epic_graph(s03="reviewing", s04="passed"))
    assert mid["can_close"] is False
    assert mid["epic_done"] is False

    # Only when every child has reached terminal PASSED state can the epic close
    final = gs.epic_child_activation(
        _epic_graph(s03="passed", s04="passed", s05="passed")
    )
    assert final["can_close"] is True
    assert final["epic_done"] is True
    assert final["blocked"] == [] and final["ready"] == []

    # A failed child blocks closure even if everything else is done
    bust = gs.epic_child_activation(
        _epic_graph(s03="passed", s04="passed", s05="failed")
    )
    assert bust["can_close"] is False
    assert bust["epic_done"] is False
    assert "S05_verification_release" in bust["failed"]


def test_epic_activation_on_live_github_intelligence_epic():
    """Smoke: function runs against the real epic graph file shape."""
    import graph_scheduler as gs

    epic_path = (
        Path(__file__).resolve().parents[2]
        / "sprints"
        / "epic-20260524-p0-ai-influence-github-project-intelligence-system-upgrade.task_graph.json"
    )
    if not epic_path.exists():
        return  # do not hard-fail when run outside the live repo
    graph = json.loads(epic_path.read_text(encoding="utf-8"))
    result = gs.epic_child_activation(graph)
    assert result["ok"] is True
    assert result["schema_version"] == "solar.epic.task_graph.v1"
    # the live graph must always contain S05 and it must never be in `done`
    # until both S03 and S04 are passed
    s05_ids = {c for c in result["done"] if c == "S05_verification_release"}
    if "S03_core_runtime" not in result["done"] or "S04_orchestration_ui" not in result["done"]:
        assert not s05_ids, "S05 cannot be done before S03+S04"
