"""One static admission rule for capability presentation and candidate search.

Declaration checks are not live execution evidence. Per-node I/O/effect/trust
checks and dynamic operator availability remain separate deterministic gates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def rejection_reasons(capsule: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if capsule.get("status", "stable") != "stable":
        reasons.append("CAPSULE_NOT_STABLE")
    verification = capsule.get("verification") or {}
    if not (verification.get("self_checks") or verification.get("pass_conditions")
            or verification.get("external_required")):
        reasons.append("VERIFICATION_CONTRACT_MISSING")
    if not (capsule.get("implementation") or {}).get("declared"):
        reasons.append("IMPLEMENTATION_UNDECLARED")
    if not (capsule.get("operator_compatibility") or {}).get("selectable_preferred"):
        reasons.append("NO_SELECTABLE_PHYSICAL_OPERATOR")
    if not capsule.get("task_types"):
        reasons.append("TASK_TYPE_UNDECLARED")
    return reasons


def model_contract(capsule: dict[str, Any]) -> dict[str, Any]:
    """Preserve contract meanings; never let an optimistic cached flag win."""
    result = deepcopy(capsule)
    reasons = rejection_reasons(capsule)
    result["executable"] = not reasons
    result["unavailability_reasons"] = reasons
    return result
