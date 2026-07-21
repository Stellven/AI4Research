"""Unit tests for schema_adapter.py — normalize round-trip + validation.

Covers normalize_to_s02/denormalize_from_s02 round-trip fidelity,
field mapping correctness, and validate_* error handling.
"""

import pytest
from jsonschema import ValidationError

from harness.lib.research.schema_adapter import (
    denormalize_from_s02,
    normalize_to_s02,
    validate_execution_metrics,
    validate_model_usage_line,
)


# Minimal valid model_usage.jsonl line per S02 §5.1 schema
_MINIMAL_USAGE_LINE = {
    "ts": "2026-05-18T19:10:00Z",
    "sprint_id": "sprint-test",
    "stage": "writer",
    "backend": "claude-cli",
    "model": "claude-opus-4-7",
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150,
    "usage_source": "provider_usage_ledger",
    "estimated": False,
    "fallback_reason": None,
    "request_id": "req-001",
    "extra": {},
}

_MINIMAL_USAGE_SCHEMA = {
    "type": "object",
    "required": [
        "ts", "sprint_id", "stage", "backend", "model",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "usage_source", "estimated",
    ],
    "properties": {
        "ts": {"type": "string"},
        "sprint_id": {"type": "string"},
        "stage": {"type": "string"},
        "usage_source": {"type": "string"},
        "estimated": {"type": "boolean"},
        "total_tokens": {"type": "number"},
    },
    "additionalProperties": True,
}

_MINIMAL_METRICS = {
    "sprint_id": "sprint-test",
    "generated_at": "2026-05-18T19:10:00Z",
    "serper_calls": 1,
    "sources_count": 3,
    "backend_calls": 2,
    "total_tokens": 300,
    "prompt_tokens": 200,
    "completion_tokens": 100,
    "usage_source": "provider_usage_ledger",
    "estimated": False,
    "document_word_count": 1500,
    "ledger_path": "model_usage.jsonl",
    "ledger_lines": 3,
    "fallback_reasons": [],
}

_MINIMAL_METRICS_SCHEMA = {
    "type": "object",
    "required": [
        "sprint_id", "generated_at", "total_tokens",
        "usage_source", "estimated", "document_word_count",
    ],
    "properties": {
        "sprint_id": {"type": "string"},
        "total_tokens": {"type": "number"},
        "usage_source": {"type": "string"},
        "estimated": {"type": "boolean"},
        "document_word_count": {"type": "number"},
    },
    "additionalProperties": True,
}


class TestNormalizeRoundTrip:
    """normalize_to_s02 <-> denormalize_from_s02 must be lossless."""

    def test_codex_to_s02_round_trip(self):
        codex_data = {
            "token_usage_source": "provider_usage_ledger",
            "token_usage_is_estimated": False,
            "other_field": "unchanged",
        }
        s02 = normalize_to_s02(codex_data)
        assert "usage_source" in s02
        assert "estimated" in s02
        assert "token_usage_source" not in s02

        back = denormalize_from_s02(s02)
        assert back["token_usage_source"] == "provider_usage_ledger"
        assert back["token_usage_is_estimated"] is False
        assert back["other_field"] == "unchanged"

    def test_s02_passthrough(self):
        data = {"usage_source": "estimated", "estimated": True}
        result = normalize_to_s02(data)
        assert result["usage_source"] == "estimated"
        assert result["estimated"] is True

    def test_denormalize_s02_fields(self):
        data = {"usage_source": "hybrid", "estimated": True, "extra": "keep"}
        result = denormalize_from_s02(data)
        assert "token_usage_source" in result
        assert "token_usage_is_estimated" in result
        assert result["extra"] == "keep"


class TestFieldMapping:
    """Verify exact field name mappings."""

    def test_usage_source_maps(self):
        assert normalize_to_s02({"token_usage_source": "x"})["usage_source"] == "x"

    def test_estimated_maps(self):
        assert normalize_to_s02({"token_usage_is_estimated": True})["estimated"] is True

    def test_denormalize_usage_source(self):
        assert denormalize_from_s02({"usage_source": "y"})["token_usage_source"] == "y"

    def test_denormalize_estimated(self):
        assert denormalize_from_s02({"estimated": False})["token_usage_is_estimated"] is False


class TestValidateModelUsageLine:
    """validate_model_usage_line with inline schema."""

    def test_valid_line_passes(self):
        validate_model_usage_line(_MINIMAL_USAGE_LINE, schema=_MINIMAL_USAGE_SCHEMA)

    def test_missing_required_field_throws(self):
        bad = dict(_MINIMAL_USAGE_LINE)
        del bad["usage_source"]
        with pytest.raises(ValidationError):
            validate_model_usage_line(bad, schema=_MINIMAL_USAGE_SCHEMA)

    def test_wrong_type_throws(self):
        bad = dict(_MINIMAL_USAGE_LINE)
        bad["estimated"] = "not_a_bool"
        with pytest.raises(ValidationError):
            validate_model_usage_line(bad, schema=_MINIMAL_USAGE_SCHEMA)

    def test_no_schema_raises_value_error(self):
        with pytest.raises(ValueError, match="Provide either"):
            validate_model_usage_line(_MINIMAL_USAGE_LINE)


class TestValidateExecutionMetrics:
    """validate_execution_metrics with inline schema."""

    def test_valid_metrics_pass(self):
        validate_execution_metrics(_MINIMAL_METRICS, schema=_MINIMAL_METRICS_SCHEMA)

    def test_missing_required_field_throws(self):
        bad = dict(_MINIMAL_METRICS)
        del bad["sprint_id"]
        with pytest.raises(ValidationError):
            validate_execution_metrics(bad, schema=_MINIMAL_METRICS_SCHEMA)

    def test_wrong_type_throws(self):
        bad = dict(_MINIMAL_METRICS)
        bad["total_tokens"] = "not_a_number"
        with pytest.raises(ValidationError):
            validate_execution_metrics(bad, schema=_MINIMAL_METRICS_SCHEMA)

    def test_no_schema_raises_value_error(self):
        with pytest.raises(ValueError, match="Provide either"):
            validate_execution_metrics(_MINIMAL_METRICS)
