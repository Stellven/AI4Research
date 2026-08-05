from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

HARNESS = Path(__file__).resolve().parents[4]
REPO = HARNESS.parent
PLUGIN = HARNESS / "plugins" / "autosci"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PLUGIN))

from harness.plugins.autosci.operators.research_synthesis.registry import execute_operator  # noqa: E402


NODE_RESULT_SCHEMA = json.loads((HARNESS / "schemas" / "evidence" / "research_node_result.v1.schema.json").read_text(encoding="utf-8"))


def _task_contract() -> dict:
    return {
        "schema": "research_task_contract.v1",
        "task_id": "task-research-synthesis",
        "run_id": "run-research-synthesis",
        "user_intent": "Synthesize supplied research evidence.",
        "seed_inputs": [{"seed_id": "topic-1", "seed_kind": "topic", "value": "agent evidence synthesis"}],
        "deliverable": {
            "kind": "briefing",
            "description": "A concise evidence-backed report.",
            "language": "en",
            "format": "markdown",
            "length": "short",
            "artifact_expectations": ["independent_review"],
        },
        "workflow_kind": "research_synthesis",
        "run_mode": "execute",
        "constraints": {"no_live_provider_without_approval": True, "no_secret_logging": True},
        "provider_requirements": [],
        "platform_requirements": [],
        "success_criteria": ["Every conclusion has evidence."],
    }


def _request(tmp_path: Path, node_id: str, *, payload: dict | None = None, refs: list[dict] | None = None) -> dict:
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-research-synthesis",
        "run_id": "run-research-synthesis",
        "workflow_id": "research_synthesis_v1",
        "node_id": node_id,
        "logical_operator": {"operator_id": f"logical-{node_id}", "operator_kind": "logical"},
        "physical_operator": {"operator_id": f"physical-{node_id}", "operator_kind": "physical"},
        "typed_inputs": {"input_schema": f"{node_id}.input.v1", "payload": payload or {}},
        "input_artifact_refs": refs or [],
        "authorization": {
            "scope_id": "test-scope",
            "approved_capabilities": ["write_artifact"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": ["TOP_SECRET_TOKEN"],
        },
        "read_scope": ["inputs", "out"],
        "write_scope": [f"out/{node_id}"],
        "timeout_retry_policy": {"timeout_seconds": 30, "max_attempts": 1, "retry_on": []},
    }


def _read_artifact(tmp_path: Path, result: dict) -> dict:
    ref = result["output_artifacts"][0]
    return json.loads((tmp_path / ref["path"]).read_text(encoding="utf-8"))


def _validate_result(result: dict) -> None:
    Draft202012Validator(NODE_RESULT_SCHEMA).validate(result)


def _fake_services() -> dict:
    def fetch_url(url: str, *, seed: dict) -> dict:
        return {
            "content": f"Fetched English and 中文 content from {url}.",
            "content_type": "text/html",
            "fetched_at": "2026-08-05T00:00:00Z",
            "limitations": [],
        }

    def discover_sources(*, seed_snapshot: dict, payload: dict) -> dict:
        return {
            "trace": "fake_discovery",
            "candidates": [
                {
                    "source_id": "source-alpha",
                    "title": "Alpha Evidence",
                    "url": "https://example.test/alpha",
                    "provider": "fixture",
                    "metadata": {"kind": "paper"},
                    "summary": "English content.",
                },
                {
                    "source_id": "source-beta",
                    "title": "Beta Evidence 中文",
                    "canonical_id": "doi:10.0000/beta",
                    "provider": "fixture",
                    "metadata": {"kind": "report"},
                    "summary": "中文内容.",
                },
            ],
            "provider_usage": [{"provider": "fake-search", "model": "none", "usage_kind": "provider_api"}],
        }

    def model_generate(**kwargs) -> dict:
        if kwargs["node_id"] == "evidence_synthesis":
            return {
                "provider": "writer-provider",
                "model": "writer-model",
                "claims": [
                    {
                        "claim_id": "claim-alpha",
                        "text": "Alpha evidence supports the synthesis.",
                        "evidence_ids": ["source-alpha"],
                        "uncertainty": "low",
                    },
                    {
                        "claim_id": "claim-beta",
                        "text": "中文证据 is preserved.",
                        "evidence_ids": ["source-beta"],
                        "uncertainty": "medium",
                    },
                ],
                "provider_usage": [{"provider": "writer-provider", "model": "writer-model", "usage_kind": "llm", "input_tokens": 10, "output_tokens": 20}],
            }
        return {
            "provider": "writer-provider",
            "model": "writer-model",
            "report": {
                "title": "Research synthesis draft",
                "body": "English report body with 中文内容.",
                "conclusions": [
                    {"conclusion_id": "conclusion-alpha", "text": "Alpha is supported.", "evidence_ids": ["claim-alpha"]},
                    {"conclusion_id": "conclusion-beta", "text": "Unicode is preserved.", "evidence_ids": ["claim-beta"]},
                ],
            },
            "provider_usage": [{"provider": "writer-provider", "model": "writer-model", "usage_kind": "llm", "input_tokens": 15, "output_tokens": 30}],
        }

    def review_model_generate(**kwargs) -> dict:
        return {
            "provider": "review-provider",
            "model": "review-model",
            "findings": [],
            "verdict_suggestion": "accept",
            "provider_usage": [{"provider": "review-provider", "model": "review-model", "usage_kind": "llm"}],
        }

    return {"fetch_url": fetch_url, "discover_sources": discover_sources, "model_generate": model_generate, "review_model_generate": review_model_generate}


