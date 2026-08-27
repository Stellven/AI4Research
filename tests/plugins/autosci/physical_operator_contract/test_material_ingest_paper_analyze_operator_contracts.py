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
    "paper_analyze": "paper_analyze_worker",
}


def _task_contract() -> dict[str, Any]:
    return {
        "user_intent": "Ingest and analyze the local AutoSci sample paper fixture.",
        "deliverable": {
            "kind": "scientific_evidence",
            "description": "A source-grounded local material ingestion and extractive paper analysis.",
            "language": "en",
            "format": "json",
            "artifact_expectations": ["research_paper.v1"],
        },
        "success_criteria": [
            "At least one parsed, non-empty local source section is preserved.",
            "Analysis remains source-grounded and extractive.",
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
        "task_id": "task-material-paper-analysis-contract",
        "run_id": "run-material-paper-analysis-contract",
        "workflow_id": "direct_material_paper_operator_contract_v1",
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
            "scope_id": "direct-material-paper-operator-contract",
            "approved_capabilities": ["write_artifact"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": read_scope or ["tests/plugins/autosci/fixtures"],
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
        run_contract_ref={"run_contract_id": "direct-material-paper-contract", "sha256": "c" * 64},
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


def _material_ingest(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    _copy_fixture_paper(tmp_path)
    request = _request(
        "material_ingest",
        payload={"material_path": FIXTURE_PAPER, "paper_id": "paper-sample-paper"},
        write_scope=["out/material_ingest"],
    )
    envelope = _run(tmp_path, request)
    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["error"] is None
    assert envelope["operator_id"] == "material_ingest_worker"
    assert envelope["artifacts"]
    return envelope, _artifact_body(tmp_path, envelope["artifacts"][0])


def test_material_ingest_worker_ingests_real_local_fixture_as_hash_verified_research_paper(
    tmp_path: Path,
) -> None:
    envelope, body = _material_ingest(tmp_path)
    saved = json.loads((tmp_path / "worker" / "material_ingest" / "node_envelope.json").read_text(encoding="utf-8"))
    paper = body["outputs"]["paper"]
    boundary = body["outputs"]["final_source_registration_boundary"]

    assert saved == envelope
    assert envelope["artifacts"][0]["path"] == "out/material_ingest/research_material.v1.json"
    assert body["node_id"] == "material_ingest"
    assert body["provenance"]["operator_id"] == "autosci-evidence-material-ingest"
    assert paper["paper_id"] == "paper-sample-paper"
    assert paper["source_ref"] == FIXTURE_PAPER
    assert paper["parse_status"] == "parsed"
    assert [section["section_id"] for section in paper["sections"]] == ["abstract", "method", "results"]
    assert all(section["text"].strip() for section in paper["sections"])
    assert paper["source_contract"]["content_sha256"] == hashlib.sha256(
        (tmp_path / FIXTURE_PAPER).read_bytes()
    ).hexdigest()
    assert boundary["schema"] == "autosci_source_registration_boundary.v1"
    assert boundary["final_registration_ready"] is True
    assert boundary["missing"] == []


def test_paper_analyze_worker_consumes_real_research_paper_artifact_and_adds_source_grounded_analysis(
    tmp_path: Path,
) -> None:
    material_envelope, _body = _material_ingest(tmp_path)
    paper_ref = material_envelope["artifacts"][0]
    analyze_request = _request(
        "paper_analyze",
        refs=[paper_ref],
        read_scope=["out/material_ingest"],
        write_scope=["out/paper_analyze"],
    )

    envelope = _run(tmp_path, analyze_request)
    saved = json.loads((tmp_path / "worker" / "paper_analyze" / "node_envelope.json").read_text(encoding="utf-8"))
    body = _artifact_body(tmp_path, envelope["artifacts"][0])
    paper = body["outputs"]["paper"]
    analysis = paper["analysis"]

    assert saved == envelope
    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["error"] is None
    assert envelope["operator_id"] == "paper_analyze_worker"
    assert envelope["artifacts"][0]["path"] == "out/paper_analyze/research_paper_analysis.v1.json"
    assert body["node_id"] == "paper_analyze"
    assert body["provenance"]["operator_id"] == "autosci-evidence-paper-analyze"
    assert body["provenance"]["input_sha256"]
    assert paper["paper_id"] == "paper-sample-paper"
    assert analysis["analysis_mode"] == "bounded_local_source_analysis"
    assert analysis["summary"]
    assert analysis["key_concepts"]
    assert len(analysis["section_highlights"]) == 3
    assert all(item["source_anchor"].startswith(f"{FIXTURE_PAPER}#") for item in analysis["section_highlights"])
    assert body["limitations"] == [
        "Analysis is extractive and source-grounded; it does not independently verify paper claims."
    ]


def test_material_ingest_worker_missing_material_path_fails_closed_before_artifact_authoring(tmp_path: Path) -> None:
    request = _request("material_ingest", payload={"paper_id": "paper-missing-source"})

    envelope = _run(tmp_path, request)

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "product_failure"
    assert "Ingestion requires source, paper_path, material_path, or url" in envelope["error"]["detail"]
    assert envelope["artifacts"] == []


def test_paper_analyze_worker_rejects_missing_research_paper_input_without_synthesizing_analysis(
    tmp_path: Path,
) -> None:
    request = _request("paper_analyze", read_scope=["out/material_ingest"])

    envelope = _run(tmp_path, request)

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "product_failure"
    assert "Required typed input missing; expected one of: research_paper.v1" in envelope["error"]["detail"]
    assert envelope["artifacts"] == []
