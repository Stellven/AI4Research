#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[2] / 'harness')
ROUTE_PATH = ROOT / "status-server" / "routes" / "orchestration_routes.py"


def _load_routes():
    spec = importlib.util.spec_from_file_location("s04_orchestration_routes", ROUTE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["s04_orchestration_routes"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_builder_result_pending_is_presented_as_waiting_not_blocked() -> None:
    mod = _load_routes()
    output = json.dumps({
        "ok": False,
        "dispatched": [],
        "skipped": [{
            "node": "S1",
            "reason": "builder_operator_result_pending",
            "complete": False,
        }],
        "terminalized": [],
    })
    events = [{
        "ts": "2026-08-27T21:39:05Z",
        "type": "activity_failed",
        "actor": "coordinator",
        "payload": {
            "legacy_event": "graph_eval_dispatch_failed",
            "rc": 2,
            "output": output,
            "error": "graph_eval_dispatch_failed",
        },
    }]

    timeline = mod._timeline_from_events(events, {}, "2026-08-27T21:39:05Z")
    narrative = mod._narrative_from_events(events)

    assert timeline[0]["title"] == "Waiting for Builder result for S1"
    assert timeline[0]["tone"] == "working"
    assert narrative[0]["title"] == "Waiting for Builder result S1"
    assert narrative[0]["tone"] == "working"
    assert "durable result" in narrative[0]["summary"]


def test_real_evaluator_dispatch_failure_remains_blocked() -> None:
    mod = _load_routes()
    events = [{
        "ts": "2026-08-27T21:39:05Z",
        "type": "activity_failed",
        "actor": "coordinator",
        "payload": {
            "legacy_event": "graph_eval_dispatch_failed",
            "reason": "no_available_evaluator",
        },
    }]

    narrative = mod._narrative_from_events(events)

    assert narrative[0]["title"] == "Evaluation blocked"
    assert narrative[0]["tone"] == "blocked"


def test_native_elastic_planner_terminal_failure_precedes_missing_graph() -> None:
    mod = _load_routes()
    status = {
        "status": "failed",
        "phase": "elastic_planner_failed",
        "elastic_planner_failure": {
            "task_id": "pm-elastic-failed",
            "status": "failed_contract_closeout",
            "error": {
                "code": "failed_contract_closeout",
                "detail": "Planner output did not satisfy its contract.",
            },
            "retryable": False,
        },
    }

    stall = mod._build_stall_summary(status, [], [], False)

    assert stall["state"] == "elastic_planner_failed"
    assert stall["title"] == "Planning failed"
    assert stall["detail"] == "Planner output did not satisfy its contract."
    assert stall["reasons"] == ["failed_contract_closeout"]


def test_active_elastic_planning_without_graph_is_working_not_paused() -> None:
    mod = _load_routes()
    status = {
        "status": "active",
        "phase": "elastic_planning",
        "planner_dispatch_claim": {
            "state": "submitted",
            "planner_task_id": "pm-elastic-live",
        },
    }

    stall = mod._build_stall_summary(status, [], [], False)

    assert stall == {
        "is_stalled": False,
        "state": "elastic_planner_working",
        "severity": "ok",
        "title": "Planner is working",
        "detail": "The Elastic Planner is compiling the request; a DAG is not expected until planning finishes.",
        "reasons": [],
    }


def test_active_elastic_planning_full_projection_has_no_missing_graph_diagnostic(
    tmp_path: Path,
) -> None:
    mod = _load_routes()
    payload, degraded = _scenario_projection(
        mod,
        tmp_path,
        "elastic-planner-working",
        status={
            "status": "active",
            "phase": "elastic_planning",
            "planner_dispatch_claim": {
                "state": "submitted",
                "planner_task_id": "pm-elastic-live",
            },
        },
    )

    assert degraded == []
    assert payload["nodes"] == []
    assert payload["dispatch"]["blocker_diagnostics"] == []
    assert payload["dispatch"]["stall"]["state"] == "elastic_planner_working"
    assert payload["dispatch"]["stall"]["is_stalled"] is False


def test_terminal_elastic_planner_failure_full_projection_remains_failed(tmp_path: Path) -> None:
    mod = _load_routes()
    payload, degraded = _scenario_projection(
        mod,
        tmp_path,
        "elastic-planner-failed",
        status={
            "status": "failed",
            "phase": "elastic_planner_failed",
            "elastic_planner_failure": {
                "task_id": "pm-elastic-failed",
                "status": "failed_contract_closeout",
                "error": {
                    "code": "failed_contract_closeout",
                    "detail": "Planner output did not satisfy its contract.",
                },
                "retryable": False,
            },
        },
    )

    assert any(item.startswith("task_graph:missing") for item in degraded)
    assert payload["nodes"] == []
    assert payload["dispatch"]["stall"]["state"] == "elastic_planner_failed"
    assert payload["dispatch"]["stall"]["is_stalled"] is True
    assert payload["dispatch"]["stall"]["detail"] == "Planner output did not satisfy its contract."


def test_dashboard_node_projects_safe_prework_refusal_summary(tmp_path: Path) -> None:
    mod = _load_routes()
    payload, degraded = _scenario_projection(
        mod,
        tmp_path,
        "prework-refusal",
        status={"status": "active", "phase": "graph_dispatch_active"},
        graph={
            "nodes": [{
                "id": "S1",
                "goal": "Run bounded work",
                "status": "pending",
                "depends_on": [],
            }],
        },
        runtime_state={
            "S1": {
                "status": "queued",
                "blocking_reason": "frozen_physical_candidates_temporarily_unavailable",
                "retryable": True,
                "next_action": "Wait for cooldown.",
                "candidate_observations": [{"operator_id": "op.rank2", "state": "UNAVAILABLE"}],
                "pre_work_refusal": {
                    "operator_id": "op.rank1",
                    "task_id": "private-task-id",
                    "result_json": "/private/result.json",
                    "error": {"type": "provider_quota", "detail": "private log text"},
                    "next_candidate_id": "op.rank2",
                    "recorded_at": "2026-08-28T12:00:00Z",
                },
            },
        },
    )

    assert degraded == []
    card = payload["nodes"][0]
    assert card["pre_work_refusal"] == {
        "operator_id": "op.rank1",
        "error_type": "provider_quota",
        "next_candidate_id": "op.rank2",
        "recorded_at": "2026-08-28T12:00:00Z",
    }
    assert "private-task-id" not in json.dumps(card)
    assert "/private/result.json" not in json.dumps(card)


def test_transient_missing_plan_certificate_is_working_after_certification() -> None:
    mod = _load_routes()
    events = [{
        "ts": "2026-08-27T21:39:05Z",
        "type": "log_message",
        "actor": "graph-dispatch",
        "payload": {
            "legacy_event": "plan_validator_dispatch_refused",
            "errors": [{
                "code": "PLAN_CERTIFICATE_MISSING",
                "message": "planner graph carries no plan_certificate",
            }],
        },
    }]

    narrative = mod._narrative_from_events(events, plan_certified=True)

    assert narrative[0]["title"] == "Plan awaiting certification"
    assert narrative[0]["tone"] == "working"
    assert narrative[0]["summary"] == "Dispatch resumed after the plan certificate was recorded."


def test_missing_plan_certificate_remains_blocked_without_certification() -> None:
    mod = _load_routes()
    events = [{
        "ts": "2026-08-27T21:39:05Z",
        "type": "log_message",
        "actor": "graph-dispatch",
        "payload": {
            "legacy_event": "plan_validator_dispatch_refused",
            "errors": [{"code": "PLAN_CERTIFICATE_MISSING"}],
        },
    }]

    narrative = mod._narrative_from_events(events, plan_certified=False)

    assert narrative[0]["title"] == "Plan certification required"
    assert narrative[0]["tone"] == "blocked"


def test_context_injected_is_a_completed_preparation_step() -> None:
    mod = _load_routes()
    events = [{
        "ts": "2026-08-28T13:42:18Z",
        "type": "context_injected",
        "actor": "planner",
        "payload": {"node": "A1"},
    }]

    timeline = mod._timeline_from_events(events, {}, "2026-08-28T13:42:18Z")
    narrative = mod._narrative_from_events(events)

    assert timeline[0]["title"] == "Context prepared"
    assert timeline[0]["tone"] == "complete"
    assert narrative[0]["title"] == "Context prepared"
    assert narrative[0]["tone"] == "complete"
    assert "model work" in narrative[0]["summary"]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_fixed_contract_worker_binding_is_not_projected_as_missing() -> None:
    mod = _load_routes()
    operator_id = "autosci-research-synthesis-seed-fetch-worker"
    node = {
        "id": "seed_fetch",
        "goal": "Freeze the governed research request and source authority.",
        "status": "dispatched",
        "required_operator_id": operator_id,
        "required_capabilities": ["workflow.planning", "test.tdd"],
        "capability_capsule_id": "cap.research-seed-snapshot",
        "physical_plan_ir": {
            "selected_operator_id": operator_id,
            "capability_capsule_id": "cap.research-seed-snapshot",
            "execution_candidates": [{"operator_id": operator_id}],
        },
    }

    card = mod._build_node_cards("sprint-fixed", [node], {}, [])[0]

    assert card["selected_operator_id"] == operator_id
    assert card["capability_capsule_id"] == "cap.research-seed-snapshot"
    assert card["candidate_workers_seen"] is True
    assert card["missing_capabilities"] == []
    assert card["route_decision"] == "fixed_contract_binding"


def test_required_operator_without_compiled_candidate_remains_unavailable() -> None:
    mod = _load_routes()
    node = {
        "id": "seed_fetch",
        "required_operator_id": "missing-worker",
        "required_capabilities": ["workflow.planning"],
        "capability_capsule_id": "cap.research-seed-snapshot",
        "physical_plan_ir": {"execution_candidates": []},
    }

    card = mod._build_node_cards("sprint-fixed", [node], {}, [])[0]

    assert card["candidate_workers_seen"] is False
    assert card["missing_capabilities"] == ["workflow.planning"]
    assert card["route_decision"] == "no_routing_record"


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
                "owner": "builder_main",
                "task_type": "implementation",
                "dispatch_task_type": "implementation",
                "depends_on": [],
                "status": "dispatched",
                "required_capabilities": ["harness.status"],
                "gate": "G_STATUS_API_READY",
                "estimated_cost": 1,
            },
            {
                "id": "N2",
                "goal": "blocked branch",
                "owner": "verifier",
                "task_type": "verification",
                "dispatch_task_type": "verification",
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
    runtime_state: dict | None = None,
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
    if runtime_state is not None:
        _write_json(
            tree["sprints"] / f"{sid}.task_dag.state.json",
            {
                "schema_version": "solar.task_graph_state.v1",
                "sprint_id": sid,
                "node_results": runtime_state,
                "gate_results": {},
            },
        )
    for suffix, text in (artifacts or {}).items():
        _write_text(tree["sprints"] / f"{sid}.{suffix}", text)
    if routing is not None:
        _write_json(tree["state"] / "autopilot-state.json", {"routing_decisions": [{**row, "sprint_id": sid} for row in routing]})
    if panes is not None:
        _write_json(tree["state"] / "pane-state.json", {"panes": panes})
    if operators is not None:
        _write_json(tree["config"] / "physical-operators.json", {"version": 1, "operators": operators})
    return mod.build_projection_payload(sid)


def test_projection_overlays_authoritative_task_state_sidecar(tmp_path: Path) -> None:
    mod = _load_routes()
    payload, degraded = _scenario_projection(
        mod,
        tmp_path,
        "fixed-state",
        status={"status": "active", "phase": "implementation"},
        graph={
            "nodes": [
                {
                    "id": "seed_fetch",
                    "goal": "Freeze the governed request.",
                    "status": "pending",
                }
            ]
        },
        runtime_state={"seed_fetch": {"status": "dispatched"}},
    )

    assert degraded == []
    assert payload["task_graph"]["nodes"][0]["workflow_status"] == "dispatched"
    assert payload["task_graph"]["nodes"][0]["status"] == "active"


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


def test_projection_and_sprint_index_rehydrate_split_runtime_state(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "split-runtime-projection")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-split-runtime-projection"
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "title": "Split runtime projection",
        "status": "passed",
        "phase": "finalized",
    })
    _write_json(tree["sprints"] / f"{sid}.task_graph.json", {
        "sprint_id": sid,
        "required_gates": ["G1"],
        "nodes": [{"id": "N1", "goal": "Complete work", "depends_on": [], "gate": "G1"}],
    })
    _write_json(tree["sprints"] / f"{sid}.task_dag.state.json", {
        "schema_version": "solar.task_graph_state.v1",
        "sprint_id": sid,
        "graph_ref": f"{sid}.task_graph.json",
        "node_results": {"N1": {"status": "passed"}},
        "gate_results": {"G1": {"status": "passed", "node": "N1"}},
    })

    projection, degraded = mod.build_projection_payload(sid, mode="fast")

    assert degraded == []
    assert projection["status"] == "passed"
    assert projection["phase"] == "finalized"
    assert projection["summary"]["progress"]["passed_nodes"] == 1
    assert projection["summary"]["progress"]["status_counts"] == {"passed": 1}
    assert projection["task_graph"]["nodes"][0]["status"] == "passed"

    index = mod._sprint_status_rows(limit=10)
    row = next(item for item in index if item["sprint_id"] == sid)
    assert row["node_status_counts"] == {"passed": 1}


