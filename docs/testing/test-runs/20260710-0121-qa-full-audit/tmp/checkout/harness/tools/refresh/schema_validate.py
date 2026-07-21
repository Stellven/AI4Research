"""JSON schema validation for refresh.run.v1 output.

Usage:
    from harness.lib.refresh.schema_validate import validate
    validate(result_dict)   # raises jsonschema.ValidationError on invalid input
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schemas" / "refresh.schema.json"

_schema: dict | None = None


def _load_schema() -> dict:
    global _schema
    if _schema is None:
        with open(_SCHEMA_PATH, encoding="utf-8") as fh:
            _schema = json.load(fh)
    return _schema


def validate(obj: dict) -> None:
    """Validate *obj* against the refresh.run.v1 JSON schema.

    Raises jsonschema.ValidationError with a descriptive message if invalid.
    Returns None silently on success.
    """
    schema = _load_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = list(validator.iter_errors(obj))
    if errors:
        best = jsonschema.exceptions.best_match(errors)
        raise jsonschema.ValidationError(
            f"refresh.run.v1 validation failed: {best.message} (path: {list(best.absolute_path)})"
        )
