"""Schema adapter for DeepResearch token usage data.

Bridges naming conventions between S02 JSON schemas (usage_source, estimated)
and Codex/legacy code (token_usage_source, token_usage_is_estimated).

Provides jsonschema validation against the frozen S02 schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

_FIELD_MAP_S02_TO_CODEX: dict[str, str] = {
    "usage_source": "token_usage_source",
    "estimated": "token_usage_is_estimated",
}

_FIELD_MAP_CODEX_TO_S02: dict[str, str] = {v: k for k, v in _FIELD_MAP_S02_TO_CODEX.items()}


def normalize_to_s02(data: dict[str, Any]) -> dict[str, Any]:
    """Convert Codex/legacy field names to S02 schema field names."""
    result = dict(data)
    for s02_key, codex_key in _FIELD_MAP_S02_TO_CODEX.items():
        if codex_key in result:
            result[s02_key] = result.pop(codex_key)
    return result


def denormalize_from_s02(data: dict[str, Any]) -> dict[str, Any]:
    """Convert S02 schema field names to Codex/legacy field names."""
    result = dict(data)
    for s02_key, codex_key in _FIELD_MAP_S02_TO_CODEX.items():
        if s02_key in result:
            result[codex_key] = result.pop(s02_key)
    return result


def _load_schema(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_model_usage_line(
    data: dict[str, Any],
    *,
    schema_path: str | Path | None = None,
    schema: dict[str, Any] | None = None,
) -> None:
    if schema is None:
        if schema_path is None:
            raise ValueError("Provide either schema_path or schema")
        schema = _load_schema(schema_path)
    jsonschema.validate(instance=data, schema=schema)


def validate_execution_metrics(
    data: dict[str, Any],
    *,
    schema_path: str | Path | None = None,
    schema: dict[str, Any] | None = None,
) -> None:
    if schema is None:
        if schema_path is None:
            raise ValueError("Provide either schema_path or schema")
        schema = _load_schema(schema_path)
    jsonschema.validate(instance=data, schema=schema)
