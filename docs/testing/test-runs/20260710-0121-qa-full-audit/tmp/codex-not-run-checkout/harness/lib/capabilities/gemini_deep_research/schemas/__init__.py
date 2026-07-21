"""C1 — stage handoff schemas + append-only event persistence."""

from .models import (
    MAX_QUESTION_LEN,
    AsyncState,
    DRPlan,
    DRResult,
    DRRunHandle,
    InvalidResearchRequest,
    OptimizedPrompt,
    Phase,
    Reference,
    ResearchRequest,
    ResultStatus,
    Source,
)
from .persistence import Event, EventLog

__all__ = [
    "MAX_QUESTION_LEN",
    "AsyncState",
    "DRPlan",
    "DRResult",
    "DRRunHandle",
    "InvalidResearchRequest",
    "OptimizedPrompt",
    "Phase",
    "Reference",
    "ResearchRequest",
    "ResultStatus",
    "Source",
    "Event",
    "EventLog",
]