def test_dashboard_reads_scheduler_underscore_state_filename(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "underscore-runtime-state")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-underscore-runtime-state"
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "status": "active",
        "phase": "planning_complete",
    })
    _write_json(tree["sprints"] / f"{sid}.task_graph.json", {
        "sprint_id": sid,
        "runtime_state_filename": f"{sid}.task_graph_state.json",
        "nodes": [{"id": "S1", "goal": "Work", "depends_on": []}],
    })
    _write_json(tree["sprints"] / f"{sid}.task_graph_state.json", {
        "schema_version": "solar.task_graph_state.v1",
        "artifact_role": "mutable_execution_ledger",
        "nodes": {"S1": {"status": "dispatched"}},
        "node_results": {"S1": {"status": "dispatched"}},
        "ready_nodes": [],
        "revision": 1,
        "events": [],
    })

    payload, degraded = mod.build_dashboard_payload(sid)

    assert degraded == []
    assert payload["dag"]["nodes"][0]["workflow_status"] == "dispatched"


def test_dashboard_projects_static_frozen_candidate_unsat_from_split_state(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "frozen-unsat")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-frozen-unsat"
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "status": "active",
        "phase": "planning_complete",
    })
    _write_json(tree["sprints"] / f"{sid}.task_graph.json", {
        "sprint_id": sid,
        "runtime_state_filename": f"{sid}.task_graph_state.json",
        "nodes": [{"id": "S1", "goal": "Execute", "depends_on": []}],
    })
    observations = [{
        "operator_id": "op.claude",
        "rank": 1,
        "state": "UNAVAILABLE",
        "reason": "physical_operator_provider_incompatible:allowed=openai:actual=anthropic",
    }]
    _write_json(tree["sprints"] / f"{sid}.task_graph_state.json", {
        "schema_version": "solar.task_graph_state.v1",
        "nodes": {"S1": {"status": "worker_blocked"}},
        "node_results": {
            "S1": {
                "status": "worker_blocked",
                "blocking_reason": "frozen_physical_plan_unsatisfiable",
                "retryable": False,
                "wait_classification": "static_incompatible",
                "candidate_observations": observations,
                "next_action": "Update provider policy, then explicitly resume.",
            }
        },
    })

    payload, degraded = mod.build_dashboard_payload(sid)

    assert degraded == []
    card = payload["dag"]["nodes"][0]
    assert card["status"] == "blocked"
    assert card["workflow_status"] == "worker_blocked"
    assert card["blocked_reason"] == "frozen_physical_plan_unsatisfiable"
    assert card["candidate_observations"] == observations
    assert card["retryable"] is False
    assert card["next_action"] == "Update provider policy, then explicitly resume."
    assert payload["stall"]["state"] == "frozen_physical_plan_unsatisfiable"
    assert payload["stall"]["is_stalled"] is True


