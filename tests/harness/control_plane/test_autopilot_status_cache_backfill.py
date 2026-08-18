#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[3] / "harness"
sys.path.insert(0, str(HARNESS_ROOT / "lib"))
import plan_validator


MODULE_PATH = HARNESS_ROOT / "tools" / "solar-autopilot-monitor.py"
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["solar_autopilot_monitor"] = mod
spec.loader.exec_module(mod)


def test_load_state_backfills_missing_status_cache_from_graph(tmp_path, monkeypatch) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    sid = "sprint-backfill-status"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps({
        "sprint_id": sid,
        "title": "Backfill Graph",
        "nodes": [
            {
                "id": "S1",
                "goal": "Implement slice",
                "status": "dispatched",
                "depends_on": [],
                "write_scope": ["/tmp/example"],
            }
        ],
    }) + "\n")
    state_path = tmp_path / "autopilot-state.json"
    state_path.write_text(json.dumps({
        "actions": {f"{sid}:ready_for_builder": {"ts": "2026-05-28T00:00:00Z"}},
        "target_actions": {},
    }) + "\n")

    monkeypatch.setattr(mod, "SPRINTS", sprints)
    monkeypatch.setattr(mod, "STATE", state_path)

    state = mod.load_state()

    status_path = sprints / f"{sid}.status.json"
    assert status_path.exists() is True
    payload = json.loads(status_path.read_text())
    assert payload["status"] == "active"
    assert payload["phase"] == "graph_in_progress"
    assert payload["graph_status_cache"] is True
    assert payload["active_node"] == "S1"
    assert f"{sid}:ready_for_builder" in state["actions"]


def test_load_state_refreshes_existing_status_projection_when_graph_changes(tmp_path, monkeypatch) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    sid = "sprint-refresh-status"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps({
        "sprint_id": sid,
        "title": "Refresh Graph",
        "nodes": [
            {
                "id": "N1",
                "goal": "New graph node",
                "status": "pending",
                "depends_on": [],
                "write_scope": ["/tmp/example"],
            }
        ],
    }) + "\n")
    status_path = sprints / f"{sid}.status.json"
    status_path.write_text(json.dumps({
        "sprint_id": sid,
        "status": "active",
        "phase": "planning_complete",
        "active_node": "S1",
        "open_nodes": ["S1", "S2"],
        "failed_nodes": [],
        "graph_parent_ready": {"ready": False, "open_nodes": ["S1", "S2"]},
        "task_graph_status": "active",
        "history": [],
    }) + "\n")
    state_path = tmp_path / "autopilot-state.json"
    state_path.write_text(json.dumps({"actions": {}, "target_actions": {}}) + "\n")

    monkeypatch.setattr(mod, "SPRINTS", sprints)
    monkeypatch.setattr(mod, "STATE", state_path)

    mod.load_state()

    payload = json.loads(status_path.read_text())
    assert payload["phase"] == "planning_complete"
    assert payload["active_node"] == "N1"
    assert payload["open_nodes"] == ["N1"]
    assert payload["task_graph_status"] == "active"
    assert any(item.get("event") == "graph_parent_projection_refreshed" for item in payload["history"])


