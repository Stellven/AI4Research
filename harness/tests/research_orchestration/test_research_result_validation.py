from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.result_validation import (  # noqa: E402
    ResearchResultValidationError,
    validate_node_request,
    validate_node_result,
    validate_result_identity,
    validate_result_scopes,
)


REQUEST_SCHEMA = ROOT / "schemas/draft/research_node_request.v1.schema.json"
RESULT_SCHEMA = ROOT / "schemas/evidence/research_node_result.v1.schema.json"
HASH = "a" * 64


def valid_request() -> dict:
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-phase2",
        "run_id": "run-phase2",
        "workflow_id": "workflow-phase2",
        "node_id": "node-dispatch",
        "logical_operator": {
            "operator_id": "ScientificLiteratureDiscoverer",
            "operator_kind": "logical",
            "capabilities": ["cap.research-literature-discover"],
        },
        "physical_operator": {
            "operator_id": "autosci-literature-discover-worker",
            "operator_kind": "physical",
            "capabilities": ["bounded_worker"],
        },
        "typed_inputs": {
            "input_schema": "literature_discovery_request.v1",
            "payload": {"query": "bounded dispatch"},
        },
        "input_artifact_refs": [
            {"artifact_id": "task-contract", "path": "dispatch/task.json", "sha256": HASH}
        ],
        "authorization": {
            "scope_id": "scope-node-dispatch",
            "approved_capabilities": ["cap.research-literature-discover"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": ["dispatch/task.json"],
        "write_scope": ["artifacts/research/run-phase2/node-dispatch"],
        "timeout_retry_policy": {
            "timeout_seconds": 60,
            "max_attempts": 1,
            "retry_on": [],
        },
    }


def valid_result() -> dict:
    return {
        "schema": "research_node_result.v1",
        "task_id": "task-phase2",
        "run_id": "run-phase2",
        "workflow_id": "workflow-phase2",
        "node_id": "node-dispatch",
        "status": "completed",
        "status_is_terminal": True,
        "output_artifacts": [
            {
                "artifact_id": "discovery-result",
                "path": "artifacts/research/run-phase2/node-dispatch/result.json",
                "schema": "literature_discovery.v1",
                "sha256": HASH,
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev-discovery",
                "kind": "literature_discovery",
                "summary": "Worker produced a bounded result.",
                "artifact_id": "discovery-result",
            }
        ],
        "hashes": [{"hash_id": "discovery-result", "algorithm": "sha256", "value": HASH}],
        "model_provider_usage": [
            {"provider": "none", "model": "none", "usage_kind": "none"}
        ],
        "errors": [],
        "limitations": [],
        "secret_redaction_assertion": {
            "no_secrets_observed": True,
            "redaction_review": "passed",
        },
    }


def test_valid_request_result_identity_and_scopes_pass(tmp_path: Path) -> None:
    request = valid_request()
    result = valid_result()
    validate_node_request(request, REQUEST_SCHEMA)
    validate_node_result(result, RESULT_SCHEMA)
    validate_result_identity(request, result)
    validate_result_scopes(request, result, tmp_path)


def test_wrong_run_or_node_identity_is_rejected() -> None:
    request = valid_request()
    result = valid_result()
    for key in ("task_id", "run_id", "workflow_id", "node_id"):
        mutated = copy.deepcopy(result)
        mutated[key] = "wrong"
        with pytest.raises(ResearchResultValidationError, match=key):
            validate_result_identity(request, mutated)


def test_path_traversal_and_scope_escape_are_rejected(tmp_path: Path) -> None:
    request = valid_request()
    traversal = valid_result()
    traversal["output_artifacts"][0]["path"] = "../escape/result.json"
    with pytest.raises(ResearchResultValidationError, match="artifact_root"):
        validate_result_scopes(request, traversal, tmp_path)

    outside_scope = valid_result()
    outside_scope["output_artifacts"][0]["path"] = "artifacts/research/run-phase2/other/result.json"
    with pytest.raises(ResearchResultValidationError, match="write_scope"):
        validate_result_scopes(request, outside_scope, tmp_path)


def test_windows_and_unix_path_normalization_accept_in_scope_paths(tmp_path: Path) -> None:
    request = valid_request()
    request["write_scope"] = [r"artifacts\research\run-phase2\node-dispatch"]
    result = valid_result()
    result["output_artifacts"][0]["path"] = r"artifacts\research\run-phase2\node-dispatch\result.json"
    validate_result_scopes(request, result, tmp_path)

    request["write_scope"] = ["artifacts/research/run-phase2/node-dispatch"]
    result["output_artifacts"][0]["path"] = "artifacts/research/run-phase2/node-dispatch/result.json"
    validate_result_scopes(request, result, tmp_path)


def test_live_provider_requires_approval_and_network() -> None:
    request = valid_request()
    request["authorization"]["allow_live_provider"] = True
    request["authorization"]["allow_network"] = True
    with pytest.raises(ResearchResultValidationError):
        validate_node_request(request, REQUEST_SCHEMA)

    request["authorization"]["approval_ref"] = "approval-123"
    validate_node_request(request, REQUEST_SCHEMA)

    request["authorization"]["allow_network"] = False
    with pytest.raises(ResearchResultValidationError):
        validate_node_request(request, REQUEST_SCHEMA)


def test_completed_failed_terminal_hash_and_secret_invariants() -> None:
    completed = valid_result()
    completed["evidence"] = []
    with pytest.raises(ResearchResultValidationError, match="evidence"):
        validate_node_result(completed, RESULT_SCHEMA)

    failed = valid_result()
    failed["status"] = "failed"
    failed["errors"] = []
    with pytest.raises(ResearchResultValidationError, match="errors"):
        validate_node_result(failed, RESULT_SCHEMA)

    terminal_mismatch = valid_result()
    terminal_mismatch["status_is_terminal"] = False
    with pytest.raises(ResearchResultValidationError):
        validate_node_result(terminal_mismatch, RESULT_SCHEMA)

    bad_hash = valid_result()
    bad_hash["hashes"][0]["value"] = "not-a-hash"
    with pytest.raises(ResearchResultValidationError):
        validate_node_result(bad_hash, RESULT_SCHEMA)

    no_assertion = valid_result()
    no_assertion.pop("secret_redaction_assertion")
    with pytest.raises(ResearchResultValidationError):
        validate_node_result(no_assertion, RESULT_SCHEMA)


def test_worker_cannot_expand_capability_read_or_write_scope(tmp_path: Path) -> None:
    request = valid_request()
    request["physical_operator"]["capabilities"] = ["bounded_worker", "cap.not-approved"]
    with pytest.raises(ResearchResultValidationError, match="capabilities"):
        validate_result_scopes(request, valid_result(), tmp_path)

    request = valid_request()
    request["write_scope"] = ["../escape"]
    with pytest.raises(ResearchResultValidationError, match="scope"):
        validate_result_scopes(request, valid_result(), tmp_path)


def test_result_validation_does_not_mutate_inputs(tmp_path: Path) -> None:
    request = valid_request()
    result = valid_result()
    before_request = copy.deepcopy(request)
    before_result = copy.deepcopy(result)
    validate_node_request(request, REQUEST_SCHEMA)
    validate_node_result(result, RESULT_SCHEMA)
    validate_result_identity(request, result)
    validate_result_scopes(request, result, tmp_path)
    assert request == before_request
    assert result == before_result
