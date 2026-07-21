from __future__ import annotations

import types
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

browser_use = types.ModuleType("browser_use")
browser_use_browser = types.ModuleType("browser_use.browser")
browser_use_profile = types.ModuleType("browser_use.browser.profile")
browser_use_session = types.ModuleType("browser_use.browser.session")
browser_use_profile.BrowserProfile = object
browser_use_session.BrowserSession = object
sys.modules.setdefault("browser_use", browser_use)
sys.modules.setdefault("browser_use.browser", browser_use_browser)
sys.modules.setdefault("browser_use.browser.profile", browser_use_profile)
sys.modules.setdefault("browser_use.browser.session", browser_use_session)

playwright = types.ModuleType("playwright")
playwright_async_api = types.ModuleType("playwright.async_api")
playwright_async_api.async_playwright = object
sys.modules.setdefault("playwright", playwright)
sys.modules.setdefault("playwright.async_api", playwright_async_api)

import browser_agent_youtube_transcript_wrapper as yt_wrapper


def test_normalize_youtube_watch_url_from_shorts():
    url = "https://www.youtube.com/shorts/wZmn9slGfmw"
    assert yt_wrapper._normalize_youtube_watch_url(url) == "https://www.youtube.com/watch?v=wZmn9slGfmw"


def test_normalize_youtube_watch_url_preserves_watch_id():
    url = "https://www.youtube.com/watch?v=LMbeDEQO6QM&t=10s"
    assert yt_wrapper._normalize_youtube_watch_url(url) == "https://www.youtube.com/watch?v=LMbeDEQO6QM"
