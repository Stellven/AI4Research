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


REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_PAPER = Path("tests/plugins/autosci/fixtures/sample_paper.md")
SYNTHESIS_OPERATOR_BY_NODE = {
    "seed_fetch": "seed_fetch_operator",
    "source_discovery": "source_discovery_operator",
    "source_validation": "source_validation_operator",
    "evidence_synthesis": "evidence_synthesis_operator",
    "report_draft": "report_draft_operator",
    "independent_review": "independent_review_operator",
    "report_revision": "report_revision_operator",
    "final_acceptance": "final_acceptance_operator",
}
EXPECTED_STATUSES_WITHOUT_LIVE_MODEL = {
    "seed_fetch": "completed",
    "source_discovery": "completed",
    "source_validation": "completed",
    "evidence_synthesis": "awaiting_external",
    "report_draft": "awaiting_external",
    "independent_review": "awaiting_external",
    "report_revision": "failed",
    "final_acceptance": "failed",
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
        "schema": "research_task_contract.v1",
        "task_id": "task-all-synthesis-contract",
        "run_id": "run-all-synthesis-contract",
        "workflow_kind": "research_synthesis",
        "run_mode": "execute",
        "user_intent": (
            "Synthesize the AutoSci Adapter Fixture Paper about deterministic "
            "bridge actions and Solar Evidence ABI artifacts."
        ),
        "seed_inputs": [
            {
                "seed_id": "autosci-adapter-fixture-paper",
                "seed_kind": "markdown",
                "value": FIXTURE_PAPER.as_posix(),
            }
        ],
        "deliverable": {
            "kind": "briefing",
            "description": "A source-linked synthesis grounded in checked-in repository evidence.",
            "language": "en",
            "format": "markdown",
            "length": "short",
            "artifact_expectations": ["independent_review"],
            "required_content": [
                {"requirement_id": "method_evidence", "required": True},
                {"requirement_id": "result_claims", "required": True},
            ],
        },
        "success_criteria": [
            "Every conclusion has evidence.",
            "The report body is non empty.",
            "Independent review has accept verdict.",
        ],
        "constraints": {"no_secret_logging": True},
        "provider_requirements": [],
        "platform_requirements": [],
        "run_provenance": {"repo_head": "test", "captured_at": "2026-08-26T12:00:00Z"},
    }


def _copy_fixture_paper(tmp_path: Path) -> str:
    source = REPO_ROOT / FIXTURE_PAPER
    target = tmp_path / FIXTURE_PAPER
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target.read_text(encoding="utf-8")


def _source_candidate(fixture_text: str) -> dict[str, Any]:
    summary = " ".join(fixture_text.split())
    return {
        "source_id": "source-autosci-adapter-fixture-paper",
        "title": "AutoSci Adapter Fixture Paper",
        "canonical_id": "repo:tests/plugins/autosci/fixtures/sample_paper.md",
        "provider": "checked_in_repository_fixture",
        "url": FIXTURE_PAPER.as_posix(),
        "metadata": {"authority": "authoritative", "relevance_score": 1.0},
        "provenance": {
            "provider": "checked_in_repository_fixture",
            "acquisition_channel": "source_pack",
            "source_path": FIXTURE_PAPER.as_posix(),
        },
        "acquisition_channel": "source_pack",
        "content_summary": summary,
        "summary": summary,
    }


def _request(
    node_id: str,
    *,
    payload: dict[str, Any] | None = None,
    refs: list[dict[str, Any]] | None = None,
    live_model: bool = False,
) -> dict[str, Any]:
    operator_id = SYNTHESIS_OPERATOR_BY_NODE[node_id]
    approved_capabilities = ["write_artifact"]
    secret_refs: list[str] = []
    if live_model:
        approved_capabilities.append("research_model_generate")
        secret_refs.append("OPENROUTER_API_KEY")
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-all-synthesis-contract",
        "run_id": "run-all-synthesis-contract",
        "workflow_id": "research_synthesis_v1",
        "node_id": node_id,
        "logical_operator": {
            "operator_id": f"logical-{node_id}",
            "operator_kind": "logical",
            "capabilities": ["write_artifact"],
        },
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
        "authorization": {
            "scope_id": "all-synthesis-contract",
            "approved_capabilities": approved_capabilities,
            "allow_network": live_model,
            "allow_live_provider": live_model,
            "approval_ref": "user-message:2026-08-26:approve-all-tests" if live_model else "",
            "secret_refs": secret_refs,
        },
        "read_scope": ["tests/plugins/autosci/fixtures", "out"],
        "write_scope": [f"out/{node_id}"],
        "timeout_retry_policy": {"timeout_seconds": 30, "max_attempts": 1, "retry_on": []},
    }


