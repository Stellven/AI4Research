from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

HARNESS = (Path(__file__).resolve().parents[4] / 'harness')
REPO = HARNESS.parent
PLUGIN = HARNESS / "plugins" / "autosci"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(PLUGIN))

from harness.plugins.autosci.operators.research_synthesis.base import (  # noqa: E402
    OperatorContext,
    ResearchOperatorError,
    write_artifact,
)
from harness.plugins.autosci.operators.research_synthesis.evidence_synthesis import assess_claim_grounding  # noqa: E402
from harness.plugins.autosci.operators.research_synthesis.registry import execute_operator  # noqa: E402


NODE_RESULT_SCHEMA = json.loads((HARNESS / "schemas" / "evidence" / "research_node_result.v1.schema.json").read_text(encoding="utf-8"))
WORKFLOW = json.loads((HARNESS / "workflows" / "drafts" / "research_synthesis_v1.json").read_text(encoding="utf-8"))
BASELINE_ARTIFACTS_FOR_TEST = ("independent_review", "report_draft", "evidence_synthesis", "source_validation")


def test_chinese_evidence_claim_survives_grounding_when_source_supports_it() -> None:
    quote = "高精度数字孪生能够把城市、工业与自然系统映射到虚拟空间"
    claims = [
        {
            "claim_id": "claim-cjk",
            "text": "镜像世界通过数字孪生映射城市与工业系统，使现实世界可被预测和优化。",
            "evidence_ids": ["source-cjk"],
            "evidence_quotes": [{"source_id": "source-cjk", "quote": quote}],
        }
    ]

    kept, rejected = assess_claim_grounding(
        claims,
        {"source-cjk": quote + "，让现实世界可被预测和优化。"},
    )

    assert [item["claim_id"] for item in kept] == ["claim-cjk"]
    assert rejected == []


def _test_fs_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


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


def test_write_artifact_supports_long_windows_workspace_paths(tmp_path: Path) -> None:
    long_root = (
        tmp_path
        / ("phase5-generalization-integration-" + "x" * 80)
        / ("research-synthesis-artifacts-" + "y" * 80)
        / ("content-diversity-run-" + "z" * 60)
    )
    request = _request(long_root, "source_discovery")
    request["write_scope"] = ["artifacts/research_synthesis_v1/discovery/"]
    context = OperatorContext.from_request(request, workspace_root=long_root)

    artifact, hash_record = write_artifact(
        context,
        "artifacts/research_synthesis_v1/discovery/source_discovery.json",
        {"schema": "research_synthesis.source_discovery.v1", "candidates": []},
        artifact_id="source_discovery",
        schema="research_synthesis.source_discovery.v1",
    )

    target = long_root / artifact["path"]
    assert len(str(target)) > 260
    assert os.path.isfile(_test_fs_path(target))
    with open(_test_fs_path(target), "rb") as handle:
        body = handle.read()
    assert artifact["sha256"] == hashlib.sha256(body).hexdigest()
    assert hash_record["value"] == artifact["sha256"]


def _request(
    tmp_path: Path,
    node_id: str,
    *,
    payload: dict | None = None,
    refs: list[dict] | None = None,
    secret_refs: list[str] | None = None,
) -> dict:
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
            "secret_refs": list(secret_refs or []),
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


def _accepted_review() -> dict:
    return {
        "schema": "research_synthesis.independent_review.v1",
        "node_id": "independent_review",
        "findings": [],
        "verdict_suggestion": "accept",
        "evidence_lineage": ["independent_review", "report_draft", "evidence_synthesis", "source_validation"],
        "chain_validation": {
            "complete": True,
            "report_draft_present": True,
            "evidence_synthesis_present": True,
            "source_validation_present": True,
            "report_body_present": True,
            "conclusion_count": 1,
            "cited_claim_count": 1,
            "cited_source_count": 1,
        },
    }


