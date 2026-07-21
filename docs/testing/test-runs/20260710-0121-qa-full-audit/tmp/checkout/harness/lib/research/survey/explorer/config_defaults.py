"""Planner-locked constants for survey/explorer/.

S03 N6 implementation per S02 exploration-arch.md §5 + S03 design.md §3
"Planner-Locked Non-Builder Decisions": uniform 4-dimension weights,
DIRECTION_INITIAL_PROTOCOL='llm_propose_n_3', ELIMINATION_THRESHOLD=None
(threshold deferred to S05 fixture-driven calibration).
"""

from __future__ import annotations

# Per design.md §3 row "Direction scoring weights":
# uniform baseline {"source_coverage": 1.0, "novelty": 1.0,
# "feasibility": 1.0, "evidence_density": 1.0}; 4 dimensions equal weight.
DIRECTION_SCORE_WEIGHTS: dict[str, float] = {
    "source_coverage": 1.0,
    "novelty": 1.0,
    "feasibility": 1.0,
    "evidence_density": 1.0,
}

# Ordered list of scoring dimension names (matches DIRECTION_SCORE_WEIGHTS keys).
DIRECTION_SCORE_DIMENSIONS: tuple[str, ...] = (
    "source_coverage",
    "novelty",
    "feasibility",
    "evidence_density",
)

# Per design.md §3 row "Direction initial selection protocol":
# llm_propose_n_3: start with 3 candidate directions via planner candidate
# generation + dedup. S03 only locks the protocol name; the propose hook
# lives in survey/planner.py (frozen) and is not modified here.
DIRECTION_INITIAL_PROTOCOL: str = "llm_propose_n_3"

# Per design.md §3 + exploration-arch.md §9: numeric threshold values for
# elimination are intentionally absent from S03. S05 fixture-driven
# calibration will set the threshold; until then exploration_run() falls back
# to "eliminate the single lowest-scoring direction when count >= 2".
ELIMINATION_THRESHOLD: float | None = None

# Canonical taxonomy used when an ExplorationDirection lacks a SourceMatrix
# (mirrors gates/config_defaults SOURCE_TAXONOMY high-authority slice; the
# explorer scorer must remain pure and cannot import the gates registry).
DEFAULT_HIGH_AUTHORITY_TYPES: tuple[str, ...] = (
    "paper",
    "code",
    "official",
    "benchmark",
)
