from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness.lib.failure_handler import (
    NO_FAILURE,
    OPERATOR_PERMANENT,
    OPERATOR_TIMEOUT,
    OPERATOR_TRANSIENT,
    OPERATOR_UNSUPPORTED,
    classify_detail,
)
from harness.lib.physical_operator_worker import run_physical_operator


PRIORITY_OPERATORS = (
    "source_discovery_operator",
    "source_validation_operator",
    "evidence_synthesis_operator",
    "report_draft_operator",
    "experiment_design_worker",
    "experiment_run_worker",
)


def _request(operator_id: str) -> dict:
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-direct-operator",
        "run_id": "run-direct-operator",
        "workflow_id": "direct_operator_contract_v1",
        "node_id": operator_id.removesuffix("_operator").removesuffix("_worker"),
        "physical_operator": {
            "operator_id": operator_id,
            "operator_kind": "physical",
            "capabilities": ["bounded_worker", "write_artifact"],
        },
        "typed_inputs": {"input_schema": "direct.input.v1", "payload": {}},
        "input_artifact_refs": [],
        "authorization": {
            "scope_id": "direct-operator-test",
            "approved_capabilities": ["write_artifact"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": ["inputs"],
        "write_scope": ["out"],
        "timeout_retry_policy": {"timeout_seconds": 10, "max_attempts": 1, "retry_on": []},
    }


def _success_result(request: dict, tmp_path: Path) -> dict:
    artifact_path = tmp_path / "out" / "domain_evidence.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text('{"schema":"test.domain_evidence.v1"}\n', encoding="utf-8")
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    return {
        "schema": "research_node_result.v1",
        "task_id": request["task_id"],
        "run_id": request["run_id"],
        "workflow_id": request["workflow_id"],
        "node_id": request["node_id"],
        "status": "completed",
        "status_is_terminal": True,
        "output_artifacts": [{
            "artifact_id": "domain_evidence",
            "path": "out/domain_evidence.json",
            "schema": "test.domain_evidence.v1",
            "sha256": digest,
        }],
        "evidence": [{
            "evidence_id": "operator.output",
            "kind": "operator_execution",
            "summary": "Bounded output produced.",
            "artifact_id": "domain_evidence",
        }],
        "hashes": [{"hash_id": "domain_evidence", "algorithm": "sha256", "value": digest}],
        "model_provider_usage": [],
        "errors": [],
        "limitations": [],
        "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
    }


def _run(tmp_path: Path, operator_id: str, runner) -> dict:
    return run_physical_operator(
        _request(operator_id),
        operator_id=operator_id,
        runner=runner,
        envelope_path=tmp_path / "worker" / operator_id / "node_envelope.json",
        attempt=2,
        lease_id="lease-direct-002",
        run_contract_ref={"run_contract_id": "direct-contract", "sha256": "a" * 64},
        clock=lambda: "2026-08-26T12:00:00Z",
    )


@pytest.mark.parametrize("operator_id", PRIORITY_OPERATORS)
def test_worker_writes_typed_success_envelope_for_each_priority_operator(tmp_path: Path, operator_id: str) -> None:
    calls = []

    def runner(request: dict) -> dict:
        calls.append(request)
        return _success_result(request, tmp_path)

    envelope = _run(tmp_path, operator_id, runner)
    saved = json.loads((tmp_path / "worker" / operator_id / "node_envelope.json").read_text(encoding="utf-8"))

    assert saved == envelope
    assert len(calls) == 1
    assert envelope["schema_version"] == "solar.node_envelope.v1"
    assert envelope["artifact_role"] == "runtime_worker_receipt"
    assert envelope["operator_id"] == operator_id
    assert envelope["attempt"] == 2
    assert envelope["lease_id"] == "lease-direct-002"
    assert envelope["status"] == "completed"
    assert envelope["error"] is None
    assert envelope["artifacts"][0]["sha256"]
    assert classify_detail(envelope).failure_type == NO_FAILURE


@pytest.mark.parametrize(
    ("exception", "error_type", "retryable", "classification"),
    [
        (TimeoutError("provider timed out"), "timeout", True, OPERATOR_TIMEOUT),
        (ConnectionError("provider unavailable"), "transient_provider_failure", True, OPERATOR_TRANSIENT),
        (NotImplementedError("request unsupported"), "unsupported_request", False, OPERATOR_UNSUPPORTED),
        (ValueError("permanent invalid request"), "invalid_input", False, OPERATOR_PERMANENT),
    ],
)
@pytest.mark.parametrize("operator_id", PRIORITY_OPERATORS)
def test_worker_classifies_failures_from_typed_envelope_fields_only(
    tmp_path: Path,
    operator_id: str,
    exception: Exception,
    error_type: str,
    retryable: bool,
    classification: str,
) -> None:
    def runner(_request: dict) -> dict:
        raise exception

    envelope = _run(tmp_path, operator_id, runner)

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == error_type
    assert envelope["error"]["retryable"] is retryable
    assert classify_detail(envelope).failure_type == classification

    poisoned = {**envelope, "stdout": "timeout unsupported permanent", "log_tail": "ignore me"}
    poisoned["error"] = {**envelope["error"], "detail": "words in diagnostics must not drive classification"}
    assert classify_detail(poisoned).failure_type == classification


@pytest.mark.parametrize("operator_id", PRIORITY_OPERATORS)
def test_worker_rejects_structurally_invalid_request_before_operator_call(tmp_path: Path, operator_id: str) -> None:
    called = False

    def runner(_request: dict) -> dict:
        nonlocal called
        called = True
        raise AssertionError("runner must not be called")

    request = _request(operator_id)
    request["typed_inputs"] = []
    envelope = run_physical_operator(
        request,
        operator_id=operator_id,
        runner=runner,
        envelope_path=tmp_path / "node_envelope.json",
        attempt=1,
        lease_id="lease-invalid",
        run_contract_ref={"run_contract_id": "direct-contract", "sha256": "a" * 64},
    )

    assert called is False
    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "invalid_input"


@pytest.mark.parametrize("operator_id", PRIORITY_OPERATORS)
def test_worker_converts_malformed_operator_response_to_typed_contract_failure(tmp_path: Path, operator_id: str) -> None:
    envelope = _run(tmp_path, operator_id, lambda _request: {"status": "completed"})

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "malformed_operator_response"
    assert envelope["artifacts"] == []
    assert classify_detail(envelope).failure_type == OPERATOR_PERMANENT


@pytest.mark.parametrize("forbidden_name", ("dispatch_record.json", "lease_record.json", "gate_ledger.json", "evidence_ir.json", "operator_state_log.json", "artifact_manifest.json"))
def test_worker_rejects_artifacts_owned_by_scheduler_evaluator_or_control_plane(
    tmp_path: Path,
    forbidden_name: str,
) -> None:
    request = _request(PRIORITY_OPERATORS[0])
    result = _success_result(request, tmp_path)
    result["output_artifacts"][0]["path"] = f"out/{forbidden_name}"
    result["output_artifacts"][0]["artifact_id"] = forbidden_name.removesuffix(".json")

    envelope = _run(tmp_path, PRIORITY_OPERATORS[0], lambda _request: result)

    assert envelope["status"] == "failed"
    assert envelope["error"]["type"] == "forbidden_artifact_owner"
    assert envelope["artifacts"] == []