def _valid_acceptance_refs(
    tmp_path: Path,
    *,
    report_body: str = "Grounded report body.",
    verdict: str = "accept",
    findings: list[dict] | None = None,
    source_count: int = 2,
    cited_source_count: int = 1,
    report_limitations: list[str] | None = None,
    source_urls: bool = False,
) -> list[dict]:
    sources = [f"source-{index}" for index in range(1, source_count + 1)]
    primary_source = sources[0] if sources else "missing-source"
    claim_sources = sources[:cited_source_count] or [primary_source]
    refs: list[dict] = []

    def write_ref(node_id: str, payload: dict) -> dict:
        payload.update({
            "artifact_id": node_id,
            "task_id": "task-research-synthesis",
            "run_id": "run-research-synthesis",
            "workflow_id": "research_synthesis_v1",
        })
        path = tmp_path / "out" / "acceptance-inputs" / f"{node_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        ref = {
            "artifact_id": node_id,
            "path": str(path.relative_to(tmp_path)).replace("\\", "/"),
            "schema": payload["schema"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        refs.append(ref)
        return ref

    validation_ref = write_ref("source_validation", {
        "schema": "research_synthesis.source_validation.v1",
        "node_id": "source_validation",
        "accepted": [
            {
                "source_id": source_id,
                "title": source_id,
                **({"url": f"https://example.test/{source_id}"} if source_urls else {}),
            }
            for source_id in sources
        ],
    })
    synthesis_ref = write_ref("evidence_synthesis", {
        "schema": "research_synthesis.evidence_synthesis.v1",
        "node_id": "evidence_synthesis",
        "input_lineage": {"seed_snapshot": "seed_snapshot", "source_validation": "source_validation"},
        "input_artifact_hashes": {"seed_snapshot": "seed-hash-not-required-by-final", "source_validation": validation_ref["sha256"]},
        "claims": [{"claim_id": "claim-1", "text": "Grounded", "evidence_ids": claim_sources}],
    })
    report_ref = write_ref("report_draft", {
        "schema": "research_synthesis.report_draft.v1",
        "node_id": "report_draft",
        "evidence_lineage": ["evidence_synthesis", "source_validation", "seed_snapshot"],
        "input_artifact_hashes": {"evidence_synthesis": synthesis_ref["sha256"]},
        "claim_source_lineage": {"claim-1": claim_sources},
        "limitations": list(report_limitations or []),
        "report": {
            "body": report_body,
            "conclusions": [{"conclusion_id": "conclusion-1", "text": "Grounded", "evidence_ids": ["claim-1"]}],
        },
    })
    write_ref("independent_review", {
        **_accepted_review(),
        "verdict_suggestion": verdict,
        "findings": list(findings or []),
        "reviewed_artifact_hashes": {
            "report_draft": report_ref["sha256"],
            "source_validation": validation_ref["sha256"],
        },
    })
    return refs


def test_final_acceptance_rejects_report_that_hides_cited_source_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    refs = _valid_acceptance_refs(tmp_path, source_urls=True, report_body="Grounded report body. Grounded")

    result = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=refs),
        services={},
    )
    decision = _read_artifact(tmp_path, result)

    assert result["status"] == "failed"
    assert decision["decision"] == "rejected"
    assert any("omits reader-visible URL" in reason for reason in decision["reasons"])


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
                    "summary": "Beta evidence preserves 中文内容.",
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
                        "text": "English content.",
                        "evidence_ids": ["source-alpha"],
                        "evidence_quotes": [
                            {"source_id": "source-alpha", "quote": "English content."}
                        ],
                        "uncertainty": "low",
                    },
                    {
                        "claim_id": "claim-beta",
                        "text": "Beta evidence preserves 中文内容.",
                        "evidence_ids": ["source-beta"],
                        "evidence_quotes": [
                            {"source_id": "source-beta", "quote": "Beta evidence preserves 中文内容."}
                        ],
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
                "body": (
                    "English report body with 中文内容.\n\n"
                    "## Sources\n\n"
                    "- [source-alpha — Alpha Evidence](https://example.test/alpha)"
                ),
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
    produced_by_declared_path: dict[str, dict] = {}
    results: dict[str, dict] = {}
    refs_used: dict[str, list[dict]] = {}
    for node in WORKFLOW["nodes"]:
        node_id = node["node_id"]
        for dependency in node["depends_on"]:
            assert results[dependency]["status"] == "completed"
        refs = [produced_by_declared_path[path] for path in node["input_artifacts"] if path in produced_by_declared_path]
        payload = {"task_contract": _task_contract()}
        if node_id == "seed_fetch":
            payload["seed_inputs"] = [{"seed_id": "url-1", "seed_kind": "url", "value": "https://example.test/seed"}]
        result = execute_operator(_request(tmp_path, node_id, payload=payload, refs=refs), services=services)
        results[node_id] = result
        refs_used[node_id] = refs
        assert len(node["output_artifacts"]) == len(result["output_artifacts"]), result
        for declared_path, actual_ref in zip(node["output_artifacts"], result["output_artifacts"], strict=True):
            produced_by_declared_path[declared_path] = actual_ref
    final_node = next(node for node in WORKFLOW["nodes"] if node["node_id"] == "final_acceptance")
    assert refs_used["final_acceptance"] == [produced_by_declared_path[path] for path in final_node["input_artifacts"]]
    assert len(refs_used["final_acceptance"]) == len(final_node["input_artifacts"])
    for result in results.values():
        assert result["status"] == "completed"
        _validate_result(result)
        for ref in result["output_artifacts"]:
            if ref.get("schema") == "text/markdown":
                assert (tmp_path / ref["path"]).read_text(encoding="utf-8").strip()
                continue
            artifact = json.loads((tmp_path / ref["path"]).read_text(encoding="utf-8"))
            assert {"schema", "artifact_id", "task_id", "run_id", "workflow_id", "node_id"} <= set(artifact)
            assert artifact["schema"] == ref["schema"]
            assert artifact["artifact_id"] == ref["artifact_id"]
            assert artifact["task_id"] == result["task_id"]
            assert artifact["run_id"] == result["run_id"]
            assert artifact["workflow_id"] == result["workflow_id"]
            assert artifact["node_id"] == result["node_id"]
    assert _read_artifact(tmp_path, results["final_acceptance"])["decision"] == "accepted"
    draft = results["report_draft"]
    assert "中文" in json.dumps(_read_artifact(tmp_path, draft), ensure_ascii=False)


def test_write_artifact_rejects_conflicting_embedded_artifact_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = OperatorContext.from_request(_request(tmp_path, "seed_fetch"), workspace_root=tmp_path)

    with pytest.raises(ResearchOperatorError) as error:
        write_artifact(
            context,
            "out/seed_fetch/conflict.json",
            {
                "schema": "research_synthesis.seed_snapshot.v1",
                "artifact_id": "caller-supplied-conflict",
                "node_id": "seed_fetch",
            },
            artifact_id="seed_snapshot",
            schema="research_synthesis.seed_snapshot.v1",
        )

    assert error.value.error_type == "artifact_identity_mismatch"
    assert not (tmp_path / "out" / "seed_fetch" / "conflict.json").exists()


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
    assert all(seed["source_contract"]["schema"] == "autosci_seed_source_contract.v1" for seed in artifact["seeds"])
    assert "中文 content" in artifact["seeds"][1]["content"]

def test_seed_fetch_uses_unified_contract_for_chinese_url_english_topic_and_local_pdf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fitz = pytest.importorskip("fitz")
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    pdf_path = inputs / "local-source.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Local PDF Source\nAbstract\nThis PDF contains provenance text.", fontsize=11)
    doc.save(pdf_path)
    doc.close()

    def fetch_url(url: str, *, seed: dict) -> dict:
        return {
            "requested_url": url,
            "final_url": url,
            "fetched_at": "2026-08-06T00:00:00Z",
            "content_type": "text/html; charset=utf-8",
            "content": "Chinese-language source content for provenance.",
            "title": "Chinese technical source",
            "provider": "bounded_http_fixture",
            "content_sha256": "c" * 64,
            "response_sha256": "d" * 64,
            "request_sha256": "e" * 64,
            "metadata_sha256": "f" * 64,
            "response_bytes": 64,
        }

    payload = {
        "seed_inputs": [
            {"seed_id": "url-zh", "seed_kind": "url", "value": "https://example.test/中文/报告"},
            {"seed_id": "topic-en", "seed_kind": "topic", "value": "retrieval augmented generation reliability"},
            {"seed_id": "pdf-local", "seed_kind": "pdf", "value": "inputs/local-source.pdf"},
        ]
    }
    result = execute_operator(_request(tmp_path, "seed_fetch", payload=payload), services={"fetch_url": fetch_url})
    artifact = _read_artifact(tmp_path, result)

    assert result["status"] == "completed"
    contracts = {seed["seed_id"]: seed["source_contract"] for seed in artifact["seeds"]}
    assert set(contracts) == {"url-zh", "topic-en", "pdf-local"}
    assert contracts["url-zh"]["seed_kind"] == "url"
    assert contracts["topic-en"]["seed_kind"] == "topic"
    assert contracts["pdf-local"]["seed_kind"] == "pdf"
    assert "provenance text" in next(seed for seed in artifact["seeds"] if seed["seed_id"] == "pdf-local")["content"]
    assert all(contract["content_sha256"] for contract in contracts.values())


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
    assert artifact["source_policy_summary"]["duplicate_rejections"] == 1