def test_dashboard_projects_bounded_frozen_candidate_wait_from_split_state(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "frozen-wait")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-frozen-wait"
    retry_after = "2026-08-28T12:30:00Z"
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "status": "active",
        "phase": "planning_complete",
    })
    _write_json(tree["sprints"] / f"{sid}.task_graph.json", {
        "sprint_id": sid,
        "runtime_state_filename": f"{sid}.task_graph_state.json",
        "nodes": [{"id": "S1", "goal": "Execute", "depends_on": []}],
    })
    _write_json(tree["sprints"] / f"{sid}.task_graph_state.json", {
        "schema_version": "solar.task_graph_state.v1",
        "node_results": {
            "S1": {
                "status": "queued",
                "blocking_reason": "frozen_physical_candidates_temporarily_unavailable",
                "retryable": True,
                "retry_after": retry_after,
                "wait_classification": "transient",
                "candidate_wait_attempts": 2,
                "candidate_observations": [{
                    "operator_id": "op.primary",
                    "rank": 1,
                    "state": "UNAVAILABLE",
                    "reason": "worker_capacity_exhausted",
                }],
                "next_action": "Wait for capacity to clear.",
            }
        },
    })

    payload, degraded = mod.build_dashboard_payload(sid)

    assert degraded == []
    card = payload["dag"]["nodes"][0]
    assert card["status"] == "pending"
    assert card["blocked_reason"] == "frozen_physical_candidates_temporarily_unavailable"
    assert card["retryable"] is True
    assert card["retry_after"] == retry_after
    assert card["candidate_wait_attempts"] == 2
    assert payload["stall"]["state"] == "frozen_physical_candidates_waiting"
    assert retry_after in payload["stall"]["detail"]


