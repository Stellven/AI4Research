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
from harness.plugins.autosci.operators.scientific_lifecycle.registry import registration_entries


REPO = Path(__file__).resolve().parents[4]
FIXTURES = REPO / "tests" / "harness" / "evaluators" / "scientific" / "fixtures" / "pass"
RESULT_PATH = REPO / ".codex-tmp" / "phase22-worker-results" / "all-action-contracts" / "result.json"
RESULT_REQUIRED_FIELDS = {
    "schema",
    "task_id",
    "run_id",
    "workflow_id",
    "node_id",
    "status",
    "status_is_terminal",
    "output_artifacts",
    "evidence",
    "hashes",
    "model_provider_usage",
    "errors",
    "limitations",
    "secret_redaction_assertion",
}
ACTION_NODES = (
    "idea_generate",
    "idea_evaluate",
    "experiment_design",
    "experiment_approval_gate",
    "experiment_run",
    "experiment_monitor",
    "claim_verify",
    "report_plan",
    "report_draft",
    "artifact_review",
    "publication_produce",
    "final_evaluation",
    "workflow_evolve",
)
USER_TEST_APPROVAL_REF = "user-message:2026-08-26:approve-all-tests"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _input_ref(tmp_path: Path, name: str, schema: str, outputs: dict[str, Any]) -> dict[str, str]:
    path = tmp_path / "inputs" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": schema,
        "task_id": "task-all-action-contracts",
        "sprint_id": "run-all-action-contracts",
        "node_id": name,
        "status": "completed",
        "inputs": {},
        "outputs": outputs,
        "artifacts": [],
        "provenance": {},
        "limitations": [],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "artifact_id": name,
        "path": path.relative_to(tmp_path).as_posix(),
        "schema": schema,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _task_contract() -> dict[str, Any]:
    return {
        "user_intent": "Assess whether fixture evidence supports an evidence coverage result.",
        "deliverable": {
            "required_content": [
                {"requirement_id": "result_claims", "description": "Preserve result claims.", "required": True},
                {"requirement_id": "limitations", "description": "Preserve limitations.", "required": True},
            ],
            "review_requirement": {
                "expected_mode": "local_surrogate",
                "independent_peer_review_required": False,
                "limitation_disclosure_required": True,
            },
        },
        "success_criteria": [
            "Every reported claim is linked to evidence sources",
            "The final report contains non-empty body content",
            "The local structural review is disclosed with its independent-review limitation",
        ],
        "run_provenance": {
            "repo_head": "test",
            "worktree_status": "not_asserted",
            "captured_at": "2026-08-26T12:00:00Z",
            "workflow_identity": {
                "workflow_id": "scientific_research_lifecycle_full_v1",
                "workflow_version": 1,
                "workflow_kind": "scientific_lifecycle",
            },
        },
    }


def _report_revision_regression_idea() -> dict[str, Any]:
    """A real test idea grounded in the observed report-revision defect."""

    evidence_ids = [
        "harness/plugins/autosci/operators/research_synthesis/report_revision.py",
        (
            "tests/plugins/autosci/physical_operator_contract/"
            "test_all_synthesis_result_receipt_contracts.py::"
            "test_all_research_synthesis_physical_operators_emit_result_and_worker_receipt"
        ),
    ]
    return {
        "schema": "idea_candidate.v1",
        "outputs": {
            "ideas": [
                {
                    "idea_id": "idea-report-revision-missing-input",
                    "title": "Report revision must fail closed without upstream evidence",
                    "hypothesis": (
                        "Requiring all hash-bound upstream artifacts prevents report_revision "
                        "from claiming completion with an empty Markdown report."
                    ),
                    "approach": (
                        "Call the production report_revision worker without upstream artifact "
                        "references and inspect its typed result and persisted worker receipt."
                    ),
                    "origin_evidence_ids": evidence_ids,
                    "source_proof": {
                        "status": "source_backed",
                        "evidence_ids": evidence_ids,
                        "proof": "The defect and its regression selector are present in the checked-out repository.",
                        "limitations": [],
                    },
                    "risks": ["A malformed result could still be wrapped unless the worker boundary rejects it."],
                    "falsifiability": (
                        "The hypothesis is false if the worker completes or writes artifacts when the four "
                        "required upstream references are absent."
                    ),
                    "validation_method": "Run the focused physical-operator contract test and inspect its receipt.",
                    "minimum_experiment": (
                        "Invoke report_revision_worker once with no upstream artifact references; require "
                        "status=failed, error_type=missing_input, and zero output artifacts."
                    ),
                }
            ]
        },
    }