def test_source_validation_keeps_good_sources_when_one_candidate_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {
            "source_id": "good",
            "title": "Grounded Source",
            "url": "https://example.test/good",
            "provider": "semantic_scholar",
            "canonical_id": "doi:10.0000/good",
            "summary": "A substantive relevant source summary for validation.",
        },
        {
            "source_id": "failed",
            "title": "Failed Source",
            "url": "https://example.test/failed",
            "provider": "semantic_scholar",
            "status": "failed",
            "error": "provider timeout",
        },
    ]
    result = execute_operator(_request(tmp_path, "source_validation", payload={"candidates": candidates}), services={})
    artifact = _read_artifact(tmp_path, result)

    assert result["status"] == "completed"
    assert artifact["accepted_count"] == 1
    assert artifact["rejected_count"] == 1
    assert artifact["source_policy_summary"]["source_failure_rejections"] == 2
    assert any(reason.startswith("source_failure:") for reason in artifact["rejected"][0]["reasons"])


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
    accepted_refs = _valid_acceptance_refs(tmp_path)
    passed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=accepted_refs),
        services={"model_generate": pytest.fail},
    )
    passed_decision = _read_artifact(tmp_path, passed)["decision"]
    rejected_refs = _valid_acceptance_refs(
        tmp_path,
        verdict="revise",
        findings=[{"finding_id": "f1", "severity": "high", "category": "unsupported_claim", "message": "bad"}],
    )
    rejected = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=rejected_refs),
        services={},
    )
    assert passed_decision == "accepted"
    assert passed["status"] == "completed"
    assert _read_artifact(tmp_path, rejected)["decision"] == "rejected"
    assert rejected["status"] == "failed"
    assert rejected["errors"][0]["error_type"] == "acceptance_gate_rejected"


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
        _request(
            tmp_path,
            "seed_fetch",
            payload={"seed_inputs": [{"seed_id": "topic", "seed_kind": "topic", "value": "TOP_SECRET_TOKEN"}]},
            secret_refs=["TOP_SECRET_TOKEN"],
        ),
        services={"secret_values": {"TOP_SECRET_TOKEN": "opaque-runtime-secret"}},
    )
    artifact_ref = result["output_artifacts"][0]
    artifact_text = (tmp_path / artifact_ref["path"]).read_text(encoding="utf-8")
    assert artifact_ref["sha256"] == result["hashes"][0]["value"]
    # Secret refs are names, not secret values. Merely mentioning the reference
    # must not create a false redaction claim.
    assert "TOP_SECRET_TOKEN" in artifact_text
    assert result["secret_redaction_assertion"] == {"no_secrets_observed": True, "redaction_review": "passed"}
    _validate_result(result)


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


def test_report_draft_compiles_structured_sections_when_provider_omits_duplicate_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def model_generate(**kwargs) -> dict:
        return {
            "provider": "writer",
            "model": "sections-only-model",
            "limitations": ["The surveyed evidence is incomplete."],
            "report": {
                "title": "WebAssembly optimization survey",
                "sections": [
                    {"title": "Trade-offs", "body": "Tiered compilation balances startup latency against peak throughput."},
                    {"title": "Open problems", "body": "Portable profiling and adaptive optimization remain open research problems."},
                ],
                "conclusions": [{
                    "conclusion_id": "c1",
                    "text": "Tiered compilation has explicit performance trade-offs.",
                    "evidence_ids": ["claim-alpha"],
                }],
            },
        }

    synthesis = {"claims": [{"claim_id": "claim-alpha", "text": "A", "evidence_ids": ["source-alpha"]}]}
    result = execute_operator(
        _request(tmp_path, "report_draft", payload={"task_contract": _task_contract(), "evidence_synthesis": synthesis}),
        services={"model_generate": model_generate},
    )

    assert result["status"] == "completed"
    artifact = _read_artifact(tmp_path, result)
    body = artifact["report"]["body"]
    assert body.startswith("# WebAssembly optimization survey")
    assert "## Trade-offs" in body
    assert "startup latency against peak throughput" in body
    assert "## Open problems" in body
    assert "adaptive optimization remain open research problems" in body
    assert "## Conclusions" in body
    assert "Tiered compilation has explicit performance trade-offs." in body
    assert "## Limitations" in body
    assert "The surveyed evidence is incomplete." in body


