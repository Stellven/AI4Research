from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from harness.lib.physical_operator_worker import run_physical_operator
from harness.lib.research_orchestration.runtime import default_production_resolver


FIXTURE_PAPER = "tests/plugins/autosci/fixtures/sample_paper.md"
REPO_ROOT = Path(__file__).resolve().parents[4]
FORBIDDEN_FILENAMES = {
    "artifact_manifest.json",
    "dispatch_record.json",
    "evidence_ir.json",
    "gate_ledger.json",
    "lease_record.json",
    "node_envelope.json",
    "operator_state_log.json",
}
OPERATOR_BY_NODE = {
    "literature_discover": "literature_discover_worker",
    "paper_ingest": "paper_ingest_worker",
}
IMPLEMENTATION_BY_NODE = {
    "literature_discover": "autosci-evidence-literature-discover",
    "paper_ingest": "autosci-evidence-paper-ingest",
}
SCHEMA_BY_NODE = {
    "literature_discover": "literature_discovery.v1",
    "paper_ingest": "research_paper.v1",
}
DISCOVERY_REQUEST_FIXTURE = "tests/journeys/phase22/fixtures/j02_j05/j05_discovery_request.json"


def _task_contract() -> dict[str, Any]:
    return {
        "user_intent": "Discover traceable solar literature and ingest the selected local fixture paper.",
        "deliverable": {
            "kind": "scientific_evidence",
            "description": "Production-boundary evidence for first-scope AutoSci evidence operators.",
            "language": "en",
            "format": "json",
            "artifact_expectations": ["literature_discovery.v1", "research_paper.v1"],
        },
        "success_criteria": [
            "Literature discovery returns traceable provider candidates without live network.",
            "Paper ingestion preserves local source text, source identity, and content hash.",
        ],
        "run_provenance": {"repo_head": "test", "captured_at": "2026-08-26T12:00:00Z"},
    }


