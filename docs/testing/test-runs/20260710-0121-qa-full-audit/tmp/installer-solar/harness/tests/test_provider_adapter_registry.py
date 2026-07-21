#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import provider_adapter_registry as par  # noqa: E402


def test_resolve_provider_prefers_registry_model_alias():
    assert par.resolve_provider(model="gemini", backend="") == "gemini"
    assert par.resolve_provider(model="glm", backend="") == "zhipu"
    assert par.resolve_provider(model="deepseek-v4", backend="") == "deepseek"


def test_resolve_provider_handles_backend_aliases():
    assert par.resolve_provider(model="custom", backend="gemini-cli") == "gemini"
    assert par.resolve_provider(model="custom", backend="claude-sdk") == "anthropic"


def test_route_model_alias_uses_registry_and_provider_defaults():
    assert par.route_model_alias(provider="zhipu", model="glm47") == "glm-4.7"
    assert par.route_model_alias(provider="deepseek", model="deepseek-v4-pro") == "deepseek"
    assert par.route_model_alias(provider="openai", model="chatgpt-5.5") == "chatgpt-5.5"
