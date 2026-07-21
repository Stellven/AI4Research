"""
test_prompt_injector — Verify dispatch_prompt_injector research rule injection.

Test integrity: no @mock.patch, all tests use real injection logic.
"""

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

# Module under test
sys_path_hint = str(Path(__file__).resolve().parent.parent.parent / "lib")
import sys

if sys_path_hint not in sys.path:
    sys.path.insert(0, sys_path_hint)

from dispatch_prompt_injector import (
    RESEARCH_RULES,
    inject_file,
    inject_research_rules,
    verify_rules_present,
)


class TestInjectResearchRules:
    """Unit tests for inject_research_rules(text, node_id) -> str."""

    def test_research_node_gets_rules_appended(self):
        text = "## Build the thing\nDo the work."
        result = inject_research_rules(text, "R4_claim_mining")
        assert "## Build the thing" in result
        assert "research-hard-rules" in result

    def test_non_research_node_unchanged(self):
        text = "## Build the thing\nDo the work."
        result = inject_research_rules(text, "N5")
        assert result is text

    def test_empty_node_id_unchanged(self):
        text = "hello"
        result = inject_research_rules(text, "")
        assert result is text

    def test_none_node_id_unchanged(self):
        text = "hello"
        result = inject_research_rules(text, None or "")
        assert result is text

    def test_idempotent_double_injection(self):
        text = "Original"
        first = inject_research_rules(text, "R1")
        second = inject_research_rules(first, "R1")
        assert first == second
        assert second.count("research-hard-rules") == 1

    def test_all_four_rules_present(self):
        text = "Dispatch text"
        result = inject_research_rules(text, "R7_section_writing")
        missing = verify_rules_present(result)
        assert missing == [], f"Missing rule markers: {missing}"

    def test_non_research_r_prefix_rejected(self):
        """Nodes like 'RC123' should still match (starts with R)."""
        text = "text"
        result = inject_research_rules(text, "RC_something")
        assert "research-hard-rules" in result

    def test_lowercase_r_not_matched(self):
        """Only uppercase R prefix counts as research node."""
        text = "text"
        result = inject_research_rules(text, "r4_claim")
        assert result is text

    def test_rule_rollback_targets_present(self):
        text = "dispatch"
        result = inject_research_rules(text, "R2_external_search")
        assert "R4_claim_mining" in result
        assert "R2_external_search" in result
        assert "R6_report_ast" in result


class TestVerifyRulesPresent:
    """Tests for the verification helper."""

    def test_all_present(self):
        text = "has unsupported claim and span_text and connector and 100k chars"
        assert verify_rules_present(text) == []

    def test_missing_one(self):
        text = "has unsupported claim and span_text and connector"
        missing = verify_rules_present(text)
        assert "100k" in missing

    def test_missing_all(self):
        assert len(verify_rules_present("nothing here")) == 4


class TestInjectFile:
    """Integration tests for inject_file(dispatch_file, node_id)."""

    def test_inject_creates_rules_in_file(self, tmp_path):
        dispatch = tmp_path / "test-dispatch.md"
        dispatch.write_text("# Original dispatch\nDo work.\n", encoding="utf-8")
        result = inject_file(dispatch, "R3_evidence")
        assert result is True
        content = dispatch.read_text(encoding="utf-8")
        assert "research-hard-rules" in content
        assert "# Original dispatch" in content

    def test_non_research_file_not_modified(self, tmp_path):
        dispatch = tmp_path / "test-dispatch.md"
        original = "# Original dispatch\nDo work.\n"
        dispatch.write_text(original, encoding="utf-8")
        result = inject_file(dispatch, "N5")
        assert result is False
        assert dispatch.read_text(encoding="utf-8") == original

    def test_missing_file_returns_false(self, tmp_path):
        result = inject_file(tmp_path / "nonexistent.md", "R1")
        assert result is False

    def test_idempotent_file_injection(self, tmp_path):
        dispatch = tmp_path / "test-dispatch.md"
        dispatch.write_text("Original", encoding="utf-8")
        inject_file(dispatch, "R1")
        first_content = dispatch.read_text(encoding="utf-8")
        inject_file(dispatch, "R1")
        second_content = dispatch.read_text(encoding="utf-8")
        assert first_content == second_content


class TestCLI:
    """CLI smoke tests for the injector as a subprocess."""

    def test_cli_research_node(self, tmp_path):
        dispatch = tmp_path / "cli-dispatch.md"
        dispatch.write_text("CLI test dispatch", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "dispatch_prompt_injector", str(dispatch), "R5"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent / "lib"),
        )
        assert proc.returncode == 0
        assert "injected" in proc.stdout.lower()

    def test_cli_non_research_node(self, tmp_path):
        dispatch = tmp_path / "cli-dispatch.md"
        dispatch.write_text("CLI test dispatch", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "dispatch_prompt_injector", str(dispatch), "N5"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent / "lib"),
        )
        assert proc.returncode == 0
        assert "skip" in proc.stdout.lower()
