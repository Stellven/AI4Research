"""Tests for Antigravity placement policy — final-authority denial before scoring."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from failure_fingerprint import apply_antigravity_denial

def test_final_architecture_denial():
    d = apply_antigravity_denial("task", "a1", is_final_architecture=True)
    assert "final_architecture" in d
    assert d["final_architecture"] is True
    print("PASS: final_architecture_denial")

def test_final_verifier_denial():
    d = apply_antigravity_denial("task", "a1", is_final_verifier=True)
    assert "final_verifier" in d
    print("PASS: final_verifier_denial")

def test_security_gate_denial():
    d = apply_antigravity_denial("task", "a1", is_security_gate=True)
    assert "security_gate" in d
    print("PASS: security_gate_denial")

def test_core_runtime_denial():
    d = apply_antigravity_denial("task", "a1", is_core_runtime=True)
    assert "core_runtime_approval" in d
    print("PASS: core_runtime_denial")

def test_no_denial_for_normal():
    d = apply_antigravity_denial("task", "a1")
    assert len(d) == 0
    print("PASS: no_denial_for_normal")

if __name__ == "__main__":
    test_final_architecture_denial()
    test_final_verifier_denial()
    test_security_gate_denial()
    test_core_runtime_denial()
    test_no_denial_for_normal()
    print("\n5/5 passed")
