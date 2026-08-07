#!/usr/bin/env python3
"""Regression tests for full physical-operator fleet exposure in status-server."""

import importlib.util
import json
from pathlib import Path


MODULE = (Path(__file__).resolve().parents[2] / 'harness') / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


def test_physical_operator_summary_returns_full_fleet_and_prioritizes_idle(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    config_dir = harness / "config"
    config_dir.mkdir(parents=True)
    registry = {
        "version": 1,
        "operators": {
            "op-disabled": {
                "role": "builder",
                "backend": "command",
                "enabled": False,
                "available": False,
            },
            "op-idle": {
                "role": "planner",
                "backend": "claude-cli",
                "enabled": True,
                "available": True,
            },
            "op-busy": {
                "role": "evaluator",
                "backend": "claude-cli",
                "enabled": True,
                "available": True,
            },
        },
    }
    (config_dir / "physical-operators.json").write_text(json.dumps(registry), encoding="utf-8")

    lease_dir = harness / "run" / "operator-leases"
    lease_dir.mkdir(parents=True)
    (lease_dir / "op-busy.json").write_text(
        json.dumps({"state": "leased", "expires_at": "2099-01-01T00:00:00Z"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(status_server, "HARNESS_DIR", harness)

    summary = status_server._physical_operator_summary(limit=2)

    assert summary["count"] == 3
    assert len(summary["items"]) == 3
    assert summary["items"][0]["operator_id"] == "op-idle"
    assert summary["items"][-1]["operator_id"] == "op-disabled"


def test_physical_operator_summary_uses_central_runtime_state(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    config_dir = harness / "config"
    config_dir.mkdir(parents=True)
    registry = {
        "version": 1,
        "operators": {
            "op-stale": {
                "role": "evaluator",
                "backend": "command",
                "enabled": True,
                "available": True,
            },
        },
    }
    (config_dir / "physical-operators.json").write_text(json.dumps(registry), encoding="utf-8")
    lease_dir = harness / "run" / "operator-leases"
    lease_dir.mkdir(parents=True)
    (lease_dir / "op-stale.json").write_text(
        json.dumps({"state": "running", "expires_at": "2099-01-01T00:00:00Z", "worker_pid": 999999}),
        encoding="utf-8",
    )

    monkeypatch.setattr(status_server, "HARNESS_DIR", harness)
    monkeypatch.setattr(status_server, "_central_operator_runtime_state", lambda operator_id: "idle")

    summary = status_server._physical_operator_summary(limit=2)

    item = summary["items"][0]
    assert item["operator_id"] == "op-stale"
    assert item["runtime_state"] == "idle"
    assert item["runtime_state_source"] == "operator_runtime"
    assert summary["dispatchable"] == 1


def test_physical_operator_summary_exposes_planner_evaluator_role_pools(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    config_dir = harness / "config"
    config_dir.mkdir(parents=True)
    registry = {
        "version": 1,
        "operators": {
            "planner-cooldown": {
                "role": "planner",
                "roles": ["planner"],
                "backend": "claude-cli",
                "enabled": True,
                "available": True,
                "quota_guard_state": "cooldown",
                "quota_refresh_at": "2099-01-01T00:00:00Z",
            },
            "planner-evaluator-auth": {
                "role": "planner",
                "roles": ["planner", "evaluator"],
                "backend": "antigravity",
                "enabled": True,
                "available": True,
                "quota_guard_state": "auth_expired",
                "quota_refresh_at": "2099-01-02T00:00:00Z",
            },
            "evaluator-idle": {
                "role": "evaluator",
                "roles": ["evaluator"],
                "backend": "claude-cli",
                "enabled": True,
                "available": True,
            },
        },
    }
    (config_dir / "physical-operators.json").write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(status_server, "HARNESS_DIR", harness)

    summary = status_server._physical_operator_summary(limit=4)

    planner = summary["role_pools"]["planner"]
    evaluator = summary["role_pools"]["evaluator"]
    assert planner["total"] == 2
    assert planner["dispatchable"] == 0
    assert planner["status"] == "blocked"
    assert planner["counts"]["cooldown"] == 1
    assert planner["counts"]["auth_expired"] == 1
    assert planner["next_available_at"] == "2099-01-01T00:00:00Z"
    assert evaluator["total"] == 2
    assert evaluator["dispatchable"] == 1
    assert evaluator["status"] == "ok"
