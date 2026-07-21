"""Approval-required policy.

check(risk_class) -> bool

Default mapping (matches S02 policy-decisions.md §2.3):
- high  → True (approval required)
- medium → False
- low    → False
- n/a / unknown → True (POLICY_WARN — safe default escalates)
"""

from __future__ import annotations


_LOOKUP = {
    "high": True,
    "medium": False,
    "low": False,
}


def check(risk_class: str) -> bool:
    if risk_class is None:
        return True
    key = str(risk_class).strip().lower()
    if key in _LOOKUP:
        return _LOOKUP[key]
    return True