def _request(
    node_id: str,
    *,
    payload: dict[str, Any] | None = None,
    read_scope: list[str] | None = None,
    write_scope: list[str] | None = None,
) -> dict[str, Any]:
    operator_id = OPERATOR_BY_NODE[node_id]
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-literature-paper-first-scope-contract",
        "run_id": "run-literature-paper-first-scope-contract",
        "workflow_id": "direct_literature_paper_operator_contract_v1",
        "node_id": node_id,
        "logical_operator": {
            "operator_id": f"logical-{node_id}",
            "operator_kind": "logical",
            "capabilities": ["write_artifact"],
        },
        "physical_operator": {
            "operator_id": operator_id,
            "operator_kind": "physical",
            "capabilities": ["bounded_worker", "write_artifact"],
        },
        "typed_inputs": {
            "input_schema": f"{node_id}.input.v1",
            "payload": {
                "allow_network_fetch": False,
                "evidence_timestamp": "2026-08-26T12:00:00Z",
                "task_contract": _task_contract(),
                **(payload or {}),
            },
        },
        "input_artifact_refs": [],
        "authorization": {
            "scope_id": "direct-literature-paper-operator-contract",
            "approved_capabilities": ["write_artifact"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": read_scope or ["tests/plugins/autosci/fixtures"],
        "write_scope": write_scope or [f"out/{node_id}"],
        "timeout_retry_policy": {"timeout_seconds": 30, "max_attempts": 1, "retry_on": []},
    }


def _run(tmp_path: Path, request: dict[str, Any], services: dict[str, Any]) -> dict[str, Any]:
    resolver = default_production_resolver(services=services, workspace_root=tmp_path)
    return run_physical_operator(
        request,
        operator_id=request["physical_operator"]["operator_id"],
        runner=resolver.execute,
        envelope_path=tmp_path / "worker" / request["node_id"] / "node_envelope.json",
        attempt=1,
        lease_id=f"lease-{request['node_id']}",
        run_contract_ref={"run_contract_id": "direct-literature-paper-contract", "sha256": "d" * 64},
        clock=lambda: "2026-08-26T12:00:00Z",
    )


def _copy_fixture_paper(tmp_path: Path) -> Path:
    source = REPO_ROOT / FIXTURE_PAPER
    target = tmp_path / FIXTURE_PAPER
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def _artifact_body(tmp_path: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / artifact["path"]
    assert path.is_file()
    assert path.name not in FORBIDDEN_FILENAMES
    assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["schema"] == artifact["schema"]
    return body


def _literature_case() -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = json.loads((REPO_ROOT / DISCOVERY_REQUEST_FIXTURE).read_text(encoding="utf-8-sig"))
    request = _request(
        "literature_discover",
        payload={
            "query": fixture["topic"],
            "mode": "topic",
            "anchors": fixture["anchors"],
            "negative_ids": fixture["negative_ids"],
            "limit": fixture["limit"],
            "allow_network_fetch": False,
        },
        read_scope=["tests/journeys/phase22/fixtures/j02_j05"],
        write_scope=["out/literature_discover"],
    )
    return request, fixture


def _paper_case(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    copied = _copy_fixture_paper(tmp_path)
    request = _request(
        "paper_ingest",
        payload={"paper_path": FIXTURE_PAPER, "paper_id": "paper-autosci-adapter-fixture"},
        read_scope=["tests/plugins/autosci/fixtures"],
        write_scope=["out/paper_ingest"],
    )
    return request, {}, copied


def test_literature_discover_worker_uses_real_journey_request_and_reports_offline_provider_boundary(
    tmp_path: Path,
) -> None:
    request, fixture = _literature_case()

    envelope = _run(tmp_path, request, {})
    saved = json.loads((tmp_path / "worker" / "literature_discover" / "node_envelope.json").read_text(encoding="utf-8"))
    body = _artifact_body(tmp_path, envelope["artifacts"][0])

    assert saved == envelope
    assert envelope["schema_version"] == "solar.node_envelope.v1"
    assert envelope["artifact_role"] == "runtime_worker_receipt"
    assert envelope["operator_id"] == "literature_discover_worker"
    assert envelope["status"] == "awaiting_external"
    assert envelope["error"]["type"] == "provider_environment_failure"
    assert envelope["artifacts"][0]["path"] == "out/literature_discover/literature_discovery.v1.json"
    assert envelope["artifacts"][0]["schema"] == "literature_discovery.v1"
    assert body["node_id"] == "literature_discover"
    assert body["provenance"]["operator_id"] == "autosci-evidence-literature-discover"
    assert body["provenance"]["operator_version"] == "1.1.0"
    assert body["provenance"]["input_sha256"]
    assert body["provenance"]["output_sha256"]
    assert body["provenance"]["outcome_class"] == "provider_environment_failure"
    assert body["status"] == "inconclusive"
    assert body["outputs"]["query"] == fixture["topic"]
    assert body["outputs"]["mode"] == "topic"
    assert body["outputs"]["anchors"] == fixture["anchors"]
    assert body["outputs"]["candidates"] == []
    assert body["limitations"]


@pytest.mark.live_provider
def test_literature_discover_worker_returns_real_provider_candidates_for_real_journey_anchors(
    tmp_path: Path,
) -> None:
    authorized = (
        os.environ.get("PHASE22_ENABLE_NETWORK_JOURNEYS") == "1"
        and os.environ.get("SOLAR_AUTOSCI_ALLOW_NETWORK") == "1"
    )
    if not authorized:
        pytest.skip("live network discovery is not authorized")

    request, fixture = _literature_case()
    request["typed_inputs"]["payload"]["allow_network_fetch"] = True
    request["typed_inputs"]["payload"]["mode"] = "anchors"
    request["typed_inputs"]["payload"]["no_citation_expand"] = True
    request["typed_inputs"]["payload"]["max_retries"] = 0
    request["typed_inputs"]["payload"]["max_retry_wait_seconds"] = 5
    request["authorization"]["allow_network"] = True
    request["authorization"]["allow_live_provider"] = True

    envelope = _run(tmp_path, request, {})
    saved = json.loads((tmp_path / "worker" / "literature_discover" / "node_envelope.json").read_text(encoding="utf-8"))

    assert saved == envelope
    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["error"] is None
    assert envelope["operator_id"] == "literature_discover_worker"

    body = _artifact_body(tmp_path, envelope["artifacts"][0])
    outputs = body["outputs"]
    candidates = outputs["candidates"]

    assert body["status"] == "completed"
    assert body["provenance"]["outcome_class"] == "success"
    assert outputs["query"] == fixture["topic"]
    assert outputs["mode"] == "anchors"
    assert outputs["anchors"] == fixture["anchors"]
    assert 1 <= len(candidates) <= fixture["limit"]
    assert all(candidate["candidate_id"] for candidate in candidates)
    assert all(candidate["title"] for candidate in candidates)
    assert all(candidate["source_channels"] for candidate in candidates)
    assert all(candidate["year"] for candidate in candidates)
    assert all(candidate["source_ref"].startswith(("http://", "https://")) for candidate in candidates)
    serialized = json.dumps(candidates).lower()
    assert not any(marker in serialized for marker in ("dummy", "placeholder", "example.test", "synthetic"))
    assert not any(negative_id.lower() in serialized for negative_id in fixture["negative_ids"])


def test_paper_ingest_worker_parses_existing_local_fixture_and_preserves_source_contract(
    tmp_path: Path,
) -> None:
    request, services, copied = _paper_case(tmp_path)

    envelope = _run(tmp_path, request, services)
    saved = json.loads((tmp_path / "worker" / "paper_ingest" / "node_envelope.json").read_text(encoding="utf-8"))
    body = _artifact_body(tmp_path, envelope["artifacts"][0])
    paper = body["outputs"]["paper"]
    boundary = body["outputs"]["final_source_registration_boundary"]

    assert saved == envelope
    assert envelope["schema_version"] == "solar.node_envelope.v1"
    assert envelope["artifact_role"] == "runtime_worker_receipt"
    assert envelope["operator_id"] == "paper_ingest_worker"
    assert envelope["status"] == "completed"
    assert envelope["error"] is None
    assert envelope["artifacts"][0]["path"] == "out/paper_ingest/research_paper.v1.json"
    assert envelope["artifacts"][0]["schema"] == "research_paper.v1"
    assert body["node_id"] == "paper_ingest"
    assert body["provenance"]["operator_id"] == "autosci-evidence-paper-ingest"
    assert body["provenance"]["operator_version"] == "1.1.0"
    assert body["provenance"]["input_sha256"]
    assert body["provenance"]["output_sha256"]
    assert body["provenance"]["outcome_class"] == "success"
    assert paper["paper_id"] == "paper-autosci-adapter-fixture"
    assert paper["title"] == "AutoSci Adapter Fixture Paper"
    assert paper["source_type"] == "markdown"
    assert paper["source_ref"] == FIXTURE_PAPER
    assert paper["parse_status"] == "parsed"
    assert [section["section_id"] for section in paper["sections"]] == ["abstract", "method", "results"]
    assert all(section["text"].strip() for section in paper["sections"])
    assert paper["source_contract"]["content_sha256"] == hashlib.sha256(copied.read_bytes()).hexdigest()
    assert boundary["schema"] == "autosci_source_registration_boundary.v1"
    assert boundary["final_registration_ready"] is True
    assert boundary["missing"] == []


def test_paper_ingest_reuses_hash_identical_output_for_same_identity(
    tmp_path: Path,
) -> None:
    paper_request, paper_services, _copied = _paper_case(tmp_path)

    first_paper = _run(tmp_path, paper_request, paper_services)
    second_paper = _run(tmp_path, paper_request, paper_services)

    assert first_paper["status"] == second_paper["status"] == "completed"
    assert first_paper["artifacts"][0]["sha256"] == second_paper["artifacts"][0]["sha256"]
    assert first_paper["self_reported"]["hashes"] == second_paper["self_reported"]["hashes"]
    assert "Idempotent replay" in second_paper["self_reported"]["limitations"][0]


def test_literature_discover_and_paper_ingest_fail_closed_without_required_materials(
    tmp_path: Path,
) -> None:
    cases = [
        (
            _request("literature_discover", payload={}, write_scope=["out/literature_discover"]),
            {},
            "Literature discovery requires query/topic, anchors, venue, or an explicit mode",
        ),
        (
            _request("paper_ingest", payload={}, write_scope=["out/paper_ingest"]),
            {},
            "Ingestion requires source, paper_path, material_path, or url",
        ),
    ]

    for request, services, expected_detail in cases:
        envelope = _run(tmp_path, request, services)

        assert envelope["status"] == "failed"
        assert envelope["error"]["type"] == "product_failure"
        assert expected_detail in envelope["error"]["detail"]
        assert envelope["artifacts"] == []
