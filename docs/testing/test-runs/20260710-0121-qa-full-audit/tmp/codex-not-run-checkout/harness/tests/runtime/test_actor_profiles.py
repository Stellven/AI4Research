"""Tests for actor_profiles.py — Profile routing decisions."""
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from actor_profiles import ActorProfile, load_profiles, ACTORS_PATH

def test_profile_risk_denial():
    p = ActorProfile("a1", {}, {
        "destructive_actions": "denied",
        "git_push": "denied",
        "payment_or_external_action": "denied",
        "allowed_secrets": "secret_ref_only",
    }, {}, {})
    assert p.check_risk_denial(["destructive"]) == "destructive_actions_denied"
    assert p.check_risk_denial(["git_push"]) == "git_push_denied"
    assert p.check_risk_denial(["payment"]) == "payment_denied"
    assert p.check_risk_denial(["raw_secret_access"]) == "secrets_denied"
    assert p.check_risk_denial(["read"]) is None
    print("PASS: profile_risk_denial")

def test_profile_cost_reserve():
    p = ActorProfile("a1", {}, {}, {
        "prefer_for": ["planning", "architecture"],
        "avoid_for": ["bulk-extraction", "cheap-background"],
    }, {})
    assert p.check_cost_reserve("bulk-extraction") is not None
    assert p.check_cost_reserve("cheap-background") is not None
    assert p.check_cost_reserve("planning") is None
    print("PASS: profile_cost_reserve")

def test_load_profiles():
    if not ACTORS_PATH.exists():
        print("SKIP: agent-actors.json not found")
        return
    profiles = load_profiles()
    assert len(profiles) > 0
    for aid, p in profiles.items():
        assert p.actor_id == aid
        assert isinstance(p.capability, dict)
        assert isinstance(p.risk, dict)
        assert isinstance(p.cost, dict)
    print(f"PASS: load_profiles ({len(profiles)} actors)")

if __name__ == "__main__":
    test_profile_risk_denial()
    test_profile_cost_reserve()
    test_load_profiles()
    print("\n3/3 passed")
