from __future__ import annotations

import json
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _load_config(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def _candidate_ids(logical: dict, operator: str) -> list[str]:
    return [c["actor_id"] for c in logical["bindings"][operator]["candidates"]]


def test_prd_planner_path_prefers_opus_then_codex_gpt55() -> None:
    logical = _load_config("logical-operators.json")

    deep_architect = _candidate_ids(logical, "DeepArchitect")
    parallel_explorer = _candidate_ids(logical, "ParallelExplorer")

    preferred_prefix = [
        "mini-claude-opus-planner",
        "mini-claude-opus-planner-2",
        "mini-claude-opus-planner-3",
        "mini-codex-gpt55-medium-planner-1",
        "mini-codex-gpt55-medium-planner-2",
    ]
    assert deep_architect[:5] == preferred_prefix
    assert parallel_explorer[:5] == preferred_prefix
    assert deep_architect[-1] == "mini-antigravity-gemini31-pro"
    assert parallel_explorer[-1] == "mini-antigravity-gemini31-pro"


def test_codex_gpt55_planner_support_is_registered_as_planner_not_builder() -> None:
    physical = _load_config("physical-operators.json")
    actors = _load_config("agent-actors.json")

    for actor_id in [
        "mini-codex-gpt55-medium-planner-1",
        "mini-codex-gpt55-medium-planner-2",
    ]:
        op = physical["operators"][actor_id]
        actor = actors["actors"][actor_id]

        assert op["model"] == "gpt-5.5"
        assert op["role"] == "planner"
        assert "prd" in op["task_classes"]
        assert "builder_pool" not in op
        assert actor["role"] == "planner"
        assert actor["persona_binding"]["persona_id"] == "planner"


def test_antigravity_planner_is_emergency_fallback_for_prd_path() -> None:
    logical = _load_config("logical-operators.json")
    physical = _load_config("physical-operators.json")

    for operator in ["DeepArchitect", "ParallelExplorer"]:
        antigravity = logical["bindings"][operator]["candidates"][-1]
        assert antigravity == {
            "actor_id": "mini-antigravity-gemini31-pro",
            "priority": 99,
            "condition": "emergency_only",
        }

    antigravity_op = physical["operators"]["mini-antigravity-gemini31-pro"]
    assert antigravity_op["quota_guard_state"] == "conserve"
    assert "quota-sensitive-planning" in antigravity_op["avoid_for"]
