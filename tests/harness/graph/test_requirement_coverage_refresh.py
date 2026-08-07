#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = (Path(__file__).resolve().parents[3] / 'harness') / "lib"
sys.path.insert(0, str(HARNESS_LIB))


def test_node_verdict_refreshes_requirement_coverage_artifacts(tmp_path, monkeypatch):
    import graph_node_dispatcher as gnd

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)

    sid = "sprint-test-coverage-refresh"
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": "N1",
                "goal": "Implement first slice",
                "depends_on": [],
                "acceptance": ["slice one exists"],
                "status": "reviewing",
                "requirement_ids": ["REQ-001"],
            },
            {
                "id": "N2",
                "goal": "Implement second slice",
                "depends_on": ["N1"],
                "acceptance": ["slice two exists"],
                "status": "pending",
                "requirement_ids": ["REQ-001"],
            },
        ],
        "node_results": {},
        "gate_results": {},
    }
    (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{sid}.status.json").write_text(json.dumps({"sprint_id": sid, "status": "active"}), encoding="utf-8")
    (sprints / f"{sid}.requirement_ir.json").write_text(
        json.dumps(
            {
                "id": "req-test",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "source_text": "All planned slices are delivered.",
                        "success_criteria": ["both nodes done"],
                        "verification_method": "task_graph_closeout",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    stale_trace = {
        "schema_version": "solar.requirement_trace.v1",
        "requirement_ir_id": "req-test",
        "sprint_id": sid,
        "items": [{"requirement_id": "REQ-001", "mapped_nodes": ["R1", "R2"], "final_status": "missing"}],
    }
    (sprints / f"{sid}.requirement_trace.json").write_text(json.dumps(stale_trace), encoding="utf-8")
    (sprints / f"{sid}.finalized").write_text("", encoding="utf-8")

    monkeypatch.setattr(gnd, "release_lease", lambda *a, **kw: {"released": False})
    monkeypatch.setattr(gnd, "_mark_parent_sprint_passed_if_ready", lambda *a, **kw: False)

    eval_json = sprints / f"{sid}.N1-eval.json"
    eval_json.write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    result = gnd.node_verdict(
        str(sprints / f"{sid}.task_graph.json"),
        "N1",
        "pass",
        eval_json=str(eval_json),
        dispatch_downstream=False,
    )

    trace = json.loads((sprints / f"{sid}.requirement_trace.json").read_text(encoding="utf-8"))
    coverage = json.loads((sprints / f"{sid}.coverage_report.json").read_text(encoding="utf-8"))
    verdict = json.loads((sprints / f"{sid}.acceptance_verdict.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["coverage_refresh"]["ok"] is True
    assert trace["items"][0]["mapped_nodes"] == ["N1", "N2"]
    assert coverage["summary"]["partial"] == 1
    # Mid-run / incomplete-or-uncovered graph is non-PASS (IN_PROGRESS while the
    # graph is still running, FAIL only once complete-but-uncovered); either way the
    # refresh must clear a stale `.finalized`.
    assert verdict["verdict"] != "PASS"
    assert not (sprints / f"{sid}.finalized").exists()