def test_terminal_direct_answer_does_not_report_missing_dag_stall(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "direct-terminal")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-direct-terminal"
    report = tree["sprints"] / f"{sid}.direct-response-report.md"
    _write_text(report, "Photosynthesis converts light energy into stored chemical energy.\n")
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "status": "passed",
        "phase": "direct_response_complete",
        "execution_mode": "direct_response",
        "direct_response_ref": {
            "path": str(report),
            "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        },
    })

    payload, degraded = mod.build_dashboard_payload(sid)

    assert degraded == []
    assert payload["progress"]["total_nodes"] == 0
    assert payload["stall"]["is_stalled"] is False


def test_terminal_direct_answer_requires_existing_report(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "direct-terminal-missing")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-direct-terminal-missing"
    report = tree["sprints"] / f"{sid}.direct-response-report.md"
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "status": "passed",
        "phase": "direct_response_complete",
        "execution_mode": "direct_response",
        "direct_response_ref": {"path": str(report), "sha256": "a" * 64},
    })

    payload, degraded = mod.build_dashboard_payload(sid)

    assert f"direct_response:invalid:{sid}:report_missing" in degraded
    assert f"task_graph:missing:{sid}" in degraded
    assert payload["stall"]["is_stalled"] is True


def test_terminal_direct_answer_rejects_report_outside_sprints(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "direct-terminal-outside")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-direct-terminal-outside"
    report = tmp_path / "outside-report.md"
    _write_text(report, "This file is outside the sprint authority.\n")
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "status": "passed",
        "phase": "direct_response_complete",
        "execution_mode": "direct_response",
        "direct_response_ref": {
            "path": str(report),
            "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        },
    })

    _payload, degraded = mod.build_dashboard_payload(sid)

    assert f"direct_response:invalid:{sid}:path_outside_sprints" in degraded
    assert f"task_graph:missing:{sid}" in degraded


