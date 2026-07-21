"""Pure direction-scoring function.

S03 N6 implementation per S02 exploration-arch.md §5 (5 scoring dimensions
collapsed to 4 planner-locked dimensions per S03 design.md §3) and §9
(weights externalized via config_defaults). Pure function: no IO, no random,
no datetime/time calls, no LLM, no network.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from research.survey.explorer.config_defaults import (
    DEFAULT_HIGH_AUTHORITY_TYPES,
    DIRECTION_SCORE_DIMENSIONS,
    DIRECTION_SCORE_WEIGHTS,
)


def _as_dict(source: Any) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    if hasattr(source, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(source)
    raise TypeError(
        f"score_direction: source must be Mapping or dataclass, got {type(source).__name__}"
    )


def _clamp_unit(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _score_source_coverage(
    direction: Any, sources: list[dict[str, Any]]
) -> float:
    actual_types = {s.get("source_type", "") for s in sources if s.get("source_type")}
    matrix = getattr(direction, "source_matrix", None)
    required = list(getattr(matrix, "required_source_types", []) or []) if matrix else []
    if required:
        covered = sum(1 for t in required if t in actual_types)
        return _clamp_unit(covered / len(required))
    if not actual_types:
        return 0.0
    authoritative = actual_types.intersection(DEFAULT_HIGH_AUTHORITY_TYPES)
    return _clamp_unit(len(authoritative) / len(DEFAULT_HIGH_AUTHORITY_TYPES))


def _score_novelty(direction: Any, sources: list[dict[str, Any]]) -> float:
    all_claims: list[str] = []
    for s in sources:
        claims = s.get("claims") or s.get("claim_ids") or []
        all_claims.extend(str(c) for c in claims)
    if not all_claims:
        return 0.0
    distinct = len(set(all_claims))
    return _clamp_unit(distinct / len(all_claims))


def _score_feasibility(direction: Any, sources: list[dict[str, Any]]) -> float:
    # Deterministic proxy: ≥3 sources => fully feasible. Below that, linear.
    return _clamp_unit(len(sources) / 3.0)


def _score_evidence_density(
    direction: Any, sources: list[dict[str, Any]]
) -> float:
    if not sources:
        return 0.0
    total_evidence = 0
    for s in sources:
        if "evidence_count" in s:
            total_evidence += int(s["evidence_count"])
        else:
            ev = s.get("evidence") or s.get("evidence_ids") or []
            total_evidence += len(ev)
    # Deterministic proxy: avg ≥2 evidence per source => fully dense.
    avg = total_evidence / len(sources)
    return _clamp_unit(avg / 2.0)


_DIMENSION_FUNCS = {
    "source_coverage": _score_source_coverage,
    "novelty": _score_novelty,
    "feasibility": _score_feasibility,
    "evidence_density": _score_evidence_density,
}


def score_direction(
    direction: Any,
    sources: Iterable[Any],
    weights: Mapping[str, float] | None = None,
) -> float:
    """Compute composite direction quality score in [0.0, 1.0].

    Pure: deterministic in (direction, sources, weights). No external IO.
    """
    weights_map = dict(weights) if weights is not None else dict(DIRECTION_SCORE_WEIGHTS)
    source_dicts = [_as_dict(s) for s in sources]
    total_weight = sum(weights_map.get(d, 0.0) for d in DIRECTION_SCORE_DIMENSIONS)
    if total_weight <= 0.0:
        return 0.0
    weighted_sum = 0.0
    for dim in DIRECTION_SCORE_DIMENSIONS:
        w = weights_map.get(dim, 0.0)
        if w == 0.0:
            continue
        dim_score = _DIMENSION_FUNCS[dim](direction, source_dicts)
        weighted_sum += w * dim_score
    return _clamp_unit(weighted_sum / total_weight)


def score_breakdown(
    direction: Any,
    sources: Iterable[Any],
) -> dict[str, float]:
    """Return per-dimension scores (used for EliminationRecord.score_breakdown)."""
    source_dicts = [_as_dict(s) for s in sources]
    return {
        dim: _DIMENSION_FUNCS[dim](direction, source_dicts)
        for dim in DIRECTION_SCORE_DIMENSIONS
    }
