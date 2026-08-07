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

HARNESS_LIB = (Path(__file__).resolve().parents[3] / 'harness') / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from requirement_coverage import build_acceptance_verdict, build_coverage_report


def _verdict(
    *,
    graph_complete: bool,
    graph_terminal: bool = False,
    graph_failed: bool = False,
    missing: int = 0,
    partial: int = 0,
    requested: str = "pass",
) -> dict:
    coverage = {
        "summary": {
            "graph_complete": graph_complete,
            "graph_terminal": graph_terminal,
            "graph_failed": graph_failed,
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


def test_terminal_failed_graph_is_fail_not_in_progress():
    v = _verdict(graph_complete=False, graph_terminal=True, graph_failed=True, missing=1)
    assert v["verdict"] == "FAIL"
    assert "task_graph_failed" in v["reasons"]
    assert "task_graph_incomplete" not in v["reasons"]


def test_complete_and_fully_covered_is_pass():
    assert _verdict(graph_complete=True, missing=0, partial=0)["verdict"] == "PASS"


def test_complete_but_uncovered_is_fail():
    assert _verdict(graph_complete=True, missing=1)["verdict"] == "FAIL"
    assert _verdict(graph_complete=True, partial=1)["verdict"] == "FAIL"


def test_non_pass_request_is_fail_even_when_incomplete():
    assert _verdict(graph_complete=False, requested="reject")["verdict"] == "FAIL"


def test_coverage_report_distinguishes_terminal_failure_from_running_graph():
    trace = {
        "requirement_ir_id": "req-x",
        "items": [{"requirement_id": "REQ-1", "final_status": "partial"}],
    }
    graph = {
        "sprint_id": "sid-x",
        "nodes": [{"id": "N1"}, {"id": "N2"}],
        "node_results": {"N1": {"status": "passed"}, "N2": {"status": "failed"}},
    }

    summary = build_coverage_report(trace, graph)["summary"]

    assert summary["graph_complete"] is False
    assert summary["graph_terminal"] is True
    assert summary["graph_failed"] is True
