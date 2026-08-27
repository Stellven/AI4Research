from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
PLUGIN = HARNESS / "plugins" / "autosci"
sys.path.insert(0, str(PLUGIN))

from backends import literature_discover  # noqa: E402


def _test_fs_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


class FakeS2Response:
    def __init__(self, status_code: int, payload=None, headers=None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_from_wiki_uses_recent_arxiv_anchors_and_honors_limit(monkeypatch, tmp_path: Path) -> None:
    wiki = tmp_path / "artifacts" / "autosci" / "workspace" / "wiki"
    paper_dir = wiki / "papers"
    paper_dir.mkdir(parents=True)
    paper_dir.joinpath("seed.md").write_text(
        "---\ntitle: Seed Paper\narxiv: 2401.00001\n---\n# Seed Paper\n",
        encoding="utf-8",
    )

    def fake_recommend(positive_ids, negative_ids, limit):
        assert positive_ids == ["2401.00001"]
        return [
            {
                "paperId": "s2-a",
                "title": "First New Candidate",
                "abstract": "Skill synthesis and agent learning.",
                "externalIds": {"ArXiv": "2401.00002"},
                "citationCount": 25,
                "year": 2025,
                "url": "https://example.test/a",
            },
            {
                "paperId": "s2-b",
                "title": "Second New Candidate",
                "abstract": "Agent skill discovery.",
                "externalIds": {"ArXiv": "2401.00003"},
                "citationCount": 5,
                "year": 2024,
                "url": "https://example.test/b",
            },
        ]

    monkeypatch.setattr(literature_discover, "_s2_recommend", fake_recommend)
    monkeypatch.setattr(literature_discover, "_s2_references", lambda arxiv_id, limit: [])
    monkeypatch.setattr(literature_discover, "_s2_citations", lambda arxiv_id, limit: [])
    result = literature_discover.discover_literature(
        mode="wiki",
        limit=1,
        wiki_root=wiki,
        workspace_root=tmp_path,
        repository_root=HARNESS,
    )
    assert result["status"] == "completed"
    assert result["mode"] == "wiki"
    assert result["anchors"] == ["2401.00001"]
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["candidate_id"] == "arxiv:2401.00002"
    assert candidate["source_channels"] == ["recommend"]
    assert candidate["dedup_status"] == "new"


def test_from_wiki_without_network_returns_inconclusive_not_fixture(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    paper_dir = wiki / "papers"
    paper_dir.mkdir(parents=True)
    paper_dir.joinpath("seed.md").write_text(
        "---\ntitle: Seed Paper\narxiv_id: 2401.00001\n---\n",
        encoding="utf-8",
    )
    result = literature_discover.discover_literature(
        mode="wiki",
        limit=10,
        wiki_root=wiki,
        workspace_root=tmp_path,
        repository_root=HARNESS,
        allow_network_fetch=False,
    )
    assert result["status"] == "inconclusive"
    assert result["candidates"] == []
    assert "fixture" not in " ".join(result["limitations"]).lower()


def test_topic_discovery_retries_semantic_scholar_429_then_returns_candidates(monkeypatch, tmp_path: Path, capsys) -> None:
    responses = [
        FakeS2Response(429, headers={"Retry-After": "0.25"}),
        FakeS2Response(
            200,
            {
                "data": [
                    {
                        "paperId": "s2-skillgen-related",
                        "title": "Verified Inference-Time Agent Skill Synthesis",
                        "abstract": "A related paper about skill synthesis for inference-time agents.",
                        "externalIds": {"ArXiv": "2601.12345"},
                        "citationCount": 17,
                        "year": 2026,
                        "url": "https://example.test/skillgen-related",
                    }
                ]
            },
        ),
    ]
    calls = []
    sleeps = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(literature_discover, "HAS_REQUESTS", True)
    monkeypatch.setattr(literature_discover, "requests", SimpleNamespace(request=fake_request))
    monkeypatch.setattr(literature_discover.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setenv("AUTOSCI_S2_RATE_LIMIT_DELAY_SECONDS", "0")
    monkeypatch.setenv("AUTOSCI_S2_MAX_RETRIES", "1")
    monkeypatch.setenv("AUTOSCI_S2_RETRY_DELAY_SECONDS", "60")
    progress_path = (
        tmp_path
        / ("phase5-long-progress-" + "x" * 80)
        / ("semantic-scholar-retry-" + "y" * 80)
        / "semantic_scholar_retry_progress.json"
    )

    result = literature_discover.discover_literature(
        mode="topic",
        query="SkillGen verified inference-time agent skill synthesis",
        limit=1,
        wiki_root=tmp_path / "wiki",
        workspace_root=tmp_path,
        repository_root=HARNESS,
        progress_path=progress_path,
    )

    stderr = capsys.readouterr().err
    assert result["status"] == "completed"
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["candidate_id"] == "arxiv:2601.12345"
    assert len(calls) == 2
    assert sleeps == [0.25]
    assert any("Semantic Scholar rate-limit retry 1/1" in item for item in result["limitations"])
    assert "waiting 0.25s before retry 1/1" in stderr
    assert "progress write failed" not in stderr
    with open(_test_fs_path(progress_path), encoding="utf-8") as handle:
        progress = json.load(handle)
    assert progress["schema"] == "autosci_s2_retry_progress.v1"
    assert progress["status"] == "waiting_for_rate_limit"
    assert progress["current_event"]["status_code"] == 429
    assert any(artifact["type"] == "semantic_scholar_retry_progress_json" for artifact in result["artifacts"])


def test_topic_discovery_exhausted_semantic_scholar_429_is_inconclusive(monkeypatch, tmp_path: Path) -> None:
    calls = []
    sleeps = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeS2Response(429)

    monkeypatch.setattr(literature_discover, "HAS_REQUESTS", True)
    monkeypatch.setattr(literature_discover, "requests", SimpleNamespace(request=fake_request))
    monkeypatch.setattr(literature_discover.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setenv("AUTOSCI_S2_RATE_LIMIT_DELAY_SECONDS", "0")
    monkeypatch.setenv("AUTOSCI_S2_MAX_RETRIES", "1")
    monkeypatch.setenv("AUTOSCI_S2_RETRY_DELAY_SECONDS", "0.5")

    result = literature_discover.discover_literature(
        mode="topic",
        query="SkillGen verified inference-time agent skill synthesis",
        limit=2,
        wiki_root=tmp_path / "wiki",
        workspace_root=tmp_path,
        repository_root=HARNESS,
    )

    assert result["status"] == "inconclusive"
    assert result["candidates"] == []
    assert len(calls) == 2
    assert sleeps == [0.5]
    assert any("Discovery source failed: Semantic Scholar API rate limited after 2 attempt(s)" in item for item in result["limitations"])
    assert any("Semantic Scholar rate-limit retry 1/1" in item for item in result["limitations"])


def test_semantic_scholar_key_is_sent_only_as_header(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_request(_method, _url, **kwargs):
        calls.append(kwargs)
        return FakeS2Response(200, {"data": []})

    monkeypatch.setattr(literature_discover, "HAS_REQUESTS", True)
    monkeypatch.setattr(literature_discover, "requests", SimpleNamespace(request=fake_request))
    monkeypatch.setattr(literature_discover.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("AUTOSCI_S2_RATE_LIMIT_DELAY_SECONDS", "0")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "opaque-test-key")

    literature_discover._s2_request("GET", "https://api.semanticscholar.org/graph/v1/paper/search")

    assert calls[0]["headers"] == {"x-api-key": "opaque-test-key"}
    assert "opaque-test-key" not in calls[0]["params"]
    assert "opaque-test-key" not in str(calls[0].get("json"))


def test_semantic_scholar_429_uses_exponential_backoff_without_retry_after(monkeypatch) -> None:
    responses = [
        FakeS2Response(429),
        FakeS2Response(429),
        FakeS2Response(200, {"data": []}),
    ]
    sleeps: list[float] = []

    monkeypatch.setattr(literature_discover, "HAS_REQUESTS", True)
    monkeypatch.setattr(
        literature_discover,
        "requests",
        SimpleNamespace(request=lambda *_args, **_kwargs: responses.pop(0)),
    )
    monkeypatch.setattr(literature_discover.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setenv("AUTOSCI_S2_RATE_LIMIT_DELAY_SECONDS", "0")
    monkeypatch.setenv("AUTOSCI_S2_RETRY_DELAY_SECONDS", "0.5")

    literature_discover._s2_request(
        "GET",
        "https://api.semanticscholar.org/graph/v1/paper/search",
        max_retries=2,
    )

    assert sleeps == [0.5, 1.0]


def test_topic_discovery_does_not_retry_before_provider_retry_after(monkeypatch, tmp_path: Path) -> None:
    responses = [FakeS2Response(429, headers={"Retry-After": "120"})]
    sleeps: list[float] = []
    calls: list[tuple[tuple, dict]] = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(
        literature_discover,
        "requests",
        SimpleNamespace(request=request),
    )
    monkeypatch.setattr(literature_discover, "HAS_REQUESTS", True)
    monkeypatch.setattr(literature_discover.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setenv("AUTOSCI_S2_RATE_LIMIT_DELAY_SECONDS", "0")
    progress_path = tmp_path / "semantic-scholar-progress.json"

    result = literature_discover.discover_literature(
        mode="topic",
        query="bounded retry",
        limit=1,
        wiki_root=tmp_path / "wiki",
        workspace_root=tmp_path,
        max_retries=1,
        max_retry_wait_seconds=5,
        progress_path=progress_path,
    )

    assert result["status"] == "inconclusive"
    assert result["candidates"] == []
    assert len(calls) == 1
    assert sleeps == []
    assert any("Retry-After 120s exceeds retry budget 5s" in item for item in result["limitations"])
    assert any("no early retry was attempted" in item for item in result["limitations"])
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert progress["status"] == "retry_budget_exceeded"
    event = progress["current_event"]
    assert event["provider_retry_after_seconds"] == 120.0
    assert event["max_retry_wait_seconds"] == 5.0
    assert event["actual_wait_seconds"] == 0.0
    assert event["budget_exceeded"] is True


def test_topic_discovery_still_bounded_retries_network_failure_without_retry_after(monkeypatch, tmp_path: Path) -> None:
    responses: list[object] = [
        OSError("temporary network failure"),
        FakeS2Response(
            200,
            {
                "data": [
                    {
                        "paperId": "network-retry",
                        "title": "Bounded network retry",
                        "abstract": "We evaluate a bounded retry and report completed results.",
                        "url": "https://example.test/network-retry",
                    }
                ]
            },
        ),
    ]
    sleeps: list[float] = []

    def request(*_args, **_kwargs):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(literature_discover, "requests", SimpleNamespace(request=request))
    monkeypatch.setattr(literature_discover, "HAS_REQUESTS", True)
    monkeypatch.setattr(literature_discover.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setenv("AUTOSCI_S2_RATE_LIMIT_DELAY_SECONDS", "0")
    monkeypatch.setenv("AUTOSCI_S2_RETRY_DELAY_SECONDS", "60")

    result = literature_discover.discover_literature(
        mode="topic",
        query="bounded network retry",
        limit=1,
        wiki_root=tmp_path / "wiki",
        workspace_root=tmp_path,
        max_retries=1,
        max_retry_wait_seconds=5,
    )

    assert result["status"] == "completed"
    assert sleeps == [5.0]
    assert any("waited 5s" in item for item in result["limitations"])
