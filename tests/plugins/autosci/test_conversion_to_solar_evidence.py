from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN = (Path(__file__).resolve().parents[3] / 'harness' / 'plugins' / 'autosci')
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from adapters.autosci_to_claim_verdict import convert as convert_verdict
from adapters.autosci_to_code_evidence_map import convert as convert_code_map
from adapters.autosci_to_experiment_plan import convert as convert_plan
from adapters.autosci_to_experiment_result import convert as convert_result
from adapters.autosci_to_experiment_status import convert as convert_status
from adapters.autosci_to_idea_candidate import convert as convert_idea
from adapters.autosci_to_idea_evaluation import convert as convert_idea_eval
from adapters.autosci_to_literature_discovery import convert as convert_literature
from adapters.autosci_to_research_claims import convert as convert_claims
from adapters.autosci_to_research_graph_update import convert as convert_graph
from adapters.autosci_to_research_memory_update import convert as convert_memory
from adapters.autosci_to_research_method import convert as convert_method
from adapters.autosci_to_research_paper import convert as convert_paper
from adapters.autosci_to_scientific_report import convert as convert_report
from adapters.autosci_to_workflow_evolution import convert as convert_workflow


def assert_evidence_shape(payload: dict, schema: str) -> None:
    assert payload["schema"] == schema
    for field in ["task_id", "sprint_id", "node_id", "status", "inputs", "outputs", "artifacts", "provenance", "limitations"]:
        assert field in payload
    assert payload["provenance"]["implementation_package"] == "plugins/autosci"


def test_raw_claims_convert_to_unverified_solar_claims() -> None:
    raw = json.loads((FIXTURES / "sample_autosci_raw_claims.json").read_text(encoding="utf-8"))
    payload = convert_claims(raw, {"task_id": "t", "sprint_id": "s", "node_id": "n", "inputs": {}})
    assert_evidence_shape(payload, "research_claims.v1")
    assert payload["outputs"]["claims"]
    assert all(claim["verification_status"] == "unverified" for claim in payload["outputs"]["claims"])
    assert all(claim["source_anchor"] for claim in payload["outputs"]["claims"])


def test_core_phase4_converters_emit_expected_schema_names() -> None:
    envelope = {"task_id": "t", "sprint_id": "s", "node_id": "n", "inputs": {}}
    paper = convert_paper({"paper_id": "p", "title": "T", "source_type": "markdown", "source_ref": "sample.md"}, envelope)
    plan = convert_plan({}, envelope)
    result = convert_result({}, envelope)
    status = convert_status({}, envelope)
    verdict = convert_verdict({}, envelope)
    report = convert_report({}, envelope)
    method = convert_method({}, envelope)
    code_map = convert_code_map({}, envelope)
    idea = convert_idea({}, envelope)
    idea_eval = convert_idea_eval({}, envelope)
    assert_evidence_shape(paper, "research_paper.v1")
    assert_evidence_shape(plan, "experiment_plan.v1")
    assert_evidence_shape(result, "experiment_result.v1")
    assert_evidence_shape(status, "experiment_status.v1")
    assert_evidence_shape(verdict, "claim_verdict.v1")
    assert_evidence_shape(report, "scientific_report.v1")
    assert_evidence_shape(method, "research_method.v1")
    assert_evidence_shape(code_map, "code_evidence_map.v1")
    assert_evidence_shape(idea, "idea_candidate.v1")
    assert_evidence_shape(idea_eval, "idea_evaluation.v1")


def test_research_paper_converter_does_not_fixture_fill_failed_parse() -> None:
    envelope = {"task_id": "t", "sprint_id": "s", "node_id": "n", "inputs": {}}
    payload = convert_paper(
        {
            "paper_id": "p-missing",
            "title": "Missing Source",
            "source_type": "unknown",
            "source_ref": "raw/papers/missing.pdf",
            "parse_status": "failed",
            "status": "failed",
            "sections": [],
        },
        envelope,
    )
    serialized = json.dumps(payload)
    assert "Fixture abstract" not in serialized
    assert "sample_paper.md#abstract" not in serialized
    section = payload["outputs"]["paper"]["sections"][0]
    assert section["section_id"] == "parse-failure"
    assert payload["status"] == "failed"


def test_phase9_converters_emit_memory_graph_and_discovery_schema_names() -> None:
    envelope = {"task_id": "t", "sprint_id": "s", "node_id": "n", "inputs": {}}
    memory = convert_memory({"paper_id": "p", "title": "T"}, envelope)
    graph = convert_graph({"paper_id": "p", "source_ref": "sample.md"}, envelope)
    literature = convert_literature({"query": "solar evidence", "mode": "fixture"}, envelope)
    assert_evidence_shape(memory, "research_memory_update.v1")
    assert_evidence_shape(graph, "research_graph_update.v1")
    assert_evidence_shape(literature, "literature_discovery.v1")
    assert memory["outputs"]["changes"][0]["operation"] == "propose"
    assert graph["outputs"]["edges"]
    assert literature["outputs"]["candidates"]


def test_literature_converter_does_not_synthesize_fixture_candidates_by_default() -> None:
    envelope = {"task_id": "t", "sprint_id": "s", "node_id": "n", "inputs": {}}
    literature = convert_literature({"query": "solar evidence"}, envelope)
    assert_evidence_shape(literature, "literature_discovery.v1")
    assert literature["outputs"]["candidates"] == []


def test_phase16_converter_emits_workflow_evolution_schema() -> None:
    envelope = {"task_id": "t", "sprint_id": "s", "node_id": "n", "inputs": {}}
    payload = convert_workflow({
        "failed_nodes": [{"node_id": "experiment_run"}],
        "gate_rejection_reasons": [{"gate_id": "G_EXPERIMENT_RUN", "reasons": ["missing log"]}],
        "ambiguous_manuals_or_prompts": [{"manual_id": "m"}],
        "insufficient_schemas": [{"schema": "experiment_result.v1"}],
        "poor_operator_bindings": [],
        "human_intervention_points": [],
        "runtime_errors": [{"error_id": "runtime.missing-log"}],
        "evidence_ids": ["experiment_run", "G_EXPERIMENT_RUN"],
        "proposed_changes": [
            {
                "change_id": "change.manual",
                "category": "manual",
                "target": "manual",
                "description": "Clarify retry.",
                "evidence_ids": ["experiment_run"],
                "review_required": True,
                "application_state": "proposed_only",
            }
        ],
        "review": {
            "human_accept_reject_required": True,
            "protected_core_edits_applied": False,
            "application_state": "proposed_only",
        },
    }, envelope)
    assert_evidence_shape(payload, "workflow_evolution.v1")
    assert payload["outputs"]["evolution"]["approval_state"] == "proposed"
