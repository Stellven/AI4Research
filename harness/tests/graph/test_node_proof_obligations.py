#!/usr/bin/env python3
"""Tests for eval sidecar gate — AC1/AC2/AC3 of O2_eval_sidecar_gate.

AC1: handoff-only pass reports reviewing (node_status downgrade)
AC2: node_verdict pass without eval_json is blocked
AC3: eval PASS allows passed (normal flow when eval_json exists)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_scheduler as gs
import graph_node_dispatcher as gnd


def _base_graph(sid: str = "sprint-test-eval-gate") -> dict:
    return {
        "schema_version": "solar.task_graph.v1",
        "sprint_id": sid,
        "nodes": [
            {
                "id": "N1",
                "goal": "test node",
                "depends_on": [],
                "acceptance": ["ac1"],
                "write_scope": ["test_output.txt"],
                "status": "reviewing",
            },
        ],
        "node_results": {},
    }


def _setup_dispatcher_graph(tmp_path, monkeypatch, sid):
    sprints = tmp_path / "sprints"
    sprints.mkdir(exist_ok=True)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)

    graph = _base_graph(sid)
    graph["nodes"][0]["status"] = "reviewing"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False))
    return graph_path


# ── AC1: handoff-only pass → reviewing ─────────────────────────────────


class TestHandoffOnlyPassReportsReviewing:
    def test_node_status_downgrades_to_reviewing_when_no_eval(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        sid = "sprint-ac1-downgrade"
        graph = _base_graph(sid)
        graph["nodes"][0]["status"] = "passed"

        handoff = tmp_path / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")

        assert gs.node_status(graph, "N1") == "reviewing"

    def test_node_status_returns_passed_when_eval_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        sid = "sprint-ac1-with-eval"
        graph = _base_graph(sid)
        graph["nodes"][0]["status"] = "passed"

        handoff = tmp_path / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")
        eval_json = tmp_path / f"{sid}.N1-eval.json"
        eval_json.write_text(json.dumps({"verdict": "PASS"}))
        # New contract: an independent eval REPORT (eval.md), not just a self-written verdict JSON,
        # is required to certify PASS (closes the eval-backfill self-grade vector).
        (tmp_path / f"{sid}.N1-eval.md").write_text("## Verdict\nPASS\n")

        assert gs.node_status(graph, "N1") == "passed"

    def test_node_status_passed_no_handoff_no_eval(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        sid = "sprint-ac1-no-handoff"
        graph = _base_graph(sid)
        graph["nodes"][0]["status"] = "passed"

        assert gs.node_status(graph, "N1") == "passed"

    def test_doctor_detects_passed_missing_eval(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        sid = "sprint-ac1-doctor"
        graph = _base_graph(sid)
        graph["nodes"][0]["status"] = "passed"

        handoff = tmp_path / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")

        result = gs.doctor_graph(graph, repair=False)
        assert not result["ok"]
        issue_types = [i["type"] for i in result["issues"]]
        assert "passed_missing_eval" in issue_types

    def test_doctor_repairs_passed_missing_eval(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        sid = "sprint-ac1-repair"
        graph = _base_graph(sid)
        graph["nodes"][0]["status"] = "passed"

        handoff = tmp_path / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")

        result = gs.doctor_graph(graph, repair=True)
        assert graph["nodes"][0]["status"] == "reviewing"
        repair_types = [r["repair"] for r in result["repairs"]]
        assert "reopened_passed_missing_eval" in repair_types


# ── AC2: node_verdict pass without eval_json is blocked ─────────────────


class TestNodeVerdictBlocksPassWithoutEval:
    def test_verdict_pass_blocked_without_eval_json(self, tmp_path, monkeypatch):
        sid = "sprint-ac2-blocked"
        graph_path = _setup_dispatcher_graph(tmp_path, monkeypatch, sid)

        handoff = tmp_path / "sprints" / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")

        result = gnd.node_verdict(
            str(graph_path), "N1", "pass",
            dry_run=True,
        )
        assert result["ok"] is False
        assert result["reason"] == "missing_eval_json_for_pass"
        assert result["status"] == "blocked"

    def test_verdict_pass_blocked_with_nonexistent_eval_path(self, tmp_path, monkeypatch):
        sid = "sprint-ac2-nonexistent"
        graph_path = _setup_dispatcher_graph(tmp_path, monkeypatch, sid)

        result = gnd.node_verdict(
            str(graph_path), "N1", "pass",
            eval_json=str(tmp_path / "nonexistent-eval.json"),
            dry_run=True,
        )
        assert result["ok"] is False
        assert "missing_eval_json" in result["reason"]

    def test_assert_pass_mark_allowed_raises_without_eval(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        sid = "sprint-ac2-assert"
        graph = _base_graph(sid)
        graph["nodes"][0]["status"] = "reviewing"

        handoff = tmp_path / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")

        with pytest.raises(ValueError, match="passed_requires_eval_json"):
            gs._assert_pass_mark_allowed(graph, "N1", "passed")

    def test_verdict_pass_blocked_self_graded_without_independent_report(self, tmp_path, monkeypatch):
        # Guard for the eval-backfill false-positive vector: an executor node (has a handoff) wrote
        # its OWN verdict JSON (eval.json) but there is NO independent evaluator report -- no non-empty
        # {node}-eval.md and no {node}-eval-dispatch sidecar. A self-graded verdict must never stand in
        # for a real evaluation: the node stays UNVERIFIED (blocked), never PASS.
        sid = "sprint-ac2-self-graded"
        graph_path = _setup_dispatcher_graph(tmp_path, monkeypatch, sid)

        sprints = tmp_path / "sprints"
        handoff = sprints / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")
        eval_json = sprints / f"{sid}.N1-eval.json"
        # Self-graded verdict with NO sibling {sid}.N1-eval.md and NO eval-dispatch sidecar.
        eval_json.write_text(json.dumps({"node_id": "N1", "verdict": "PASS", "summary": "self"}))

        result = gnd.node_verdict(
            str(graph_path), "N1", "pass",
            eval_json=str(eval_json),
            dry_run=True,
        )
        assert result["ok"] is False
        assert result["reason"] == "self_graded_eval_requires_independent_report"
        assert result["status"] == "blocked"

        # Scheduler-level backstop: the same self-graded node must not be mark-able as passed.
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        with pytest.raises(ValueError, match="passed_requires_eval_json"):
            gs._assert_pass_mark_allowed(graph, "N1", "passed")


# ── AC3: eval PASS allows passed ────────────────────────────────────────


class TestEvalPassAllowsPassed:
    def test_verdict_pass_with_eval_json_succeeds(self, tmp_path, monkeypatch):
        sid = "sprint-ac3-pass"
        graph_path = _setup_dispatcher_graph(tmp_path, monkeypatch, sid)

        handoff = tmp_path / "sprints" / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")

        eval_json = tmp_path / "sprints" / f"{sid}.N1-eval.json"
        eval_json.write_text(json.dumps({
            "node_id": "N1",
            "verdict": "PASS",
            "summary": "All ACs verified",
        }))
        # New contract: a genuine independent eval REPORT (eval.md) -- not just a self-written verdict
        # JSON -- is required to certify PASS (closes the eval-backfill self-grade vector).
        (tmp_path / "sprints" / f"{sid}.N1-eval.md").write_text("## Verdict\nPASS\n")

        result = gnd.node_verdict(
            str(graph_path), "N1", "pass",
            eval_json=str(eval_json),
            dry_run=True,
        )
        assert result["ok"] is True
        assert result["status"] == "passed"

    def test_verdict_fail_does_not_require_eval_json(self, tmp_path, monkeypatch):
        sid = "sprint-ac3-fail"
        graph_path = _setup_dispatcher_graph(tmp_path, monkeypatch, sid)

        result = gnd.node_verdict(
            str(graph_path), "N1", "fail",
            reason="test failure",
            dry_run=True,
        )
        assert result["ok"] is True
        assert result["status"] == "failed"

    def test_assert_pass_mark_allowed_ok_with_eval(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        sid = "sprint-ac3-assert-ok"
        graph = _base_graph(sid)
        graph["nodes"][0]["status"] = "reviewing"

        handoff = tmp_path / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\n")
        eval_json = tmp_path / f"{sid}.N1-eval.json"
        eval_json.write_text(json.dumps({"verdict": "PASS"}))
        # New contract: an independent eval REPORT (eval.md) is required to certify PASS.
        (tmp_path / f"{sid}.N1-eval.md").write_text("## Verdict\nPASS\n")

        gs._assert_pass_mark_allowed(graph, "N1", "passed")

    def test_verdict_pass_with_handoff_and_eval_succeeds(self, tmp_path, monkeypatch):
        sid = "sprint-ac3-full"
        graph_path = _setup_dispatcher_graph(tmp_path, monkeypatch, sid)

        handoff = tmp_path / "sprints" / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff — full integration test\n")
        eval_json = tmp_path / "sprints" / f"{sid}.N1-eval.json"
        eval_json.write_text(json.dumps({
            "node_id": "N1",
            "verdict": "PASS",
            "summary": "Full integration",
            "acceptance_results": {"ac1": True, "ac2": True, "ac3": True},
        }))
        # New contract: an independent eval REPORT (eval.md) is required to certify PASS.
        (tmp_path / "sprints" / f"{sid}.N1-eval.md").write_text("## Verdict\nPASS\n")

        result = gnd.node_verdict(
            str(graph_path), "N1", "pass",
            eval_json=str(eval_json),
            dry_run=True,
        )
        assert result["ok"] is True
        assert result["status"] == "passed"
        assert result["proof_gate"]["required"] is False

    def test_verdict_pass_materializes_capsule_proof_sidecars(self, tmp_path, monkeypatch):
        sid = "sprint-ac3-capsule-proof-sidecars"
        graph_path = _setup_dispatcher_graph(tmp_path, monkeypatch, sid)

        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        graph["nodes"][0]["proof_obligations"] = [
            {"kind": "self_check", "source_capsule_id": "guard.secret-leak-guard", "requirement": "check.guard_decision_written"},
            {"kind": "pass_condition", "source_capsule_id": "guard.secret-leak-guard", "requirement": "guard_decision exists"},
            {"kind": "postcondition", "source_capsule_id": "guard.secret-leak-guard", "requirement": "output_present", "field": "guard_decision"},
            {"kind": "self_check", "source_capsule_id": "resource.github-readonly", "requirement": "check.resource_binding_written"},
            {"kind": "pass_condition", "source_capsule_id": "resource.github-readonly", "requirement": "resource_binding exists"},
            {"kind": "postcondition", "source_capsule_id": "resource.github-readonly", "requirement": "output_present", "field": "resource_binding"},
            {"kind": "self_check", "source_capsule_id": "adapter.artifact-type-bridge", "requirement": "check.adapter_output_written"},
            {"kind": "pass_condition", "source_capsule_id": "adapter.artifact-type-bridge", "requirement": "adapter output exists"},
            {"kind": "postcondition", "source_capsule_id": "adapter.artifact-type-bridge", "requirement": "output_present", "field": "bridged_artifact"},
            {
                "kind": "adapter_contract",
                "source_capsule_id": "adapter.artifact-type-bridge",
                "requirement": "type_mismatch_bridge",
                "target_stage_id": "N1:capability",
                "missing_required_inputs": ["markdown"],
                "source_artifacts": ["artifact.guard_decision", "artifact.resource_binding", "json"],
            },
        ]
        graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")

        sprints = tmp_path / "sprints"
        handoff = sprints / f"{sid}.N1-handoff.md"
        handoff.write_text("# Handoff\nNo sensitive values here.\n", encoding="utf-8")
        patch_diff = sprints / f"{sid}.patch.diff"
        patch_diff.write_text("# no source patch\n", encoding="utf-8")
        eval_json = sprints / f"{sid}.N1-eval.json"
        eval_json.write_text(json.dumps({"node_id": "N1", "verdict": "PASS"}), encoding="utf-8")
        # New contract: an independent eval REPORT (eval.md) is required to certify PASS.
        (sprints / f"{sid}.N1-eval.md").write_text("## Verdict\nPASS\n", encoding="utf-8")

        monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
        monkeypatch.setattr(gnd, "release_lease", lambda *a, **kw: {"released": False})
        monkeypatch.setattr(gnd, "_mark_parent_sprint_passed_if_ready", lambda *a, **kw: False)

        result = gnd.node_verdict(
            str(graph_path), "N1", "pass",
            eval_json=str(eval_json),
            dry_run=True,
            dispatch_downstream=False,
        )

        assert result["ok"] is True
        assert result["proof_gate"]["ok"] is True
        guard = sprints / f"{sid}.N1-guard_decision.json"
        resource = sprints / f"{sid}.N1-resource_binding.json"
        bridge = sprints / f"{sid}.N1-bridged_artifact.md"
        assert json.loads(guard.read_text(encoding="utf-8"))["decision"] == "allow"
        assert json.loads(resource.read_text(encoding="utf-8"))["bound"] is True
        assert "artifact.guard_decision" in bridge.read_text(encoding="utf-8")

        eval_prompt = gnd.build_eval_dispatch_text(
            graph,
            str(graph_path),
            graph["nodes"][0],
            "solar-test:0.3",
            "dispatch-eval-test",
        )
        assert "## Proof Support Artifacts" in eval_prompt
        assert str(guard) in eval_prompt
        assert str(resource) in eval_prompt
        assert str(bridge) in eval_prompt
