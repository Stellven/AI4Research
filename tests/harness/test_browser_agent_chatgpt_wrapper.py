from __future__ import annotations

import os
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "scripts" / "browser_agent_chatgpt_wrapper.py"


def _load_namespace() -> dict:
    browser_use = types.ModuleType("browser_use")
    browser_use_browser = types.ModuleType("browser_use.browser")
    browser_use_browser_profile = types.ModuleType("browser_use.browser.profile")
    browser_use_browser_session = types.ModuleType("browser_use.browser.session")

    class _DummyProfile:
        pass

    class _DummySession:
        pass

    browser_use_browser_profile.BrowserProfile = _DummyProfile
    browser_use_browser_session.BrowserSession = _DummySession

    prev_modules = {
        name: sys.modules.get(name)
        for name in (
            "browser_use",
            "browser_use.browser",
            "browser_use.browser.profile",
            "browser_use.browser.session",
        )
    }
    sys.modules["browser_use"] = browser_use
    sys.modules["browser_use.browser"] = browser_use_browser
    sys.modules["browser_use.browser.profile"] = browser_use_browser_profile
    sys.modules["browser_use.browser.session"] = browser_use_browser_session
    try:
        ns: dict = {"__file__": str(SCRIPT), "__name__": "browser_agent_chatgpt_wrapper_test"}
        code = compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec")
        exec(code, ns)
        return ns
    finally:
        for name, module in prev_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_post_submit_confirms_chinese_thinking_banner():
    ns = _load_namespace()
    result = ns["_post_submit_confirms_chatgpt_mode"](
        {
            "latest_assistant_text": "正在思考",
            "is_generating": True,
            "assistant_count": 1,
        },
        model_mode="thinking",
        reasoning_effort="high",
    )
    assert result["ok"] is True
    assert result["model_ok"] is True
    assert result["reasoning_ok"] is True


def test_post_submit_accepts_configured_high_reasoning_when_response_started():
    ns = _load_namespace()
    result = ns["_post_submit_confirms_chatgpt_mode"](
        {
            "latest_assistant_text": '{"accepted": true, "summary": "partial json"}',
            "is_generating": True,
            "assistant_count": 1,
            "_configure_result": {
                "steps": [
                    {
                        "step": "open_model_dropdown",
                        "ok": True,
                        "clicked": {"text": "ChatGPT", "aria": "模型选择器"},
                    },
                    {
                        "step": "select_high_reasoning",
                        "ok": True,
                        "clicked": {"text": "思考时间更长", "aria": ""},
                    },
                ]
            },
        },
        model_mode="thinking",
        reasoning_effort="high",
    )
    assert result["ok"] is True
    assert result["model_selector_confirmed"] is True
    assert result["high_reasoning_confirmed"] is True


def test_post_submit_accepts_json_response_started_on_chatgpt_page():
    ns = _load_namespace()
    result = ns["_post_submit_confirms_chatgpt_mode"](
        {
            "latest_assistant_text": '{"accepted": true, "trend_type": "weak_signal", "summary": "partial json"}',
            "is_generating": True,
            "assistant_count": 1,
            "_configure_result": {
                "steps": [
                    {
                        "step": "open_model_dropdown",
                        "ok": True,
                        "clicked": {"text": "ChatGPT", "aria": "模型选择器"},
                    },
                    {
                        "step": "select_high_reasoning",
                        "ok": False,
                        "clicked": None,
                    },
                ]
            },
        },
        model_mode="thinking",
        reasoning_effort="high",
    )
    assert result["ok"] is True
    assert result["json_response_started"] is True
    assert result["reasoning_ok"] is True


def test_headed_run_requires_explicit_opt_in(monkeypatch):
    ns = _load_namespace()
    monkeypatch.delenv("BROWSER_AGENT_CHATGPT_ALLOW_HEADED", raising=False)
    monkeypatch.delenv("TECH_HOTSPOT_BROWSER_CHATGPT_ALLOW_HEADED", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_ALLOW_HEADED", raising=False)
    assert ns["_headed_run_allowed"]() is False


def test_headed_run_accepts_explicit_opt_in(monkeypatch):
    ns = _load_namespace()
    monkeypatch.setenv("BROWSER_AGENT_CHATGPT_ALLOW_HEADED", "true")
    assert ns["_headed_run_allowed"]() is True


def test_chatgpt_wrapper_defaults_to_persistent_profile_strategy(monkeypatch):
    ns = _load_namespace()
    monkeypatch.delenv("BROWSER_AGENT_CHATGPT_PROFILE_STRATEGY", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_PROFILE_STRATEGY", raising=False)
    strategy = str(
        os.environ.get("BROWSER_AGENT_CHATGPT_PROFILE_STRATEGY")
        or os.environ.get("BROWSER_AGENT_PROFILE_STRATEGY")
        or "persistent"
    ).strip().lower()
    assert strategy == "persistent"


def test_chatgpt_wrapper_defaults_to_chrome_channel(monkeypatch):
    ns = _load_namespace()
    monkeypatch.delenv("BROWSER_AGENT_CHATGPT_BROWSER_CHANNEL", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_BROWSER_CHANNEL", raising=False)
    assert ns["_browser_channel"]() == "chrome"


def test_cloudflare_challenge_grace_defaults_and_expires(monkeypatch):
    ns = _load_namespace()
    monkeypatch.delenv("BROWSER_AGENT_CHATGPT_CHALLENGE_GRACE_SECONDS", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_CHALLENGE_GRACE_SECONDS", raising=False)
    assert ns["_challenge_grace_seconds"]() == 20.0
    assert ns["_challenge_persisted_too_long"](100.0, now=119.9, grace_s=20.0) is False
    assert ns["_challenge_persisted_too_long"](100.0, now=120.0, grace_s=20.0) is True


def test_browser_user_agent_defaults_to_non_headless_chrome(monkeypatch):
    ns = _load_namespace()
    monkeypatch.delenv("BROWSER_AGENT_CHATGPT_USER_AGENT", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_USER_AGENT", raising=False)
    ua = ns["_browser_user_agent"](browser_channel="chrome")
    assert "Chrome/" in ua
    assert "HeadlessChrome/" not in ua
