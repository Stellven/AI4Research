from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from harness.plugins.autosci.operators.research_synthesis.base import ResearchOperatorError
from harness.plugins.autosci.operators.research_synthesis.report_draft import _normalize_report
from harness.plugins.autosci.services.codex_research import CodexResearchModelService
from harness.plugins.autosci.services.production_research import (
    BoundedUrlFetcher,
    LiteratureDiscoveryService,
    ResearchModelService,
    _ProviderRoute,
    _select_candidates,
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


def _offline_urlopen(request, *, timeout: int):
    """Refuse every public provider call so a unit test never leaves the host.

    Discovery consults several bibliographic providers, so any test that leaves
    ``urlopen`` at its default would reach the live internet and its result
    would depend on what arXiv or OpenAlex happened to return that minute.
    """
    raise urllib.error.URLError("network disabled in unit tests")


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
        urlopen=_offline_urlopen,
        sleep=lambda _seconds: None,
        max_attempts_per_provider=1,
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
    usage = {item["provider"]: item for item in result["provider_usage"]}["semantic_scholar"]
    assert (tmp_path / usage["archive_path"]).is_file()
    assert len(usage["request_sha256"]) == len(usage["response_sha256"]) == 64
    # Every other provider was consulted and failed closed into a limitation
    # rather than silently disappearing from the record.
    assert {item["provider"] for item in result["provider_usage"] if item["status"] == "failed"} == {
        "arxiv",
        "europe_pmc",
        "openalex",
        "crossref",
    }


def test_literature_discovery_falls_back_after_semantic_retry_budget_is_exceeded(tmp_path: Path) -> None:
    observed: dict = {}

    def backend(**kwargs):
        observed.update(kwargs)
        return {
            "status": "inconclusive",
            "candidates": [],
            "limitations": [
                "Semantic Scholar provider Retry-After 120s exceeded the 5s retry budget; no early retry was attempted."
            ],
        }

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=backend,
        urlopen=_offline_urlopen,
        sleep=lambda _seconds: None,
    )
    discovery._openalex = lambda query: (
        [
            {
                "source_id": f"openalex:{index}",
                "canonical_id": f"https://openalex.org/W{index}",
                "title": f"Fallback source {index}",
                "url": f"https://openalex.org/W{index}",
                "provider": "openalex",
                "metadata": {},
                "provenance": {"provider": "openalex", "query": query},
                "content_summary": f"Methods and results from fallback source {index}.",
            }
            for index in range(1, 4)
        ],
        {"provider": "openalex", "request_url": "https://api.openalex.org/works", "response_sha256": "a" * 64},
    )

    result = discovery(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "bounded fallback research"}]},
        payload={},
    )

    assert observed["max_retries"] == 1
    assert observed["max_retry_wait_seconds"] == 5.0
    assert len(result["candidates"]) == 3
    assert {item["provider"] for item in result["candidates"]} == {"openalex"}
    assert [item["provider"] for item in json.loads(
        (tmp_path / result["provider_usage"][0]["archive_path"]).read_text(encoding="utf-8")
    )["provider_traces"]] == [
        "semantic_scholar",
        "arxiv",
        "europe_pmc",
        "openalex",
        "crossref",
    ]
    assert any("no early retry was attempted" in item for item in result["limitations"])