def test_report_draft_deduplicates_sections_already_rendered_in_provider_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def model_generate(**kwargs) -> dict:
        return {
            "provider": "writer",
            "model": "body-and-sections-model",
            "report": {
                "title": "WebAssembly optimization survey",
                "body": (
                    "# WebAssembly optimization survey\n\n"
                    "## 1. Trade-offs\n\n"
                    "Tiered compilation balances startup latency against peak throughput."
                ),
                "sections": [
                    {"title": "Trade-offs", "body": "Tiered compilation balances startup latency against peak throughput."},
                    {"title": "Open problems", "body": "Portable profiling remains an open research problem."},
                ],
                "conclusions": [{
                    "conclusion_id": "c1",
                    "text": "Tiered compilation has explicit performance trade-offs.",
                    "evidence_ids": ["claim-alpha"],
                }],
            },
        }

    synthesis = {"claims": [{"claim_id": "claim-alpha", "text": "A", "evidence_ids": ["source-alpha"]}]}
    result = execute_operator(
        _request(tmp_path, "report_draft", payload={"task_contract": _task_contract(), "evidence_synthesis": synthesis}),
        services={"model_generate": model_generate},
    )

    body = _read_artifact(tmp_path, result)["report"]["body"]
    assert result["status"] == "completed"
    assert body.count("# WebAssembly optimization survey") == 1
    assert body.count("Tiered compilation balances startup latency against peak throughput.") == 1
    assert body.count("## 1. Trade-offs") == 1
    assert "## Open problems" in body
    assert "Portable profiling remains an open research problem." in body


def test_report_draft_localizes_compiled_conclusion_and_limitation_headings_for_chinese(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def model_generate(**kwargs) -> dict:
        return {
            "provider": "writer",
            "model": "sections-only-model",
            "limitations": ["长期预测具有高度不确定性。"],
            "report": {
                "title": "未来技术愿景分析",
                "sections": [{"title": "技术路线", "body": "该愿景覆盖人工智能、能源与生物医学。"}],
                "conclusions": [{
                    "conclusion_id": "c1",
                    "text": "远期技术预测必须结合证据边界解读。",
                    "evidence_ids": ["claim-alpha"],
                }],
            },
        }

    synthesis = {"claims": [{"claim_id": "claim-alpha", "text": "证据", "evidence_ids": ["source-alpha"]}]}
    result = execute_operator(
        _request(tmp_path, "report_draft", payload={"task_contract": _task_contract(), "evidence_synthesis": synthesis}),
        services={"model_generate": model_generate},
    )

    body = _read_artifact(tmp_path, result)["report"]["body"]
    assert result["status"] == "completed"
    assert "## 结论" in body
    assert "证据: claim-alpha" in body
    assert "## 局限" in body
    assert "长期预测具有高度不确定性" in body


def test_final_acceptance_requires_conclusions_to_be_rendered_in_report_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_operator(
        _request(
            tmp_path,
            "final_acceptance",
            payload={"task_contract": _task_contract()},
            refs=_valid_acceptance_refs(tmp_path, report_body="A substantive but unrelated report body."),
        ),
        services={},
    )

    decision = _read_artifact(tmp_path, result)
    assert result["status"] == "failed"
    assert any("not rendered in the report body" in reason for reason in decision["reasons"])


def test_final_acceptance_checks_explicit_result_and_limitation_requirements(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    contract = _task_contract()
    contract["deliverable"]["required_content"] = [
        {"requirement_id": "result_claims", "description": "Render conclusions.", "required": True},
        {"requirement_id": "limitations", "description": "Render limitations.", "required": True},
    ]
    passing_refs = _valid_acceptance_refs(
        tmp_path,
        report_body="Grounded report body.\n\n## Limitations\n\n- The evidence is bounded.",
        report_limitations=["The evidence is bounded."],
    )
    passed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=passing_refs),
        services={},
    )
    assert passed["status"] == "completed"
    assert all(
        item["status"] == "passed"
        for item in _read_artifact(tmp_path, passed)["required_content_evaluation"]
    )

    localized_refs = _valid_acceptance_refs(
        tmp_path,
        report_body="Grounded report body.\n\n## \u4e94\u3001\u8bc1\u636e\u8bc4\u4f30\u4e0e\u62a5\u544a\u5c40\u9650\n\n- \u672a\u83b7\u53d6\u539f\u59cb\u6570\u636e\uff0c\u957f\u671f\u9884\u6d4b\u4ecd\u6709\u4e0d\u786e\u5b9a\u6027\u3002",
    )
    localized = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=localized_refs),
        services={},
    )
    assert localized["status"] == "completed"
    assert all(
        item["status"] == "passed"
        for item in _read_artifact(tmp_path, localized)["required_content_evaluation"]
    )

    failing_refs = _valid_acceptance_refs(tmp_path, report_body="Grounded report body without a limitation section.")
    failed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=failing_refs),
        services={},
    )
    assert failed["status"] == "failed"
    assert any(
        item["requirement_id"] == "limitations" and item["status"] == "failed"
        for item in _read_artifact(tmp_path, failed)["required_content_evaluation"]
    )