def test_load_state_refreshes_requirement_coverage_when_graph_replanned(tmp_path, monkeypatch) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    sid = "sprint-refresh-coverage"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps({
        "sprint_id": sid,
        "title": "Coverage Refresh Graph",
        "nodes": [
            {
                "id": "N1",
                "goal": "Spec node",
                "status": "pending",
                "depends_on": [],
                "write_scope": ["/tmp/example"],
                "requirement_ids": ["REQ-001"],
            }
        ],
    }) + "\n")
    (sprints / f"{sid}.requirement_ir.json").write_text(json.dumps({
        "id": "req-refresh",
        "requirements": [
            {"id": "REQ-001", "source_text": "refresh", "success_criteria": ["refresh"]},
        ],
    }) + "\n")
    (sprints / f"{sid}.requirement_trace.json").write_text(json.dumps({
        "items": [{"requirement_id": "REQ-001", "mapped_nodes": ["S1"], "final_status": "missing"}],
    }) + "\n")
    (sprints / f"{sid}.coverage_report.json").write_text(json.dumps({"summary": {"missing": 1}}) + "\n")
    (sprints / f"{sid}.acceptance_verdict.json").write_text(json.dumps({"verdict": "FAIL"}) + "\n")
    state_path = tmp_path / "autopilot-state.json"
    state_path.write_text(json.dumps({"actions": {}, "target_actions": {}}) + "\n")

    calls: list[str] = []

    def fake_evaluate_sid(target_sid: str, *, sprints_dir, requested_verdict, write, require_pass):
        calls.append(target_sid)
        (sprints_dir / f"{target_sid}.requirement_trace.json").write_text(json.dumps({
            "items": [{"requirement_id": "REQ-001", "mapped_nodes": ["N1"], "final_status": "missing"}],
        }) + "\n")
        (sprints_dir / f"{target_sid}.coverage_report.json").write_text(json.dumps({"summary": {"missing": 1}}) + "\n")
        (sprints_dir / f"{target_sid}.acceptance_verdict.json").write_text(json.dumps({"verdict": "FAIL"}) + "\n")
        return {}

    monkeypatch.setattr(mod, "SPRINTS", sprints)
    monkeypatch.setattr(mod, "STATE", state_path)
    monkeypatch.setattr(mod, "evaluate_requirement_coverage_sid", fake_evaluate_sid)

    mod.load_state()

    payload = json.loads((sprints / f"{sid}.requirement_trace.json").read_text())
    assert calls == [sid]
    assert payload["items"][0]["mapped_nodes"] == ["N1"]


def test_dispatch_ready_graph_nodes_passes_configured_sprints_dir_to_plan_guard(
    tmp_path, monkeypatch
) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    sid = "sprint-plan-guard-path"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph = {"sprint_id": sid, "nodes": []}
    graph_path.write_text(json.dumps(graph) + "\n", encoding="utf-8")
    seen = {}

    def fake_plan_guard(candidate, *, sprints_dir, sid):
        seen.update(graph=candidate, sprints_dir=sprints_dir, sid=sid)
        return {"ok": True}

    monkeypatch.setattr(mod, "SPRINTS", sprints)
    monkeypatch.setattr(mod, "graph_path_for", lambda _sid: graph_path)
    monkeypatch.setattr(mod, "load_graph", lambda _path: graph)
    monkeypatch.setattr(mod, "validate_graph", lambda _graph: {"ok": True})
    monkeypatch.setattr(
        mod,
        "graph_dispatch_node_evals",
        lambda *_args, **_kwargs: {"ok": True, "skipped": []},
    )
    monkeypatch.setattr(mod, "graph_dispatch_ready", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(plan_validator, "check_planner_graph_dispatchable", fake_plan_guard)

    result = mod.dispatch_ready_graph_nodes(sid)

    assert result["ok"] is True
    assert seen == {"graph": graph, "sprints_dir": sprints, "sid": sid}


def test_builder_transition_clears_stale_planner_dispatch_claim(tmp_path, monkeypatch) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    sid = "sprint-clear-planner-claim"
    status = {
        "sprint_id": sid,
        "status": "active",
        "phase": "planning_complete",
        "handoff_to": "builder_main",
        "target_role": "builder_main",
        "plan_compile_required": True,
        "planner_dispatch_claim": {
            "owner": "operator_pool",
            "state": "failed",
            "failure_reason": "no_dispatchable_operator_for_role: planner",
        },
        "history": [],
    }
    saved = []
    events = []
    monkeypatch.setattr(mod, "SPRINTS", sprints)
    monkeypatch.setattr(plan_validator, "compile_planner_graph", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(mod, "save_json", lambda _path, payload: saved.append(dict(payload)))
    monkeypatch.setattr(mod, "append_event", lambda *args: events.append(args))

    changed = mod.normalize_status_to_workflow_route(
        sid,
        status,
        {
            "route_role": "builder_main",
            "stage": "planning_complete",
            "reason": "planner_artifacts_and_task_graph_ready",
        },
    )

    assert changed is True
    assert "planner_dispatch_claim" not in status
    assert "plan_compile_required" not in status
    assert saved[-1]["handoff_to"] == "builder_main"
    assert events[-1][3]["planner_claim_cleared"] is True
