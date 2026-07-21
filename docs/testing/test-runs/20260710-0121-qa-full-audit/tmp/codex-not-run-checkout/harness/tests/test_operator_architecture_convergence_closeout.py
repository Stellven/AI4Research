from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import operator_architecture_convergence_closeout as oacc  # noqa: E402


def test_auto_closeout_operator_architecture_convergence_generates_artifacts(tmp_path, monkeypatch):
    runtime_root = tmp_path
    sprints = runtime_root / "sprints"
    sprints.mkdir()
    sid = oacc.SPRINT_ID

    (sprints / f"{sid}.requirement_ir.json").write_text(
        json.dumps({
            "requirements": [{"id": "REQ-000"}, {"id": "REQ-001"}, {"id": "REQ-002"}, {"id": "REQ-003"}],
            "required_gates": ["G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"],
        }),
        encoding="utf-8",
    )
    for suffix in [".design.md", ".plan.md", ".N1-handoff.md", ".N2-handoff.md", ".N3-handoff.md", ".N4-handoff.md"]:
        payload = f"artifact {suffix}"
        (sprints / f"{sid}{suffix}").write_text(payload, encoding="utf-8")
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps({
            "nodes": [
                {"id": "N1", "gate": "G_PLAN"},
                {"id": "N2", "gate": "G_PLAN"},
                {"id": "N3", "gate": "G_PLAN"},
                {"id": "N4", "gate": "G_VERIFY"},
                {"id": "N5", "gate": "G_REVIEW"},
            ],
            "required_gates": ["G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"],
        }),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_closeout(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "node_results": {oacc.NODE_ID: {"ok": True}}, "status_sync": {"ok": True}}

    monkeypatch.setattr(oacc, "auto_closeout_graph_nodes", fake_closeout)

    result = oacc.auto_closeout_operator_architecture_convergence(runtime_root)

    assert result["ok"] is True
    traceability_path = sprints / f"{sid}.traceability.json"
    handoff_path = sprints / f"{sid}.{oacc.NODE_ID}-handoff.md"
    assert traceability_path.exists()
    assert handoff_path.exists()
    traceability = json.loads(traceability_path.read_text(encoding="utf-8"))
    assert traceability["sprint_id"] == sid
    assert traceability["review_contract"]["node_id"] == oacc.NODE_ID
    normalized_graph = json.loads((sprints / f"{sid}.task_graph.json").read_text(encoding="utf-8"))
    assert normalized_graph["required_gates"] == ["G_PLAN", "G_VERIFY", "G_REVIEW"]
    assert captured["reason"] == "operator_architecture_convergence_traceability_compiled"
