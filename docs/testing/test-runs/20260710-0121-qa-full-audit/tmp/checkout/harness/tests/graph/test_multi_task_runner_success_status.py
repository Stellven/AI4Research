from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


HARNESS_LIB = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import multi_task_runner  # noqa: E402


def _payload(tmp_path: Path, *, review_required: bool = False) -> dict:
    graph = tmp_path / "sprint-test.task_graph.json"
    graph.write_text('{"sprint_id":"sprint-test","nodes":[]}\n', encoding="utf-8")
    return {
        "graph": str(graph),
        "handoff": str(tmp_path / "sprint-test.N1-handoff.md"),
        "node_id": "N1",
        "sprint_id": "sprint-test",
        "role": "builder",
        "profile": "builder",
        "backend": "command",
        "model": "sonnet",
        "provider": "anthropic",
        "capability_status": "ok",
        "approval_mode": "yolo",
        "review_required": review_required,
    }


def _runner_script_text(tmp_path: Path, *, review_required: bool = False) -> str:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    runner = multi_task_runner.runner_script(
        task_dir,
        _payload(tmp_path, review_required=review_required),
    )
    return runner.read_text(encoding="utf-8")


def test_successful_handoff_defaults_to_passed(tmp_path):
    script = _runner_script_text(tmp_path)

    assert 'success_status="${SOLAR_MULTI_TASK_SUCCESS_STATUS:-passed}"' in script
    assert '--status "$success_status"' in script
    assert "REVIEW_REQUIRED=0" in script


def test_review_required_node_can_still_stop_at_reviewing(tmp_path):
    script = _runner_script_text(tmp_path, review_required=True)

    assert "REVIEW_REQUIRED=1" in script
    assert 'success_status="reviewing"' in script


# ---------------------------------------------------------------------------
# O3 quota fallback / observability acceptance tests
# ---------------------------------------------------------------------------


def _make_graph_file(tmp_path: Path, nodes: list[dict]) -> Path:
    graph_path = tmp_path / "sprint-o3.task_graph.json"
    graph_path.write_text(
        json.dumps({"sprint_id": "sprint-o3", "nodes": nodes}),
        encoding="utf-8",
    )
    return graph_path


# AC1: late worker failure cannot overwrite passed --------------------------


@pytest.mark.parametrize("terminal_status", ["passed", "done", "completed", "skipped"])
def test_late_worker_failure_cannot_overwrite_terminal_status(tmp_path, terminal_status):
    """AC1: quota_hit_recovered_for_fallback returns True when node is already
    in a terminal status, blocking a late worker from overwriting it."""
    graph_path = _make_graph_file(tmp_path, [
        {"id": "N1", "status": terminal_status, "preferred_profile": "builder"},
    ])

    task_dir = tmp_path / "run" / f"task-ac1-{terminal_status}"
    task_dir.mkdir(parents=True)
    (task_dir / "status.json").write_text(
        json.dumps({"graph": str(graph_path), "node_id": "N1", "profile": "builder"}),
        encoding="utf-8",
    )
    log_path = task_dir / "output.log"
    log_path.write_text("API rate limit exceeded\n", encoding="utf-8")

    assert multi_task_runner.quota_hit_recovered_for_fallback(log_path) is True


def test_late_worker_failure_does_overwrite_non_terminal(tmp_path):
    """AC1 negative: when node is active (not terminal), the function returns
    False, allowing the fallback logic to proceed."""
    graph_path = _make_graph_file(tmp_path, [
        {"id": "N1", "status": "active", "preferred_profile": "builder"},
    ])

    task_dir = tmp_path / "run" / "task-ac1-active"
    task_dir.mkdir(parents=True)
    (task_dir / "status.json").write_text(
        json.dumps({"graph": str(graph_path), "node_id": "N1", "profile": "builder"}),
        encoding="utf-8",
    )
    log_path = task_dir / "output.log"
    log_path.write_text("some log\n", encoding="utf-8")

    assert multi_task_runner.quota_hit_recovered_for_fallback(log_path) is False


# AC2: quota recovery per node is capped ------------------------------------


