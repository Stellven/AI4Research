#!/usr/bin/env python3
"""Regression: build_acceptance_verdict must NOT stamp a mid-run (incomplete) graph
as FAIL.

A FAIL parent verdict mid-run leaks into the per-node evidence the node evaluator
reads, so every node fails an evidence-consistency check until the whole graph
closes — a structural deadlock where the first node can never pass (observed on the
Codex S-node runs). An in-progress graph is IN_PROGRESS; FAIL is reserved for a
completed-but-uncovered graph or a non-pass request. PASS still requires a complete,
fully-covered graph.
"""
from __future__ import annotations

import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from requirement_coverage import build_acceptance_verdict


def _verdict(*, graph_complete: bool, missing: int = 0, partial: int = 0, requested: str = "pass") -> dict:
    coverage = {
        "summary": {
            "graph_complete": graph_complete,
            "missing": missing,
            "partial": partial,
        }
    }
    return build_acceptance_verdict(
        {"id": "req-x"},
        {"sprint_id": "sid-x"},
        coverage,
        requested_verdict=requested,
    )


def test_incomplete_graph_is_in_progress_not_fail():
    v = _verdict(graph_complete=False, missing=4)
    assert v["verdict"] == "IN_PROGRESS"
    assert "task_graph_incomplete" in v["reasons"]


def test_complete_and_fully_covered_is_pass():
    assert _verdict(graph_complete=True, missing=0, partial=0)["verdict"] == "PASS"


def test_complete_but_uncovered_is_fail():
    assert _verdict(graph_complete=True, missing=1)["verdict"] == "FAIL"
    assert _verdict(graph_complete=True, partial=1)["verdict"] == "FAIL"


def test_non_pass_request_is_fail_even_when_incomplete():
    assert _verdict(graph_complete=False, requested="reject")["verdict"] == "FAIL"
