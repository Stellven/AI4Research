"""Test ResearchPanel widget rendering in core/ui/dashboard.ts (via Python stub).

Tests the research.html template rendering and the fallback badge logic.
Mocks only HTTP (urllib/fetch); does not mock ResearchPanel internals.
"""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

# Test the Python-side: research.html template contains correct markers and fields
_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent
    / "harness" / "status-server" / "templates" / "research.html"
)

_ROUTES_PATH = Path(__file__).parent.parent.parent / "harness" / "status-server" / "research_routes.py"
_SPEC = importlib.util.spec_from_file_location("research_routes_s04_render", _ROUTES_PATH)
_MOD = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MOD)
build_research_payload = _MOD.build_research_payload


class TestResearchHtmlTemplate:
    """research.html must contain all 3 S04 marker comments and 4 footer fields."""

    @pytest.fixture()
    def template_content(self) -> str:
        return _TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_s04_footer_marker(self, template_content: str) -> None:
        assert "S04-FOOTER" in template_content

    def test_s04_statemachine_marker(self, template_content: str) -> None:
        assert "S04-STATEMACHINE" in template_content

    def test_s04_fallback_badge_marker(self, template_content: str) -> None:
        assert "S04-FALLBACK-BADGE" in template_content

    def test_footer_four_fields_present(self, template_content: str) -> None:
        for field in [
            "Document word count",
            "Total token consumption",
            "Token usage source",
            "Token usage estimated",
        ]:
            assert field in template_content, f"template missing field: {field}"

    def test_existing_content_intact(self, template_content: str) -> None:
        assert "source_count" in template_content or "Sources" in template_content
        assert "{sid}" in template_content


class TestResearchPayloadFallbackBadge:
    """build_research_payload fallback_level drives badge class in template."""

    def test_l1_badge_data(self, tmp_path: Path) -> None:
        (tmp_path / "sprint-x.research_execution_metrics.json").write_text(
            json.dumps({"usage_source": "provider_usage_ledger", "estimated": False}),
            encoding="utf-8",
        )
        payload = build_research_payload(tmp_path, "sprint-x")
        assert payload["fallback_level"] == "L1"

    def test_l2_badge_data(self, tmp_path: Path) -> None:
        (tmp_path / "sprint-x.research_execution_metrics.json").write_text(
            json.dumps({"usage_source": "hybrid", "estimated": True}),
            encoding="utf-8",
        )
        payload = build_research_payload(tmp_path, "sprint-x")
        assert payload["fallback_level"] == "L2"

    def test_null_fallback_when_no_metrics(self, tmp_path: Path) -> None:
        payload = build_research_payload(tmp_path, "sprint-no-metrics")
        assert payload["fallback_level"] is None

    def test_state_field_in_payload(self, tmp_path: Path) -> None:
        (tmp_path / "sprint-x.research_execution_metrics.json").write_text(
            json.dumps({"usage_source": "hybrid", "state": "running"}),
            encoding="utf-8",
        )
        payload = build_research_payload(tmp_path, "sprint-x")
        assert payload["state"] == "running"

    def test_footer_metric_values_in_payload(self, tmp_path: Path) -> None:
        (tmp_path / "sprint-x.research_execution_metrics.json").write_text(
            json.dumps({"document_word_count": 321, "total_token_consumption": 654}),
            encoding="utf-8",
        )
        payload = build_research_payload(tmp_path, "sprint-x")
        assert payload["word_count"] == 321
        assert payload["total_tokens"] == 654
