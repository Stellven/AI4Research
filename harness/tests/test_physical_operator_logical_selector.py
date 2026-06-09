#!/usr/bin/env python3
import sys
from pathlib import Path

# Insert lib to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import pytest
import multi_task_runner as m
import operator_runtime

# Save original functions to prevent test pollution in pytest sessions
_orig_get_state = operator_runtime.get_operator_runtime_state
_orig_load_ops = m.load_physical_operators

@pytest.fixture(autouse=True)
def setup_mocks():
    operator_runtime.get_operator_runtime_state = lambda op_id: "idle"
    m.load_physical_operators = lambda: mock_registry
    yield
    operator_runtime.get_operator_runtime_state = _orig_get_state
    m.load_physical_operators = _orig_load_ops


# Mock registry
mock_registry = {
    "version": 1,
    "operators": {
        "operator-planner": {
            "display_name": "Mock Planner",
            "role": "planner",
            "profile": "planner",
            "enabled": True,
            "available": True,
            "key_ref": "mock_key",
            "auth_mode": "subscription",
            "quota_guard_state": "ok",
            "task_classes": ["planning", "ARCH_DESIGN"],
            "operator_class": "DeepArchitect",
            "capability": {
                "planning": 5,
                "long_context": 4
            },
            "cost_tier": "medium",
            "quota": {
                "reserve_for": ["ARCH_DESIGN"]
            }
        },
        "operator-builder": {
            "display_name": "Mock Builder",
            "role": "builder",
            "profile": "builder",
            "enabled": True,
            "available": True,
            "key_ref": "mock_key",
            "auth_mode": "subscription",
            "quota_guard_state": "ok",
            "task_classes": ["implementation", "debugging"],
            "operator_class": "DeepBuilder",
            "capability": {
                "coding": 5,
                "debugging": 4
            },
            "cost_tier": "medium"
        },
        "operator-evaluator": {
            "display_name": "Mock Evaluator",
            "role": "evaluator",
            "profile": "evaluator",
            "enabled": True,
            "available": True,
            "key_ref": "mock_key",
            "auth_mode": "subscription",
            "quota_guard_state": "ok",
            "task_classes": ["verification", "review"],
            "operator_class": "DeepEvaluator",
            "capability": {
                "review": 5
            },
            "cost_tier": "low"
        }
    }
}

# Override handled dynamically by fixtures/manual setup


def test_preferred_operator_override():
    # preferred_operator remains hard override
    node = {
        "preferred_operator": "operator-builder",
        "task_type": "ARCH_DESIGN" # conflict with builder's task classes
    }
    op, err = m.select_operator(node, {"name": "builder"})
    assert op is not None
    assert op.get("operator_id") == "operator-builder", op
    assert not err

def test_task_type_matching():
    # task_type selection
    node = {
        "task_type": "implementation"
    }
    op, err = m.select_operator(node, {"name": "builder"})
    assert op is not None
    assert op.get("operator_id") == "operator-builder", op
    assert not err


def test_codex_first_routing_prefers_codex_builder(monkeypatch):
    registry = {
        "version": 1,
        "operators": {
            "mini-claude-sonnet-builder": {
                "display_name": "Claude Builder",
                "role": "builder",
                "profile": "builder",
                "enabled": True,
                "available": True,
                "auth_mode": "subscription",
                "quota_guard_state": "ok",
                "task_classes": ["implementation"],
                "preferred_for": ["builder", "implementation"],
                "cost_tier": "low",
            },
            "mini-codex-gpt53-spark-builder-1": {
                "display_name": "Codex Builder",
                "role": "builder",
                "profile": "codex-builder",
                "provider": "openai",
                "model_config": "Codex CLI;gpt-5.3-codex-spark",
                "enabled": True,
                "available": True,
                "auth_mode": "subscription",
                "quota_guard_state": "ok",
                "task_classes": ["implementation"],
                "preferred_for": ["builder", "implementation", "codex"],
                "cost_tier": "medium",
            },
        },
    }
    monkeypatch.setattr(m, "load_physical_operators", lambda: registry)

    node = {
        "task_type": "implementation",
        "operator_selector": {
            "task_type": "implementation",
        },
    }
    op, err = m.select_operator(node, {"name": "builder"})

    assert op is not None
    assert op.get("operator_id") == "mini-codex-gpt53-spark-builder-1", op
    assert not err


def test_capability_scores():
    # required_capabilities constraint
    node = {
        "task_type": "ARCH_DESIGN",
        "required_capabilities": {
            "planning": ">=5",
            "long_context": ">=4"
        }
    }
    op, err = m.select_operator(node, {"name": "planner"})
    assert op is not None
    assert op.get("operator_id") == "operator-planner", op
    assert not err
    
    # capability too high
    node = {
        "task_type": "ARCH_DESIGN",
        "required_capabilities": {
            "planning": ">5"
        }
    }
    op, err = m.select_operator(node, {"name": "planner"})
    assert op is None
    assert "no_match" in err

def test_preferred_operator_classes():
    # select correct operator based on preferred_operator_classes
    node = {
        "task_type": "implementation",
        "preferred_operator_classes": ["DeepBuilder"]
    }
    op, err = m.select_operator(node, {"name": "builder"})
    assert op is not None
    assert op.get("operator_id") == "operator-builder", op
    
    # Class bonus overrides default score ordering (e.g. builder is selected over planner if class matches)
    # Planner matches class DeepArchitect
    node = {
        "task_type": "ARCH_DESIGN",
        "preferred_operator_classes": ["DeepArchitect"],
        "operator_selector": {
            "role": "planner"
        }
    }
    op, err = m.select_operator(node, {"name": "planner"})
    assert op is not None
    assert op.get("operator_id") == "operator-planner", op

