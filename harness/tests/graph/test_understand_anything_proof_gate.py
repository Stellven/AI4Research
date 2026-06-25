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
            "goal": "Build repo knowledge graph",
            "depends_on": [],
            "write_scope": ["/tmp/repo"],
            "status": "reviewing",
            "proof_obligations": [
                {"kind": "self_check", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "check.understand_anything_dispatch_result_written"},
                {"kind": "self_check", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "check.semantic_backend_thunderomlx_declared"},
                {"kind": "self_check", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "check.semantic_proof_artifact_written"},
                {"kind": "self_check", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "check.semantic_phase_request_written"},
                {"kind": "self_check", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "check.chunk_manifest_written"},
                {"kind": "self_check", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "check.resume_state_written"},
                {"kind": "self_check", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "check.meta_written"},
                {"kind": "postcondition", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "output_present", "field": "understand_anything_dispatch_result"},
                {"kind": "external_verifier", "source_capsule_id": "cap.understand-anything-indexer", "requirement": "external_verifier.required"},
            ],
        }],
        "node_results": {},
        "gate_results": {},
    }


def test_understand_anything_proof_gate_passes_from_operator_artifacts(tmp_path, monkeypatch):
    sid = "sprint-ua-proof-pass"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.N1-eval.json"
    eval_json.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    result_dir = tmp_path / "run" / "operator-results" / "mini-understand-anything-pane-bridge" / "task-1"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "result.json").write_text(
        json.dumps({"sprint_id": sid, "node_id": "N1", "status": "completed"}),
        encoding="utf-8",
    )
    ua_root = tmp_path / "ua"
    ua_root.mkdir()
    (ua_root / "chunk-manifest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (ua_root / "resume-state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (ua_root / "meta.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "understand-anything-result.json").write_text(
        json.dumps(
            {
                "ok": True,
                "dispatch_result": {
                    "manifest_path": str(ua_root / "chunk-manifest.json"),
                    "resume_state_path": str(ua_root / "resume-state.json"),
                    "meta_path": str(ua_root / "meta.json"),
                },
            }
        ),
        encoding="utf-8",
    )
    (result_dir / "understand-anything-semantic-proof.json").write_text(
        json.dumps({"semantic_backend_declared": "ThunderOMLX"}),
        encoding="utf-8",
    )
    (result_dir / "understand-anything-semantic-phase-request.json").write_text(
        json.dumps({"backend": "ThunderOMLX"}),
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


def test_understand_anything_proof_gate_blocks_missing_semantic_request(tmp_path, monkeypatch):
    sid = "sprint-ua-proof-fail"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.N1-eval.json"
    eval_json.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    result_dir = tmp_path / "run" / "operator-results" / "mini-understand-anything-pane-bridge" / "task-1"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "result.json").write_text(
        json.dumps({"sprint_id": sid, "node_id": "N1", "status": "completed"}),
        encoding="utf-8",
    )
    ua_root = tmp_path / "ua-missing"
    ua_root.mkdir()
    (ua_root / "chunk-manifest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (ua_root / "resume-state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (ua_root / "meta.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (result_dir / "understand-anything-result.json").write_text(
        json.dumps(
            {
                "ok": True,
                "dispatch_result": {
                    "manifest_path": str(ua_root / "chunk-manifest.json"),
                    "resume_state_path": str(ua_root / "resume-state.json"),
                    "meta_path": str(ua_root / "meta.json"),
                },
            }
        ),
        encoding="utf-8",
    )
    (result_dir / "understand-anything-semantic-proof.json").write_text(
        json.dumps({"semantic_backend_declared": "ThunderOMLX"}),
        encoding="utf-8",
    )
    handoff = tmp_path / f"{sid}.N1-handoff.md"
    handoff.write_text("# Handoff\n", encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)

    result = gnd.node_verdict(str(graph_path), "N1", "pass", eval_json=str(eval_json), dispatch_downstream=False)
    assert result["ok"] is False
    assert result["reason"] == "proof_obligations_failed"
    assert any(item["requirement"] == "check.semantic_phase_request_written" for item in result["proof_gate"]["missing"])
