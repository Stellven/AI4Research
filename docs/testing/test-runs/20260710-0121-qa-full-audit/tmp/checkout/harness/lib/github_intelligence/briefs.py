"""GitHub Project Intelligence — planning brief API surface.

Node: C4_cards_briefs_reports_pipeline
Write-scope: harness/lib/github_intelligence/briefs.py

Brief functions live here; card functions live in cards.py.
Constraint: a planning brief requires a VERIFIED analysis card (S02 §A4).
"""
from __future__ import annotations

from github_intelligence.cards import (
    create_planning_brief,
    get_briefs_for_card,
    make_brief_id,
)

__all__ = [
    "create_planning_brief",
    "get_briefs_for_card",
    "make_brief_id",
]