def _run(
    tmp_path: Path,
    request: dict[str, Any],
    *,
    use_environment_services: bool = False,
) -> dict[str, Any]:
    resolver = default_production_resolver(
        services=None if use_environment_services else {},
        workspace_root=tmp_path,
    )
    operator_id = request["physical_operator"]["operator_id"]
    return run_physical_operator(
        request,
        operator_id=operator_id,
        runner=resolver.execute,
        envelope_path=tmp_path / "worker" / request["node_id"] / "node_envelope.json",
        attempt=1,
        lease_id=f"lease-{request['node_id']}",
        run_contract_ref={"run_contract_id": "all-synthesis-contract", "sha256": "c" * 64},
        clock=lambda: "2026-08-26T12:00:00Z",
    )


def _assert_valid_worker_receipt(tmp_path: Path, node_id: str, envelope: dict[str, Any]) -> None:
    saved = json.loads((tmp_path / "worker" / node_id / "node_envelope.json").read_text(encoding="utf-8"))
    assert saved == envelope
    assert envelope["schema_version"] == "solar.node_envelope.v1"
    assert envelope["artifact_role"] == "runtime_worker_receipt"
    assert envelope["operator_id"] == SYNTHESIS_OPERATOR_BY_NODE[node_id]
    assert envelope["task_id"] == "task-all-synthesis-contract"
    assert envelope["run_id"] == "run-all-synthesis-contract"
    assert envelope["workflow_id"] == "research_synthesis_v1"
    assert envelope["node"] == node_id
    assert envelope["self_reported"]["schema"] == "research_node_result.v1"
    assert isinstance(envelope["self_reported"]["evidence"], list)
    assert isinstance(envelope["self_reported"]["hashes"], list)
    assert envelope["self_reported"]["secret_redaction_assertion"]["no_secrets_observed"] is True


def _assert_artifacts_are_owned_and_hash_verified(tmp_path: Path, envelope: dict[str, Any]) -> None:
    for artifact in envelope["artifacts"]:
        path = tmp_path / artifact["path"]
        assert path.is_file()
        assert path.name not in FORBIDDEN_FILENAMES
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        if artifact["schema"] == "text/markdown":
            assert path.read_text(encoding="utf-8").strip()
            continue
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["schema"] == artifact["schema"]
        assert body["artifact_id"] == artifact["artifact_id"]
        assert body["task_id"] == envelope["task_id"]
        assert body["run_id"] == envelope["run_id"]
        assert body["workflow_id"] == envelope["workflow_id"]
        assert body["node_id"] == envelope["node"]


def test_all_research_synthesis_physical_operators_emit_result_and_worker_receipt(tmp_path: Path) -> None:
    fixture_text = _copy_fixture_paper(tmp_path)
    registered = {
        item["physical_operator_id"]
        for item in registration_entries()
        if item["operator_family"] == "research_synthesis"
    }
    assert registered == set(SYNTHESIS_OPERATOR_BY_NODE.values())

    refs_by_node: dict[str, list[dict[str, Any]]] = {}
    envelopes: dict[str, dict[str, Any]] = {}

    seed = _run(
        tmp_path,
        _request("seed_fetch", payload={"seed_inputs": _task_contract()["seed_inputs"]}),
    )
    refs_by_node["seed_fetch"] = seed["artifacts"]
    envelopes["seed_fetch"] = seed

    discovery = _run(
        tmp_path,
        _request(
            "source_discovery",
            payload={
                "acquisition_mode": "source_pack",
                "supplied_source_candidates": [_source_candidate(fixture_text)],
            },
            refs=refs_by_node["seed_fetch"],
        ),
    )
    refs_by_node["source_discovery"] = discovery["artifacts"]
    envelopes["source_discovery"] = discovery

    validation = _run(
        tmp_path,
        _request("source_validation", refs=refs_by_node["source_discovery"]),
    )
    refs_by_node["source_validation"] = validation["artifacts"]
    envelopes["source_validation"] = validation

    envelopes["evidence_synthesis"] = _run(
        tmp_path,
        _request(
            "evidence_synthesis",
            refs=[*refs_by_node["seed_fetch"], *refs_by_node["source_validation"]],
        ),
    )
    envelopes["report_draft"] = _run(tmp_path, _request("report_draft"))
    envelopes["independent_review"] = _run(tmp_path, _request("independent_review"))
    envelopes["report_revision"] = _run(tmp_path, _request("report_revision"))
    envelopes["final_acceptance"] = _run(tmp_path, _request("final_acceptance"))

    assert set(envelopes) == set(SYNTHESIS_OPERATOR_BY_NODE)
    for node_id, envelope in envelopes.items():
        _assert_valid_worker_receipt(tmp_path, node_id, envelope)
        _assert_artifacts_are_owned_and_hash_verified(tmp_path, envelope)
        assert envelope["status"] == EXPECTED_STATUSES_WITHOUT_LIVE_MODEL[node_id]

    assert envelopes["evidence_synthesis"]["error"]["type"] == "external_dependency_pending"
    assert envelopes["report_draft"]["error"]["type"] == "external_dependency_pending"
    assert envelopes["independent_review"]["error"]["type"] == "external_dependency_pending"
    assert envelopes["report_revision"]["error"]["type"] == "missing_input"
    assert envelopes["final_acceptance"]["error"]["type"] == "acceptance_gate_rejected"


