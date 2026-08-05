from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


HARNESS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS / "lib"))

from plugins.autosci.operators.scientific_lifecycle.registry import registration_entries  # noqa: E402
from research_orchestration.routing import select_production_route  # noqa: E402
from research_orchestration.runtime import (  # noqa: E402
    FileWorkflowCatalog,
    default_production_resolver,
)


SELECTION = HARNESS / "config" / "research-workflow-selection.v1.json"
ROUTE_METADATA = HARNESS / "plugins" / "autosci" / "config" / "research_production_route.v1.json"


def _catalog() -> FileWorkflowCatalog:
    return FileWorkflowCatalog(
        harness_root=HARNESS,
        selection_path=SELECTION,
        entrypoint_aliases={
            "research_synthesis": {"web_fetch": "seed_fetch"},
            "literature_synthesis": {"source_discovery": "source_discovery"},
            "scientific_lifecycle": {"source_discovery": "literature_discover"},
            "workflow_evolution": {"workflow_evolve": "workflow_evolve"},
        },
    )


@pytest.mark.parametrize(
    ("prompt", "seeds", "semantic_start", "physical_start"),
    [
        ("Analyze https://example.test/report", [{"kind": "url", "value": "https://example.test/report"}], "web_fetch", "seed_fetch"),
        ("Synthesize paper", [{"kind": "pdf", "value": "paper.pdf"}], "paper_ingest", "paper_ingest"),
        ("Synthesize notes", [{"kind": "markdown", "value": "notes.md"}], "material_ingest", "material_ingest"),
        ("Survey fault-tolerant databases", None, "source_discovery", "source_discovery"),
    ],
)
def test_route_selection_and_physical_entry_table(
    prompt: str,
    seeds: list[dict] | None,
    semantic_start: str,
    physical_start: str,
) -> None:
    decision = select_production_route(prompt, seed_inputs=seeds)
    workflow = _catalog().load(decision)

    assert decision.start_stage == semantic_start
    assert workflow["start_node"] == physical_start
    assert workflow["nodes"][0]["node_id"] == physical_start


def test_local_material_route_prunes_unreachable_paper_read_scope() -> None:
    decision = select_production_route(
        "Synthesize notes",
        seed_inputs=[{"kind": "markdown", "value": "notes.md"}],
    )
    workflow = _catalog().load(decision)
    paper_analyze = next(node for node in workflow["nodes"] if node["node_id"] == "paper_analyze")

    assert paper_analyze["depends_on"] == ["material_ingest"]
    assert paper_analyze["read_scope"] == [
        "artifacts/scientific/scientific_research_lifecycle_full_v1/01_paper/research_material.v1.json"
    ]


def test_unified_registry_has_one_binding_per_identity_and_covers_every_reachable_node(tmp_path: Path) -> None:
    entries = registration_entries()
    identities = [item["physical_operator_id"] for item in entries]
    assert len(identities) == len(set(identities))
    resolver = default_production_resolver(workspace_root=tmp_path)
    assert set(resolver.operator_ids()) == set(identities)

    decisions = [
        select_production_route("Analyze https://example.test/report", seed_inputs=[{"kind": "url", "value": "https://example.test/report"}]),
        select_production_route("Synthesize paper", seed_inputs=[{"kind": "pdf", "value": "paper.pdf"}]),
        select_production_route("Synthesize notes", seed_inputs=[{"kind": "markdown", "value": "notes.md"}]),
        select_production_route("Survey fault-tolerant databases"),
        select_production_route("Import external evidence", seed_inputs=[{"kind": "external_evidence", "value": "prior.json"}], run_mode="import_evidence"),
    ]
    for decision in decisions:
        workflow = _catalog().load(decision)
        for node in workflow["nodes"]:
            resolved = resolver.resolve(node["physical_operator"])
            assert resolved["operator_id"] == node["physical_operator"]


def test_workflow_evolution_is_proposal_only_explicit_route() -> None:
    decision = select_production_route(
        "Analyze the failed workflow and propose a repair",
        explicit_workflow="workflow_evolution",
    )
    workflow = _catalog().load(decision)
    assert decision.start_stage == "workflow_evolve"
    assert workflow["start_node"] == "workflow_evolve"
    assert [node["node_id"] for node in workflow["nodes"]] == ["workflow_evolve"]


def test_production_route_metadata_remains_opt_in_and_rejects_temporary_default() -> None:
    payload = json.loads(ROUTE_METADATA.read_text(encoding="utf-8"))
    assert payload["status"] == "production_opt_in"
    assert payload["active_by_default"] is False
    assert payload["orchestrator"].endswith(":SolarResearchRuntime")
    assert payload["temporary_backend_forbidden_as_default"] == "real_data_research.py"
    assert len(payload["routes"]) == 5
