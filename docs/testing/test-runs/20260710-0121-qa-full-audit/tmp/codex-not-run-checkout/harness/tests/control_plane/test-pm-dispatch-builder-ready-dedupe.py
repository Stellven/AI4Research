from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_pm_dispatch(tmp_path: Path, monkeypatch):
    harness_dir = tmp_path / "harness"
    for rel in ("run/pm-inbox", "run/operator-status", "run/operator-leases", "sprints", "tools", "lib"):
        (harness_dir / rel).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    module_path = Path(__file__).resolve().parents[2] / "tools" / "pm_dispatch.py"
    spec = importlib.util.spec_from_file_location("pm_dispatch_builder_ready_dedupe_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builder_ready_nodes_skip_dispatched_markers_and_active_status(tmp_path: Path, monkeypatch):
    pm_dispatch = _load_pm_dispatch(tmp_path, monkeypatch)
    sprint_id = "sprint-test-builder-ready-dedupe"
    graph_path = pm_dispatch.SPRINTS_DIR / f"{sprint_id}.task_graph.json"
    graph_path.write_text(json.dumps({"sprint_id": sprint_id, "nodes": []}), encoding="utf-8")

    graph = {
        "nodes": [
            {"id": "A", "status": "pending", "pm_task_id": "pm-already-submitted"},
            {"id": "B", "status": "in_progress"},
            {"id": "C", "status": "pending", "goal": "safe latent node"},
            {"id": "D", "status": "pending"},
        ],
        "node_results": {
            "D": {"dispatched_via": "pm_dispatch", "pm_task_id": "pm-result-marker"},
        },
    }

    class FakeGraphScheduler:
        SPRINTS_DIR = pm_dispatch.SPRINTS_DIR

        @staticmethod
        def load_graph(path):
            return graph

        @staticmethod
        def ready_nodes(loaded_graph):
            return list(loaded_graph["nodes"])

    monkeypatch.setattr(pm_dispatch, "_load_graph_scheduler_module", lambda: FakeGraphScheduler)

    nodes, meta = pm_dispatch._builder_ready_nodes_for_sprint(sprint_id)

    assert meta["ok"] is True
    assert [node["id"] for node in nodes] == ["C"]


def test_builder_namespace_logical_operator_is_builder_ready(tmp_path: Path, monkeypatch):
    pm_dispatch = _load_pm_dispatch(tmp_path, monkeypatch)

    assert pm_dispatch._node_is_builder_ready({"logical_operator": "builder.fix"})
    assert pm_dispatch._node_is_builder_ready({"logical_operator": "builder.implementation"})
    assert not pm_dispatch._node_is_builder_ready({"logical_operator": "eval.review"})


def test_node_builder_objective_requires_canonical_handoff(tmp_path: Path, monkeypatch):
    pm_dispatch = _load_pm_dispatch(tmp_path, monkeypatch)

    objective = pm_dispatch._node_builder_objective(
        "sprint-test",
        {"id": "N1", "goal": "ship the fix", "acceptance": ["tests pass"]},
    )

    assert "canonical handoff" in objective
    assert "sprint-test.N1-handoff.md" in objective
    assert ".pm-result.md" in objective
