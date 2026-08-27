from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from harness.lib.physical_operator_worker import run_physical_operator
from harness.lib.research_orchestration.runtime import default_production_resolver
from harness.plugins.autosci.operators.research_synthesis.base import stable_json_sha256
from harness.plugins.autosci.operators.scientific_lifecycle.registry import registration_entries


OPERATOR_BY_NODE = {
    "source_discovery": "source_discovery_operator",
    "source_validation": "source_validation_operator",
    "evidence_synthesis": "evidence_synthesis_operator",
    "report_draft": "report_draft_operator",
    "experiment_design": "experiment_design_worker",
    "experiment_run": "experiment_run_worker",
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


def _task_contract() -> dict[str, Any]:
    return {
        "user_intent": "Compare authoritative evidence about global solar capacity additions.",
        "deliverable": {
            "kind": "briefing",
            "description": "A source-linked synthesis.",
            "language": "en",
            "format": "markdown",
            "length": "short",
            "artifact_expectations": ["report_markdown"],
        },
        "success_criteria": ["Every conclusion has evidence."],
        "run_provenance": {"repo_head": "test", "captured_at": "2026-08-26T12:00:00Z"},
    }


def _request(
    node_id: str,
    *,
    payload: dict[str, Any] | None = None,
    refs: list[dict[str, Any]] | None = None,
    write_scope: list[str] | None = None,
    capabilities: list[str] | None = None,
    approval_ref: str | None = None,
) -> dict[str, Any]:
    operator_id = OPERATOR_BY_NODE[node_id]
    approved = list(capabilities or ["write_artifact"])
    authorization: dict[str, Any] = {
        "scope_id": "direct-operator-contract",
        "approved_capabilities": approved,
        "allow_network": False,
        "allow_live_provider": False,
        "secret_refs": [],
    }
    if approval_ref:
        authorization["approval_ref"] = approval_ref
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-direct-operator",
        "run_id": "run-direct-operator",
        "workflow_id": "direct_operator_contract_v1",
        "node_id": node_id,
        "logical_operator": {
            "operator_id": f"logical-{node_id}",
            "operator_kind": "logical",
            "capabilities": ["write_artifact"],
        },
        "physical_operator": {
            "operator_id": operator_id,
            "operator_kind": "physical",
            "capabilities": ["bounded_worker", *approved],
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


def _source_candidate() -> dict[str, Any]:
    text = "Global solar capacity additions increased in 2024 according to authoritative energy statistics."
    return {
        "source_id": "source-solar-2024",
        "title": "Global solar capacity additions in 2024",
        "url": "https://example.test/solar-2024",
        "canonical_id": "fixture:solar-2024",
        "provider": "fixture-authoritative-source",
        "metadata": {"authority": "authoritative", "relevance_score": 1.0},
        "provenance": {"provider": "fixture", "acquisition_channel": "source_pack"},
        "acquisition_channel": "source_pack",
        "content_summary": text,
        "summary": text,
    }


def _validated_source() -> dict[str, Any]:
    source = _source_candidate()
    return {
        **source,
        "validation": {
            "status": "accepted",
            "authority": {"class": "authoritative", "score": 1.0, "proof": ["fixture"]},
            "relevance": {"class": "high", "score": 1.0, "proof": ["fixture"]},
        },
        "candidate_sha256": stable_json_sha256(source),
    }


def _model_generate(**kwargs) -> dict[str, Any]:
    if kwargs["node_id"] == "evidence_synthesis":
        source_text = _source_candidate()["content_summary"]
        return {
            "provider": "fixture-provider",
            "model": "fixture-model",
            "claims": [{
                "claim_id": "claim-solar-2024",
                "text": source_text,
                "evidence_ids": ["source-solar-2024"],
                "evidence_quotes": [{"source_id": "source-solar-2024", "quote": source_text}],
                "uncertainty": "low",
            }],
            "provider_usage": [{"provider": "fixture-provider", "model": "fixture-model", "usage_kind": "llm"}],
        }
    return {
        "provider": "fixture-provider",
        "model": "fixture-model",
        "report": {
            "title": "Global solar capacity evidence",
            "body": "# Global solar capacity evidence\n\nThe retained claim is source-linked.",
            "conclusions": [{
                "conclusion_id": "conclusion-solar-2024",
                "text": "The retained 2024 solar-capacity claim is supported.",
                "evidence_ids": ["claim-solar-2024"],
            }],
        },
        "provider_usage": [{"provider": "fixture-provider", "model": "fixture-model", "usage_kind": "llm"}],
    }


def _experiment_idea() -> dict[str, Any]:
    return {
        "idea_id": "idea-rag-benchmark",
        "hypothesis": "Embedding retrieval improves factual accuracy over no retrieval.",
        "minimum_experiment": "Compare three retrieval conditions on one bounded fixture benchmark.",
        "origin_evidence_ids": ["fixture:rag-benchmark"],
    }


def _experiment_plan() -> dict[str, Any]:
    return {
        "experiment_id": "exp-rag-benchmark",
        "objective": "Compare three retrieval conditions.",
        "hypothesis": "Embedding retrieval improves factual accuracy over no retrieval.",
        "variables": ["retrieval_condition", "accuracy"],
        "metrics": ["accuracy", "citation_validity", "latency", "cost"],
        "procedure": ["Run the fixed fixture benchmark once per condition."],
        "approval_required": True,
        "expected_artifacts": ["experiment_result.v1.json"],
        "success_criteria": ["all four metrics are recorded"],
        "safety_checks": ["no network", "bounded writes"],
        "sandbox": {"mode": "isolated", "network": False, "write_scope": ["out/experiment_run"]},
        "resource_limits": {"timeout_seconds": 30, "max_output_bytes": 10000},
        "source_idea_id": "idea-rag-benchmark",
        "origin_evidence_ids": ["fixture:rag-benchmark"],
    }


def _write_evidence_ref(
    tmp_path: Path,
    name: str,
    schema: str,
    outputs: dict[str, Any],
    *,
    node_id: str,
) -> dict[str, Any]:
    path = tmp_path / "inputs" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": schema,
        "task_id": "task-direct-operator",
        "sprint_id": "run-direct-operator",
        "node_id": node_id,
        "status": "completed",
        "inputs": {},
        "outputs": outputs,
        "artifacts": [],
        "provenance": {"operator_id": "fixture-upstream", "timestamp": "2026-08-26T12:00:00Z"},
        "limitations": [],
    }
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    return {
        "artifact_id": name,
        "path": path.relative_to(tmp_path).as_posix(),
        "schema": schema,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _experiment_refs(tmp_path: Path) -> list[dict[str, Any]]:
    plan = _experiment_plan()
    approval = {
        "experiment_id": plan["experiment_id"],
        "decision": "approved",
        "approval_ref": "approval-direct-operator",
        "plan_sha256": stable_json_sha256(plan),
        "approved_capabilities": ["execute_experiment", "write_artifact"],
        "sandbox": plan["sandbox"],
        "reasons": [],
    }
    return [
        _write_evidence_ref(tmp_path, "experiment_plan", "experiment_plan.v1", {"experiment_plan": plan}, node_id="experiment_design"),
        _write_evidence_ref(tmp_path, "experiment_approval", "experiment_approval.v1", {"approval": approval}, node_id="experiment_approval_gate"),
    ]


def _experiment_executor(**kwargs) -> dict[str, Any]:
    assert kwargs["sandbox"] == _experiment_plan()["sandbox"]
    return {
        "outcome": "supports",
        "metrics": [
            {"name": "accuracy", "value": 0.8},
            {"name": "citation_validity", "value": 1.0},
            {"name": "latency_ms", "value": 25},
            {"name": "cost_usd", "value": 0.0},
        ],
        "evidence_ids": ["fixture:rag-result"],
        "criteria_results": {"all four metrics are recorded": True},
    }


def _valid_case(tmp_path: Path, node_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if node_id == "source_discovery":
        return _request(node_id, payload={
            "acquisition_mode": "source_pack",
            "supplied_source_candidates": [_source_candidate()],
        }), {}
    if node_id == "source_validation":
        return _request(node_id, payload={"candidates": [_source_candidate()]}), {}
    if node_id == "evidence_synthesis":
        return _request(node_id, payload={
            "source_validation": {
                "schema": "research_synthesis.source_validation.v1",
                "accepted": [_validated_source()],
                "limitations": [],
            },
            "seed_snapshot": {"schema": "research_synthesis.seed_snapshot.v1", "seeds": []},
        }), {"model_generate": _model_generate}
    if node_id == "report_draft":
        return _request(node_id, payload={
            "evidence_synthesis": {
                "schema": "research_synthesis.evidence_synthesis.v1",
                "claims": [{
                    "claim_id": "claim-solar-2024",
                    "text": _source_candidate()["content_summary"],
                    "evidence_ids": ["source-solar-2024"],
                }],
                "input_lineage": {"source_validation": "source_validation"},
                "limitations": [],
            },
        }), {"model_generate": _model_generate}
    if node_id == "experiment_design":
        return _request(node_id, payload={"idea_candidate": {"ideas": [_experiment_idea()]}}), {}
    if node_id == "experiment_run":
        return _request(
            node_id,
            refs=_experiment_refs(tmp_path),
            write_scope=["out/experiment_run"],
            capabilities=["write_artifact", "execute_experiment"],
            approval_ref="approval-direct-operator",
        ), {"experiment_executor": _experiment_executor}
    raise AssertionError(node_id)


def _run(tmp_path: Path, request: dict[str, Any], services: dict[str, Any]) -> dict[str, Any]:
    resolver = default_production_resolver(services=services, workspace_root=tmp_path)
    return run_physical_operator(
        request,
        operator_id=request["physical_operator"]["operator_id"],
        runner=resolver.execute,
        envelope_path=tmp_path / "worker" / request["node_id"] / "node_envelope.json",
        attempt=1,
        lease_id=f"lease-{request['node_id']}",
        run_contract_ref={"run_contract_id": "direct-operator-contract", "sha256": "b" * 64},
        clock=lambda: "2026-08-26T12:00:00Z",
    )


def test_unified_production_registry_contains_33_unique_fail_closed_bindings(tmp_path: Path) -> None:
    entries = registration_entries()
    resolver = default_production_resolver(services={}, workspace_root=tmp_path)

    assert len(entries) == 33
    assert len({item["physical_operator_id"] for item in entries}) == 33
    assert set(resolver.operator_ids()) == {item["physical_operator_id"] for item in entries}


@pytest.mark.parametrize("node_id", tuple(OPERATOR_BY_NODE))
def test_priority_operator_valid_input_produces_owned_hash_verified_artifacts(tmp_path: Path, node_id: str) -> None:
    request, services = _valid_case(tmp_path, node_id)
    envelope = _run(tmp_path, request, services)

    assert envelope["status"] == "completed", envelope["error"]
    assert envelope["error"] is None
    assert envelope["operator_id"] == OPERATOR_BY_NODE[node_id]
    assert envelope["artifacts"]
    for artifact in envelope["artifacts"]:
        path = tmp_path / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        assert path.name not in FORBIDDEN_FILENAMES
        if artifact["schema"].endswith(".v1") and artifact["schema"] != "text/markdown":
            body = json.loads(path.read_text(encoding="utf-8"))
            assert body["schema"] == artifact["schema"]
            assert body.get("node_id") == node_id


@pytest.mark.parametrize("node_id", tuple(OPERATOR_BY_NODE))
def test_priority_operator_missing_required_input_returns_typed_non_success(tmp_path: Path, node_id: str) -> None:
    services: dict[str, Any] = {}
    if node_id in {"evidence_synthesis", "report_draft"}:
        services["model_generate"] = _model_generate
    request = _request(node_id)
    if node_id == "experiment_run":
        request = _request(
            node_id,
            write_scope=["out/experiment_run"],
            capabilities=["write_artifact", "execute_experiment"],
            approval_ref="approval-direct-operator",
        )
        services["experiment_executor"] = _experiment_executor

    envelope = _run(tmp_path, request, services)

    assert envelope["status"] != "completed"
    assert envelope["error"]
    assert envelope["error"]["type"]


@pytest.mark.parametrize(
    "node_id",
    tuple(OPERATOR_BY_NODE),
)
def test_priority_operator_permanent_or_unsupported_request_fails_closed(tmp_path: Path, node_id: str) -> None:
    if node_id == "source_discovery":
        request, services = _request(node_id, payload={"acquisition_mode": "unsupported"}), {}
    elif node_id == "source_validation":
        request, services = _request(node_id, payload={"candidates": [{"title": "unattributed"}]}), {}
    elif node_id == "evidence_synthesis":
        request, services = _valid_case(tmp_path, node_id)
        services = {"model_generate": lambda **_kwargs: {"claims": []}}
    elif node_id == "report_draft":
        request, services = _valid_case(tmp_path, node_id)
        services = {"model_generate": lambda **_kwargs: {"report": {"body": "", "conclusions": []}}}
    elif node_id == "experiment_design":
        request = _request(node_id, payload={
            "idea_candidate": {"ideas": [_experiment_idea()]},
            "sandbox": {"mode": "isolated", "network": True, "write_scope": ["out/experiment_design"]},
        })
        services = {}
    else:
        request, services = _valid_case(tmp_path, node_id)
        services = {"experiment_executor": lambda **_kwargs: {
            "outcome": "unsupported",
            "metrics": [{"name": "accuracy", "value": 0.8}],
            "evidence_ids": ["fixture:bad"],
        }}

    envelope = _run(tmp_path, request, services)

    assert envelope["status"] in {"failed", "blocked"}
    assert envelope["error"]
    assert envelope["error"]["retryable"] is False


@pytest.mark.parametrize("node_id", ("source_discovery", "evidence_synthesis", "report_draft", "experiment_run"))
def test_provider_backed_operator_rejects_malformed_provider_response(tmp_path: Path, node_id: str) -> None:
    request, _services = _valid_case(tmp_path, node_id)
    if node_id == "source_discovery":
        request = _request(node_id, payload={"acquisition_mode": "live_search", "minimum_live_sources": 1})
        services = {"discover_sources": lambda **_kwargs: []}
    elif node_id in {"evidence_synthesis", "report_draft"}:
        services = {"model_generate": lambda **_kwargs: []}
    else:
        services = {"experiment_executor": lambda **_kwargs: []}

    envelope = _run(tmp_path, request, services)

    assert envelope["status"] in {"failed", "blocked"}
    assert envelope["error"]["type"] in {
        "provider_contract",
        "provider_contract_failure",
        "product_failure",
    }


@pytest.mark.parametrize("node_id", ("experiment_design", "experiment_run"))
def test_deterministic_action_operator_replay_is_byte_identical(tmp_path: Path, node_id: str) -> None:
    request, services = _valid_case(tmp_path, node_id)
    first = _run(tmp_path, request, services)
    first_bytes = {item["path"]: (tmp_path / item["path"]).read_bytes() for item in first["artifacts"]}
    second = _run(tmp_path, request, services)
    second_bytes = {item["path"]: (tmp_path / item["path"]).read_bytes() for item in second["artifacts"]}

    assert first_bytes == second_bytes
    assert first["self_reported"]["hashes"] == second["self_reported"]["hashes"]
