from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def _load_monitor(tmp_path: Path, monkeypatch):
    harness_dir = tmp_path / "harness"
    for rel in ("run", "state", "events", "sprints", "tools", "lib", "tests"):
        (harness_dir / rel).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    module_path = Path(__file__).resolve().parents[2] / "tools" / "solar-autopilot-monitor.py"
    spec = importlib.util.spec_from_file_location("solar_autopilot_monitor_builder_drain_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_drain_builder_ready_backlog_invokes_pm_dispatch(tmp_path: Path, monkeypatch):
    monitor = _load_monitor(tmp_path, monkeypatch)
    calls = []

    class Proc:
        returncode = 0
        stdout = json.dumps({"ok": True, "latent_builder_ready": 2, "submitted": [{"ok": True}]})

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return Proc()

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    result = monitor.drain_builder_ready_backlog()

    assert result["ok"] is True
    assert result["action"] == "builder_ready_drain"
    assert calls
    cmd, kwargs = calls[0]
    assert cmd[-2:] == ["drain-builder-ready", "--json"]
    assert kwargs["env"]["HARNESS_DIR"] == str(monitor.HARNESS)
    assert kwargs["env"]["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] == "1"
    assert kwargs["env"]["SOLAR_PM_DISPATCH_BACKPRESSURE_NO_RECORD"] == "1"


def test_scan_once_drains_builder_ready_when_apply_dispatch(tmp_path: Path, monkeypatch):
    monitor = _load_monitor(tmp_path, monkeypatch)
    monkeypatch.setattr(monitor, "reconcile_pm_inbox", lambda: {"action": "pm_inbox_reconcile", "ok": True})
    monkeypatch.setattr(monitor, "retry_queue", lambda *args, **kwargs: [])
    monkeypatch.setattr(monitor, "inspect_epics", lambda: [])
    monkeypatch.setattr(monitor, "inspect_epic_child_state_drift", lambda: [])
    monkeypatch.setattr(monitor, "inspect_sprints", lambda **kwargs: [])
    monkeypatch.setattr(monitor, "inspect_deepresearch_quality_gates", lambda **kwargs: [])
    monkeypatch.setattr(monitor, "inspect_panes", lambda *args, **kwargs: [])
    monkeypatch.setattr(monitor, "inspect_knowledge_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(monitor, "inspect_model_registry", lambda *args, **kwargs: [])
    monkeypatch.setattr(monitor, "apply_findings", lambda *args, **kwargs: [])
    monkeypatch.setattr(monitor, "update_idle_pane_titles", lambda state: [])
    monkeypatch.setattr(monitor, "load_queue", lambda: [])
    monkeypatch.setattr(monitor, "save_state", lambda state: None)
    if hasattr(monitor, "pm_throughput_snapshot"):
        monkeypatch.setattr(
            monitor,
            "pm_throughput_snapshot",
            lambda: {"submitted": 0, "completed": 0, "failed": 0, "pending": 0},
        )
    monkeypatch.setattr(
        monitor,
        "drain_builder_ready_backlog",
        lambda: {"action": "builder_ready_drain", "ok": True, "latent_builder_ready": 1},
    )

    args = argparse.Namespace(apply=True, dispatch=True, loop=False, epic="", cooldown=0, stall_seconds=600)
    result = monitor.scan_once(args, {})

    assert any(action.get("action") == "builder_ready_drain" for action in result["actions"])
