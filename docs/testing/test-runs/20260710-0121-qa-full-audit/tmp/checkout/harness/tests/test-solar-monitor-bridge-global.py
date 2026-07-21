#!/usr/bin/env python3
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add 'lib' and 'tools' directories to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tools"))

import pytest
import operator_runtime
import solar_monitor_bridge

@pytest.fixture
def temp_harness_env():
    # Setup temporary directory for HARNESS_DIR
    temp_dir = tempfile.mkdtemp()
    harness_path = Path(temp_dir)
    
    # Create required subdirectories
    sprints_dir = harness_path / "sprints"
    run_dir = harness_path / "run" / "multi-task"
    config_dir = harness_path / "config"
    sprints_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    
    # Save original env and set mock env variables
    orig_harness_dir = os.environ.get("HARNESS_DIR")
    orig_operators_path = os.environ.get("SOLAR_MULTI_TASK_OPERATORS")
    
    os.environ["HARNESS_DIR"] = str(harness_path)
    os.environ["SOLAR_MULTI_TASK_OPERATORS"] = str(config_dir / "physical-operators.json")
    
    # Reload operator_runtime configuration paths based on new env variables
    operator_runtime.HARNESS_DIR = harness_path
    operator_runtime.OPERATOR_LEASE_DIR = harness_path / "run" / "operator-leases"
    operator_runtime.OPERATOR_STATUS_DIR = harness_path / "run" / "operator-status"
    operator_runtime.PHYSICAL_OPERATORS_PATH = config_dir / "physical-operators.json"
    
    # Ensure dirs exist in operator_runtime
    operator_runtime._ensure_dirs()
    
    yield {
        "harness_dir": harness_path,
        "sprints_dir": sprints_dir,
        "run_dir": run_dir,
        "config_dir": config_dir,
    }
    
    # Clean up
    shutil.rmtree(temp_dir)
    if orig_harness_dir is not None:
        os.environ["HARNESS_DIR"] = orig_harness_dir
    else:
        os.environ.pop("HARNESS_DIR", None)
        
    if orig_operators_path is not None:
        os.environ["SOLAR_MULTI_TASK_OPERATORS"] = orig_operators_path
    else:
        os.environ.pop("SOLAR_MULTI_TASK_OPERATORS", None)


