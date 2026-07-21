from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "browser_agent_gemini_deep_research_wrapper.py"


def _install_dependency_stubs() -> None:
    browser_use = types.ModuleType("browser_use")
    browser_use_browser = types.ModuleType("browser_use.browser")
    browser_use_profile = types.ModuleType("browser_use.browser.profile")
    browser_use_session = types.ModuleType("browser_use.browser.session")
    playwright_async_api = types.ModuleType("playwright.async_api")

    class _BrowserProfile:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _BrowserSession:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    async def _async_playwright():
        raise RuntimeError("async_playwright stub should not be used in these tests")

    browser_use_profile.BrowserProfile = _BrowserProfile
    browser_use_session.BrowserSession = _BrowserSession
    playwright_async_api.async_playwright = _async_playwright

    sys.modules.setdefault("browser_use", browser_use)
    sys.modules.setdefault("browser_use.browser", browser_use_browser)
    sys.modules.setdefault("browser_use.browser.profile", browser_use_profile)
    sys.modules.setdefault("browser_use.browser.session", browser_use_session)
    sys.modules.setdefault("playwright.async_api", playwright_async_api)


_install_dependency_stubs()
SPEC = importlib.util.spec_from_file_location("browser_agent_gemini_deep_research_wrapper", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_deep_search_report_signals_match_real_output_shape():
    text = """
    1. Executive Landscape Synthesis (For Reference Only)
    Core Technical Architectures
    Major Engineering Bottlenecks
    2. Categorized Literature & Link Directory (Primary Deliverable)
    Category A: Peer-Reviewed Papers & Preprints (arXiv/Conferences)
    Direct Verified URL Link: https://example.com/paper
    Category B: Technical Blogs, Engineering Post-Mortems & Industry Analyses
    Category C: Official Documentation & Open-Source Repository Ecosystems
    """.strip()
    signals = MODULE._deep_research_report_signals(
        text,
        citations=[{"title": "A", "url": "https://example.com"} for _ in range(6)],
    )
    assert signals["has_executive_overview"] is True
    assert signals["has_background_analysis"] is True
    assert signals["has_literature_repository"] is True
    assert signals["has_disclaimer"] is True
    assert signals["has_categorized_sections"] is True
    assert signals["citation_count_ge_5"] is True
    assert signals["matched_count"] >= 5


def test_deep_search_report_signals_match_operator_style_chinese_output():
    text = """
    注：以下前半部分的执行结论与综合分析仅供参考，核心交付物为后半部分的高质量分类文献与链接库。
    核心执行结论 (仅供参考)
    📚 高质量分类文献与链接库 (Categorized Literature and Link Registry)
    1. 核心研究论文 (Research Papers)
    2. 基准测试与数据集 (Benchmarks)
    3. 开源框架与自动化工具 (Frameworks & Tools)
    4. 官方技术文档 (Official Docs)
    5. 行业分析与落地实践 (Industry Analyses)
    """.strip()
    signals = MODULE._deep_research_report_signals(
        text,
        citations=[{"title": "A", "url": "https://example.com"} for _ in range(8)],
    )
    assert signals["has_executive_overview"] is True
    assert signals["has_literature_repository"] is True
    assert signals["has_disclaimer"] is True
    assert signals["has_categorized_sections"] is True
    assert signals["citation_count_ge_5"] is True
    assert signals["matched_count"] >= 5


def test_mode_evidence_strength_gate_rejects_below_threshold():
    try:
        MODULE._assert_mode_evidence_strength("medium", minimum="strong")
    except RuntimeError as exc:
        assert "gemini_deep_search_mode_evidence_below_threshold" in str(exc)
    else:
        raise AssertionError("expected mode evidence gate to reject medium < strong")


def test_mode_evidence_strength_gate_accepts_strong():
    MODULE._assert_mode_evidence_strength("strong", minimum="strong")


def test_extract_mode_label_from_selector_aria_label():
    raw = '打开模式选择器，当前模式为“Gemini Flash-Lite”'
    assert MODULE._extract_mode_label(raw) == "Gemini Flash-Lite"
    assert MODULE._mode_label_is_flash_lite("Gemini Flash-Lite") is True
    assert MODULE._mode_label_is_flash_lite("Gemini 2.5 Pro") is False


def test_parse_optimized_prompt_prefers_plaintext_block():
    raw = """
    **Your Optimized Prompt:**
    [Prompt content...]
    Plaintext
    # ROLE
    You are an elite Academic Researcher and the Gemini Deep Research engine.
    # CORE DIRECTIVE
    Conduct a massive deep dive and output categorized links at the end.
    Key Improvements:
    - x
    """.strip()
    parsed = MODULE.parse_optimized_prompt(raw)
    assert parsed.startswith("# ROLE")


def test_optimized_prompt_usable_rejects_placeholder():
    assert MODULE._optimized_prompt_usable("**\\n[Prompt content...]") is False
    assert MODULE._optimized_prompt_usable("# ROLE\\n" + ("A" * 240)) is True


def test_build_deep_search_fallback_prompt_is_source_first():
    prompt = MODULE._build_deep_search_fallback_prompt("AI agent 浏览器自动化")
    assert "source-first research engine" in prompt
    assert "categorized literature and link registry" in prompt.lower()
    assert "working URL" in prompt
