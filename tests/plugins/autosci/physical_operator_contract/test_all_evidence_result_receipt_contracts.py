from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from harness.lib.physical_operator_worker import run_physical_operator
from harness.lib.research_orchestration.runtime import default_production_resolver


REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_PAPER = "tests/plugins/autosci/fixtures/sample_paper.md"
FIXTURE_REPO = "tests/plugins/autosci/fixtures/sample_repo"
FINAL_FIXTURES = (
    ("scientific_report", "scientific_report.v1", "tests/harness/evaluators/scientific/fixtures/pass/scientific_report.json"),
    ("claim_verdict", "claim_verdict.v1", "tests/harness/evaluators/scientific/fixtures/pass/claim_verdict.json"),
)
OPERATOR_BY_NODE = {
    "evidence_import": "evidence_import_worker",
    "literature_discover": "literature_discover_worker",
    "paper_ingest": "paper_ingest_worker",
    "material_ingest": "material_ingest_worker",
    "paper_analyze": "paper_analyze_worker",
    "content_analyze": "content_analyze_worker",
    "memory_update_initial": "memory_update_initial_worker",
    "memory_update_final": "memory_update_final_worker",
    "graph_update": "graph_update_worker",
    "claim_extract": "claim_extract_worker",
    "method_extract": "method_extract_worker",
    "code_evidence_map": "code_evidence_map_worker",
}
FORBIDDEN_FILENAMES = {
    "artifact_manifest.json",
    "dispatch_record.json",
    "evidence_ir.json",
    "gate_ledger.json",
    "lease_record.json",
    "node_envelope.json",
    "operator_state_log.json",
}


def _task_contract(supplied_evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "user_intent": "Exercise all production scientific-lifecycle evidence physical operators.",
        "deliverable": {
            "kind": "scientific_evidence_contract",
            "description": "Direct worker receipts for every evidence operator.",
            "language": "en",
            "format": "json",
            "artifact_expectations": ["research_node_result.v1", "solar.node_envelope.v1"],
        },
        "success_criteria": [
            "Each production evidence worker is selected through the production resolver.",
            "Each worker returns a research_node_result.v1 accepted by the worker boundary.",
            "Each call writes a solar.node_envelope.v1 receipt.",
        ],
        "run_provenance": {"repo_head": "test", "captured_at": "2026-08-26T12:00:00Z"},
    }
    if supplied_evidence:
        contract["supplied_evidence"] = supplied_evidence
    return contract


