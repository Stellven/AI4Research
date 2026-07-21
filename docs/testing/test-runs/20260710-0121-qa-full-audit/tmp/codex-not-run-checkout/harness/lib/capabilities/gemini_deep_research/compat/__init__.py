"""C3 — backward-compat adapter (operator binding + status projection)."""

from .operator_adapter import (
    LI_PROFESSOR_TEMPLATE_ID,
    DeepResearchBrowserAdapter,
    DeepResearchGeminiAdapter,
)
from .status_projection import project_status

__all__ = [
    "LI_PROFESSOR_TEMPLATE_ID",
    "DeepResearchBrowserAdapter",
    "DeepResearchGeminiAdapter",
    "project_status",
]
