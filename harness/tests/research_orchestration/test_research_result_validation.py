from __future__ import annotations

import copy
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.result_validation import (  # noqa: E402
    ResearchResultValidationError,
    validate_node_request,
    validate_node_result,
    validate_request_artifact_scopes,
    validate_result_identity,
    validate_result_scopes,
)


REQUEST_SCHEMA = ROOT / "schemas/draft/research_node_request.v1.schema.json"
RESULT_SCHEMA = ROOT / "schemas/evidence/research_node_result.v1.schema.json"
HASH = "a" * 64


def _test_fs_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def _write_test_bytes(path: Path, content: bytes) -> None:
    os.makedirs(_test_fs_path(path.parent), exist_ok=True)
    with open(_test_fs_path(path), "wb") as handle:
        handle.write(content)


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


def materialize_result_artifacts(
    artifact_root: Path,
    result: dict,
    *,
    content: bytes = b"bounded worker artifact",
) -> Path:
    artifact = result["output_artifacts"][0]
    relative = str(artifact["path"]).replace("\\", "/")
    path = artifact_root / relative
    _write_test_bytes(path, content)
    digest = hashlib.sha256(content).hexdigest()
    artifact["sha256"] = digest
    for record in result.get("hashes") or []:
        if record.get("hash_id") == artifact.get("artifact_id"):
            record["value"] = digest
    return path


def materialize_request_artifacts(
    artifact_root: Path,
    request: dict,
    *,
    content: bytes = b"bounded request artifact",
) -> Path:
    artifact = request["input_artifact_refs"][0]
    relative = str(artifact["path"]).replace("\\", "/")
    path = artifact_root / relative
    _write_test_bytes(path, content)
    artifact["sha256"] = hashlib.sha256(content).hexdigest()
    return path


def test_valid_request_result_identity_and_scopes_pass(tmp_path: Path) -> None:
    request = valid_request()
    materialize_request_artifacts(tmp_path, request)
    result = valid_result()
    materialize_result_artifacts(tmp_path, result)
    validate_node_request(request, REQUEST_SCHEMA)
    validate_request_artifact_scopes(request, tmp_path)
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
    materialize_result_artifacts(tmp_path, result)
    validate_result_scopes(request, result, tmp_path)

    request["write_scope"] = ["artifacts/research/run-phase2/node-dispatch"]
    result["output_artifacts"][0]["path"] = "artifacts/research/run-phase2/node-dispatch/result.json"
    materialize_result_artifacts(tmp_path, result)
    validate_result_scopes(request, result, tmp_path)


def test_result_scope_validation_accepts_existing_long_windows_artifact_path(tmp_path: Path) -> None:
    artifact_root = (
        tmp_path
        / ("phase5-generalization-integration-" + "x" * 80)
        / ("content-diversity-artifact-root-" + "y" * 80)
        / ("run-with-long-id-" + "z" * 60)
    )
    request = valid_request()
    request["write_scope"] = ["artifacts/research/run-phase2/node-dispatch/"]
    result = valid_result()
    materialized = materialize_result_artifacts(artifact_root, result)

    assert len(str(materialized)) > 260
    validate_result_scopes(request, result, artifact_root)


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
    usage_is_not_a_secret = valid_result()
    usage_is_not_a_secret["model_provider_usage"][0].update(
        {"input_tokens": 10, "output_tokens": 20}
    )
    validate_node_result(usage_is_not_a_secret, RESULT_SCHEMA)

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

    leaked = valid_result()
    leaked["evidence"][0]["summary"] = "password=visible-password-value"
    with pytest.raises(ResearchResultValidationError, match="sensitive"):
        validate_node_result(leaked, RESULT_SCHEMA)


def test_legitimate_research_identifiers_are_not_classified_as_secrets() -> None:
    result = valid_result()
    result["task_id"] = "task-research-synthesis"
    result["limitations"] = ["risk-research-summary"]
    validate_node_result(result, RESULT_SCHEMA)


def test_schema_validation_message_scrubs_explicit_secret() -> None:
    canary = "schema-validation-canary-987654321"
    request = valid_request()
    request["typed_inputs"]["payload"] = canary
    with pytest.raises(ResearchResultValidationError) as excinfo:
        validate_node_request(request, REQUEST_SCHEMA, secret_values=(canary,))
    assert canary not in str(excinfo.value)
    assert "[SCRUBBED]" in str(excinfo.value)