def _operator_by_node() -> dict[str, str]:
    return {
        item["node_id"]: item["physical_operator_id"]
        for item in registration_entries()
        if item["node_id"] in ACTION_NODES
    }


def _request(
    node_id: str,
    operator_id: str,
    *,
    payload: dict[str, Any] | None = None,
    refs: list[dict[str, Any]] | None = None,
    write_scope: list[str] | None = None,
    capabilities: list[str] | None = None,
    approval_ref: str | None = None,
) -> dict[str, Any]:
    approved_capabilities = list(capabilities or ["write_artifact"])
    authorization: dict[str, Any] = {
        "scope_id": "all-action-contracts",
        "approved_capabilities": approved_capabilities,
        "allow_network": False,
        "allow_live_provider": False,
        "secret_refs": [],
    }
    if approval_ref:
        authorization["approval_ref"] = approval_ref
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-all-action-contracts",
        "run_id": "run-all-action-contracts",
        "workflow_id": "scientific_research_lifecycle_full_v1",
        "node_id": node_id,
        "logical_operator": {"operator_id": f"logical-{node_id}", "operator_kind": "logical"},
        "physical_operator": {
            "operator_id": operator_id,
            "operator_kind": "physical",
            "capabilities": ["bounded_worker", *approved_capabilities],
        },
        "typed_inputs": {
            "input_schema": f"{node_id}.input.v1",
            "payload": {
                "evidence_timestamp": "2026-08-26T12:00:00Z",
                "task_contract": _task_contract(),
                **(payload or {}),
            },
        },
        "input_artifact_refs": list(refs or []),
        "authorization": authorization,
        "read_scope": ["inputs", "out"],
        "write_scope": write_scope or [f"out/{node_id}"],
        "timeout_retry_policy": {"timeout_seconds": 30, "max_attempts": 1, "retry_on": []},
    }


def _run(
    tmp_path: Path,
    operator_by_node: dict[str, str],
    node_id: str,
    *,
    payload: dict[str, Any] | None = None,
    refs: list[dict[str, Any]] | None = None,
    write_scope: list[str] | None = None,
    capabilities: list[str] | None = None,
    approval_ref: str | None = None,
    use_environment_services: bool = False,
) -> dict[str, Any]:
    request = _request(
        node_id,
        operator_by_node[node_id],
        payload=payload,
        refs=refs,
        write_scope=write_scope,
        capabilities=capabilities,
        approval_ref=approval_ref,
    )
    resolver = default_production_resolver(
        services=None if use_environment_services else {},
        workspace_root=tmp_path,
    )
    return run_physical_operator(
        request,
        operator_id=operator_by_node[node_id],
        runner=resolver.execute,
        envelope_path=tmp_path / "worker" / node_id / "node_envelope.json",
        attempt=1,
        lease_id=f"lease-{node_id}",
        run_contract_ref={"run_contract_id": "all-action-contracts", "sha256": "c" * 64},
        clock=lambda: "2026-08-26T12:00:00Z",
    )


def _assert_worker_contract(tmp_path: Path, envelope: dict[str, Any], node_id: str, operator_id: str) -> None:
    saved = json.loads((tmp_path / "worker" / node_id / "node_envelope.json").read_text(encoding="utf-8"))
    assert saved == envelope
    assert envelope["schema_version"] == "solar.node_envelope.v1"
    assert envelope["artifact_role"] == "runtime_worker_receipt"
    assert envelope["operator_id"] == operator_id
    assert envelope["task_id"] == "task-all-action-contracts"
    assert envelope["run_id"] == "run-all-action-contracts"
    assert envelope["workflow_id"] == "scientific_research_lifecycle_full_v1"
    assert envelope["node"] == node_id
    assert envelope["status"] in {
        "completed",
        "failed",
        "blocked",
        "cancelled",
        "awaiting_human",
        "awaiting_external",
    }
    if envelope["status"] == "completed":
        assert envelope["error"] is None
        assert envelope["self_reported"]["schema"] == "research_node_result.v1"
        assert envelope["self_reported"]["evidence"]
    else:
        assert envelope["error"]
        assert envelope["error"]["type"]
    for artifact in envelope["artifacts"]:
        artifact_path = tmp_path / artifact["path"]
        assert artifact_path.is_file()
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
    assert set(envelope["self_reported"]) == {
        "schema",
        "status_is_terminal",
        "evidence",
        "hashes",
        "model_provider_usage",
        "limitations",
        "secret_redaction_assertion",
    }
    assert envelope["self_reported"]["schema"] == "research_node_result.v1"
    assert envelope["self_reported"]["secret_redaction_assertion"]["no_secrets_observed"] is True


