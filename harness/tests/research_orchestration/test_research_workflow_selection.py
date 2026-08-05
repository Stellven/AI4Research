from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from research_orchestration.selection import (  # noqa: E402
    REQUIRED_NORMALIZED_FIELDS,
    WorkflowSelectionError,
    load_and_normalize_workflow,
    load_workflow_selection,
    select_research_workflow,
)


def test_url_synthesis_selection_loads_real_skeleton() -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow(
        {"workflow_kind": "research_synthesis", "seed_kind": "url"},
        selection,
        ROOT,
    )
    workflow = load_and_normalize_workflow(selected, ROOT)

    assert workflow["workflow_id"] == "research_synthesis_v1"
    assert workflow["start_node"] == "seed_fetch"
    assert workflow["nodes"][0]["node_id"] == "seed_fetch"
    assert all(REQUIRED_NORMALIZED_FIELDS <= set(node) for node in workflow["nodes"])
    assert workflow["nodes"][0]["expected_output_artifacts"] == [
        "artifacts/research_synthesis_v1/seed/seed_snapshot.json"
    ]
    assert workflow["nodes"][0]["gate_deliverable"] == "artifacts/research_synthesis_v1/seed/seed_snapshot.json"


def test_topic_synthesis_uses_literature_route() -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow(
        {"workflow_kind": "literature_synthesis", "seed_kind": "topic"},
        selection,
        ROOT,
    )

    assert selected["workflow_id"] == "research_synthesis_v1"
    assert selected["start_node"] == "seed_fetch"


def test_scientific_lifecycle_selection_supports_existing_id_nodes() -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow({"workflow_kind": "scientific_lifecycle"}, selection, ROOT)
    workflow = load_and_normalize_workflow(selected, ROOT)

    assert workflow["workflow_id"] == "scientific_research_lifecycle_full_v1"
    assert workflow["nodes"][0]["node_id"] == "literature_discover"
    assert all("node_id" in node and "depends_on" in node for node in workflow["nodes"])


def test_workflow_evolution_selection_is_independent_capability() -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow({"workflow_kind": "workflow_evolution"}, selection, ROOT)
    workflow = load_and_normalize_workflow(selected, ROOT)

    assert [node["node_id"] for node in workflow["nodes"]] == ["workflow_evolve"]
    assert workflow["nodes"][0]["depends_on"] == []
    assert workflow["nodes"][0]["required_for_completion"] is True


def test_selection_rejects_unknown_start_node(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps({"workflow_id": "wf", "nodes": [{"node_id": "a", "depends_on": []}]}),
        encoding="utf-8",
    )
    with pytest.raises(WorkflowSelectionError, match="unknown start node"):
        load_and_normalize_workflow(
            {
                "workflow_id": "wf",
                "workflow_kind": "research_synthesis",
                "workflow_path": str(workflow),
                "start_node": "missing",
            },
            tmp_path,
        )


def test_selection_rejects_cycle(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps(
            {
                "workflow_id": "wf",
                "nodes": [
                    {"node_id": "a", "depends_on": ["b"]},
                    {"node_id": "b", "depends_on": ["a"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(WorkflowSelectionError, match="cycle detected"):
        load_and_normalize_workflow(
            {
                "workflow_id": "wf",
                "workflow_kind": "research_synthesis",
                "workflow_path": str(workflow),
                "start_node": "a",
            },
            tmp_path,
        )


def test_selection_rejects_path_escape(tmp_path: Path) -> None:
    selection = {
        "routes": [
            {
                "workflow_kind": "research_synthesis",
                "workflow_id": "wf",
                "workflow_path": "../outside.json",
                "start_node": "a",
            }
        ]
    }
    with pytest.raises(WorkflowSelectionError, match="escapes harness root"):
        select_research_workflow({"workflow_kind": "research_synthesis"}, selection, tmp_path)
