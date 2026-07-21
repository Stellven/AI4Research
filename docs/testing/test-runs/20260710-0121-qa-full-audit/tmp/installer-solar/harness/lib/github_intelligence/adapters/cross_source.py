"""CrossSourceAdapter — extract GitHub repo links from social/YouTube text content.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C2_adapters_snapshots / adapter:cross_source

Scans a list of content blobs (tweets, HN posts, YouTube descriptions, etc.)
for github.com/<owner>/<repo> patterns and emits DiscoveryCandidate records
with source_type='social_mention' or 'youtube_mention' based on blob metadata.

fetch_fn signature:
    fetch_fn(url: str, headers: dict[str, str]) -> dict   (parsed JSON)
    — used when content is fetched from a URL rather than provided inline.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

if __package__ is None or __package__ == "":
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from schema import DiscoveryCandidate, utc_now_iso
else:
    from ..schema import DiscoveryCandidate, utc_now_iso


# Matches github.com/owner/repo — stops at whitespace, quotes, angle brackets, etc.
_GH_URL_RE = re.compile(
    r'(?:https?://)?github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.\-]+)',
    re.IGNORECASE,
)

# Exclude known non-repo GitHub paths
_SKIP_OWNERS = frozenset({
    "topics", "trending", "explore", "features", "about", "pricing",
    "enterprise", "blog", "login", "signup", "settings", "organizations",
    "orgs", "marketplace", "apps", "integrations", "contact",
    "sponsors", "security", "search", "new", "404",
})


def _extract_full_names(text: str) -> list[str]:
    """Extract unique owner/repo pairs from text."""
    seen: set[str] = set()
    results: list[str] = []
    for m in _GH_URL_RE.finditer(text):
        raw = m.group(1).rstrip(".")  # strip trailing dot from sentence punctuation
        parts = raw.split("/")
        if len(parts) < 2:
            continue
        owner, repo = parts[0], parts[1]
        # Filter trailing junk from repo name (e.g., comma or paren)
        repo = re.split(r'[,;:)>"\'\s]', repo)[0]
        if not owner or not repo:
            continue
        if owner.lower() in _SKIP_OWNERS:
            continue
        full_name = f"{owner}/{repo}"
        if full_name in seen:
            continue
        seen.add(full_name)
        results.append(full_name)
    return results


def _default_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


class CrossSourceAdapter:
    """Extract GitHub repo mentions from social/YouTube/HN content blobs.

    Content items format:
        {
            "text": "...body text with github.com links...",
            "source": "twitter" | "hackernews" | "youtube" | "reddit" | ...,
            "url": "https://...",           # optional, the post URL
            "author": "...",               # optional
            "published_at": "ISO-8601",    # optional
        }

    The source_type of emitted DiscoveryCandidate is:
        - 'youtube_mention'  when item["source"] == 'youtube'
        - 'social_mention'   otherwise
    """

    def __init__(
        self,
        content_items: list[dict[str, Any]] | None = None,
        fetch_fn: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self._static_items = content_items or []
        self._fetch = fetch_fn or _default_fetch

    def run(
        self,
        since: datetime | None = None,
        fetch_fn: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
        extra_items: list[dict[str, Any]] | None = None,
    ) -> list[DiscoveryCandidate]:
        """Scan content items for GitHub repo links.

        Args:
            since: Optional cutoff — items without published_at pass through.
            fetch_fn: Unused (accepted for parity; real use-case passes items inline).
            extra_items: Additional items to process beyond static list.
        """
        now = utc_now_iso()
        items = list(self._static_items)
        if extra_items:
            items.extend(extra_items)

        seen: set[tuple[str, str]] = set()  # (full_name, source_type)
        results: list[DiscoveryCandidate] = []

        for item in items:
            text = item.get("text") or ""
            source = (item.get("source") or "social").lower()
            source_type = "youtube_mention" if source == "youtube" else "social_mention"
            published_at = item.get("published_at")
            item_url = item.get("url") or ""
            author = item.get("author") or ""

            # Optional since filter
            if since is not None and published_at:
                try:
                    pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    if pub_dt < since:
                        continue
                except (ValueError, TypeError):
                    pass  # malformed timestamp — include anyway

            full_names = _extract_full_names(text)
            for full_name in full_names:
                dedup_key = (full_name, source_type)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                results.append(
                    DiscoveryCandidate(
                        full_name=full_name,
                        source_type=source_type,
                        discovered_at=now,
                        metadata={
                            "origin_source": source,
                            "origin_url": item_url,
                            "author": author,
                            "published_at": published_at,
                            "excerpt": text[:200],
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

    # --- Unit tests for _extract_full_names ---

    # Test 1: basic github.com URL extraction
    text1 = "Check out https://github.com/openai/tiktoken and github.com/ggerganov/llama.cpp"
    names1 = _extract_full_names(text1)
    if "openai/tiktoken" in names1 and "ggerganov/llama.cpp" in names1:
        _ok("cross_source._extract_full_names.basic")
    else:
        _fail("cross_source._extract_full_names.basic", f"got {names1}")

    # Test 2: skip known non-repo paths
    text2 = "Visit https://github.com/topics/llm and https://github.com/trending"
    names2 = _extract_full_names(text2)
    if names2 == []:
        _ok("cross_source._extract_full_names.skip_non_repos")
    else:
        _fail("cross_source._extract_full_names.skip_non_repos", f"got {names2}")

    # Test 3: trailing punctuation stripped
    text3 = "See github.com/owner/repo. And also github.com/owner/repo2,"
    names3 = _extract_full_names(text3)
    if "owner/repo" in names3 and "owner/repo2" in names3:
        _ok("cross_source._extract_full_names.trailing_punct_stripped")
    else:
        _fail("cross_source._extract_full_names.trailing_punct_stripped", f"got {names3}")

    # Test 4: dedup within same text
    text4 = "github.com/owner/repo github.com/owner/repo https://github.com/owner/repo"
    names4 = _extract_full_names(text4)
    if len(names4) == 1:
        _ok("cross_source._extract_full_names.dedup_within_text")
    else:
        _fail("cross_source._extract_full_names.dedup_within_text", f"got {names4}")

    # --- Adapter run() tests ---

    sample_items = [
        {
            "text": "Just released: https://github.com/mlc-ai/mlc-llm — fast inference!",
            "source": "twitter",
            "url": "https://twitter.com/user/status/1",
            "author": "ml_enthusiast",
            "published_at": "2026-05-27T10:00:00Z",
        },
        {
            "text": "Great video explaining github.com/huggingface/transformers",
            "source": "youtube",
            "url": "https://youtube.com/watch?v=abc",
            "author": "TechYouTuber",
            "published_at": "2026-05-27T09:00:00Z",
        },
        {
            "text": "HN discussion: github.com/mlc-ai/mlc-llm and github.com/openai/openai-python",
            "source": "hackernews",
            "published_at": "2026-05-27T08:00:00Z",
        },
    ]

    adapter = CrossSourceAdapter(content_items=sample_items)
    candidates = adapter.run()

    # Test 5: total count — 4 unique (full_name, source_type) pairs:
    # mlc-ai/mlc-llm social_mention (twitter), mlc-ai/mlc-llm social_mention (HN) -> deduped to 1
    # huggingface/transformers youtube_mention (1)
    # mlc-ai/mlc-llm social_mention (1, twitter dedup with HN)
    # openai/openai-python social_mention (1)
    # Total: 3 (mlc-ai social, huggingface youtube, openai social)
    names_and_types = [(c.full_name, c.source_type) for c in candidates]
    if ("mlc-ai/mlc-llm", "social_mention") in names_and_types:
        _ok("cross_source.adapter.social_mention_created")
    else:
        _fail("cross_source.adapter.social_mention_created", f"got {names_and_types}")

    # Test 6: youtube source → youtube_mention
    if ("huggingface/transformers", "youtube_mention") in names_and_types:
        _ok("cross_source.adapter.youtube_mention_created")
    else:
        _fail("cross_source.adapter.youtube_mention_created", f"got {names_and_types}")

    # Test 7: cross-item dedup (mlc-ai appears in twitter AND HN, same source_type)
    mlc_social = [c for c in candidates if c.full_name == "mlc-ai/mlc-llm" and c.source_type == "social_mention"]
    if len(mlc_social) == 1:
        _ok("cross_source.adapter.cross_item_dedup")
    else:
        _fail("cross_source.adapter.cross_item_dedup", f"expected 1, got {len(mlc_social)}")

    # Test 8: since filter
    since_dt = datetime(2026, 5, 27, 9, 30, 0, tzinfo=timezone.utc)
    filtered = adapter.run(since=since_dt)
    # Only twitter item (10:00) passes; youtube (09:00) and HN (08:00) are too old
    filtered_names = [c.full_name for c in filtered]
    if "mlc-ai/mlc-llm" in filtered_names and "huggingface/transformers" not in filtered_names:
        _ok("cross_source.adapter.since_filter_works")
    else:
        _fail("cross_source.adapter.since_filter_works",
              f"filtered_names={filtered_names}, expected mlc-ai only")

    # Test 9: extra_items parameter
    extra = [{"text": "github.com/pytorch/pytorch is amazing", "source": "reddit"}]
    extra_cands = adapter.run(extra_items=extra)
    extra_names = [c.full_name for c in extra_cands]
    if "pytorch/pytorch" in extra_names:
        _ok("cross_source.adapter.extra_items_processed")
    else:
        _fail("cross_source.adapter.extra_items_processed", f"extra_names={extra_names}")

    # Test 10: empty items
    empty_adapter = CrossSourceAdapter(content_items=[])
    if empty_adapter.run() == []:
        _ok("cross_source.adapter.empty_items_returns_empty")
    else:
        _fail("cross_source.adapter.empty_items_returns_empty", "expected []")

    # Test 11: metadata author and origin_url preserved
    twitter_cand = next(
        (c for c in candidates if c.full_name == "mlc-ai/mlc-llm" and c.source_type == "social_mention"),
        None,
    )
    if twitter_cand and twitter_cand.metadata.get("author") == "ml_enthusiast":
        _ok("cross_source.adapter.metadata_author_preserved")
    else:
        _fail("cross_source.adapter.metadata_author_preserved",
              f"metadata={twitter_cand.metadata if twitter_cand else None}")

    return metrics


if __name__ == "__main__":
    m = _self_test()
    print(json.dumps(m, indent=2))
    sys.exit(0 if m["tests_run"] == m["tests_passed"] else 1)
