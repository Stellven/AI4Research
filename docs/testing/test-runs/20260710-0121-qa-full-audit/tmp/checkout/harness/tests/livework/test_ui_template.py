"""Tests for livework_panel.html — verify DOM IDs and source tags."""

from __future__ import annotations

from pathlib import Path

import pytest

_HTML = Path(__file__).resolve().parents[3] / "harness" / "status-server" / "templates" / "livework_panel.html"
_JS = Path(__file__).resolve().parents[3] / "harness" / "status-server" / "static" / "livework_panel.js"

EXPECTED_DOM_IDS = [
    "no-active-work-card",
    "role-next-step-card",
    "deadlock-alerts-card",
    "events-tail-card",
]


@pytest.fixture
def html_content():
    return _HTML.read_text(encoding="utf-8")


@pytest.fixture
def js_content():
    return _JS.read_text(encoding="utf-8")


class TestHTMLDomIds:
    def test_all_four_cards_present(self, html_content):
        for dom_id in EXPECTED_DOM_IDS:
            assert f'id="{dom_id}"' in html_content, f"Missing dom-id: {dom_id}"

    def test_card_class_on_each(self, html_content):
        for dom_id in EXPECTED_DOM_IDS:
            idx = html_content.index(f'id="{dom_id}"')
            line_start = html_content.rfind("\n", 0, idx) + 1
            line = html_content[line_start:idx + len(f'id="{dom_id}"') + 40]
            assert "card" in line, f"#{dom_id} missing card class"


class TestSourceTags:
    def test_source_tag_in_each_card(self, html_content):
        for dom_id in EXPECTED_DOM_IDS:
            card_start = html_content.index(f'id="{dom_id}"')
            next_card = html_content.find('<div id="', card_start + 1)
            if next_card == -1:
                next_card = html_content.index("</body>", card_start)
            card_block = html_content[card_start:next_card]
            assert "source-tag" in card_block, f"#{dom_id} missing .source-tag"

    def test_source_tag_has_content(self, html_content):
        assert "lib.livework" in html_content or "events.jsonl" in html_content


class TestJSConstraints:
    def test_js_line_count(self, js_content):
        lines = [l for l in js_content.split("\n") if l.strip() and not l.strip().startswith("//")]
        assert len(lines) <= 200, f"JS has {len(lines)} non-blank/non-comment lines"

    def test_no_framework_imports(self, js_content):
        for fw in ["react", "vue", "alpine", "lit-element"]:
            assert fw.lower() not in js_content.lower(), f"Found framework import: {fw}"

    def test_uses_fetch(self, js_content):
        assert "fetch(" in js_content, "JS must use native fetch"

    def test_s04_research_metrics_helpers_present(self, js_content):
        for marker in [
            "function formatFallbackLevel",
            "badge-fallback-",
            "function formatStateTransition",
            "requestAnimationFrame",
            "transition = \"opacity 0.4s ease, transform 0.4s ease\"",
            "function formatResearchMetrics",
            "usage_source",
            "fallback_reason",
            "fallback_level",
        ]:
            assert marker in js_content, f"Missing S04 JS marker: {marker}"


class TestEmptyState:
    def test_unknown_shown_not_blank(self, html_content):
        for dom_id in EXPECTED_DOM_IDS:
            card_start = html_content.index(f'id="{dom_id}"')
            content_start = html_content.index("card-content", card_start)
            content_end = html_content.index("</div>", content_start)
            content = html_content[content_start:content_end]
            assert "unknown" in content.lower(), f"#{dom_id} empty state not 'unknown'"