def _case_status(envelope: dict[str, Any]) -> str:
    if envelope["status"] == "completed":
        return "PASS"
    if envelope["error"]["type"] in {
        "approval_required",
        "environment_unavailable",
        "invalid_input",
        "missing_input",
        "provider_unavailable",
        "quality_gate_failed",
        "safety_violation",
    }:
        return "BLOCKED"
    return "FAIL"


def _record_result(rows: list[dict[str, Any]]) -> None:
    schema_path = REPO / "harness" / "schemas" / "evidence" / "research_node_result.v1.schema.json"
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(
            {
                "batch_id": "all-action-contracts",
                "schema": "phase22.worker_result.v1",
                "status": "PASS" if all(row["case_status"] in {"PASS", "BLOCKED"} for row in rows) else "FAIL",
                "requested_operator_count": len(ACTION_NODES),
                "observed_operator_count": len(rows),
                "operators": rows,
                "repository_blockers": [
                    {
                        "type": "schema_file_missing",
                        "path": str(schema_path.relative_to(REPO)).replace("\\", "/"),
                        "impact": "File-based JSON Schema validation is blocked; fixed fields were checked through run_physical_operator.",
                    }
                ] if not schema_path.exists() else [],
                "files_changed_by_test": [
                    ".codex-tmp/phase22-worker-results/all-action-contracts/result.json"
                ],
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def test_all_action_workers_return_valid_result_and_worker_receipt(tmp_path: Path) -> None:
    operator_by_node = _operator_by_node()
    assert operator_by_node == {node_id: f"{node_id}_worker" for node_id in ACTION_NODES}

    rows: list[dict[str, Any]] = []

    def run_case(node_id: str, **kwargs: Any) -> dict[str, Any]:
        envelope = _run(tmp_path, operator_by_node, node_id, **kwargs)
        _assert_worker_contract(tmp_path, envelope, node_id, operator_by_node[node_id])
        row = {
            "node_id": node_id,
            "operator_id": operator_by_node[node_id],
            "case_status": _case_status(envelope),
            "node_status": envelope["status"],
            "error_type": (envelope["error"] or {}).get("type"),
            "artifact_count": len(envelope["artifacts"]),
            "result_required_fields_checked": sorted(RESULT_REQUIRED_FIELDS),
            "receipt_schema": envelope["schema_version"],
        }
        rows.append(row)
        return envelope

    run_case(
        "idea_generate",
        payload={"research_context": {"question": "Do code-linked evidence maps improve claim coverage?"}},
    )
    idea_candidate = _report_revision_regression_idea()
    idea_evaluation = run_case("idea_evaluate", payload={"idea_candidate": idea_candidate})
    experiment_plan = run_case(
        "experiment_design",
        payload={
            "idea_candidate": idea_candidate,
            "sandbox": {"mode": "isolated", "network": False, "write_scope": ["out/experiment_run"]},
        },
    )
    experiment_approval = run_case(
        "experiment_approval_gate",
        refs=experiment_plan["artifacts"],
        write_scope=["out/experiment_approval_gate", "out/experiment_run"],
        capabilities=["write_artifact", "execute_experiment"],
        approval_ref=USER_TEST_APPROVAL_REF,
    )
    run_case(
        "experiment_run",
        refs=[*experiment_plan["artifacts"], *experiment_approval["artifacts"]],
        write_scope=["out/experiment_run"],
        capabilities=["write_artifact", "execute_experiment"],
        approval_ref=USER_TEST_APPROVAL_REF,
    )
    run_case("experiment_monitor", payload={"experiment_result": _fixture("experiment_result.json")})
    verified = run_case(
        "claim_verify",
        payload={
            "claims": _fixture("research_claims.json"),
            "experiment_result": _fixture("experiment_result.json"),
        },
    )
    planned = run_case(
        "report_plan",
        refs=verified["artifacts"],
        payload={"topic": "Fixture evidence coverage result"},
    )
    drafted = run_case("report_draft", refs=[*planned["artifacts"], *verified["artifacts"]])
    reviewed = run_case("artifact_review", refs=drafted["artifacts"])
    published = run_case("publication_produce", refs=[*drafted["artifacts"], *reviewed["artifacts"]])
    run_case(
        "final_evaluation",
        refs=[*published["artifacts"], *reviewed["artifacts"], *drafted["artifacts"], *verified["artifacts"]],
    )
    run_case("workflow_evolve", refs=reviewed["artifacts"])

    assert len(rows) == len(ACTION_NODES)
    assert any(row["case_status"] == "BLOCKED" for row in rows)
    assert idea_evaluation["status"] == "completed"
    _record_result(rows)


@pytest.mark.live_provider
def test_production_services_complete_idea_experiment_and_final_evaluation_chain(tmp_path: Path) -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY is not loaded into the test process")
    operator_by_node = _operator_by_node()
    live_task_contract = {
        **_task_contract(),
        "user_intent": "Assess whether J21 punctuation normalization improves classification accuracy.",
    }
    fixture_root = REPO / "tests" / "journeys" / "phase22" / "fixtures" / "j21_experiment_build_handoff"
    input_root = tmp_path / "inputs" / "j21"
    input_root.mkdir(parents=True)
    runner = input_root / "run_text_experiment.py"
    dataset = input_root / "input_samples.csv"
    shutil.copy2(fixture_root / runner.name, runner)
    shutil.copy2(fixture_root / dataset.name, dataset)
    runner_ref = runner.relative_to(tmp_path).as_posix()
    dataset_ref = dataset.relative_to(tmp_path).as_posix()
    result_ref = "out/experiment_run/runtime_result.json"
    criterion = "accuracy_uplift > 0"

    idea_generation = _run(
        tmp_path,
        operator_by_node,
        "idea_generate",
        payload={
            "task_contract": live_task_contract,
            "research_context": {
                "question": live_task_contract["user_intent"],
                "evidence_ids": [dataset_ref, runner_ref],
                "dataset": "Six checked-in labeled text samples.",
                "candidate_method": "Compare baseline matching with punctuation-aware normalization.",
            },
            "constraints": {"maximum_ideas": 1, "network": "denied"},
        },
        use_environment_services=True,
    )
    _assert_worker_contract(
        tmp_path,
        idea_generation,
        "idea_generate",
        operator_by_node["idea_generate"],
    )
    assert idea_generation["status"] == "completed"
    usage = idea_generation["self_reported"]["model_provider_usage"]
    assert usage and all(item["provider"] == "openrouter" for item in usage)
    assert all(item["model"] == "deepseek/deepseek-v3.2" for item in usage)

    plan = _run(
        tmp_path,
        operator_by_node,
        "experiment_design",
        payload={
            "task_contract": live_task_contract,
            "idea_candidate": json.loads((tmp_path / idea_generation["artifacts"][0]["path"]).read_text(encoding="utf-8")),
            "experiment_id": "p22-j21-local-experiment",
            "sandbox": {"mode": "process_restricted", "network": False, "write_scope": ["out/experiment_run"]},
            "expected_artifacts": [result_ref],
            "metrics": ["baseline_accuracy", "variant_accuracy", "accuracy_uplift"],
            "success_criteria": [criterion],
            "criteria_bindings": [
                {"criterion": criterion, "metric": "accuracy_uplift", "operator": ">", "value": 0}
            ],
            "execution": {
                "contract": "python_json_file.v1",
                "command_argv": ["python", runner_ref, dataset_ref, result_ref],
                "runner_sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
                "input_sha256s": {dataset_ref: hashlib.sha256(dataset.read_bytes()).hexdigest()},
                "result_path": result_ref,
            },
        },
        use_environment_services=True,
    )
    approval = _run(
        tmp_path,
        operator_by_node,
        "experiment_approval_gate",
        refs=plan["artifacts"],
        write_scope=["out/experiment_approval_gate", "out/experiment_run"],
        capabilities=["write_artifact", "execute_experiment"],
        approval_ref=USER_TEST_APPROVAL_REF,
        payload={"task_contract": live_task_contract},
        use_environment_services=True,
    )
    execution = _run(
        tmp_path,
        operator_by_node,
        "experiment_run",
        refs=[*plan["artifacts"], *approval["artifacts"]],
        write_scope=["out/experiment_run"],
        capabilities=["write_artifact", "execute_experiment"],
        approval_ref=USER_TEST_APPROVAL_REF,
        payload={"task_contract": live_task_contract},
        use_environment_services=True,
    )
    _assert_worker_contract(
        tmp_path,
        execution,
        "experiment_run",
        operator_by_node["experiment_run"],
    )
    assert execution["status"] == "completed"
    experiment_payload = json.loads((tmp_path / execution["artifacts"][0]["path"]).read_text(encoding="utf-8"))
    experiment = experiment_payload["outputs"]["result"]
    assert experiment["outcome"] == "supports"
    assert experiment["criteria_results"] == {criterion: True}

    claim_id = "claim-j21-positive-uplift"
    claim_ref = _input_ref(tmp_path, "j21_claims", "research_claims.v1", {
        "claims": [{
            "claim_id": claim_id,
            "text": "On the six checked-in J21 samples, punctuation normalization improved classification accuracy.",
            "acceptance_criteria": [criterion],
            "evidence_ids": [dataset_ref, runner_ref],
        }]
    })
    verified = _run(
        tmp_path,
        operator_by_node,
        "claim_verify",
        payload={"task_contract": live_task_contract},
        refs=[claim_ref, *execution["artifacts"]],
        use_environment_services=True,
    )
    assert verified["status"] == "completed"
    verdict_payload = json.loads((tmp_path / verified["artifacts"][0]["path"]).read_text(encoding="utf-8"))
    assert verdict_payload["outputs"]["verdicts"][0]["support_classification"] == "supported"

    planned = _run(
        tmp_path,
        operator_by_node,
        "report_plan",
        payload={
            "task_contract": live_task_contract,
            "topic": "J21 punctuation normalization classification accuracy",
        },
        refs=verified["artifacts"],
        use_environment_services=True,
    )
    method_ref = _input_ref(tmp_path, "j21_method", "research_method.v1", {
        "methods": [{
            "method_id": "method-j21-punctuation-normalization",
            "name": "J21 punctuation normalization comparison",
            "summary": "Compare baseline matching with lowercased punctuation-normalized matching on the checked-in J21 sample.",
            "procedure": [
                "Run both classifiers on each labeled sample.",
                "Measure accuracy and compute variant accuracy minus baseline accuracy.",
            ],
            "source_papers": [],
            "evidence_ids": [dataset_ref, runner_ref],
            "extraction_basis": "checked_in_experiment_runner",
        }]
    })
    drafted = _run(
        tmp_path,
        operator_by_node,
        "report_draft",
        payload={"task_contract": live_task_contract},
        refs=[*planned["artifacts"], *verified["artifacts"], method_ref],
        use_environment_services=True,
    )
    reviewed = _run(
        tmp_path,
        operator_by_node,
        "artifact_review",
        payload={"task_contract": live_task_contract},
        refs=drafted["artifacts"],
        use_environment_services=True,
    )
    published = _run(
        tmp_path,
        operator_by_node,
        "publication_produce",
        payload={"task_contract": live_task_contract},
        refs=[*drafted["artifacts"], *reviewed["artifacts"]],
        use_environment_services=True,
    )
    final = _run(
        tmp_path,
        operator_by_node,
        "final_evaluation",
        payload={"task_contract": live_task_contract},
        refs=[
            *published["artifacts"],
            *reviewed["artifacts"],
            *drafted["artifacts"],
            *verified["artifacts"],
            method_ref,
        ],
        use_environment_services=True,
    )
    _assert_worker_contract(tmp_path, final, "final_evaluation", operator_by_node["final_evaluation"])
    assert final["status"] == "completed"
    final_payload = json.loads((tmp_path / final["artifacts"][0]["path"]).read_text(encoding="utf-8"))
    assert final_payload["outputs"]["evaluation"]["accepted"] is True