def test_worker_cannot_expand_capability_read_or_write_scope(tmp_path: Path) -> None:
    request = valid_request()
    request["physical_operator"]["capabilities"] = ["bounded_worker", "cap.not-approved"]
    with pytest.raises(ResearchResultValidationError, match="capabilities"):
        validate_result_scopes(request, valid_result(), tmp_path)

    request = valid_request()
    request["write_scope"] = ["../escape"]
    with pytest.raises(ResearchResultValidationError, match="scope"):
        validate_result_scopes(request, valid_result(), tmp_path)


def test_input_artifacts_require_existing_read_scope_file_and_matching_hash(
    tmp_path: Path,
) -> None:
    missing_scope = valid_request()
    missing_scope["read_scope"] = []
    with pytest.raises(ResearchResultValidationError, match="read_scope"):
        validate_request_artifact_scopes(missing_scope, tmp_path)

    missing_file = valid_request()
    with pytest.raises(ResearchResultValidationError, match="read_scope does not exist"):
        validate_request_artifact_scopes(missing_file, tmp_path)

    wrong_hash = valid_request()
    materialize_request_artifacts(tmp_path, wrong_hash)
    wrong_hash["input_artifact_refs"][0]["sha256"] = "f" * 64
    with pytest.raises(ResearchResultValidationError, match="sha256"):
        validate_request_artifact_scopes(wrong_hash, tmp_path)

    outside_scope = valid_request()
    materialize_request_artifacts(tmp_path, outside_scope)
    outside_scope["read_scope"] = ["dispatch/other.json"]
    other = tmp_path / "dispatch/other.json"
    other.write_text("other", encoding="utf-8")
    with pytest.raises(ResearchResultValidationError, match="escapes read_scope"):
        validate_request_artifact_scopes(outside_scope, tmp_path)

def test_result_validation_does_not_mutate_inputs(tmp_path: Path) -> None:
    request = valid_request()
    result = valid_result()
    materialize_result_artifacts(tmp_path, result)
    before_request = copy.deepcopy(request)
    before_result = copy.deepcopy(result)
    validate_node_request(request, REQUEST_SCHEMA)
    validate_node_result(result, RESULT_SCHEMA)
    validate_result_identity(request, result)
    validate_result_scopes(request, result, tmp_path)
    assert request == before_request
    assert result == before_result


def test_output_artifact_must_exist_and_match_declared_hash(tmp_path: Path) -> None:
    request = valid_request()
    missing = valid_result()
    with pytest.raises(ResearchResultValidationError, match="does not exist"):
        validate_result_scopes(request, missing, tmp_path)

    mismatch = valid_result()
    path = materialize_result_artifacts(tmp_path, mismatch)
    mismatch["output_artifacts"][0]["sha256"] = "f" * 64
    with pytest.raises(ResearchResultValidationError, match="sha256"):
        validate_result_scopes(request, mismatch, tmp_path)

    matching_artifact_bad_record = valid_result()
    materialize_result_artifacts(tmp_path, matching_artifact_bad_record)
    matching_artifact_bad_record["hashes"][0]["value"] = "e" * 64
    with pytest.raises(ResearchResultValidationError, match="hash record"):
        validate_result_scopes(request, matching_artifact_bad_record, tmp_path)

    orphan = valid_result()
    materialize_result_artifacts(tmp_path, orphan)
    orphan["hashes"].append(
        {"hash_id": "not-an-artifact", "algorithm": "sha256", "value": "d" * 64}
    )
    with pytest.raises(ResearchResultValidationError, match="orphan"):
        validate_result_scopes(request, orphan, tmp_path)

    assert path.is_file()


def test_output_artifact_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "result.json").write_bytes(b"outside")
    link = tmp_path / "artifacts/research/run-phase2/node-dispatch"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("symlink creation is unavailable on this platform")
        created = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            pytest.skip("junction creation is unavailable on this platform")
    result = valid_result()
    result["output_artifacts"][0]["sha256"] = hashlib.sha256(b"outside").hexdigest()
    result["hashes"][0]["value"] = result["output_artifacts"][0]["sha256"]
    with pytest.raises(ResearchResultValidationError, match="artifact_root"):
        validate_result_scopes(valid_request(), result, tmp_path)


def test_input_read_scope_symlink_or_junction_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-input"
    outside.mkdir()
    content = b"outside input"
    (outside / "task.json").write_bytes(content)
    link = tmp_path / "dispatch"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("symlink creation is unavailable on this platform")
        created = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            pytest.skip("junction creation is unavailable on this platform")
    request = valid_request()
    request["input_artifact_refs"][0]["sha256"] = hashlib.sha256(content).hexdigest()
    with pytest.raises(ResearchResultValidationError, match="artifact_root"):
        validate_request_artifact_scopes(request, tmp_path)
