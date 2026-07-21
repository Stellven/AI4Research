"""Tests for survey/explorer/score_direction.py.

S03 N6 implementation test per S02 exploration-arch.md §5 (scoring
dimensions) + S03 design.md §3 (uniform weights baseline).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_LIB = Path(__file__).resolve().parents[4] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research.survey.explorer.config_defaults import (  # noqa: E402
    DIRECTION_SCORE_WEIGHTS,
)
from research.survey.explorer.score_direction import (  # noqa: E402
    score_breakdown,
    score_direction,
)
from research.survey.schemas import ExplorationDirection, SourceMatrix  # noqa: E402


def _make_direction(direction_id: str = "dir-a", matrix: SourceMatrix | None = None) -> ExplorationDirection:
    return ExplorationDirection(
        direction_id=direction_id,
        direction_name=f"Direction {direction_id}",
        query="research question",
        status="active",
        source_matrix=matrix,
    )


def _src(source_id: str, source_type: str, claims=None, evidence_count: int = 1) -> dict:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "claims": list(claims) if claims else [],
        "evidence_count": evidence_count,
    }


def test_score_returns_zero_for_empty_sources() -> None:
    score = score_direction(_make_direction(), [])
    assert score == 0.0


def test_score_is_deterministic() -> None:
    direction = _make_direction()
    sources = [
        _src("s1", "paper", claims=["c1"], evidence_count=2),
        _src("s2", "code", claims=["c2"], evidence_count=1),
    ]
    first = score_direction(direction, sources)
    second = score_direction(direction, sources)
    third = score_direction(direction, list(sources))
    assert first == second == third


def test_score_higher_with_diverse_high_authority_sources() -> None:
    direction = _make_direction()
    sparse = [_src("s1", "blog", claims=["c1"], evidence_count=1)]
    rich = [
        _src("s1", "paper", claims=["c1"], evidence_count=3),
        _src("s2", "code", claims=["c2"], evidence_count=2),
        _src("s3", "official", claims=["c3"], evidence_count=2),
        _src("s4", "benchmark", claims=["c4"], evidence_count=4),
    ]
    assert score_direction(direction, rich) > score_direction(direction, sparse)


def test_score_uses_source_matrix_required_types_when_set() -> None:
    matrix = SourceMatrix(
        section_id="sec-a",
        required_source_types=["paper", "code"],
        recommended_source_types=[],
        min_sources=2,
        min_evidence=1,
    )
    direction = _make_direction(matrix=matrix)
    # Both required types covered → source_coverage should be 1.0.
    full = [
        _src("s1", "paper", claims=["c1"], evidence_count=2),
        _src("s2", "code", claims=["c2"], evidence_count=2),
    ]
    # Only one required type covered → source_coverage = 0.5.
    half = [
        _src("s1", "paper", claims=["c1"], evidence_count=2),
        _src("s2", "blog", claims=["c2"], evidence_count=2),
    ]
    full_breakdown = score_breakdown(direction, full)
    half_breakdown = score_breakdown(direction, half)
    assert full_breakdown["source_coverage"] == 1.0
    assert half_breakdown["source_coverage"] == 0.5


def test_score_breakdown_has_all_four_dimensions() -> None:
    breakdown = score_breakdown(_make_direction(), [_src("s1", "paper", claims=["c1"])])
    assert set(breakdown.keys()) == {
        "source_coverage",
        "novelty",
        "feasibility",
        "evidence_density",
    }
    assert all(0.0 <= v <= 1.0 for v in breakdown.values())


def test_score_uniform_weights_average() -> None:
    direction = _make_direction()
    sources = [_src("s1", "paper", claims=["c1"], evidence_count=2)]
    composite = score_direction(direction, sources)
    breakdown = score_breakdown(direction, sources)
    expected = sum(breakdown.values()) / 4.0
    assert abs(composite - expected) < 1e-9


def test_score_custom_weights_can_zero_a_dimension() -> None:
    direction = _make_direction()
    sources = [
        _src("s1", "paper", claims=["c1", "c1"], evidence_count=2),
    ]
    composite_default = score_direction(direction, sources)
    # Zero out novelty → composite should differ (novelty was depressed by duplicate claim).
    composite_no_novelty = score_direction(
        direction,
        sources,
        weights={"source_coverage": 1.0, "novelty": 0.0, "feasibility": 1.0, "evidence_density": 1.0},
    )
    assert composite_default != composite_no_novelty


def test_default_weights_uniform() -> None:
    assert set(DIRECTION_SCORE_WEIGHTS.keys()) == {
        "source_coverage",
        "novelty",
        "feasibility",
        "evidence_density",
    }
    assert all(v == 1.0 for v in DIRECTION_SCORE_WEIGHTS.values())
