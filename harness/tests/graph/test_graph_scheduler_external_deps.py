from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HARNESS_LIB = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_scheduler  # noqa: E402


def test_external_depends_on_blocks_ready_nodes(monkeypatch, tmp_path):
    graph = {
        "sprint_id": "epic-external",
        "nodes": [
            {
                "id": "S01_requirements",
                "status": "blocked",
                "depends_on": ["external:sprint-browser-agent-cutover"],
                "write_scope": ["sprints/*prd.md"],
                "acceptance": ["requirements ready"],
                "required_capabilities": ["planning"],
            }
        ],
    }
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", tmp_path)

    validation = graph_scheduler.validate_graph(graph)
    blocked = graph_scheduler.blocked_external_prerequisites(graph)

    assert validation["ok"] is True
    assert blocked
    assert blocked[0]["sprint_id"] == "sprint-browser-agent-cutover"
    assert graph_scheduler.ready_nodes(graph) == []


def test_external_depends_on_allows_ready_after_upstream_passed(monkeypatch, tmp_path):
    graph = {
        "sprint_id": "epic-external",
        "nodes": [
            {
                "id": "S01_requirements",
                "status": "pending",
                "depends_on": ["external:sprint-browser-agent-cutover"],
                "write_scope": ["sprints/*prd.md"],
                "acceptance": ["requirements ready"],
                "required_capabilities": ["planning"],
            }
        ],
    }
    (tmp_path / "sprint-browser-agent-cutover.status.json").write_text(
        json.dumps({"status": "passed", "phase": "completed"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", tmp_path)

    assert graph_scheduler.blocked_external_prerequisites(graph) == []
    assert [node["id"] for node in graph_scheduler.ready_nodes(graph)] == ["S01_requirements"]


def test_ready_nodes_does_not_raise_parallelism_quality_during_inflight():
    graph = {
        "sprint_id": "runtime-parallelism-quality",
        "quality_gates": {"parallelism": {"min_ready_width": 1}},
        "nodes": [
            {
                "id": "S1",
                "status": "dispatched",
                "depends_on": [],
                "write_scope": ["sprints/S1.md"],
                "acceptance": ["S1 done"],
                "required_capabilities": ["implementation"],
            },
            {
                "id": "S2",
                "status": "pending",
                "depends_on": ["S1"],
                "write_scope": ["sprints/S2.md"],
                "acceptance": ["S2 done"],
                "required_capabilities": ["implementation"],
            },
        ],
    }

    validation = graph_scheduler.validate_graph(graph)
    assert any(str(error).startswith("parallelism_quality:") for error in validation["errors"])
    assert graph_scheduler.ready_nodes(graph) == []


def test_ready_nodes_still_raises_structural_validation_errors():
    graph = {
        "sprint_id": "runtime-structural-error",
        "nodes": [
            {
                "id": "S2",
                "status": "pending",
                "depends_on": ["S1"],
                "write_scope": ["sprints/S2.md"],
                "acceptance": ["S2 done"],
                "required_capabilities": ["implementation"],
            },
        ],
    }

    with pytest.raises(ValueError, match="S2 depends on missing node S1"):
        graph_scheduler.ready_nodes(graph)


def test_enqueue_ready_rechecks_admission_before_queueing_stale_assignment(monkeypatch, tmp_path):
    graph = {
        "sprint_id": "runtime-admission",
        "nodes": [
            {
                "id": "S1",
                "status": "pending",
                "depends_on": [],
                "write_scope": ["sprints/S1.md"],
                "acceptance": ["S1 done"],
                "required_capabilities": ["implementation"],
            },
            {
                "id": "S2",
                "status": "pending",
                "depends_on": ["S1"],
                "write_scope": ["sprints/S2.md"],
                "acceptance": ["S2 done"],
                "required_capabilities": ["implementation"],
            },
        ],
    }
    graph_path = tmp_path / "runtime-admission.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(
        graph_scheduler,
        "assign_ready",
        lambda *args, **kwargs: {
            "assigned": [{"node": "S2", "pane": "pane-1"}],
            "queued": [],
            "batch": ["S2"],
            "blocked_prerequisites": [],
            "capability_enrichment": {},
        },
    )

    result = graph_scheduler.enqueue_ready(graph, str(graph_path), [{"pane": "pane-1"}], dry_run=True)

    assert result["enqueued"] == []
    assert result["queued"][0]["reason"] == "admission_rejected"
    assert result["queued"][0]["details"]["reason"] == "dependencies_unmet"
    assert result["queued"][0]["details"]["unmet_dependencies"] == ["S1"]
