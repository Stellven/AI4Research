from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

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
    "material_ingest": "material_ingest_worker",
    "content_analyze": "content_analyze_worker",
    "claim_extract": "claim_extract_worker",
    "method_extract": "method_extract_worker",
}


def _task_contract() -> dict[str, Any]:
    return {
        "user_intent": "Analyze and extract claims from the local AutoSci sample paper fixture.",
        "deliverable": {
            "kind": "scientific_evidence",
            "description": "Source-grounded content analysis and unverified claim extraction.",
            "language": "en",
            "format": "json",
            "artifact_expectations": ["research_paper.v1", "research_claims.v1"],
        },
        "success_criteria": [
            "Analysis preserves source section anchors.",
            "Extracted claims remain source-anchored and unverified.",
        ],
        "run_provenance": {"repo_head": "test", "captured_at": "2026-08-26T12:00:00Z"},
    }


def _request(
    node_id: str,
    *,
    payload: dict[str, Any] | None = None,
    refs: list[dict[str, Any]] | None = None,
    read_scope: list[str] | None = None,
    write_scope: list[str] | None = None,
) -> dict[str, Any]:
    operator_id = OPERATOR_BY_NODE[node_id]
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-content-claim-contract",
        "run_id": "run-content-claim-contract",
        "workflow_id": "direct_content_claim_operator_contract_v1",
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
        "input_artifact_refs": list(refs or []),
        "authorization": {
            "scope_id": "direct-content-claim-operator-contract",
            "approved_capabilities": ["write_artifact"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": read_scope or ["out/material_ingest"],
        "write_scope": write_scope or [f"out/{node_id}"],
        "timeout_retry_policy": {"timeout_seconds": 30, "max_attempts": 1, "retry_on": []},
    }


def _run(tmp_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    resolver = default_production_resolver(services={}, workspace_root=tmp_path)
    return run_physical_operator(
        request,
        operator_id=request["physical_operator"]["operator_id"],
        runner=resolver.execute,
        envelope_path=tmp_path / "worker" / request["node_id"] / "node_envelope.json",
        attempt=1,
        lease_id=f"lease-{request['node_id']}",
        run_contract_ref={"run_contract_id": "direct-content-claim-contract", "sha256": "d" * 64},
        clock=lambda: "2026-08-26T12:00:00Z",
    )


def _artifact_body(tmp_path: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / artifact["path"]
    assert path.is_file()
    assert path.name not in FORBIDDEN_FILENAMES
    assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["schema"] == artifact["schema"]
    return body


def _copy_fixture_paper(tmp_path: Path) -> None:
    source = REPO_ROOT / FIXTURE_PAPER
    target = tmp_path / FIXTURE_PAPER
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _research_paper_ref(tmp_path: Path) -> dict[str, Any]:
    _copy_fixture_paper(tmp_path)
    request = _request(
        "material_ingest",
        payload={"material_path": FIXTURE_PAPER, "paper_id": "paper-sample-paper"},
        read_scope=["tests/plugins/autosci/fixtures"],
        write_scope=["out/material_ingest"],
    )
    envelope = _run(tmp_path, request)
    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["operator_id"] == "material_ingest_worker"
    artifact = envelope["artifacts"][0]
    body = _artifact_body(tmp_path, artifact)
    paper = body["outputs"]["paper"]
    assert artifact["schema"] == "research_paper.v1"
    assert paper["source_ref"] == FIXTURE_PAPER
    assert [section["section_id"] for section in paper["sections"]] == ["abstract", "method", "results"]
    return artifact


def test_content_analyze_worker_consumes_real_research_paper_and_preserves_source_highlights(
    tmp_path: Path,
) -> None:
    paper_ref = _research_paper_ref(tmp_path)
    request = _request("content_analyze", refs=[paper_ref], write_scope=["out/content_analyze"])

    envelope = _run(tmp_path, request)
    saved = json.loads((tmp_path / "worker" / "content_analyze" / "node_envelope.json").read_text(encoding="utf-8"))
    body = _artifact_body(tmp_path, envelope["artifacts"][0])
    paper = body["outputs"]["paper"]
    analysis = paper["analysis"]

    assert saved == envelope
    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["error"] is None
    assert envelope["operator_id"] == "content_analyze_worker"
    assert envelope["artifacts"][0]["path"] == "out/content_analyze/research_content_analysis.v1.json"
    assert body["node_id"] == "content_analyze"
    assert body["provenance"]["operator_id"] == "autosci-evidence-content-analyze"
    assert body["provenance"]["input_sha256"]
    assert paper["paper_id"] == "paper-sample-paper"
    assert analysis["analysis_mode"] == "bounded_local_source_analysis"
    assert analysis["summary"].startswith("This fixture paper exists only to test Solar-native adapter boundaries.")
    assert {"fixture", "adapter", "solar-native"}.issubset(set(analysis["key_concepts"]))
    assert [item["section"] for item in analysis["section_highlights"]] == ["Abstract", "Method", "Results"]
    assert [item["source_anchor"] for item in analysis["section_highlights"]] == [
        f"{FIXTURE_PAPER}#abstract",
        f"{FIXTURE_PAPER}#method",
        f"{FIXTURE_PAPER}#results",
    ]
    assert body["limitations"] == [
        "Analysis is extractive and source-grounded; it does not independently verify paper claims."
    ]


def test_claim_extract_worker_consumes_real_research_paper_and_emits_unverified_source_anchored_claims(
    tmp_path: Path,
) -> None:
    paper_ref = _research_paper_ref(tmp_path)
    request = _request("claim_extract", refs=[paper_ref], payload={"limit": 5}, write_scope=["out/claim_extract"])

    envelope = _run(tmp_path, request)
    saved = json.loads((tmp_path / "worker" / "claim_extract" / "node_envelope.json").read_text(encoding="utf-8"))
    body = _artifact_body(tmp_path, envelope["artifacts"][0])
    claims = body["outputs"]["claims"]

    assert saved == envelope
    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["error"] is None
    assert envelope["operator_id"] == "claim_extract_worker"
    assert envelope["artifacts"][0]["path"] == "out/claim_extract/research_claims.v1.json"
    assert body["node_id"] == "claim_extract"
    assert body["provenance"]["operator_id"] == "autosci-evidence-claim-extract"
    assert body["provenance"]["input_sha256"]
    assert claims == [
        {
            "claim_id": "claim-001",
            "text": "The fixture path should produce a `result.json` file and an `evidence.jsonl` ledger entry without invoking a monolithic AutoSci workflow owner.",
            "claim_type": "result",
            "source_anchor": f"{FIXTURE_PAPER}#results",
            "testability": "partially_testable",
            "verification_status": "unverified",
            "evidence_ids": [f"{FIXTURE_PAPER}#results"],
        }
    ]
    assert body["limitations"] == ["Claims are extracted and unverified; downstream verification is required."]


def test_method_extract_worker_consumes_real_research_paper_and_preserves_explicit_method_anchor(
    tmp_path: Path,
) -> None:
    paper_ref = _research_paper_ref(tmp_path)
    request = _request("method_extract", refs=[paper_ref], write_scope=["out/method_extract"])

    envelope = _run(tmp_path, request)
    saved = json.loads((tmp_path / "worker" / "method_extract" / "node_envelope.json").read_text(encoding="utf-8"))
    body = _artifact_body(tmp_path, envelope["artifacts"][0])

    assert saved == envelope
    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["error"] is None
    assert envelope["operator_id"] == "method_extract_worker"
    assert envelope["artifacts"][0]["path"] == "out/method_extract/research_method.v1.json"
    assert body["node_id"] == "method_extract"
    assert body["provenance"]["operator_id"] == "autosci-evidence-method-extract"
    assert body["provenance"]["input_sha256"]
    assert body["outputs"]["method_evidence_status"] == "explicitly_extracted"
    assert body["outputs"]["methods"] == [
        {
            "method_id": "method-001",
            "name": "Method",
            "summary": "The fixture method runs a deterministic bridge action and records the generated Solar Evidence ABI artifact.",
            "procedure": [
                "The fixture method runs a deterministic bridge action and records the generated Solar Evidence ABI artifact."
            ],
            "source_papers": ["paper-sample-paper"],
            "evidence_ids": [f"{FIXTURE_PAPER}#method"],
            "extraction_basis": "explicit_method_heading",
            "confidence": 1.0,
        }
    ]
    assert body["limitations"] == ["Method steps are extractive and retain their source anchors."]


def test_content_analyze_worker_rejects_missing_research_paper_input_without_artifact(
    tmp_path: Path,
) -> None:
    request = _request("content_analyze", write_scope=["out/content_analyze"])

    envelope = _run(tmp_path, request)

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "product_failure"
    assert "Required typed input missing; expected one of: research_paper.v1" in envelope["error"]["detail"]
    assert envelope["artifacts"] == []


def test_claim_extract_worker_rejects_missing_research_paper_input_without_artifact(
    tmp_path: Path,
) -> None:
    request = _request("claim_extract", write_scope=["out/claim_extract"])

    envelope = _run(tmp_path, request)

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "product_failure"
    assert "Required typed input missing; expected one of: research_paper.v1" in envelope["error"]["detail"]
    assert envelope["artifacts"] == []


def test_method_extract_worker_rejects_missing_research_paper_input_without_artifact(
    tmp_path: Path,
) -> None:
    request = _request("method_extract", write_scope=["out/method_extract"])

    envelope = _run(tmp_path, request)

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "product_failure"
    assert "Required typed input missing; expected one of: research_paper.v1" in envelope["error"]["detail"]
    assert envelope["artifacts"] == []
