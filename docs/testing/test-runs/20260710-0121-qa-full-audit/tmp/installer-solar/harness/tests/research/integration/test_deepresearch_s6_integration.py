"""Integration test for DeepResearch OS S6 integration.

Verifies:
1. S6 Browser Agent call wrappers submit jobs to the browser-jobs directory.
2. S6 Evidence Ledger entries are written under run/actor-evidence/.
3. Figures are successfully compiled into S6 task_graph.json.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add harness lib to sys.path
_LIB_DIR = Path(__file__).resolve().parents[3] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import browser_job_runtime as bjrt
import operator_runtime
from research import cli as research_cli


@pytest.fixture(autouse=True)
def setup_s6_env(monkeypatch, tmp_path):
    """Fixture to isolate S6 paths for integration testing."""
    harness_dir = tmp_path / "harness"
    jobs_dir = harness_dir / "run" / "browser-jobs"
    results_dir = harness_dir / "run" / "operator-results"
    evidence_dir = harness_dir / "run" / "actor-evidence"
    sprints_dir = harness_dir / "sprints"
    
    jobs_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sprints_dir.mkdir(parents=True, exist_ok=True)
    
    # Mock paths inside S6 modules
    monkeypatch.setattr(bjrt, "BROWSER_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(bjrt, "OPERATOR_RESULTS_DIR", results_dir)
    monkeypatch.setattr(bjrt, "HARNESS_DIR", harness_dir)
    monkeypatch.setattr(operator_runtime, "HARNESS_DIR", harness_dir)
    monkeypatch.setattr(operator_runtime, "OPERATOR_LEASE_DIR", harness_dir / "run" / "operator-leases")
    monkeypatch.setattr(operator_runtime, "OPERATOR_STATUS_DIR", harness_dir / "run" / "operator-status")
    monkeypatch.setattr(operator_runtime, "OPERATOR_INBOX_DIR", harness_dir / "run" / "operator-inbox")
    monkeypatch.setattr(operator_runtime, "OPERATOR_RESULTS_DIR", results_dir)
    
    # Environment variables
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("HARNESS_SPRINT_ID", "sprint-test-s6")
    monkeypatch.setenv("HARNESS_NODE_ID", "N4")
    monkeypatch.setenv("HARNESS_TASK_ID", "T001")
    monkeypatch.setenv("SOLAR_ACTIVE_ACTOR_ID", "mini-antigravity-gemini35-flash-image")
    monkeypatch.setenv("SOLAR_RESEARCH_DISABLE_BROWSER_USE", "1")  # Disable real browser call to avoid Playwright launch
    
    yield {
        "harness_dir": harness_dir,
        "jobs_dir": jobs_dir,
        "results_dir": results_dir,
        "evidence_dir": evidence_dir,
        "sprints_dir": sprints_dir,
    }


def test_browser_agent_search_submits_job(setup_s6_env):
    """Verify browser_use_search submits a job to browser_jobs_runtime."""
    # Under test
    hits, errors = research_cli.browser_use_search("test query", max_results=1)
    
    # Assert a job was registered on disk
    jobs = list(setup_s6_env["jobs_dir"].glob("job-*"))
    assert len(jobs) == 1
    
    state_file = jobs[0] / "state.json"
    assert state_file.exists()
    
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["actor_id"] == "mini-antigravity-gemini35-flash-image"
    assert state_data["envelope"]["task_id"] == "T001"
    assert state_data["envelope"]["sprint_id"] == "sprint-test-s6"
    assert state_data["envelope"]["node_id"] == "N4"
    assert "test query" in state_data["envelope"]["objective"]


def test_evidence_ledger_entry_written(setup_s6_env):
    """Verify write_s6_evidence_entry appends an entry to the S6 evidence ledger."""
    output_md = setup_s6_env["harness_dir"] / "final.md"
    
    # Under test
    research_cli.write_s6_evidence_entry(output_md)
    
    ledger_file = setup_s6_env["evidence_dir"] / "sprint-test-s6.jsonl"
    assert ledger_file.exists()
    
    lines = ledger_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    
    entry = json.loads(lines[0])
    assert entry["event_type"] == "run_dispatched"
    assert entry["task_id"] == "T001"
    assert entry["sprint_id"] == "sprint-test-s6"
    assert entry["node_id"] == "N4"
    assert entry["actor_id"] == "mini-antigravity-gemini35-flash-image"
    assert entry["logical_operator"] == "WebDeepResearch"
    assert entry["final_report_target"] == str(output_md)


def test_compile_figures_to_dag(setup_s6_env):
    """Verify compile_figures_to_dag appends figure nodes to task_graph.json."""
    output_dir = setup_s6_env["harness_dir"] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write mock figures.json
    figures = [
        {
            "figure_id": "fig_arch_1",
            "title": "S6 Pipeline",
            "figure_type": "architecture_diagram",
            "grounding_ids": ["cl_1"],
            "spec_data": {"nodes": [], "edges": []}
        }
    ]
    with open(output_dir / "figures.json", "w", encoding="utf-8") as f:
        json.dump(figures, f)
        
    # Write mock task_graph.json
    graph_path = setup_s6_env["sprints_dir"] / "sprint-test-s6.task_graph.json"
    graph_data = {
        "nodes": [
            {"id": "N4", "status": "running"}
        ]
    }
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f)
        
    # Under test
    research_cli.compile_figures_to_dag(output_dir)
    
    # Assert node was appended
    updated_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = updated_graph["nodes"]
    assert len(nodes) == 2
    
    fig_node = next((n for n in nodes if n["id"] == "fig_gen_fig_arch_1"), None)
    assert fig_node is not None
    assert fig_node["logical_operator"] == "BrowserAssetGeneration"
    assert "S6 Pipeline" in fig_node["goal"]
    assert "BrowserAssetGeneration" in fig_node["logical_operator"]
    assert fig_node["status"] == "pending"