def test_constraints():
    # constraints (cost tier)
    node = {
        "task_type": "verification",
        "constraints": {
            "max_cost_tier": "low"
        }
    }
    op, err = m.select_operator(node, {"name": "evaluator"})
    assert op is not None
    assert op.get("operator_id") == "operator-evaluator", op
    
    # constraint prevents matching because cost is higher
    node = {
        "task_type": "implementation",
        "constraints": {
            "max_cost_tier": "low"
        }
    }
    op, err = m.select_operator(node, {"name": "builder"})
    assert op is None
    assert "no_match" in err

def test_quota_reserve():
    # quota reserve protects high-value task ARCH_DESIGN
    node = {
        "task_type": "planning" # Not reserved ARCH_DESIGN
    }
    # operator-planner has reserve_for = ["ARCH_DESIGN"]
    # So a non-ARCH_DESIGN task (like planning) shouldn't be allowed to select operator-planner
    op, err = m.select_operator(node, {"name": "planner"})
    assert op is None, op
    assert "no_match" in err
    
    # But ARCH_DESIGN can select it
    node = {
        "task_type": "ARCH_DESIGN"
    }
    op, err = m.select_operator(node, {"name": "planner"})
    assert op is not None
    assert op.get("operator_id") == "operator-planner"

def test_verifier_conflict():
    # verifier_required rejects same operator as writer when prior operator is provided
    node = {
        "task_type": "verification",
        "verifier_required": True,
        "prior_operator": "operator-evaluator"
    }
    op, err = m.select_operator(node, {"name": "evaluator"})
    assert op is None, op
    assert "no_match" in err
    
    # If verifier_required is False, it is allowed
    node = {
        "task_type": "verification",
        "verifier_required": False,
        "prior_operator": "operator-evaluator"
    }
    op, err = m.select_operator(node, {"name": "evaluator"})
    assert op is not None
    assert op.get("operator_id") == "operator-evaluator"

    # Preferred operator is rejected when verifier_required is True and conflicts with prior operator
    node = {
        "preferred_operator": "operator-evaluator",
        "verifier_required": True,
        "prior_operator": "operator-evaluator"
    }
    op, err = m.select_operator(node, {"name": "evaluator"})
    assert op is None
    assert "verifier_conflict" in err

    node = {
        "preferred_operator": "operator-evaluator",
        "verifier_required": True,
        "prior_operator": "evaluator" # profile conflict
    }
    op, err = m.select_operator(node, {"name": "evaluator"})
    assert op is None
    assert "verifier_conflict" in err


def test_profile_alias_builder_main_selects_builder(monkeypatch):
    profiles = {
        "builder": {
            "role": "builder",
            "persona": "builder",
            "backend": "claude-cli",
            "model": "sonnet",
        }
    }
    monkeypatch.setattr(m, "load_profiles", lambda: {"defaults": {"profile": "builder"}, "profiles": profiles})

    selected = m.select_profile({"preferred_profile": "builder_main"})

    assert selected["name"] == "builder"
    assert selected["model"] == "sonnet"


def test_quota_fallback_skips_blocked_anthropic_profile(monkeypatch):
    profiles = {
        "builder": {
            "role": "builder",
            "persona": "builder",
            "backend": "claude-cli",
            "model": "sonnet",
        },
        "gemini-builder": {
            "role": "builder",
            "persona": "builder",
            "backend": "gemini-cli",
            "model": "gemini-3.5-flash",
        },
        "thunderomlx-local": {
            "role": "builder",
            "persona": "builder",
            "backend": "claude-cli",
            "model": "thunderomlx-local",
        },
    }
    monkeypatch.setattr(m, "load_profiles", lambda: {"defaults": {"profile": "builder"}, "profiles": profiles})
    monkeypatch.setattr(
        m,
        "capability_for_profile",
        lambda profile, include_probe=False: {
            "status": "ok",
            "provider": m.model_provider(str(profile.get("model") or ""), str(profile.get("backend") or "")),
        },
    )

    node = {
        "role": "builder",
        "preferred_profile": "builder_main",
        "preferred_model": "sonnet",
        "quota_blocked_profiles": ["builder"],
    }
    selected = m.select_profile(node)

    assert selected["name"] == "gemini-builder"
    assert selected["model"] == "gemini-3.5-flash"
    assert selected["quota_fallback_from"] == "builder"
    assert selected["quota_fallback_reason"] == "quota_exhausted"


def test_quota_regex_matches_org_monthly_usage_limit():
    text = "You've hit your org's monthly usage limit\nprofile: builder\nbackend: claude-cli\nmodel: sonnet"
    assert m.QUOTA_RE.search(text)


def setup_manual():
    operator_runtime.get_operator_runtime_state = lambda op_id: "idle"
    m.load_physical_operators = lambda: mock_registry

def teardown_manual():
    operator_runtime.get_operator_runtime_state = _orig_get_state
    m.load_physical_operators = _orig_load_ops

if __name__ == "__main__":
    setup_manual()
    try:
        test_preferred_operator_override()
        test_task_type_matching()
        test_capability_scores()
        test_preferred_operator_classes()
        test_constraints()
        test_quota_reserve()
        test_verifier_conflict()
        print("ALL TESTS PASSED SUCCESSFULLY!")
    finally:
        teardown_manual()
