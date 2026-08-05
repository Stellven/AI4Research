from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from harness.plugins.autosci.operators.research_synthesis.base import ResearchOperatorError
from harness.plugins.autosci.services.production_research import (
    BoundedUrlFetcher,
    LiteratureDiscoveryService,
    ResearchModelService,
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