def test_full_seven_node_chain_with_injected_services(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "inputs").mkdir()
    services = _fake_services()
    seed = execute_operator(
        _request(tmp_path, "seed_fetch", payload={"task_contract": _task_contract(), "seed_inputs": [{"seed_id": "url-1", "seed_kind": "url", "value": "https://example.test/seed"}]}),
        services=services,
    )
    discovery = execute_operator(_request(tmp_path, "source_discovery", refs=seed["output_artifacts"]), services=services)
    validation = execute_operator(_request(tmp_path, "source_validation", refs=discovery["output_artifacts"]), services=services)
    synthesis = execute_operator(_request(tmp_path, "evidence_synthesis", payload={"task_contract": _task_contract()}, refs=[*seed["output_artifacts"], *validation["output_artifacts"]]), services=services)
    draft = execute_operator(_request(tmp_path, "report_draft", payload={"task_contract": _task_contract()}, refs=synthesis["output_artifacts"]), services=services)
    review = execute_operator(_request(tmp_path, "independent_review", payload={"task_contract": _task_contract()}, refs=[*draft["output_artifacts"], *validation["output_artifacts"]]), services=services)
    final = execute_operator(_request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=review["output_artifacts"]), services=services)
    for result in (seed, discovery, validation, synthesis, draft, review, final):
        assert result["status"] == "completed"
        _validate_result(result)
    assert _read_artifact(tmp_path, final)["decision"] == "accepted"
    assert "中文" in json.dumps(_read_artifact(tmp_path, draft), ensure_ascii=False)


def test_seed_fetch_supports_topic_and_local_markdown_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    seed_file = inputs / "local_seed.md"
    seed_file.write_text("# Local Seed\nEnglish and 中文 content.\n", encoding="utf-8")
    payload = {
        "seed_inputs": [
            {"seed_id": "topic-1", "seed_kind": "topic", "value": "English topic"},
            {"seed_id": "md-1", "seed_kind": "markdown", "value": "inputs/local_seed.md"},
        ]
    }
    result = execute_operator(_request(tmp_path, "seed_fetch", payload=payload), services={})
    artifact = _read_artifact(tmp_path, result)
    assert result["status"] == "completed"
    assert artifact["seed_count"] == 2
    assert "中文 content" in artifact["seeds"][1]["content"]


def test_seed_path_traversal_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "inputs").mkdir()
    result = execute_operator(
        _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "bad", "seed_kind": "markdown", "value": "../outside.md"}]}),
        services={},
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "scope_violation"


def test_write_scope_escape_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    request = _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "topic", "seed_kind": "topic", "value": "x"}]})
    request["write_scope"] = ["out/seed_fetch/child.json"]
    result = execute_operator(request, services={})
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "scope_violation"


def test_source_validation_deduplicates_and_records_rejection_reasons(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_id": "a", "title": "A", "url": "https://example.test/a", "provider": "fixture"},
        {"source_id": "a2", "title": "A duplicate", "url": "https://example.test/a/", "provider": "fixture"},
        {"source_id": "bad", "url": "https://example.test/bad"},
    ]
    result = execute_operator(_request(tmp_path, "source_validation", payload={"candidates": candidates}), services={})
    artifact = _read_artifact(tmp_path, result)
    assert artifact["accepted_count"] == 1
    assert artifact["rejected_count"] == 2
    assert any("duplicate_of:a" in reason for row in artifact["rejected"] for reason in row["reasons"])
    assert any("missing source title" in reason for row in artifact["rejected"] for reason in row["reasons"])


