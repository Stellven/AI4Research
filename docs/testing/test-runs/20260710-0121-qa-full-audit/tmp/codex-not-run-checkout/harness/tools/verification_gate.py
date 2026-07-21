"""verification_gate.py — Evidence-based verification gate for DAG completion.

Requires: patch/artifact evidence, test or benchmark evidence,
and independent verifier decision for critical DAG completion.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class VerificationGate:
    """Gate that enforces evidence requirements before DAG node completion."""

    def __init__(self, evidence_dir: Optional[Path] = None):
        self.evidence_dir = evidence_dir

    def check_code_task(
        self,
        has_patch: bool,
        has_test_evidence: bool,
        writer_actor_id: Optional[str] = None,
        verifier_actor_id: Optional[str] = None,
        verifier_decision: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check if a code task can PASS. Returns {passed, reasons}."""
        reasons = []
        if not has_patch:
            reasons.append("no_patch_artifact")
        if not has_test_evidence:
            reasons.append("no_test_evidence")

        # Same writer and verifier is rejected
        if writer_actor_id and verifier_actor_id and writer_actor_id == verifier_actor_id:
            reasons.append("writer_and_verifier_same_actor")

        if verifier_decision not in ("pass", "approved"):
            reasons.append("no_verifier_decision")

        return {
            "passed": len(reasons) == 0,
            "reasons": reasons,
        }

    def check_dag_done(
        self,
        has_patch: bool,
        has_test_or_benchmark: bool,
        verifier_decision: Optional[str] = None,
        verifier_actor_id: Optional[str] = None,
        writer_actor_id: Optional[str] = None,
        high_risk: bool = False,
        available_providers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Check if DAG can be marked DONE."""
        reasons = []
        if not has_patch:
            reasons.append("no_patch_artifact")
        if not has_test_or_benchmark:
            reasons.append("no_test_or_benchmark_evidence")
        if verifier_decision not in ("pass", "approved"):
            reasons.append("no_verifier_decision")
        if writer_actor_id and verifier_actor_id and writer_actor_id == verifier_actor_id:
            reasons.append("writer_and_verifier_same_actor")

        # High-risk tasks prefer cross-provider verifier
        if high_risk and available_providers and verifier_actor_id:
            providers = set()
            if writer_actor_id:
                for p in available_providers:
                    if p in writer_actor_id:
                        providers.add("writer_" + p)
                    if p in verifier_actor_id:
                        providers.add("verifier_" + p)
            # If same provider prefix for both, warn
            writer_prov = _extract_provider(writer_actor_id or "")
            verifier_prov = _extract_provider(verifier_actor_id or "")
            if writer_prov and verifier_prov and writer_prov == verifier_prov:
                reasons.append("high_risk_same_provider_verifier")

        return {
            "passed": len(reasons) == 0,
            "reasons": reasons,
        }

    def check_destructive_action(
        self,
        action: str,
        lease_acquired: bool,
    ) -> Dict[str, Any]:
        """Check if a destructive action is allowed."""
        destructive_actions = {
            "rm_rf", "force_push", "drop_table", "delete_branch",
            "secret_access", "git_push", "payment", "external_action",
            "out_of_scope_write",
        }
        if action in destructive_actions and not lease_acquired:
            return {"allowed": False, "reason": f"destructive_action_{action}_requires_lease"}
        if action in destructive_actions:
            return {"allowed": False, "reason": f"destructive_action_{action}_denied_by_policy"}
        return {"allowed": True, "reason": ""}


def _extract_provider(actor_id: str) -> Optional[str]:
    """Extract provider from actor_id (e.g., 'mini-claude-opus-planner' -> 'claude')."""
    known = ["claude", "gemini", "glm", "deepseek", "antigravity"]
    for p in known:
        if p in actor_id.lower():
            return p
    return None