def test_empty_review_and_empty_artifact_expectations_fail_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    contract = _task_contract()
    contract["deliverable"]["artifact_expectations"] = []
    result = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract, "independent_review": {}}),
        services={},
    )
    decision = _read_artifact(tmp_path, result)
    assert result["status"] == "failed"
    assert decision["decision"] == "rejected"
    assert set(decision["missing_required_artifacts"]) >= {"independent_review", "report_draft", "evidence_synthesis", "source_validation"}


@pytest.mark.parametrize("verdict", ["revise", "revise_required", "reject", ""])
def test_non_accepting_or_empty_review_verdict_is_rejected(tmp_path: Path, monkeypatch, verdict: str) -> None:
    monkeypatch.chdir(tmp_path)
    refs = _valid_acceptance_refs(tmp_path, verdict=verdict)
    result = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=refs),
        services={},
    )
    assert _read_artifact(tmp_path, result)["decision"] == "rejected"
    assert result["status"] == "failed"


def test_unsupported_task_success_criterion_is_explicitly_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    contract = _task_contract()
    contract["success_criteria"] = ["The prose should delight an expert reader."]
    result = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=_valid_acceptance_refs(tmp_path)),
        services={},
    )
    decision = _read_artifact(tmp_path, result)
    assert decision["decision"] == "rejected"
    assert decision["success_criteria_evaluation"][0]["status"] == "unsupported"


def test_poisoned_claim_source_lineage_forces_review_revision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    report_draft = {
        "schema": "research_synthesis.report_draft.v1",
        "report": {
            "body": "A report body.",
            "conclusions": [{"conclusion_id": "c1", "text": "Poisoned", "evidence_ids": ["claim-1"]}],
        },
        "claim_source_lineage": {"claim-1": ["unknown-source"]},
        "evidence_lineage": ["evidence_synthesis", "source_validation"],
        "writer_usage": [{"provider": "writer", "model": "writer", "usage_kind": "llm"}],
    }
    validation = {
        "schema": "research_synthesis.source_validation.v1",
        "accepted": [{"source_id": "validated-source", "title": "Validated"}],
    }

    def accepting_reviewer(**kwargs) -> dict:
        return {"provider": "reviewer", "model": "reviewer", "findings": [], "verdict_suggestion": "accept"}

    result = execute_operator(
        _request(
            tmp_path,
            "independent_review",
            payload={"task_contract": _task_contract(), "report_draft": report_draft, "source_validation": validation},
        ),
        services={"review_model_generate": accepting_reviewer},
    )
    artifact = _read_artifact(tmp_path, result)
    assert artifact["verdict_suggestion"] == "revise"
    assert artifact["chain_validation"]["complete"] is False
    assert any(item["category"] == "citation_truthfulness" and item["severity"] == "critical" for item in artifact["findings"])
    final = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=result["output_artifacts"]),
        services={},
    )
    assert _read_artifact(tmp_path, final)["decision"] == "rejected"


def test_zero_discovery_and_zero_validation_do_not_complete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    def empty_discovery(**kwargs) -> dict:
        return {"candidates": [], "trace": "empty-provider"}

    discovery = execute_operator(
        _request(tmp_path, "source_discovery", payload={"seed_snapshot": {"schema": "research_synthesis.seed_snapshot.v1"}}),
        services={"discover_sources": empty_discovery},
    )
    assert discovery["status"] == "blocked"
    validation = execute_operator(
        _request(tmp_path, "source_validation", payload={"candidates": [{"source_id": "bad"}]}),
        services={},
    )
    assert validation["status"] == "blocked"
    assert validation["output_artifacts"]


