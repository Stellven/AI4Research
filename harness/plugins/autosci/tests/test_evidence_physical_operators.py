from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from harness.plugins.autosci.operators.scientific_lifecycle.evidence import (
    OPERATOR_SPECS,
    execute_operator,
    registration_entries,
    resolve_entrypoint,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = REPO_ROOT / "harness" / "schemas" / "evidence"
NODE_IDS = tuple(OPERATOR_SPECS)


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
        import hashlib
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
    elif node_id in {"paper_analyze", "content_analyze", "memory_update_initial", "claim_extract", "method_extract"}:
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
    return request, services


def validate_result_and_artifact(result: dict, workspace: Path) -> dict:
    result_schema = json.loads((SCHEMAS / "research_node_result.v1.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(result_schema).validate(result)
    assert result["status"] == "completed", result
    artifact_ref = result["output_artifacts"][0]
    artifact = json.loads((workspace / artifact_ref["path"]).read_text(encoding="utf-8"))
    artifact_schema = json.loads((SCHEMAS / f"{artifact['schema']}.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(artifact_schema).validate(artifact)
    assert artifact["provenance"]["operator_version"] == "1.0.0"
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


@pytest.mark.parametrize("node_id", NODE_IDS)
def test_each_evidence_operator_rejects_missing_required_input_as_product_failure(node_id: str, workspace: Path) -> None:
    request, _services = request_for(node_id, workspace)
    request["typed_inputs"] = {"payload": {}}
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
    assert len(entries) == len(NODE_IDS) == 12
    assert len({item["node_id"] for item in entries}) == len(entries)
    assert len({item["operator_id"] for item in entries}) == len(entries)
    assert all(item["operator_version"] == "1.0.0" for item in entries)
    assert all(item["mutates_global_state"] is False for item in entries)
    for node_id in NODE_IDS:
        resolved = resolve_entrypoint(node_id)
        assert resolved.operator_spec is OPERATOR_SPECS[node_id]


def test_unknown_operator_fails_closed() -> None:
    with pytest.raises(Exception, match="No evidence physical operator registered"):
        resolve_entrypoint("not-a-node")
