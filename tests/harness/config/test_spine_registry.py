"""Lane 0 spine-config contract tests (R8 — shipped surface).

Guards the shipped defaults:
- only healthy Claude-CLI / Codex operators are enabled (AC-R8.2)
- enabled implies non-deprecated (registry hygiene G7)
- personal/provider defaults are neutralized in the shipped user config
- dead config does not ship (G8)
"""
import json
from pathlib import Path

CONFIG_DIR = (Path(__file__).resolve().parents[3] / 'harness') / "config"

SPINE_OPERATORS = {
    "mini-claude-opus-planner-print",
    "mini-claude-sonnet-builder-2",
    "mini-claude-sonnet-evaluator-print",
    "mini-codex-gpt55-medium-planner-1",
    "mini-codex-gpt55-medium-planner-2",
    "mini-codex-gpt55-medium-builder-1",
    "mini-codex-gpt53-spark-builder-1",
    "mini-codex-gpt55-medium-evaluator-1",
    "mini-codex-gpt55-medium-evaluator-2",
}
SPINE_PROVIDERS = {"anthropic", "openai"}


def _operators():
    data = json.loads((CONFIG_DIR / "physical-operators.json").read_text())
    return data["operators"]


def test_enabled_operators_are_spine_providers_only():
    bad = {
        oid: o.get("provider")
        for oid, o in _operators().items()
        if o.get("enabled") and o.get("provider") not in SPINE_PROVIDERS
    }
    assert not bad, f"non-spine providers enabled in shipped registry: {bad}"


def test_enabled_operators_are_not_deprecated():
    bad = [oid for oid, o in _operators().items() if o.get("enabled") and o.get("deprecated")]
    assert not bad, f"enabled-but-deprecated operators ship confusion (G7): {bad}"


def test_spine_operators_enabled_and_roles_covered():
    ops = _operators()
    missing = [oid for oid in SPINE_OPERATORS if not ops.get(oid, {}).get("enabled")]
    assert not missing, f"spine operators disabled: {missing}"
    for provider in SPINE_PROVIDERS:
        roles = {
            o.get("role")
            for o in ops.values()
            if o.get("enabled") and o.get("provider") == provider
        }
        assert {"planner", "builder", "evaluator"} <= roles, (
            f"{provider} cannot staff a full DAG with enabled operators: roles={roles}"
        )


def test_exactly_the_spine_is_enabled():
    enabled = {oid for oid, o in _operators().items() if o.get("enabled")}
    assert enabled == SPINE_OPERATORS, (
        f"shipped enabled set drifted: extra={enabled - SPINE_OPERATORS}, "
        f"missing={SPINE_OPERATORS - enabled}"
    )


def test_user_config_defaults_are_neutral():
    cfg = json.loads((CONFIG_DIR / "solar-user-config.json").read_text())
    assert cfg["providers"]["prefer_zhipu"] is False
    assert "glm" not in cfg["models"]["lab_builder_matrix"], (
        "shipped lab matrix must not route to GLM (bare-alias trap, F-068)"
    )
    assert cfg["apple_notes"]["enabled"] is False, "personal ingest must ship disabled (R8)"
    assert cfg["mirage"]["enabled"] is False, "personal integration must ship disabled (R8)"


def test_dead_config_does_not_ship():
    assert not (CONFIG_DIR / "operator-model-selections.json").exists(), (
        "operator-model-selections.json is dead config (G8) and must not ship"
    )
