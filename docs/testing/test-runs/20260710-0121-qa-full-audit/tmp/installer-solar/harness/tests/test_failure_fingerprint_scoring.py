"""Tests for failure_fingerprint.py — Fingerprint penalties."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from failure_fingerprint import (
    compute_fingerprint_penalty, apply_antigravity_denial,
    FINGERPRINT_PENALTIES,
)

def test_final_review_penalty():
    failures = [{"actor_id": "a1", "task_type": "FINAL_REVIEW"}]
    r = compute_fingerprint_penalty("a1", "FINAL_REVIEW", failures)
    assert r.penalty > 0
    assert r.fingerprint_type == "FINAL_REVIEW"
    print("PASS: final_review_penalty")

def test_performance_kernel_debug_penalty():
    failures = [{"actor_id": "a1", "task_type": "PERFORMANCE_KERNEL_DEBUG"}]
    r = compute_fingerprint_penalty("a1", "PERFORMANCE_KERNEL_DEBUG", failures)
    assert r.penalty > 0
    print("PASS: performance_kernel_debug_penalty")

def test_fast_prototype_penalty():
    failures = [{"actor_id": "a1", "task_type": "FAST_PROTOTYPE"}]
    r = compute_fingerprint_penalty("a1", "FAST_PROTOTYPE", failures)
    assert r.penalty > 0
    print("PASS: fast_prototype_penalty")

def test_no_failures_no_penalty():
    r = compute_fingerprint_penalty("a1", "FINAL_REVIEW", [])
    assert r.penalty == 0
    print("PASS: no_failures_no_penalty")

def test_antigravity_denial():
    d = apply_antigravity_denial("ARCH_DESIGN", "a1", is_final_architecture=True)
    assert "final_architecture" in d
    d2 = apply_antigravity_denial("VERIFY", "a1", is_final_verifier=True)
    assert "final_verifier" in d2
    d3 = apply_antigravity_denial("SECURITY", "a1", is_security_gate=True)
    assert "security_gate" in d3
    d4 = apply_antigravity_denial("CORE_RUNTIME", "a1", is_core_runtime=True)
    assert "core_runtime_approval" in d4
    print("PASS: antigravity_denial")

if __name__ == "__main__":
    test_final_review_penalty()
    test_performance_kernel_debug_penalty()
    test_fast_prototype_penalty()
    test_no_failures_no_penalty()
    test_antigravity_denial()
    print("\n5/5 passed")
