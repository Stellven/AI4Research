"""DAG node-verdict integration for DeepResearch deterministic quality gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LIB = _ROOT / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import graph_node_dispatcher as gnd  # noqa: E402


def _graph(sid: str) -> dict:
    return {
        "sprint_id": sid,
        "nodes": [{
            "id": "R8_section_fact_check",
            "goal": "Evaluate DeepResearch citation and factuality quality",
            "depends_on": [],
            "write_scope": ["/tmp/eval"],
            "required_capabilities": ["research.factuality_evaluator"],
            "status": "reviewing",
        }],
        "node_results": {},
        "gate_results": {},
    }


def test_deepresearch_node_verdict_requires_quality_gate(tmp_path, monkeypatch):
    sid = "sprint-test-deepresearch-gate"
    graph = _graph(sid)
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.R8-eval.json"
    eval_json.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)

    result = gnd.node_verdict(str(graph_path), "R8_section_fact_check", "pass", eval_json=str(eval_json), dispatch_downstream=False)

    assert result["ok"] is False
    assert result["reason"] == "missing_deepresearch_quality_gate"


def test_deepresearch_node_verdict_blocks_failed_quality_gate(tmp_path, monkeypatch):
    sid = "sprint-test-deepresearch-gate-fail"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.R8-eval.json"
    eval_json.write_text(json.dumps({
        "verdict": "PASS",
        "research_quality_gate": {"ok": False, "verdict": "FAIL", "errors": ["claim_count_zero"]},
    }), encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)

    result = gnd.node_verdict(str(graph_path), "R8_section_fact_check", "pass", eval_json=str(eval_json), dispatch_downstream=False)

    assert result["ok"] is False
    assert result["reason"] == "deepresearch_quality_gate_failed"


def test_deepresearch_node_verdict_accepts_passing_quality_gate(tmp_path, monkeypatch):
    sid = "sprint-test-deepresearch-gate-pass"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.R8-eval.json"
    eval_json.write_text(json.dumps({
        "verdict": "PASS",
        "research_quality_gate": {"ok": True, "verdict": "PASS", "errors": []},
    }), encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "release_lease", lambda *a, **kw: {"released": False})
    monkeypatch.setattr(gnd, "_mark_parent_sprint_passed_if_ready", lambda *a, **kw: False)

    result = gnd.node_verdict(str(graph_path), "R8_section_fact_check", "pass", eval_json=str(eval_json), dispatch_downstream=False)

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["research_quality_gate"]["ok"] is True


def test_deepresearch_node_verdict_auto_runs_missing_quality_gate(tmp_path, monkeypatch):
    sid = "sprint-test-deepresearch-gate-auto"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.R8-eval.json"
    research_eval = out_dir / "run-research_eval.json"
    research_eval.write_text(json.dumps({
        "status": "passed",
        "output_dir": str(out_dir),
        "source_count": 2,
        "evidence_count": 3,
        "claim_count": 2,
        "section_count": 1,
        "unsupported_rate": 0.0,
        "citation_accuracy": 1.0,
    }), encoding="utf-8")
    (out_dir / "report_ast.json").write_text(json.dumps({
        "chapters": [{"sections": [{"id": "s1", "title": "Section"}]}],
    }), encoding="utf-8")
    (out_dir / "final.md").write_text("Supported claim [cite:ev_abc123].\n", encoding="utf-8")
    (out_dir / "evidence.jsonl").write_text(
        json.dumps({"id": "ev_abc123", "content": "Supported claim evidence."}) + "\n",
        encoding="utf-8",
    )
    (out_dir / "sources.jsonl").write_text(
        json.dumps({"id": "src_1", "source_type": "paper", "title": "Paper", "url": "https://arxiv.org/abs/2501.00001"}) + "\n",
        encoding="utf-8",
    )
    (out_dir / "sections.jsonl").write_text(
        json.dumps({"id": "s1", "title": "Section", "content": "Supported claim evidence [cite:ev_abc123]. This section analyzes the runtime architecture, projection gate, deployment boundary, and evaluation policy for research systems. The implementation should preserve audit evidence and failure recovery while separating model exploration from control-plane orchestration."}) + "\n",
        encoding="utf-8",
    )
    (out_dir / "final.bibliography.json").write_text("[]", encoding="utf-8")
    eval_json.write_text(json.dumps({
        "verdict": "PASS",
        "research_eval_json": str(research_eval),
    }), encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "release_lease", lambda *a, **kw: {"released": False})
    monkeypatch.setattr(gnd, "_mark_parent_sprint_passed_if_ready", lambda *a, **kw: False)

    result = gnd.node_verdict(str(graph_path), "R8_section_fact_check", "pass", eval_json=str(eval_json), dispatch_downstream=False)

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["research_quality_gate"]["auto_run"] is True
    assert result["research_quality_gate"]["ok"] is True


def test_deepresearch_node_verdict_auto_run_blocks_bad_artifacts(tmp_path, monkeypatch):
    sid = "sprint-test-deepresearch-gate-auto-fail"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid)), encoding="utf-8")
    eval_json = tmp_path / f"{sid}.R8-eval.json"
    research_eval = out_dir / "run-research_eval.json"
    research_eval.write_text(json.dumps({
        "status": "passed",
        "output_dir": str(out_dir),
        "source_count": 1,
        "evidence_count": 1,
        "claim_count": 0,
        "section_count": 1,
        "unsupported_rate": 0.0,
        "citation_accuracy": 1.0,
    }), encoding="utf-8")
    (out_dir / "report_ast.json").write_text(json.dumps({
        "chapters": [{"sections": [{"id": "s1", "title": "Section"}]}],
    }), encoding="utf-8")
    (out_dir / "final.md").write_text("Unsupported claim [cite:ev_abc123].\n", encoding="utf-8")
    eval_json.write_text(json.dumps({
        "verdict": "PASS",
        "research_eval_json": str(research_eval),
    }), encoding="utf-8")

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)

    result = gnd.node_verdict(str(graph_path), "R8_section_fact_check", "pass", eval_json=str(eval_json), dispatch_downstream=False)

    assert result["ok"] is False
    assert result["reason"] == "deepresearch_quality_gate_failed"
    assert result["research_quality_gate"]["auto_run"] is True
    assert "claim_count_zero" in result["research_quality_gate"]["gate"]["errors"]
