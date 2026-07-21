"""Tests for survey/explorer/exploration_run.py.

S03 N6 implementation test per S02 exploration-arch.md §6 (exploration_run
interface + ExplorationRunResult output) + dispatch.md acceptance (3-direction
fixture eliminating exactly one weak direction + kill_reason mandatory in
elimination_log.jsonl + 0/1 candidate edge cases).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HARNESS_LIB = Path(__file__).resolve().parents[4] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research.survey.explorer.exploration_run import exploration_run  # noqa: E402
from research.survey.schemas import (  # noqa: E402
    ExplorationDirection,
    ExplorationRunResult,
    SourceMatrix,
    SurveyQuestion,
)


def _direction(direction_id: str, name: str) -> ExplorationDirection:
    return ExplorationDirection(
        direction_id=direction_id,
        direction_name=name,
        query=f"query for {name}",
        status="active",
    )


def _strong_sources() -> list[dict]:
    return [
        {"source_id": "p1", "source_type": "paper", "claims": ["c1"], "evidence_count": 3},
        {"source_id": "c1", "source_type": "code", "claims": ["c2"], "evidence_count": 2},
        {"source_id": "o1", "source_type": "official", "claims": ["c3"], "evidence_count": 2},
    ]


def _medium_sources() -> list[dict]:
    return [
        {"source_id": "p2", "source_type": "paper", "claims": ["c1"], "evidence_count": 2},
        {"source_id": "b1", "source_type": "benchmark", "claims": ["c4"], "evidence_count": 1},
    ]


def _weak_sources() -> list[dict]:
    return [
        {"source_id": "w1", "source_type": "blog", "claims": ["c1", "c1"], "evidence_count": 0},
    ]


def _fixture_provider() -> dict[str, list[dict]]:
    return {
        "dir-strong": _strong_sources(),
        "dir-medium": _medium_sources(),
        "dir-weak": _weak_sources(),
    }


def _fixed_clock(value: str = "2026-05-17T23:30:00Z"):
    return lambda: value


def test_three_direction_fixture_eliminates_one_weak(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-1", text="What is X?")
    fixture = _fixture_provider()
    directions = [
        _direction("dir-strong", "Strong"),
        _direction("dir-medium", "Medium"),
        _direction("dir-weak", "Weak"),
    ]
    log_path = tmp_path / "elimination_log.jsonl"
    result = exploration_run(
        question,
        directions,
        source_provider=lambda d: fixture[d.direction_id],
        log_path=log_path,
        clock=_fixed_clock(),
    )
    assert isinstance(result, ExplorationRunResult)
    assert len(result.selected_directions) == 2
    assert len(result.eliminated_directions) == 1
    assert result.eliminated_directions[0].direction_id == "dir-weak"
    assert result.eliminated_directions[0].status == "eliminated"
    assert {d.direction_id for d in result.selected_directions} == {
        "dir-strong",
        "dir-medium",
    }
    assert all(d.status == "selected" for d in result.selected_directions)


def test_three_direction_fixture_writes_kill_reason_in_log(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-1", text="What is X?")
    fixture = _fixture_provider()
    directions = [
        _direction("dir-strong", "Strong"),
        _direction("dir-medium", "Medium"),
        _direction("dir-weak", "Weak"),
    ]
    log_path = tmp_path / "elimination_log.jsonl"
    exploration_run(
        question,
        directions,
        source_provider=lambda d: fixture[d.direction_id],
        log_path=log_path,
        clock=_fixed_clock("2026-05-17T23:31:00Z"),
    )
    raw = log_path.read_text(encoding="utf-8").splitlines()
    assert len(raw) == 1
    record = json.loads(raw[0])
    assert record["direction_id"] == "dir-weak"
    assert record["kill_reason"].strip() != ""
    assert "weakest dimension" in record["kill_reason"]
    assert record["decision_ts"] == "2026-05-17T23:31:00Z"
    assert record["evidence_refs"] == ["w1"]
    assert record["candidate_count"] == 1
    assert set(record["score_breakdown"].keys()) == {
        "source_coverage",
        "novelty",
        "feasibility",
        "evidence_density",
    }


def test_zero_candidates_returns_empty_result(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-empty", text="")
    log_path = tmp_path / "elimination_log.jsonl"
    result = exploration_run(question, [], log_path=log_path, clock=_fixed_clock())
    assert result.selected_directions == []
    assert result.eliminated_directions == []
    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8") == ""
    assert result.run_id == "q-empty"


def test_single_candidate_is_selected_not_eliminated(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-1", text="What is X?")
    direction = _direction("dir-only", "Only")
    log_path = tmp_path / "elimination_log.jsonl"
    result = exploration_run(
        question,
        [direction],
        source_provider=lambda d: _strong_sources(),
        log_path=log_path,
        clock=_fixed_clock(),
    )
    assert len(result.selected_directions) == 1
    assert result.selected_directions[0].direction_id == "dir-only"
    assert result.selected_directions[0].status == "selected"
    assert result.eliminated_directions == []
    assert log_path.read_text(encoding="utf-8") == ""


def test_elimination_record_has_all_required_fields(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-fields", text="Check fields")
    fixture = _fixture_provider()
    directions = [
        _direction("dir-strong", "Strong"),
        _direction("dir-weak", "Weak"),
    ]
    log_path = tmp_path / "log.jsonl"
    result = exploration_run(
        question,
        directions,
        source_provider=lambda d: fixture[d.direction_id],
        log_path=log_path,
        clock=_fixed_clock(),
    )
    eliminated = result.eliminated_directions[0]
    record = eliminated.elimination_record
    assert record is not None
    assert record.direction_id == "dir-weak"
    assert record.direction_name == "Weak"
    assert record.kill_reason.strip() != ""
    assert len(record.evidence_refs) >= 1
    assert record.decision_ts.strip() != ""
    assert 0.0 <= record.score <= 1.0


def test_run_id_propagated_from_survey_run_attr() -> None:
    class _StubSurveyRun:
        run_id = "stub-run-007"

    result = exploration_run(_StubSurveyRun(), [], clock=_fixed_clock())
    assert result.run_id == "stub-run-007"


def test_threshold_eliminates_all_below(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-thresh", text="")
    fixture = _fixture_provider()
    directions = [
        _direction("dir-strong", "Strong"),
        _direction("dir-medium", "Medium"),
        _direction("dir-weak", "Weak"),
    ]
    log_path = tmp_path / "log.jsonl"
    # Set threshold high enough to eliminate medium + weak but keep strong.
    result = exploration_run(
        question,
        directions,
        source_provider=lambda d: fixture[d.direction_id],
        log_path=log_path,
        clock=_fixed_clock(),
        elimination_threshold=0.9,
    )
    eliminated_ids = {d.direction_id for d in result.eliminated_directions}
    assert "dir-weak" in eliminated_ids
    assert "dir-medium" in eliminated_ids
    assert {d.direction_id for d in result.selected_directions} == {"dir-strong"}


def test_run_without_log_path_does_not_write(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-nolog", text="")
    fixture = _fixture_provider()
    directions = [
        _direction("dir-strong", "Strong"),
        _direction("dir-weak", "Weak"),
    ]
    result = exploration_run(
        question,
        directions,
        source_provider=lambda d: fixture[d.direction_id],
        clock=_fixed_clock(),
    )
    assert result.elimination_log_path == ""
    # No file written anywhere under tmp_path.
    assert not any(tmp_path.iterdir())
    assert len(result.eliminated_directions) == 1


def test_source_matrix_consumed_propagated_to_result() -> None:
    matrix = SourceMatrix(
        section_id="sec-1",
        required_source_types=["paper"],
        recommended_source_types=[],
        min_sources=1,
        min_evidence=1,
    )
    question = SurveyQuestion(question_id="q-sm", text="")
    result = exploration_run(question, [], source_matrix=matrix, clock=_fixed_clock())
    assert result.source_matrix_consumed is matrix


def test_clock_default_placeholder_when_not_injected(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-clock", text="")
    fixture = _fixture_provider()
    directions = [
        _direction("dir-strong", "Strong"),
        _direction("dir-weak", "Weak"),
    ]
    log_path = tmp_path / "log.jsonl"
    exploration_run(
        question,
        directions,
        source_provider=lambda d: fixture[d.direction_id],
        log_path=log_path,
    )
    line = log_path.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    # Default placeholder timestamp satisfies the non-empty constraint.
    assert record["decision_ts"] == "1970-01-01T00:00:00Z"


def test_default_provider_returns_no_sources_scores_zero(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-default", text="")
    directions = [
        _direction("dir-a", "A"),
        _direction("dir-b", "B"),
    ]
    log_path = tmp_path / "log.jsonl"
    result = exploration_run(question, directions, log_path=log_path, clock=_fixed_clock())
    # Both directions score 0; lowest direction_id (dir-a) eliminated by tiebreak.
    assert len(result.eliminated_directions) == 1
    assert result.eliminated_directions[0].direction_id == "dir-a"
    assert result.selected_directions[0].direction_id == "dir-b"
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["score"] == 0.0


def test_evidence_refs_fall_back_to_direction_id_when_no_sources(tmp_path: Path) -> None:
    question = SurveyQuestion(question_id="q-fallback", text="")
    directions = [
        _direction("dir-x", "X"),
        _direction("dir-y", "Y"),
    ]
    log_path = tmp_path / "log.jsonl"
    exploration_run(
        question,
        directions,
        source_provider=lambda d: [],
        log_path=log_path,
        clock=_fixed_clock(),
    )
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    # No sources for any direction → evidence_refs falls back to direction_id.
    assert record["evidence_refs"] == [record["direction_id"]]
