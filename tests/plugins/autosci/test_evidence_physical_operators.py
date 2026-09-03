from __future__ import annotations

import json
from pathlib import Path
import hashlib

import jsonschema
import pytest

from harness.plugins.autosci.operators.scientific_lifecycle.evidence import (
    OPERATOR_SPECS,
    execute_operator,
    registration_entries,
    resolve_entrypoint,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = REPO_ROOT / "harness" / "schemas" / "evidence"
NODE_IDS = tuple(OPERATOR_SPECS)
VERSION_OVERRIDES = {
    "claim_extract": "1.2.0",
    "claim_select_one": "1.0.0",
    "method_extract": "1.3.0",
}


def paper_evidence() -> dict:
    return {
        "schema": "research_paper.v1",
        "task_id": "task-evidence",
        "sprint_id": "run-evidence",
        "node_id": "paper_ingest",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "paper": {
                "paper_id": "paper-bounded",
                "title": "Bounded Evidence Operators",
                "source_type": "markdown",
                "source_ref": "inputs/paper.md",
                "parse_status": "parsed",
                "sections": [
                    {
                        "section_id": "methods",
                        "title": "Methods",
                        "text": "We parse each source document. We compare the output hash with a deterministic baseline.",
                        "source_anchor": "inputs/paper.md#methods",
                    },
                    {
                        "section_id": "results",
                        "title": "Results",
                        "text": "The bounded parser improves latency by 20 percent compared with the baseline.",
                        "source_anchor": "inputs/paper.md#results",
                    },
                ],
            }
        },
        "artifacts": [],
        "provenance": {"operator_id": "fixture", "implementation_package": "tests", "timestamp": "2026-08-05T00:00:00Z"},
        "limitations": [],
    }


def discovery_evidence(workspace: Path) -> dict:
    return {
        "schema": "literature_discovery.v1",
        "task_id": "task-evidence",
        "sprint_id": "run-evidence",
        "node_id": "literature_discover",
        "status": "completed",
        "inputs": {"query": "bounded evidence"},
        "outputs": {
            "query": "bounded evidence",
            "candidates": [
                {
                    "candidate_id": "paper-001",
                    "title": "Bounded Evidence Operators",
                    "source_channels": ["local"],
                    "ranking_score": 0.9,
                    "ranking_rationale": "A real scoped source used by the operator test.",
                    "dedup_status": "new",
                    "fetch_status": "not_requested",
                    "source_ref": "inputs/paper.md",
                },
                {
                    "candidate_id": "paper-002",
                    "title": "Bounded Evidence Replication",
                    "source_channels": ["local"],
                    "ranking_score": 0.8,
                    "ranking_rationale": "A second real scoped source used to prove cardinality.",
                    "dedup_status": "new",
                    "fetch_status": "not_requested",
                    "source_ref": "inputs/paper-two.md",
                },
            ],
        },
        "artifacts": [],
        "provenance": {"operator_id": "test-input", "implementation_package": "tests"},
        "limitations": [],
    }


def claims_evidence() -> dict:
    return {
        "schema": "research_claims.v1",
        "task_id": "task-evidence",
        "sprint_id": "run-evidence",
        "node_id": "claim_extract",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "claims": [
                {
                    "claim_id": "claim-001",
                    "text": "The bounded parser improves latency by 20 percent.",
                    "source_anchor": "inputs/paper.md#results",
                    "testability": "testable",
                    "verification_status": "unverified",
                    "evidence_ids": ["inputs/paper.md#results"],
                }
            ]
        },
        "artifacts": [],
        "provenance": {"operator_id": "fixture", "implementation_package": "tests", "timestamp": "2026-08-05T00:00:00Z"},
        "limitations": [],
    }


