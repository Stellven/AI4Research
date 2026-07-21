"""Multi-direction exploration package.

S03 N6 implementation per S02 exploration-arch.md §7 (package layout) and
S03 design.md §3 (planner-locked constants DIRECTION_SCORE_WEIGHTS uniform +
DIRECTION_INITIAL_PROTOCOL='llm_propose_n_3' + ELIMINATION_THRESHOLD=None).
"""

from __future__ import annotations

from research.survey.explorer.config_defaults import (
    DIRECTION_INITIAL_PROTOCOL,
    DIRECTION_SCORE_DIMENSIONS,
    DIRECTION_SCORE_WEIGHTS,
    ELIMINATION_THRESHOLD,
)
from research.survey.explorer.exploration_run import exploration_run
from research.survey.explorer.log_writer import LogWriter
from research.survey.explorer.score_direction import score_direction
from research.survey.schemas import (
    EliminationRecord,
    ExplorationDirection,
    ExplorationRunResult,
)

__all__ = [
    "DIRECTION_INITIAL_PROTOCOL",
    "DIRECTION_SCORE_DIMENSIONS",
    "DIRECTION_SCORE_WEIGHTS",
    "ELIMINATION_THRESHOLD",
    "EliminationRecord",
    "ExplorationDirection",
    "ExplorationRunResult",
    "LogWriter",
    "exploration_run",
    "score_direction",
]
