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


def test_worker_catalog_advertises_requirement_compiler_capsules(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_GRAPH_DISPATCH_FAKE_WORKERS", "1")
    monkeypatch.delenv("SOLAR_GRAPH_DISPATCH_RESTRICT_SESSION", raising=False)
    worker = mod._discover_workers(dry_run=True)[0]
    capabilities = set(worker["capabilities"])

    assert "cap.requirement-compiler-planner" in capabilities
    assert "cap.requirement-compiler-implementation" in capabilities
    assert "cap.requirement-compiler-verification" in capabilities
    assert "cap.requirement-compiler-audit" in capabilities
    assert "artifact.requirement_trace" in capabilities


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
