"""G3 — RepoSignalScoringOperator (L3 Scoring).

Computes six independent scores, noise_risk gate, signal class,
and actionability flags from snapshots + enrichments.
"""
from __future__ import annotations

from typing import Any

from ..models import RepoEnrichment, RepoSignal, RepoSnapshot, _gen_id, _json_dump, utc_now_iso


class RepoSignalScoringOperator:
    """Scores repos on six dimensions plus noise_risk gate."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.noise_gate = (self.config or {}).get("noise_risk_gate", 0.6)

    def run(
        self,
        snapshots: list[RepoSnapshot],
        enrichments: list[RepoEnrichment],
    ) -> list[RepoSignal]:
        enr_map = {e.repo_key: e for e in enrichments}
        signals: list[RepoSignal] = []

        for snap in snapshots:
            enr = enr_map.get(snap.repo_key)
            scores = self._compute_scores(snap, enr)
            noise = self._compute_noise(snap, enr)
            sig_class = self._classify(scores["github_hotspot"])
            flags = self._actionability(scores, noise)
            ev_ids = _json_load(enr.evidence_ids_json) if enr else []

            signals.append(RepoSignal(
                signal_id=_gen_id("sig-"),
                repo_key=snap.repo_key,
                scored_at=utc_now_iso(),
                score_window="daily",
                **scores,
                noise_risk=noise,
                signal_class=sig_class,
                actionability_flags_json=_json_dump(flags),
                evidence_ids_json=_json_dump(ev_ids),
            ))

        return signals

    def _compute_scores(
        self, snap: RepoSnapshot, enr: RepoEnrichment | None
    ) -> dict[str, float]:
        stars = snap.stars or 0
        delta24 = snap.stars_delta_24h or 0
        delta7d = snap.stars_delta_7d or 0

        hotspot = min(1.0, max(0.0, (delta24 * 2 + delta7d) / max(stars or 1, 100)))
        tech = 0.5 if (enr and enr.readme_compressed) else 0.1
        community = min(1.0, (snap.active_contributors_30d or 0) / 50)
        intervention = 0.3 if (snap.open_issues or 0) > 20 else 0.1
        open_proj = 0.2
        strategic = 0.2

        return {
            "github_hotspot": round(hotspot, 3),
            "technical_substance": round(tech, 3),
            "community_health": round(community, 3),
            "intervention_opportunity": round(intervention, 3),
            "open_project_opportunity": round(open_proj, 3),
            "strategic_fit": round(strategic, 3),
        }

    def _compute_noise(
        self, snap: RepoSnapshot, enr: RepoEnrichment | None
    ) -> float:
        noise = 0.0
        if snap.archived:
            noise += 0.7
        if (snap.stars or 0) < 50 and (snap.stars_delta_24h or 0) < 1:
            noise += 0.3
        return round(min(1.0, noise), 3)

    def _classify(self, hotspot: float) -> str:
        if hotspot > 0.7:
            return "hot"
        if hotspot > 0.3:
            return "rising"
        if hotspot > 0.1:
            return "sustained"
        return "cooling"

    def _actionability(
        self, scores: dict[str, float], noise: float
    ) -> list[str]:
        flags: list[str] = []
        if noise >= self.noise_gate:
            flags.append("noise_filtered")
        if scores["intervention_opportunity"] > 0.5:
            flags.append("intervention_candidate")
        if scores["open_project_opportunity"] > 0.5:
            flags.append("open_project_candidate")
        return flags


def _json_load(value: str) -> Any:
    import json
    if not value:
        return []
    return json.loads(value)
