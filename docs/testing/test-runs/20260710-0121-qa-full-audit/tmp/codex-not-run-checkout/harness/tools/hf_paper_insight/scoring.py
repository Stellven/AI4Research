"""SignalScorer — multi-objective scoring + packet gate check.

Per interfaces §5: compute_scores, packet_gate_check.
Per design D4: YAML profile + hardcoded fallback.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from schema import (
    PaperCanonical,
    PaperEnrichment,
    PaperSignal,
    PaperTaxonomy,
    _gen_id,
    _utc_now,
)


# Hardcoded fallback weights (per design D4: hardcoded fallback when no YAML profile)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "attention.upvotes": 0.15,
    "attention.downloads": 0.10,
    "attention.trending": 0.05,
    "quality.peer_reviewed": 0.10,
    "quality.abstract_length": 0.05,
    "quality.has_code": 0.05,
    "reproducibility.has_repo": 0.10,
    "reproducibility.has_dataset": 0.05,
    "reproducibility.has_demo": 0.05,
    "ecosystem.linked_models": 0.05,
    "ecosystem.linked_spaces": 0.05,
    "ecosystem.community_engagement": 0.05,
    "productization.stack_relevance": 0.05,
    "productization.maturity": 0.05,
    "productization.license_open": 0.05,
}


@dataclass
class ScoreProfile:
    name: str = "default"
    weights: dict = field(default_factory=lambda: dict(_DEFAULT_WEIGHTS))


def _load_weights_from_dict(profile_data: dict) -> ScoreProfile:
    return ScoreProfile(
        name=profile_data.get("name", "loaded"),
        weights=profile_data.get("weights", dict(_DEFAULT_WEIGHTS)),
    )


class SignalScorer:
    """Computes multi-objective scores for papers.

    5 composite scores: research_signal, insight_report, experiment,
    open_project, deep_research_seed.
    4 raw signals: attention, novelty, reproducibility, industry_coupling.
    """

    def __init__(self, profile: Optional[ScoreProfile] = None) -> None:
        self._profile = profile or ScoreProfile()

    def compute_scores(
        self,
        canonical: PaperCanonical,
        enrichment: PaperEnrichment,
        taxonomy: PaperTaxonomy,
        profile_name: str = "",
    ) -> PaperSignal:
        hf_meta = json.loads(enrichment.hf_metadata_json)
        arxiv_meta = json.loads(enrichment.arxiv_metadata_json)
        hf_assets = json.loads(enrichment.hf_assets_json)
        github = json.loads(enrichment.github_repo_json)

        attention = self._score_attention(hf_meta, arxiv_meta)
        novelty = self._score_novelty(arxiv_meta, taxonomy)
        reproducibility = self._score_reproducibility(hf_assets, github, arxiv_meta)
        industry = self._score_industry(hf_meta, hf_assets, taxonomy)

        w = self._profile.weights
        research = (
            attention * 0.3 + novelty * 0.3 +
            reproducibility * 0.2 + industry * 0.2
        )
        insight = (
            novelty * 0.4 + attention * 0.3 +
            reproducibility * 0.15 + industry * 0.15
        )
        experiment = (
            reproducibility * 0.5 + industry * 0.25 +
            attention * 0.15 + novelty * 0.1
        )
        open_project = (
            reproducibility * 0.4 + industry * 0.3 +
            attention * 0.2 + novelty * 0.1
        )
        deep_research = (
            novelty * 0.5 + attention * 0.2 +
            reproducibility * 0.15 + industry * 0.15
        )

        score_inputs = {
            "attention_raw": round(attention, 3),
            "novelty_raw": round(novelty, 3),
            "reproducibility_raw": round(reproducibility, 3),
            "industry_raw": round(industry, 3),
        }

        return PaperSignal(
            signal_id=_gen_id("sig-"),
            paper_id=canonical.paper_id,
            research_signal_score=round(research, 3),
            insight_report_score=round(insight, 3),
            experiment_score=round(experiment, 3),
            open_project_score=round(open_project, 3),
            deep_research_seed_score=round(deep_research, 3),
            attention_signal=round(attention, 3),
            novelty_signal=round(novelty, 3),
            reproducibility_signal=round(reproducibility, 3),
            industry_coupling_signal=round(industry, 3),
            score_profile=profile_name or self._profile.name,
            score_inputs_json=json.dumps(score_inputs),
        )

    def packet_gate_check(
        self, signal: PaperSignal, enrichment: PaperEnrichment
    ) -> dict:
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        hf_meta = json.loads(enrichment.hf_metadata_json)
        arxiv_meta = json.loads(enrichment.arxiv_metadata_json)
        hf_assets = json.loads(enrichment.hf_assets_json)

        # Source check: at least one provider succeeded
        provider_success = json.loads(enrichment.provider_success_json)
        has_source = bool(provider_success)
        checks["has_source"] = has_source
        if not has_source:
            reasons.append("no_provider_succeeded")

        # Metadata check: at least abstract or description
        has_abstract = bool(arxiv_meta.get("abstract", "").strip())
        has_desc = bool(hf_meta.get("card_data", {}).get("description", "").strip()) if isinstance(hf_meta.get("card_data"), dict) else False
        checks["has_metadata"] = has_abstract or has_desc
        if not checks["has_metadata"]:
            reasons.append("no_abstract_or_description")

        # Code link check
        has_repo = bool(hf_assets.get("linked_models")) or bool(json.loads(enrichment.github_repo_json).get("url"))
        checks["has_code_link"] = has_repo
        if not has_repo:
            reasons.append("no_code_link")

        # Minimal provenance
        has_provenance = bool(arxiv_meta.get("arxiv_id")) or bool(hf_meta.get("repo_id"))
        checks["has_provenance"] = has_provenance
        if not has_provenance:
            reasons.append("no_provenance_id")

        # Score threshold
        min_score = max(
            signal.research_signal_score,
            signal.insight_report_score,
            signal.experiment_score,
        )
        checks["meets_score_threshold"] = min_score >= 0.1
        if not checks["meets_score_threshold"]:
            reasons.append("all_scores_below_threshold")

        passed = all(checks.values())
        return {
            "passed": passed,
            "checks": checks,
            "reasons": reasons,
        }

    def _score_attention(self, hf_meta: dict, arxiv_meta: dict) -> float:
        score = 0.0
        downloads = hf_meta.get("downloads", 0) if isinstance(hf_meta, dict) else 0
        if downloads > 10000:
            score += 0.3
        elif downloads > 1000:
            score += 0.2
        elif downloads > 100:
            score += 0.1

        likes = hf_meta.get("likes", 0) if isinstance(hf_meta, dict) else 0
        if likes > 100:
            score += 0.2
        elif likes > 50:
            score += 0.15
        elif likes > 10:
            score += 0.1

        tags = hf_meta.get("tags", []) if isinstance(hf_meta, dict) else []
        if tags and len(tags) > 5:
            score += 0.1

        return min(score, 1.0)

    def _score_novelty(self, arxiv_meta: dict, taxonomy: PaperTaxonomy) -> float:
        score = 0.4
        if arxiv_meta.get("abstract"):
            score += 0.2
        if taxonomy.method in ("pretraining", "architecture", "generation"):
            score += 0.2
        if taxonomy.domain in ("nlp", "cv", "multimodal", "rl"):
            score += 0.1
        if taxonomy.confidence > 0.7:
            score += 0.1
        return min(score, 1.0)

    def _score_reproducibility(self, hf_assets: dict, github: dict, arxiv_meta: dict) -> float:
        score = 0.0
        if hf_assets.get("linked_models"):
            score += 0.3
        if hf_assets.get("linked_datasets"):
            score += 0.2
        if hf_assets.get("linked_spaces") or hf_assets.get("demo_urls"):
            score += 0.2
        if github.get("url") or github.get("stars"):
            score += 0.2
        if arxiv_meta.get("abstract"):
            score += 0.1
        return min(score, 1.0)

    def _score_industry(self, hf_meta: dict, hf_assets: dict, taxonomy: PaperTaxonomy) -> float:
        score = 0.0
        if taxonomy.maturity == "prototype":
            score += 0.3
        elif taxonomy.maturity == "peer_reviewed":
            score += 0.2

        if taxonomy.stack_layer in ("inference", "training", "adaptation"):
            score += 0.3
        elif taxonomy.stack_layer == "model":
            score += 0.1

        if hf_assets.get("demo_urls"):
            score += 0.2
        if hf_meta.get("pipeline_tag"):
            score += 0.1
        return min(score, 1.0)
