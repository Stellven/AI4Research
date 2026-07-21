"""Convert AutoSci idea candidates to `idea_candidate.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None, *, status: str | None = None) -> dict[str, Any]:
    ideas = list(raw.get("ideas") or [{
        "idea_id": "idea-001",
        "title": "Fixture research idea",
        "hypothesis": "A bounded fixture can verify the adapter contract before real backend execution.",
        "approach": "Run deterministic fixture conversions and inspect Solar Evidence ABI output.",
        "origin_evidence_ids": ["claim-001"],
        "novelty_hypothesis": "This is a test fixture, not a novelty claim.",
    }])
    return evidence_base(
        "idea_candidate.v1",
        envelope,
        {"ideas": ideas},
        artifacts=list(raw.get("artifacts") or []),
        status=status or str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Fixture idea generation is grounded only in supplied local evidence."]),
    )
