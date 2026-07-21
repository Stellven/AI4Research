"""TrendingAdapter — discover repos by scraping GitHub Trending page.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C2_adapters_snapshots / adapter:trending

Source:  https://github.com/trending?since=daily (HTML scrape)
         Also supports: since=weekly, since=monthly

fetch_fn signature:
    fetch_fn(url: str, headers: dict[str, str]) -> bytes  (raw HTML bytes)
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


_BASE_URL = "https://github.com/trending"

# Pattern to extract repo slugs from trending page article tags.
# GitHub trending page has hrefs like /owner/repo in <h2> anchors.
_REPO_HREF_RE = re.compile(
    r'<h2[^>]*>\s*<a\s+href="(/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+))"',
    re.IGNORECASE,
)
# Stars (current period) shown as "X stars today/this week/this month"
_STARS_TODAY_RE = re.compile(
    r'([\d,]+)\s+stars?\s+(?:today|this week|this month)',
    re.IGNORECASE,
)
# Total stars in star count span
_TOTAL_STARS_RE = re.compile(
    r'<span[^>]*>\s*([\d,]+)\s*</span>',
    re.IGNORECASE,
)


def _default_fetch(url: str, headers: dict[str, str]) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def _parse_int(s: str | None) -> int | None:
    if s is None:
        return None
    cleaned = s.replace(",", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return None


def _extract_repos_from_html(html: str) -> list[dict[str, Any]]:
    """Parse GitHub trending page HTML into a list of repo dicts."""
    repos: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Split into article blocks — each article corresponds to one trending repo.
    # GitHub uses <article class="Box-row"> for each entry.
    article_blocks = re.split(r'<article\b[^>]*>', html, flags=re.IGNORECASE)

    for rank, block in enumerate(article_blocks[1:], start=1):  # skip preamble
        # Extract full_name from the first h2/h3 anchor in the block
        href_match = _REPO_HREF_RE.search(block)
        if not href_match:
            continue
        full_name = href_match.group(2).strip("/")
        # Normalize: remove leading slash artifacts
        parts = full_name.strip("/").split("/")
        if len(parts) != 2:
            continue
        owner, repo_name = parts
        # Skip org/profile pages that sneak in
        if not owner or not repo_name:
            continue
        if full_name in seen:
            continue
        seen.add(full_name)

        # Stars added in this period
        period_stars_match = _STARS_TODAY_RE.search(block)
        period_stars = _parse_int(period_stars_match.group(1)) if period_stars_match else None

        repos.append(
            {
                "full_name": full_name,
                "rank": rank,
                "period_stars": period_stars,
            }
        )

    return repos


class TrendingAdapter:
    """Discover repos from GitHub Trending page via HTML scraping."""

    source_type = "trending"

    def __init__(
        self,
        since: str = "daily",  # daily | weekly | monthly
        languages: list[str] | None = None,
        fetch_fn: Callable[[str, dict[str, str]], bytes] | None = None,
    ) -> None:
        self.since = since
        self.languages = languages or [None]  # type: ignore[list-item]
        self._fetch = fetch_fn or _default_fetch

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def _build_url(self, language: str | None) -> str:
        url = f"{_BASE_URL}?since={self.since}"
        if language:
            url += f"&spoken_language_code=&l={urllib.request.quote(language)}"
        return url

    def run(
        self,
        since: datetime | None = None,
        fetch_fn: Callable[[str, dict[str, str]], bytes] | None = None,
    ) -> list[DiscoveryCandidate]:
        """Scrape trending page(s) and return DiscoveryCandidate list.

        Args:
            since: Unused (trending has no incremental timestamp); kept for interface parity.
            fetch_fn: Optional override, replaces instance fetch_fn.
        """
        fn = fetch_fn or self._fetch
        now = utc_now_iso()
        seen: set[str] = set()
        results: list[DiscoveryCandidate] = []

        for lang in self.languages:
            url = self._build_url(lang)
            try:
                raw = fn(url, self._headers())
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429, 503):
                    continue
                raise
            except Exception:
                continue

            html = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
            repos = _extract_repos_from_html(html)

            for repo_info in repos:
                full_name: str = repo_info["full_name"]
                if full_name in seen:
                    continue
                seen.add(full_name)
                results.append(
                    DiscoveryCandidate(
                        full_name=full_name,
                        source_type=self.source_type,
                        discovered_at=now,
                        metadata={
                            "since": self.since,
                            "rank": repo_info["rank"],
                            "period_stars": repo_info.get("period_stars"),
                            "language": lang,
                        },
                    )
                )

        return results


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_STUB_HTML = """\
<!DOCTYPE html>
<html>
<body>
<article class="Box-row">
  <h2 class="h3">
    <a href="/openai/tiktoken">openai / tiktoken</a>
  </h2>
  <span class="d-inline-block float-sm-right">
    <a href="/openai/tiktoken/stargazers">
      <svg>...</svg>
      1,234
    </a>
  </span>
  <p>1,200 stars today</p>
