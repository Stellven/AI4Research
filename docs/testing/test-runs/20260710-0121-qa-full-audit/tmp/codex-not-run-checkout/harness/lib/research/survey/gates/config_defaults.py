"""Planner-locked constants for survey quality gates.

Values defined here are the S03 behavioural baseline.  They may be overridden
via config in S04/S05, but S03 builders must reference these constants rather
than hard-coding values.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# O1 — Source quality distribution
# ---------------------------------------------------------------------------

SOURCE_TAXONOMY: list[str] = [
    "paper",
    "code",
    "official",
    "benchmark",
    "web",
    "blog",
    "wiki",
]

HIGH_AUTHORITY_TYPES: frozenset[str] = frozenset(
    ["paper", "code", "official", "benchmark"]
)

# ---------------------------------------------------------------------------
# O2 — Argument density (5 dimension detectors)
# ---------------------------------------------------------------------------

DIMENSION_DETECTORS: dict[str, dict[str, list[str]]] = {
    "mechanism_comparison": {
        "keywords": ["versus", "对比", "compare", "vs."],
        "patterns": ["X优于Y", "outperforms"],
    },
    "method_taxonomy": {
        "keywords": ["category", "taxonomy", "类型", "分类"],
        "min_subtypes": 2,
    },
    "evaluation_protocol": {
        "keywords": ["benchmark", "evaluation", "metric", "评测"],
    },
    "failure_negative_evidence": {
        "keywords": ["fail", "negative", "反例", "limitation"],
    },
    "engineering_implication": {
        "keywords": ["implication", "deploy", "production", "engineering"],
    },
}

# ---------------------------------------------------------------------------
# O3 — Contradiction matrix
# ---------------------------------------------------------------------------

CLAIM_GRANULARITY: str = "dual_indexing"
# claim_id format: "{chapter_id}.{section_id}.{seq}"
# chapter-level claims: "chapter.{chapter_id}.summary"

# ---------------------------------------------------------------------------
# O4 — Multi-direction exploration
# ---------------------------------------------------------------------------

DIRECTION_SCORE_WEIGHTS: dict[str, float] = {
    "source_coverage": 1.0,
    "novelty": 1.0,
    "feasibility": 1.0,
    "evidence_density": 1.0,
}

DIRECTION_INITIAL_PROTOCOL: str = "llm_propose_n_3"
# Starting 3 candidate directions; dedup via survey/planner.py interface.