def test_missing_discovery_provider_returns_awaiting_external(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "inputs").mkdir()
    result = execute_operator(_request(tmp_path, "source_discovery", payload={}), services={})
    assert result["status"] == "awaiting_external"
    assert result["status_is_terminal"] is False


def test_missing_model_provider_returns_awaiting_external(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    validation = {"accepted": [{"source_id": "source-alpha", "title": "A"}]}
    result = execute_operator(_request(tmp_path, "evidence_synthesis", payload={"source_validation": validation}), services={})
    assert result["status"] == "awaiting_external"
    assert "model_generate" in result["limitations"][0]


def test_independent_review_records_same_model_limitation_and_unsupported_claim(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    report_draft = {
        "report": {"conclusions": [{"conclusion_id": "c1", "text": "Unsupported.", "evidence_ids": []}]},
        "writer_usage": [{"provider": "same", "model": "same", "usage_kind": "llm"}],
    }
    validation = {"accepted": [{"source_id": "source-alpha", "title": "A"}]}

    def review_model_generate(**kwargs) -> dict:
        return {"provider": "same", "model": "same", "findings": [], "verdict_suggestion": "revise"}

    result = execute_operator(
        _request(tmp_path, "independent_review", payload={"report_draft": report_draft, "source_validation": validation, "task_contract": _task_contract()}),
        services={"review_model_generate": review_model_generate},
    )
    artifact = _read_artifact(tmp_path, result)
    assert result["status"] == "completed"
    assert any(item["category"] == "unsupported_claim" for item in artifact["findings"])
    assert any("same provider/model" in item for item in artifact["limitations"])


def test_final_acceptance_pass_and_reject(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    passed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"independent_review": {"findings": [], "verdict_suggestion": "accept"}}),
        services={"model_generate": pytest.fail},
    )
    passed_decision = _read_artifact(tmp_path, passed)["decision"]
    rejected = execute_operator(
        _request(
            tmp_path,
            "final_acceptance",
            payload={
                "independent_review": {
                    "findings": [{"finding_id": "f1", "severity": "high", "category": "unsupported_claim", "message": "bad"}],
                    "verdict_suggestion": "revise",
                }
            },
        ),
        services={},
    )
    assert passed_decision == "accepted"
    assert _read_artifact(tmp_path, rejected)["decision"] == "rejected"


def test_wrong_node_identity_fails_schema_valid_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    request = _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "topic", "seed_kind": "topic", "value": "x"}]})
    request["node_id"] = "not_registered"
    result = execute_operator(request, services={})
    assert result["status"] == "failed"
    _validate_result(result)


def test_hash_matches_artifact_and_secret_is_redacted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_operator(
        _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "topic", "seed_kind": "topic", "value": "TOP_SECRET_TOKEN"}]}),
        services={},
    )
    artifact_ref = result["output_artifacts"][0]
    artifact_text = (tmp_path / artifact_ref["path"]).read_text(encoding="utf-8")
    assert artifact_ref["sha256"] == result["hashes"][0]["value"]
    assert "TOP_SECRET_TOKEN" not in artifact_text
    assert "TOP_SECRET_TOKEN" not in json.dumps(result)


def test_report_requirements_come_from_task_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    captured = {}

    def model_generate(**kwargs) -> dict:
        captured.update(kwargs["deliverable_requirements"])
        return {
            "provider": "writer",
            "model": "generic",
            "report": {
                "title": "Custom",
                "body": "Body",
                "conclusions": [{"conclusion_id": "c1", "text": "Traceable", "evidence_ids": ["claim-alpha"]}],
            },
        }

    task_contract = _task_contract()
    task_contract["deliverable"] = {"kind": "memo", "description": "Board memo", "language": "fr", "format": "html", "length": "900 words"}
    synthesis = {"claims": [{"claim_id": "claim-alpha", "text": "A", "evidence_ids": ["source-alpha"]}]}
    result = execute_operator(
        _request(tmp_path, "report_draft", payload={"task_contract": task_contract, "evidence_synthesis": synthesis}),
        services={"model_generate": model_generate},
    )
    assert result["status"] == "completed"
    assert captured == {"kind": "memo", "description": "Board memo", "language": "fr", "format": "html", "length": "900 words", "artifact_expectations": []}


def test_no_task_specific_constants_and_no_graph_state_access() -> None:
    package = HARNESS / "plugins" / "autosci" / "operators" / "research_synthesis"
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    forbidden = ["Tencent", "腾讯", "4-6 trends", "four to six trends", "real_data_research", "research_run_state", "graph_state"]
    assert not any(item in text for item in forbidden)
