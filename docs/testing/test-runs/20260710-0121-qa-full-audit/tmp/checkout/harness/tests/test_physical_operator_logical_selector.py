#!/usr/bin/env python3
import json
import sys
from pathlib import Path

# Insert lib to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "lib"))

import pytest
import yaml
import multi_task_runner as m
import operator_runtime
import pm_dispatch

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


def test_model_provider_recognizes_codex_openai_models():
    assert m.model_provider("gpt-5.5", "command") == "openai"
    assert m.model_provider("codex-gpt-5.3-spark", "command") == "openai"
    assert m.model_provider("o3", "command") == "openai"


def test_codex_only_provider_policy_selects_codex_profiles(monkeypatch):
    profiles = {
        "builder": {"role": "builder", "persona": "builder", "backend": "claude-cli", "model": "sonnet"},
        "evaluator": {"role": "evaluator", "persona": "evaluator", "backend": "claude-cli", "model": "opus"},
        "planner": {"role": "planner", "persona": "planner", "backend": "claude-cli", "model": "opus"},
        "codex-builder": {"role": "builder", "persona": "builder", "backend": "command", "model": "gpt-5.5", "command": "codex"},
        "codex-evaluator": {"role": "evaluator", "persona": "evaluator", "backend": "command", "model": "gpt-5.5", "command": "codex"},
        "codex-planner": {"role": "planner", "persona": "planner", "backend": "command", "model": "gpt-5.5", "command": "codex"},
    }
    monkeypatch.setattr(m, "load_profiles", lambda: {"defaults": {"profile": "builder"}, "profiles": profiles})
    monkeypatch.setattr(m, "DEFAULT_OPERATOR_PROVIDER_ORDER", ("openai",))
    monkeypatch.setattr(m, "DEFAULT_OPERATOR_PROVIDERS", frozenset({"openai"}))
    monkeypatch.setattr(
        m,
        "capability_for_profile",
        lambda profile, include_probe=True: {
            "status": "ok",
            "provider": m.model_provider(str(profile.get("model") or ""), str(profile.get("backend") or "")),
        },
    )

    builder = m.select_profile({"logical_operator": "ImplementationWorker"})
    evaluator = m.select_profile({"logical_operator": "Verifier"})
    planner = m.select_profile({"target_role": "planner"})

    assert builder["name"] == "codex-builder"
    assert evaluator["name"] == "codex-evaluator"
    assert planner["name"] == "codex-planner"


def test_codex_only_capability_fallback_does_not_cross_to_claude(monkeypatch):
    profiles = {
        "builder": {"role": "builder", "persona": "builder", "backend": "claude-cli", "model": "sonnet"},
        "codex-builder": {"role": "builder", "persona": "builder", "backend": "command", "model": "gpt-5.5", "command": "codex"},
    }
    monkeypatch.setattr(m, "DEFAULT_OPERATOR_PROVIDER_ORDER", ("openai",))
    monkeypatch.setattr(m, "DEFAULT_OPERATOR_PROVIDERS", frozenset({"openai"}))
    monkeypatch.setattr(
        m,
        "capability_for_profile",
        lambda profile, include_probe=True: {
            "status": "ok",
            "provider": m.model_provider(str(profile.get("model") or ""), str(profile.get("backend") or "")),
        },
    )

    assert m.select_capability_fallback_profile({"logical_operator": "ImplementationWorker"}, "codex-builder", profiles) == ""


def test_multi_task_auto_selection_skips_deprecated_operator(monkeypatch):
    registry = {
        "version": 1,
        "operators": {
            "z-deprecated-builder": {
                "role": "builder",
                "profile": "builder",
                "enabled": True,
                "available": True,
                "deprecated": True,
                "auth_mode": "subscription",
                "quota_guard_state": "ok",
                "task_classes": ["implementation"],
                "capability": {"coding": 5},
            },
            "a-active-builder": {
                "role": "builder",
                "profile": "builder",
                "enabled": True,
                "available": True,
                "deprecated": False,
                "auth_mode": "subscription",
                "quota_guard_state": "ok",
                "task_classes": ["implementation"],
                "capability": {"coding": 5},
            },
        },
    }
    monkeypatch.setattr(m, "load_physical_operators", lambda: registry)

    op, err = m.select_operator({"task_type": "implementation"}, {"name": "builder"})

    assert not err
    assert op is not None
    assert op["operator_id"] == "a-active-builder"


