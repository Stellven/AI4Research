"""Negative control: single exploration direction produces no elimination."""

from __future__ import annotations

import json
from pathlib import Path

from research.survey.explorer.exploration_run import exploration_run
from research.survey.schemas import ExplorationDirection

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nc_single_direction_exploration.json"


def test_single_direction_exploration_has_no_elimination_and_must_warn(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text())
    directions = [
        ExplorationDirection(
            direction_id=item["direction_id"],
            direction_name=item["direction_name"],
            query=item["query"],
            status="active",
        )
        for item in data["directions"]
    ]
    log_path = tmp_path / "elimination_log.jsonl"
    result = exploration_run(data["run_id"], directions, log_path=log_path)
    warning = len(result.eliminated_directions) == 0 and log_path.read_text() == ""
    assert len(result.selected_directions) == 1
    assert len(result.eliminated_directions) == 0
    assert warning is True

