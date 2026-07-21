"""U1 — autopilot/DAG auto-activation + role routing."""

from .auto_activation import (
    ROLE_BUILDER,
    ROLE_EVALUATOR,
    ROLE_HUMAN,
    ROLE_PLANNER,
    ActivationDecision,
    decide_run_role,
    ready_nodes,
    route_sprint,
)

__all__ = [
    "ROLE_BUILDER",
    "ROLE_EVALUATOR",
    "ROLE_HUMAN",
    "ROLE_PLANNER",
    "ActivationDecision",
    "decide_run_role",
    "ready_nodes",
    "route_sprint",
]
