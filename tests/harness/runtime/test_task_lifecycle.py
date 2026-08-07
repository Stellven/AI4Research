"""Shared multi-task lifecycle contract regressions.

These tests cover the rc.9 published-run failures where ``submitted`` was
active in route proof but historical in the scheduler, and where a durable
operatord result did not converge the multi-task status row.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


HARNESS_DIR = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(HARNESS_DIR / "lib"))

import multi_task_runner as mtr  # noqa: E402
import route_proof  # noqa: E402


def test_runner_and_route_proof_share_task_status_vocabulary() -> None:
    assert mtr.ACTIVE_TASK_STATUSES == route_proof.ACTIVE_TASK_STATUSES
    assert mtr.TERMINAL_TASK_STATUSES == route_proof.TERMINAL_TASK_STATUSES
    assert "submitted" in mtr.ACTIVE_TASK_STATUSES
    assert "submitted_fallback" in mtr.ACTIVE_TASK_STATUSES


def test_submitted_task_occupies_its_exact_node() -> None:
    task = {
        "id": "mt-submitted",
        "sprint_id": "sprint-lifecycle",
        "node_id": "S3",
        "status": "submitted",
        "effective_status": "submitted",
    }

    assert mtr.active_task_for_node("sprint-lifecycle", "S3", [task]) == task


def test_exact_durable_result_converges_submitted_status(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "task_id": "mt-result",
                "operator_id": "operator-1",
                "status": "completed",
                "exit_code": 0,
                "finished_at": "2026-07-15T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    row = {
        "id": "mt-result",
        "operator_id": "operator-1",
        "status": "submitted",
        "result_path": str(result_path),
        "graph_status": "reviewing",
    }

    assert mtr.effective_task_status(row) == "completed"


def test_foreign_result_cannot_converge_task_status(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "task_id": "different-task",
                "operator_id": "operator-1",
                "status": "completed",
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )
    row = {
        "id": "mt-result",
        "operator_id": "operator-1",
        "status": "submitted",
        "result_path": str(result_path),
        "graph_status": "reviewing",
    }

    assert mtr.effective_task_status(row) == "submitted"
