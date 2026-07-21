#!/usr/bin/env python3
import sys
from pathlib import Path

# Insert lib to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import multi_task_runner as m
import operator_runtime
operator_runtime.get_operator_runtime_state = lambda op_id: "idle"

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

# Override load_physical_operators
m.load_physical_operators = lambda: mock_registry

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


if __name__ == "__main__":
    test_preferred_operator_override()
    test_task_type_matching()
    test_capability_scores()
    test_preferred_operator_classes()
    test_constraints()
    test_quota_reserve()
    test_verifier_conflict()
    print("ALL TESTS PASSED SUCCESSFULLY!")
