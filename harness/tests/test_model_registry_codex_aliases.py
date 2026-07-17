from __future__ import annotations

import json
from pathlib import Path

import pytest

import model_registry


HARNESS_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = HARNESS_DIR / "config" / "model-registry.json"
PHYSICAL_OPERATORS_PATH = HARNESS_DIR / "config" / "physical-operators.json"


def _registry() -> dict:
    return model_registry.load_registry(REGISTRY_PATH)


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("gpt-5.5", "openai-gpt-5.5"),
        ("codex-gpt-5.5", "openai-gpt-5.5"),
        ("openai-gpt-5.5", "openai-gpt-5.5"),
        ("gpt-5.3-codex-spark", "openai-gpt-5.3-codex-spark"),
        ("codex-gpt-5.3-spark", "openai-gpt-5.3-codex-spark"),
        ("codex-spark", "openai-gpt-5.3-codex-spark"),
        ("gpt53-spark", "openai-gpt-5.3-codex-spark"),
    ],
)
def test_codex_aliases_are_valid_main_models(alias: str, canonical: str) -> None:
    reg = _registry()
    assert model_registry.normalize(reg, alias) == canonical
    assert model_registry.spec(reg, alias)["main_allowed"] is True


def test_codex_aliases_expose_provider_and_model_key() -> None:
    reg = _registry()

    gpt55 = model_registry.spec(reg, "gpt-5.5")
    assert gpt55["provider"] == "openai"
    assert gpt55["model_key"] == "gpt-5.5"

    spark = model_registry.spec(reg, "gpt-5.3-codex-spark")
    assert spark["provider"] == "openai"
    assert spark["model_key"] == "gpt-5.3-codex-spark"


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("opus", "claude-opus"),
        ("claude", "claude-sonnet"),
        ("anthropic-sonnet", "claude-sonnet"),
        ("anthropic-opus", "claude-opus"),
    ],
)
def test_claude_main_aliases_still_validate(alias: str, canonical: str) -> None:
    reg = _registry()
    assert model_registry.normalize(reg, alias) == canonical
    assert model_registry.spec(reg, alias)["main_allowed"] is True


@pytest.mark.parametrize("alias", ["sonnet", "sonnet-4", "opus-4"])
def test_legacy_claude_short_alias_failures_are_preserved(alias: str) -> None:
    reg = _registry()
    with pytest.raises(SystemExit):
        spec = model_registry.spec(reg, alias)
        if not spec.get("main_allowed"):
            raise SystemExit(f"model not allowed on main panes: {alias}")


def test_enabled_openai_physical_operator_models_resolve() -> None:
    reg = _registry()
    operators = json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8")).get("operators") or {}

    unresolved: list[str] = []
    for operator_id, operator in sorted(operators.items()):
        if operator.get("enabled") is False:
            continue
        provider = str(operator.get("provider") or operator.get("vendor") or "").lower()
        if provider != "openai":
            continue
        model = str(operator.get("model") or "").strip()
        if not model:
            continue
        try:
            model_registry.normalize(reg, model)
        except SystemExit as exc:
            unresolved.append(f"{operator_id}: {model} ({exc})")

    assert not unresolved
