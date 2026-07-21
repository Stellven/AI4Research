"""failure_fingerprint.py — Failure fingerprint scoring with machine-readable explanations.

Applies fingerprint penalties for FINAL_REVIEW, PERFORMANCE_KERNEL_DEBUG,
and FAST_PROTOTYPE task types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Fingerprint penalty configs
FINGERPRINT_PENALTIES = {
    "FINAL_REVIEW": 0.25,
    "PERFORMANCE_KERNEL_DEBUG": 0.20,
    "FAST_PROTOTYPE": 0.10,
}


@dataclass
class FingerprintResult:
    fingerprint_type: str
    penalty: float
    explanation: str
    actor_id: str


def compute_fingerprint_penalty(
    actor_id: str,
    task_type: str,
    recent_failures: Optional[List[Dict]] = None,
) -> FingerprintResult:
    """Compute failure fingerprint penalty for an actor on a task type."""
    failures = recent_failures or []
    penalty = 0.0
    reasons = []

    base_penalty = FINGERPRINT_PENALTIES.get(task_type, 0.0)
    matching = [f for f in failures if f.get("actor_id") == actor_id and f.get("task_type") == task_type]

    if matching:
        count = len(matching)
        penalty = base_penalty * min(count, 3)  # cap at 3x
        reasons.append(f"{count} recent failure(s) for {task_type}")

    explanation = "; ".join(reasons) if reasons else "no fingerprint match"

    return FingerprintResult(
        fingerprint_type=task_type,
        penalty=penalty,
        explanation=explanation,
        actor_id=actor_id,
    )


def apply_antigravity_denial(
    task_type: str,
    actor_id: str,
    is_final_architecture: bool = False,
    is_final_verifier: bool = False,
    is_security_gate: bool = False,
    is_core_runtime: bool = False,
) -> Dict[str, bool]:
    """Apply Antigravity final-authority denial before scoring."""
    denial_reasons = {}

    if is_final_architecture:
        denial_reasons["final_architecture"] = True
    if is_final_verifier:
        denial_reasons["final_verifier"] = True
    if is_security_gate:
        denial_reasons["security_gate"] = True
    if is_core_runtime:
        denial_reasons["core_runtime_approval"] = True

    return denial_reasons
