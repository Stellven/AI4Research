from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.dispatch import (  # noqa: E402
    ResearchDispatchError,
    dispatch_research_node as _dispatch_research_node,
    operator_runtime_submit_adapter,
    synchronous_json_command_runner,
)
from research_orchestration.result_validation import ResearchResultValidationError  # noqa: E402
from research_orchestration.transport import ResearchTransportError  # noqa: E402
from test_research_result_validation import (  # noqa: E402
    RESULT_SCHEMA,
    REQUEST_SCHEMA,
    materialize_request_artifacts,
    materialize_result_artifacts,
    valid_request,
    valid_result,
)


def dispatch_research_node(*args, **kwargs):
    """Inject the explicit physical-operator fixture used by unit tests."""

    kwargs.setdefault(
        "operator_resolver",
        lambda operator_id: {"operator_id": operator_id, "enabled": True},
    )
    return _dispatch_research_node(*args, **kwargs)


def dispatch_request(tmp_path: Path) -> dict:
    request = valid_request()
    materialize_request_artifacts(tmp_path, request)
    return request


def test_dispatch_returns_completed_worker_result(tmp_path: Path) -> None:
    request = dispatch_request(tmp_path)
    completed = valid_result()
    materialize_result_artifacts(tmp_path, completed)

    def runner(node_request: dict) -> dict:
        assert node_request == request
        return completed

    result = dispatch_research_node(
        request,
        runner=runner,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert result["status"] == "completed"


def test_dispatch_accepts_failed_worker_result(tmp_path: Path) -> None:
    request = dispatch_request(tmp_path)
    failed = valid_result()
    failed["status"] = "failed"
    failed["status_is_terminal"] = True
    failed["output_artifacts"] = []
    failed["evidence"] = []
    failed["hashes"] = []
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
    request = dispatch_request(tmp_path)

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
    assert result["evidence"][0]["receipt"] == {
        "status": "submitted",
        "inbox_path": "inbox/task.json",
    }


def test_malformed_request_is_rejected_before_runner(tmp_path: Path) -> None:
    request = dispatch_request(tmp_path)
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
    request = dispatch_request(tmp_path)
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
    request = dispatch_request(tmp_path)

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
    request = dispatch_request(tmp_path)

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
    request = dispatch_request(tmp_path)
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
    request = dispatch_request(tmp_path)
    result = valid_result()
    materialize_result_artifacts(tmp_path, result)
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
import hashlib, json, sys
from pathlib import Path
request = json.loads(sys.stdin.read())
artifact = Path("artifacts/research/run-phase2/node-dispatch/result.json")
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_bytes(b"worker artifact")
digest = hashlib.sha256(b"worker artifact").hexdigest()
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
    "sha256": digest
  }],
  "evidence": [{"evidence_id": "ev", "kind": "worker", "summary": "done"}],
  "hashes": [{"hash_id": "discovery-result", "algorithm": "sha256", "value": digest}],
  "model_provider_usage": [{"provider": "none", "model": "none", "usage_kind": "none"}],
  "errors": [],
  "limitations": [],
  "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"}
}
print(json.dumps(result))
""",
        encoding="utf-8",
    )
    request = dispatch_request(tmp_path)
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


def test_generic_exception_and_nested_receipt_secrets_are_scrubbed(tmp_path: Path) -> None:
    request = dispatch_request(tmp_path)
    request_body = request["typed_inputs"]["payload"]["query"]
    canary = "canary-explicit-credential-12345"

    def failing_runner(_: dict) -> dict:
        raise RuntimeError(
            f"api_key={canary} nested password=hunter-two "
            f"Bearer bearer-token-value-12345 request={request_body}"
        )

    failed = dispatch_research_node(
        request,
        runner=failing_runner,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
        secret_values=(canary,),
    )
    rendered = str(failed)
    assert canary not in rendered
    assert "hunter-two" not in rendered
    assert "bearer-token-value" not in rendered
    assert request_body not in rendered

    env_secret = "opaque-receipt-environment-secret"

    class OpaqueReceiptValue:
        def __repr__(self) -> str:
            return f"OpaqueReceiptValue({env_secret})"

    receipt_runner = operator_runtime_submit_adapter(
        submit=lambda _: {
            "status": "submitted",
            "nested": {"api_key": canary, "request_body": {"prompt": "private body"}},
            "echoed_query": request_body,
            "large": "x" * 50_000,
            "opaque": {"layer": [{"value": OpaqueReceiptValue()}]},
            "near_boundary": "risk-research-summary",
            "deep": {"a": {"b": {"c": {"d": {"request_body": request_body}}}}},
            **{f"padding_{index}": f"ordinary_{index}" for index in range(30)},
            "request_body": {"prompt": request_body},
        },
        secret_values=(canary,),
        env={"RESEARCH_PROVIDER_TOKEN": env_secret},
        env_allowlist={"RESEARCH_PROVIDER_TOKEN"},
    )
    receipt = dispatch_research_node(
        request,
        runner=receipt_runner,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
        secret_values=(canary,),
    )
    receipt_text = str(receipt["evidence"][0]["receipt"])
    assert canary not in receipt_text
    assert "private body" not in receipt_text
    assert request_body not in receipt_text
    assert env_secret not in receipt_text
    assert "risk-research-summary" not in receipt_text
    assert len(receipt_text.encode("utf-8")) < 8_500
    assert receipt["status"] == "awaiting_external"
    assert receipt["evidence"][0]["receipt"] == {"status": "submitted"}

    strict_receipt = dispatch_research_node(
        request,
        runner=operator_runtime_submit_adapter(
            submit=lambda _: {
                "status": "submitted",
                "opaque": {"unlisted_private_value": "short-secret"},
            }
        ),
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert strict_receipt["evidence"][0]["receipt"] == {"status": "submitted"}


def test_malformed_secret_bearing_result_fails_closed_without_leak(tmp_path: Path) -> None:
    canary = "malformed-result-canary-123456789"
    malformed = valid_result()
    malformed["errors"] = [
        {
            "error_id": "forged-success",
            "error_type": "provider_error",
            "message": f"api_key={canary}",
        }
    ]
    with pytest.raises(ResearchResultValidationError) as excinfo:
        dispatch_research_node(
            dispatch_request(tmp_path),
            runner=lambda _: malformed,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
            secret_values=(canary,),
        )
    assert canary not in str(excinfo.value)


def test_completed_result_omits_private_request_body_without_mutating_worker_result(
    tmp_path: Path,
) -> None:
    request = dispatch_request(tmp_path)
    request_body = request["typed_inputs"]["payload"]["query"]
    completed = valid_result()
    completed["evidence"][0]["summary"] = f"completed for {request_body}"
    completed["evidence"][0]["payload"] = {"query": request_body}
    materialize_result_artifacts(tmp_path, completed)
    original = copy.deepcopy(completed)

    accepted = dispatch_research_node(
        request,
        runner=lambda _: completed,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert request_body not in str(accepted["evidence"])
    assert "[OMITTED_REQUEST_BODY]" in str(accepted["evidence"])
    assert completed == original

    short_request = dispatch_request(tmp_path)
    short_request["typed_inputs"]["payload"]["query"] = "xy"
    short_result = valid_result()
    short_result["evidence"][0]["summary"] = "private=xy"
    materialize_result_artifacts(tmp_path, short_result, content=b"short request result")
    short_accepted = dispatch_research_node(
        short_request,
        runner=lambda _: short_result,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )
    assert "xy" not in str(short_accepted["evidence"])


def test_request_echo_sanitization_preserves_evidence_artifact_linkage_and_ids(
    tmp_path: Path,
) -> None:
    request = dispatch_request(tmp_path)
    private_query = "private-seed-query"
    request["typed_inputs"]["payload"] = {
        "query": private_query,
        "node_label": request["node_id"],
        "artifact_hint": "discovery-result",
    }
    completed = valid_result()
    evidence_id = f"{request['node_id']}.snapshot"
    completed["evidence"][0].update(
        {
            "evidence_id": evidence_id,
            "artifact_id": completed["output_artifacts"][0]["artifact_id"],
            "summary": f"completed for {private_query}",
        }
    )
    materialize_result_artifacts(tmp_path, completed)

    accepted = dispatch_research_node(
        request,
        runner=lambda _: completed,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
    )

    evidence = accepted["evidence"][0]
    assert evidence["evidence_id"] == evidence_id
    assert evidence["artifact_id"] == accepted["output_artifacts"][0]["artifact_id"]
    assert evidence["artifact_id"] == "discovery-result"
    assert private_query not in evidence["summary"]
    assert "[OMITTED_REQUEST_BODY]" in evidence["summary"]


def test_redteam_combined_forged_completed_proof_is_rejected(tmp_path: Path) -> None:
    request = dispatch_request(tmp_path)
    request_body = request["typed_inputs"]["payload"]["query"]
    secret = "opaque-redteam-completed-secret"
    forged = valid_result()
    forged["evidence"][0].update(
        {
            "summary": f"completed for {request_body}",
            "payload": {"private_request": request_body},
            "opaque": {"provider_value": secret},
        }
    )
    materialize_result_artifacts(tmp_path, forged)

    with pytest.raises(ResearchResultValidationError, match="sensitive") as excinfo:
        _dispatch_research_node(
            request,
            runner=lambda _: forged,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
            operator_resolver=lambda operator_id: {
                "operator_id": operator_id,
                "enabled": True,
                "state": {"availability": "ready"},
            },
            secret_values=(secret,),
        )
    assert secret not in str(excinfo.value)


def test_physical_operator_resolver_rejects_unknown_disabled_and_wrong_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = dispatch_request(tmp_path)
    called = False

    def runner(_: dict) -> dict:
        nonlocal called
        called = True
        return valid_result()

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "spoofed-production")
    with pytest.raises(ResearchDispatchError, match="resolver is required"):
        _dispatch_research_node(
            request,
            runner=runner,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
        )

    with pytest.raises(TypeError, match="trusted_test_bypass"):
        _dispatch_research_node(
            request,
            runner=runner,
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
            trusted_test_bypass_operator_resolution=True,
        )

    for resolver in (
        lambda _: None,
        lambda operator_id: {"operator_id": operator_id, "enabled": False},
        lambda _: {"operator_id": "wrong", "enabled": True},
        lambda operator_id: {
            "operator_id": operator_id,
            "state": {"availability": "disabled"},
        },
        lambda operator_id: {
            "operator_id": operator_id,
            "runtime_state": {"status": "disabled"},
        },
        lambda operator_id: {"operator_id": operator_id, "status": "disabled"},
    ):
        with pytest.raises(ResearchDispatchError, match="operator"):
            dispatch_research_node(
                request,
                runner=runner,
                request_schema_path=REQUEST_SCHEMA,
                result_schema_path=RESULT_SCHEMA,
                artifact_root=tmp_path,
                operator_resolver=resolver,
            )
    assert called is False

    completed = valid_result()
    materialize_result_artifacts(tmp_path, completed)
    accepted = dispatch_research_node(
        request,
        runner=lambda _: completed,
        request_schema_path=REQUEST_SCHEMA,
        result_schema_path=RESULT_SCHEMA,
        artifact_root=tmp_path,
        operator_resolver=lambda operator_id: {"operator_id": operator_id, "enabled": True},
    )
    assert accepted["status"] == "completed"


def test_cyclic_typed_payload_fails_fast_before_dispatch(tmp_path: Path) -> None:
    request = valid_request()
    cyclic: dict = {}
    cyclic["self"] = cyclic
    request["typed_inputs"]["payload"] = cyclic
    started = time.monotonic()
    with pytest.raises(ResearchDispatchError, match="cyclic"):
        _dispatch_research_node(
            request,
            runner=lambda _: valid_result(),
            request_schema_path=REQUEST_SCHEMA,
            result_schema_path=RESULT_SCHEMA,
            artifact_root=tmp_path,
            operator_resolver=lambda operator_id: {
                "operator_id": operator_id,
                "enabled": True,
            },
        )
    assert time.monotonic() - started < 1.0
