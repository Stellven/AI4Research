from __future__ import annotations

import hashlib
import json
import os
import urllib.error
from pathlib import Path

import pytest

from harness.plugins.autosci.operators.research_synthesis.base import ResearchOperatorError
from harness.plugins.autosci.operators.research_synthesis.report_draft import _normalize_report
from harness.plugins.autosci.services.production_research import (
    BoundedUrlFetcher,
    LiteratureDiscoveryService,
    ResearchModelService,
    _ProviderRoute,
    _topic_from_snapshot,
    production_services_from_environment,
)


PUBLIC_DNS = lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))]


def _test_fs_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


class _Response:
    def __init__(self, body: bytes, *, url: str, content_type: str = "text/html; charset=utf-8") -> None:
        self._body = body
        self._url = url
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body)), "ETag": "test"}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount: int) -> bytes:
        return self._body[:amount]

    def geturl(self) -> str:
        return self._url


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.timeout = None

    def open(self, request, *, timeout: int):
        assert request.full_url.startswith("https://")
        self.timeout = timeout
        return self.response


class _ModelResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _amount: int) -> bytes:
        return self._body


def _model_payload(content: dict) -> dict:
    return {
        "model": "test-model",
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def _model_service(tmp_path: Path, urlopen) -> ResearchModelService:
    return ResearchModelService(
        tmp_path,
        routes=[_ProviderRoute("openai_compatible", "https://provider.example.test/chat", "test-model", "test-key")],
        max_attempts=3,
        retry_max_sleep_seconds=0,
        urlopen=urlopen,
        clock=lambda: "2026-08-05T12:00:00Z",
    )


def _model_kwargs() -> dict:
    return {
        "node_id": "evidence_synthesis",
        "task_contract": {"user_intent": "Summarize evidence.", "deliverable": {"language": "en"}},
        "validated_sources": [{"source_id": "source-1", "title": "Evidence", "content_summary": "Traceable facts."}],
    }


def test_bounded_url_fetch_archives_traceable_visible_content(tmp_path: Path) -> None:
    body = (
        "<html><head><title>WebAssembly optimization</title>"
        "<meta name='description' content='compiler runtime evidence'></head>"
        "<body><article>Tiered compilation trades startup latency for peak throughput.</article>"
        "<script>secret-invisible-script</script></body></html>"
    ).encode()
    opener = _Opener(_Response(body, url="https://example.test/article"))
    fetch = BoundedUrlFetcher(
        tmp_path,
        timeout_seconds=7,
        resolver=PUBLIC_DNS,
        opener_factory=lambda *_handlers: opener,
        clock=lambda: "2026-08-05T12:00:00Z",
    )

    result = fetch("https://example.test/article", seed={"seed_id": "seed-001"})

    assert result["service_id"] == "autosci-production-bounded-url-fetch"
    assert result["service_version"] == "1.0.0"
    assert result["title"] == "WebAssembly optimization"
    assert "Tiered compilation" in result["content"]
    assert "secret-invisible-script" not in result["content"]
    assert result["response_sha256"] == hashlib.sha256(body).hexdigest()
    assert opener.timeout == 7
    assert (tmp_path / result["archive_path"]).read_bytes() == body
    metadata = json.loads((tmp_path / result["metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["requested_url"] == "https://example.test/article"
    assert metadata["fetched_at"] == "2026-08-05T12:00:00Z"
    assert metadata["request_sha256"] == result["request_sha256"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/private"])
def test_bounded_url_fetch_rejects_unsafe_urls(tmp_path: Path, url: str) -> None:
    fetch = BoundedUrlFetcher(
        tmp_path,
        resolver=lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))],
    )

    with pytest.raises(ResearchOperatorError) as raised:
        fetch(url, seed={"seed_id": "seed-unsafe"})

    assert raised.value.error_type in {"invalid_url", "url_policy_rejected"}


def test_literature_discovery_reuses_backend_and_hashes_multiple_sources(tmp_path: Path) -> None:
    observed: dict = {}

    def backend(**kwargs):
        observed.update(kwargs)
        return {
            "status": "completed",
            "candidates": [
                {
                    "candidate_id": f"s2-{index}",
                    "title": title,
                    "source_ref": f"https://www.semanticscholar.org/paper/s2-{index}",
                    "abstract": f"Evidence about {title}.",
                    "source_channels": ["semantic_scholar"],
                }
                for index, title in enumerate(
                    ["Tiered compilation", "WebAssembly JIT trade-offs", "Runtime optimization survey"],
                    start=1,
                )
            ],
            "limitations": [],
        }

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=backend,
        clock=lambda: "2026-08-05T12:00:00Z",
    )
    snapshot = {"seeds": [{"seed_kind": "topic", "content": "WebAssembly runtime compiler optimization"}]}

    result = discovery(seed_snapshot=snapshot, payload={"task_contract": {"user_intent": "Survey WebAssembly optimizations"}})

    assert observed["allow_network_fetch"] is True
    assert observed["max_retries"] == 1
    assert observed["max_retry_wait_seconds"] == 5.0
    assert result["service_id"] == "autosci-production-literature-discovery"
    assert result["query"] == "WebAssembly runtime compiler optimization"
    assert len(result["candidates"]) == 3
    assert {item["provider"] for item in result["candidates"]} == {"semantic_scholar"}
    assert all(len(item["candidate_sha256"]) == 64 for item in result["candidates"])
    usage = result["provider_usage"][0]
    assert (tmp_path / usage["archive_path"]).is_file()
    assert len(usage["request_sha256"]) == len(usage["response_sha256"]) == 64


def test_literature_discovery_archives_under_long_windows_workspace_path(tmp_path: Path) -> None:
    long_root = (
        tmp_path
        / ("phase5-generalization-integration-" + "x" * 80)
        / ("content-diversity-provider-retry-" + "y" * 80)
        / ("service-evidence-root-" + "z" * 60)
    )

    def backend(**_kwargs):
        return {
            "status": "completed",
            "candidates": [
                {
                    "candidate_id": "s2-long-path",
                    "title": "Long path provider evidence",
                    "source_ref": "https://www.semanticscholar.org/paper/s2-long-path",
                    "abstract": "Evidence archived below a deep Windows workspace path.",
                    "source_channels": ["semantic_scholar"],
                }
            ],
            "limitations": [],
        }

    discovery = LiteratureDiscoveryService(long_root, backend=backend)
    snapshot = {"seeds": [{"seed_kind": "topic", "content": "Long path archive"}]}

    result = discovery(seed_snapshot=snapshot, payload={})

    archive_path = long_root / result["provider_usage"][0]["archive_path"]
    assert len(str(archive_path)) > 260
    assert os.path.isfile(_test_fs_path(archive_path))
    with open(_test_fs_path(archive_path), "rb") as handle:
        body = handle.read()
    assert result["provider_usage"][0]["archive_sha256"] == hashlib.sha256(body).hexdigest()


def test_production_service_composition_supports_injected_fakes_without_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fake = object()

    services = production_services_from_environment(workspace_root=tmp_path, overrides={"fetch_url": fake})

    assert services["fetch_url"] is fake
    assert callable(services["discover_sources"])
    assert callable(services["model_generate"])
    assert services["secret_values"] == {}
    assert services["service_metadata"]["fetch_url"]["version"] == "1.0.0"


def test_openrouter_is_default_and_openai_key_is_not_bound_when_both_exist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-secret")
    monkeypatch.setenv("AUTOSCI_LIVE_REVIEW_LLM_PROVIDER", "openai")
    monkeypatch.setenv("AUTOSCI_LIVE_REVIEW_LLM_MODEL", "gpt-5.5")
    monkeypatch.delenv("AUTOSCI_RESEARCH_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("AUTOSCI_RESEARCH_LLM_MODEL", raising=False)
    monkeypatch.delenv("AUTOSCI_RESEARCH_ALLOW_OPENAI_FALLBACK", raising=False)

    model = ResearchModelService.from_environment(tmp_path)
    services = production_services_from_environment(workspace_root=tmp_path)

    assert [(route.provider, route.model) for route in model.routes] == [
        ("openrouter", "deepseek/deepseek-v3.2")
    ]
    assert services["secret_values"]["OPENROUTER_API_KEY"] == "test-openrouter-secret"
    assert "OPENAI_API_KEY" not in services["secret_values"]


def test_research_model_prompt_preserves_content_acceptance_requirements(tmp_path: Path) -> None:
    service = ResearchModelService(tmp_path, routes=[])
    task_contract = {
        "user_intent": "Generate a technical survey with traceable judgments.",
        "deliverable": {"language": "en"},
    }

    _system, synthesis_user = service._prompt(
        "evidence_synthesis",
        {
            "task_contract": task_contract,
            "validated_sources": [
                {"source_id": "source-1", "title": "One", "content_summary": "A"},
                {"source_id": "source-2", "title": "Two", "content_summary": "B"},
            ],
        },
    )
    _system, report_user = service._prompt(
        "report_draft",
        {
            "task_contract": task_contract,
            "evidence_synthesis": {
                "claims": [
                    {"claim_id": "claim-1", "evidence_ids": ["source-1"]},
                    {"claim_id": "claim-2", "evidence_ids": ["source-2"]},
                ]
            },
        },
    )
    _system, review_user = service._prompt("independent_review", {"task_contract": task_contract})
    _system, revision_user = service._prompt(
        "report_revision",
        {
            "task_contract": task_contract,
            "evidence_synthesis": {
                "claims": [
                    {"claim_id": "claim-1", "evidence_ids": ["source-1"], "limitations": ["bounded evidence"]},
                ]
            },
            "original_report": {"report": {"body": "Draft"}},
            "independent_review": {
                "verdict_suggestion": "revise",
                "findings": [{"severity": "high", "message": "Missing method section"}],
            },
        },
    )
    _system, revision_review_user = service._prompt(
        "report_revision_review",
        {
            "task_contract": task_contract,
            "report_draft": {"report": {"body": "Revised"}},
            "source_validation": {"accepted": [{"source_id": "source-1"}]},
            "prior_review": {"findings": [{"severity": "high", "message": "Missing method section"}]},
        },
    )

    synthesis_requirements = " ".join(synthesis_user["quality_requirements"])
    report_requirements = " ".join(report_user["quality_requirements"])
    review_rules = " ".join(review_user["review_rules"])
    revision_requirements = " ".join(revision_user["quality_requirements"])
    revision_review_rules = " ".join(revision_review_user["review_rules"])
    assert synthesis_user["allowed_source_ids"] == ["source-1", "source-2"]
    assert "at least two distinct exact source_id values" in synthesis_requirements
    assert "copied exactly from allowed_source_ids" in synthesis_requirements
    assert "do not abbreviate, hash, prefix, suffix, or repair source ids" in synthesis_requirements
    assert "explicit Method or Evidence Method section" in report_requirements
    assert "at least two distinct cited sources" in report_requirements
    assert "avoid repeating the same Failure modes" in report_requirements
    assert "explicitly labeled as synthesis" in report_requirements
    assert "do not expand a source-specific finding into a general guarantee" in report_requirements
    assert "explicit Method or Evidence Method section" in review_rules
    assert "at least two cited source lineages" in review_rules
    assert revision_user["basis_verdict"] == "revise"
    assert "preserve exact claim_id values" in revision_requirements
    assert "Repair only issues identified by the independent review" in revision_requirements
    assert "Replace the report body instead of appending duplicate section summaries" in revision_requirements
    assert "Do not claim immutable evidence_synthesis claim_source_lineage was removed" in revision_requirements
    assert "resolves high and critical prior review findings" in revision_review_rules
    assert "Do not require report_revision to mutate immutable evidence_synthesis claim_source_lineage" in revision_review_rules
    assert "all remaining findings are low-severity nits" in revision_review_rules
    assert "Return revise only for medium, high, or critical issues" in revision_review_rules
    assert revision_review_user["prior_review_findings"][0]["severity"] == "high"


def test_report_normalizer_adds_evidence_method_when_model_omits_it() -> None:
    report = _normalize_report(
        {
            "report": {
                "title": "Traceable survey",
                "body": "## Findings\n\nA bounded finding.",
                "conclusions": [
                    {
                        "conclusion_id": "conclusion-001",
                        "text": "A bounded finding.",
                        "evidence_ids": ["claim-001"],
                    }
                ],
            }
        },
        {"claim-001"},
    )

    assert "## Evidence Method" in report["body"]
    assert "source-bounded synthesis" in report["body"]


def test_report_normalizer_accepts_top_level_conclusions_with_nested_report_body() -> None:
    report = _normalize_report(
        {
            "report": {
                "title": "Traceable revision",
                "body": "## Evidence Method\n\nOnly supplied claims are used.",
            },
            "conclusions": [
                {
                    "conclusion_id": "conclusion-1",
                    "text": "The revised report is traceable.",
                    "evidence_ids": ["claim-1"],
                }
            ],
            "sections": [{"title": "Findings", "body": "The revised report is traceable."}],
        },
        {"claim-1"},
    )

    assert report["title"] == "Traceable revision"
    assert report["conclusions"][0]["evidence_ids"] == ["claim-1"]
    assert "## Findings" in report["body"]


def test_report_normalizer_removes_repeated_markdown_sections() -> None:
    report = _normalize_report(
        {
            "report": {
                "title": "Traceable revision",
                "body": (
                    "# Traceable revision\n\n"
                    "## 1. Evidence Method\n\nFirst method section.\n\n"
                    "## Conclusions\n\nThe revised report is traceable.\n\n"
                    "## Evidence Method\n\nDuplicate method section.\n\n"
                    "## Conclusions\n\nDuplicate conclusion section."
                ),
                "conclusions": [
                    {
                        "conclusion_id": "conclusion-1",
                        "text": "The revised report is traceable.",
                        "evidence_ids": ["claim-1"],
                    }
                ],
            }
        },
        {"claim-1"},
    )

    assert report["body"].count("Evidence Method") == 1
    assert report["body"].count("## Conclusions") == 1
    assert "Duplicate method section" not in report["body"]


def test_topic_discovery_query_distills_research_subject_from_instruction() -> None:
    query = _topic_from_snapshot(
        {
            "seeds": [
                {
                    "seed_kind": "topic",
                    "content": (
                        "Search public sources and generate an English technical survey on reliability and "
                        "evaluation methods for retrieval-augmented generation systems. Cover evaluation "
                        "dimensions, benchmark design, failure modes, observability, trade-offs, and open "
                        "research problems."
                    ),
                }
            ]
        },
        {"task_contract": {}},
    )

    assert query == "reliability and evaluation methods for retrieval-augmented generation systems"
    assert "Search public sources" not in query
    assert "Cover evaluation dimensions" not in query


def test_research_model_retries_429_retry_after_on_same_route(tmp_path: Path) -> None:
    calls = []

    def urlopen(request, *, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limited",
                {"Retry-After": "2"},
                None,
            )
        return _ModelResponse(_model_payload({"claims": [{"claim_id": "claim-1", "text": "ok", "evidence_ids": ["source-1"]}]}))

    result = _model_service(tmp_path, urlopen)(**_model_kwargs())

    assert len(calls) == 2
    usage = result["provider_usage"][0]
    assert usage["attempt_count"] == 2
    assert usage["retry_events"][0]["status_code"] == 429
    assert result["claims"][0]["claim_id"] == "claim-1"


def test_research_model_exhausts_persistent_429_without_completed_payload(tmp_path: Path) -> None:
    calls = []

    def urlopen(request, *, timeout):
        calls.append((request, timeout))
        raise urllib.error.HTTPError(request.full_url, 429, "rate limited", {"Retry-After": "0"}, None)

    with pytest.raises(ResearchOperatorError) as raised:
        _model_service(tmp_path, urlopen)(**_model_kwargs())

    assert len(calls) == 3
    assert raised.value.error_type == "provider_unavailable"
    assert "provider_rate_limited" in str(raised.value)


def test_research_model_retries_timeout_on_same_route(tmp_path: Path) -> None:
    calls = []

    def urlopen(_request, *, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError("provider did not respond")
        return _ModelResponse(_model_payload({"claims": [{"claim_id": "claim-1", "text": "ok", "evidence_ids": ["source-1"]}]}))

    result = _model_service(tmp_path, urlopen)(**_model_kwargs())

    assert calls == [60, 60]
    usage = result["provider_usage"][0]
    assert usage["attempt_count"] == 2
    assert usage["retry_events"][0]["failure"] == "TimeoutError"
