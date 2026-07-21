#!/usr/bin/env python3
"""Apply user-selected model bindings to physical operator registries."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
DEFAULT_OPERATORS_PATH = Path(os.environ.get("SOLAR_MULTI_TASK_OPERATORS", HARNESS_DIR / "config" / "physical-operators.json"))
DEFAULT_SELECTIONS_PATH = Path(os.environ.get("SOLAR_OPERATOR_MODEL_SELECTIONS", HARNESS_DIR / "config" / "operator-model-selections.json"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_model_selections(path: Path | None = None) -> dict[str, Any]:
    """Return the persisted operator -> model selection map."""
    payload = _read_json(path or DEFAULT_SELECTIONS_PATH)
    selections = payload.get("selections", {}) if isinstance(payload, dict) else {}
    return selections if isinstance(selections, dict) else {}


def apply_model_selections(
    registry: dict[str, Any],
    *,
    selections_path: Path | None = None,
) -> dict[str, Any]:
    """Overlay UI model choices onto a physical-operators registry dict.

    This is intentionally non-destructive: callers get a copied registry with
    selected model/provider/vendor fields applied. The status UI may still
    persist selections back to ``physical-operators.json`` for human visibility,
    but schedulers should use this overlay so a missed write cannot desync the
    runtime from the UI selection file.
    """
    if not isinstance(registry, dict):
        return {"version": 1, "operators": {}}
    result = dict(registry)
    operators = result.get("operators", {})
    if not isinstance(operators, dict):
        result["operators"] = {}
        return result

    selections = load_model_selections(selections_path)
    patched: dict[str, Any] = {}
    for operator_id, cfg in operators.items():
        if not isinstance(cfg, dict):
            patched[operator_id] = cfg
            continue
        merged = dict(cfg)
        selection = selections.get(operator_id, {})
        if isinstance(selection, dict):
            model_id = str(selection.get("model_id") or "").strip()
            if model_id:
                merged["model"] = model_id
                if selection.get("provider"):
                    merged["provider"] = str(selection.get("provider"))
                if selection.get("vendor"):
                    merged["vendor"] = str(selection.get("vendor"))
                merged["model_selection"] = dict(selection)
                if merged.get("backend") == "claude-cli":
                    surface = dict(merged.get("surface") or {})
                    is_print = str(merged.get("launch_cmd_kind") or "") == "print_once" or "--print" in str(surface.get("launch_cmd") or "")
                    surface["tool"] = "claude"
                    surface["launch_cmd"] = f"claude {'--print ' if is_print else ''}--model {model_id}".replace("  ", " ").strip()
                    merged["surface"] = surface
        patched[operator_id] = merged
    result["operators"] = patched
    return result


def load_physical_operator_registry(
    operators_path: Path | None = None,
    *,
    selections_path: Path | None = None,
) -> dict[str, Any]:
    """Load physical operators with user model selections applied."""
    path = operators_path or DEFAULT_OPERATORS_PATH
    registry = _read_json(path)
    if not registry:
        return {"version": 1, "operators": {}}
    return apply_model_selections(registry, selections_path=selections_path)
