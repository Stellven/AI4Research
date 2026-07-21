"""Test that build_research_payload returns the 5 new S04 fields.

Mocks only file IO (tmp_path fixture), not internal functions.
"""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

_ROUTES_PATH = Path(__file__).parent.parent.parent / "harness" / "status-server" / "research_routes.py"
_SPEC = importlib.util.spec_from_file_location("research_routes_s04_fields", _ROUTES_PATH)
_MOD = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MOD)
build_research_payload = _MOD.build_research_payload


SID = "sprint-test-s04-fields"


def _write_metrics(sprints_dir: Path, sid: str, metrics: dict) -> None:
    (sprints_dir / f"{sid}.research_execution_metrics.json").write_text(
        json.dumps(metrics), encoding="utf-8"
    )


class TestBuildResearchPayloadS04Fields:
    """build_research_payload must return the 5 S04 fields."""

    def test_five_fields_present_when_metrics_exist(self, tmp_path: Path) -> None:
        _write_metrics(tmp_path, SID, {
            "usage_source": "provider_usage_ledger",
            "estimated": False,
            "fallback_reason": None,
            "state": "completed",
        })
        payload = build_research_payload(tmp_path, SID)
        for field in ("usage_source", "estimated", "fallback_reason", "state", "fallback_level"):
            assert field in payload, f"missing field: {field}"

    def test_usage_source_value(self, tmp_path: Path) -> None:
        _write_metrics(tmp_path, SID, {"usage_source": "hybrid", "estimated": True})
        payload = build_research_payload(tmp_path, SID)
        assert payload["usage_source"] == "hybrid"
        assert payload["estimated"] is True

    def test_fallback_level_L1(self, tmp_path: Path) -> None:
        _write_metrics(tmp_path, SID, {
            "usage_source": "provider_usage_ledger",
            "estimated": False,
        })
        payload = build_research_payload(tmp_path, SID)
        assert payload["fallback_level"] == "L1"

    def test_fallback_level_L2(self, tmp_path: Path) -> None:
        _write_metrics(tmp_path, SID, {"usage_source": "hybrid", "estimated": True})
        payload = build_research_payload(tmp_path, SID)
        assert payload["fallback_level"] == "L2"

    def test_fallback_level_L3(self, tmp_path: Path) -> None:
        _write_metrics(tmp_path, SID, {
            "usage_source": "estimated",
            "estimated": True,
            "fallback_reason": "cli_no_usage",
        })
        payload = build_research_payload(tmp_path, SID)
        assert payload["fallback_level"] == "L3"

    def test_fallback_level_L4(self, tmp_path: Path) -> None:
        _write_metrics(tmp_path, SID, {
            "usage_source": "estimated",
            "estimated": True,
            "fallback_reason": "all_unavailable",
        })
        payload = build_research_payload(tmp_path, SID)
        assert payload["fallback_level"] == "L4"

    def test_fields_none_when_metrics_missing(self, tmp_path: Path) -> None:
        payload = build_research_payload(tmp_path, SID)
        assert payload["usage_source"] is None
        assert payload["estimated"] is None
        assert payload["fallback_reason"] is None
        assert payload["state"] == "unknown"
        assert payload["fallback_level"] is None
        assert payload["word_count"] is None
        assert payload["total_tokens"] is None

    def test_legacy_s03_metric_names_are_mapped(self, tmp_path: Path) -> None:
        _write_metrics(tmp_path, SID, {
            "token_usage_source": "estimated_from_report_artifacts",
            "token_usage_is_estimated": True,
            "document_word_count": 1234,
            "total_token_consumption": 5678,
        })
        payload = build_research_payload(tmp_path, SID)
        assert payload["usage_source"] == "estimated_from_report_artifacts"
        assert payload["estimated"] is True
        assert payload["fallback_level"] == "L4"
        assert payload["word_count"] == 1234
        assert payload["total_tokens"] == 5678

    def test_metrics_loaded_from_eval_output_dir(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "run-output"
        output_dir.mkdir()
        (tmp_path / f"{SID}-research_eval.json").write_text(
            json.dumps({"status": "passed", "output_dir": str(output_dir)}),
            encoding="utf-8",
        )
        (output_dir / "research_execution_metrics.json").write_text(
            json.dumps({
                "usage_source": "provider_usage_ledger",
                "estimated": False,
                "word_count": 88,
                "total_tokens": 99,
            }),
            encoding="utf-8",
        )
        payload = build_research_payload(tmp_path, SID)
        assert payload["usage_source"] == "provider_usage_ledger"
        assert payload["fallback_level"] == "L1"
        assert payload["word_count"] == 88
        assert payload["total_tokens"] == 99

    def test_metrics_loaded_from_eval_embedded_execution_metrics(self, tmp_path: Path) -> None:
        (tmp_path / f"{SID}-research_eval.json").write_text(
            json.dumps({
                "status": "passed",
                "execution_metrics": {
                    "token_usage_source": "estimated_from_report_artifacts",
                    "token_usage_is_estimated": True,
                    "document_word_count": 2447,
                    "total_token_consumption": 5146,
                },
            }),
            encoding="utf-8",
        )
        payload = build_research_payload(tmp_path, SID)
        assert payload["usage_source"] == "estimated_from_report_artifacts"
        assert payload["estimated"] is True
        assert payload["fallback_level"] == "L4"
        assert payload["word_count"] == 2447
        assert payload["total_tokens"] == 5146

    def test_existing_signature_unchanged(self, tmp_path: Path) -> None:
        """build_research_payload(sprints_dir, sid) signature must not change."""
        import inspect

        sig = inspect.signature(build_research_payload)
        params = list(sig.parameters)
        assert params[0] == "sprints_dir"
        assert params[1] == "sid"