def test_pm_dispatch_auto_selection_skips_deprecated_operator(monkeypatch):
    registry = {
        "operators": {
            "z-deprecated-builder": {
                "role": "builder",
                "profile": "builder",
                "enabled": True,
                "available": True,
                "deprecated": True,
                "auth_mode": "subscription",
                "quota_guard_state": "ok",
                "task_classes": ["implementation"],
                "operator_class": "builder",
                "capability": {"coding": 5},
            },
            "a-active-builder": {
                "role": "builder",
                "profile": "builder",
                "enabled": True,
                "available": True,
                "deprecated": False,
                "auth_mode": "subscription",
                "quota_guard_state": "ok",
                "task_classes": ["implementation"],
                "operator_class": "builder",
                "capability": {"coding": 5},
            },
        }
    }
    monkeypatch.setattr(pm_dispatch, "load_registry", lambda: registry)

    op_id, op, reason = pm_dispatch.select_operator_by_role("builder", task_type="implementation")

    assert not reason
    assert op_id == "a-active-builder"
    assert op["deprecated"] is False


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


def test_evaluator_graph_eval_uses_verification_capsule():
    node = {
        "id": "B1",
        "capability_native": True,
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "dispatch_task_type": "implementation",
        "logical_operator": "ImplementationWorker",
        "capsule_plan": {
            "capability_capsule_id": "cap.requirement-compiler-implementation",
            "dispatch_task_type": "implementation",
        },
    }
    capsule = pm_dispatch._capsule_submit_metadata(node)
    capsule, logical_operator = pm_dispatch._apply_role_capsule_override(
        role="evaluator",
        task_type="graph_eval",
        capsule_submit=capsule,
        logical_operator=capsule.get("logical_operator", ""),
    )

    assert capsule["capability_capsule_id"] == "cap.requirement-compiler-verification"
    assert capsule["dispatch_task_type"] == "graph_eval"
    assert capsule["capsule_plan"]["capability_capsule_id"] == "cap.requirement-compiler-verification"
    assert logical_operator == "Verifier"
    assert capsule["capsule_override_reason"] == "evaluator_role_requires_verification_capsule"


def test_graph_eval_pm_result_path_does_not_clobber_builder_result():
    path = pm_dispatch._pm_result_path_for_role("sprint-x", "B1", "evaluator", "graph_eval")
    assert path.name == "sprint-x.B1-eval.pm-result.md"
    builder_path = pm_dispatch._pm_result_path_for_role("sprint-x", "B1", "builder", "implementation")
    assert builder_path.name == "sprint-x.B1.pm-result.md"


def test_verification_capsule_accepts_graph_eval():
    capsule_path = ROOT / "config" / "capability-capsules" / "cap.requirement-compiler-verification.yaml"
    payload = yaml.safe_load(capsule_path.read_text(encoding="utf-8"))
    assert "graph_eval" in payload["applicability"]["task_types"]
    preconditions = payload["contract"]["preconditions"]
    task_type_precondition = next(item for item in preconditions if item.get("check") == "task_type_in")
    assert "graph_eval" in task_type_precondition["values"]


def test_enabled_codex_and_claude_evaluators_accept_graph_eval():
    registry = json.loads((ROOT / "config" / "physical-operators.json").read_text(encoding="utf-8"))
    operators = registry["operators"]
    codex_eval = operators["mini-codex-gpt55-medium-evaluator-1"]
    claude_eval = operators["mini-claude-sonnet-evaluator-print"]

    assert codex_eval["enabled"] is True
    assert codex_eval["deprecated"] is False
    assert codex_eval["provider"] == "openai"
    assert "graph_eval" in codex_eval["task_classes"]

    assert claude_eval["enabled"] is True
    assert claude_eval["deprecated"] is False
    assert claude_eval["provider"] == "anthropic"
    assert "graph_eval" in claude_eval["task_classes"]


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