def test_literature_discovery_can_require_provider_diversity(tmp_path: Path) -> None:
    def backend(**_kwargs):
        return {
            "status": "completed",
            "candidates": [
                {
                    "candidate_id": f"s2-{index}",
                    "paperId": f"s2-{index}",
                    "title": f"Semantic source {index}",
                    "source_ref": f"https://www.semanticscholar.org/paper/s2-{index}",
                    "source_channels": ["search_s2"],
                }
                for index in range(1, 4)
            ],
            "limitations": [],
        }

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=backend,
        limit=4,
        urlopen=_offline_urlopen,
        sleep=lambda _seconds: None,
    )
    discovery._openalex = lambda query: (
        [
            {
                "source_id": "openalex:1",
                "canonical_id": "https://openalex.org/W1",
                "title": "Independent OpenAlex source",
                "url": "https://openalex.org/W1",
                "provider": "openalex",
                "metadata": {"year": 2026},
                "provenance": {"provider": "openalex", "query": query},
                "content_summary": "Independent provider content.",
            }
        ],
        {"provider": "openalex", "request_url": "https://api.openalex.org/works", "response_sha256": "a" * 64},
    )

    result = discovery(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "provider diversity"}]},
        payload={"task_contract": {"min_provider_families": 2}},
    )

    assert {item["provider"] for item in result["candidates"]} == {"semantic_scholar", "openalex"}
    assert result["candidates"][0]["provider"] == "semantic_scholar"
    assert result["candidates"][1]["provider"] == "openalex"


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

    discovery = LiteratureDiscoveryService(
        long_root,
        backend=backend,
        urlopen=_offline_urlopen,
        sleep=lambda _seconds: None,
        max_attempts_per_provider=1,
    )
    snapshot = {"seeds": [{"seed_kind": "topic", "content": "Long path archive"}]}

    result = discovery(seed_snapshot=snapshot, payload={})

    archive_path = long_root / result["provider_usage"][0]["archive_path"]
    assert len(str(archive_path)) > 260
    assert os.path.isfile(_test_fs_path(archive_path))
    with open(_test_fs_path(archive_path), "rb") as handle:
        body = handle.read()
    assert result["provider_usage"][0]["archive_sha256"] == hashlib.sha256(body).hexdigest()


def test_literature_discovery_retries_then_archives_raw_openalex_attempts(tmp_path: Path) -> None:
    calls: list[str] = []
    sleeps: list[float] = []
    openalex = {
        "results": [
            {
                "id": f"https://openalex.org/W{index}",
                "doi": f"https://doi.org/10.1000/rag{index}",
                "title": f"Retrieval augmented generation evaluation method {index}",
                "publication_year": 2025,
                "primary_location": {"landing_page_url": f"https://openalex.org/W{index}", "source": {}},
                "authorships": [],
                "abstract_inverted_index": {"retrieval": [0], "evaluation": [1], "method": [2]},
            }
            for index in range(1, 4)
        ]
    }

    def urlopen(request, *, timeout):
        calls.append(request.full_url)
        if "api.openalex.org" not in request.full_url:
            raise urllib.error.URLError("provider not part of this scenario")
        if len([call for call in calls if "api.openalex.org" in call]) == 1:
            raise urllib.error.URLError("temporary provider failure")
        return _Response(
            json.dumps(openalex).encode("utf-8"),
            url=request.full_url,
            content_type="application/json",
        )

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=lambda **_kwargs: {"status": "inconclusive", "candidates": [], "limitations": ["S2 unavailable"]},
        urlopen=urlopen,
        sleep=sleeps.append,
        clock=lambda: "2026-08-18T12:00:00Z",
        max_attempts_per_provider=2,
        max_total_wait_seconds=2,
    )
    result = discovery(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "retrieval augmented generation evaluation"}]},
        payload={"task_contract": {"user_intent": "Research retrieval augmented generation evaluation"}},
    )

    assert len(result["candidates"]) == 3
    assert {item["provider"] for item in result["candidates"]} == {"openalex"}
    usage = {item["provider"]: item for item in result["provider_usage"]}
    # Every bibliographic provider in the chain retried its transient failure
    # exactly once, with the same one-second backoff. Only OpenAlex recovers on
    # its second attempt; the rest stay failed and are recorded as such.
    consulted_over_http = {"arxiv", "europe_pmc", "openalex", "crossref"}
    assert sleeps == [1.0] * len(consulted_over_http)
    assert {name for name, item in usage.items() if item["status"] == "failed"} == (
        consulted_over_http - {"openalex"}
    )
    # Semantic Scholar answered, it just had nothing to offer. That is not the
    # same as the transport failing, and the record must not conflate them.
    assert usage["semantic_scholar"]["status"] == "empty"
    assert usage["openalex"]["status"] == "completed"
    attempts = json.loads((tmp_path / usage["openalex"]["archive_path"]).read_text(encoding="utf-8"))["provider_attempts"]
    openalex_attempts = [item for item in attempts if item["provider"] == "openalex"]
    assert [item["status"] for item in openalex_attempts] == ["failed", "completed"]
    for attempt in openalex_attempts:
        assert (tmp_path / attempt["request_path"]).is_file()
        assert (tmp_path / attempt["response_path"]).is_file()
        assert len(attempt["request_sha256"]) == len(attempt["response_sha256"]) == 64


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


