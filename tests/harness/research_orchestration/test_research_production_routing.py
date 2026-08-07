from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.resolver import (  # noqa: E402
    PhysicalOperatorBinding,
    PhysicalOperatorResolutionError,
    PhysicalOperatorResolver,
)
from research_orchestration.routing import (  # noqa: E402
    ResearchRoutingError,
    apply_task_conditions,
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


def _conditional_workflow() -> dict:
    return {
        "workflow_id": "conditional-research",
        "nodes": [
            {"node_id": "claim_extract", "depends_on": [], "read_scope": [], "write_scope": ["claims.json"]},
            {"node_id": "method_extract", "depends_on": [], "read_scope": [], "write_scope": ["methods.json"]},
            {"node_id": "code_evidence_map", "depends_on": ["claim_extract"], "read_scope": ["claims.json"], "write_scope": ["code.json"]},
            {"node_id": "claim_verify", "depends_on": ["claim_extract", "code_evidence_map"], "read_scope": ["claims.json", "code.json"], "write_scope": ["verdict.json"]},
            {"node_id": "report_plan", "depends_on": ["claim_verify"], "read_scope": ["verdict.json"], "write_scope": ["plan.json"]},
            {"node_id": "report_draft", "depends_on": ["report_plan"], "read_scope": ["plan.json"], "write_scope": ["report.json"]},
        ],
    }


def test_conditional_graph_skips_code_mapping_without_code_and_keeps_downstream_report() -> None:
    contract = {"user_intent": "Synthesize the supplied Markdown", "constraints": {"repository_inputs": []}}

    selected = apply_task_conditions(_conditional_workflow(), contract)

    by_id = {item["node_id"]: item for item in selected["nodes"]}
    assert "code_evidence_map" not in by_id
    assert by_id["claim_verify"]["depends_on"] == ["claim_extract", "method_extract"]
    assert by_id["report_draft"]["depends_on"] == ["report_plan", "claim_verify", "method_extract"]
    skip = next(item for item in selected["conditional_skips"] if item["node_id"] == "code_evidence_map")
    assert skip["status"] == "skipped"
    assert "No code" in skip["reason"]


def test_conditional_graph_runs_code_mapping_for_repository_input() -> None:
    contract = {
        "user_intent": "Synthesize the material with repository evidence",
        "constraints": {"repository_inputs": [{"snapshot_path": "inputs/repository"}]},
    }

    selected = apply_task_conditions(_conditional_workflow(), contract)

    by_id = {item["node_id"]: item for item in selected["nodes"]}
    assert "code_evidence_map" in by_id
    assert "inputs/repository" in by_id["code_evidence_map"]["read_scope"]
    assert "code_evidence_map" in by_id["claim_verify"]["depends_on"]
    assert all(item["node_id"] != "code_evidence_map" for item in selected["conditional_skips"])


def test_conditional_graph_preserves_experiment_status_for_claim_verification() -> None:
    workflow = _conditional_workflow()
    workflow["nodes"].extend(
        [
            {"node_id": "idea_generate", "depends_on": ["method_extract"], "read_scope": [], "write_scope": ["idea.json"]},
            {"node_id": "idea_evaluate", "depends_on": ["idea_generate"], "read_scope": ["idea.json"], "write_scope": ["idea-eval.json"]},
            {"node_id": "experiment_design", "depends_on": ["idea_evaluate"], "read_scope": ["idea-eval.json"], "write_scope": ["plan.json"]},
            {"node_id": "experiment_approval_gate", "depends_on": ["experiment_design"], "read_scope": ["plan.json"], "write_scope": ["approval.json"]},
            {"node_id": "experiment_run", "depends_on": ["experiment_approval_gate"], "read_scope": ["approval.json"], "write_scope": ["result.json"]},
            {"node_id": "experiment_monitor", "depends_on": ["experiment_run"], "read_scope": ["result.json"], "write_scope": ["status.json"]},
        ]
    )
    contract = {
        "user_intent": "Synthesize the material, design an experiment, and verify claims.",
        "constraints": {"repository_inputs": []},
    }

    selected = apply_task_conditions(workflow, contract)

    by_id = {item["node_id"]: item for item in selected["nodes"]}
    claim_verify = by_id["claim_verify"]
    approval_gate = by_id["experiment_approval_gate"]
    assert "experiment_monitor" in claim_verify["depends_on"]
    assert (
        "artifacts/scientific/scientific_research_lifecycle_full_v1/07_experiment_result/experiment_status.v1.json"
        in claim_verify["read_scope"]
    )
    assert (
        "artifacts/scientific/scientific_research_lifecycle_full_v1/07_experiment_result/experiment_result.v1.json"
        in claim_verify["read_scope"]
    )
    assert (
        "artifacts/scientific/scientific_research_lifecycle_full_v1/07_experiment_result/experiment_result.v1.json"
        in approval_gate["write_scope"]
    )