def test_hybrid_discovery_preserves_pack_fallback_without_claiming_live(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    pack = {
        "source_id": "pack-rag",
        "canonical_id": "pack:rag",
        "title": "Retrieval augmented generation evaluation evidence",
        "url": "https://example.test/pack-rag",
        "provider": "host_source_pack",
        "content_summary": "Retrieval evaluation compares grounded answer quality and citation support.",
        "provenance": {"provider": "host_source_pack"},
    }

    def unavailable(**_kwargs) -> dict:
        raise ResearchOperatorError("all public providers unavailable", error_type="provider_unavailable")

    discovery = execute_operator(
        _request(
            tmp_path,
            "source_discovery",
            payload={
                "seed_snapshot": {"schema": "research_synthesis.seed_snapshot.v1", "seeds": []},
                "task_contract": {"user_intent": "retrieval augmented generation evaluation"},
                "acquisition_mode": "hybrid",
                "minimum_live_sources": 3,
                "supplied_source_candidates": [pack],
            },
        ),
        services={"discover_sources": unavailable},
    )
    artifact = _read_artifact(tmp_path, discovery)

    assert discovery["status"] == "completed"
    assert artifact["acquisition_summary"]["source_pack_count"] == 1
    assert artifact["acquisition_summary"]["live_source_count"] == 0
    assert artifact["acquisition_summary"]["live_claim_allowed"] is False
    assert any("must not claim live coverage" in item for item in artifact["limitations"])


def test_live_relevance_accepts_topic_sources_and_rejects_obvious_off_topic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {
            "source_id": f"live-{index}",
            "canonical_id": f"doi:10.1000/live{index}",
            "title": title,
            "url": f"https://doi.org/10.1000/live{index}",
            "provider": "openalex",
            "acquisition_channel": "live_search",
            "content_summary": summary,
            "provenance": {"provider": "openalex", "acquisition_channel": "live_search"},
        }
        for index, (title, summary) in enumerate(
            [
                ("Retrieval augmented generation evaluation", "Evaluation methods for retrieval grounded generation."),
                ("RAG retrieval benchmarks", "Retrieval augmented generation benchmark evidence."),
                ("Evaluating grounded generation", "Generation evaluation with retrieval evidence."),
                ("Marine coral reef ecology", "A field survey of tropical fish habitats."),
            ],
            start=1,
        )
    ]
    discovery_payload = {
        "schema": "research_synthesis.source_discovery.v1",
        "artifact_id": "source_discovery",
        "task_id": "task-research-synthesis",
        "run_id": "run-research-synthesis",
        "workflow_id": "research_synthesis_v1",
        "node_id": "source_discovery",
        "query": "retrieval augmented generation evaluation",
        "acquisition_mode": "live_search",
        "acquisition_summary": {"minimum_live_sources": 3},
        "candidates": candidates,
        "limitations": [],
    }
    path = tmp_path / "out/source_discovery/source_discovery.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(discovery_payload), encoding="utf-8")
    ref = {
        "artifact_id": "source_discovery",
        "path": str(path.relative_to(tmp_path)),
        "schema": "research_synthesis.source_discovery.v1",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    result = execute_operator(_request(tmp_path, "source_validation", refs=[ref]), services={})
    artifact = _read_artifact(tmp_path, result)

    assert result["status"] == "completed"
    assert artifact["source_policy_summary"]["accepted_live_count"] == 3
    assert artifact["source_policy_summary"]["live_claim_allowed"] is True
    assert any(item["source_id"] == "live-4" and "relevance: no task-query token overlap" in item["reasons"] for item in artifact["rejected"])
    assert all((item["validation"]["relevance"].get("query_binding") or {}).get("query_sha256") for item in artifact["accepted"])


def test_external_evidence_requires_scoped_provenance_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence_path = inputs / "imported.json"
    evidence_path.write_text(json.dumps({"claim": "scoped evidence"}), encoding="utf-8")
    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    declared = {
        "artifact_id": "imported-evidence",
        "path": "inputs/imported.json",
        "sha256": digest,
        "provenance": {"source": "user-import", "captured_at": "2026-08-05T00:00:00Z"},
    }
    seed = {"seed_id": "external-1", "seed_kind": "external_evidence", "value": "must-not-be-used", "artifact_ref": declared}
    contract = _task_contract()
    contract["run_mode"] = "import_evidence"
    missing_ref = execute_operator(_request(tmp_path, "seed_fetch", payload={"task_contract": contract, "seed_inputs": [seed]}), services={})
    assert missing_ref["status"] == "failed"
    execute_mode = execute_operator(
        _request(
            tmp_path,
            "seed_fetch",
            payload={"task_contract": _task_contract(), "seed_inputs": [seed]},
            refs=[{"artifact_id": "imported-evidence", "path": "inputs/imported.json", "sha256": digest}],
        ),
        services={},
    )
    assert execute_mode["status"] == "failed"
    assert execute_mode["errors"][0]["error_type"] == "unverified_external_evidence"
    request = _request(
        tmp_path,
        "seed_fetch",
        payload={"task_contract": contract, "seed_inputs": [seed]},
        refs=[{"artifact_id": "imported-evidence", "path": "inputs/imported.json", "sha256": digest}],
    )
    imported = execute_operator(request, services={})
    artifact = _read_artifact(tmp_path, imported)
    assert imported["status"] == "completed"
    assert artifact["seeds"][0]["content"] == {"claim": "scoped evidence"}
    assert artifact["seeds"][0]["provenance"]["source"] == "user-import"


def test_invalid_pdf_is_blocked_without_raw_byte_decode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "bad.pdf").write_bytes(b"%PDF-1.4\xff\xfe\x00not-a-document")
    result = execute_operator(
        _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "pdf-1", "seed_kind": "pdf", "value": "inputs/bad.pdf"}]}),
        services={},
    )
    assert result["status"] == "blocked"
    assert result["errors"][0]["error_type"] == "pdf_extraction_unavailable"
    assert not result["output_artifacts"]


def test_nested_secret_canaries_are_sanitized_from_provider_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    opaque_secret = "semanticscholar-opaque-P7xQ2mN9vL4cT8w"
    report = {
        "schema": "research_synthesis.report_draft.v1",
        "report": {"body": "Body", "conclusions": [{"conclusion_id": "c1", "evidence_ids": ["claim-1"]}]},
        "claim_source_lineage": {"claim-1": ["source-1"]},
        "evidence_lineage": ["evidence_synthesis", "source_validation"],
    }
    validation = {"schema": "research_synthesis.source_validation.v1", "accepted": [{"source_id": "source-1"}]}

    def poisoned_reviewer(**kwargs) -> dict:
        return {
            "provider": "reviewer",
            "model": "reviewer",
            "verdict_suggestion": "revise",
            "findings": [{
                "finding_id": "poison",
                "severity": "medium",
                "category": "provider_note",
                "message": f"Provider trace contained {opaque_secret}",
                "nested": {"provider_value": opaque_secret},
            }],
        }

    result = execute_operator(
        _request(
            tmp_path,
            "independent_review",
            payload={"report_draft": report, "source_validation": validation},
            secret_refs=["SEMANTIC_SCHOLAR_API_KEY"],
        ),
        services={
            "review_model_generate": poisoned_reviewer,
            "secret_values": {"SEMANTIC_SCHOLAR_API_KEY": opaque_secret},
        },
    )
    serialized = json.dumps(_read_artifact(tmp_path, result)) + json.dumps(result)
    assert opaque_secret not in serialized
    assert "[REDACTED]" in serialized
    assert result["secret_redaction_assertion"] == {"no_secrets_observed": True, "redaction_review": "passed"}
    _validate_result(result)


