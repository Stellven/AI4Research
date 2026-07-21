from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import prerequisite_resolver as pr  # noqa: E402


def _write_status(sprints_dir: Path, sid: str, status: str, phase: str) -> None:
    payload = {"id": sid, "status": status, "phase": phase}
    (sprints_dir / f"{sid}.status.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_planning_complete_requirement_accepts_finalized_terminal_state(tmp_path: Path) -> None:
    _write_status(tmp_path, "upstream", "passed", "finalized")

    ok, detail = pr.evaluate_prerequisite(
        {"sprint_id": "upstream", "required_status": "planning_complete"},
        tmp_path,
    )

    assert ok is True
    assert detail["current_status"] == "passed"
    assert detail["current_phase"] == "finalized"


def test_iter_blocked_dedupes_and_clears_terminal_phase_successor(tmp_path: Path) -> None:
    _write_status(tmp_path, "upstream", "passed", "finalized")
    graph = {
        "prerequisites": [
            {"sprint_id": "upstream", "required_status": "planning_complete"},
        ],
        "dependency_policy": {
            "blocks_until": [
                {"sprint_id": "upstream", "required_status": "planning_complete"},
            ]
        },
    }

    blocked = pr.iter_blocked(graph, tmp_path)

    assert blocked == []
