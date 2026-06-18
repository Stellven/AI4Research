#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = ROOT / "status-server" / "routes" / "orchestration_routes.py"


def _load_routes():
    spec = importlib.util.spec_from_file_location("s04_orchestration_routes", ROUTE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["s04_orchestration_routes"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_tree(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "harness"
    sprints = root / "sprints"
    sessions = root / "sessions"
    state = root / "state"
    config = root / "config"
    _write_json(config / "actor-hosts.json", {
        "hosts": {
            "mini": {"host_id": "mini", "host_type": "claude_code_session"},
        }
    })
    _write_json(config / "agent-actors.json", {
        "actors": {
            "builder-a": {
                "actor_id": "builder-a",
                "host_id": "mini",
                "role": "builder",
                "capability_profile": {"harness.status": 5, "dag.ready_nodes": 4},
            }
        }
    })
    _write_json(config / "physical-operators.json", {
        "operators": {
            "builder-a": {
                "pane": "pane-builder",
                "compat_maps_to": {"host_type": "tmux_pane"},
            }
        }
    })
    _write_json(sprints / "sprint-active.status.json", {
        "sprint_id": "sprint-active",
        "epic_id": "epic-demo",
        "title": "Active sprint",
        "status": "active",
        "phase": "planning_complete",
    })
    _write_json(sprints / "sprint-active.task_graph.json", {
        "sprint_id": "sprint-active",
        "required_gates": ["G_STATUS_API_READY"],
        "nodes": [
            {
                "id": "N1",
                "goal": "status api",
                "depends_on": [],
                "status": "dispatched",
                "required_capabilities": ["harness.status"],
                "gate": "G_STATUS_API_READY",
                "estimated_cost": 1,
            },
            {
                "id": "N2",
                "goal": "blocked branch",
                "depends_on": ["N1"],
                "status": "blocked",
                "required_capabilities": ["dag.ready_nodes"],
                "gate": "G_STATUS_API_READY",
                "estimated_cost": 2,
            },
        ],
    })
    _write_text(sprints / "sprint-active.design.md", "# Design\n")
    _write_text(sprints / "sprint-active.plan.md", "# Plan\n")
    _write_json(sprints / "sprint-active.requirement_trace.json", {"requirements": []})
    _write_json(sprints / "sprint-active.coverage_report.json", {"summary": {"covered": 1, "missing": 0}})
    _write_json(sprints / "sprint-active.acceptance_verdict.json", {"verdict": "PASS", "reasons": []})
    _write_json(state / "pane-state.json", {
        "panes": [
            {"id": "pane-builder", "role": "builder", "state": "active", "model": "spark"},
        ]
    })
    _write_json(state / "autopilot-state.json", {
        "routing_decisions": [
            {
                "sprint_id": "sprint-active",
                "node_id": "N1",
                "decision": "dispatched",
                "target_pane": "pane-builder",
                "provided_capabilities": ["harness.status"],
                "blocked_reason": "",
            },
            {
                "sprint_id": "sprint-active",
                "node_id": "N2",
                "decision": "blocked",
                "target_pane": "pane-builder",
                "provided_capabilities": [],
                "blocked_reason": "dependency_blocked",
            },
        ]
    })
    return {"root": root, "sprints": sprints, "sessions": sessions, "state": state}


def _scenario_tree(tmp_path: Path, name: str) -> dict[str, Path]:
    root = tmp_path / name / "harness"
    sprints = root / "sprints"
    sessions = root / "sessions"
    state = root / "state"
    config = root / "config"
    for path in (sprints, sessions, state, config):
        path.mkdir(parents=True, exist_ok=True)
    return {"root": root, "sprints": sprints, "sessions": sessions, "state": state, "config": config}


def _patch_dirs(mod, tree: dict[str, Path]) -> None:
    mod.HARNESS_DIR = tree["root"]
    mod.SPRINTS_DIR = tree["sprints"]
    mod.SESSIONS_DIR = tree["sessions"]
    mod.STATE_DIR = tree["state"]
    mod.EVENTS_JSONL = tree["root"] / "events.jsonl"


def _scenario_projection(
    mod,
    tmp_path: Path,
    name: str,
    *,
    status: dict | None = None,
    graph: dict | None = None,
    artifacts: dict[str, str] | None = None,
    routing: list[dict] | None = None,
    panes: list[dict] | None = None,
    operators: dict | None = None,
) -> tuple[dict, list[str]]:
    sid = f"sprint-{name}"
    tree = _scenario_tree(tmp_path, name)
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {
        str(pane.get("id") or ""): [str(cap) for cap in (pane.get("provided_capabilities") or [])]
        for pane in (panes or [])
    }
    if status is not None:
        payload = {"sprint_id": sid, "title": name.replace("-", " ").title(), **status}
        _write_json(tree["sprints"] / f"{sid}.status.json", payload)
    if graph is not None:
        _write_json(tree["sprints"] / f"{sid}.task_graph.json", {"sprint_id": sid, **graph})
    for suffix, text in (artifacts or {}).items():
        _write_text(tree["sprints"] / f"{sid}.{suffix}", text)
    if routing is not None:
        _write_json(tree["state"] / "autopilot-state.json", {"routing_decisions": [{**row, "sprint_id": sid} for row in routing]})
    if panes is not None:
        _write_json(tree["state"] / "pane-state.json", {"panes": panes})
    if operators is not None:
        _write_json(tree["config"] / "physical-operators.json", {"version": 1, "operators": operators})
    return mod.build_projection_payload(sid)


def test_dashboard_payload_separates_actorhost_from_pane_carrier(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {"pane-builder": ["harness.status", "dag.ready_nodes"]}

    payload, degraded = mod.build_dashboard_payload("sprint-active")

    assert degraded == []
    pane = payload["capabilities"]["pane_supply"][0]
    assert pane["pane_carrier"]["pane_id"] == "pane-builder"
    assert pane["actor_id"] == "builder-a"
    assert pane["host_id"] == "mini"
    assert pane["host_type"] == "claude_code_session"
    assert pane["lease_state"] == "idle"
    assert pane["actorhost"]["resolution_source"] == "actor_hosts"


def test_dashboard_payload_exposes_route_decision_and_blocked_reason(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {"pane-builder": ["harness.status"]}

    payload, degraded = mod.build_dashboard_payload("sprint-active")

    assert degraded == []
    nodes = {node["id"]: node for node in payload["dag"]["nodes"]}
    assert nodes["N1"]["route_decision"] == "dispatched"
    assert nodes["N1"]["pane_carrier"]["pane_id"] == "pane-builder"
    assert nodes["N1"]["actor_id"] == "builder-a"
    assert nodes["N2"]["route_decision"] == "blocked"
    assert nodes["N2"]["blocked_reason"] == "dependency_blocked"


def test_dashboard_payload_reports_degraded_missing_task_graph(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    (tree["sprints"] / "sprint-active.task_graph.json").unlink()

    payload, degraded = mod.build_dashboard_payload("sprint-active")

    assert any(item.startswith("task_graph:missing") for item in degraded)
    assert payload["blocker_diagnostics"][0]["kind"] == "task_graph"
    assert payload["progress"]["total_nodes"] == 0


def test_projection_payload_surfaces_ui_action_contract(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {"pane-builder": ["harness.status"]}

    payload, degraded = mod.build_projection_payload("sprint-active")

    assert degraded == []
    assert payload["projection_schema"] == "solar.dashboard_projection.v1"
    assert payload["sprint_id"] == "sprint-active"
    assert payload["sprint"]["phase"] == "planning_complete"
    assert payload["requirements"]["present"] is True
    assert payload["requirements"]["coverage_summary"]["covered"] == 1
    assert payload["plan"]["complete"] is True
    assert payload["task_graph"]["present"] is True
    assert payload["nodes"][0]["id"] == "N1"
    assert payload["dependencies"][0] == {"from": "N1", "to": "N2"}
    assert payload["dispatch"]["capability_mismatch"]["present"] is True
    assert payload["human_gates"][0]["kind"] == "plan_review"
    assert payload["human_gates"][0]["status"] == "available"
    assert payload["human_gates"][0]["allowed_actions"] == ["approve", "reject"]
    assert payload["evaluation"]["verdict"] == "PASS"
    assert payload["operators"]
    assert payload["human_action_required"]["type"] == "capability_mismatch"
    assert payload["capability_mismatch"]["present"] is True
    assert payload["capability_mismatch"]["blocked_node"] == "N2"
    assert payload["capability_mismatch"]["missing_capability"] == "dag.ready_nodes"
    assert any(item["kind"] == "task_graph" for item in payload["artifacts"])
    actions = {item["id"]: item for item in payload["available_actions"]}
    assert actions["view_artifacts"]["availability"] == "supported_now"
    assert actions["view_artifacts"]["enabled"] is True
    assert actions["wake"]["availability"] == "unsupported_deferred"
    assert actions["wake"]["enabled"] is False
    assert actions["retry_dispatch"]["safe"] is False
    assert actions["retry_dispatch"]["enabled"] is False
    assert payload["runtime_health"][0]["pane_id"] == "pane-builder"
    assert payload["timeline"]


def _install_fake_solar(bin_dir: Path) -> None:
    _write_text(
        bin_dir / "solar",
        """#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" > "$HARNESS_DIR/verdict-args.txt"
cmd="$2"
sid="$3"
verdict="${4:-}"
status="active"
phase="unknown"
if [[ "$cmd" == "plan-verdict" ]]; then
  phase="plan_reviewed"
  if [[ "$verdict" == "approve" ]]; then status="approved"; else status="active"; fi
elif [[ "$cmd" == "eval-verdict" ]]; then
  phase="eval_completed"
  if [[ "$verdict" == "pass" ]]; then status="passed"; else status="failed_review"; fi
elif [[ "$cmd" == "handoff-submit" ]]; then
  sid="$3"
  phase="implementation_completed"
  status="reviewing"
fi
mkdir -p "$HARNESS_DIR/sprints"
printf '{"sprint_id":"%s","status":"%s","phase":"%s","title":"Verdict Sprint"}\n' "$sid" "$status" "$phase" > "$HARNESS_DIR/sprints/$sid.status.json"
echo "$cmd: $sid -> $status"
""",
    )
    (bin_dir / "solar").chmod(0o755)


def test_plan_verdict_payload_validates_and_runs_safe_cli(tmp_path: Path, monkeypatch) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _install_fake_solar(fake_bin)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("HARNESS_DIR", str(tree["root"]))

    payload, status_code = mod.submit_plan_verdict_payload("sprint-active", {"verdict": "approve", "reason": "scope ok"})

    assert status_code == 200, payload
    assert payload["ok"] is True
    assert payload["projection"]["status"] == "approved"
    assert "plan-verdict sprint-active approve scope ok" in (tree["root"] / "verdict-args.txt").read_text(encoding="utf-8")
    assert payload["command"] == "solar harness plan-verdict <sid> <verdict> <reason>"


def test_verdict_payload_rejects_unsafe_or_incomplete_requests(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)

    payload, status_code = mod.submit_plan_verdict_payload("../bad", {"verdict": "approve"})
    assert status_code == 400
    assert payload["error"] == "invalid_sprint_id"

    payload, status_code = mod.submit_plan_verdict_payload("sprint-active", {"verdict": "skip"})
    assert status_code == 400
    assert payload["error"] == "invalid_verdict"

    payload, status_code = mod.submit_eval_verdict_payload("sprint-active", {"verdict": "fail"})
    assert status_code == 400
    assert payload["error"] == "reason_required"


def test_handoff_submit_payload_is_supported_only_for_ready_handoff(tmp_path: Path, monkeypatch) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _install_fake_solar(fake_bin)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("HARNESS_DIR", str(tree["root"]))
    _write_json(tree["sprints"] / "sprint-active.status.json", {
        "sprint_id": "sprint-active",
        "status": "approved",
        "phase": "plan_reviewed",
        "title": "Ready handoff",
    })
    _write_text(tree["sprints"] / "sprint-active.handoff.md", "# Handoff\n")
    _write_json(tree["sprints"] / "sprint-active.task_graph.json", {
        "sprint_id": "sprint-active",
        "nodes": [
            {
                "id": "N1",
                "goal": "handoff node",
                "depends_on": [],
                "status": "passed",
                "required_capabilities": [],
            }
        ],
    })
    _write_json(tree["state"] / "autopilot-state.json", {"routing_decisions": []})

    payload, degraded = mod.build_projection_payload("sprint-active")
    assert degraded == []
    actions = {item["id"]: item for item in payload["available_actions"]}
    assert actions["handoff_submit"]["availability"] == "supported_now"
    assert actions["handoff_submit"]["enabled"] is True
    assert actions["handoff_submit"]["endpoint"] == "/api/sprints/sprint-active/handoff-submit"

    result, status_code = mod.submit_handoff_payload("sprint-active", {})
    assert status_code == 200, result
    assert result["ok"] is True
    assert result["projection"]["status"] == "reviewing"
    assert "handoff-submit sprint-active" in (tree["root"] / "verdict-args.txt").read_text(encoding="utf-8")


def test_projection_scenario_map_for_frontend_states(tmp_path: Path) -> None:
    mod = _load_routes()

    empty, degraded = _scenario_projection(mod, tmp_path, "missing")
    assert empty["sprint"]["status"] == ""
    assert any(item.startswith("sprint_status:missing") for item in degraded)
    assert empty["plan"]["status"] == "waiting"

    spec, _ = _scenario_projection(
        mod,
        tmp_path,
        "spec",
        status={"status": "active", "phase": "spec"},
    )
    assert spec["sprint"]["phase"] == "spec"
    assert spec["human_gates"][0]["status"] == "waiting"
    assert "plan_approve" not in {item["id"] for item in spec["available_actions"]}

    partial_plan, _ = _scenario_projection(
        mod,
        tmp_path,
        "partial-planning",
        status={"status": "active", "phase": "planning"},
        artifacts={"plan.md": "# Partial Plan\n"},
    )
    assert partial_plan["plan"]["status"] == "partial"
    assert partial_plan["human_gates"][0]["status"] == "waiting"
    assert "plan_approve" not in {item["id"] for item in partial_plan["available_actions"]}

    plan_review, _ = _scenario_projection(
        mod,
        tmp_path,
        "plan-review",
        status={"status": "active", "phase": "planning_complete"},
        graph={"nodes": [{"id": "N1", "goal": "build", "depends_on": [], "status": "pending"}]},
        artifacts={"design.md": "# Design\n", "plan.md": "# Plan\n"},
    )
    plan_actions = {item["id"]: item for item in plan_review["available_actions"]}
    assert plan_review["plan"]["complete"] is True
    assert plan_review["human_gates"][0]["status"] == "available"
    assert plan_actions["plan_approve"]["enabled"] is True
    assert plan_actions["plan_reject"]["endpoint"] == "/api/sprints/sprint-plan-review/plan-verdict"

    running, _ = _scenario_projection(
        mod,
        tmp_path,
        "running",
        status={"status": "active", "phase": "planning_complete"},
        graph={"nodes": [{"id": "N1", "goal": "running node", "depends_on": [], "status": "dispatched"}]},
        routing=[{"node_id": "N1", "decision": "dispatched", "target_pane": "pane-builder", "provided_capabilities": []}],
        panes=[{"id": "pane-builder", "role": "builder", "state": "running", "model": "claude-sonnet"}],
    )
    assert running["summary"]["active_node"] == "N1"
    assert running["operators"][0]["readiness"] == "busy"

    stalled, _ = _scenario_projection(
        mod,
        tmp_path,
        "stalled",
        status={"status": "active", "phase": "planning_complete"},
        graph={"nodes": [{"id": "N1", "goal": "email", "depends_on": [], "status": "blocked", "required_capabilities": ["transactional_email"]}]},
        routing=[{"node_id": "N1", "decision": "no_matching_worker", "blocked_reason": "no_matching_worker", "provided_capabilities": []}],
    )
    stalled_actions = {item["id"]: item for item in stalled["available_actions"]}
    assert stalled["capability_mismatch"]["present"] is True
    assert stalled["capability_mismatch"]["missing_capability"] == "transactional_email"
    assert stalled_actions["retry_dispatch"]["enabled"] is False

    handoff, _ = _scenario_projection(
        mod,
        tmp_path,
        "handoff",
        status={"status": "approved", "phase": "plan_reviewed"},
        graph={"nodes": [{"id": "N1", "goal": "done", "depends_on": [], "status": "passed"}]},
        artifacts={"handoff.md": "# Handoff\n"},
    )
    handoff_actions = {item["id"]: item for item in handoff["available_actions"]}
    assert handoff["human_action_required"]["type"] == "handoff_submit"
    assert handoff_actions["handoff_submit"]["enabled"] is True

    eval_review, _ = _scenario_projection(
        mod,
        tmp_path,
        "eval-review",
        status={"status": "reviewing", "phase": "implementation_completed"},
        graph={"nodes": [{"id": "N1", "goal": "done", "depends_on": [], "status": "passed"}]},
        artifacts={"handoff.md": "# Handoff\n", "eval.md": "# Eval\n"},
    )
    eval_actions = {item["id"]: item for item in eval_review["available_actions"]}
    assert eval_review["human_gates"][1]["status"] == "available"
    assert eval_actions["eval_pass"]["enabled"] is True
    assert eval_actions["eval_fail"]["endpoint"] == "/api/sprints/sprint-eval-review/eval-verdict"

    done, _ = _scenario_projection(
        mod,
        tmp_path,
        "done",
        status={"status": "passed", "phase": "eval_completed"},
        graph={"nodes": [{"id": "N1", "goal": "done", "depends_on": [], "status": "passed"}]},
        artifacts={"handoff.md": "# Handoff\n", "eval.md": "# Eval\n"},
    )
    done_actions = {item["id"]: item for item in done["available_actions"]}
    assert done["human_action_required"]["type"] == "none"
    assert done_actions["edit_rerun"]["enabled"] is False

    failed_review, _ = _scenario_projection(
        mod,
        tmp_path,
        "failed-review",
        status={"status": "failed_review", "phase": "eval_completed"},
        graph={"nodes": [{"id": "N1", "goal": "fix", "depends_on": [], "status": "failed"}]},
        artifacts={"eval.md": "# Eval failed\n"},
    )
    assert failed_review["human_action_required"]["type"] == "builder_fixes"

    operator_blocked, _ = _scenario_projection(
        mod,
        tmp_path,
        "operator-blocked",
        status={"status": "active", "phase": "planning_complete"},
        graph={"nodes": []},
        operators={
            "op-auth": {
                "display_name": "Auth blocked",
                "role": "builder",
                "enabled": True,
                "available": True,
                "auth_mode": "subscription",
                "key_ref": "claude_subscription",
                "state": {"runtime_state": "auth_expired"},
            },
            "op-quota": {
                "display_name": "Quota blocked",
                "role": "planner",
                "enabled": True,
                "available": True,
                "quota_guard_state": "quota_exhausted",
            },
        },
    )
    readiness = {item["operator_id"]: item["readiness"] for item in operator_blocked["operators"]}
    assert readiness["op-auth"] == "auth_blocked"
    assert readiness["op-quota"] == "quota_blocked"