def test_missing_secret_value_returns_static_schema_valid_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_operator(
        _request(
            tmp_path,
            "source_discovery",
            payload={},
            secret_refs=["SEMANTIC_SCHOLAR_API_KEY"],
        ),
        services={"discover_sources": pytest.fail},
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "secret_verification_unavailable"
    assert result["secret_redaction_assertion"] == {"no_secrets_observed": True, "redaction_review": "passed"}
    assert result["output_artifacts"] == []
    serialized = json.dumps(result)
    assert "SEMANTIC_SCHOLAR_API_KEY" not in serialized
    assert "provider output was not reviewed" in serialized
    _validate_result(result)


def test_empty_secret_refs_produce_schema_valid_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_operator(
        _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "topic", "seed_kind": "topic", "value": "research"}]}),
        services={},
    )
    assert result["status"] == "completed"
    assert result["secret_redaction_assertion"] == {"no_secrets_observed": True, "redaction_review": "passed"}
    _validate_result(result)


def test_generic_input_refs_use_embedded_schema_and_hash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "inputs").mkdir()
    services = _fake_services()

    def generic_refs(result: dict) -> list[dict]:
        return [
            {"artifact_id": f"generic:input:{index}", "path": ref["path"], "sha256": ref["sha256"]}
            for index, ref in enumerate(result["output_artifacts"])
        ]

    seed = execute_operator(_request(tmp_path, "seed_fetch", payload={"task_contract": _task_contract(), "seed_inputs": [{"seed_id": "url", "seed_kind": "url", "value": "https://example.test"}]}), services=services)
    discovery = execute_operator(_request(tmp_path, "source_discovery", refs=generic_refs(seed)), services=services)
    validation = execute_operator(_request(tmp_path, "source_validation", refs=generic_refs(discovery)), services=services)
    synthesis_refs = [*generic_refs(seed), *generic_refs(validation)]
    synthesis = execute_operator(_request(tmp_path, "evidence_synthesis", payload={"task_contract": _task_contract()}, refs=synthesis_refs), services=services)
    draft = execute_operator(_request(tmp_path, "report_draft", payload={"task_contract": _task_contract()}, refs=generic_refs(synthesis)), services=services)
    review_refs = [*generic_refs(draft), *generic_refs(validation)]
    review = execute_operator(_request(tmp_path, "independent_review", payload={"task_contract": _task_contract()}, refs=review_refs), services=services)
    final_refs = [*generic_refs(review), *generic_refs(draft), *generic_refs(synthesis), *generic_refs(validation)]
    final = execute_operator(_request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=final_refs), services=services)
    chain = (seed, discovery, validation, synthesis, draft, review, final)
    assert [item["status"] for item in chain] == ["completed"] * 7, [item["errors"] for item in chain]
    assert _read_artifact(tmp_path, final)["decision"] == "accepted"


def test_poisoned_artifact_hash_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    path = out / "source_discovery.json"
    path.write_text(json.dumps({"schema": "research_synthesis.source_discovery.v1", "candidates": []}), encoding="utf-8")
    result = execute_operator(
        _request(tmp_path, "source_validation", refs=[{"artifact_id": "source_discovery", "path": "out/source_discovery.json", "schema": "research_synthesis.source_discovery.v1", "sha256": "0" * 64}]),
        services={},
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "artifact_hash_mismatch"


def test_final_acceptance_rejects_self_reported_chain_without_actual_refs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = execute_operator(
        _request(
            tmp_path,
            "final_acceptance",
            payload={"task_contract": _task_contract(), "independent_review": _accepted_review()},
        ),
        services={},
    )
    decision = _read_artifact(tmp_path, result)
    assert result["status"] == "failed"
    assert decision["gate_outcome"] == "fail"
    assert set(decision["missing_required_artifacts"]) == set(BASELINE_ARTIFACTS_FOR_TEST)


def test_acceptance_critical_ref_requires_hash_and_matching_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    refs = _valid_acceptance_refs(tmp_path)
    no_hash_refs = [dict(ref) for ref in refs]
    next(ref for ref in no_hash_refs if ref["artifact_id"] == "independent_review").pop("sha256")
    no_hash = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=no_hash_refs),
        services={},
    )
    assert no_hash["status"] == "failed"
    assert any("no sha256" in reason for reason in _read_artifact(tmp_path, no_hash)["reasons"])

    report_ref = next(ref for ref in refs if ref["artifact_id"] == "report_draft")
    report_path = tmp_path / report_ref["path"]
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["task_id"] = "different-task"
    report_path.write_text(json.dumps(report_payload, sort_keys=True), encoding="utf-8")
    report_ref["sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    wrong_identity = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=refs),
        services={},
    )
    assert wrong_identity["status"] == "failed"
    assert any("task_id does not match" in reason for reason in _read_artifact(tmp_path, wrong_identity)["reasons"])


@pytest.mark.parametrize("identity_key", ["task_id", "run_id", "workflow_id", "node_id"])
def test_acceptance_rejects_missing_identity_even_after_rehash(tmp_path: Path, monkeypatch, identity_key: str) -> None:
    monkeypatch.chdir(tmp_path)
    refs = _valid_acceptance_refs(tmp_path)
    report_ref = next(ref for ref in refs if ref["artifact_id"] == "report_draft")
    report_path = tmp_path / report_ref["path"]
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload.pop(identity_key)
    report_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    report_ref["sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    result = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": _task_contract()}, refs=refs),
        services={},
    )
    assert result["status"] == "failed"
    assert any(f"missing required {identity_key}" in reason for reason in _read_artifact(tmp_path, result)["reasons"])


