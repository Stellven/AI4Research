"""Tests for verification_gate.py — Evidence gate enforcement."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from verification_gate import VerificationGate

def test_reject_code_task_without_test():
    vg = VerificationGate()
    r = vg.check_code_task(has_patch=True, has_test_evidence=False, verifier_decision="pass")
    assert not r["passed"]
    assert "no_test_evidence" in r["reasons"]
    print("PASS: reject_code_task_without_test")

def test_reject_dag_done_without_verifier():
    vg = VerificationGate()
    r = vg.check_dag_done(has_patch=True, has_test_or_benchmark=True, verifier_decision=None)
    assert not r["passed"]
    assert "no_verifier_decision" in r["reasons"]
    print("PASS: reject_dag_done_without_verifier")

def test_reject_same_writer_verifier():
    vg = VerificationGate()
    r = vg.check_code_task(
        has_patch=True, has_test_evidence=True,
        writer_actor_id="actor-1", verifier_actor_id="actor-1",
        verifier_decision="pass",
    )
    assert not r["passed"]
    assert "writer_and_verifier_same_actor" in r["reasons"]
    print("PASS: reject_same_writer_verifier")

def test_high_risk_cross_provider():
    vg = VerificationGate()
    r = vg.check_dag_done(
        has_patch=True, has_test_or_benchmark=True,
        verifier_decision="pass",
        writer_actor_id="mini-claude-opus-planner",
        verifier_actor_id="mini-claude-sonnet-builder",
        high_risk=True,
        available_providers=["claude", "gemini"],
    )
    assert "high_risk_same_provider_verifier" in r["reasons"]
    print("PASS: high_risk_cross_provider")

def test_deny_destructive_actions():
    vg = VerificationGate()
    for action in ["rm_rf", "force_push", "secret_access", "git_push", "payment", "external_action", "out_of_scope_write"]:
        r = vg.check_destructive_action(action, lease_acquired=True)
        assert not r["allowed"], f"{action} should be denied"
    print("PASS: deny_destructive_actions")

def test_reserve_premium_for_high_value():
    from actor_profiles import ActorProfile
    p = ActorProfile("premium-actor", {}, {}, {
        "prefer_for": ["ARCH_DESIGN", "ROOT_CAUSE_DEBUG", "FINAL_REVIEW"],
        "avoid_for": ["BULK_DOC_EDIT", "TRIVIAL_RENAME", "GREP_SCAN"],
    }, {})
    for high in ["ARCH_DESIGN", "ROOT_CAUSE_DEBUG", "FINAL_REVIEW"]:
        assert p.check_cost_reserve(high) is None
    for low in ["BULK_DOC_EDIT", "TRIVIAL_RENAME", "GREP_SCAN"]:
        assert p.check_cost_reserve(low) is not None
    print("PASS: reserve_premium_for_high_value")

if __name__ == "__main__":
    test_reject_code_task_without_test()
    test_reject_dag_done_without_verifier()
    test_reject_same_writer_verifier()
    test_high_risk_cross_provider()
    test_deny_destructive_actions()
    test_reserve_premium_for_high_value()
    print("\n6/6 passed")