def test_terminal_direct_answer_rejects_tampered_report(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "direct-terminal-tampered")
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {}
    sid = "sprint-direct-terminal-tampered"
    report = tree["sprints"] / f"{sid}.direct-response-report.md"
    _write_text(report, "Original answer.\n")
    recorded_sha = hashlib.sha256(report.read_bytes()).hexdigest()
    _write_text(report, "Tampered answer.\n")
    _write_json(tree["sprints"] / f"{sid}.status.json", {
        "sprint_id": sid,
        "status": "passed",
        "phase": "direct_response_complete",
        "execution_mode": "direct_response",
        "direct_response_ref": {"path": str(report), "sha256": recorded_sha},
    })

    _payload, degraded = mod.build_dashboard_payload(sid)

    assert f"direct_response:invalid:{sid}:sha256_mismatch" in degraded
    assert f"task_graph:missing:{sid}" in degraded


def test_dashboard_payload_preserves_compiler_owned_node_role_authority(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    mod._capability_registry = lambda: {"pane-builder": ["harness.status"]}

    payload, degraded = mod.build_dashboard_payload("sprint-active")

    assert degraded == []
    nodes = {node["id"]: node for node in payload["dag"]["nodes"]}
    assert nodes["N1"]["owner"] == "builder_main"
    assert nodes["N1"]["task_type"] == "implementation"
    assert nodes["N1"]["dispatch_task_type"] == "implementation"
    assert nodes["N1"]["status"] == "active"
    assert nodes["N1"]["workflow_status"] == "dispatched"
    assert nodes["N2"]["owner"] == "verifier"
    assert nodes["N2"]["task_type"] == "verification"


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
    assert payload["projection_mode"] == "full"
    assert payload["sprint_id"] == "sprint-active"
    assert payload["lazy_slices"]["events"] == "/events?sprint_id=sprint-active&limit=140"
    assert payload["lazy_slices"]["deliverables"] == "/sprints/sprint-active/deliverables"
    assert payload["lazy_slices"]["usage"] == "/usage"
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

    fast_payload, fast_degraded = mod.build_projection_payload("sprint-active", mode="fast")

    assert fast_degraded == []
    assert fast_payload["projection_mode"] == "fast"
    assert fast_payload["sprint_id"] == "sprint-active"
    assert fast_payload["human_gates"][0]["kind"] == "plan_review"
    assert fast_payload["available_actions"][0]["id"] == "view_artifacts"
    assert fast_payload["events"] == []
    assert fast_payload["timeline"] == []
    assert actions["wake"]["availability"] == "unsupported_deferred"
    assert actions["wake"]["enabled"] is False
    assert actions["retry_dispatch"]["safe"] is False
    assert actions["retry_dispatch"]["enabled"] is False
    assert payload["runtime_health"][0]["pane_id"] == "pane-builder"
    assert payload["timeline"]


def test_projection_exposes_full_original_prompt_without_json_navigation(
    tmp_path: Path,
) -> None:
    mod = _load_routes()
    prompt = (
        "Analyze the attached article and preserve every comparison dimension.\n\n"
        "Requirements:\n- cite the source\n- explain uncertainty\n- keep the final table"
    )
    payload, degraded = _scenario_projection(
        mod,
        tmp_path,
        "full-original-prompt",
        status={"status": "active", "phase": "planning"},
        graph={"nodes": []},
        artifacts={
            "raw_intent.json": json.dumps(
                {"raw": {"text": prompt}},
                ensure_ascii=False,
            ),
        },
    )

    assert degraded == []
    assert payload["original_prompt"] == prompt
    assert payload["sprint"]["original_prompt"] == prompt
    assert "\n\nRequirements:\n" in payload["original_prompt"]
    assert payload["title"].endswith("…")


def _install_fake_solar(bin_dir: Path) -> list[str]:
    script = bin_dir / "fake_solar.py"
    _write_text(
        script,
        """from __future__ import annotations

import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
root = Path(os.environ["HARNESS_DIR"])
(root / "verdict-args.txt").write_text(" ".join(args) + "\\n", encoding="utf-8")
cmd = args[1]
sid = args[2]
verdict = args[3] if len(args) > 3 else ""
status, phase = "active", "unknown"
if cmd == "plan-verdict":
    phase = "plan_reviewed"
    status = "approved" if verdict == "approve" else "active"
elif cmd == "eval-verdict":
    phase = "eval_completed"
    status = "passed" if verdict == "pass" else "failed_review"
elif cmd == "handoff-submit":
    phase, status = "implementation_completed", "reviewing"
(root / "sprints").mkdir(parents=True, exist_ok=True)
(root / "sprints" / f"{sid}.status.json").write_text(
    json.dumps({"sprint_id": sid, "status": status, "phase": phase, "title": "Verdict Sprint"}),
    encoding="utf-8",
)
print(f"{cmd}: {sid} -> {status}")
""",
    )
    return [sys.executable, str(script), "harness"]


def test_plan_verdict_payload_validates_and_runs_safe_cli(tmp_path: Path, monkeypatch) -> None:
    mod = _load_routes()
    tree = _fixture_tree(tmp_path)
    _patch_dirs(mod, tree)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_prefix = _install_fake_solar(fake_bin)
    monkeypatch.setattr(mod, "_solar_harness_command_prefix", lambda: command_prefix)
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
    command_prefix = _install_fake_solar(fake_bin)
    monkeypatch.setattr(mod, "_solar_harness_command_prefix", lambda: command_prefix)
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


def test_projection_events_are_scoped_and_normalized(tmp_path: Path) -> None:
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "event-scope")
    _patch_dirs(mod, tree)
    sid = "sprint-event-scope"
    (tree["sessions"] / sid).mkdir(parents=True)
    _write_text(
        tree["sessions"] / sid / "events.jsonl",
        "\n".join(
            [
                json.dumps({"ts": "2026-06-26T00:00:01Z", "type": "missing_id"}),
                json.dumps({"ts": "2026-06-26T00:00:02Z", "type": "right_id", "sprint_id": sid}),
                json.dumps({"ts": "2026-06-26T00:00:03Z", "type": "wrong_id", "sprint_id": "sprint-other"}),
            ]
        )
        + "\n",
    )

    events = mod._projection_events(sid, limit=10)

    assert [event["type"] for event in events] == ["missing_id", "right_id"]
    assert {event["sprint_id"] for event in events} == {sid}
    assert {event["_event_scope"] for event in events} == {"requested"}
    assert {event["_event_source"] for event in events} == {"session_file"}


