from __future__ import annotations

import hashlib
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import jsonschema
import pytest


HARNESS = (Path(__file__).resolve().parents[4] / 'harness')
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS / "lib"))

from plugins.autosci.operators.scientific_lifecycle.registry import production_bindings  # noqa: E402
from research_orchestration.resolver import PhysicalOperatorBinding, PhysicalOperatorResolver  # noqa: E402
from research_orchestration.runtime import FileWorkflowCatalog, SolarResearchRuntime  # noqa: E402


FIXTURES = HARNESS / "tests/research_orchestration/fixtures/phase5/seed_portability"
LIFECYCLE_ROOT = Path("artifacts/scientific/scientific_research_lifecycle_full_v1")
EXPERIMENT_EVIDENCE_ID = "external-experiment:phase5-seed-portability-ext-exp-001"
EXPERIMENT_RESULT_PATH = LIFECYCLE_ROOT / "07_experiment_result/experiment_result.v1.json"
CLAIM_VERDICT_PATH = LIFECYCLE_ROOT / "08_verdict/claim_verdict.v1.json"


def _catalog() -> FileWorkflowCatalog:
    return FileWorkflowCatalog(harness_root=HARNESS)


def _runtime(
    artifact_root: Path,
    *,
    services: dict[str, Any] | None = None,
    resolver: PhysicalOperatorResolver | None = None,
) -> SolarResearchRuntime:
    return SolarResearchRuntime(
        artifact_root=artifact_root,
        workflow_loader=_catalog().load,
        operator_resolver=resolver
        or PhysicalOperatorResolver(
            production_bindings(
                services=services or {},
                workspace_root=artifact_root,
                binding_factory=PhysicalOperatorBinding,
            )
        ),
        authorization={
            "allow_network": False,
            "allow_live_provider": False,
            "approval_ref": "phase5-fixture-approval",
            "approved_capabilities": ["execute_experiment"],
        },
    )


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pdf_seed() -> list[dict[str, str]]:
    return [{"seed_kind": "pdf", "value": str(FIXTURES / "local_pdf_synthesis_seed.pdf")}]