def memory_evidence() -> dict:
    return {
        "schema": "research_memory_update.v1",
        "task_id": "task-evidence",
        "sprint_id": "run-evidence",
        "node_id": "memory_update_initial",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "changes": [
                {
                    "entity_type": "paper",
                    "entity_id": "paper-bounded",
                    "operation": "propose",
                    "path": "knowledge/research/papers/paper-bounded.md",
                    "evidence_ids": ["inputs/paper.md#methods"],
                }
            ]
        },
        "artifacts": [],
        "provenance": {"operator_id": "fixture", "implementation_package": "tests", "timestamp": "2026-08-05T00:00:00Z"},
        "limitations": [],
    }


def final_source_evidence() -> dict:
    return {
        "schema": "scientific_report.v1",
        "task_id": "task-evidence",
        "sprint_id": "run-evidence",
        "node_id": "report_draft",
        "status": "completed",
        "inputs": {},
        "outputs": {"report": {"title": "Bounded report", "sections": [{"title": "Findings", "content": "Traceable result."}]}},
        "artifacts": [],
        "provenance": {"operator_id": "fixture", "implementation_package": "tests", "timestamp": "2026-08-05T00:00:00Z"},
        "limitations": [],
    }


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    inputs = tmp_path / "inputs"
    code = inputs / "code"
    code.mkdir(parents=True)
    (inputs / "paper.md").write_text(
        "# Bounded Evidence Operators\n\n## Methods\nWe parse each source document. We compare the output hash with a deterministic baseline.\n\n"
        "## Results\nThe bounded parser improves latency by 20 percent compared with the baseline.\n",
        encoding="utf-8",
    )
    (inputs / "paper-two.md").write_text(
        "# Bounded Evidence Replication\n\n## Methods\n"
        "We evaluate the same parser with a second retained source and compare exact output hashes.\n\n"
        "## Results\nThe replicated run reduces parsing failures by 10 percent compared with the baseline.\n",
        encoding="utf-8",
    )
    (code / "parser.py").write_text(
        "def bounded_parser_improves_latency():\n    return '20 percent faster'\n",
        encoding="utf-8",
    )
    return tmp_path


def discovery_service(**_kwargs) -> dict:
    return {
        "query": "bounded evidence",
        "mode": "topic",
        "limit": 3,
        "status": "completed",
        "candidates": [
            {
                "candidate_id": "paper-001",
                "title": "Bounded Scientific Evidence",
                "source_channels": ["test_provider"],
                "ranking_score": 0.9,
                "ranking_rationale": "Matches the explicit query.",
                "dedup_status": "new",
                "fetch_status": "not_requested",
                "source_ref": "https://example.test/paper-001",
            }
        ],
        "limitations": ["Injected deterministic provider used by the physical operator test."],
        "artifacts": [],
    }


