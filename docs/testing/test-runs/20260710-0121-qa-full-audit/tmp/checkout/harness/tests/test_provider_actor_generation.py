#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
sys.path.insert(0, str(ROOT / "lib"))

import actor_registry as ar  # noqa: E402
import provider_adapter_registry as par  # noqa: E402


PHYSICAL_OPERATORS_FILE = CONFIG_DIR / "physical-operators.json"
ACTORS_FILE = CONFIG_DIR / "agent-actors.json"
ACTORS_SCHEMA_FILE = CONFIG_DIR / "agent-actors.schema.json"


def test_physical_operator_registry_passes_provider_adapter_validation():
    registry = json.loads(PHYSICAL_OPERATORS_FILE.read_text(encoding="utf-8"))
    result = par.validate_physical_operator_registry(registry)
    assert result["ok"], result["errors"]
    assert result["summary"]["operator_count"] >= 1


def test_provider_probe_hints_cover_google_glm_and_local_command_operators():
    physical = json.loads(PHYSICAL_OPERATORS_FILE.read_text(encoding="utf-8"))["operators"]
    notebooklm = par.probe_hints(
        provider=str(physical["mini-browser-notebooklm"].get("provider") or ""),
        model=str(physical["mini-browser-notebooklm"].get("model") or ""),
        backend=str(physical["mini-browser-notebooklm"].get("backend") or ""),
    )
    glm = par.probe_hints(
        provider=str(physical["mini-glm51-knowledge"].get("provider") or ""),
        model=str(physical["mini-glm51-knowledge"].get("model") or ""),
        backend=str(physical["mini-glm51-knowledge"].get("backend") or ""),
    )
    local = par.probe_hints(
        provider=str(physical["mini-thunderomlx-qwen36-knowledge"].get("provider") or ""),
        model=str(physical["mini-thunderomlx-qwen36-knowledge"].get("model") or ""),
        backend=str(physical["mini-thunderomlx-qwen36-knowledge"].get("backend") or ""),
    )
    assert notebooklm["provider"] == "gemini"
    assert notebooklm["doctor_kind"] == "gemini_adapter"
    assert "command" in notebooklm["supported_backends"]
    assert glm["provider"] == "zhipu"
    assert glm["doctor_kind"] == "env_proxy"
    assert glm["probe_auth_key"] == "zhipu_auth"
    assert local["provider"] == "local"
    assert local["doctor_kind"] == "local_proxy"


def test_derived_actor_registry_validates_against_schema():
    derived = ar.load_actor_registry(ACTORS_FILE)
    schema = json.loads(ACTORS_SCHEMA_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(instance=derived, schema=schema)


def test_actor_registry_validation_accepts_current_config():
    result = ar.validate_actor_registry(ACTORS_FILE)
    assert result["ok"], result["errors"]
    assert result["summary"]["actor_count"] >= result["summary"]["physical_operator_count"]
