"""Integration tests: local-command fixture → report_metrics.build_execution_metrics.

Proves:
  1. Real usage fixture walks through build_execution_metrics and produces
     usage_source='provider_usage_ledger' / estimated=False.
  2. No-usage (or estimated-only) fixture forces estimated=True.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from harness.lib.research.report_metrics import build_execution_metrics

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
REAL_USAGE_FIXTURE = FIXTURES / "local_command_usage.json"


class TestRealUsageProviderLedger:
    def test_real_fixture_walks_through_build_metrics(self):
        """Real usage JSON → build_execution_metrics returns provider_usage_ledger."""
        tmp = tempfile.mkdtemp()
        # Copy fixture into temp output_dir so _discover_token_usage finds it
        fixture_data = json.loads(REAL_USAGE_FIXTURE.read_text(encoding="utf-8"))
        usage_path = Path(tmp) / "local_command_usage.json"
        usage_path.write_text(json.dumps(fixture_data), encoding="utf-8")

        metrics = build_execution_metrics("# Test Report\n\nContent.", output_dir=tmp)

        assert metrics["token_usage_source"] == "provider_usage_ledger", (
            f"Expected provider_usage_ledger, got {metrics['token_usage_source']}"
        )
        assert metrics["token_usage_is_estimated"] is False, (
            f"Expected estimated=False, got {metrics['token_usage_is_estimated']}"
        )
        assert metrics["total_token_consumption"] == 2360, (
            f"Expected 2360 total tokens from fixture, got {metrics['total_token_consumption']}"
        )
        assert metrics["input_tokens"] == 1520
        assert metrics["output_tokens"] == 840
        usage_path.unlink(missing_ok=True)

    def test_real_fixture_s02_fields_match(self):
        """S02 alias fields (usage_source/estimated) match Codex fields."""
        tmp = tempfile.mkdtemp()
        fixture_data = json.loads(REAL_USAGE_FIXTURE.read_text(encoding="utf-8"))
        usage_path = Path(tmp) / "local_command_usage.json"
        usage_path.write_text(json.dumps(fixture_data), encoding="utf-8")

        metrics = build_execution_metrics("Test text", output_dir=tmp)

        assert metrics["usage_source"] == "provider_usage_ledger"
        assert metrics["estimated"] is False
        usage_path.unlink(missing_ok=True)

    def test_fixture_file_has_valid_usage_fields(self):
        """Fixture JSON contains prompt_tokens/completion_tokens/total_tokens."""
        data = json.loads(REAL_USAGE_FIXTURE.read_text(encoding="utf-8"))
        assert "prompt_tokens" in data and isinstance(data["prompt_tokens"], int)
        assert "completion_tokens" in data and isinstance(data["completion_tokens"], int)
        assert "total_tokens" in data and isinstance(data["total_tokens"], int)
        assert data["total_tokens"] == data["prompt_tokens"] + data["completion_tokens"]


class TestNoUsageForcesEstimated:
    def test_empty_dir_forces_estimated(self):
        """No usage files in output_dir → estimated=True."""
        tmp = tempfile.mkdtemp()
        metrics = build_execution_metrics("# Report\n\nContent.", output_dir=tmp)

        assert metrics["token_usage_is_estimated"] is True, (
            f"Expected estimated=True for empty dir, got {metrics['token_usage_is_estimated']}"
        )
        assert metrics["token_usage_source"] != "provider_usage_ledger", (
            f"Expected source != provider_usage_ledger, got {metrics['token_usage_source']}"
        )

    def test_estimated_fixture_skipped(self):
        """File with token_usage_is_estimated=true is skipped → still estimated."""
        tmp = tempfile.mkdtemp()
        estimated_fixture = {
            "backend": "local-command",
            "model": "n/a",
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "token_usage_is_estimated": True,
            "token_usage_source": "estimated_from_model_io",
        }
        usage_path = Path(tmp) / "usage_token_backend.json"
        usage_path.write_text(json.dumps(estimated_fixture), encoding="utf-8")

        metrics = build_execution_metrics("Report text", output_dir=tmp)

        assert metrics["token_usage_is_estimated"] is True
        assert metrics["token_usage_source"] != "provider_usage_ledger"
        usage_path.unlink(missing_ok=True)

    def test_no_dir_forces_estimated(self):
        """output_dir=None → estimated=True."""
        metrics = build_execution_metrics("Report text", output_dir=None)

        assert metrics["token_usage_is_estimated"] is True
        assert "estimated" in metrics["token_usage_source"]

    def test_negative_invariant_estimated_never_claims_provider(self):
        """When estimated=True, usage_source must never be provider_usage_ledger."""
        tmp = tempfile.mkdtemp()
        metrics = build_execution_metrics("Text", output_dir=tmp)
        if metrics["token_usage_is_estimated"] is True:
            assert metrics["token_usage_source"] != "provider_usage_ledger"
