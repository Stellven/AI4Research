"""Main entry: exploration_run(question, candidates).

S03 N6 implementation per S02 exploration-arch.md §6 (function interface) +
§10 (failure modes) and S03 design.md §3 (planner-locked weights /
DIRECTION_INITIAL_PROTOCOL='llm_propose_n_3' / ELIMINATION_THRESHOLD=None).
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from research.survey.explorer.config_defaults import (
    DIRECTION_SCORE_WEIGHTS,
    ELIMINATION_THRESHOLD,
)
from research.survey.explorer.log_writer import LogWriter
from research.survey.explorer.score_direction import score_breakdown, score_direction
from research.survey.schemas import (
    EliminationRecord,
    ExplorationDirection,
    ExplorationRunResult,
    SourceMatrix,
)

# Placeholder ISO 8601 UTC timestamp. exploration_run() never reads a wall
# clock directly (the deterministic stop rules in design.md §9 forbid it);
# callers inject a clock callable so test runs stay reproducible. This
# placeholder satisfies the "decision_ts must be set" constraint when no
# clock is provided.
_PLACEHOLDER_TS = "1970-01-01T00:00:00Z"


def _stable_run_id(question: Any) -> str:
    for attr in ("run_id", "question_id", "id"):
        value = getattr(question, attr, None)
        if isinstance(value, str) and value:
            return value
    if isinstance(question, str) and question:
        return question
    return "exploration-run-unknown"


def _default_source_provider(direction: ExplorationDirection) -> list[dict[str, Any]]:
    return []


def _format_kill_reason(score: float, breakdown: dict[str, float]) -> str:
    if not breakdown:
        return f"score {score:.4f}; no scoring dimensions evaluated"
    weakest_dim, weakest_value = min(breakdown.items(), key=lambda kv: (kv[1], kv[0]))
    return (
        f"score {score:.4f} below elimination boundary; "
        f"weakest dimension {weakest_dim}={weakest_value:.4f}"
    )


def _select_eliminations(
    scored: list[tuple[ExplorationDirection, float]],
    threshold: float | None,
) -> set[str]:
    """Decide which direction_ids to eliminate.

    With threshold None (S03 default per ELIMINATION_THRESHOLD), eliminate
    the single lowest-scoring direction when ≥ 2 candidates exist
    (deterministic tiebreak by direction_id ascending). With a threshold,
    eliminate every direction whose score is strictly below the threshold.
    """
    if not scored:
        return set()
    if threshold is not None:
        return {d.direction_id for d, s in scored if s < threshold}
    if len(scored) < 2:
        return set()
    min_score = min(s for _, s in scored)
    losers = sorted(
        (d for d, s in scored if s == min_score),
        key=lambda d: d.direction_id,
    )
    return {losers[0].direction_id}


def exploration_run(
    question: Any,
    candidates: Iterable[ExplorationDirection],
    *,
    source_provider: Callable[[ExplorationDirection], list[dict[str, Any]]]
    | None = None,
    log_path: str | os.PathLike[str] | None = None,
    clock: Callable[[], str] | None = None,
    source_matrix: SourceMatrix | None = None,
    weights: Mapping[str, float] | None = None,
    elimination_threshold: float | None = ELIMINATION_THRESHOLD,
) -> ExplorationRunResult:
    """Score candidate directions, eliminate the weakest, and return result.

    Pure with respect to all injected callables (``source_provider``,
    ``clock``). No wall-clock reads, no entropy sources, no LLM. The only
    external IO is the optional ``log_path`` written via :class:`LogWriter`.
    """
    candidates_list = list(candidates)
    weights_map = dict(weights) if weights is not None else dict(DIRECTION_SCORE_WEIGHTS)
    provider = source_provider if source_provider is not None else _default_source_provider
    clock_fn = clock if clock is not None else (lambda: _PLACEHOLDER_TS)

    run_id = _stable_run_id(question)

    resolved_log_path: pathlib.Path | None
    if log_path is not None:
        resolved_log_path = pathlib.Path(log_path)
    else:
        resolved_log_path = None
    log_writer: LogWriter | None = LogWriter(resolved_log_path) if resolved_log_path else None

    scored: list[tuple[ExplorationDirection, float, dict[str, float], list[dict[str, Any]]]] = []
    for direction in candidates_list:
        sources = provider(direction)
        sources_list = list(sources)
        breakdown = score_breakdown(direction, sources_list)
        score = score_direction(direction, sources_list, weights_map)
        scored.append((direction, score, breakdown, sources_list))

    eliminate_ids = _select_eliminations(
        [(d, s) for d, s, _b, _src in scored],
        elimination_threshold,
    )

    selected: list[ExplorationDirection] = []
    eliminated: list[ExplorationDirection] = []
    for direction, score, breakdown, sources_list in scored:
        if direction.direction_id in eliminate_ids:
            kill_reason = _format_kill_reason(score, breakdown)
            evidence_refs = [
                str(s.get("source_id", f"src-{idx}"))
                for idx, s in enumerate(sources_list)
            ]
            if not evidence_refs:
                evidence_refs = [direction.direction_id]
            decision_ts = clock_fn() or _PLACEHOLDER_TS
            record = EliminationRecord(
                direction_id=direction.direction_id,
                direction_name=direction.direction_name,
                score=score,
                kill_reason=kill_reason,
                evidence_refs=evidence_refs,
                decision_ts=decision_ts,
                direction_query=direction.query,
                candidate_count=len(sources_list),
                score_breakdown=dict(breakdown),
            )
            updated = ExplorationDirection(
                direction_id=direction.direction_id,
                direction_name=direction.direction_name,
                query=direction.query,
                status="eliminated",
                source_matrix=direction.source_matrix,
                elimination_record=record,
            )
            eliminated.append(updated)
            if log_writer is not None:
                log_writer.append(record)
        else:
            updated = ExplorationDirection(
                direction_id=direction.direction_id,
                direction_name=direction.direction_name,
                query=direction.query,
                status="selected",
                source_matrix=direction.source_matrix,
                elimination_record=direction.elimination_record,
            )
            selected.append(updated)

    return ExplorationRunResult(
        run_id=run_id,
        selected_directions=selected,
        eliminated_directions=eliminated,
        elimination_log_path=str(resolved_log_path) if resolved_log_path else "",
        source_matrix_consumed=source_matrix,
    )
