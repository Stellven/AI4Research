"""Integration test: real vs estimated token usage switching.

Covers L1 (provider_usage_ledger), L2 (hybrid), L3 (estimated) paths
through report_metrics.build_execution_metrics and build_model_usage_event.
"""

from __future__ import annotations

import json
import textwrap

from harness.lib.research import report_metrics


def _write_usage_jsonl(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")


def test_l1_provider_usage_ledger(tmp_path):
    """L1: backend returns real usage → provider_usage_ledger, estimated=False."""
    usage_file = tmp_path / "model_usage.jsonl"
    _write_usage_jsonl(usage_file, [
        {
            "ts": "2026-05-18T20:00:00Z",
            "token_usage_source": "provider_usage_ledger",
            "token_usage_is_estimated": False,
            "total_tokens": 500,
            "input_tokens": 300,
            "output_tokens": 200,
        }
    ])
    metrics = report_metrics.build_execution_metrics("test document content", str(tmp_path))
    assert metrics["token_usage_source"] == "provider_usage_ledger"
    assert metrics["token_usage_is_estimated"] is False
    assert metrics["usage_source"] == "provider_usage_ledger"
    assert metrics["estimated"] is False
    assert metrics["total_token_consumption"] >= 500


def test_l2_hybrid(tmp_path):
    """L2: mixed real and estimated rows → provider_usage_ledger (real rows win)."""
    usage_file = tmp_path / "model_usage.jsonl"
    _write_usage_jsonl(usage_file, [
        {
            "ts": "2026-05-18T20:00:00Z",
            "token_usage_source": "provider_usage_ledger",
            "token_usage_is_estimated": False,
            "total_tokens": 400,
        },
        {
            "ts": "2026-05-18T20:01:00Z",
            "token_usage_source": "estimated_from_model_io",
            "token_usage_is_estimated": True,
            "total_tokens": 100,
        },
    ])
    metrics = report_metrics.build_execution_metrics("hybrid test", str(tmp_path))
    assert metrics["token_usage_source"] == "provider_usage_ledger"
    assert metrics["token_usage_is_estimated"] is False
    assert metrics["usage_source"] == "provider_usage_ledger"


def test_l3_estimated_no_provider(tmp_path):
    """L3: no provider usage file → estimated_from_report_artifacts, estimated=True."""
    metrics = report_metrics.build_execution_metrics("estimated only content", str(tmp_path))
    assert metrics["token_usage_source"] == "estimated_from_report_artifacts"
    assert metrics["token_usage_is_estimated"] is True
    assert metrics["usage_source"] == "estimated_from_report_artifacts"
    assert metrics["estimated"] is True
    assert metrics["fallback_reason"] is not None


def test_build_model_usage_event_real():
    """build_model_usage_event with real usage → provider_usage_ledger."""
    event = report_metrics.build_model_usage_event(
        backend="claude-cli",
        model="test-model",
        prompt="hello",
        output="world",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    assert event["token_usage_source"] == "provider_usage_ledger"
    assert event["token_usage_is_estimated"] is False


def test_build_model_usage_event_estimated():
    """build_model_usage_event without usage → estimated."""
    event = report_metrics.build_model_usage_event(
        backend="local-command",
        model="test",
        prompt="hello",
        output="world",
    )
    assert event["token_usage_source"] == "estimated_from_model_io"
    assert event["token_usage_is_estimated"] is True