@pytest.mark.live_provider
def test_model_backed_synthesis_chain_uses_authorized_low_cost_production_provider(tmp_path: Path) -> None:
    if os.environ.get("PHASE22_ENABLE_NETWORK_JOURNEYS") != "1":
        pytest.skip("live provider execution is not authorized")
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY is not loaded into the test process")
    assert os.environ.get("AUTOSCI_RESEARCH_LLM_PROVIDER") == "openrouter"
    assert os.environ.get("AUTOSCI_RESEARCH_LLM_MODEL") == "deepseek/deepseek-v3.2"

    fixture_text = _copy_fixture_paper(tmp_path)
    seed = _run(
        tmp_path,
        _request("seed_fetch", payload={"seed_inputs": _task_contract()["seed_inputs"]}),
    )
    discovery = _run(
        tmp_path,
        _request(
            "source_discovery",
            payload={
                "acquisition_mode": "source_pack",
                "supplied_source_candidates": [_source_candidate(fixture_text)],
            },
            refs=seed["artifacts"],
        ),
    )
    validation = _run(
        tmp_path,
        _request("source_validation", refs=discovery["artifacts"]),
    )

    synthesis = _run(
        tmp_path,
        _request(
            "evidence_synthesis",
            refs=[*seed["artifacts"], *validation["artifacts"]],
            live_model=True,
        ),
        use_environment_services=True,
    )
    assert synthesis["status"] == "completed", synthesis["error"]

    draft = _run(
        tmp_path,
        _request("report_draft", refs=synthesis["artifacts"], live_model=True),
        use_environment_services=True,
    )
    assert draft["status"] == "completed", draft["error"]

    review = _run(
        tmp_path,
        _request(
            "independent_review",
            refs=[*draft["artifacts"], *validation["artifacts"]],
            live_model=True,
        ),
        use_environment_services=True,
    )
    assert review["status"] == "completed", review["error"]

    revision = _run(
        tmp_path,
        _request(
            "report_revision",
            refs=[
                *draft["artifacts"],
                *review["artifacts"],
                *validation["artifacts"],
                *synthesis["artifacts"],
            ],
            live_model=True,
        ),
        use_environment_services=True,
    )
    assert revision["status"] == "completed", revision["error"]

    acceptance = _run(
        tmp_path,
        _request(
            "final_acceptance",
            refs=[
                *draft["artifacts"],
                *review["artifacts"],
                *validation["artifacts"],
                *synthesis["artifacts"],
                *revision["artifacts"],
            ],
        ),
    )
    assert acceptance["status"] == "completed", acceptance["error"]

    for node_id, envelope in {
        "evidence_synthesis": synthesis,
        "report_draft": draft,
        "independent_review": review,
        "report_revision": revision,
        "final_acceptance": acceptance,
    }.items():
        _assert_valid_worker_receipt(tmp_path, node_id, envelope)
        _assert_artifacts_are_owned_and_hash_verified(tmp_path, envelope)
