"""Helpers for loading the logical-operator registry as a single config truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness_paths import resolve_runtime_harness_dir

HARNESS_DIR = resolve_runtime_harness_dir()
LOGICAL_OPERATORS_PATH = HARNESS_DIR / "config" / "logical-operators.json"


def load_logical_operator_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = Path(path or LOGICAL_OPERATORS_PATH)
    if not registry_path.exists():
        return {}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def logical_operator_def(operator_type: str, path: Path | None = None) -> dict[str, Any]:
    payload = load_logical_operator_registry(path=path)
    return dict((payload.get("logical_operators") or {}).get(str(operator_type or ""), {}))


def logical_operator_binding(operator_type: str, path: Path | None = None) -> dict[str, Any]:
    payload = load_logical_operator_registry(path=path)
    return dict((payload.get("bindings") or {}).get(str(operator_type or ""), {}))