def test_compound_success_criterion_evaluates_every_conjunct(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    contract = _task_contract()
    contract["success_criteria"] = ["Every conclusion has evidence and the report body is non-empty."]
    result = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=_valid_acceptance_refs(tmp_path, report_body="")),
        services={},
    )
    evaluation = _read_artifact(tmp_path, result)["success_criteria_evaluation"][0]
    assert result["status"] == "failed"
    assert evaluation["status"] == "failed"
    assert [check["status"] for check in evaluation["checks"]] == ["passed", "failed"]


def test_numeric_success_criteria_use_exact_thresholds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    passing = _task_contract()
    passing["success_criteria"] = ["At least 2 validated sources and exactly 1 conclusion."]
    passed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": passing}, refs=_valid_acceptance_refs(tmp_path, source_count=2)),
        services={},
    )
    assert passed["status"] == "completed"
    failing = _task_contract()
    failing["success_criteria"] = ["At least 3 validated sources."]
    failed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": failing}, refs=_valid_acceptance_refs(tmp_path, source_count=2)),
        services={},
    )
    assert failed["status"] == "failed"
    check = _read_artifact(tmp_path, failed)["success_criteria_evaluation"][0]["checks"][0]
    assert check["status"] == "failed"
    assert "required threshold=3" in check["evidence"]

    cited = _task_contract()
    cited["success_criteria"] = ["At least 2 cited sources."]
    cited_pass = execute_operator(
        _request(
            tmp_path,
            "final_acceptance",
            payload={"task_contract": cited},
            refs=_valid_acceptance_refs(tmp_path, source_count=2, cited_source_count=2),
        ),
        services={},
    )
    assert cited_pass["status"] == "completed"
    cited_fail = execute_operator(
        _request(
            tmp_path,
            "final_acceptance",
            payload={"task_contract": cited},
            refs=_valid_acceptance_refs(tmp_path, source_count=2, cited_source_count=1),
        ),
        services={},
    )
    cited_check = _read_artifact(tmp_path, cited_fail)["success_criteria_evaluation"][0]["checks"][0]
    assert cited_fail["status"] == "failed"
    assert cited_check["status"] == "failed"
    assert "cited_source_count=1" in cited_check["evidence"]


@pytest.mark.parametrize(
    "criterion",
    [
        "There should not be fewer than 2 validated sources.",
        "Approximately 2 validated sources.",
        "The report should be good enough.",
        "A score of 80 or better.",
    ],
)
def test_negated_or_ambiguous_criteria_are_unsupported(tmp_path: Path, monkeypatch, criterion: str) -> None:
    monkeypatch.chdir(tmp_path)
    contract = _task_contract()
    contract["success_criteria"] = [criterion]
    result = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=_valid_acceptance_refs(tmp_path)),
        services={},
    )
    assert result["status"] == "failed"
    assert _read_artifact(tmp_path, result)["success_criteria_evaluation"][0]["status"] == "unsupported"


def test_legitimate_artifact_expectation_aliases_are_supported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    contract = _task_contract()
    contract["deliverable"]["artifact_expectations"] = [
        "Markdown report", "evidence index", "validated source list", "review verdict",
    ]
    passed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=_valid_acceptance_refs(tmp_path)),
        services={},
    )
    assert passed["status"] == "completed"
    contract["deliverable"]["artifact_expectations"].append("beautiful executive graphic")
    failed = execute_operator(
        _request(tmp_path, "final_acceptance", payload={"task_contract": contract}, refs=_valid_acceptance_refs(tmp_path)),
        services={},
    )
    assert failed["status"] == "failed"
    assert _read_artifact(tmp_path, failed)["unsupported_artifact_expectations"] == ["beautiful executive graphic"]


def test_absolute_scopes_outside_workspace_are_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    outside_file = outside / "seed.md"
    outside_file.write_text("outside", encoding="utf-8")
    read_request = _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "md", "seed_kind": "markdown", "value": str(outside_file)}]})
    read_request["read_scope"] = [str(outside)]
    read_result = execute_operator(read_request, services={})
    assert read_result["status"] == "failed"
    assert read_result["errors"][0]["error_type"] == "scope_violation"

    write_request = _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "topic", "seed_kind": "topic", "value": "safe"}]})
    write_request["write_scope"] = [str(outside / "write")]
    write_result = execute_operator(write_request, services={})
    assert write_result["status"] == "failed"
    assert write_result["errors"][0]["error_type"] == "scope_violation"


def test_symlink_scope_cannot_escape_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-symlink-target"
    outside.mkdir()
    (outside / "seed.md").write_text("outside", encoding="utf-8")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    link = inputs / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - host policy may deny symlink creation
        if os.name != "nt":
            pytest.skip(f"host denied symlink creation: {exc}")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if junction.returncode != 0:
            pytest.fail(f"could not create a symlink or junction for escape test: {junction.stderr}")
    result = execute_operator(
        _request(tmp_path, "seed_fetch", payload={"seed_inputs": [{"seed_id": "md", "seed_kind": "markdown", "value": "inputs/escape/seed.md"}]}),
        services={},
    )
    assert result["status"] == "failed"
    assert result["errors"][0]["error_type"] == "scope_violation"


def test_no_task_specific_constants_and_no_graph_state_access() -> None:
    package = HARNESS / "plugins" / "autosci" / "operators" / "research_synthesis"
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    forbidden = ["Tencent", "腾讯", "4-6 trends", "four to six trends", "real_data_research", "research_run_state", "graph_state"]
    assert not any(item in text for item in forbidden)
