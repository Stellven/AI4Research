from __future__ import annotations

import sys
from pathlib import Path


HARNESS_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_scheduler as gs  # noqa: E402


def test_normalize_worker_entry_backfills_planner_capabilities() -> None:
    worker = gs._normalize_worker_entry(
        {
            "id": "solar-harness:0.1",
            "pane": "solar-harness:0.1",
            "role": "planner",
            "skills": [],
            "capabilities": [],
        }
    )

    for skill in ("workflow.planning", "browser.qa", "debug.systematic", "skill.methodology"):
        assert skill in worker["skills"]
    for capability in (
        "harness.context_preflight",
        "harness.dispatch_visibility",
        "harness.dag",
        "artifact.requirement_trace",
        "browser.browse",
        "code.review",
        "test.tdd",
    ):
        assert capability in worker["capabilities"]
