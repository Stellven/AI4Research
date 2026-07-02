"""Convert AutoSci idea evaluations to `idea_evaluation.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    evaluations = list(raw.get("evaluations") or [{
        "idea_id": "idea-001",
        "novelty": 0.5,
        "feasibility": 0.5,
        "recommendation": "inconclusive",
        "risks": ["No supplied idea evidence was available."],
        "evidence_ids": ["idea-001"],
        "novelty_rationale": "Novelty could not be established from fixture evidence.",
        "feasibility_rationale": "Feasibility could not be established from fixture evidence.",
    }])
    return evidence_base(
        "idea_evaluation.v1",
        envelope,
        {"evaluations": evaluations},
        artifacts=list(raw.get("artifacts") or []),
        limitations=list(raw.get("limitations") or ["Fixture evaluation is bounded to supplied local evidence."]),
    )