def request_for(node_id: str, workspace: Path) -> tuple[dict, dict]:
    payload: dict = {}
    services: dict = {}
    if node_id == "evidence_import":
        imported = workspace / "inputs" / "imported.json"
        imported.write_text('{"schema":"external.test.v1","value":"bounded"}', encoding="utf-8")
        payload = {
            "task_contract": {
                "supplied_evidence": [{
                    "artifact_id": "external-1",
                    "path": "inputs/imported.json",
                    "sha256": hashlib.sha256(imported.read_bytes()).hexdigest(),
                    "provenance": {"source": "prior-run"},
                }]
            }
        }
    elif node_id == "literature_discover":
        payload = {"query": "bounded evidence", "mode": "topic", "limit": 3}
        services["discover_literature"] = discovery_service
    elif node_id in {"paper_ingest", "material_ingest"}:
        payload = {"source": "inputs/paper.md", "allow_network_fetch": False}
    elif node_id == "discovery_ingest":
        discovery_path = workspace / "inputs" / "literature-discovery.json"
        discovery_path.write_text(json.dumps(discovery_evidence(workspace)), encoding="utf-8")
        payload = {"max_sources": 2, "allow_network_fetch": False}
    elif node_id == "source_assess":
        discovery = discovery_evidence(workspace)
        discovery["outputs"]["query"] = "dense sparse retrieval"
        discovery["outputs"]["candidates"][0]["title"] = "Dense and Sparse Retrieval Benchmark"
        discovery["outputs"]["candidates"][0]["source_channels"] = ["crossref"]
        discovery["outputs"]["candidates"][0]["doi"] = "10.0000/bounded"
        discovery["outputs"]["candidates"][1]["title"] = "Dense Sparse Retrieval Replication"
        discovery["outputs"]["candidates"][1]["source_channels"] = ["crossref"]
        discovery["outputs"]["candidates"][1]["doi"] = "10.0000/replication"
        paper = paper_evidence()
        paper["outputs"]["paper"]["paper_id"] = "paper-001"
        paper["outputs"]["paper"]["title"] = "Dense and Sparse Retrieval Benchmark"
        paper["outputs"]["paper"]["abstract"] = (
            "A public question-answering benchmark comparing dense and sparse retrieval methods."
        )
        paper["outputs"]["paper"]["identifiers"] = {"doi": "10.0000/bounded"}
        payload = {
            "discovery_evidence": discovery,
            "paper_evidence": paper,
        }
    elif node_id in {
        "paper_analyze",
        "content_analyze",
        "memory_update_initial",
        "claim_extract",
        "claim_select_one",
        "method_extract",
    }:
        payload = {"paper_evidence": paper_evidence()}
    elif node_id == "memory_update_final":
        payload = {"source_evidence": final_source_evidence()}
    elif node_id == "graph_update":
        payload = {"memory_evidence": memory_evidence()}
    elif node_id == "code_evidence_map":
        payload = {"claims_evidence": claims_evidence(), "repo_path": "inputs/code"}
    request = {
        "schema": "research_node_request.v1",
        "task_id": "task-evidence",
        "run_id": "run-evidence",
        "sprint_id": "run-evidence",
        "workflow_id": "scientific_research_lifecycle_full_v1",
        "node_id": node_id,
        "typed_inputs": {"payload": payload},
        "input_artifact_refs": [],
        "read_scope": ["inputs/"],
        "write_scope": [f"outputs/{node_id}.json"],
        "authorization": {"secret_refs": []},
        "issued_at": "2026-08-05T00:00:00Z",
    }
    if node_id == "discovery_ingest":
        discovery_path = workspace / "inputs" / "literature-discovery.json"
        request["input_artifact_refs"] = [{
            "artifact_id": "evidence.literature_discover",
            "path": "inputs/literature-discovery.json",
            "schema": "literature_discovery.v1",
            "sha256": hashlib.sha256(discovery_path.read_bytes()).hexdigest(),
        }]
        request["write_scope"] = ["outputs/discovery_ingest/"]
    return request, services


