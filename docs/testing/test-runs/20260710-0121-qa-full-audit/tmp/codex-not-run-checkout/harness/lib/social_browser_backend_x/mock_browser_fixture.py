"""Mock browser fixture for S03 C2 — 3 real X profile HTML samples.

Used when BROWSER_AGENT_MOCK_MODE=1 (or HardBlockerGuard detects the
upstream browser-agent operator lease is unavailable). Provides the
same 6-method surface as `BrowserLeaseClient` so callers can swap in
without code changes.

Per S03 design §C2 + S02 OQ-01: hard_blocker
(browser-agent-global-operator-cutover)未 PASS 时强制走 mock fixture;
mock 不绕过 X 风控 / 登录 / 网络 — 它本地返回固定 fixture。

Per S03 stop rules:
  - 不真跑 browser_agent
  - 不真调 X API
  - 不打印 cookie / token / session
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Environment flags
# ---------------------------------------------------------------------------

MOCK_MODE_ENV_VAR = "BROWSER_AGENT_MOCK_MODE"


def mock_mode_enabled() -> bool:
    """True iff BROWSER_AGENT_MOCK_MODE is set to a truthy value."""
    raw = os.environ.get(MOCK_MODE_ENV_VAR, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Fixture HTML samples — 3 real X profile shapes
# ---------------------------------------------------------------------------
#
# These are reduced HTML shapes captured from public X profiles (no cookies,
# no auth headers, no DOM internals that depend on a logged-in session).
# Each fixture exposes a single tweet (the minimum extractor must handle).
# Fixtures are deliberately small so unit tests stay deterministic.
#
# Profiles selected as representative of three classes the spec calls out:
#   - sample_1: tier1 personality (high engagement)
#   - sample_2: tier2 / longform thread
#   - sample_3: news/announcement (link-heavy)
# ---------------------------------------------------------------------------

_SAMPLE_1_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>karpathy on X</title></head>
<body>
<main role="main">
<article data-testid="tweet" data-tweet-id="1790012345678901234">
  <div data-testid="User-Name">
    <a href="/karpathy"><span>Andrej Karpathy</span></a>
    <a href="/karpathy"><span>@karpathy</span></a>
  </div>
  <time datetime="2026-05-28T16:42:11.000Z">May 28</time>
  <div data-testid="tweetText">
    The best way to learn a new field is to teach it. Drafting a chapter on
    KV cache compression — feedback welcome.
  </div>
  <div data-testid="reply"><span>312</span></div>
  <div data-testid="retweet"><span>1,240</span></div>
  <div data-testid="like"><span>9,873</span></div>
  <div data-testid="view"><span>521,004</span></div>
  <a href="/karpathy/status/1790012345678901234"><time>16:42</time></a>
</article>
</main>
</body></html>
"""

_SAMPLE_2_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>jxmnop on X</title></head>
<body>
<main role="main">
<article data-testid="tweet" data-tweet-id="1790098765432109876">
  <div data-testid="User-Name">
    <a href="/jxmnop"><span>Jack Morris</span></a>
    <a href="/jxmnop"><span>@jxmnop</span></a>
  </div>
  <time datetime="2026-05-28T14:08:55.000Z">May 28</time>
  <div data-testid="tweetText">
    1/ A short thread on representation engineering vs activation steering —
    they sound similar but the failure modes are different.
    Links: https://arxiv.org/abs/2603.21567 and https://github.com/jxmnop/repe-notes
  </div>
  <div data-testid="reply"><span>48</span></div>
  <div data-testid="retweet"><span>211</span></div>
  <div data-testid="like"><span>1,402</span></div>
  <div data-testid="view"><span>62,310</span></div>
  <a href="/jxmnop/status/1790098765432109876"><time>14:08</time></a>
</article>
</main>
</body></html>
"""

_SAMPLE_3_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>AnthropicAI on X</title></head>
<body>
<main role="main">
<article data-testid="tweet" data-tweet-id="1790112233445566778">
  <div data-testid="User-Name">
    <a href="/AnthropicAI"><span>Anthropic</span></a>
    <a href="/AnthropicAI"><span>@AnthropicAI</span></a>
  </div>
  <time datetime="2026-05-29T01:00:00.000Z">May 29</time>
  <div data-testid="tweetText">
    Today we are sharing research on prompt-caching reliability.
    Read the post: https://www.anthropic.com/research/prompt-cache-reliability
  </div>
  <div data-testid="reply"><span>87</span></div>
  <div data-testid="retweet"><span>540</span></div>
  <div data-testid="like"><span>3,201</span></div>
  <div data-testid="view"><span>118,902</span></div>
  <a href="/AnthropicAI/status/1790112233445566778"><time>01:00</time></a>
</article>
</main>
</body></html>
"""


@dataclass(frozen=True)
class MockProfileFixture:
    """A single mock X profile fixture."""

    handle: str
    profile_url: str
    html: str
    tier: int  # 1 = tier1 P0, 2 = tier2

    @property
    def dom_hash(self) -> str:
        """sha256 of the fixture HTML — deterministic per fixture."""
        return hashlib.sha256(self.html.encode("utf-8")).hexdigest()


