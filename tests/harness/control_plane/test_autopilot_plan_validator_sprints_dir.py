from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


def _load_monitor():
    module_path = Path(__file__).resolve().parents[3] / "harness" / "tools" / "solar-autopilot-monitor.py"
    spec = importlib.util.spec_from_file_location("solar_autopilot_monitor_plan_dir_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dispatch_guard_uses_monitor_sprints_directory(tmp_path, monkeypatch):
    monitor = _load_monitor()
    sid = "sprint-plan-guard"
    graph = {"sprint_id": sid, "nodes": []}
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    observed: dict[str, object] = {}

    def check_planner_graph_dispatchable(payload, *, sprints_dir, sid):
        observed.update(payload=payload, sprints_dir=sprints_dir, sid=sid)
        return {"ok": True}

    monkeypatch.setattr(monitor, "SPRINTS", tmp_path)
    monkeypatch.setattr(monitor, "graph_path_for", lambda _sid: graph_path)
    monkeypatch.setattr(monitor, "load_graph", lambda _path: graph)
    monkeypatch.setattr(monitor, "validate_graph", lambda _graph: {"ok": True})
    monkeypatch.setattr(
        monitor,
        "graph_dispatch_node_evals",
        lambda *_args, **_kwargs: {"ok": True, "dispatched": [], "skipped": []},
    )
    monkeypatch.setattr(
        monitor,
        "graph_dispatch_ready",
        lambda *_args, **_kwargs: {"ok": True, "dispatched": [], "skipped": []},
    )
    monkeypatch.setitem(
        sys.modules,
        "plan_validator",
        types.SimpleNamespace(check_planner_graph_dispatchable=check_planner_graph_dispatchable),
    )

    result = monitor.dispatch_ready_graph_nodes(sid, lease=False)

    assert result["ok"] is True
    assert observed == {"payload": graph, "sprints_dir": tmp_path, "sid": sid}
