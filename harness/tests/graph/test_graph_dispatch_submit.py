#!/usr/bin/env python3
"""test_graph_dispatch_submit.py — N3 tests: pane submit reliability.

Tests verify:
  - send_to_pane uses literal input (-l flag) and explicit submit timing
  - dispatch creates ack/submit evidence
  - submit failure releases lease and requeues node
  - eval dispatch failure also releases lease and clears assignment
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Add harness lib to path
HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_harness(tmp_path, monkeypatch):
    """Create a minimal harness directory structure for testing."""
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    run_dir = tmp_path / "run" / "queue"
    run_dir.mkdir(parents=True)
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()

    # Create a minimal task_graph
    sid = "test-graph-submit"
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": "N1",
                "goal": "Test goal",
                "depends_on": [],
                "write_scope": ["/tmp/test"],
                "required_skills": ["bash"],
                "acceptance": ["test acceptance"],
                "status": "pending",
            },
            {
                "id": "N2",
                "goal": "Test goal 2",
                "depends_on": ["N1"],
                "write_scope": ["/tmp/test2"],
                "required_skills": ["bash"],
                "acceptance": ["test acceptance 2"],
                "status": "pending",
            },
        ],
        "node_results": {},
        "gate_results": {},
    }
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph) + "\n")

    monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
    import graph_node_dispatcher
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(graph_node_dispatcher, "HARNESS_DIR", tmp_path)
    import graph_scheduler
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", sprints)

    return tmp_path, sprints, sid, graph


# ---------------------------------------------------------------------------
# Test: send_to_pane uses literal input and explicit submit
# ---------------------------------------------------------------------------

class TestSendToPaneLiteral:
    """send_to_pane uses literal input and verifies Claude actually started."""

    def test_uses_literal_flag(self, tmp_harness, monkeypatch):
        """_send_to_pane sends command with -l flag (literal mode)."""
        calls_log = []

        def mock_run(cmd, **kwargs):
            calls_log.append(cmd)
            if isinstance(cmd, list) and cmd[:2] == ["tmux", "capture-pane"]:
                return MagicMock(returncode=0, stdout="test-dispatch.md\n⏺ Reading 2 files")
            return MagicMock(returncode=0)

        import graph_node_dispatcher as gnd
        monkeypatch.setattr("subprocess.run", mock_run)
        import time as time_mod
        monkeypatch.setattr(time_mod, "sleep", lambda x: None)

        result = gnd._send_to_pane("test:0.1", Path("/tmp/test-dispatch.md"), dry_run=False)
        assert result is True

        # Find the literal send call
        literal_calls = [c for c in calls_log if "-l" in c]
        assert len(literal_calls) > 0, "Expected -l (literal) flag in tmux send-keys"

    def test_sprint_level_handoff_does_not_reconcile_before_dependencies_pass(self, tmp_harness):
        """A sprint-level handoff must not advance a node before its deps pass."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        graph["required_gates"] = ["gate-shared"]
        graph["nodes"] = [
            {
                "id": "N9",
                "goal": "Render planning.html",
                "depends_on": ["N8"],
                "write_scope": [f"sprints/{sid}.planning.html"],
                "acceptance": ["planning.html exists"],
                "status": "pending",
                "gate": "gate-shared",
            },
            {
                "id": "N10",
                "goal": "Write sprint handoff",
                "depends_on": ["N8"],
                "write_scope": [f"sprints/{sid}.handoff.md"],
                "acceptance": ["handoff exists"],
                "status": "pending",
                "gate": "gate-shared",
            },
        ]
        (sprints / f"{sid}.handoff.md").write_text("# Sprint handoff\n", encoding="utf-8")

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert repaired == [
            {
                "node": "N10",
                "status": "pending",
                "reason": "handoff_reconcile_blocked_by_dependencies",
                "handoff": str(sprints / f"{sid}.handoff.md"),
                "blocked_by": ["N8"],
            }
        ]
        assert graph["nodes"][0]["status"] == "pending"
        assert graph["nodes"][1]["status"] == "pending"

    def test_sprint_level_handoff_reconciles_owner_node_after_dependencies_pass(self, tmp_harness):
        """A sprint-level handoff may advance its owner node once deps passed."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        graph["required_gates"] = ["gate-shared"]
        graph["nodes"] = [
            {
                "id": "N8",
                "goal": "Prerequisite",
                "depends_on": [],
                "write_scope": [f"sprints/{sid}.prep.md"],
                "acceptance": ["prep exists"],
                "status": "passed",
                "gate": "gate-shared",
            },
            {
                "id": "N9",
                "goal": "Render planning.html",
                "depends_on": ["N8"],
                "write_scope": [f"sprints/{sid}.planning.html"],
                "acceptance": ["planning.html exists"],
                "status": "pending",
                "gate": "gate-shared",
            },
            {
                "id": "N10",
                "goal": "Write sprint handoff",
                "depends_on": ["N8"],
                "write_scope": [f"sprints/{sid}.handoff.md"],
                "acceptance": ["handoff exists"],
                "status": "pending",
                "gate": "gate-shared",
            },
        ]
        graph["node_results"] = {"N8": {"status": "passed"}}
        (sprints / f"{sid}.handoff.md").write_text("# Sprint handoff\n", encoding="utf-8")

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert repaired == [
            {
                "node": "N10",
                "status": "reviewing",
                "reason": "handoff_file_exists",
                "handoff": str(sprints / f"{sid}.handoff.md"),
            }
        ]
        assert graph["nodes"][1]["status"] == "pending"
        assert graph["nodes"][2]["status"] == "reviewing"

    def test_eval_sidecar_does_not_reconcile_before_dependencies_pass(self, tmp_harness):
        """A downstream eval sidecar cannot fail/pass a node before deps pass."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        graph["nodes"] = [
            {
                "id": "N8",
                "goal": "Prerequisite",
                "depends_on": [],
                "write_scope": [f"sprints/{sid}.prep.md"],
                "acceptance": ["prep exists"],
                "status": "pending",
            },
            {
                "id": "N10",
                "goal": "Write sprint handoff",
                "depends_on": ["N8"],
                "write_scope": [f"sprints/{sid}.handoff.md"],
                "acceptance": ["handoff exists"],
                "status": "reviewing",
            },
        ]
        (sprints / f"{sid}.handoff.md").write_text("# Sprint handoff\n", encoding="utf-8")
        (sprints / f"{sid}.N10-eval.json").write_text(
            json.dumps({"verdict": "FAIL", "node_id": "N10"}) + "\n",
            encoding="utf-8",
        )

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert repaired == [
            {
                "node": "N10",
                "status": "reviewing",
                "reason": "sidecar_reconcile_blocked_by_dependencies",
                "handoff": str(sprints / f"{sid}.handoff.md"),
                "eval_json": str(sprints / f"{sid}.N10-eval.json"),
                "blocked_by": ["N8"],
            }
        ]
        assert graph["nodes"][1]["status"] == "reviewing"
        assert "N10" not in graph["node_results"]

    def test_stale_submit_ack_without_live_lease_does_not_resurrect_dispatch(self, tmp_harness, monkeypatch):
        """Old ack files are not proof of a current dispatch after the lease expired."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        node = graph["nodes"][0]
        node["status"] = "pending"
        dispatch_id = f"graph-{sid}-N1-old"
        dispatch_file = sprints / f"{sid}.N1-dispatch.md"
        dispatch_file.write_text("# stale dispatch\n", encoding="utf-8")
        ack_dir = sprints / "graph-acks"
        ack_dir.mkdir()
        (ack_dir / f"{sid}.N1-submit-ack.json").write_text(
            json.dumps({"dispatch_id": dispatch_id, "pane": "solar-harness-lab:0.3"}) + "\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(gnd, "_ledger_dispatch_for", lambda *_: {"pane": "solar-harness-lab:0.3", "dispatch_id": dispatch_id})
        monkeypatch.setattr(gnd, "read_lease", lambda *_: None)
        monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda *_: "quota_exhausted")
        monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda *_: "")
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **k: None)

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert graph["nodes"][0]["status"] == "pending"
        assert "N1" not in graph["node_results"]
        assert repaired == [
            {
                "node": "N1",
                "pane": "solar-harness-lab:0.3",
                "dispatch_id": dispatch_id,
                "status": "pending",
                "reason": "quota_exhausted",
            }
        ]

    def test_active_dispatch_without_live_lease_requeues_pending(self, tmp_harness, monkeypatch):
        """A dispatched node without a matching live lease must not stay dispatched."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        node = graph["nodes"][0]
        node["status"] = "dispatched"
        node["assigned_to"] = "solar-harness-lab:0.3"
        node["dispatch_id"] = f"graph-{sid}-N1-old"
        graph["node_results"]["N1"] = {
            "status": "dispatched",
            "assigned_to": node["assigned_to"],
            "dispatch_id": node["dispatch_id"],
        }

        release_calls = []
        monkeypatch.setattr(gnd, "read_lease", lambda *_: None)
        monkeypatch.setattr(gnd, "_pane_title", lambda *_: "worker")
        monkeypatch.setattr(gnd, "_pane_tail", lambda *_: "")
        monkeypatch.setattr(gnd, "_pane_dispatch_prompt_reason", lambda *_: "")
        monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda *_: "")
        monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda *_: "")
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **k: release_calls.append(a) or {"released": True})

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert node["status"] == "pending"
        assert "assigned_to" not in node
        assert "dispatch_id" not in node
        assert node["dispatch_retry_reason"] == "stale_submit_ack_without_live_lease"
        assert "N1" not in graph["node_results"]
        assert len(release_calls) == 1
        assert repaired == [
            {
                "node": "N1",
                "pane": "solar-harness-lab:0.3",
                "dispatch_id": f"graph-{sid}-N1-old",
                "status": "pending",
                "reason": "stale_submit_ack_without_live_lease",
            }
        ]

    def test_reconcile_accepts_lowercase_passed_eval_sidecar(self, tmp_harness, monkeypatch):
        """Evaluator sidecars may write verdict=passed; reconcile must still close the node."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        node = graph["nodes"][0]
        node["status"] = "reviewing"
        graph["node_results"]["N1"] = {"status": "reviewing"}
        (sprints / f"{sid}.N1-handoff.md").write_text("# handoff\n", encoding="utf-8")
        (sprints / f"{sid}.N1-eval.json").write_text(
            json.dumps({"verdict": "passed", "node_id": "N1"}) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **k: {"released": True})

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert graph["nodes"][0]["status"] == "passed"
        assert graph["node_results"]["N1"]["status"] == "passed"
        assert graph["nodes"][0]["eval_json"] == str(sprints / f"{sid}.N1-eval.json")
        assert repaired == [
            {
                "node": "N1",
                "status": "passed",
                "reason": "eval_sidecar_exists",
                "handoff": str(sprints / f"{sid}.N1-handoff.md"),
                "eval_json": str(sprints / f"{sid}.N1-eval.json"),
                "verdict": "PASS",
            }
        ]

    def test_eval_fail_requests_graph_node_repair_round(self, tmp_harness, monkeypatch):
        """A first evaluator FAIL feeds critique back to the node instead of terminal-failing."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        node = graph["nodes"][0]
        node["status"] = "reviewing"
        node["assigned_to"] = "solar-harness-lab:0.2"
        node["dispatch_id"] = "dispatch-N1"
        node["max_repair_attempts"] = 1
        graph["node_results"]["N1"] = {
            "status": "reviewing",
            "assigned_to": node["assigned_to"],
            "dispatch_id": node["dispatch_id"],
        }
        handoff = sprints / f"{sid}.N1-handoff.md"
        eval_md = sprints / f"{sid}.N1-eval.md"
        eval_json = sprints / f"{sid}.N1-eval.json"
        handoff.write_text("# handoff\n", encoding="utf-8")
        eval_md.write_text("## Verdict\nFAIL\n\nEvidence\n", encoding="utf-8")
        eval_json.write_text(
            json.dumps(
                {
                    "verdict": "FAIL",
                    "node_id": "N1",
                    "summary": "Missing required entrypoint coverage.",
                    "failed_conditions": ["AC1", "AC2"],
                    "errors": [
                        {
                            "cond": "AC1",
                            "severity": "high",
                            "evidence": "inventory omitted a required launcher",
                            "fix_hint": "Add the missing launcher row with cwd/env assumptions.",
                        }
                    ],
                }
            ) + "\n",
            encoding="utf-8",
        )
        release_calls = []
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **k: release_calls.append(a) or {"released": True})

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert node["status"] == "failed_review"
        assert graph["node_results"]["N1"]["status"] == "failed_review"
        assert node["repair_attempts"] == 1
        assert node["repair_context"]["summary"] == "Missing required entrypoint coverage."
        assert node["repair_context"]["failed_conditions"] == ["AC1", "AC2"]
        assert node["repair_context"]["errors"][0]["fix_hint"] == "Add the missing launcher row with cwd/env assumptions."
        assert "assigned_to" not in node
        assert "dispatch_id" not in node
        assert "eval_json" not in node
        assert not handoff.exists()
        assert not eval_json.exists()
        assert not eval_md.exists()
        archived = node["repair_context"]["archived_sidecars"]
        assert Path(archived["handoff_md"]).exists()
        assert Path(archived["eval_json"]).exists()
        assert Path(archived["eval_md"]).exists()
        assert len(release_calls) == 1
        assert repaired == [
            {
                "node": "N1",
                "status": "failed_review",
                "reason": "eval_sidecar_failed_repair_requested",
                "handoff": str(handoff),
                "eval_json": str(eval_json),
                "verdict": "FAIL",
                "repair_attempt": 1,
                "max_repair_attempts": 1,
            }
        ]

    def test_eval_fail_after_repair_limit_marks_terminal_failed(self, tmp_harness, monkeypatch):
        """A node still fails terminally once the capped repair attempts are exhausted."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        node = graph["nodes"][0]
        node["status"] = "reviewing"
        node["repair_attempts"] = 1
        node["max_repair_attempts"] = 1
        graph["node_results"]["N1"] = {"status": "reviewing"}
        handoff = sprints / f"{sid}.N1-handoff.md"
        eval_json = sprints / f"{sid}.N1-eval.json"
        handoff.write_text("# handoff\n", encoding="utf-8")
        eval_json.write_text(json.dumps({"verdict": "FAIL", "node_id": "N1"}) + "\n", encoding="utf-8")
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **k: {"released": True})

        repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

        assert node["status"] == "failed"
        assert graph["node_results"]["N1"]["status"] == "failed"
        assert handoff.exists()
        assert eval_json.exists()
        assert repaired == [
            {
                "node": "N1",
                "status": "failed",
                "reason": "eval_sidecar_exists",
                "handoff": str(handoff),
                "eval_json": str(eval_json),
                "verdict": "FAIL",
            }
        ]

    def test_direct_node_verdict_fail_requests_graph_node_repair_round(self, tmp_harness, monkeypatch):
        """Primary evaluator node-verdict FAIL uses the same repair path as sidecar reconcile."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        graph_path = sprints / f"{sid}.task_graph.json"
        node = graph["nodes"][0]
        node["status"] = "reviewing"
        node["assigned_to"] = "solar-harness-lab:0.2"
        node["dispatch_id"] = "dispatch-N1"
        node["eval_assignments"] = [
            {
                "pane": "solar-harness-lab:0.3",
                "dispatch_id": "eval-N1",
                "role": "primary",
                "eval_md_path": str(sprints / f"{sid}.N1-eval.md"),
                "eval_json_path": str(sprints / f"{sid}.N1-eval.json"),
            }
        ]
        node["max_repair_attempts"] = 1
        graph["node_results"]["N1"] = {
            "status": "reviewing",
            "assigned_to": node["assigned_to"],
            "dispatch_id": node["dispatch_id"],
        }
        graph_path.write_text(json.dumps(graph) + "\n", encoding="utf-8")
        handoff = sprints / f"{sid}.N1-handoff.md"
        eval_md = sprints / f"{sid}.N1-eval.md"
        eval_json = sprints / f"{sid}.N1-eval.json"
        handoff.write_text("# handoff\n", encoding="utf-8")
        eval_md.write_text("## Verdict\nFAIL\n\nEvidence\n", encoding="utf-8")
        eval_json.write_text(
            json.dumps(
                {
                    "verdict": "FAIL",
                    "node_id": "N1",
                    "summary": "Artifact omitted package manifests.",
                    "failed_conditions": ["ACC-003"],
                    "errors": [
                        {
                            "cond": "ACC-003",
                            "severity": "high",
                            "evidence": "package.json exists but was reported absent",
                            "fix_hint": "Correct the manifest inventory.",
                        }
                    ],
                }
            ) + "\n",
            encoding="utf-8",
        )
        release_calls = []
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **k: release_calls.append(a) or {"released": True})

        result = gnd.node_verdict(str(graph_path), "N1", "fail", reason="manifest inventory wrong", eval_json=str(eval_json))
        saved = gnd.load_graph(graph_path)
        saved_node = saved["nodes"][0]

        assert result["ok"] is True
        assert result["status"] == "failed_review"
        assert saved_node["status"] == "failed_review"
        assert saved["node_results"]["N1"]["status"] == "failed_review"
        assert saved_node["repair_attempts"] == 1
        assert saved_node["repair_context"]["summary"] == "Artifact omitted package manifests."
        assert saved_node["repair_context"]["failed_conditions"] == ["ACC-003"]
        assert saved_node["repair_context"]["errors"][0]["fix_hint"] == "Correct the manifest inventory."
        assert "assigned_to" not in saved_node
        assert "dispatch_id" not in saved_node
        assert "eval_assignments" not in saved_node
        assert "eval_json" not in saved_node
        assert not handoff.exists()
        assert not eval_json.exists()
        assert not eval_md.exists()
        archived = saved_node["repair_context"]["archived_sidecars"]
        assert Path(archived["handoff_md"]).exists()
        assert Path(archived["eval_json"]).exists()
        assert Path(archived["eval_md"]).exists()
        assert ("solar-harness-lab:0.2", "dispatch-N1", "node_failed_review") in release_calls
        assert ("solar-harness-lab:0.3", "eval-N1", "node_failed_review") in release_calls

    def test_direct_node_verdict_fail_after_repair_limit_marks_terminal_failed(self, tmp_harness, monkeypatch):
        """Direct evaluator FAIL still terminal-fails once repair attempts are exhausted."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        graph_path = sprints / f"{sid}.task_graph.json"
        node = graph["nodes"][0]
        node["status"] = "reviewing"
        node["repair_attempts"] = 1
        node["max_repair_attempts"] = 1
        graph["node_results"]["N1"] = {"status": "reviewing"}
        graph_path.write_text(json.dumps(graph) + "\n", encoding="utf-8")
        handoff = sprints / f"{sid}.N1-handoff.md"
        eval_json = sprints / f"{sid}.N1-eval.json"
        handoff.write_text("# handoff\n", encoding="utf-8")
        eval_json.write_text(json.dumps({"verdict": "FAIL", "node_id": "N1"}) + "\n", encoding="utf-8")
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **k: {"released": True})

        result = gnd.node_verdict(str(graph_path), "N1", "fail", eval_json=str(eval_json))
        saved = gnd.load_graph(graph_path)

        assert result["ok"] is True
        assert result["status"] == "failed"
        assert saved["nodes"][0]["status"] == "failed"
        assert saved["node_results"]["N1"]["status"] == "failed"
        assert handoff.exists()
        assert eval_json.exists()

    def test_failed_review_nodes_are_ready_for_repair_dispatch(self, tmp_harness):
        """Graph scheduler treats failed_review as a repairable ready node."""
        tmp_path, sprints, sid, graph = tmp_harness
        from graph_scheduler import ready_nodes

        graph["nodes"] = [
            {"id": "N1", "status": "passed", "depends_on": [], "write_scope": ["/tmp/a"]},
            {
                "id": "N2",
                "status": "failed_review",
                "depends_on": ["N1"],
                "write_scope": ["/tmp/b"],
                "repair_context": {"attempt": 1, "max_attempts": 1},
            },
        ]
        graph["node_results"] = {
            "N1": {"status": "passed"},
            "N2": {"status": "failed_review"},
        }

        ready = ready_nodes(graph)

        assert [node["id"] for node in ready] == ["N2"]

    def test_dispatch_text_includes_repair_feedback(self, tmp_harness):
        """A repair dispatch gives the builder evaluator errors and fix hints."""
        tmp_path, sprints, sid, graph = tmp_harness
        import graph_node_dispatcher as gnd

        node = {
            "id": "N1",
            "goal": "Repair audit artifact",
            "depends_on": [],
            "write_scope": [f"sprints/{sid}.audit.md"],
            "acceptance": ["covers required entrypoints"],
            "repair_context": {
                "attempt": 1,
                "max_attempts": 1,
                "summary": "Missing required entrypoint coverage.",
                "failed_conditions": ["AC1"],
                "errors": [
                    {
                        "cond": "AC1",
                        "severity": "high",
                        "evidence": "artifact omitted status-server route modules",
                        "fix_hint": "Add route modules and launch assumptions.",
                    }
                ],
                "archived_sidecars": {"eval_json": str(sprints / f"{sid}.N1-eval.repair1.json")},
            },
        }

        text = gnd.build_dispatch_text({"sprint_id": sid, "node": node}, "solar-harness-lab:0.2")

        assert "## Repair Context" in text
        assert "Missing required entrypoint coverage." in text
        assert "`AC1` (high)" in text
        assert "artifact omitted status-server route modules" in text
        assert "Add route modules and launch assumptions." in text
        assert "eval_json:" in text

    def test_assigned_pane_plan_mode_prompt_is_unavailable(self, tmp_harness, monkeypatch):
        """A pane blocked in Claude plan-mode confirmation is not dispatchable."""
        import graph_node_dispatcher as gnd

        monkeypatch.setattr(gnd, "_pane_title", lambda *_: "Builder 3")
        monkeypatch.setattr(gnd, "_pane_health", lambda *_: {})
        monkeypatch.setattr(gnd, "_models_for_pane", lambda *_: ["glm"])
        monkeypatch.setattr(
            gnd,
            "_pane_tail",
            lambda *_args, **_kwargs: "Claude has written up a plan and is ready to execute. Would you like to proceed?",
        )

        assert gnd._assigned_pane_unavailable_reason("solar-harness-lab:0.2") == "proceed_confirmation_prompt"

    def test_uses_confirmed_enter_submit(self, tmp_harness, monkeypatch):
        """_send_to_pane submits and verifies processing, avoiding prompt-stuck false positives."""
        calls_log = []

        def mock_run(cmd, **kwargs):
            calls_log.append(cmd)
            if isinstance(cmd, list) and cmd[:2] == ["tmux", "capture-pane"]:
                return MagicMock(returncode=0, stdout="test-dispatch.md\n⏺ Reading 2 files")
            return MagicMock(returncode=0)

        import graph_node_dispatcher as gnd
        monkeypatch.setattr("subprocess.run", mock_run)
        import time as time_mod
        monkeypatch.setattr(time_mod, "sleep", lambda x: None)

        result = gnd._send_to_pane("test:0.1", Path("/tmp/test-dispatch.md"), dry_run=False)
        assert result is True

        # Count Enter calls vs C-m calls
        enter_calls = [c for c in calls_log if "Enter" in c and isinstance(c, list)]
        cm_calls = [c for c in calls_log if "C-m" in c and isinstance(c, list)]

        # Claude Code may swallow the first Enter; the dispatcher now sends a
        # harmless confirmation Enter and verifies real processing before it
        # reports success.
        assert len(enter_calls) >= 2, f"Expected confirmed Enter submit, got {len(enter_calls)}"
        assert len(cm_calls) == 0, f"Expected 0 C-m calls, got {len(cm_calls)}"
        capture_calls = [c for c in calls_log if isinstance(c, list) and c[:2] == ["tmux", "capture-pane"]]
        assert capture_calls, "Expected capture-pane verification after submit"

    def test_clears_line_before_send(self, tmp_harness, monkeypatch):
        """_send_to_pane clears the input line before sending command."""
        calls_log = []

        def mock_run(cmd, **kwargs):
            calls_log.append(cmd)
            if isinstance(cmd, list) and cmd[:2] == ["tmux", "capture-pane"]:
                return MagicMock(returncode=0, stdout="test-dispatch.md\n⏺ Reading 2 files")
            return MagicMock(returncode=0)

        import graph_node_dispatcher as gnd
        monkeypatch.setattr("subprocess.run", mock_run)
        import time as time_mod
        monkeypatch.setattr(time_mod, "sleep", lambda x: None)

        result = gnd._send_to_pane("test:0.1", Path("/tmp/test-dispatch.md"), dry_run=False)
        assert result is True

        # The first tmux send-keys call should clear the line. A prior
        # display-message call may update/read pane title before sending.
        send_key_calls = [c for c in calls_log if isinstance(c, list) and c[:3] == ["tmux", "send-keys", "-t"]]
        assert send_key_calls, "Expected tmux send-keys calls"
        assert "C-u" in send_key_calls[0], "Expected C-u (clear line) as first send-keys action"

    def test_dry_run_returns_true(self, tmp_harness):
        """_send_to_pane returns True immediately in dry_run mode."""
        import graph_node_dispatcher as gnd
        result = gnd._send_to_pane("test:0.1", Path("/tmp/test.md"), dry_run=True)
        assert result is True

    def test_dry_run_dispatch_skips_context_injection(self, tmp_harness, monkeypatch):
        """Dry-run must not run slow/side-effecting context injection."""
        import graph_node_dispatcher as gnd

        _, sprints, sid, _ = tmp_harness
        injection_calls = []
        monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *a, **kw: injection_calls.append(a))

        item = {
            "intent": "graph_node|node_id=N1",
            "priority": 80,
            "payload": {
                "sprint_id": sid,
                "node": {"id": "N1", "goal": "Test"},
                "assignment": {"pane": "test:0.1"},
                "dispatch_id": "dispatch-123",
                "graph": str(sprints / f"{sid}.task_graph.json"),
            },
        }

        result = gnd.dispatch_queue_item(item, dry_run=True)
        assert result["ok"] is True
        assert injection_calls == []

    def test_dispatch_text_canonicalizes_harness_sprint_outputs(self, tmp_path, monkeypatch):
        """Builder worktrees need absolute canonical paths for sprint artifacts."""
        import graph_node_dispatcher as gnd

        repo = tmp_path / "repo"
        harness = repo / "harness"
        sprints = harness / "sprints"
        sprints.mkdir(parents=True)
        monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
        monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)

        sid = "sprint-canonical-output"
        raw_output = f"harness/sprints/{sid}.entrypoints_inventory.md"
        expected = sprints / f"{sid}.entrypoints_inventory.md"
        payload = {
            "sprint_id": sid,
            "node": {
                "id": "S1",
                "goal": "Write inventory",
                "write_scope": [raw_output, "harness/lib/source_file.py"],
                "outputs": [raw_output],
                "acceptance": ["canonical artifact exists"],
            },
        }

        text = gnd.build_dispatch_text(payload, "solar-codex-cockpit:0.2")

        assert "## Canonical Output Paths" in text
        assert f"`write_scope` `{raw_output}` -> `{expected}`" in text
        assert f"`outputs` `{raw_output}` -> `{expected}`" in text
        assert "harness/lib/source_file.py` ->" not in text


# ---------------------------------------------------------------------------
# Test: submit creates ack/submit evidence
# ---------------------------------------------------------------------------

class TestSubmitAckEvidence:
    """dispatch creates ack or observable submit evidence."""

    def test_write_submit_ack_creates_file(self, tmp_harness):
        """_write_submit_ack creates a JSON file with dispatch metadata."""
        import graph_node_dispatcher as gnd
        _, sprints, sid, _ = tmp_harness

        gnd._write_submit_ack(sid, "N1", "test:0.1", "dispatch-123")

        ack_dir = sprints / "graph-acks"
        ack_file = ack_dir / f"{sid}.N1-submit-ack.json"
        assert ack_file.exists(), f"Expected ack file at {ack_file}"

        ack = json.loads(ack_file.read_text(encoding="utf-8"))
        assert ack["sid"] == sid
        assert ack["node_id"] == "N1"
        assert ack["pane"] == "test:0.1"
        assert ack["dispatch_id"] == "dispatch-123"
        assert "submitted_at" in ack

    def test_write_submit_ack_fail_open(self, tmp_harness):
        """_write_submit_ack does not raise on write failure."""
        import graph_node_dispatcher as gnd
        _, sprints, sid, _ = tmp_harness

        # Should not raise even with bad path
        gnd._write_submit_ack(sid, "N1", "test:0.1", "dispatch-123")


# ---------------------------------------------------------------------------
# Test: submit failure releases lease and requeues
# ---------------------------------------------------------------------------

class TestSubmitFailureRecovery:
    """Submit failure releases lease and requeues node."""

    def test_dispatch_releases_lease_on_send_failure(self, tmp_harness, monkeypatch):
        """When _send_to_pane returns False, lease is released and node requeued."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        monkeypatch.setenv("SOLAR_HARNESS_SESSION", "test")
        monkeypatch.setattr(gnd, "SESSION", "test")
        # Mock pane exists
        monkeypatch.setattr(gnd, "_pane_exists", lambda p: True)
        # Mock lease acquire success
        monkeypatch.setattr(gnd, "acquire_lease", lambda *a, **kw: {"acquired": True})
        # Mock send failure
        monkeypatch.setattr(gnd, "_send_to_pane", lambda *a, **kw: False)
        # Mock release_lease to track it was called
        release_calls = []
        def mock_release(pane, dispatch_id, reason):
            release_calls.append({"pane": pane, "dispatch_id": dispatch_id, "reason": reason})
            return {"released": True}
        monkeypatch.setattr(gnd, "release_lease", mock_release)
        # Mock enqueue
        enqueue_calls = []
        def mock_enqueue(sid, intent, priority, payload):
            enqueue_calls.append({"sid": sid, "intent": intent})
            return {"ok": True}
        monkeypatch.setattr(gnd, "enqueue", mock_enqueue)
        # Mock load/save graph
        monkeypatch.setattr(gnd, "load_graph", lambda p: graph)
        monkeypatch.setattr(gnd, "save_graph", lambda p, g: None)
        monkeypatch.setattr(gnd, "_mark_graph_node", lambda *a, **kw: True)

        item = {
            "intent": "graph_node|node_id=N1",
            "priority": 80,
            "payload": {
                "sprint_id": sid,
                "node": {"id": "N1", "goal": "Test"},
                "assignment": {"pane": "test:0.1"},
                "dispatch_id": "dispatch-123",
                "graph": str(sprints / f"{sid}.task_graph.json"),
            },
        }

        result = gnd.dispatch_queue_item(item, dry_run=False)
        assert result["ok"] is False
        assert result["reason"] == "send_failed"
        assert result["requeued"] is True

        # Verify lease was released
        assert len(release_calls) == 1
        assert release_calls[0]["dispatch_id"] == "dispatch-123"
        assert release_calls[0]["reason"] == "graph_dispatch_send_failed"

        # Verify node was requeued
        assert len(enqueue_calls) == 1

    def test_dispatch_success_no_lease_release(self, tmp_harness, monkeypatch):
        """When _send_to_pane succeeds, lease is NOT released."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        monkeypatch.setattr(gnd, "_pane_exists", lambda p: True)
        monkeypatch.setattr(gnd, "acquire_lease", lambda *a, **kw: {"acquired": True})
        monkeypatch.setattr(gnd, "_send_to_pane", lambda *a, **kw: True)
        monkeypatch.setattr(gnd, "_write_submit_ack", lambda *a: None)
        monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *a, **kw: None)

        release_calls = []
        def mock_release(*a, **kw):
            release_calls.append(True)
            return {"released": True}
        monkeypatch.setattr(gnd, "release_lease", mock_release)

        monkeypatch.setattr(gnd, "load_graph", lambda p: graph)
        monkeypatch.setattr(gnd, "save_graph", lambda p, g: None)
        monkeypatch.setattr(gnd, "set_node_status", lambda *a, **kw: None)

        item = {
            "intent": "graph_node|node_id=N1",
            "priority": 80,
            "payload": {
                "sprint_id": sid,
                "node": {"id": "N1", "goal": "Test"},
                "assignment": {"pane": "test:0.1"},
                "dispatch_id": "dispatch-123",
                "graph": str(sprints / f"{sid}.task_graph.json"),
            },
        }

        result = gnd.dispatch_queue_item(item, dry_run=False)
        assert result["ok"] is True
        assert len(release_calls) == 0, "Lease should NOT be released on success"

    def test_pane_missing_requeues(self, tmp_harness, monkeypatch):
        """When pane does not exist, node is requeued."""
        import graph_node_dispatcher as gnd

        tmp_path, sprints, sid, graph = tmp_harness

        monkeypatch.setattr(gnd, "_pane_exists", lambda p: False)

        enqueue_calls = []
        def mock_enqueue(sid, intent, priority, payload):
            enqueue_calls.append({"sid": sid, "intent": intent})
            return {"ok": True}
        monkeypatch.setattr(gnd, "enqueue", mock_enqueue)
        monkeypatch.setattr(gnd, "_mark_graph_node", lambda *a, **kw: True)

        item = {
            "intent": "graph_node|node_id=N1",
            "priority": 80,
            "payload": {
                "sprint_id": sid,
                "node": {"id": "N1", "goal": "Test"},
                "assignment": {"pane": "test:0.1"},
            },
        }

        result = gnd.dispatch_queue_item(item, dry_run=False)
        assert result["ok"] is False
        assert result["reason"] == "pane_missing"
        assert result["requeued"] is True


class TestQueueStateSemantics:
    """Queue assignment is distinct from confirmed pane dispatch."""

    def test_enqueue_ready_marks_assigned_not_dispatched(self, tmp_harness, monkeypatch):
        """Scheduler queueing cannot claim a pane has received the task."""
        from graph_scheduler import enqueue_ready

        tmp_path, sprints, sid, graph = tmp_harness

        monkeypatch.setattr("task_queue.enqueue", lambda sid, intent, priority, payload: {"ok": True, "id": "q-1", "intent": intent})
        result = enqueue_ready(
            graph,
            str(sprints / f"{sid}.task_graph.json"),
            [{"pane": "test:0.1", "models": ["sonnet"], "skills": ["bash"], "capabilities": ["read", "shell", "bash"], "role": "builder", "dispatch_role": "builder", "host_role": "builder"}],
            lease=False,
        )

        assert result["ok"] is True
        assert result["enqueued"][0]["node"] == "N1"
        assert graph["nodes"][0]["status"] == "assigned"
        assert graph["nodes"][0]["assigned_to"] == "test:0.1"
        assert graph["nodes"][0]["dispatch_id"]
        assert "dispatch_id=" in result["enqueued"][0]["queue"].get("intent", "")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
