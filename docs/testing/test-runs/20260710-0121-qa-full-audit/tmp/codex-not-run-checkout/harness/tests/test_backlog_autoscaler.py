from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import backlog_autoscaler as ba  # noqa: E402
import concurrency_policy as cp  # noqa: E402


def _write_status(root: Path, name: str, status: str, phase: str) -> None:
    payload = {"status": status, "phase": phase}
    (root / f"{name}.status.json").write_text(json.dumps(payload), encoding="utf-8")


def test_build_snapshot_scales_from_backlog(monkeypatch, tmp_path):
    sprints_dir = tmp_path / "sprints"
    config_dir = tmp_path / "config"
    sprints_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(5):
        _write_status(sprints_dir, f"draft-{idx}", "drafting", "spec")
    for idx in range(7):
        _write_status(sprints_dir, f"prd-{idx}", "active", "prd_ready")
    for idx in range(9):
        _write_status(sprints_dir, f"build-{idx}", "active", "planning_complete")
    for idx in range(4):
        _write_status(sprints_dir, f"review-{idx}", "reviewing", "handoff_ready")

    operators = {
        "operators": {
            "planner-1": {"role": "planner", "enabled": True, "available": True},
            "planner-2": {"role": "planner", "enabled": True, "available": False},
            "builder-1": {"role": "builder", "enabled": True, "available": True},
            "builder-2": {"role": "builder", "enabled": False, "available": False},
        }
    }
    registry_path = config_dir / "physical-operators.json"
    registry_path.write_text(json.dumps(operators), encoding="utf-8")

    monkeypatch.setattr(ba, "SPRINTS_DIR", sprints_dir)
    monkeypatch.setattr(ba, "PHYSICAL_OPERATORS_PATH", registry_path)
    monkeypatch.setattr(ba, "HARNESS_DIR", tmp_path)

    policy = {
        "backlog_autoscaling": {
            "enabled": True,
            "snapshot_path": "run/backlog-autoscale/latest.json",
            "metrics": {
                "drafting_spec": {"status": "drafting", "phase": "spec"},
                "active_prd_ready": {"status": "active", "phase": "prd_ready"},
                "active_planning_complete": {"status": "active", "phase": "planning_complete"},
                "reviewing_handoff_ready": {"status": "reviewing", "phase": "handoff_ready"},
            },
            "profile_targets": {
                "pm": {
                    "metric": "drafting_spec",
                    "base": 4,
                    "min": 2,
                    "max": 8,
                    "trigger_backlog": 4,
                    "backlog_per_step": 2,
                    "step": 1,
                },
                "builder": {
                    "metric": "active_planning_complete",
                    "base": 4,
                    "min": 2,
                    "max": 10,
                    "trigger_backlog": 8,
                    "backlog_per_step": 4,
                    "step": 2,
                },
            },
            "logical_operator_targets": {
                "DeepArchitect": {
                    "metric": "active_prd_ready",
                    "base": 6,
                    "min": 3,
                    "max": 10,
                    "trigger_backlog": 6,
                    "backlog_per_step": 3,
                    "step": 1,
                }
            },
            "builder_pool_targets": {
                "desired_total": {
                    "metric": "active_planning_complete",
                    "base": 14,
                    "min": 10,
                    "max": 20,
                    "trigger_backlog": 8,
                    "backlog_per_step": 4,
                    "step": 1,
                },
                "groups": {
                    "codex-gpt-5.3-spark": {
                        "metric": "active_planning_complete",
                        "base": 1,
                        "min": 1,
                        "max": 4,
                        "trigger_backlog": 8,
                        "backlog_per_step": 4,
                        "step": 1,
                    }
                },
            },
            "global_limits": {
                "max_workers": {
                    "base": 4,
                    "cap": 16,
                    "profile_names": ["pm", "builder"],
                }
            },
        }
    }

    snapshot = ba.build_snapshot(policy)
    assert snapshot["metrics"] == {
        "drafting_spec": 5,
        "active_prd_ready": 7,
        "active_planning_complete": 9,
        "reviewing_handoff_ready": 4,
    }
    assert snapshot["role_capacity"]["planner"] == {"configured": 2, "enabled": 2, "available": 1}
    assert snapshot["role_capacity"]["builder"] == {"configured": 2, "enabled": 1, "available": 1}
    assert snapshot["profile_limits"]["pm"] == 5
    assert snapshot["profile_limits"]["builder"] == 6
    assert snapshot["logical_operator_limits"]["DeepArchitect"] == 7
    assert snapshot["builder_pool"]["desired_total"] == 15
    assert snapshot["builder_pool"]["groups"]["codex-gpt-5.3-spark"] == 2
    assert snapshot["global_limits"]["max_workers"] == 11


def test_concurrency_policy_reads_backlog_snapshot(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "backlog.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "profile_limits": {"pm": 7},
                "logical_operator_limits": {"DeepArchitect": 9},
                "global_limits": {"max_workers": 12},
                "builder_pool": {
                    "desired_total": 18,
                    "groups": {"codex-gpt-5.3-spark": 3},
                },
            }
        ),
        encoding="utf-8",
    )
    policy = {
        "builder_pool": {
            "enabled": True,
            "desired_total": 14,
            "groups": {"codex-gpt-5.3-spark": {"desired": 1}},
        },
        "backlog_autoscaling": {
            "enabled": True,
            "snapshot_path": str(snapshot_path),
            "snapshot_ttl_seconds": 3600,
        },
    }

    assert cp.effective_profile_max_parallel("pm", 4, policy) == 7
    assert cp.effective_logical_max_parallel("DeepArchitect", 6, policy) == 9
    assert cp.effective_global_max_workers(4, policy) == 12
    assert cp.pool_group_desired("codex-gpt-5.3-spark", policy) == 3
    assert cp.builder_pool_desired_total(policy) == 18
