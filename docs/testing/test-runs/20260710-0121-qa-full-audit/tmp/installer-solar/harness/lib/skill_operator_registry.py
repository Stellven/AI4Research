#!/usr/bin/env python3
"""skill_operator_registry.py — explicit skill/logical/physical/capsule bindings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

HARNESS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BINDINGS_PATH = HARNESS_DIR / "config" / "skill-operator-bindings.yaml"


@dataclass
class SkillOperatorBinding:
    skill_id: str
    logical_operator: str
    physical_operator: str
    capsule_id: str
    actor: str = "codex"
    semantic_backend: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


def _read_bindings_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "skill_operator_bindings": [], "defaults": {}}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {"version": 1, "skill_operator_bindings": [], "defaults": {}}
    raw.setdefault("version", 1)
    raw.setdefault("skill_operator_bindings", [])
    raw.setdefault("defaults", {})
    return raw


def load_bindings(path: Path | None = None) -> list[SkillOperatorBinding]:
    payload = _read_bindings_payload(Path(path or DEFAULT_BINDINGS_PATH))
    bindings: list[SkillOperatorBinding] = []
    for item in payload.get("skill_operator_bindings", []) or []:
        if not isinstance(item, dict):
            continue
        if not all(item.get(field) for field in ("skill_id", "logical_operator", "physical_operator", "capsule_id")):
            continue
        bindings.append(
            SkillOperatorBinding(
                skill_id=str(item["skill_id"]),
                logical_operator=str(item["logical_operator"]),
                physical_operator=str(item["physical_operator"]),
                capsule_id=str(item["capsule_id"]),
                actor=str(item.get("actor") or "codex"),
                semantic_backend=str(item["semantic_backend"]) if item.get("semantic_backend") else None,
            )
        )
    return bindings


def lookup_by_skill(skill_id: str, path: Path | None = None) -> SkillOperatorBinding | None:
    for binding in load_bindings(path):
        if binding.skill_id == str(skill_id):
            return binding
    return None


def lookup_by_logical_operator(logical_operator: str, path: Path | None = None) -> SkillOperatorBinding | None:
    for binding in load_bindings(path):
        if binding.logical_operator == str(logical_operator):
            return binding
    return None


def register_binding(binding: SkillOperatorBinding, path: Path | None = None) -> None:
    binding_path = Path(path or DEFAULT_BINDINGS_PATH)
    payload = _read_bindings_payload(binding_path)
    current = [
        item
        for item in payload.get("skill_operator_bindings", []) or []
        if not (
            isinstance(item, dict)
            and item.get("skill_id") == binding.skill_id
            and item.get("logical_operator") == binding.logical_operator
        )
    ]
    current.append(binding.to_dict())
    payload["skill_operator_bindings"] = sorted(
        current,
        key=lambda item: (str(item.get("logical_operator", "")), str(item.get("skill_id", ""))),
    )
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def merge_with_defaults(default_map: dict[str, str], path: Path | None = None) -> dict[str, str]:
    merged = dict(default_map)
    for binding in load_bindings(path):
        merged[binding.logical_operator] = binding.capsule_id
    return merged
