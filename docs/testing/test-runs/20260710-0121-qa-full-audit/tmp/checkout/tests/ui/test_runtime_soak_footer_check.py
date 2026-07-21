"""Test check_research_footer_fields in solar-runtime-soak.py.

Mocks only file IO via tmp_path; does not mock the function itself.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SOAK_PATH = Path(__file__).parent.parent.parent / "harness" / "tools" / "solar-runtime-soak.py"

FOOTER_FIELDS = [
    "Document word count",
    "Total token consumption",
    "Token usage source",
    "Token usage estimated",
]

SID = "sprint-test-footer"


def _load_soak():
    spec = importlib.util.spec_from_file_location("solar_runtime_soak", _SOAK_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestCheckResearchFooterFields:
    """check_research_footer_fields must detect all 4 required footer fields."""

    @pytest.fixture()
    def soak(self):
        return _load_soak()

    def test_all_fields_present_returns_ok(self, soak, tmp_path: Path) -> None:
        final_md = tmp_path / f"{SID}.final.md"
        content = "\n".join([
            "# Report",
            "Main content...",
            "",
            "Document word count: 1234",
            "Total token consumption: 5678",
            "Token usage source: provider_usage_ledger",
            "Token usage estimated: false",
        ])
        final_md.write_text(content, encoding="utf-8")
        with patch.object(soak, "SPRINTS", tmp_path):
            result = soak.check_research_footer_fields(SID)
        assert result["ok"] is True
        assert len(result["checks"]) == 4
        for check in result["checks"]:
            assert check["present"] is True

    def test_exact_field_text_assertion(self, soak, tmp_path: Path) -> None:
        """Verify each of the 4 exact field strings is checked individually."""
        final_md = tmp_path / f"{SID}.final.md"
        final_md.write_text("\n".join(FOOTER_FIELDS), encoding="utf-8")
        with patch.object(soak, "SPRINTS", tmp_path):
            result = soak.check_research_footer_fields(SID)
        fields_checked = {c["field"] for c in result["checks"]}
        for field in FOOTER_FIELDS:
            assert field in fields_checked, f"field not checked: {field}"

    def test_missing_field_returns_not_ok(self, soak, tmp_path: Path) -> None:
        final_md = tmp_path / f"{SID}.final.md"
        # Missing "Token usage estimated"
        final_md.write_text(
            "Document word count: 1\nTotal token consumption: 2\nToken usage source: x\n",
            encoding="utf-8",
        )
        with patch.object(soak, "SPRINTS", tmp_path):
            result = soak.check_research_footer_fields(SID)
        assert result["ok"] is False
        missing = [c for c in result["checks"] if not c["present"]]
        assert any(c["field"] == "Token usage estimated" for c in missing)

    def test_no_final_md_returns_not_ok(self, soak, tmp_path: Path) -> None:
        with patch.object(soak, "SPRINTS", tmp_path):
            result = soak.check_research_footer_fields(SID)
        assert result["ok"] is False
        assert result["files_found"] == 0

    def test_result_has_required_keys(self, soak, tmp_path: Path) -> None:
        with patch.object(soak, "SPRINTS", tmp_path):
            result = soak.check_research_footer_fields(SID)
        for key in ("sid", "checks", "ok", "files_found"):
            assert key in result, f"missing key: {key}"
