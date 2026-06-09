#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "lib" / "graph_node_dispatcher.py"
spec = importlib.util.spec_from_file_location("graph_node_dispatcher", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["graph_node_dispatcher"] = mod
spec.loader.exec_module(mod)


def test_fake_worker_catalog_includes_spec_and_codex_bridge(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_GRAPH_DISPATCH_FAKE_WORKERS", "1")
    monkeypatch.delenv("SOLAR_GRAPH_DISPATCH_RESTRICT_SESSION", raising=False)
    workers = mod._discover_workers(dry_run=True)
    assert workers
    worker = workers[0]
    assert "spec.write" in worker["skills"]
    assert "provider.contract" in worker["skills"]
    assert "codex.bridge" in worker["capabilities"]
    assert "pane3.bridge" in worker["capabilities"]


def test_dry_run_worker_discovery_includes_operator_pool(monkeypatch) -> None:
    monkeypatch.delenv("SOLAR_GRAPH_DISPATCH_FAKE_WORKERS", raising=False)
    monkeypatch.delenv("SOLAR_GRAPH_DISPATCH_RESTRICT_SESSION", raising=False)
    monkeypatch.setattr(mod, "_prune_expired_operator_blocks", lambda: None)
    monkeypatch.setattr(mod, "_builder_operator_pool_available_count", lambda: 1)
    monkeypatch.setattr(mod.subprocess, "check_output", lambda *args, **kwargs: b"")

    workers = mod._discover_workers(dry_run=True)

    pool_workers = [item for item in workers if str(item.get("pane", "")).startswith("operator-pool:builder")]
    assert pool_workers
    assert pool_workers[0]["role"] == "builder"
    assert "codex.bridge" in pool_workers[0]["capabilities"]
    assert "guard.secret-leak-guard" in pool_workers[0]["capabilities"]
    assert "resource.repo-workspace" in pool_workers[0]["capabilities"]


def test_pm_submit_parser_accepts_dry_run_operator_id() -> None:
    parsed = mod._parse_pm_submit_output(
        "[DRY-RUN] operator_id = mini-codex-gpt53-spark-builder-6\n"
        "[DRY-RUN] task_id     = pm-sprint-S1-test\n"
    )

    assert parsed["operator_id"] == "mini-codex-gpt53-spark-builder-6"


def test_worker_discovery_keeps_planner_panes_for_role_aware_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(
        mod.subprocess,
        "check_output",
        lambda *a, **kw: (
            b"solar-harness:0.1\tPlanner | \xe6\xa8\xa1\xe5\x9e\x8b:Opus\n"
            b"solar-harness-lab:0.0\tBuilder | \xe6\xa8\xa1\xe5\x9e\x8b:GLM\n"
        ),
    )
    monkeypatch.setattr(mod, "read_lease", lambda pane: None)
    monkeypatch.setattr(mod, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(mod, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(mod, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(mod, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(mod, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(mod, "_pane_health", lambda pane: {})
    monkeypatch.setattr(mod, "_pane_current_command", lambda pane: "claude")

    workers = mod._discover_workers(dry_run=False)

    roles = {item["pane"]: item["dispatch_role"] for item in workers}
    assert roles["solar-harness:0.1"] == "planner"
    assert roles["solar-harness-lab:0.0"] == "builder"