</article>
<article class="Box-row">
  <h2 class="h3">
    <a href="/ggerganov/llama.cpp">ggerganov / llama.cpp</a>
  </h2>
  <span class="d-inline-block float-sm-right">
    <svg>...</svg>
    55,000
  </span>
  <p>300 stars today</p>
</article>
<article class="Box-row">
  <h2 class="h3">
    <a href="/mlc-ai/mlc-llm">mlc-ai / mlc-llm</a>
  </h2>
  <p>50 stars today</p>
</article>
</body>
</html>
"""


def _self_test() -> dict[str, Any]:
    metrics: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "details": []}

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["details"].append({"test": name, "status": "pass"})

    def _fail(name: str, reason: str) -> None:
        metrics["tests_run"] += 1
        metrics["details"].append({"test": name, "status": "fail", "reason": reason})

    # Stub returns known HTML
    def _stub_fetch(url: str, headers: dict[str, str]) -> bytes:
        return _STUB_HTML.encode("utf-8")

    # Test 1: parse 3 repos from stub HTML
    adapter = TrendingAdapter(since="daily", fetch_fn=_stub_fetch)
    candidates = adapter.run()
    if len(candidates) == 3:
        _ok("trending_adapter.parse_3_repos")
    else:
        _fail("trending_adapter.parse_3_repos", f"expected 3, got {len(candidates)}: {[c.full_name for c in candidates]}")

    # Test 2: source_type == 'trending'
    if all(c.source_type == "trending" for c in candidates):
        _ok("trending_adapter.source_type_correct")
    else:
        _fail("trending_adapter.source_type_correct", "wrong source_type")

    # Test 3: rank order preserved
    names = [c.full_name for c in candidates]
    if names[0] == "openai/tiktoken" and names[1] == "ggerganov/llama.cpp":
        _ok("trending_adapter.rank_order_preserved")
    else:
        _fail("trending_adapter.rank_order_preserved", f"order={names}")

    # Test 4: period_stars extracted for repo 1
    cand0 = candidates[0]
    if cand0.metadata.get("period_stars") == 1200:
        _ok("trending_adapter.period_stars_extracted")
    else:
        _fail("trending_adapter.period_stars_extracted",
              f"period_stars={cand0.metadata.get('period_stars')}")

    # Test 5: dedup when multiple languages overlap
    def _same_repo_fetch(url: str, headers: dict[str, str]) -> bytes:
        return _STUB_HTML.encode("utf-8")

    dedup_adapter = TrendingAdapter(
        since="daily", languages=["python", "go"], fetch_fn=_same_repo_fetch
    )
    dedup_cands = dedup_adapter.run()
    # 3 repos * 2 languages but deduped = still 3
    if len(dedup_cands) == 3:
        _ok("trending_adapter.dedup_across_languages")
    else:
        _fail("trending_adapter.dedup_across_languages", f"expected 3, got {len(dedup_cands)}")

    # Test 6: 503 error is silently skipped
    import urllib.error as _ue

    def _503_fetch(url: str, headers: dict[str, str]) -> bytes:
        raise _ue.HTTPError(url, 503, "service unavailable", {}, None)  # type: ignore[arg-type]

    err_adapter = TrendingAdapter(since="daily", fetch_fn=_503_fetch)
    err_candidates = err_adapter.run()
    if err_candidates == []:
        _ok("trending_adapter.http_503_skipped")
    else:
        _fail("trending_adapter.http_503_skipped", "expected empty list")

    # Test 7: empty HTML
    def _empty_fetch(url: str, headers: dict[str, str]) -> bytes:
        return b"<html><body></body></html>"

    empty_adapter = TrendingAdapter(since="daily", fetch_fn=_empty_fetch)
    if empty_adapter.run() == []:
        _ok("trending_adapter.empty_html_returns_empty")
    else:
        _fail("trending_adapter.empty_html_returns_empty", "expected []")

    # Test 8: runtime fetch_fn override
    call_log: list[str] = []

    def _tracking_fetch(url: str, headers: dict[str, str]) -> bytes:
        call_log.append(url)
        return b"<html><body></body></html>"

    adapter2 = TrendingAdapter(since="weekly", fetch_fn=_stub_fetch)
    adapter2.run(fetch_fn=_tracking_fetch)
    if len(call_log) == 1 and "weekly" in call_log[0]:
        _ok("trending_adapter.fetch_fn_runtime_override")
    else:
        _fail("trending_adapter.fetch_fn_runtime_override", f"call_log={call_log}")

    return metrics


if __name__ == "__main__":
    m = _self_test()
    print(json.dumps(m, indent=2))
    sys.exit(0 if m["tests_run"] == m["tests_passed"] else 1)
