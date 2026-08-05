from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.resolver import (  # noqa: E402
    PhysicalOperatorBinding,
    PhysicalOperatorResolutionError,
    PhysicalOperatorResolver,
)
from research_orchestration.routing import (  # noqa: E402
    ResearchRoutingError,
    select_production_route,
    workflow_from_entry_stage,
)


@pytest.mark.parametrize(
    ("prompt", "seed_inputs", "seed_kind", "start_stage"),
    [
        ("分析 https://example.test/paper 并用中文输出", None, "url", "web_fetch"),
        ("Synthesize this paper", [{"kind": "pdf", "value": "C:/data/paper.pdf"}], "pdf", "paper_ingest"),
        ("Summarize this note", [{"kind": "markdown", "value": "C:/data/note.md"}], "markdown", "material_ingest"),
        ("Summarize this text", [{"kind": "text", "value": "C:/data/note.txt"}], "markdown", "material_ingest"),
        ("Survey causal representation learning", None, "topic", "source_discovery"),
    ],
)
def test_production_route_selection_table(
    prompt: str,
    seed_inputs: list[dict] | None,
    seed_kind: str,
    start_stage: str,
) -> None:
    decision = select_production_route(prompt, seed_inputs=seed_inputs)

    assert decision.seed_kind == seed_kind
    assert decision.start_stage == start_stage
    assert decision.workflow_kind != "workflow_evolution"


def test_workflow_evolution_requires_explicit_or_matching_user_intent() -> None:
    normal = select_production_route("Research workflow scheduling techniques")
    explicit = select_production_route(
        "Analyze the failed workflow and propose a repair",
        explicit_workflow="workflow_evolution",
    )

    assert normal.workflow_kind != "workflow_evolution"
    assert explicit.workflow_kind == "workflow_evolution"


def test_workflow_entry_resolution_prunes_predecessors_and_keeps_descendants() -> None:
    decision = select_production_route("Survey trustworthy AI")
    workflow = {
        "workflow_id": "general-research",
        "nodes": [
            {"node_id": "web_fetch", "depends_on": []},
            {"node_id": "source_discovery", "depends_on": ["web_fetch"]},
            {"node_id": "synthesis", "depends_on": ["source_discovery"]},
        ],
    }

    selected = workflow_from_entry_stage(workflow, decision)

    assert selected["start_node"] == "source_discovery"
    assert [node["node_id"] for node in selected["nodes"]] == ["source_discovery", "synthesis"]
    assert selected["nodes"][0]["depends_on"] == []


def test_workflow_entry_resolution_fails_closed_when_stage_is_missing() -> None:
    decision = select_production_route(
        "Summarize the note",
        seed_inputs=[{"kind": "text", "value": "note.txt"}],
    )
    with pytest.raises(ResearchRoutingError, match="no physical entry node for stage material_ingest"):
        workflow_from_entry_stage(
            {"workflow_id": "incomplete", "nodes": [{"node_id": "paper_ingest", "depends_on": []}]},
            decision,
        )


def test_physical_operator_resolver_rejects_unknown_disabled_and_duplicate_bindings() -> None:
    runner = lambda request: request
    resolver = PhysicalOperatorResolver([PhysicalOperatorBinding("known", runner)])
    disabled = PhysicalOperatorResolver([PhysicalOperatorBinding("disabled", runner, enabled=False)])

    assert resolver.resolve("known")["runtime_state"] == "active"
    with pytest.raises(PhysicalOperatorResolutionError, match="unknown physical operator"):
        resolver.resolve("missing")
    with pytest.raises(PhysicalOperatorResolutionError, match="disabled physical operator"):
        disabled.resolve("disabled")
    with pytest.raises(PhysicalOperatorResolutionError, match="duplicate physical operator binding"):
        PhysicalOperatorResolver(
            [PhysicalOperatorBinding("same", runner), PhysicalOperatorBinding("same", runner)]
        )