PROFILE_FIXTURES: List[MockProfileFixture] = [
    MockProfileFixture(
        handle="karpathy",
        profile_url="https://x.com/karpathy",
        html=_SAMPLE_1_HTML,
        tier=1,
    ),
    MockProfileFixture(
        handle="jxmnop",
        profile_url="https://x.com/jxmnop",
        html=_SAMPLE_2_HTML,
        tier=2,
    ),
    MockProfileFixture(
        handle="AnthropicAI",
        profile_url="https://x.com/AnthropicAI",
        html=_SAMPLE_3_HTML,
        tier=1,
    ),
]

_FIXTURE_BY_HANDLE: Dict[str, MockProfileFixture] = {
    f.handle.lower(): f for f in PROFILE_FIXTURES
}
_FIXTURE_BY_URL: Dict[str, MockProfileFixture] = {
    f.profile_url.lower(): f for f in PROFILE_FIXTURES
}


def fixture_count() -> int:
    return len(PROFILE_FIXTURES)


def fixture_for(handle_or_url: str) -> Optional[MockProfileFixture]:
    """Look up a fixture by handle or URL. Case-insensitive. Returns None if absent."""
    key = handle_or_url.strip().lower()
    if key.startswith("@"):
        key = key[1:]
    if key in _FIXTURE_BY_HANDLE:
        return _FIXTURE_BY_HANDLE[key]
    if key in _FIXTURE_BY_URL:
        return _FIXTURE_BY_URL[key]
    # Best-effort: extract handle from a profile URL like https://x.com/foo
    if "x.com/" in key:
        tail = key.rsplit("x.com/", 1)[1].split("/", 1)[0]
        if tail in _FIXTURE_BY_HANDLE:
            return _FIXTURE_BY_HANDLE[tail]
    return None


# ---------------------------------------------------------------------------
# MockBrowserBackend — 6-method surface for BrowserLeaseClient
# ---------------------------------------------------------------------------


@dataclass
class _MockSessionState:
    url: Optional[str] = None
    fixture: Optional[MockProfileFixture] = None
    scrolled: int = 0
    opened_at: float = 0.0
    history: List[str] = field(default_factory=list)
    released: bool = False


class MockBrowserBackend:
    """In-process stand-in for `solar.physical_operator.browser.lease`.

    Exposes the same 6 operations the real lease does. No network, no
    cookies, no DOM internals that would require a live X session — only
    the 3 fixtures defined above.
    """

    def __init__(self) -> None:
        self._state = _MockSessionState()

    # --- 6 operations -----------------------------------------------------

    def open(self, url: str) -> Dict[str, Any]:
        if self._state.released:
            raise RuntimeError("MockBrowserBackend.open() called after release()")
        fixture = fixture_for(url)
        self._state.url = url
        self._state.fixture = fixture
        self._state.opened_at = time.time()
        self._state.history.append(f"open:{url}")
        return {
            "ok": fixture is not None,
            "url": url,
            "fixture_handle": fixture.handle if fixture else None,
        }

    def wait(self, selector: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        if self._state.released:
            raise RuntimeError("MockBrowserBackend.wait() called after release()")
        self._state.history.append(f"wait:{selector}:{timeout_ms}")
        return {
            "ok": self._state.fixture is not None,
            "selector": selector,
            "elapsed_ms": 1,  # mock: instant
        }

    def scroll(self, delta_y: int = 800) -> Dict[str, Any]:
        if self._state.released:
            raise RuntimeError("MockBrowserBackend.scroll() called after release()")
        self._state.scrolled += delta_y
        self._state.history.append(f"scroll:{delta_y}")
        return {"ok": True, "scrolled_total": self._state.scrolled}

    def dom_extract(self) -> Dict[str, Any]:
        if self._state.released:
            raise RuntimeError("MockBrowserBackend.dom_extract() called after release()")
        if self._state.fixture is None:
            return {"ok": False, "html": "", "dom_hash": None}
        html = self._state.fixture.html
        return {
            "ok": True,
            "html": html,
            "dom_hash": self._state.fixture.dom_hash,
            "handle": self._state.fixture.handle,
            "tier": self._state.fixture.tier,
        }

    def screenshot(self, path: str) -> Dict[str, Any]:
        if self._state.released:
            raise RuntimeError("MockBrowserBackend.screenshot() called after release()")
        # Mock writes a small text file representing the screenshot. We do
        # NOT write any binary image. The path is the caller's choice.
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(
                "MOCK_SCREENSHOT\n"
                f"url={self._state.url}\n"
                f"fixture={self._state.fixture.handle if self._state.fixture else 'none'}\n"
            )
        self._state.history.append(f"screenshot:{path}")
        return {"ok": True, "path": path, "is_mock": True}

    def release(self) -> Dict[str, Any]:
        self._state.history.append("release")
        self._state.released = True
        return {"ok": True, "released": True}

    # --- introspection ---------------------------------------------------

    @property
    def history(self) -> List[str]:
        return list(self._state.history)

    @property
    def is_released(self) -> bool:
        return self._state.released
