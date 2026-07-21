"""TopicAdapter — discover repos via GitHub Search API by topic list.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C2_adapters_snapshots / adapter:topic

Queries:
    GET /search/repositories?q=topic:{topic}&sort=stars&order=desc

fetch_fn signature:
    fetch_fn(url: str, headers: dict[str, str]) -> dict   (parsed JSON)
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

# Allow standalone execution from adapters/ directory
if __package__ is None or __package__ == "":
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from schema import DiscoveryCandidate, utc_now_iso
else:
    from ..schema import DiscoveryCandidate, utc_now_iso


_GH_SEARCH_URL = "https://api.github.com/search/repositories"
_DEFAULT_TOPICS = [
    "llm",
    "large-language-model",
    "ai-agent",
    "rag",
    "vector-database",
    "mlx",
    "transformer",
]
_DEFAULT_PER_PAGE = 30


def _default_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


class TopicAdapter:
    """Discover repos from GitHub Search API using a list of topics."""

    source_type = "topic"

    def __init__(
        self,
        topics: list[str] | None = None,
        per_page: int = _DEFAULT_PER_PAGE,
        github_token: str | None = None,
        fetch_fn: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self.topics = topics if topics is not None else _DEFAULT_TOPICS
        self.per_page = per_page
        self.github_token = github_token
        self._fetch = fetch_fn or _default_fetch

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            h["Authorization"] = f"Bearer {self.github_token}"
        return h

    def run(
        self,
        since: datetime | None = None,
        fetch_fn: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ) -> list[DiscoveryCandidate]:
        """Query each topic and return deduplicated DiscoveryCandidate list.

        Args:
            since: Not used by GitHub Search, kept for interface parity.
            fetch_fn: Optional override; if provided, replaces instance fetch_fn.
        """
        fn = fetch_fn or self._fetch
        now = utc_now_iso()
        seen: set[str] = set()
        results: list[DiscoveryCandidate] = []

        for topic in self.topics:
            url = (
                f"{_GH_SEARCH_URL}?q=topic:{topic}"
                f"&sort=stars&order=desc&per_page={self.per_page}"
            )
            try:
                data = fn(url, self._headers())
            except urllib.error.HTTPError as exc:
                # 403 rate-limit, 422 validation error — skip topic, don't crash
                if exc.code in (403, 422, 429):
                    continue
                raise
            except Exception:
                continue

            items = data.get("items") or []
            for item in items:
                full_name: str = item.get("full_name", "")
                if not full_name or full_name in seen:
                    continue
                seen.add(full_name)
                results.append(
                    DiscoveryCandidate(
                        full_name=full_name,
                        source_type=self.source_type,
                        discovered_at=now,
                        metadata={
                            "query_topic": topic,
                            "stars": item.get("stargazers_count"),
                            "forks": item.get("forks_count"),
                            "pushed_at": item.get("pushed_at"),
                            "description": (item.get("description") or "")[:200],
                            "topics": item.get("topics") or [],
                        },
                    )
                )

        return results


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _self_test() -> dict[str, Any]:
    metrics: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "details": []}

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["details"].append({"test": name, "status": "pass"})

    def _fail(name: str, reason: str) -> None:
        metrics["tests_run"] += 1
        metrics["details"].append({"test": name, "status": "fail", "reason": reason})

    # Stub fetch: returns two repos for 'llm', one repo for 'rag'
    def _stub_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        if "topic:llm" in url:
            return {
                "total_count": 2,
                "items": [
                    {
                        "full_name": "owner/llm-repo",
                        "stargazers_count": 5000,
                        "forks_count": 300,
                        "pushed_at": "2026-05-27T00:00:00Z",
                        "description": "LLM inference engine",
                        "topics": ["llm", "python"],
                    },
                    {
                        "full_name": "owner/another-llm",
                        "stargazers_count": 1200,
                        "forks_count": 100,
                        "pushed_at": "2026-05-26T00:00:00Z",
                        "description": "Another LLM tool",
                        "topics": ["llm"],
                    },
                ],
            }
        if "topic:rag" in url:
            return {
                "total_count": 1,
                "items": [
                    {
                        "full_name": "owner/rag-framework",
                        "stargazers_count": 800,
                        "forks_count": 50,
                        "pushed_at": "2026-05-25T00:00:00Z",
                        "description": "RAG pipeline",
                        "topics": ["rag"],
                    }
                ],
            }
        return {"total_count": 0, "items": []}

    # Test 1: basic run returns correct candidates
    adapter = TopicAdapter(topics=["llm", "rag"], fetch_fn=_stub_fetch)
    candidates = adapter.run()
    if len(candidates) == 3:
        _ok("topic_adapter.basic_run_count")
    else:
        _fail("topic_adapter.basic_run_count", f"expected 3, got {len(candidates)}")

    # Test 2: all source_type == 'topic'
    if all(c.source_type == "topic" for c in candidates):
        _ok("topic_adapter.source_type_correct")
    else:
        _fail("topic_adapter.source_type_correct", "wrong source_type")

    # Test 3: dedup across topics (llm-repo appears in both, but stub only queries once)
    def _dup_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        return {
            "total_count": 1,
            "items": [
                {
                    "full_name": "shared/repo",
                    "stargazers_count": 100,
                    "forks_count": 5,
                    "pushed_at": "2026-05-27T00:00:00Z",
                    "description": "",
                    "topics": [],
                }
            ],
        }

    dup_adapter = TopicAdapter(topics=["llm", "rag", "mlx"], fetch_fn=_dup_fetch)
    dup_candidates = dup_adapter.run()
    if len(dup_candidates) == 1:
        _ok("topic_adapter.dedup_cross_topics")
    else:
        _fail("topic_adapter.dedup_cross_topics", f"expected 1 deduped, got {len(dup_candidates)}")

    # Test 4: fetch_fn override at run() call time
    call_log: list[str] = []

    def _tracking_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        call_log.append(url)
        return {"total_count": 0, "items": []}

    adapter2 = TopicAdapter(topics=["mlx"], fetch_fn=_stub_fetch)
    adapter2.run(fetch_fn=_tracking_fetch)
    if len(call_log) == 1 and "mlx" in call_log[0]:
        _ok("topic_adapter.fetch_fn_runtime_override")
    else:
        _fail("topic_adapter.fetch_fn_runtime_override", f"call_log={call_log}")

    # Test 5: HTTP 403 is silently skipped (rate limit)
    import urllib.error as _ue

    def _rate_limit_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
        raise _ue.HTTPError(url, 403, "rate limited", {}, None)  # type: ignore[arg-type]

    rl_adapter = TopicAdapter(topics=["llm"], fetch_fn=_rate_limit_fetch)
    rl_candidates = rl_adapter.run()
    if rl_candidates == []:
        _ok("topic_adapter.http_403_skipped")
    else:
        _fail("topic_adapter.http_403_skipped", "expected empty list")

    # Test 6: empty response
    empty_adapter = TopicAdapter(topics=[], fetch_fn=_stub_fetch)
    if empty_adapter.run() == []:
        _ok("topic_adapter.empty_topics_list")
    else:
        _fail("topic_adapter.empty_topics_list", "expected []")

    # Test 7: metadata fields preserved
    llm_cand = next(c for c in candidates if c.full_name == "owner/llm-repo")
    if llm_cand.metadata["stars"] == 5000 and llm_cand.metadata["query_topic"] == "llm":
        _ok("topic_adapter.metadata_fields_preserved")
    else:
        _fail("topic_adapter.metadata_fields_preserved", f"metadata={llm_cand.metadata}")

    return metrics


if __name__ == "__main__":
    m = _self_test()
    print(json.dumps(m, indent=2))
    sys.exit(0 if m["tests_run"] == m["tests_passed"] else 1)
