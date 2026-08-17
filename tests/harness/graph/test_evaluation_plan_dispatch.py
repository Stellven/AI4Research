"""Regression tests for evaluation planning before evaluator dispatch."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(ROOT / "lib"))

import graph_node_dispatcher as gnd  # noqa: E402


def test_plan_node_evaluation_derives_staged_mode_for_code_impl() -> None:
    node = {
        "id": "N1",
        "task_type": "CODE_IMPL",
        "verifier_required": True,
        "write_scope": ["/tmp/example.py"],
    }

    plan = gnd._plan_node_evaluation({}, node)

    assert plan["planning_source"] == "derived"
    assert plan["review_mode"] == "staged"
    assert plan["required_evaluators"] == 1
    assert "Verifier" in plan["evaluator_classes"]
    assert "patch_diff" in plan["evidence_requirements"]
    assert "test_report" in plan["evidence_requirements"]


def test_dispatch_node_evals_falls_back_dual_plan_to_staged_with_single_evaluator(monkeypatch) -> None:
    graph = {
        "sprint_id": "sid-eval-plan",
        "nodes": [
            {
                "id": "N2",
                "goal": "needs dual review",
                "status": "reviewing",
                "evaluation_plan": {
                    "review_mode": "dual",
                    "required_evaluators": 2,
                    "evaluator_classes": ["Verifier"],
                },
            }
        ],
    }
    saved: dict[str, object] = {}

    monkeypatch.setattr(gnd, "load_graph", lambda path: graph)
    monkeypatch.setattr(gnd, "save_graph", lambda path, data: saved.setdefault("graph", data))
    monkeypatch.setattr(gnd, "_node_eval_needed", lambda *args, **kwargs: True)
    monkeypatch.setattr(gnd, "_existing_node_handoff", lambda sid, node, graph: Path("/tmp/handoff.md"))
    monkeypatch.setattr(gnd, "_node_handoff_candidates", lambda sid, node, graph: [Path("/tmp/handoff.md")])
    monkeypatch.setattr(gnd, "_eval_md_file", lambda sid, node_id: Path("/tmp/eval.md"))
    monkeypatch.setattr(gnd, "_eval_json_file", lambda sid, node_id: Path("/tmp/eval.json"))
    monkeypatch.setattr(gnd, "_dispatch_file", lambda sid, node_id: Path("/tmp/dispatch.md"))
    monkeypatch.setattr(gnd, "_eval_dispatch_file", lambda sid, node_id: Path("/tmp/eval-dispatch.md"))
    monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(gnd, "_write_submit_ack", lambda *args, **kwargs: None)
    monkeypatch.setattr(gnd, "_send_to_pane", lambda *args, **kwargs: True)
    monkeypatch.setattr(gnd, "_ensure_lease", lambda *args, **kwargs: {"acquired": True, "reason": "ok"})
    monkeypatch.setattr(
        gnd,
        "_discover_evaluators",
        lambda dry_run=False: [
            {"pane": "solar-harness:0.3", "busy": False, "models": ["opus"], "skills": ["review"]},
        ],
    )

    result = gnd.dispatch_node_evals("/tmp/sid-eval-plan.task_graph.json", dry_run=False)

    assert result["skipped"] == []
    assert result["dispatched"][0]["node"] == "N2"
    plan = graph["nodes"][0]["evaluation_plan"]
    requested = graph["nodes"][0]["evaluation_plan_requested"]
    assert requested["review_mode"] == "dual"
    assert requested["required_evaluators"] == 2
    assert plan["review_mode"] == "staged"
    assert plan["required_evaluators"] == 1
    assert plan["fallback_applied"] is True
    assert plan["requested_review_mode"] == "dual"
    assert plan["capacity"]["available_evaluators"] == 1
    assert plan["capacity"]["dispatchable_now"] is True


def test_dispatch_node_evals_keeps_dual_plan_when_quorum_capacity_exists(monkeypatch) -> None:
    graph = {
        "sprint_id": "sid-eval-plan-quorum",
        "nodes": [
            {
                "id": "N4",
                "goal": "needs committee",
                "status": "reviewing",
                "evaluation_plan": {
                    "review_mode": "dual",
                    "required_evaluators": 2,
                    "evaluator_classes": ["Verifier"],
                },
            }
        ],
    }

    monkeypatch.setattr(gnd, "load_graph", lambda path: graph)
    monkeypatch.setattr(gnd, "save_graph", lambda path, data: None)
    monkeypatch.setattr(gnd, "_node_eval_needed", lambda *args, **kwargs: True)
    monkeypatch.setattr(gnd, "_existing_node_handoff", lambda sid, node, graph: Path("/tmp/handoff.md"))
    monkeypatch.setattr(gnd, "_node_handoff_candidates", lambda sid, node, graph: [Path("/tmp/handoff.md")])
    monkeypatch.setattr(gnd, "_eval_md_file", lambda sid, node_id: Path("/tmp/eval.md"))
    monkeypatch.setattr(gnd, "_eval_json_file", lambda sid, node_id: Path("/tmp/eval.json"))
    monkeypatch.setattr(gnd, "_dispatch_file", lambda sid, node_id: Path("/tmp/dispatch.md"))
    monkeypatch.setattr(gnd, "_eval_dispatch_file", lambda sid, node_id: Path("/tmp/eval-dispatch.md"))
    monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(gnd, "_write_submit_ack", lambda *args, **kwargs: None)
    monkeypatch.setattr(gnd, "_send_to_pane", lambda *args, **kwargs: True)
    monkeypatch.setattr(gnd, "_ensure_lease", lambda *args, **kwargs: {"acquired": True, "reason": "ok"})
    monkeypatch.setattr(
        gnd,
        "_discover_evaluators",
        lambda dry_run=False: [
            {"pane": "solar-harness:0.3", "busy": False, "models": ["opus"], "skills": ["review"]},
            {"pane": "solar-harness-lab:0.3", "busy": False, "models": ["opus"], "skills": ["review"]},
        ],
    )

    result = gnd.dispatch_node_evals("/tmp/sid-eval-plan-quorum.task_graph.json", dry_run=False)

    assert result["skipped"] == []
    assert len(result["dispatched"]) == 2
    assert {item["pane"] for item in result["dispatched"]} == {"solar-harness:0.3", "solar-harness-lab:0.3"}
    plan = graph["nodes"][0]["evaluation_plan"]
    requested = graph["nodes"][0]["evaluation_plan_requested"]
    assert requested["review_mode"] == "dual"
    assert requested["capacity"]["quorum_dispatch_supported"] is True
    assert plan["review_mode"] == "dual"
    assert plan["required_evaluators"] == 2
    assert plan["capacity"]["dispatchable_now"] is True
    assert graph["nodes"][0]["eval_assignments"][0]["role"] == "primary"
    assert graph["nodes"][0]["eval_assignments"][1]["role"] == "secondary"


def test_busy_evaluator_dispatch_is_backpressure_not_a_failed_dispatch(monkeypatch, tmp_path) -> None:
    graph = {
        "sprint_id": "sid-eval-busy",
        "nodes": [
            {
                "id": "N5",
                "goal": "review blocked by busy evaluator",
                "status": "reviewing",
            }
        ],
        "node_results": {"N5": {"status": "reviewing"}},
    }
    emitted: list[tuple[str, str]] = []
    saved: dict[str, object] = {}

    monkeypatch.setattr(gnd, "GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES", 1)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path / "sprints")
    gnd.SPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(gnd, "load_graph", lambda path: graph)
    monkeypatch.setattr(gnd, "save_graph", lambda path, data: saved.setdefault("graph", data))
    monkeypatch.setattr(gnd, "_node_eval_needed", lambda *args, **kwargs: True)
    monkeypatch.setattr(gnd, "_emit_node_proof_sidecars", lambda sid, node: emitted.append((sid, node["id"])) or {"patch_diff": "/tmp/patch.diff"})
    monkeypatch.setattr(
        gnd,
        "_discover_evaluators",
        lambda dry_run=False: [
            {"pane": "operator-pool:evaluator.0", "busy": True, "models": ["gpt-5.5"], "skills": ["review"]},
        ],
    )

    result = gnd.dispatch_node_evals(str(tmp_path / "sid-eval-busy.task_graph.json"), dry_run=False)

    assert emitted == [("sid-eval-busy", "N5")]
    assert result["dispatched"] == []
    assert result["skipped"][0]["reason"] == "evaluator_temporarily_busy"
    assert result["terminalized"] == []
    assert "eval_dispatch_failures" not in graph["nodes"][0]
    assert graph["nodes"][0]["status"] == "reviewing"
    assert graph["node_results"]["N5"]["status"] == "reviewing"
    assert saved["graph"] is graph


def test_missing_evaluator_capacity_still_escalates_at_the_configured_bound(monkeypatch) -> None:
    graph = {
        "sprint_id": "sid-eval-absent",
        "nodes": [{"id": "N6", "status": "reviewing"}],
        "node_results": {"N6": {"status": "reviewing"}},
    }
    monkeypatch.setattr(gnd, "GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES", 1)
    monkeypatch.setattr(gnd, "_append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(gnd, "_record_node_runstate", lambda *args, **kwargs: None)

    terminalized = gnd._account_eval_dispatch_failures(
        graph,
        "sid-eval-absent",
        [{"node": "N6", "reason": "no_available_evaluator"}],
        False,
    )

    assert terminalized == [
        {
            "node": "N6",
            "status": "needs_human_review",
            "reason": "eval_dispatch_unavailable:no_available_evaluator:1_consecutive_failures",
        }
    ]
    assert graph["nodes"][0]["status"] == "needs_human_review"


def test_build_eval_dispatch_text_includes_evaluation_plan(monkeypatch, tmp_path) -> None:
    graph = {"sprint_id": "sid-eval-text"}
    node = {
        "id": "N3",
        "goal": "review with explicit plan",
        "eval_artifact_snapshot": {
            "schema": "solar.eval_artifact_snapshot.v1",
            "path": "/tmp/sid-eval-text.N3-eval-snapshot.json",
            "snapshot_digest": "a" * 64,
        },
        "evaluation_plan": {
            "review_mode": "single",
            "required_evaluators": 1,
            "evaluator_classes": ["Verifier"],
            "evidence_requirements": ["handoff_md", "session_log"],
        },
    }
    handoff = tmp_path / "sid-eval-text.N3-handoff.md"
    dispatch = tmp_path / "sid-eval-text.N3-dispatch.md"
    monkeypatch.setattr(gnd, "_existing_node_handoff", lambda sid, node, graph: handoff)
    monkeypatch.setattr(gnd, "_node_handoff_candidates", lambda sid, node, graph: [handoff])
    monkeypatch.setattr(gnd, "_eval_md_file", lambda sid, node_id: tmp_path / "eval.md")
    monkeypatch.setattr(gnd, "_eval_json_file", lambda sid, node_id: tmp_path / "eval.json")
    monkeypatch.setattr(gnd, "_dispatch_file", lambda sid, node_id: dispatch)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    (tmp_path / "sid-eval-text.contract.md").write_text("# contract\n", encoding="utf-8")

    text = gnd.build_eval_dispatch_text(graph, "/tmp/graph.json", node, "solar-harness:0.3", "did")

    assert "## Evaluation Plan" in text
    assert "Review Mode: `single`" in text
    assert '"evaluation_plan": {' in text
    assert "canonical content digest" in text
    assert "intentionally not the SHA-256 of the complete JSON file bytes" in text
    assert "Do not compare it with" in text
    assert "Any change to the canonical snapshot material" in text
    assert "Any byte change after dispatch" not in text


def _patch_eval_dispatch_paths(monkeypatch, tmp_path, sid: str, node_id: str) -> None:
    handoff = tmp_path / f"{sid}.{node_id}-handoff.md"
    dispatch = tmp_path / f"{sid}.{node_id}-dispatch.md"
    monkeypatch.setattr(gnd, "_existing_node_handoff", lambda sid, node, graph: handoff)
    monkeypatch.setattr(gnd, "_node_handoff_candidates", lambda sid, node, graph: [handoff])
    monkeypatch.setattr(gnd, "_eval_md_file", lambda sid, node_id: tmp_path / f"{node_id}-eval.md")
    monkeypatch.setattr(gnd, "_eval_json_file", lambda sid, node_id: tmp_path / f"{node_id}-eval.json")
    monkeypatch.setattr(gnd, "_dispatch_file", lambda sid, node_id: dispatch)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    (tmp_path / f"{sid}.contract.md").write_text("# contract\n", encoding="utf-8")


def test_build_eval_dispatch_text_does_not_require_research_gate_for_local_audit(monkeypatch, tmp_path) -> None:
    sid = "sid-local-audit"
    node = {
        "id": "N4_compile_audit",
        "goal": "Compile a local packaging-readiness audit from inspected repository files",
        "required_capabilities": ["harness.reporting", "report.compile", "source.local.read"],
        "write_scope": [f"harness/sprints/{sid}.packaging-readiness-audit.md"],
    }
    _patch_eval_dispatch_paths(monkeypatch, tmp_path, sid, "N4_compile_audit")

    text = gnd.build_eval_dispatch_text({"sprint_id": sid}, "/tmp/graph.json", node, "solar-harness:0.3", "did")

    assert "DeepResearch deterministic artifact gate is **not required**" in text
    assert "Do not run `solar-harness research eval-artifacts`" in text
    assert "generic `report.compile` outputs are judged by this node's acceptance criteria" in text
    assert "没有 `research_quality_gate.ok=true` 不允许 PASS" not in text


def test_build_eval_dispatch_text_requires_research_gate_for_deepresearch_node(monkeypatch, tmp_path) -> None:
    sid = "sid-deepresearch"
    node = {
        "id": "R8_section_fact_check",
        "goal": "Evaluate DeepResearch citation and factuality quality",
        "required_capabilities": ["research.report_ast", "citation.verify"],
        "artifacts": {"research_eval": "out/run-research_eval.json", "report_ast": "out/report_ast.json"},
    }
    _patch_eval_dispatch_paths(monkeypatch, tmp_path, sid, "R8_section_fact_check")

    text = gnd.build_eval_dispatch_text({"sprint_id": sid}, "/tmp/graph.json", node, "solar-harness:0.3", "did")

    assert "This node declares DeepResearch claims or report artifacts" in text
    assert "solar-harness research eval-artifacts --eval-json" in text
    assert "Do not PASS unless `research_quality_gate.ok=true`" in text
    assert "DeepResearch deterministic artifact gate is **not required**" not in text


def test_synthesis_only_node_does_not_inherit_grounded_report_bundle_proofs() -> None:
    node = {
        "id": "R2",
        "write_scope": ["workspace/research/synthesis/synthesis_plan.json"],
        "proof_obligations": [
            {
                "kind": "self_check",
                "source_capsule_id": "cap.requirement-research-synthesizer",
                "requirement": "check.source_packs_verified",
            },
            {
                "kind": "self_check",
                "source_capsule_id": "cap.requirement-research-synthesizer",
                "requirement": "check.grounded_report_bundle_written",
            },
            {
                "kind": "postcondition",
                "source_capsule_id": "cap.requirement-research-synthesizer",
                "requirement": "output_present",
                "field": "claims_jsonl",
            },
            {
                "kind": "pass_condition",
                "source_capsule_id": "cap.requirement-research-synthesizer",
                "requirement": "final.md citations resolve to evidence.jsonl",
            },
        ],
    }

    obligations = gnd._node_proof_obligations("sid-synthesis-only", node)

    assert [item["requirement"] for item in obligations] == ["check.source_packs_verified"]


def test_deepresearch_node_keeps_grounded_report_bundle_proofs() -> None:
    node = {
        "id": "R3",
        "research_quality_gate_required": True,
        "proof_obligations": [
            {
                "kind": "postcondition",
                "source_capsule_id": "cap.requirement-research-synthesizer",
                "requirement": "output_present",
                "field": "claims_jsonl",
            },
            {
                "kind": "postcondition",
                "source_capsule_id": "cap.requirement-research-synthesizer",
                "requirement": "output_present",
                "field": "research_eval_json",
            },
        ],
    }

    obligations = gnd._node_proof_obligations("sid-deepresearch", node)

    assert [item["field"] for item in obligations] == ["claims_jsonl", "research_eval_json"]
