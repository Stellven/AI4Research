"""actor_profiles.py — Capability, risk, and cost profiles for actor selection.

Loads profiles from agent-actors.json and provides routing decisions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME = Path.home()
HARNESS_DIR = Path.home() / ".solar" / "harness"
ACTORS_PATH = HARNESS_DIR / "config" / "agent-actors.json"

CAPABILITY_PROFILE_KEYS = [
    "architecture_reasoning", "code_impl", "root_cause_debug",
    "test_generation", "test_execution", "research_synthesis",
    "academic_critique", "browser_use", "gui_use", "long_context",
    "multi_agent_coordination", "speed",
]

RISK_PROFILE_KEYS = [
    "allowed_write_scope", "allowed_shell_scope", "allowed_network",
    "allowed_secrets", "destructive_actions", "git_commit",
    "git_push", "payment_or_external_action", "requires_human_for",
]

COST_PROFILE_KEYS = [
    "cost_tier", "token_budget_class", "quota_period",
    "reserve_ratio", "effort", "prefer_for", "avoid_for",
]


class ActorProfile:
    """Loaded profile for a single actor."""

    def __init__(self, actor_id: str, capability: Dict, risk: Dict, cost: Dict, raw: Dict):
        self.actor_id = actor_id
        self.capability = capability
        self.risk = risk
        self.cost = cost
        self.raw = raw

    @classmethod
    def from_actor_data(cls, data: Dict[str, Any]) -> "ActorProfile":
        return cls(
            actor_id=data["actor_id"],
            capability=data.get("capability_profile", {}),
            risk=data.get("risk_profile", {}),
            cost=data.get("cost_profile", {}),
            raw=data,
        )

    def check_risk_denial(self, required_capabilities: List[str]) -> Optional[str]:
        """Return denial reason if actor's risk profile blocks the task."""
        if self.risk.get("destructive_actions") == "denied" and "destructive" in required_capabilities:
            return "destructive_actions_denied"
        if self.risk.get("git_push") == "denied" and "git_push" in required_capabilities:
            return "git_push_denied"
        if self.risk.get("payment_or_external_action") == "denied" and "payment" in required_capabilities:
            return "payment_denied"
        if self.risk.get("allowed_secrets") == "secret_ref_only" and "raw_secret_access" in required_capabilities:
            return "secrets_denied"
        return None

    def check_cost_reserve(self, task_type: str) -> Optional[str]:
        """Return reason if actor should be reserved, not used for this task."""
        avoid = self.cost.get("avoid_for", [])
        prefer = self.cost.get("prefer_for", [])
        if task_type.lower() in [a.lower() for a in avoid]:
            return f"task_type '{task_type}' in avoid_for"
        return None


def load_profiles(path: Optional[Path] = None) -> Dict[str, ActorProfile]:
    """Load all actor profiles from agent-actors.json."""
    p = path or ACTORS_PATH
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    actors = data.get("actors", {})
    return {
        aid: ActorProfile.from_actor_data(ad)
        for aid, ad in actors.items()
    }
