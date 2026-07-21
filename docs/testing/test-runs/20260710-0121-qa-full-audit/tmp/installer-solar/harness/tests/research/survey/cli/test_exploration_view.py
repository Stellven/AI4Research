"""Tests for exploration_view — S04 N4.

≥ 6 tests: format output structure, counts, elimination log path,
to_dict round-trip, fixtures load, edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.research.survey.schemas import (
    EliminationRecord,
    ExplorationDirection,
    ExplorationRunResult,
)
from lib.research.survey.cli.exploration_view import (
    format_exploration,
    to_dict_exploration,
)


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _direction(
    did: str,
    name: str,
    status: str = "selected",
    kill_reason: str = "",
) -> ExplorationDirection:
    elim = None
    if status == "eliminated" and kill_reason:
        elim = EliminationRecord(
            direction_id=did,
            direction_name=name,
            score=0.2,
            kill_reason=kill_reason,
            evidence_refs=["src_1"],
            decision_ts="2026-05-17T12:00:00Z",
        )
    return ExplorationDirection(
        direction_id=did,
        direction_name=name,
        query=f"query for {name}",
        status=status,
        elimination_record=elim,
    )


def _result_typical() -> ExplorationRunResult:
    return ExplorationRunResult(
        run_id="run_001",
        selected_directions=[
            _direction("d1", "Transformer Scaling", "selected"),
            _direction("d2", "Efficient Attention", "selected"),
        ],
        eliminated_directions=[
            _direction("d3", "RNN Revival", "eliminated", "insufficient_source_coverage"),
        ],
        elimination_log_path="runtime/survey-continue/run_001/elimination_log.jsonl",
    )


def _result_high_kill() -> ExplorationRunResult:
    return ExplorationRunResult(
        run_id="run_002",
        selected_directions=[
            _direction("d1", "LLM Reasoning", "selected"),
        ],
        eliminated_directions=[
            _direction("d2", "Symbolic AI", "eliminated", "low_novelty_score"),
            _direction("d3", "Neuro-Symbolic", "eliminated", "insufficient_source_coverage"),
            _direction("d4", "Bayesian Reasoning", "eliminated", "low_evidence_density"),
        ],
        elimination_log_path="runtime/survey-continue/run_002/elimination_log.jsonl",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFormatExploration:
    def test_output_contains_run_id(self) -> None:
        output = format_exploration(_result_typical())
        assert "run_id:               run_001" in output

    def test_output_contains_counts(self) -> None:
        output = format_exploration(_result_typical())
        assert "proposed_count:       3" in output
        assert "selected_count:       2" in output
        assert "eliminated_count:     1" in output

    def test_output_contains_elimination_log_path(self) -> None:
        output = format_exploration(_result_typical())
        assert "elimination_log_path: runtime/survey-continue/run_001/elimination_log.jsonl" in output

    def test_output_lists_eliminated_with_reason(self) -> None:
        output = format_exploration(_result_typical())
        assert "RNN Revival" in output
        assert "insufficient_source_coverage" in output

    def test_high_kill_shows_all_eliminated(self) -> None:
        output = format_exploration(_result_high_kill())
        assert "proposed_count:       4" in output
        assert "selected_count:       1" in output
        assert "eliminated_count:     3" in output
        assert "Symbolic AI" in output
        assert "Neuro-Symbolic" in output
        assert "Bayesian Reasoning" in output


class TestToDictExploration:
    def test_round_trip(self) -> None:
        result = _result_typical()
        d = to_dict_exploration(result)
        assert d["run_id"] == "run_001"
        assert len(d["selected_directions"]) == 2
        assert len(d["eliminated_directions"]) == 1
        assert d["elimination_log_path"] == "runtime/survey-continue/run_001/elimination_log.jsonl"
        elim = d["eliminated_directions"][0]
        assert elim["elimination_record"]["kill_reason"] == "insufficient_source_coverage"


class TestFixtures:
    def test_typical_fixture_loads(self) -> None:
        data = json.loads((FIXTURES / "exploration_run_typical.json").read_text())
        assert data["run_id"] == "run_typical_001"
        assert len(data["selected_directions"]) == 2
        assert len(data["eliminated_directions"]) == 1

    def test_high_kill_fixture_loads(self) -> None:
        data = json.loads((FIXTURES / "exploration_run_high_kill.json").read_text())
        assert data["run_id"] == "run_highkill_001"
        assert len(data["selected_directions"]) == 1
        assert len(data["eliminated_directions"]) == 3