def validate_result_and_artifact(result: dict, workspace: Path) -> dict:
    result_schema = json.loads((SCHEMAS / "research_node_result.v1.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(result_schema).validate(result)
    assert result["status"] == "completed", result
    artifact_ref = result["output_artifacts"][0]
    artifact = json.loads((workspace / artifact_ref["path"]).read_text(encoding="utf-8"))
    artifact_schema = json.loads((SCHEMAS / f"{artifact['schema']}.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(artifact_schema).validate(artifact)
    expected_version = VERSION_OVERRIDES.get(artifact["provenance"]["node_id"], "1.1.0")
    assert artifact["provenance"]["operator_version"] == expected_version
    assert len(artifact["provenance"]["input_sha256"]) == 64
    assert len(artifact["provenance"]["output_sha256"]) == 64
    assert artifact["provenance"]["outcome_class"] == "success"
    return artifact


@pytest.mark.parametrize("node_id", NODE_IDS)
def test_each_evidence_operator_executes_real_positive_path(node_id: str, workspace: Path) -> None:
    request, services = request_for(node_id, workspace)
    result = execute_operator(request, services=services, workspace_root=workspace)
    artifact = validate_result_and_artifact(result, workspace)
    assert artifact["outputs"]
    if node_id == "claim_extract":
        claim = artifact["outputs"]["claims"][0]
        span = claim["citation_spans"][0]
        section = next(
            item
            for item in paper_evidence()["outputs"]["paper"]["sections"]
            if item["source_anchor"] == span["source_ref"]
        )
        normalized = " ".join(section["text"].split())
        assert normalized[span["start_char"]:span["end_char"]] == claim["text"] == span["quote"]
        assert span["source_text_sha256"] == hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def test_landscape_memory_update_projects_each_pre_report_evidence_class(
    workspace: Path,
) -> None:
    request, services = request_for("memory_update_initial", workspace)
    request["typed_inputs"]["payload"] = {
        "paper_evidence": paper_evidence(),
        "verdict_evidence": {
            "schema": "claim_verdict.v1",
            "outputs": {
                "verdicts": [
                    {
                        "claim_id": "claim-001",
                        "verdict": "supported",
                        "confidence": 0.9,
                        "evidence_ids": ["inputs/paper.md#results"],
                    }
                ]
            },
        },
        "research_method": {
            "schema": "research_method.v1",
            "outputs": {
                "methods": [
                    {
                        "method_id": "method-001",
                        "name": "Bounded parser",
                        "confidence": 0.8,
                        "evidence_ids": ["inputs/paper.md#methods"],
                    }
                ]
            },
        },
        "source_assessment": {
            "schema": "research_source_assessment.v1",
            "outputs": {
                "assessments": [
                    {
                        "source_id": "paper-bounded",
                        "decision": "selected",
                        "evidence_ids": ["inputs/paper.md#methods"],
                        "credibility": {"score": 0.85},
                    }
                ]
            },
        },
        "report_plan": {
            "schema": "scientific_report_plan.v1",
            "outputs": {
                "report_plan": {
                    "report_id": "landscape-plan-001",
                    "evidence_ids": ["inputs/paper.md#results"],
                    "reportable_claim_ids": ["claim-001"],
                }
            },
        },
    }

    result = execute_operator(request, services=services, workspace_root=workspace)
    artifact = validate_result_and_artifact(result, workspace)
    changes = artifact["outputs"]["changes"]

    assert {
        "paper",
        "claim_verdict",
        "research_method",
        "source_assessment",
        "research_landscape_plan",
    }.issubset({item["entity_type"] for item in changes})
    assert all(item["evidence_ids"] for item in changes)
    assert artifact["outputs"]["phase"] == "initial"


def test_composed_scheduler_node_routes_by_frozen_implementation_identity(
    workspace: Path,
) -> None:
    request, services = request_for("literature_discover", workspace)
    scheduled_node_id = "source_acquisition__7fd24db4_c01"
    request.update(
        {
            "node_id": scheduled_node_id,
            "scheduled_node_id": scheduled_node_id,
            "implementation_node_id": "literature_discover",
        }
    )

    result = execute_operator(request, services=services, workspace_root=workspace)

    assert result["status"] == "completed", result
    assert result["node_id"] == scheduled_node_id
    artifact = json.loads(
        (workspace / result["output_artifacts"][0]["path"]).read_text(encoding="utf-8")
    )
    assert artifact["provenance"]["node_id"] == scheduled_node_id


@pytest.mark.parametrize("node_id", NODE_IDS)
def test_each_evidence_operator_rejects_missing_required_input_as_product_failure(node_id: str, workspace: Path) -> None:
    request, _services = request_for(node_id, workspace)
    request["typed_inputs"] = {"payload": {}}
    request["input_artifact_refs"] = []
    result = execute_operator(request, workspace_root=workspace)
    assert result["status"] == "failed"
    assert result["status_is_terminal"] is True
    assert result["errors"][0]["error_type"] == "product_failure"
    assert result["output_artifacts"] == []


@pytest.mark.parametrize("node_id", NODE_IDS)
def test_each_evidence_operator_is_idempotent_for_same_identity_version_and_input(node_id: str, workspace: Path) -> None:
    request, services = request_for(node_id, workspace)
    first = execute_operator(request, services=services, workspace_root=workspace)
    second = execute_operator(request, services=services, workspace_root=workspace)
    assert first["status"] == second["status"] == "completed"
    assert first["output_artifacts"][0]["sha256"] == second["output_artifacts"][0]["sha256"]
    assert first["hashes"] == second["hashes"]
    if node_id != "discovery_ingest":
        assert "Idempotent replay" in second["limitations"][0]


def test_discovery_provider_failure_is_classified_as_environment_failure(workspace: Path) -> None:
    request, _services = request_for("literature_discover", workspace)

    def unavailable(**_kwargs):
        raise ConnectionError("provider unavailable")

    result = execute_operator(
        request,
        services={"discover_literature": unavailable},
        workspace_root=workspace,
    )
    assert result["status"] == "awaiting_external"
    assert result["status_is_terminal"] is False
    assert result["errors"][0]["error_type"] == "provider_environment_failure"
    artifact = json.loads((workspace / result["output_artifacts"][0]["path"]).read_text(encoding="utf-8"))
    assert artifact["status"] == "inconclusive"
    assert artifact["provenance"]["outcome_class"] == "provider_environment_failure"


def test_discovery_provider_failure_continues_with_frozen_local_seeds(workspace: Path) -> None:
    request, _services = request_for("literature_discover", workspace)
    local = workspace / "inputs" / "local-paper.md"
    local.write_text("# Local paper\n\nEvidence from a real local source.", encoding="utf-8")
    digest = hashlib.sha256(local.read_bytes()).hexdigest()
    request["typed_inputs"]["payload"]["local_sources"] = [
        {"path": str(local), "relative_path": "inputs/local-paper.md", "sha256": digest}
    ]

    def unavailable(**_kwargs):
        raise ConnectionError("provider unavailable")

    result = execute_operator(
        request,
        services={"discover_literature": unavailable},
        workspace_root=workspace,
    )

    assert result["status"] == "completed"
    artifact = json.loads((workspace / result["output_artifacts"][0]["path"]).read_text(encoding="utf-8"))
    assert artifact["status"] == "completed"
    assert artifact["outputs"]["candidates"][0]["candidate_id"] == f"local-{digest[:16]}"
    assert artifact["outputs"]["candidates"][0]["source_ref"] == str(local)
    assert any("provider failed" in item.lower() for item in artifact["limitations"])


def test_structured_inconclusive_discovery_continues_with_frozen_local_seeds(
    workspace: Path,
) -> None:
    request, _services = request_for("literature_discover", workspace)
    local = workspace / "inputs" / "local-paper.md"
    local.write_text("# Local paper\n\nEvidence from a real local source.", encoding="utf-8")
    digest = hashlib.sha256(local.read_bytes()).hexdigest()
    request["typed_inputs"]["payload"]["local_sources"] = [
        {"path": str(local), "relative_path": "inputs/local-paper.md", "sha256": digest}
    ]

    def structured_environment_failure(**kwargs):
        return {
            "status": "inconclusive",
            "query": kwargs["query"],
            "candidates": [],
            "limitations": ["Discovery source failed: provider rate limited."],
        }

    result = execute_operator(
        request,
        services={"discover_literature": structured_environment_failure},
        workspace_root=workspace,
    )

    assert result["status"] == "completed"
    artifact = json.loads((workspace / result["output_artifacts"][0]["path"]).read_text(encoding="utf-8"))
    assert artifact["status"] == "completed"
    assert artifact["outputs"]["candidates"][0]["candidate_id"] == f"local-{digest[:16]}"
    assert artifact["artifacts"] == [
        {"type": "local_seed", "path": str(local), "sha256": digest}
    ]
    assert any("continued with 1 controller-frozen local seed" in item for item in artifact["limitations"])


def test_discovery_prefers_production_multi_provider_service(workspace: Path) -> None:
    request, _services = request_for("literature_discover", workspace)
    calls: list[dict] = []

    def discover_sources(*, seed_snapshot, payload):
        calls.append({"seed_snapshot": seed_snapshot, "payload": payload})
        return {
            "status": "completed",
            "query": payload["query"],
            "candidates": [
                {
                    "source_id": "arxiv:2401.00001",
                    "title": "Traceable KV Cache Study",
                    "provider": "arxiv",
                    "url": "https://arxiv.org/abs/2401.00001",
                }
            ],
            "limitations": [],
        }

    result = execute_operator(
        request,
        services={
            "discover_sources": discover_sources,
            "discover_literature": pytest.fail,
        },
        workspace_root=workspace,
    )

    assert result["status"] == "completed"
    assert len(calls) == 1
    artifact = json.loads(
        (workspace / result["output_artifacts"][0]["path"]).read_text(encoding="utf-8")
    )
    assert artifact["outputs"]["candidates"][0]["candidate_id"] == "arxiv:2401.00001"


def test_input_artifact_hash_mismatch_fails_closed(workspace: Path) -> None:
    input_path = workspace / "inputs" / "paper-evidence.json"
    input_path.write_text(json.dumps(paper_evidence()), encoding="utf-8")
    request, _services = request_for("paper_analyze", workspace)
    request["typed_inputs"] = {"payload": {}}
    request["input_artifact_refs"] = [
        {
            "artifact_id": "paper.input",
            "path": "inputs/paper-evidence.json",
            "schema": "research_paper.v1",
            "sha256": "0" * 64,
        }
    ]
    result = execute_operator(request, workspace_root=workspace)
    assert result["status"] == "failed"
    assert "artifact_hash_mismatch" in result["errors"][0]["message"]


def test_direct_source_content_change_invalidates_idempotent_ingest_reuse(workspace: Path) -> None:
    request, services = request_for("material_ingest", workspace)
    first = execute_operator(request, services=services, workspace_root=workspace)
    source = workspace / "inputs" / "paper.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nThe updated material shows a second traceable result.\n",
        encoding="utf-8",
    )
    second = execute_operator(request, services=services, workspace_root=workspace)
    assert first["status"] == second["status"] == "completed"
    assert first["hashes"][0]["value"] != second["hashes"][0]["value"]
    assert first["output_artifacts"][0]["sha256"] != second["output_artifacts"][0]["sha256"]
    assert not any("Idempotent replay" in item for item in second["limitations"])


def test_package_local_registration_is_unique_and_resolvable() -> None:
    entries = registration_entries()
    assert len(entries) == len(NODE_IDS) == 15
    assert len({item["node_id"] for item in entries}) == len(entries)
    assert len({item["operator_id"] for item in entries}) == len(entries)
    assert all(
        item["operator_version"] == VERSION_OVERRIDES.get(item["node_id"], "1.1.0")
        for item in entries
    )
    assert all(item["mutates_global_state"] is False for item in entries)
    for node_id in NODE_IDS:
        resolved = resolve_entrypoint(node_id)
        assert resolved.operator_spec is OPERATOR_SPECS[node_id]


def test_discovery_ingest_emits_multiple_real_papers_and_claims_read_all(
    workspace: Path,
) -> None:
    request, services = request_for("discovery_ingest", workspace)
    result = execute_operator(request, services=services, workspace_root=workspace)
    assert result["status"] == "completed", result
    assert len(result["output_artifacts"]) == 2
    assert len({item["artifact_id"] for item in result["output_artifacts"]}) == 2

    claim_request, _ = request_for("claim_extract", workspace)
    claim_request["typed_inputs"] = {"payload": {"limit": 12}}
    claim_request["input_artifact_refs"] = result["output_artifacts"]
    claim_request["read_scope"] = ["outputs/discovery_ingest/"]
    claim_result = execute_operator(claim_request, workspace_root=workspace)
    claim_artifact = validate_result_and_artifact(claim_result, workspace)
    claim_text = " ".join(item["text"] for item in claim_artifact["outputs"]["claims"])
    assert "20 percent" in claim_text
    assert "10 percent" in claim_text


def test_claim_extraction_balances_a_bounded_limit_across_papers(
    workspace: Path,
) -> None:
    first = paper_evidence()
    first["outputs"]["paper"]["paper_id"] = "paper-first"
    first["outputs"]["paper"]["sections"][1]["text"] = " ".join(
        f"The first-paper method improves metric {index} by {index + 1} percent compared with baseline."
        for index in range(8)
    )
    second = paper_evidence()
    second["outputs"]["paper"]["paper_id"] = "paper-second"
    second["outputs"]["paper"]["sections"][1] = {
        "section_id": "results",
        "title": "Results",
        "text": "The second-paper method reduces latency by 17 percent compared with baseline.",
        "source_anchor": "inputs/paper-two.md#results",
    }

    request, services = request_for("claim_extract", workspace)
    request["typed_inputs"]["payload"] = {
        "limit": 4,
        "paper_evidence": [first, second],
    }
    result = execute_operator(request, services=services, workspace_root=workspace)
    claims = validate_result_and_artifact(result, workspace)["outputs"]["claims"]

    assert len(claims) == 4
    assert any("second-paper" in claim["text"] for claim in claims)
    assert claims[0]["source_anchor"] == "inputs/paper.md#results"
    assert claims[1]["source_anchor"] == "inputs/paper-two.md#results"


def test_source_assessment_selects_only_relevant_credible_ingested_sources_and_retains_unknowns(
    workspace: Path,
) -> None:
    request, services = request_for("source_assess", workspace)

    result = execute_operator(request, services=services, workspace_root=workspace)
    artifact = validate_result_and_artifact(result, workspace)

    outputs = artifact["outputs"]
    assert outputs["selected_source_ids"] == ["paper-001"]
    assert outputs["unresolved_source_ids"] == ["paper-002"]
    selected = outputs["assessments"][0]
    assert selected["relevance"]["status"] == "relevant"
    assert selected["credibility"]["status"] == "credible"
    assert selected["ingestion"]["status"] == "parsed"
    assert outputs["unresolved_questions"]


def test_claim_select_one_emits_exactly_one_disclosed_testable_choice(
    workspace: Path,
) -> None:
    request, services = request_for("claim_select_one", workspace)
    paper = paper_evidence()
    paper["outputs"]["paper"]["sections"][1]["text"] = (
        "The bounded parser improves reliability across source documents. "
        "The bounded parser reduces latency by 20 percent compared with the baseline."
    )
    request["typed_inputs"]["payload"] = {"paper_evidence": paper}

    result = execute_operator(request, services=services, workspace_root=workspace)
    artifact = validate_result_and_artifact(result, workspace)

    claims = artifact["outputs"]["claims"]
    assert len(claims) == 1
    assert claims[0]["testability"] == "testable"
    assert artifact["outputs"]["selection"] == {
        "selected_claim_id": claims[0]["claim_id"],
        "candidate_count": 2,
        "criteria": [
            "prefer testable over partially_testable, unknown, and not_testable",
            "prefer greater lexical alignment with the frozen validation objective",
            "prefer more retained evidence identifiers",
            "prefer the more specific claim text when earlier criteria tie",
            "break remaining ties by stable claim identifier",
        ],
        "priority_objective": "",
        "selected_objective_term_overlap": 0,
    }


@pytest.mark.parametrize("separator", ["/", "\\"])
def test_discovery_ingest_honors_explicit_directory_scope_with_json_suffix(
    workspace: Path,
    separator: str,
) -> None:
    request, services = request_for("discovery_ingest", workspace)
    request["write_scope"] = [f"outputs/research_paper.v1.schema.json{separator}"]

    result = execute_operator(request, services=services, workspace_root=workspace)

    assert result["status"] == "completed", result
    assert len(result["output_artifacts"]) == 2
    assert all(
        item["path"].replace("\\", "/").startswith("outputs/research_paper.v1.schema.json/")
        for item in result["output_artifacts"]
    )


def test_discovery_ingest_rejects_untrailed_json_file_scope(workspace: Path) -> None:
    request, services = request_for("discovery_ingest", workspace)
    request["write_scope"] = ["outputs/research_paper.v1.schema.json"]

    result = execute_operator(request, services=services, workspace_root=workspace)

    assert result["status"] == "failed"
    assert "requires a directory write scope" in result["errors"][0]["message"]


@pytest.mark.parametrize(
    ("title", "text", "expected_status", "expected_basis", "expected_count"),
    [
        (
            "Methods",
            "We used a bounded parser and compared its output hash with a deterministic baseline.",
            "explicitly_extracted",
            "explicit_method_heading",
            1,
        ),
        (
            "Evaluation",
            "We evaluated the runtime using three benchmark suites and measured latency against the baseline.",
            "extracted_with_inference",
            "method_description_without_heading",
            1,
        ),
        (
            "Abstract",
            "This study evaluates bounded adapters. Method The method ingests a local paper, preserves source hashes, extracts claims, and records a provenance ledger.",
            "extracted_with_inference",
            "method_description_without_heading",
            1,
        ),
        (
            "Background",
            "Compiler optimizations affect runtime performance, but this document reports no procedural details.",
            "insufficient_evidence",
            None,
            0,
        ),
    ],
)
def test_method_extract_preserves_explicit_inferred_and_insufficient_evidence(
    tmp_path: Path,
    monkeypatch,
    title: str,
    text: str,
    expected_status: str,
    expected_basis: str | None,
    expected_count: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    paper = paper_evidence()
    paper["outputs"]["paper"]["sections"] = [{
        "section_id": "section-001",
        "title": title,
        "text": text,
        "source_anchor": "inputs/paper.md#section-001",
    }]
    request, services = request_for("method_extract", tmp_path)
    request["typed_inputs"]["payload"] = {"paper_evidence": paper}

    result = execute_operator(request, services=services, workspace_root=tmp_path)

    artifact = validate_result_and_artifact(result, tmp_path)
    assert artifact["outputs"]["method_evidence_status"] == expected_status
    assert len(artifact["outputs"]["methods"]) == expected_count
    if expected_basis:
        assert artifact["outputs"]["methods"][0]["extraction_basis"] == expected_basis
        assert artifact["outputs"]["methods"][0]["evidence_ids"] == ["inputs/paper.md#section-001"]
    else:
        assert artifact["outputs"]["methods"] == []
        assert any("No method was synthesized" in item for item in artifact["limitations"])


def test_claim_and_method_extract_merge_duplicate_ingest_views(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    paper = paper_evidence()
    result_text = "Results The bounded adapter improves auditability by linking every result to deterministic hashes."
    method_text = "Method The method ingests a local paper, preserves source hashes, and records a provenance ledger."
    paper["outputs"]["paper"]["sections"] = [
        {
            "section_id": "abstract",
            "title": "Abstract",
            "text": f"{method_text} {result_text}",
            "source_anchor": "inputs/paper.pdf#abstract",
        },
        {
            "section_id": "recovered-text",
            "title": "Recovered Text",
            "text": f"{method_text} {result_text}",
            "source_anchor": "inputs/paper.pdf#recovered-text",
        },
    ]

    claim_request, claim_services = request_for("claim_extract", tmp_path)
    claim_request["typed_inputs"]["payload"] = {"paper_evidence": paper}
    claims = validate_result_and_artifact(
        execute_operator(claim_request, services=claim_services, workspace_root=tmp_path),
        tmp_path,
    )["outputs"]["claims"]
    assert len(claims) == 1
    assert claims[0]["evidence_ids"] == ["inputs/paper.pdf#abstract", "inputs/paper.pdf#recovered-text"]

    method_request, method_services = request_for("method_extract", tmp_path)
    method_request["typed_inputs"]["payload"] = {"paper_evidence": paper}
    methods = validate_result_and_artifact(
        execute_operator(method_request, services=method_services, workspace_root=tmp_path),
        tmp_path,
    )["outputs"]["methods"]
    assert len(methods) == 1
    assert methods[0]["extraction_basis"] == "method_description_without_heading"
    assert methods[0]["evidence_ids"] == ["inputs/paper.pdf#abstract", "inputs/paper.pdf#recovered-text"]


def test_unknown_operator_fails_closed() -> None:
    with pytest.raises(Exception, match="No evidence physical operator registered"):
        resolve_entrypoint("not-a-node")