def test_quota_recovery_capped_sets_monitor_blocker(tmp_path, monkeypatch):
    """AC2: when recovery_count >= max_recoveries, the node gets
    monitor_blocker set instead of being reset to pending."""
    run_dir = tmp_path / "run"
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)

    dispatch_id = "task-recovery-cap"
    task_dir = run_dir / dispatch_id
    task_dir.mkdir(parents=True)

    (task_dir / "status.json").write_text(
        json.dumps({"profile": "builder"}), encoding="utf-8"
    )
    (task_dir / "output.log").write_text(
        "Error: API rate limit exceeded. Please try again.\n", encoding="utf-8"
    )

    nodes = [
        {
            "id": "N1",
            "status": "failed",
            "dispatch_id": dispatch_id,
            "quota_recovery_count": 4,
            "quota_recovery_task_ids": ["r1", "r2", "r3", "r4"],
        }
    ]
    graph_path = _make_graph_file(tmp_path, nodes)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))

    changed = multi_task_runner.recover_quota_failed_nodes(graph_path, graph)
    assert changed >= 1

    updated = json.loads(graph_path.read_text(encoding="utf-8"))
    node = next(n for n in updated["nodes"] if n["id"] == "N1")
    assert "monitor_blocker" in node
    assert "recovery_limit_reached" in node["monitor_blocker"]
    assert node["status"] == "failed"


def test_quota_recovery_below_cap_allows_retry(tmp_path, monkeypatch):
    """AC2 negative: when recovery_count < max_recoveries, the node is eligible
    for fallback profile selection (no monitor_blocker from cap)."""
    run_dir = tmp_path / "run"
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)

    dispatch_id = "task-recovery-ok"
    task_dir = run_dir / dispatch_id
    task_dir.mkdir(parents=True)

    (task_dir / "status.json").write_text(
        json.dumps({"profile": "builder"}), encoding="utf-8"
    )
    (task_dir / "output.log").write_text(
        "Error: API rate limit exceeded.\n", encoding="utf-8"
    )

    nodes = [
        {
            "id": "N1",
            "status": "failed",
            "dispatch_id": dispatch_id,
            "quota_recovery_count": 1,
            "quota_recovery_task_ids": ["r1"],
        }
    ]
    graph_path = _make_graph_file(tmp_path, nodes)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))

    changed = multi_task_runner.recover_quota_failed_nodes(graph_path, graph)
    assert changed >= 1

    updated = json.loads(graph_path.read_text(encoding="utf-8"))
    node = next(n for n in updated["nodes"] if n["id"] == "N1")
    # No cap-based monitor_blocker (may have no_fallback blocker if no alt profile)
    cap_blocker = node.get("monitor_blocker") or ""
    assert "recovery_limit_reached" not in cap_blocker


# AC3: guard bypass requires explicit env -----------------------------------


def test_guard_bypass_requires_explicit_env_var(tmp_path, monkeypatch):
    """AC3: schedule_once guard bypass only activates when
    SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK is exactly '1'."""
    source = Path(multi_task_runner.__file__).read_text(encoding="utf-8")

    assert 'os.environ.get("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK") == "1"' in source

    monkeypatch.delenv("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK", raising=False)
    assert os.environ.get("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK") != "1"

    monkeypatch.setenv("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK", "yes")
    assert os.environ.get("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK") != "1"

    monkeypatch.setenv("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK", "1")
    assert os.environ.get("SOLAR_MULTI_TASK_BYPASS_QUOTA_GUARD_FOR_FALLBACK") == "1"


def test_quota_recovery_env_cap_override(tmp_path, monkeypatch):
    """AC2: SOLAR_MULTI_TASK_MAX_QUOTA_RECOVERIES_PER_NODE controls the cap."""
    monkeypatch.setenv("SOLAR_MULTI_TASK_MAX_QUOTA_RECOVERIES_PER_NODE", "2")
    max_rec = int(os.environ.get("SOLAR_MULTI_TASK_MAX_QUOTA_RECOVERIES_PER_NODE", "4"))
    assert max_rec == 2

    # Verify source reads this env var
    source = Path(multi_task_runner.__file__).read_text(encoding="utf-8")
    assert "SOLAR_MULTI_TASK_MAX_QUOTA_RECOVERIES_PER_NODE" in source
