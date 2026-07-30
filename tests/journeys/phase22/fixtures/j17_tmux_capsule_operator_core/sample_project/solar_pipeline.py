from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialCandidate:
    sample_id: str
    bandgap_ev: float
    stability_score: float
    synthesis_risk: float


def normalize_candidate(candidate: MaterialCandidate) -> dict[str, float | str]:
    score = candidate.bandgap_ev * candidate.stability_score
    return {
        "sample_id": candidate.sample_id,
        "bandgap_ev": candidate.bandgap_ev,
        "stability_score": candidate.stability_score,
        "synthesis_risk": candidate.synthesis_risk,
        "priority_score": round(score, 3),
    }


def rank_candidates(candidates: list[MaterialCandidate]) -> list[dict[str, float | str]]:
    rows = [normalize_candidate(candidate) for candidate in candidates]
    return sorted(rows, key=lambda row: float(row["priority_score"]), reverse=True)
