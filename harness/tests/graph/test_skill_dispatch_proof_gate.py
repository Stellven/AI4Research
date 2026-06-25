from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402


def _graph(sid: str) -> dict:
    return {
        "sprint_id": sid,
        "nodes": [{
            "id": "N1",
            "goal": "Execute selected installed skill in a controlled pane task",
            "depends_on": [],
            "write_scope": ["/tmp/repo"],
            "status": "reviewing",
            "proof_obligations": [
                {"kind": "self_check", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "check.skill_dispatch_result_written"},
                {"kind": "self_check", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "check.skill_dispatch_prompt_written"},
                {"kind": "self_check", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "check.skill_dispatch_selection_proof_written"},
                {"kind": "self_check", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "check.skill_dispatch_contract_written"},
                {"kind": "self_check", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "check.skill_dispatch_command_protocol_declared"},
                {"kind": "self_check", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "check.skill_dispatch_workflow_phases_declared"},
                {"kind": "self_check", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "check.skill_dispatch_delivery_expectation_declared"},
                {"kind": "postcondition", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "output_present", "field": "skill_dispatch_result"},
                {"kind": "external_verifier", "source_capsule_id": "cap.skill-execution-bridge", "requirement": "external_verifier.required"},
            ],
        }],
        "node_results": {},
        "gate_results": {},
    }


def test_skill_dispatch_proof_gate_passes_from_operator_artifacts(tmp_path, monkeypatch):
    sid = "sprint-skill-dispatch-proof-pass"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.N1-eval.json"
    eval_json.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    result_dir = tmp_path / "run" / "operator-results" / "mini-skill-dispatch-pane-bridge" / "task-1"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "result.json").write_text(
        json.dumps({"sprint_id": sid, "node_id": "N1", "status": "completed"}),
        encoding="utf-8",
    )
    (result_dir / "skill-dispatch-result.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "skill-dispatch-pane-prompt.md").write_text("# Prompt\n", encoding="utf-8")
    (result_dir / "skill-dispatch-selection-proof.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "skill-dispatch-bridge-contract.json").write_text(
        json.dumps(
            {
                "command_protocol": {
                    "mode": "workflow_methodology",
                    "first_command": "",
                    "verify_command": "",
                    "command_template": "",
                    "record_exact_commands": False,
                },
                "workflow_contract": {
                    "phases": [
                        "frame_objective_and_constraints",
                        "apply_skill_workflow",
                    ],
                    "delivery_expectation": "phase_checklist_and_decision_log",
                },
            }
        ),
        encoding="utf-8",
    )
    handoff = tmp_path / f"{sid}.N1-handoff.md"
    handoff.write_text("# Handoff\n", encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "release_lease", lambda *a, **kw: {"released": False})
    monkeypatch.setattr(gnd, "_mark_parent_sprint_passed_if_ready", lambda *a, **kw: False)

    # New contract: the executor's self-written eval.json needs an INDEPENDENT eval report (eval.md)
    # for the node to certify PASS; without it the self-graded guard blocks the verdict. This test
    # exercises the proof gate, so give the node a genuine evaluator report alongside the handoff.
    (tmp_path / f"{sid}.N1-eval.md").write_text("## Verdict\nPASS\n", encoding="utf-8")

    result = gnd.node_verdict(str(graph_path), "N1", "pass", eval_json=str(eval_json), dispatch_downstream=False)
    assert result["ok"] is True
    assert result["proof_gate"]["ok"] is True


def test_skill_dispatch_proof_gate_blocks_missing_workflow_contract(tmp_path, monkeypatch):
    sid = "sprint-skill-dispatch-proof-fail"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.N1-eval.json"
    eval_json.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    result_dir = tmp_path / "run" / "operator-results" / "mini-skill-dispatch-pane-bridge" / "task-1"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "result.json").write_text(
        json.dumps({"sprint_id": sid, "node_id": "N1", "status": "completed"}),
        encoding="utf-8",
    )
    (result_dir / "skill-dispatch-result.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "skill-dispatch-pane-prompt.md").write_text("# Prompt\n", encoding="utf-8")
    (result_dir / "skill-dispatch-selection-proof.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "skill-dispatch-bridge-contract.json").write_text(
        json.dumps(
            {
                "command_protocol": {
                    "mode": "workflow_methodology",
                },
                "workflow_contract": {
                    "phases": [],
                    "delivery_expectation": "",
                },
            }
        ),
        encoding="utf-8",
    )
    handoff = tmp_path / f"{sid}.N1-handoff.md"
    handoff.write_text("# Handoff\n", encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)

    result = gnd.node_verdict(str(graph_path), "N1", "pass", eval_json=str(eval_json), dispatch_downstream=False)
    assert result["ok"] is False
    assert result["reason"] == "proof_obligations_failed"
    missing = {item["requirement"] for item in result["proof_gate"]["missing"]}
    assert "check.skill_dispatch_workflow_phases_declared" in missing
    assert "check.skill_dispatch_delivery_expectation_declared" in missing
