#!/usr/bin/env python3
"""Canonical static view of the shipped physical-operator catalog.

This module intentionally does not inspect leases, quota, credentials, or live
process state.  It answers the release/compile-time question shared by capsule
validation and physical-plan compilation: is this configured operator eligible
to be selected at all?
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HEALTHY_STATIC_STATUSES = {"", "ok", "healthy", "ready"}


def load_physical_operator_catalog(path: Path) -> dict[str, dict[str, Any]]:
    """Load the canonical ``operator_id -> specification`` mapping."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    operators = payload.get("operators") if isinstance(payload, dict) else None
    if not isinstance(operators, dict):
        raise ValueError(f"physical operator catalog has no operators mapping: {path}")
    return {
        str(operator_id): dict(spec)
        for operator_id, spec in operators.items()
        if isinstance(spec, dict)
    }


def static_operator_rejection_reasons(spec: dict[str, Any]) -> list[str]:
    """Return deterministic reasons a configured operator is not selectable."""
    reasons: list[str] = []
    if spec.get("enabled") is not True:
        reasons.append("disabled")
    # Legacy normalized operator records predate the explicit ``available``
    # field and the runtime has always interpreted omission as available.
    # Preserve that compatibility while rejecting an explicit false value.
    if spec.get("available", True) is not True:
        reasons.append("unavailable")
    if spec.get("deprecated") is True:
        reasons.append("deprecated")
    health = str(spec.get("health_status") or "").strip().lower()
    if health not in HEALTHY_STATIC_STATUSES:
        reasons.append(f"health_status={health}")
    return reasons


def is_operator_statically_selectable(spec: dict[str, Any]) -> bool:
    """Whether a catalog entry may participate in compile-time selection."""
    return not static_operator_rejection_reasons(spec)


def resolve_static_operator_reference(
    reference: str,
    operators: dict[str, dict[str, Any]],
    *,
    allow_profile: bool,
) -> dict[str, Any]:
    """Resolve an operator ID, or a profile only when no exact ID exists.

    Exact-ID precedence is deliberate.  A retired operator named ``old-builder``
    must not silently pass merely because its record happens to share the
    ``builder`` profile with a newer operator.
    """
    ref = str(reference or "").strip()
    exact = operators.get(ref)
    if exact is not None:
        reasons = static_operator_rejection_reasons(exact)
        return {
            "reference": ref,
            "resolution_kind": "operator_id",
            "matches": [ref],
            "selectable_matches": [] if reasons else [ref],
            "rejection_reasons": {ref: reasons} if reasons else {},
        }

    profile_matches = sorted(
        operator_id
        for operator_id, spec in operators.items()
        if allow_profile and str(spec.get("profile") or "").strip() == ref
    )
    selectable = [
        operator_id
        for operator_id in profile_matches
        if is_operator_statically_selectable(operators[operator_id])
    ]
    return {
        "reference": ref,
        "resolution_kind": "profile" if profile_matches else "missing",
        "matches": profile_matches,
        "selectable_matches": selectable,
        "rejection_reasons": {
            operator_id: static_operator_rejection_reasons(operators[operator_id])
            for operator_id in profile_matches
            if not is_operator_statically_selectable(operators[operator_id])
        },
    }
