"""Policy decision module — N4 (s03-core-runtime).

Exports the three policy primitives:
- action_policy.classify_action: kind+command/path → RiskRule from 18-row RISK_CLASS_TABLE
- write_scope_policy.check: write_set vs node_write_scope → (PASS|DENY, reason)
- approval_policy.check: risk_class → approval_required bool

The RISK_CLASS_TABLE matches S02 policy-decisions.md §2 row-for-row.
"""

from .action_policy import (
    RISK_CLASS_TABLE,
    RiskRule,
    classify_action,
)
from .approval_policy import check as check_approval_required
from .write_scope_policy import check as check_write_scope

__all__ = [
    "RISK_CLASS_TABLE",
    "RiskRule",
    "classify_action",
    "check_write_scope",
    "check_approval_required",
]
