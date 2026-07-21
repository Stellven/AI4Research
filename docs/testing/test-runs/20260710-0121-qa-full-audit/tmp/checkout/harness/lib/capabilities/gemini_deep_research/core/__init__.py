"""C2 — outcome state machine + O1-O6 controller API + event-replay."""

from .controller import (
    DEFAULT_TEMPLATE_ID,
    GeminiDRController,
    OptimizeFailed,
    RunSnapshot,
)
from .ports import BrowserOperatorPort
from .retry import MIN_REFS, Disposition, RetryPolicy, SuccessCheck, evaluate_success
from .state_machine import (
    TERMINAL_STATES,
    ControllerState,
    InvalidTransition,
    all_states,
    assert_transition,
    can_transition,
)

__all__ = [
    "DEFAULT_TEMPLATE_ID",
    "GeminiDRController",
    "OptimizeFailed",
    "RunSnapshot",
    "BrowserOperatorPort",
    "MIN_REFS",
    "Disposition",
    "RetryPolicy",
    "SuccessCheck",
    "evaluate_success",
    "TERMINAL_STATES",
    "ControllerState",
    "InvalidTransition",
    "all_states",
    "assert_transition",
    "can_transition",
]