def test_projection_narrative_dedups_and_humanizes(tmp_path: Path) -> None:
    """WS3 contract: build_projection_payload emits a de-noised, de-duplicated human
    narrative — the coordinator double-write is collapsed, machine noise is dropped, the
    internal tokens are humanized, and it ships in fast mode (what the client fetches)."""
    mod = _load_routes()
    tree = _scenario_tree(tmp_path, "narrative")
    _patch_dirs(mod, tree)
    sid = "sprint-narrative"
    _write_json(
        tree["sprints"] / f"{sid}.status.json",
        {"sprint_id": sid, "status": "active", "phase": "build_complete", "title": "Narrative"},
    )
    sess = tree["sessions"] / sid
    sess.mkdir(parents=True, exist_ok=True)
    events = [
        {"sprint_id": sid, "ts": "2026-06-26T10:00:00Z", "type": "log_message", "actor": "coordinator",
         "payload": {"legacy_event": "dispatched", "node_id": "build-api", "role": "builder", "round": 1}},
        # dual-write sibling of the same action (carries the same legacy_event)
        {"sprint_id": sid, "ts": "2026-06-26T10:00:00Z", "type": "command_issued", "actor": "coordinator",
         "payload": {"legacy_event": "dispatched", "node_id": "build-api", "role": "builder", "round": 1}},
        # machine noise — must be dropped
        {"sprint_id": sid, "ts": "2026-06-26T10:00:30Z", "type": "log_message", "actor": "solar-autopilot",
         "payload": {"legacy_event": "autopilot_probe_failed"}},
        {"sprint_id": sid, "ts": "2026-06-26T10:01:00Z", "type": "log_message", "actor": "coordinator",
         "payload": {"legacy_event": "handle_passed_completed", "node_id": "build-api", "role": "builder", "round": 1}},
    ]
    (sess / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    payload, _ = mod.build_projection_payload(sid)
    narrative = payload.get("narrative")
    assert isinstance(narrative, list) and narrative, "narrative must be present and non-empty"
    titles = [str(row.get("title") or "") for row in narrative]
    tokens = [str(row.get("token") or "") for row in narrative]
    assert sum(1 for t in tokens if t == "dispatched") == 1, f"dual-write not collapsed: {tokens}"
    assert not any("autopilot" in t for t in tokens), f"machine noise leaked: {tokens}"
    assert any(t.startswith("Routed") for t in titles), f"not humanized: {titles}"
    assert any("completed" in t.lower() for t in titles), f"missing completion: {titles}"

    fast, _ = mod.build_projection_payload(sid, mode="fast")
    assert fast.get("narrative"), "narrative must ship in fast mode too"


def test_projection_narrative_preserves_dispatch_reason_and_collapses_prerequisite_waits() -> None:
    mod = _load_routes()
    pending = json.dumps(
        {
            "ok": True,
            "dispatched": [],
            "waiting": [
                {
                    "node": "S1",
                    "reason": "builder_operator_result_pending",
                }
            ],
            "blocking_skips": [],
        }
    )
    events = [
        {
            "ts": f"2026-06-26T10:00:{second:02d}Z",
            "type": "activity_failed" if second < 31 else "log_message",
            "actor": "coordinator",
            "payload": {
                "legacy_event": (
                    "graph_eval_dispatch_failed" if second < 31 else "graph_nodes_dispatched"
                ),
                (
                    "output" if second < 31 else "eval_output"
                ): (
                    json.dumps(
                        {
                            "ok": False,
                            "dispatched": [],
                            "skipped": [
                                {
                                    "node": "S1",
                                    "reason": "builder_operator_result_pending",
                                }
                            ],
                        }
                    )
                    if second < 31
                    else pending
                ),
            },
        }
        for second in (1, 16, 31)
    ]

    narrative = mod._narrative_from_events(events)

    waits = [row for row in narrative if row["title"].startswith("Waiting for Builder result")]
    assert len(waits) == 1
    assert waits[0]["tone"] == "working"
    assert waits[0]["summary"] == "Evaluation starts after the Builder publishes its durable result."

    real_failure = mod._narrative_from_events(
        [
            {
                "ts": f"2026-06-26T10:01:{second:02d}Z",
                "type": "activity_failed",
                "actor": "coordinator",
                "payload": {
                    "legacy_event": "graph_eval_dispatch_failed",
                    "output": json.dumps(
                        {
                            "ok": False,
                            "skipped": [
                                {"node": "S1", "reason": "no_available_evaluator"}
                            ],
                        }
                    ),
                },
            }
            for second in (0, 15)
        ]
    )
    assert len(real_failure) == 1
    assert real_failure[0]["title"] == "Evaluation blocked S1"
    assert real_failure[0]["summary"] == "no available evaluator"
    assert real_failure[0]["tone"] == "blocked"


def test_failed_planner_dispatch_is_projected_as_a_stall(tmp_path: Path) -> None:
    mod = _load_routes()

    projection, _ = _scenario_projection(
        mod,
        tmp_path,
        "planner-dispatch-failed",
        status={
            "status": "drafting",
            "phase": "prd_ready",
            "handoff_to": "planner",
            "planner_dispatch_claim": {
                "owner": "operator_pool",
                "state": "failed",
                "failure_reason": "no_dispatchable_operator_for_role: planner",
                "returncode": 1,
            },
        },
        graph={"nodes": [{"id": "N0", "goal": "plan", "status": "pending"}]},
    )
    stall = projection["dispatch"]["stall"]

    assert stall["is_stalled"] is True
    assert stall["state"] == "planner_dispatch_failed"
    assert stall["title"] == "Planner temporarily unavailable"
    assert stall["reasons"] == ["no_dispatchable_operator_for_role: planner"]
    assert "No eligible Planner worker" in stall["detail"]


def test_completed_planning_supersedes_an_old_failed_planner_claim(tmp_path: Path) -> None:
    mod = _load_routes()

    projection, _ = _scenario_projection(
        mod,
        tmp_path,
        "planner-dispatch-recovered",
        status={
            "status": "active",
            "phase": "planning_complete",
            "handoff_to": "builder_main",
            "planner_dispatch_claim": {
                "owner": "operator_pool",
                "state": "failed",
                "failure_reason": "no_dispatchable_operator_for_role: planner",
            },
        },
        graph={"nodes": [{"id": "N1", "goal": "build", "status": "pending"}]},
    )

    stall = projection["dispatch"]["stall"]
    assert stall.get("state") != "planner_dispatch_failed"
    assert stall.get("title") != "Planner temporarily unavailable"