def _stable_json_sha256(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _validate_external_experiment_fixture(path: Path) -> dict[str, Any]:
    evidence = _json(path)
    assert evidence["schema"] == "external_experiment_evidence.v1"
    payload = evidence["canonical_payload"]
    assert payload["experiment_identity"]["experiment_id"]
    assert payload["method"]["procedure"]
    assert payload["inputs"]["expected_records"] == 17
    assert payload["results"]["outcome"] == "supports"
    assert payload["observed_at"].endswith("Z")
    assert payload["provenance"]["source"] == "external_fixture_lab"
    assert evidence["hashes"] == {
        "algorithm": "sha256",
        "canonical_payload_sha256": _stable_json_sha256(payload),
    }
    return evidence


def _node_record_hashes(state: dict[str, Any], artifact_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for node_id, node_state in state["node_states"].items():
        if node_state.get("status") != "completed" or not node_state.get("result_ref"):
            continue
        result_ref = Path(str(node_state["result_ref"]))
        hashes[node_id] = _sha256_file(result_ref)
    assert hashes
    return hashes


def _awaiting_resolver(artifact_root: Path, awaiting_nodes: set[str]) -> PhysicalOperatorResolver:
    base = PhysicalOperatorResolver(
        production_bindings(
            services={
                "idea_generator": _idea_generator,
                "experiment_executor": _unexpected_experiment_executor,
            },
            workspace_root=artifact_root,
            binding_factory=PhysicalOperatorBinding,
        )
    )

    def runner(request: dict[str, Any]) -> dict[str, Any]:
        node_id = str(request["node_id"])
        if node_id in awaiting_nodes:
            return {
                "schema": "research_node_result.v1",
                "task_id": request["task_id"],
                "run_id": request["run_id"],
                "workflow_id": request["workflow_id"],
                "node_id": node_id,
                "status": "awaiting_external",
                "status_is_terminal": False,
                "output_artifacts": [],
                "evidence": [
                    {
                        "evidence_id": f"{node_id}.external_wait",
                        "kind": "external_research_node_wait",
                        "summary": f"{node_id} is awaiting externally produced Phase 5 evidence.",
                    }
                ],
                "hashes": [],
                "model_provider_usage": [],
                "errors": [],
                "limitations": ["The node must be resumed with hash-verified external evidence."],
                "secret_redaction_assertion": {
                    "no_secrets_observed": True,
                    "redaction_review": "passed",
                },
            }
        return base.execute(request)

    bindings = [
        PhysicalOperatorBinding(operator_id=operator_id, runner=runner, version="phase5-test-wrapper")
        for operator_id in base.operator_ids()
    ]
    return PhysicalOperatorResolver(bindings)


def _idea_generator(*, evidence: list[dict[str, Any]], constraints: dict[str, Any]) -> dict[str, Any]:
    del evidence, constraints
    return {
        "ideas": [
            {
                "idea_id": "phase5-portability-check",
                "title": "Replay external portability checklist",
                "hypothesis": "The local PDF seed preserves source-grounded method and result facts.",
                "approach": "Use an offline checklist result as external experiment evidence.",
                "origin_evidence_ids": ["seed-portability-pdf#results"],
                "risks": ["Fixture scope is intentionally small."],
                "falsifiability": "The checklist fails if any expected PDF section is missing.",
                "validation_method": "Compare extracted report facts to the external checklist.",
                "minimum_experiment": "Record validated_records and required section presence.",
            }
        ]
    }


def _unexpected_experiment_executor(**_: Any) -> dict[str, Any]:
    raise AssertionError("experiment_run must be satisfied by resume-imported evidence")


def _write_external_experiment_result(
    artifact_root: Path,
    *,
    task_id: str,
    run_id: str,
    workflow_id: str,
    external: dict[str, Any],
) -> dict[str, Any]:
    payload = external["canonical_payload"]
    target = artifact_root / EXPERIMENT_RESULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": "experiment_result.v1",
        "task_id": task_id,
        "sprint_id": run_id,
        "node_id": "experiment_run",
        "status": "completed",
        "inputs": {
            "external_evidence_sha256": external["hashes"]["canonical_payload_sha256"],
            "external_evidence_id": payload["experiment_identity"]["experiment_id"],
        },
        "outputs": {
            "result": {
                "experiment_id": payload["experiment_identity"]["experiment_id"],
                "outcome": payload["results"]["outcome"],
                "metrics": payload["results"]["metrics"],
                "evidence_ids": [EXPERIMENT_EVIDENCE_ID],
                "criteria_results": payload["results"]["criteria_results"],
                "method": payload["method"],
                "input": payload["inputs"],
                "result": payload["results"],
                "time": payload["observed_at"],
                "provenance": payload["provenance"],
                "hash": external["hashes"],
                "source_run_id": payload["experiment_identity"]["source_run_id"],
            }
        },
        "artifacts": [
            {
                "type": "external_experiment_evidence",
                "path": "imports/external_experiment_evidence.json",
                "sha256": _sha256_file(artifact_root / "imports/external_experiment_evidence.json"),
            }
        ],
        "provenance": {
            "artifact_id": "experiment_result",
            "operator_id": "external-checklist-runner-v1",
            "implementation_package": "external/phase5-fixture-lab",
            "task_id": task_id,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "node_id": "experiment_run",
            "timestamp": payload["observed_at"],
            "source_run_id": payload["experiment_identity"]["source_run_id"],
            "external_payload_sha256": external["hashes"]["canonical_payload_sha256"],
        },
        "limitations": [
            "External experiment evidence was imported and still requires downstream Solar verification/report gates."
        ],
    }
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = _sha256_file(target)
    return _node_result(
        task_id=task_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="experiment_run",
        artifact_id="experiment_result",
        artifact_path=EXPERIMENT_RESULT_PATH,
        artifact_schema="experiment_result.v1",
        artifact_sha256=digest,
        evidence_id="experiment_run.external_import",
        summary="Hash-verified external experiment result was imported into experiment_run.",
    )


def _write_imported_claim_verdict(
    artifact_root: Path,
    *,
    task_id: str,
    run_id: str,
    workflow_id: str,
    external: dict[str, Any],
) -> dict[str, Any]:
    payload = external["canonical_payload"]
    target = artifact_root / CLAIM_VERDICT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    claim_text = (
        "The result shows local PDF seeds preserved the source title and method text in the report."
    )
    document = {
        "schema": "claim_verdict.v1",
        "task_id": task_id,
        "sprint_id": run_id,
        "node_id": "claim_verify",
        "status": "completed",
        "inputs": {
            "external_experiment_sha256": external["hashes"]["canonical_payload_sha256"],
            "source_run_id": payload["experiment_identity"]["source_run_id"],
        },
        "outputs": {
            "verdicts": [
                {
                    "claim_id": "claim-001",
                    "claim_text": claim_text,
                    "verdict": "supported",
                    "support_classification": "supported",
                    "confidence": 0.9,
                    "basis": (
                        "External experiment phase5-seed-portability-ext-exp-001 supports the PDF "
                        "seed portability claim without being promoted directly to final acceptance."
                    ),
                    "evidence_ids": [
                        EXPERIMENT_EVIDENCE_ID,
                        f"external-sha256:{external['hashes']['canonical_payload_sha256']}",
                    ],
                    "limitations": ["External evidence was imported through resume and then cited by downstream report gates."],
                }
            ]
        },
        "artifacts": [],
        "provenance": {
            "artifact_id": "claim_verdict",
            "operator_id": "external-claim-verification-review-v1",
            "implementation_package": "external/phase5-fixture-lab",
            "task_id": task_id,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "node_id": "claim_verify",
            "timestamp": payload["observed_at"],
            "source_run_id": payload["experiment_identity"]["source_run_id"],
            "external_payload_sha256": external["hashes"]["canonical_payload_sha256"],
        },
        "limitations": ["Imported verification is downstream evidence, not a final run verdict."],
    }
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = _sha256_file(target)
    return _node_result(
        task_id=task_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="claim_verify",
        artifact_id="claim_verdict",
        artifact_path=CLAIM_VERDICT_PATH,
        artifact_schema="claim_verdict.v1",
        artifact_sha256=digest,
        evidence_id="claim_verify.external_import",
        summary="Hash-verified external experiment evidence was reviewed in claim_verify.",
    )


def _node_result(
    *,
    task_id: str,
    run_id: str,
    workflow_id: str,
    node_id: str,
    artifact_id: str,
    artifact_path: Path,
    artifact_schema: str,
    artifact_sha256: str,
    evidence_id: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "schema": "research_node_result.v1",
        "task_id": task_id,
        "run_id": run_id,
        "workflow_id": workflow_id,
        "node_id": node_id,
        "status": "completed",
        "status_is_terminal": True,
        "output_artifacts": [
            {
                "artifact_id": artifact_id,
                "path": artifact_path.as_posix(),
                "schema": artifact_schema,
                "sha256": artifact_sha256,
            }
        ],
        "evidence": [
            {
                "evidence_id": evidence_id,
                "kind": "external_evidence_import",
                "summary": summary,
                "artifact_id": artifact_id,
            }
        ],
        "hashes": [{"hash_id": artifact_id, "algorithm": "sha256", "value": artifact_sha256}],
        "model_provider_usage": [],
        "errors": [],
        "limitations": ["Solar evaluator must accept this artifact before downstream nodes can use it."],
        "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
    }


def test_local_pdf_synthesis_uses_extracted_text_hashes_and_formal_gates(tmp_path: Path) -> None:
    pdf = FIXTURES / "local_pdf_synthesis_seed.pdf"
    runtime = _runtime(tmp_path)

    result = runtime.run(
        prompt=(
            "Synthesize the local PDF Seed Portability Micro Study. Preserve its method, results, "
            "and limitations in the final report."
        ),
        run_id="phase5-pdf-synthesis",
        seed_inputs=[{"seed_kind": "pdf", "value": str(pdf)}],
        max_steps=40,
    )

    assert result["route"]["seed_kind"] == "pdf"
    assert result["route"]["start_stage"] == "paper_ingest"
    assert result["final_status"] == "completed"
    state = _json(Path(result["state_path"]))
    assert state["final_status"] == "completed"

    input_snapshot = next((tmp_path / "inputs/phase5-pdf-synthesis").glob("*.pdf"))
    assert _sha256_file(input_snapshot) == _sha256_file(pdf)
    paper = _json(tmp_path / LIFECYCLE_ROOT / "01_paper/research_paper.v1.json")
    source_artifact = paper["artifacts"][0]
    assert source_artifact["path"].endswith("local_pdf_synthesis_seed.pdf")
    assert source_artifact["sha256"] == _sha256_file(input_snapshot)
    body = "\n".join(section["text"] for section in paper["outputs"]["paper"]["sections"])
    assert "Seed Portability Micro Study" in body
    assert "Our method uses a controlled local PDF ingestion task" in body
    assert "The result shows local PDF seeds preserved" in body
    assert "The limitation is that this micro study uses one small local PDF" in body

    report = (tmp_path / LIFECYCLE_ROOT / "09_report/final-report.md").read_text(encoding="utf-8")
    assert "Seed Portability Micro Study" in report
    assert "## Methods" in report
    assert "bounded parser" in report
    assert "17 validated records" in report
    assert "## Limitations" in report

    final_evaluation = _json(tmp_path / LIFECYCLE_ROOT / "09_report/research_final_evaluation.v1.json")
    evaluation = final_evaluation["outputs"]["evaluation"]
    assert evaluation["accepted"] is True
    assert all(item["status"] == "passed" for item in evaluation["criterion_results"])


def test_invalid_pdf_seed_fails_as_product_input_not_environment_block(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    result = runtime.run(
        prompt="Synthesize this invalid local PDF and report method, results, and limitations.",
        run_id="phase5-invalid-pdf",
        seed_inputs=[{"seed_kind": "pdf", "value": str(FIXTURES / "invalid_pdf_seed.pdf")}],
        max_steps=10,
    )

    assert result["route"]["seed_kind"] == "pdf"
    assert result["final_status"] in {"failed", "blocked"}
    blocker_text = json.dumps(result["current_blockers"], sort_keys=True)
    assert "ENVIRONMENT_BLOCKED" not in blocker_text
    assert "PDF" in blocker_text or "source" in blocker_text


def test_resume_imports_external_experiment_evidence_and_continues_to_cited_report(tmp_path: Path) -> None:
    external_fixture = FIXTURES / "external_experiment_evidence.json"
    imported_copy = tmp_path / "imports/external_experiment_evidence.json"
    imported_copy.parent.mkdir(parents=True)
    shutil.copyfile(external_fixture, imported_copy)
    external = _validate_external_experiment_fixture(imported_copy)
    resolver = _awaiting_resolver(tmp_path, {"claim_verify"})
    runtime = _runtime(tmp_path, resolver=resolver)

    first = runtime.run(
        prompt=(
            "Use the local PDF seed and outside-lab results to validate the result claim before "
            "writing a source-grounded report with methods, results, and limitations."
        ),
        run_id="phase5-external-import",
        seed_inputs=[{"seed_kind": "pdf", "value": str(FIXTURES / "local_pdf_synthesis_seed.pdf")}],
        max_steps=40,
    )
    assert first["final_status"] == "awaiting_external"
    assert first["node_states"]["claim_verify"]["status"] == "awaiting_external"
    assert first["node_states"].get("experiment_run", {}).get("status") in {None, "cancelled"}
    before_hashes = _node_record_hashes(_json(Path(first["state_path"])), tmp_path)

    claim_verdict = _write_imported_claim_verdict(
        tmp_path,
        task_id=first["task_id"],
        run_id=first["run_id"],
        workflow_id=first["workflow_id"],
        external=external,
    )
    final = runtime.run(
        prompt=first["prompt"],
        run_id=first["run_id"],
        seed_inputs=_pdf_seed(),
        run_mode="resume",
        explicit_workflow="paper_ingestion",
        imported_result=claim_verdict,
        max_steps=40,
    )

    assert final["run_id"] == first["run_id"]
    assert final["final_status"] == "completed"
    final_state = _json(Path(final["state_path"]))
    for node_id, digest in before_hashes.items():
        assert _sha256_file(Path(final_state["node_states"][node_id]["result_ref"])) == digest

    report = (tmp_path / LIFECYCLE_ROOT / "09_report/final-report.md").read_text(encoding="utf-8")
    assert EXPERIMENT_EVIDENCE_ID in report
    assert external["hashes"]["canonical_payload_sha256"] in report
    assert "directly to final acceptance" in _json(tmp_path / CLAIM_VERDICT_PATH)["outputs"]["verdicts"][0]["basis"]
    assert final["node_states"].get("experiment_run", {}).get("status") in {None, "cancelled"}
    final_evaluation = _json(tmp_path / LIFECYCLE_ROOT / "09_report/research_final_evaluation.v1.json")
    assert final_evaluation["outputs"]["evaluation"]["accepted"] is True
    assert "claim_verify.external_import" in final["final_status_evidence_refs"]


@pytest.fixture()
def awaiting_experiment_run(tmp_path: Path) -> tuple[SolarResearchRuntime, dict[str, Any], dict[str, Any]]:
    imported_copy = tmp_path / "imports/external_experiment_evidence.json"
    imported_copy.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "external_experiment_evidence.json", imported_copy)
    external = _validate_external_experiment_fixture(imported_copy)
    runtime = _runtime(tmp_path, resolver=_awaiting_resolver(tmp_path, {"claim_verify"}))
    state = runtime.run(
        prompt="Use the local PDF seed and outside-lab results to validate the result claim.",
        run_id="phase5-negative-import",
        seed_inputs=_pdf_seed(),
        max_steps=40,
    )
    assert state["node_states"]["claim_verify"]["status"] == "awaiting_external"
    return runtime, state, external


def test_resume_rejects_tampered_external_evidence_hash(
    tmp_path: Path,
    awaiting_experiment_run: tuple[SolarResearchRuntime, dict[str, Any], dict[str, Any]],
) -> None:
    runtime, state, external = awaiting_experiment_run
    result = _write_imported_claim_verdict(
        tmp_path,
        task_id=state["task_id"],
        run_id=state["run_id"],
        workflow_id=state["workflow_id"],
        external=external,
    )
    result["output_artifacts"][0]["sha256"] = "f" * 64
    result["hashes"][0]["value"] = "f" * 64

    with pytest.raises(ValueError, match="sha256"):
        runtime.run(
            prompt=state["prompt"],
            run_id=state["run_id"],
            seed_inputs=_pdf_seed(),
            run_mode="resume",
            explicit_workflow="paper_ingestion",
            imported_result=result,
        )


def test_resume_rejects_evidence_identity_for_wrong_run(
    tmp_path: Path,
    awaiting_experiment_run: tuple[SolarResearchRuntime, dict[str, Any], dict[str, Any]],
) -> None:
    runtime, state, external = awaiting_experiment_run
    result = _write_imported_claim_verdict(
        tmp_path,
        task_id=state["task_id"],
        run_id=state["run_id"],
        workflow_id=state["workflow_id"],
        external=external,
    )
    result["run_id"] = "wrong-phase5-run"

    with pytest.raises(ValueError, match="run_id"):
        runtime.run(
            prompt=state["prompt"],
            run_id=state["run_id"],
            seed_inputs=_pdf_seed(),
            run_mode="resume",
            explicit_workflow="paper_ingestion",
            imported_result=result,
        )


def test_resume_rejects_external_evidence_path_outside_node_write_scope(
    tmp_path: Path,
    awaiting_experiment_run: tuple[SolarResearchRuntime, dict[str, Any], dict[str, Any]],
) -> None:
    runtime, state, external = awaiting_experiment_run
    result = _write_imported_claim_verdict(
        tmp_path,
        task_id=state["task_id"],
        run_id=state["run_id"],
        workflow_id=state["workflow_id"],
        external=external,
    )
    outside = tmp_path / "outside-claim-verdict.v1.json"
    shutil.move(str(tmp_path / CLAIM_VERDICT_PATH), outside)
    result["output_artifacts"][0]["path"] = str(outside)
    result["output_artifacts"][0]["sha256"] = _sha256_file(outside)
    result["hashes"][0]["value"] = _sha256_file(outside)

    with pytest.raises(ValueError, match="write_scope|artifact_root"):
        runtime.run(
            prompt=state["prompt"],
            run_id=state["run_id"],
            seed_inputs=_pdf_seed(),
            run_mode="resume",
            explicit_workflow="paper_ingestion",
            imported_result=result,
        )


def test_external_experiment_fixture_matches_schema_identity_provenance_and_hash() -> None:
    external = _validate_external_experiment_fixture(FIXTURES / "external_experiment_evidence.json")
    schema = {
        "type": "object",
        "required": ["schema", "canonical_payload", "hashes"],
        "properties": {
            "schema": {"const": "external_experiment_evidence.v1"},
            "canonical_payload": {
                "type": "object",
                "required": ["experiment_identity", "method", "inputs", "results", "observed_at", "provenance"],
            },
            "hashes": {
                "type": "object",
                "required": ["algorithm", "canonical_payload_sha256"],
                "properties": {
                    "algorithm": {"const": "sha256"},
                    "canonical_payload_sha256": {"pattern": "^[A-Fa-f0-9]{64}$"},
                },
            },
        },
    }
    jsonschema.Draft202012Validator(schema).validate(external)
