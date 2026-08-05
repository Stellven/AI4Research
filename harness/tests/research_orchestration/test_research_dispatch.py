from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.dispatch import (  # noqa: E402
    dispatch_research_node,
    operator_runtime_submit_adapter,
    synchronous_json_command_runner,
)
from research_orchestration.result_validation import ResearchResultValidationError  # noqa: E402
from research_orchestration.transport import ResearchTransportError  # noqa: E402
from test_research_result_validation import RESULT_SCHEMA, REQUEST_SCHEMA, valid_request, valid_result  # noqa: E402


def test_dispatch_returns_completed_worker_result(tmp_path: Path) -> None:
    request = valid_request()

    def runner(node_request: dict) -> dict:
        result = valid_result()
        assert node_request == request
        return result

    result = dispatch_research_node(
        request,
        runner=runner,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert result["status"] == "completed"


def test_dispatch_accepts_failed_worker_result(tmp_path: Path) -> None:
    request = valid_request()
    failed = valid_result()
    failed["status"] = "failed"
    failed["status_is_terminal"] = True
    failed["output_artifacts"] = []
    failed["evidence"] = []
    failed["errors"] = [
        {"error_id": "worker-failed", "error_type": "worker_failed", "message": "worker failed"}
    ]

    result = dispatch_research_node(
        request,
        runner=lambda _: failed,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert result["status"] == "failed"


def test_operator_runtime_submit_adapter_returns_awaiting_external_receipt(tmp_path: Path) -> None:
    request = valid_request()

    def submit(envelope: dict) -> dict:
        assert envelope["operator_id"] == request["physical_operator"]["operator_id"]
        return {"status": "submitted", "inbox_path": "inbox/task.json"}

    result = dispatch_research_node(
        request,
        runner=operator_runtime_submit_adapter(submit=submit),
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert result["status"] == "awaiting_external"
    assert result["status_is_terminal"] is False
    assert result["evidence"][0]["kind"] == "operator_runtime_receipt"


def test_malformed_request_is_rejected_before_runner(tmp_path: Path) -> None:
    request = valid_request()
    request.pop("task_id")
    called = False

    def runner(_: dict) -> dict:
        nonlocal called
        called = True
        return valid_result()

    with pytest.raises(ResearchResultValidationError):
        dispatch_research_node(
            request,
            runner=runner,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
        )
    assert called is False


def test_malformed_result_and_wrong_identity_are_rejected(tmp_path: Path) -> None:
    request = valid_request()
    malformed = valid_result()
    malformed.pop("schema")
    with pytest.raises(ResearchResultValidationError):
        dispatch_research_node(
            request,
            runner=lambda _: malformed,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
        )

    wrong_identity = valid_result()
    wrong_identity["node_id"] = "other-node"
    with pytest.raises(ResearchResultValidationError, match="node_id"):
        dispatch_research_node(
            request,
            runner=lambda _: wrong_identity,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
        )


def test_runner_exception_converts_to_contract_failed_result(tmp_path: Path) -> None:
    request = valid_request()

    def runner(_: dict) -> dict:
        raise RuntimeError("boom")

    result = dispatch_research_node(
        request,
        runner=runner,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "RuntimeError"
    assert result["evidence"] == []


def test_transport_exception_converts_to_scrubbed_failed_result(tmp_path: Path) -> None:
    request = valid_request()

    def runner(_: dict) -> dict:
        raise ResearchTransportError("nonzero_exit", "token=sk-" + "a" * 40)

    result = dispatch_research_node(
        request,
        runner=runner,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert result["status"] == "failed"
    assert "sk-" not in result["errors"][0]["message"]
    assert "[SCRUBBED]" in result["errors"][0]["message"]


def test_live_provider_without_approval_or_network_is_rejected(tmp_path: Path) -> None:
    request = valid_request()
    request["authorization"]["allow_live_provider"] = True
    request["authorization"]["allow_network"] = True
    with pytest.raises(ResearchResultValidationError):
        dispatch_research_node(
            request,
            runner=lambda _: valid_result(),
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
        )

    request["authorization"]["approval_ref"] = "approval-123"
    request["authorization"]["allow_network"] = False
    with pytest.raises(ResearchResultValidationError):
        dispatch_research_node(
            request,
            runner=lambda _: valid_result(),
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
        )


def test_dispatch_does_not_mutate_request_or_result(tmp_path: Path) -> None:
    request = valid_request()
    result = valid_result()
    before_request = copy.deepcopy(request)
    before_result = copy.deepcopy(result)
    dispatch_research_node(
        request,
        runner=lambda _: result,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert request == before_request
    assert result == before_result


def test_synchronous_json_command_runner(tmp_path: Path) -> None:
    worker = tmp_path / "worker.py"
    worker.write_text(
        """
import json, sys
request = json.loads(sys.stdin.read())
result = {
  "schema": "research_node_result.v1",
  "task_id": request["task_id"],
  "run_id": request["run_id"],
  "workflow_id": request["workflow_id"],
  "node_id": request["node_id"],
  "status": "completed",
  "status_is_terminal": True,
  "output_artifacts": [{
    "artifact_id": "discovery-result",
    "path": "artifacts/research/run-phase2/node-dispatch/result.json",
    "schema": "literature_discovery.v1",
    "sha256": "a" * 64
  }],
  "evidence": [{"evidence_id": "ev", "kind": "worker", "summary": "done"}],
  "hashes": [{"hash_id": "h", "algorithm": "sha256", "value": "a" * 64}],
  "model_provider_usage": [{"provider": "none", "model": "none", "usage_kind": "none"}],
  "errors": [],
  "limitations": [],
  "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"}
}
print(json.dumps(result))
""",
        encoding="utf-8",
    )
    request = valid_request()
    runner = synchronous_json_command_runner(
        [sys.executable, str(worker)],
        cwd=tmp_path,
        timeout_seconds=5,
    )
    result = dispatch_research_node(
        request,
        runner=runner,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert result["status"] == "completed"