def test_production_service_composition_can_select_codex_subscription(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "ambient-openrouter-key")
    monkeypatch.setenv("AUTOSCI_REVIEW_LLM_API_KEY", "ambient-compatible-key")
    monkeypatch.setenv("SOLAR_CODEX_BINARY", "C:/trusted/codex.exe")

    services = production_services_from_environment(
        workspace_root=tmp_path,
        requested_model_provider="codex",
        requested_model="gpt-test",
    )

    writer = services["model_generate"]
    reviewer = services["review_model_generate"]
    assert isinstance(writer, CodexResearchModelService)
    assert isinstance(reviewer, CodexResearchModelService)
    assert writer.role == "writer"
    assert reviewer.role == "reviewer"
    assert writer.model == reviewer.model == "gpt-test"
    assert writer.codex_binary == reviewer.codex_binary == "C:/trusted/codex.exe"
    assert services["secret_values"] == {}
    assert services["service_metadata"]["model_generate"]["service_id"] == writer.service_id


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
    source_policy_summary = {
        "acquisition_mode": "live_search",
        "live_requirement_met": True,
        "accepted_live_count": 2,
    }
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
            "source_policy_summary": source_policy_summary,
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
                ],
                "source_lineage": [
                    {"source_id": "source-1", "title": "One", "url": "https://example.test/one"},
                    {"source_id": "source-2", "title": "Two", "url": "https://example.test/two"},
                ],
                "source_policy_summary": source_policy_summary,
            },
        },
    )
    _system, review_user = service._prompt(
        "independent_review",
        {
            "task_contract": task_contract,
            "report_draft": {"claim_source_lineage": {"claim-1": ["source-1"]}},
            "source_validation": {
                "accepted": [{"source_id": "source-1"}, {"source_id": "source-2"}],
                "source_policy_summary": source_policy_summary,
            },
        },
    )
    _system, revision_user = service._prompt(
        "report_revision",
        {
            "task_contract": task_contract,
            "evidence_synthesis": {
                "claims": [
                    {"claim_id": "claim-1", "evidence_ids": ["source-1"], "limitations": ["bounded evidence"]},
                ],
                "source_lineage": [
                    {"source_id": "source-1", "title": "One", "url": "https://example.test/one"},
                ],
                "source_policy_summary": source_policy_summary,
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
            "source_validation": {
                "accepted": [{"source_id": "source-1"}],
                "source_policy_summary": source_policy_summary,
            },
            "prior_review": {"findings": [{"severity": "high", "message": "Missing method section"}]},
        },
    )

    synthesis_requirements = " ".join(synthesis_user["quality_requirements"])
    report_requirements = " ".join(report_user["quality_requirements"])
    review_rules = " ".join(review_user["review_rules"])
    revision_requirements = " ".join(revision_user["quality_requirements"])
    revision_review_rules = " ".join(revision_review_user["review_rules"])
    assert synthesis_user["allowed_source_ids"] == ["source-1", "source-2"]
    assert synthesis_user["source_policy_summary"] == source_policy_summary
    assert "at least two distinct exact source_id values" in synthesis_requirements
    assert "copied exactly from allowed_source_ids" in synthesis_requirements
    assert "do not abbreviate, hash, prefix, suffix, or repair source ids" in synthesis_requirements
    assert "explicit Method or Evidence Method section" in report_requirements
    assert report_user["source_catalog"][0]["url"] == "https://example.test/one"
    assert report_user["source_policy_summary"] == source_policy_summary
    assert report_user["source_usage_summary"] == {
        "validated_source_count": 2,
        "validated_source_ids": ["source-1", "source-2"],
        "grounded_claim_source_count": 2,
        "grounded_claim_source_ids": ["source-1", "source-2"],
        "unused_validated_source_ids": [],
    }
    assert "reader-visible Markdown link" in report_requirements
    assert "at least two distinct cited sources" in report_requirements
    assert "avoid repeating the same Failure modes" in report_requirements
    assert "explicitly labeled as synthesis" in report_requirements
    assert "do not expand a source-specific finding into a general guarantee" in report_requirements
    assert "controller performed live public discovery" in report_requirements
    assert "unused_validated_source_ids" in report_requirements
    assert "explicit Method or Evidence Method section" in review_rules
    assert "at least two cited source lineages" in review_rules
    assert "controller-performed live public discovery" in review_rules
    assert review_user["source_usage_summary"]["unused_validated_source_ids"] == ["source-2"]
    assert "validated inputs" in review_rules
    assert revision_user["basis_verdict"] == "revise"
    assert "preserve exact claim_id values" in revision_requirements
    assert revision_user["source_catalog"][0]["source_id"] == "source-1"
    assert revision_user["source_policy_summary"] == source_policy_summary
    assert revision_user["source_usage_summary"]["grounded_claim_source_ids"] == ["source-1"]
    assert "reader-visible URL" in revision_requirements
    assert "Repair only issues identified by the independent review" in revision_requirements
    assert "Replace the report body instead of appending duplicate section summaries" in revision_requirements
    assert "Do not claim immutable evidence_synthesis claim_source_lineage was removed" in revision_requirements
    assert "controller performed live public discovery" in revision_requirements
    assert "unused_validated_source_ids" in revision_requirements
    assert "resolves high and critical prior review findings" in revision_review_rules
    assert "exact URL" in revision_review_rules
    assert "Do not require report_revision to mutate immutable evidence_synthesis claim_source_lineage" in revision_review_rules
    assert "all remaining findings are low-severity nits" in revision_review_rules
    assert "Return revise only for medium, high, or critical issues" in revision_review_rules
    assert "controller-performed live public discovery" in revision_review_rules
    assert "unused validated sources" in revision_review_rules
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


def test_report_normalizer_preserves_nested_subsections_exactly_once() -> None:
    report = _normalize_report(
        {
            "report": {
                "title": "Technology trends",
                "body": (
                    "# Technology trends\n\n"
                    "## Evidence Method\n\nOnly supplied claims are used.\n\n"
                    "## Key trends\n\n"
                    "### 1. Agents\n\nAgent evidence.\n\n"
                    "### 2. Robotics\n\nRobot evidence.\n\n"
                    "## Conclusions\n\nThe trends are evidence bounded."
                ),
                "conclusions": [
                    {
                        "conclusion_id": "conclusion-1",
                        "text": "The trends are evidence bounded.",
                        "evidence_ids": ["claim-1"],
                    }
                ],
            }
        },
        {"claim-1"},
    )

    assert report["body"].count("### 1. Agents") == 1
    assert report["body"].count("Agent evidence.") == 1
    assert report["body"].count("### 2. Robotics") == 1
    assert report["body"].count("Robot evidence.") == 1


def test_report_normalizer_does_not_append_section_summaries_after_references() -> None:
    report = _normalize_report(
        {
            "report": {
                "title": "Complete report",
                "body": (
                    "# Complete report\n\n"
                    "## Evidence Method\n\nOnly supplied claims are used.\n\n"
                    "## Detailed findings\n\nThe conclusion is grounded.\n\n"
                    "## References\n\n- source-1: https://example.test/one"
                ),
                "sections": [
                    {"title": "Findings summary", "body": "Compressed duplicate of the detailed findings."},
                    {"title": "Limitations", "body": "Compressed duplicate limitation."},
                ],
                "conclusions": [
                    {
                        "conclusion_id": "conclusion-1",
                        "text": "The conclusion is grounded.",
                        "evidence_ids": ["claim-1"],
                    }
                ],
            }
        },
        {"claim-1"},
    )

    assert report["body"].endswith("- source-1: https://example.test/one")
    assert "Findings summary" not in report["body"]
    assert "Compressed duplicate" not in report["body"]


def test_report_normalizer_inserts_generated_sections_before_references() -> None:
    report = _normalize_report(
        {
            "report": {
                "title": "Bounded report",
                "body": (
                    "# Bounded report\n\n"
                    "## Findings\n\nA source-grounded finding.\n\n"
                    "## References\n\n- source-1: https://example.test/one"
                ),
                "conclusions": [
                    {
                        "conclusion_id": "conclusion-1",
                        "text": "A bounded conclusion not copied into the provider body.",
                        "evidence_ids": ["claim-1"],
                    }
                ],
            },
            "limitations": ["Only one validated source was available."],
        },
        {"claim-1"},
    )

    body = report["body"]
    assert body.index("## Conclusions") < body.index("## Limitations") < body.index("## References")
    assert body.rstrip().endswith("- source-1: https://example.test/one")


def test_report_normalizer_merges_traceable_bullets_into_numbered_conclusions() -> None:
    report = _normalize_report(
        {
            "report": {
                "title": "中文报告",
                "body": (
                    "# 中文报告\n\n"
                    "## 方法\n\n仅使用已验证证据。\n\n"
                    "## 七、结论\n\n总体判断保持谨慎。\n\n"
                    "## 参考资料\n\n- source-1: https://example.test/one"
                ),
                "conclusions": [
                    {
                        "conclusion_id": "conclusion-1",
                        "text": "证据支持一项有边界的技术趋势判断。",
                        "evidence_ids": ["claim-1"],
                    }
                ],
            }
        },
        {"claim-1"},
    )

    body = report["body"]
    assert body.count("结论") == 1
    assert "证据支持一项有边界的技术趋势判断。 证据: claim-1." in body
    assert body.index("证据支持一项有边界的技术趋势判断") < body.index("## 参考资料")


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


def test_webpage_discovery_uses_structured_topic_instead_of_generic_headline() -> None:
    query = _topic_from_snapshot(
        {
            "seeds": [
                {
                    "seed_kind": "url",
                    "title": "中国科学家首次叩响未来之门，发布2049十大科技愿景",
                    "content": "愿景一：AI智能体深度嵌入行业流程\n愿景二：通用机器人突破操作瓶颈",
                }
            ]
        },
        {"task_contract": {"user_intent": "梳理网页技术趋势并搜索公开资料"}},
    )

    assert query == "AI智能体"


def test_multitopic_candidate_selection_preserves_each_controller_query() -> None:
    seeded = [
        {
            "source_id": "seed-page",
            "canonical_id": "https://example.test/trends",
            "title": "Technology trends",
            "provider": "bounded_http",
        }
    ]

    def candidate(source_id: str, provider: str, query: str) -> dict:
        return {
            "source_id": source_id,
            "canonical_id": f"https://example.test/{source_id}",
            "title": source_id,
            "provider": provider,
            "provenance": {"provider": provider, "query": query},
        }

    discovered = [
        candidate("broad-1", "catalog-a", "人工智能"),
        candidate("broad-2", "catalog-a", "人工智能"),
        candidate("broad-3", "catalog-a", "人工智能"),
        candidate("robotics", "wikipedia_zh", "通用机器人"),
        candidate("flying-car", "wikipedia_zh", "飞行汽车"),
    ]

    selected = _select_candidates(seeded, discovered, limit=4)

    assert [item["source_id"] for item in selected] == [
        "seed-page",
        "broad-1",
        "robotics",
        "flying-car",
    ]


def test_wikipedia_discovery_searches_four_bounded_webpage_topics(tmp_path: Path) -> None:
    discovery = LiteratureDiscoveryService(tmp_path, urlopen=_offline_urlopen)
    observed: list[str] = []

    def open_json(_provider: str, url: str):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["gsrsearch"][0]
        observed.append(query)
        page_id = len(observed)
        return {
            "query": {
                "pages": [
                    {
                        "pageid": page_id,
                        "title": query,
                        "fullurl": f"https://zh.wikipedia.org/?curid={page_id}",
                        "extract": f"Evidence about {query}.",
                    }
                ]
            }
        }, str(page_id) * 64

    discovery._open_json = open_json
    candidates, _trace = discovery._wikipedia(["人工智能", "通用机器人", "飞行汽车", "镜像世界", "量子计算"])

    assert observed == ["人工智能", "通用机器人", "飞行汽车", "镜像世界"]
    assert [item["provenance"]["query"] for item in candidates] == observed


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


_ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2410.03810v3</id>
    <published>2024-10-04T00:00:00Z</published>
    <title>Exploring the Limitations of Mamba in COPY
      and CoT Reasoning</title>
    <summary>We study where the Mamba state space architecture
      falls short of transformers.</summary>
    <author><name>Ada Researcher</name></author>
    <author><name>Bo Reviewer</name></author>
    <arxiv:primary_category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2404.15772v3</id>
    <published>2024-04-24T00:00:00Z</published>
    <title>Bi-Mamba+: Bidirectional Mamba for Time Series Forecasting</title>
    <summary>A bidirectional Mamba variant for forecasting.</summary>
    <author><name>Cai Author</name></author>
    <arxiv:doi>10.1000/bimamba</arxiv:doi>
    <arxiv:journal_ref>Journal of Sequence Models 3 (2025) 1-20</arxiv:journal_ref>
    <arxiv:primary_category term="cs.LG"/>
  </entry>
  <entry>
    <id></id>
    <title>Entry without an identifier is skipped</title>
  </entry>
</feed>
"""


def test_literature_discovery_parses_arxiv_atom_into_traceable_candidates(tmp_path: Path) -> None:
    def urlopen(request, *, timeout):
        if "export.arxiv.org" not in request.full_url:
            raise urllib.error.URLError("provider not part of this scenario")
        return _Response(
            _ARXIV_ATOM.encode("utf-8"),
            url=request.full_url,
            content_type="application/atom+xml",
        )

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=lambda **_kwargs: {"status": "inconclusive", "candidates": [], "limitations": []},
        urlopen=urlopen,
        sleep=lambda _seconds: None,
        clock=lambda: "2026-08-18T12:00:00Z",
        max_attempts_per_provider=1,
    )

    result = discovery(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "mamba architecture transformer"}]},
        payload={"task_contract": {"user_intent": "Research mamba architecture transformer"}},
    )

    assert {item["provider"] for item in result["candidates"]} == {"arxiv"}
    by_id = {item["source_id"]: item for item in result["candidates"]}
    assert set(by_id) == {"arxiv:2410.03810v3", "arxiv:2404.15772v3"}

    limitations_paper = by_id["arxiv:2410.03810v3"]
    # The Atom title wraps across lines; it must arrive as one normalized line.
    assert limitations_paper["title"] == "Exploring the Limitations of Mamba in COPY and CoT Reasoning"
    # arXiv answers with an http id; the candidate must carry https so the
    # downstream URL policy does not reject its own discovery result.
    assert limitations_paper["canonical_id"] == "https://arxiv.org/abs/2410.03810v3"
    assert limitations_paper["url"] == "https://arxiv.org/abs/2410.03810v3"
    assert limitations_paper["metadata"]["year"] == 2024
    assert limitations_paper["metadata"]["venue"] == "arXiv preprint"
    assert limitations_paper["metadata"]["authors"] == ["Ada Researcher", "Bo Reviewer"]
    assert limitations_paper["metadata"]["primary_category"] == "cs.LG"
    assert "state space architecture falls short" in limitations_paper["content_summary"]

    # A published DOI outranks the abs URL as the canonical identifier.
    assert by_id["arxiv:2404.15772v3"]["canonical_id"] == "https://doi.org/10.1000/bimamba"
    assert by_id["arxiv:2404.15772v3"]["metadata"]["venue"] == "Journal of Sequence Models 3 (2025) 1-20"

    usage = {item["provider"]: item for item in result["provider_usage"]}
    assert usage["arxiv"]["status"] == "completed"
    assert (tmp_path / usage["arxiv"]["evidence_paths"][0]).is_file()


def test_literature_discovery_rejects_arxiv_response_that_is_not_atom(tmp_path: Path) -> None:
    def urlopen(request, *, timeout):
        if "export.arxiv.org" not in request.full_url:
            raise urllib.error.URLError("provider not part of this scenario")
        return _Response(b"<html>rate exceeded</html", url=request.full_url, content_type="text/html")

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=lambda **_kwargs: {"status": "inconclusive", "candidates": [], "limitations": []},
        urlopen=urlopen,
        sleep=lambda _seconds: None,
        max_attempts_per_provider=1,
    )

    with pytest.raises(ResearchOperatorError) as raised:
        discovery(
            seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "mamba architecture"}]},
            payload={},
        )

    # No provider answered, so discovery fails closed rather than reporting an
    # empty but successful search.
    assert raised.value.error_type == "provider_unavailable"


def test_literature_discovery_shares_the_candidate_budget_across_providers(tmp_path: Path) -> None:
    """One broad provider must not be able to fill the whole candidate budget."""

    def openalex_payload(count: int) -> bytes:
        return json.dumps(
            {
                "results": [
                    {
                        "id": f"https://openalex.org/W{index}",
                        "doi": f"https://doi.org/10.1000/broad{index}",
                        "title": f"Loosely related survey {index}",
                        "publication_year": 2025,
                        "primary_location": {"landing_page_url": f"https://openalex.org/W{index}", "source": {}},
                        "authorships": [],
                        "abstract_inverted_index": {"survey": [0]},
                    }
                    for index in range(1, count + 1)
                ]
            }
        ).encode("utf-8")

    def urlopen(request, *, timeout):
        if "export.arxiv.org" in request.full_url:
            return _Response(_ARXIV_ATOM.encode("utf-8"), url=request.full_url, content_type="application/atom+xml")
        if "api.openalex.org" in request.full_url:
            return _Response(openalex_payload(20), url=request.full_url, content_type="application/json")
        raise urllib.error.URLError("provider not part of this scenario")

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=lambda **_kwargs: {"status": "inconclusive", "candidates": [], "limitations": []},
        urlopen=urlopen,
        sleep=lambda _seconds: None,
        max_attempts_per_provider=1,
        limit=4,
    )

    result = discovery(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "mamba architecture transformer"}]},
        payload={},
    )

    providers = [item["provider"] for item in result["candidates"]]
    # OpenAlex offered 20 rows and arXiv 2; round-robin keeps both arXiv rows
    # instead of letting the larger response crowd them out.
    assert providers.count("arxiv") == 2
    assert providers.count("openalex") == 3


def test_literature_discovery_collapses_the_same_work_seen_under_two_identifiers(tmp_path: Path) -> None:
    """A preprint and its published record are one source, not two."""
    openalex = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/preprint",
                "title": "When Does BiMamba Beat Transformers in JEPA-style Prediction?",
                "publication_year": 2025,
                "primary_location": {"landing_page_url": "https://openalex.org/W1", "source": {}},
                "authorships": [],
                "abstract_inverted_index": {"comparison": [0]},
            },
            {
                "id": "https://openalex.org/W2",
                "doi": "https://doi.org/10.1000/published",
                "title": "When does BiMamba beat Transformers in JEPA-style prediction?",
                "publication_year": 2026,
                "primary_location": {"landing_page_url": "https://openalex.org/W2", "source": {}},
                "authorships": [],
                "abstract_inverted_index": {"comparison": [0]},
            },
            {
                "id": "https://openalex.org/W3",
                "doi": "https://doi.org/10.1000/distinct",
                "title": "A genuinely different state space survey",
                "publication_year": 2025,
                "primary_location": {"landing_page_url": "https://openalex.org/W3", "source": {}},
                "authorships": [],
                "abstract_inverted_index": {"survey": [0]},
            },
        ]
    }

    def urlopen(request, *, timeout):
        if "api.openalex.org" not in request.full_url:
            raise urllib.error.URLError("provider not part of this scenario")
        return _Response(json.dumps(openalex).encode("utf-8"), url=request.full_url, content_type="application/json")

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=lambda **_kwargs: {"status": "inconclusive", "candidates": [], "limitations": []},
        urlopen=urlopen,
        sleep=lambda _seconds: None,
        max_attempts_per_provider=1,
    )

    result = discovery(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "bimamba transformers jepa"}]},
        payload={},
    )

    # The two DOIs differ, so identifier dedup alone would have kept both.
    titles = [item["title"] for item in result["candidates"]]
    assert len(titles) == 2
    assert titles[0] == "When Does BiMamba Beat Transformers in JEPA-style Prediction?"
    assert titles[1] == "A genuinely different state space survey"


def test_literature_discovery_parses_europe_pmc_life_science_records(tmp_path: Path) -> None:
    """arXiv does not index the life sciences; Europe PMC is why they are reachable."""
    europe_pmc = {
        "hitCount": 27841,
        "resultList": {
            "result": [
                {
                    "id": "42046128",
                    "source": "MED",
                    "pmid": "42046128",
                    "doi": "10.1186/s12967-026-08175-1",
                    "title": "Deep learning-driven prediction of off-target risk in CRISPR editing.",
                    "authorString": "Du W, Zhang T, Guo L",
                    "pubYear": "2026",
                    "journalInfo": {"journal": {"title": "Journal of translational medicine"}},
                    "abstractText": "<h4>Background</h4> The CRISPR/Cas9 system has emerged as a tool.",
                },
                {
                    "id": "PMC13295995",
                    "source": "PMC",
                    "title": "Advances in Fish Gene Editing",
                    "authorString": "Xu J, Cheng F",
                    "pubYear": "2026",
                    "journalInfo": {"journal": {"title": "Animals"}},
                    "abstractText": "",
                },
                {"id": "", "source": "", "title": "Unidentifiable record is skipped"},
            ]
        },
    }

    def urlopen(request, *, timeout):
        if "europepmc" not in request.full_url:
            raise urllib.error.URLError("provider not part of this scenario")
        return _Response(
            json.dumps(europe_pmc).encode("utf-8"), url=request.full_url, content_type="application/json"
        )

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=lambda **_kwargs: {"status": "inconclusive", "candidates": [], "limitations": []},
        urlopen=urlopen,
        sleep=lambda _seconds: None,
        max_attempts_per_provider=1,
    )

    result = discovery(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "crispr off target screening"}]},
        payload={},
    )

    by_id = {item["source_id"]: item for item in result["candidates"]}
    assert set(by_id) == {"doi:10.1186/s12967-026-08175-1", "europepmc:PMC/PMC13295995"}

    with_doi = by_id["doi:10.1186/s12967-026-08175-1"]
    assert with_doi["canonical_id"] == "https://doi.org/10.1186/s12967-026-08175-1"
    # The trailing period Europe PMC puts on titles is dropped so the same work
    # from another provider collapses onto it.
    assert with_doi["title"] == "Deep learning-driven prediction of off-target risk in CRISPR editing"
    assert with_doi["metadata"]["year"] == 2026
    assert with_doi["metadata"]["pmid"] == "42046128"
    assert with_doi["metadata"]["authors"] == ["Du W", "Zhang T", "Guo L"]
    # Europe PMC embeds section markup in abstracts; it must not reach evidence.
    assert "<h4>" not in with_doi["content_summary"]
    assert with_doi["content_summary"].startswith("Background")

    # A record without a DOI is still addressable through its Europe PMC id.
    assert by_id["europepmc:PMC/PMC13295995"]["canonical_id"] == "https://europepmc.org/article/PMC/PMC13295995"


def test_literature_discovery_refuses_an_arxiv_feed_that_declares_an_entity(tmp_path: Path) -> None:
    """XML from the network is the one amplification vector this service has."""
    hostile = (
        b'<?xml version="1.0"?>\n'
        b'<!DOCTYPE feed [<!ENTITY lol "aaaaaaaaaa">]>\n'
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        b"<id>https://arxiv.org/abs/1</id><title>&lol;</title>"
        b"</entry></feed>"
    )

    def urlopen(request, *, timeout):
        if "export.arxiv.org" not in request.full_url:
            raise urllib.error.URLError("provider not part of this scenario")
        return _Response(hostile, url=request.full_url, content_type="application/atom+xml")

    discovery = LiteratureDiscoveryService(
        tmp_path,
        backend=lambda **_kwargs: {"status": "inconclusive", "candidates": [], "limitations": []},
        urlopen=urlopen,
        sleep=lambda _seconds: None,
        max_attempts_per_provider=1,
    )

    with pytest.raises(ResearchOperatorError) as raised:
        discovery(seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "mamba"}]}, payload={})

    assert raised.value.error_type == "provider_unavailable"