def test_monitor_bridge_global_accounting(temp_harness_env, monkeypatch):
    sprints_dir = temp_harness_env["sprints_dir"]
    run_dir = temp_harness_env["run_dir"]
    
    # 1. Setup mock operators registry
    mock_operators = {
        "version": 1,
        "operators": {
            "op-builder-1": {
                "display_name": "Test Builder 1",
                "role": "builder",
                "profile": "builder",
                "provider": "google",
                "vendor": "Google",
                "enabled": True,
            },
            "op-planner-1": {
                "display_name": "Test Planner 1",
                "role": "planner",
                "profile": "planner",
                "provider": "anthropic",
                "vendor": "Anthropic",
                "enabled": True,
            },
            "op-disabled-1": {
                "display_name": "Disabled Operator",
                "role": "builder",
                "profile": "builder",
                "provider": "anthropic",
                "vendor": "Anthropic",
                "enabled": False,
            },
            "mini-antigravity-gemini35-flash-high": {
                "display_name": "Antigravity Gemini 3.5 Flash High",
                "role": "builder",
                "profile": "builder",
                "provider": "google",
                "vendor": "Google",
                "enabled": True,
                "available": True,
                "auth_mode": "local",
                "model": "gemini-3.5-flash-high"
            },
            "mini-claude-sonnet-builder": {
                "display_name": "Claude Sonnet Builder",
                "role": "builder",
                "profile": "builder",
                "provider": "anthropic",
                "vendor": "Anthropic",
                "enabled": True,
                "available": True,
                "auth_mode": "local",
                "model": "sonnet-3.5"
            }
        }
    }
    operator_runtime.PHYSICAL_OPERATORS_PATH.write_text(json.dumps(mock_operators, indent=2))
    
    # 2. Setup mock sprint graphs
    # sprint-1: active sprint, N1 passed, N2 dispatched (active), N3 pending, N4 pending (ready)
    graph_1_path = sprints_dir / "sprint-1.task_graph.json"
    graph_1 = {
        "sprint_id": "sprint-1",
        "nodes": [
            {
                "id": "N1",
                "status": "passed",
                "task_type": "infra"
            },
            {
                "id": "N2",
                "status": "dispatched",
                "depends_on": ["N1"],
                "task_type": "coding"
            },
            {
                "id": "N3",
                "status": "pending",
                "depends_on": ["N2"],
                "task_type": "review"
            },
            {
                "id": "N4",
                "status": "pending",
                "depends_on": ["N1"],
                "task_type": "coding"
            }
        ]
    }
    graph_1_path.write_text(json.dumps(graph_1, indent=2))
    
    # sprint-2: active sprint, B1 reviewing but handoff missing (so blocked by handoff_missing_or_small)
    graph_2_path = sprints_dir / "sprint-2.task_graph.json"
    graph_2 = {
        "sprint_id": "sprint-2",
        "nodes": [
            {
                "id": "B1",
                "status": "reviewing",
                "task_type": "review"
            }
        ]
    }
    graph_2_path.write_text(json.dumps(graph_2, indent=2))
    
    # 3. Setup mock tasks in run_dir
    # task_1: running node N2 of sprint-1 (active)
    task_1_dir = run_dir / "task-1"
    task_1_dir.mkdir(parents=True)
    task_1_status = {
        "id": "task-1",
        "sprint_id": "sprint-1",
        "node_id": "N2",
        "status": "running",
        "operator_id": "op-builder-1",
        "role": "builder",
        "graph": "/invalid/path/sprint-1.task_graph.json" # testing fallback to filename in sprints_dir
    }
    (task_1_dir / "status.json").write_text(json.dumps(task_1_status, indent=2))
    
    # task_2: running node N1 of sprint-1 (passed in graph - should NOT be counted as active)
    task_2_dir = run_dir / "task-2"
    task_2_dir.mkdir(parents=True)
    task_2_status = {
        "id": "task-2",
        "sprint_id": "sprint-1",
        "node_id": "N1",
        "status": "running",
        "operator_id": "op-builder-1",
        "role": "builder",
        "graph": "/invalid/path/sprint-1.task_graph.json"
    }
    (task_2_dir / "status.json").write_text(json.dumps(task_2_status, indent=2))

    # 4. Summarize all
    summary = solar_monitor_bridge.summarize_all(
        sprints_dir=sprints_dir,
        run_dir=run_dir,
        stale_sec=300,
        include_passed_limit=5
    )
    
    # Verify outputs
    assert "operator_fleet" in summary
    assert "operator_class_counts" in summary
    assert "ready_by_task_type" in summary
    assert "blocked_by_reason" in summary
    
    # Check graph-effective active task accounting:
    # task-2 should NOT be active since node N1 is passed in the graph.
    # task-1 should be active.
    assert summary["active_task_count"] == 1
    assert len(summary["active_tasks"]) == 1
    assert summary["active_tasks"][0]["task"] == "task-1"
    
    # Check operator_class_counts
    # Only active task is task-1, which has role "builder"
    assert summary["operator_class_counts"] == {"builder": 1}
    
    # Check operator_fleet
    fleet = summary["operator_fleet"]
    assert "op-builder-1" in fleet
    assert fleet["op-builder-1"]["active_task_count"] == 1
    assert fleet["op-builder-1"]["runtime_state"] == "idle" # no leases or overrides exist, config matches enabled
    
    assert "op-planner-1" in fleet
    assert fleet["op-planner-1"]["active_task_count"] == 0
    assert fleet["op-planner-1"]["runtime_state"] == "idle"
    
    assert "op-disabled-1" in fleet
    assert fleet["op-disabled-1"]["runtime_state"] == "disabled"
    
    # Check ready_by_task_type
    # sprint-1 has N4 ready, task_type coding.
    # sprint-2 has no ready nodes.
    assert summary["ready_by_task_type"] == {"coding": 1}
    
    # Check blocked_by_reason
    # B1 of sprint-2 has status "reviewing" without handoff file -> blocker handoff_missing_or_small
    # N2 of sprint-1 is active but has no tmux window -> blocker tmux_window_missing
    assert summary["blocked_by_reason"] == {"handoff_missing_or_small": 1, "tmux_window_missing": 1}

    # Check provider_counts and model_counts
    assert "provider_counts" in summary
    assert "model_counts" in summary
    assert summary["provider_counts"] == {"google": 1}
    assert summary["model_counts"] == {"N/A": 1}

    # Check fallback_ladder_health
    assert "fallback_ladder_health" in summary
    assert summary["fallback_ladder_health"]["CODE_IMPL"] == "ok"
    
    # Test fallback ladder health statuses under different scenarios by monkeypatching
    # Scenario A: primary candidate is busy (dynamic state "running"), backup is idle
    monkeypatch.setattr(operator_runtime, "get_operator_runtime_state", lambda op_id: "running" if op_id == "mini-antigravity-gemini35-flash-high" else "idle")
    summary_degraded = solar_monitor_bridge.summarize_all(sprints_dir=sprints_dir, run_dir=run_dir, stale_sec=300, include_passed_limit=5)
    assert summary_degraded["fallback_ladder_health"]["CODE_IMPL"] == "degraded"
    
    # Scenario B: primary and backup are both busy
    monkeypatch.setattr(operator_runtime, "get_operator_runtime_state", lambda op_id: "running" if op_id in ("mini-antigravity-gemini35-flash-high", "mini-claude-sonnet-builder") else "idle")
    summary_busy = solar_monitor_bridge.summarize_all(sprints_dir=sprints_dir, run_dir=run_dir, stale_sec=300, include_passed_limit=5)
    assert summary_busy["fallback_ladder_health"]["CODE_IMPL"] == "busy"
    
    # Scenario C: primary is disabled, backup is disabled
    monkeypatch.setattr(operator_runtime, "get_operator_runtime_state", lambda op_id: "disabled" if op_id in ("mini-antigravity-gemini35-flash-high", "mini-claude-sonnet-builder") else "idle")
    summary_unavailable = solar_monitor_bridge.summarize_all(sprints_dir=sprints_dir, run_dir=run_dir, stale_sec=300, include_passed_limit=5)
    assert summary_unavailable["fallback_ladder_health"]["CODE_IMPL"] == "unavailable"