def _request(
    node_id: str,
    *,
    payload: dict[str, Any] | None = None,
    refs: list[dict[str, Any]] | None = None,
    read_scope: list[str] | None = None,
    write_scope: list[str] | None = None,
    supplied_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    operator_id = OPERATOR_BY_NODE[node_id]
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-all-evidence-operator-contract",
        "run_id": "run-all-evidence-operator-contract",
        "workflow_id": "direct_all_evidence_operator_contract_v1",
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
                "task_contract": _task_contract(supplied_evidence),
                **(payload or {}),
            },
        },
        "input_artifact_refs": list(refs or []),
        "authorization": {
            "scope_id": "direct-all-evidence-operator-contract",
            "approved_capabilities": ["write_artifact"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": read_scope or ["inputs", "out"],
        "write_scope": write_scope or [f"out/{node_id}"],
        "timeout_retry_policy": {"timeout_seconds": 30, "max_attempts": 1, "retry_on": []},
    }


def _copy_tree_or_file(tmp_path: Path, rel: str) -> Path:
    source = REPO_ROOT / rel
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
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


def _run(tmp_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    resolver = default_production_resolver(services={}, workspace_root=tmp_path)
    envelope = run_physical_operator(
        request,
        operator_id=request["physical_operator"]["operator_id"],
        runner=resolver.execute,
        envelope_path=tmp_path / "worker" / request["node_id"] / "node_envelope.json",
        attempt=1,
        lease_id=f"lease-{request['node_id']}",
        run_contract_ref={"run_contract_id": "direct-all-evidence-contract", "sha256": "e" * 64},
        clock=lambda: "2026-08-26T12:00:00Z",
    )
    saved = json.loads((tmp_path / "worker" / request["node_id"] / "node_envelope.json").read_text(encoding="utf-8"))
    assert saved == envelope
    assert envelope["schema_version"] == "solar.node_envelope.v1"
    assert envelope["artifact_role"] == "runtime_worker_receipt"
    assert envelope["operator_id"] == request["physical_operator"]["operator_id"]
    assert envelope["self_reported"]["schema"] == "research_node_result.v1"
    assert envelope["self_reported"]["secret_redaction_assertion"]["no_secrets_observed"] is True
    for artifact in envelope["artifacts"]:
        _artifact_body(tmp_path, artifact)
    return envelope


def _copied_fixture_ref(tmp_path: Path, rel: str, artifact_id: str, schema: str) -> dict[str, Any]:
    path = _copy_tree_or_file(tmp_path, rel)
    return {
        "artifact_id": artifact_id,
        "path": rel,
        "schema": schema,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "provenance": {"source": "checked_in_fixture", "path": rel},
    }


def _copied_final_fixture(tmp_path: Path, artifact_id: str, schema: str, rel: str) -> dict[str, Any]:
    target = _copy_tree_or_file(tmp_path, rel)
    body = json.loads(target.read_text(encoding="utf-8"))
    assert body["schema"] == schema
    return body


def test_all_scientific_lifecycle_evidence_workers_return_node_result_and_worker_receipt(tmp_path: Path) -> None:
    paper_ref = _copied_fixture_ref(tmp_path, FIXTURE_PAPER, "fixture_sample_paper_md", "text/markdown")
    _copy_tree_or_file(tmp_path, FIXTURE_REPO)

    evidence_import = _run(
        tmp_path,
        _request(
            "evidence_import",
            read_scope=["tests/plugins/autosci/fixtures"],
            write_scope=["out/evidence_import"],
            supplied_evidence=[paper_ref],
        ),
    )
    literature_discover = _run(
        tmp_path,
        _request(
            "literature_discover",
            payload={
                "query": "Solar-native AutoSci adapter fixture evidence",
                "mode": "topic",
                "limit": 3,
            },
            read_scope=["tests/plugins/autosci/fixtures"],
            write_scope=["out/literature_discover"],
        ),
    )
    paper_ingest = _run(
        tmp_path,
        _request(
            "paper_ingest",
            payload={"paper_path": FIXTURE_PAPER, "paper_id": "paper-all-evidence-fixture"},
            read_scope=["tests/plugins/autosci/fixtures"],
            write_scope=["out/paper_ingest"],
        ),
    )
    material_ingest = _run(
        tmp_path,
        _request(
            "material_ingest",
            payload={"material_path": FIXTURE_PAPER, "paper_id": "paper-all-evidence-material"},
            read_scope=["tests/plugins/autosci/fixtures"],
            write_scope=["out/material_ingest"],
        ),
    )
    paper_analyze = _run(
        tmp_path,
        _request(
            "paper_analyze",
            refs=material_ingest["artifacts"],
            read_scope=["out/material_ingest"],
            write_scope=["out/paper_analyze"],
        ),
    )
    content_analyze = _run(
        tmp_path,
        _request(
            "content_analyze",
            refs=material_ingest["artifacts"],
            read_scope=["out/material_ingest"],
            write_scope=["out/content_analyze"],
        ),
    )
    memory_update_initial = _run(
        tmp_path,
        _request(
            "memory_update_initial",
            refs=material_ingest["artifacts"],
            read_scope=["out/material_ingest"],
            write_scope=["out/memory_update_initial"],
        ),
    )
    graph_update = _run(
        tmp_path,
        _request(
            "graph_update",
            refs=memory_update_initial["artifacts"],
            read_scope=["out/memory_update_initial"],
            write_scope=["out/graph_update"],
        ),
    )
    claim_extract = _run(
        tmp_path,
        _request(
            "claim_extract",
            payload={"limit": 5},
            refs=material_ingest["artifacts"],
            read_scope=["out/material_ingest"],
            write_scope=["out/claim_extract"],
        ),
    )
    method_extract = _run(
        tmp_path,
        _request(
            "method_extract",
            refs=material_ingest["artifacts"],
            read_scope=["out/material_ingest"],
            write_scope=["out/method_extract"],
        ),
    )
    code_evidence_map = _run(
        tmp_path,
        _request(
            "code_evidence_map",
            payload={"repo_path": FIXTURE_REPO, "execution_entrypoint": "bridge_fixture.run_fixture_bridge"},
            refs=claim_extract["artifacts"],
            read_scope=["out/claim_extract", "tests/plugins/autosci/fixtures/sample_repo"],
            write_scope=["out/code_evidence_map"],
        ),
    )
    final_evidence = [
        _copied_final_fixture(tmp_path, artifact_id, schema, rel)
        for artifact_id, schema, rel in FINAL_FIXTURES
    ]
    memory_update_final = _run(
        tmp_path,
        _request(
            "memory_update_final",
            payload={"source_evidence": final_evidence[0], "verdict_evidence": final_evidence[1]},
            read_scope=["tests/harness/evaluators/scientific/fixtures/pass"],
            write_scope=["out/memory_update_final"],
        ),
    )

    envelopes = {
        "evidence_import": evidence_import,
        "literature_discover": literature_discover,
        "paper_ingest": paper_ingest,
        "material_ingest": material_ingest,
        "paper_analyze": paper_analyze,
        "content_analyze": content_analyze,
        "memory_update_initial": memory_update_initial,
        "memory_update_final": memory_update_final,
        "graph_update": graph_update,
        "claim_extract": claim_extract,
        "method_extract": method_extract,
        "code_evidence_map": code_evidence_map,
    }

    assert set(envelopes) == set(OPERATOR_BY_NODE)
    assert {envelope["operator_id"] for envelope in envelopes.values()} == set(OPERATOR_BY_NODE.values())
    assert evidence_import["status"] == "completed"
    assert literature_discover["status"] == "awaiting_external"
    assert literature_discover["error"]["type"] == "provider_environment_failure"
    assert paper_ingest["status"] == "completed"
    assert paper_analyze["status"] == "completed"
    assert content_analyze["status"] == "completed"
    assert memory_update_initial["status"] == "completed"
    assert memory_update_final["status"] == "completed"
    assert graph_update["status"] == "completed"
    assert claim_extract["status"] == "completed"
    assert method_extract["status"] == "completed"
    assert code_evidence_map["status"] == "completed"
    assert _artifact_body(tmp_path, code_evidence_map["artifacts"][0])["outputs"]["mappings"][0]["files"]
