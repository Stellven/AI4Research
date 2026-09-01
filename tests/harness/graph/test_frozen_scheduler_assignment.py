"""Frozen SchedulerInput authority on the legacy graph-scheduler bridge."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import types

import pytest

import graph_scheduler as gs
import graph_node_dispatcher as gnd
import scheduler_input


@pytest.fixture(autouse=True)
def _admit_unit_projection(monkeypatch):
    monkeypatch.setattr(
        scheduler_input,
        "verify_runtime_projection",
        lambda *_args, **_kwargs: {"ok": True, "errors": []},
    )
    monkeypatch.setattr(gnd, "_broker_env", lambda *_args, **_kwargs: {})


def _node(
    node_id: str,
    *,
    priority: int,
    candidates: list[tuple[str, int]],
    depends_on: list[str] | None = None,
) -> dict:
    return {
        "id": node_id,
        "goal": f"Run {node_id}",
        "logical_operator": "FrozenWorker",
        "dispatch_task_type": "frozen-work",
        "depends_on": list(depends_on or []),
        "requirement_ids": [f"REQ-{node_id}"],
        "capability_capsule_id": "cap.frozen.v1",
        "capsule_binding": {
            "capsule_ids": ["cap.frozen.v1"],
            "composition_id": None,
            "contract_sha256": "0" * 64,
        },
        "physical_candidates": [
            {"operator_id": operator_id, "rank": rank, "admission_state": "ELIGIBLE"}
            for operator_id, rank in candidates
        ],
        "artifact_contract": {"consumes": [], "produces": [f"artifact.{node_id}.v1"]},
        "evaluation_binding": {"deterministic_gate_ids": ["gate.test"], "semantic_evaluator_ids": []},
        "resource_requirements": {
            "cpu_cores_min": 1,
            "memory_mb_min": 128,
            "gpu_required": False,
            "network": "forbidden",
        },
        "effects": ["read", "write"],
        "priority": priority,
        "failure_policy": {"max_attempts": 2, "on_exhausted": "fail_run"},
        "write_scope": [f"/tmp/{node_id}"],
    }


def _graph(nodes: list[dict]) -> dict:
    return {
        "schema_version": "solar.scheduler_runtime_projection.v1",
        "sprint_id": "frozen-sprint",
        "planning_authority": "frozen_execution_plan_v1",
        "nodes": nodes,
    }


def _worker(operator_id: str, *, busy: bool = False, unavailable_reason: str = "") -> dict:
    return {
        "operator_id": operator_id,
        "pane": f"operator:{operator_id}",
        "role": "builder",
        "busy": busy,
        "unavailable_reason": unavailable_reason,
        # Deliberately irrelevant to frozen selection: exact operator identity
        # replaces legacy capability/skill/model fallback.
        "skills": [],
        "capabilities": [],
        "models": [],
    }


def test_assign_ready_uses_priority_then_ascending_frozen_candidate_rank(monkeypatch) -> None:
    graph = _graph([
        _node("a-low", priority=1, candidates=[("op.low", 1)]),
        _node(
            "z-high",
            priority=100,
            candidates=[("op.high-last", 3), ("op.high-primary", 1), ("op.high-fallback", 2)],
        ),
    ])

    def forbidden_enrichment(*_args, **_kwargs):
        raise AssertionError("frozen scheduler graph must not be enriched")

    monkeypatch.setattr(gs, "auto_enrich_graph", forbidden_enrichment)
    result = gs.assign_ready(
        graph,
        [
            _worker("op.high-primary", busy=True),
            _worker("op.high-fallback"),
            _worker("op.high-last"),
            _worker("op.low"),
            _worker("op.not-admitted"),
        ],
        max_parallel=2,
    )

    assert [item["node"] for item in result["assigned"]] == ["z-high", "a-low"]
    high = result["assigned"][0]
    assert high["operator_id"] == "op.high-fallback"
    assert high["candidate_rank"] == 2
    assert [(item["operator_id"], item["state"]) for item in high["candidate_observations"]] == [
        ("op.high-primary", "UNAVAILABLE"),
        ("op.high-fallback", "READY"),
        ("op.high-last", "NOT_EVALUATED_AFTER_SELECTION"),
    ]
    assert result["capability_enrichment"] == {"changed_nodes": [], "auto": False}


def test_assign_ready_keeps_dependency_blocked_frozen_node_out_of_batch() -> None:
    graph = _graph([
        _node("parent", priority=1, candidates=[("op.parent", 1)]),
        _node("child", priority=999, candidates=[("op.child", 1)], depends_on=["parent"]),
    ])

    result = gs.assign_ready(
        graph,
        [_worker("op.parent"), _worker("op.child")],
        max_parallel=2,
    )

    assert [item["node"] for item in result["assigned"]] == ["parent"]
    assert result["batch"] == ["parent"]


def test_enqueue_ready_uses_frozen_payload_without_compilation_or_materialization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)]),
    ])
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text("{}", encoding="utf-8")

    def forbidden_enrichment(*_args, **_kwargs):
        raise AssertionError("frozen scheduler graph must not be enriched")

    monkeypatch.setattr(gs, "auto_enrich_graph", forbidden_enrichment)
    forbidden_compiler = types.ModuleType("apo_plan_compiler")

    def forbidden_planning(*_args, **_kwargs):
        raise AssertionError("frozen scheduler graph must not be compiled or materialized")

    forbidden_compiler.compile_execution_plan_for_node = forbidden_planning
    forbidden_compiler.materialize_execution_plan_artifacts = forbidden_planning
    monkeypatch.setitem(sys.modules, "apo_plan_compiler", forbidden_compiler)
    result = gs.enqueue_ready(
        graph,
        str(graph_path),
        [_worker("op.primary", unavailable_reason="cooldown"), _worker("op.fallback")],
        dry_run=True,
    )

    payload = result["enqueued"][0]["payload"]
    assert payload["assignment"]["operator_id"] == "op.fallback"
    assert payload["capsule_plan_ir"]["capsule_authority"] == "frozen_scheduler_input"
    assert payload["physical_plan_ir"]["selected_operator_id"] == "op.fallback"
    assert [item["operator_id"] for item in payload["physical_plan_ir"]["execution_candidates"]] == [
        "op.primary",
        "op.fallback",
    ]
    assert payload["plan_artifacts"] == {
        "authority": "frozen_scheduler_input",
        "scheduler_input_ref": {},
    }
    assert not (tmp_path / "sprints").exists()


def test_enqueue_ready_preserves_frozen_primary_capsule_when_guard_is_first(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.primary", 1)]),
    ])
    node = graph["nodes"][0]
    node["capsule_binding"]["capsule_ids"] = [
        "guard.secret-leak-guard",
        "cap.frozen.v1",
    ]
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}
    queue_module = types.ModuleType("task_queue")

    def capture_enqueue(sprint_id, task, priority, payload):
        captured.update(
            sprint_id=sprint_id,
            task=task,
            priority=priority,
            payload=payload,
        )
        return {"ok": True, "result": "queued", "id": "queue-primary-capsule"}

    queue_module.enqueue = capture_enqueue
    monkeypatch.setitem(sys.modules, "task_queue", queue_module)

    result = gs.enqueue_ready(
        graph,
        str(graph_path),
        [_worker("op.primary")],
        dry_run=False,
    )

    assert result["enqueued"][0]["queue"]["result"] == "queued"
    payload = captured["payload"]
    assert payload["capsule_plan_ir"]["capsule_ids"] == [
        "guard.secret-leak-guard",
        "cap.frozen.v1",
    ]
    assert payload["capsule_plan_ir"]["capability_capsule_id"] == "cap.frozen.v1"
    assert payload["node"]["capability_capsule_id"] == "cap.frozen.v1"
    assert graph["nodes"][0]["capability_capsule_id"] == "cap.frozen.v1"


def test_enqueue_ready_blocks_unregistered_frozen_candidates_as_unsatisfiable(tmp_path: Path) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)]),
    ])
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text("{}", encoding="utf-8")

    result = gs.enqueue_ready(
        graph,
        str(graph_path),
        [_worker("op.not-admitted")],
        dry_run=True,
    )

    assert result["enqueued"] == []
    assert result["queued"][0]["reason"] == "frozen_physical_plan_unsatisfiable"
    assert result["queued"][0]["retryable"] is False
    assert result["worker_blocked"][0]["node"] == "frozen"
    assert graph["nodes"][0]["status"] == "worker_blocked"
    assert graph["node_results"]["frozen"]["blocking_reason"] == "frozen_physical_plan_unsatisfiable"
    assert graph["node_results"]["frozen"]["retryable"] is False
    assert graph["node_results"]["frozen"]["wait_classification"] == "static_incompatible"
    repeated = gs.enqueue_ready(
        graph,
        str(graph_path),
        [_worker("op.not-admitted")],
        dry_run=True,
    )
    assert repeated["enqueued"] == []
    assert repeated["queued"] == []
    assert "dispatch_id" not in graph["nodes"][0]


def test_dispatcher_projects_ranked_frozen_candidates_from_registry_and_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.fallback", 2), ("op.primary", 1)]),
    ])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    monkeypatch.setattr(
        gnd,
        "_physical_operator_spec",
        lambda operator_id: {
            "enabled": True,
            "available": True,
            "role": "builder",
            "model": operator_id,
        },
    )
    monkeypatch.setattr(gnd, "_operator_runtime_state_for_graph", lambda _operator_id: "idle")

    workers = gnd._scheduler_input_bound_physical_workers(graph, graph_path)
    assignment = gs.assign_ready(graph, workers)

    assert [worker["operator_id"] for worker in workers] == ["op.primary", "op.fallback"]
    assert assignment["assigned"][0]["operator_id"] == "op.primary"
    assert assignment["assigned"][0]["candidate_rank"] == 1


def test_dispatcher_frozen_candidate_falls_back_when_primary_is_busy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)]),
    ])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    monkeypatch.setattr(
        gnd,
        "_physical_operator_spec",
        lambda _operator_id: {"enabled": True, "available": True, "role": "builder"},
    )
    monkeypatch.setattr(
        gnd,
        "_operator_runtime_state_for_graph",
        lambda operator_id: "leased" if operator_id == "op.primary" else "idle",
    )

    workers = gnd._scheduler_input_bound_physical_workers(graph, graph_path)
    assignment = gs.assign_ready(graph, workers)

    assert workers[0]["runtime_state"] == "leased"
    assert workers[0]["busy"] is True
    assert assignment["assigned"][0]["operator_id"] == "op.fallback"
    assert assignment["assigned"][0]["candidate_rank"] == 2


def test_dispatcher_frozen_candidate_falls_back_when_primary_provider_is_incompatible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.claude", 1), ("op.codex", 2)]),
    ])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    specs = {
        "op.claude": {
            "enabled": True,
            "available": True,
            "role": "builder",
            "provider": "anthropic",
            "model": "claude-sonnet",
        },
        "op.codex": {
            "enabled": True,
            "available": True,
            "role": "builder",
            "provider": "openai",
            "model": "gpt-5.5",
        },
    }
    monkeypatch.setattr(gnd, "_physical_operator_spec", lambda operator_id: specs[operator_id])
    monkeypatch.setattr(gnd, "_operator_runtime_state_for_graph", lambda _operator_id: "idle")
    monkeypatch.setattr(
        gnd,
        "_broker_env",
        lambda *_args, **_kwargs: {"SOLAR_PM_DEFAULT_PROVIDERS": "openai"},
    )

    workers = gnd._scheduler_input_bound_physical_workers(graph, graph_path)
    assignment = gs.assign_ready(graph, workers)

    assert workers[0]["operator_id"] == "op.claude"
    assert workers[0]["unavailable_reason"].startswith(
        "physical_operator_provider_incompatible:"
    )
    assert assignment["assigned"][0]["operator_id"] == "op.codex"
    assert assignment["assigned"][0]["candidate_rank"] == 2
    assert assignment["assigned"][0]["candidate_observations"][0]["state"] == "UNAVAILABLE"


def test_dispatcher_all_provider_incompatible_candidates_block_without_retry_churn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.claude-1", 1), ("op.claude-2", 2)]),
    ])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    monkeypatch.setattr(
        gnd,
        "_physical_operator_spec",
        lambda operator_id: {
            "enabled": True,
            "available": True,
            "role": "builder",
            "provider": "anthropic",
            "model": operator_id,
        },
    )
    monkeypatch.setattr(gnd, "_operator_runtime_state_for_graph", lambda _operator_id: "idle")
    monkeypatch.setattr(
        gnd,
        "_broker_env",
        lambda *_args, **_kwargs: {"SOLAR_PM_DEFAULT_PROVIDERS": "openai"},
    )

    workers = gnd._scheduler_input_bound_physical_workers(graph, graph_path)
    result = gs.enqueue_ready(graph, str(graph_path), workers, dry_run=True)

    assert result["enqueued"] == []
    assert result["queued"][0]["reason"] == "frozen_physical_plan_unsatisfiable"
    observations = result["queued"][0]["details"]["candidate_observations"]
    assert [item["operator_id"] for item in observations] == ["op.claude-1", "op.claude-2"]
    assert all(
        item["reason"].startswith("physical_operator_provider_incompatible:")
        for item in observations
    )
    assert graph["nodes"][0]["status"] == "worker_blocked"
    assert graph["node_results"]["frozen"]["blocking_reason"] == "frozen_physical_plan_unsatisfiable"
    assert graph["node_results"]["frozen"]["retryable"] is False
    assert graph["node_results"]["frozen"]["next_action"]
    repeated = gs.enqueue_ready(graph, str(graph_path), workers, dry_run=True)
    assert repeated["enqueued"] == []
    assert repeated["queued"] == []
    assert "dispatch_id" not in graph["nodes"][0]


def test_dispatcher_frozen_candidates_report_typed_unavailable_states(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)]),
    ])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    monkeypatch.setattr(
        gnd,
        "_physical_operator_spec",
        lambda _operator_id: {"enabled": True, "available": True, "role": "builder"},
    )
    monkeypatch.setattr(
        gnd,
        "_operator_runtime_state_for_graph",
        lambda operator_id: "cooldown" if operator_id == "op.primary" else "auth_expired",
    )

    workers = gnd._scheduler_input_bound_physical_workers(graph, graph_path)
    assignment = gs.assign_ready(graph, workers)

    assert assignment["assigned"] == []
    queued = assignment["queued"][0]
    assert queued["reason"] == "frozen_physical_candidates_temporarily_unavailable"
    assert queued["retryable"] is True
    assert queued["retry_after"]
    assert queued["details"]["candidate_observations"] == [
        {
            "operator_id": "op.primary",
            "rank": 1,
            "state": "UNAVAILABLE",
            "reason": "operator_runtime_cooldown",
        },
        {
            "operator_id": "op.fallback",
            "rank": 2,
            "state": "UNAVAILABLE",
            "reason": "operator_runtime_auth_expired",
        },
    ]


def test_transient_frozen_candidate_wait_is_bounded(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOLAR_FROZEN_CANDIDATE_WAIT_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("SOLAR_FROZEN_CANDIDATE_RETRY_SECONDS", "30")
    graph = _graph([_node("frozen", priority=5, candidates=[("op.primary", 1)])])
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    worker = _worker("op.primary", unavailable_reason="operator_runtime_cooldown")

    first = gs.enqueue_ready(graph, str(graph_path), [worker], dry_run=True)

    assert first["queued"][0]["retryable"] is True
    assert graph["nodes"][0]["status"] == "queued"
    assert graph["node_results"]["frozen"]["candidate_wait_attempts"] == 1
    deferred = gs.enqueue_ready(graph, str(graph_path), [worker], dry_run=True)
    assert deferred["queued"] == []
    assert graph["node_results"]["frozen"]["candidate_wait_attempts"] == 1

    graph["node_results"]["frozen"]["retry_after"] = "2000-01-01T00:00:00Z"
    graph["nodes"][0]["retry_after"] = "2000-01-01T00:00:00Z"
    exhausted = gs.enqueue_ready(graph, str(graph_path), [worker], dry_run=True)

    assert exhausted["queued"][0]["reason"] == "frozen_physical_candidate_wait_exhausted"
    assert exhausted["queued"][0]["retryable"] is False
    assert graph["nodes"][0]["status"] == "worker_blocked"
    assert graph["node_results"]["frozen"]["candidate_wait_attempts"] == 2
    assert graph["node_results"]["frozen"]["wait_classification"] == "transient_exhausted"


@pytest.mark.parametrize(
    ("returned_operator", "expected_ok"),
    [("op.fallback", True), ("op.primary", False)],
)
def test_frozen_dispatch_submits_only_scheduler_selected_operator(
    tmp_path: Path,
    monkeypatch,
    returned_operator: str,
    expected_ok: bool,
) -> None:
    graph = _graph([
        _node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)]),
    ])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text("{}\n", encoding="utf-8")
    node = graph["nodes"][0]
    captured: list[str] = []

    def fake_run(cmd, **_kwargs):
        captured.extend(cmd)
        return types.SimpleNamespace(
            returncode=0,
            stdout=f"task_id = pm-frozen\noperator_id = {returned_operator}\n",
            stderr="",
        )

    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "load_graph", lambda _path: graph)
    monkeypatch.setattr(gnd, "_verified_frozen_scheduler_projection", lambda *_args: True)
    monkeypatch.setattr(gnd, "_builder_operator_pool_enabled", lambda: False)
    monkeypatch.setattr(gnd, "_builder_operator_pool_allowed_for_pane", lambda _pane: False)
    monkeypatch.setattr(gnd.subprocess, "run", fake_run)
    payload = {
        "sprint_id": "frozen-sprint",
        "graph": str(graph_path),
        "node": node,
        "assignment": {
            "pane": "operator:op.fallback",
            "operator_id": "op.fallback",
            "candidate_rank": 2,
            "frozen_candidate": True,
            "dispatch_role": "builder",
        },
        "physical_plan_ir": {
            "plan_authority": "frozen_scheduler_input",
            "selected_operator_id": "op.fallback",
        },
        "capsule_plan_ir": {"capsule_authority": "frozen_scheduler_input"},
        "dispatch_id": "graph-frozen-sprint-frozen-test",
    }

    result = gnd.dispatch_queue_item(
        {"sprint_id": "frozen-sprint", "payload": payload},
        dry_run=True,
    )

    alternatives = [
        captured[index + 1]
        for index, value in enumerate(captured[:-1])
        if value == "--operator-alternative"
    ]
    assert result["ok"] is expected_ok
    assert alternatives == ["op.fallback"]
    assert "op.primary" not in captured
    if expected_ok:
        assert result["dispatch_mode"] == "operator_pool"
    else:
        assert result["reason"] == "frozen_operator_identity_mismatch"
        assert result["expected_operator_id"] == "op.fallback"


def test_frozen_pm_refusal_releases_exact_assignment_and_projects_parent_retryable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([_node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)])])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    node = graph["nodes"][0]
    node.update(
        {
            "status": "assigned",
            "assigned_to": "operator:op.primary",
            "dispatch_id": "graph-frozen-sprint-frozen-r9",
        }
    )
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    released: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        gnd,
        "release_lease",
        lambda pane, dispatch_id, reason: released.append((pane, dispatch_id, reason)),
    )
    gs.save_graph(graph_path, graph)

    reconciliation = gnd._reconcile_frozen_operator_submit_refusal(
        graph_path=str(graph_path),
        sid="frozen-sprint",
        node_id="frozen",
        pane="operator:op.primary",
        dispatch_id="graph-frozen-sprint-frozen-r9",
        returncode=1,
    )

    persisted = gs.load_graph(graph_path)
    persisted_node = next(item for item in persisted["nodes"] if item["id"] == "frozen")
    status = json.loads(
        (tmp_path / "frozen-sprint.status.json").read_text(encoding="utf-8")
    )
    assert reconciliation["ok"] is True
    assert reconciliation["updated"] is True
    assert reconciliation["retryable"] is True
    assert released == [
        (
            "operator:op.primary",
            "graph-frozen-sprint-frozen-r9",
            "frozen_operator_submit_refused",
        )
    ]
    assert persisted_node["status"] == "queued"
    assert "assigned_to" not in persisted_node
    assert "dispatch_id" not in persisted_node
    assert persisted["node_results"]["frozen"]["blocking_reason"] == "frozen_operator_submit_refused"
    assert persisted["node_results"]["frozen"]["last_operator_submission_failure"]["retryable"] is True
    assert status["status"] == "active"
    assert status["phase"] == "graph_in_progress"

    next_tick = gs.enqueue_ready(
        persisted,
        str(graph_path),
        [
            _worker("op.primary", unavailable_reason="provider_incompatible"),
            _worker("op.fallback"),
        ],
        dry_run=True,
    )
    assert next_tick["enqueued"][0]["node"] == "frozen"
    assert next_tick["enqueued"][0]["payload"]["assignment"]["operator_id"] == "op.fallback"


def test_stale_frozen_pm_refusal_cannot_release_newer_assignment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([_node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)])])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    graph["nodes"][0].update(
        {
            "status": "assigned",
            "assigned_to": "operator:op.fallback",
            "dispatch_id": "graph-frozen-sprint-frozen-new",
        }
    )
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    released: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        gnd,
        "release_lease",
        lambda pane, dispatch_id, reason: released.append((pane, dispatch_id, reason)),
    )
    gs.save_graph(graph_path, graph)

    reconciliation = gnd._reconcile_frozen_operator_submit_refusal(
        graph_path=str(graph_path),
        sid="frozen-sprint",
        node_id="frozen",
        pane="operator:op.primary",
        dispatch_id="graph-frozen-sprint-frozen-old",
        returncode=1,
    )

    persisted = gs.load_graph(graph_path)
    persisted_node = next(item for item in persisted["nodes"] if item["id"] == "frozen")
    assert reconciliation["updated"] is False
    assert reconciliation["reason"] == "stale_frozen_submit_refusal"
    assert persisted_node["assigned_to"] == "operator:op.fallback"
    assert persisted_node["dispatch_id"] == "graph-frozen-sprint-frozen-new"
    assert persisted_node["status"] == "assigned"
    assert released == []


def test_restart_reconciliation_consumes_exact_durable_frozen_pm_refusal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([_node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)])])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    dispatch_id = "graph-frozen-sprint-frozen-crash-window"
    graph["nodes"][0].update(
        {
            "status": "assigned",
            "assigned_to": "operator:op.primary",
            "dispatch_id": dispatch_id,
        }
    )
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    pm_dir = tmp_path / "run" / "pm-inbox"
    pm_dir.mkdir(parents=True)
    refusal_path = pm_dir / "pm-refusal.json"
    refusal_path.write_text(
        json.dumps(
            {
                "task_id": "pm-refusal",
                "sprint_id": "frozen-sprint",
                "node_id": "frozen",
                "operator_id": "",
                "selected_frozen_operator_id": "op.primary",
                "graph_dispatch_id": dispatch_id,
                "dispatch_id": "dispatch-pm-refusal",
                "attempt_id": "1",
                "correlation_id": "frozen-sprint:frozen",
                "queue_item_id": "queue-refusal",
                "requested_role": "builder",
                "status": "failed_no_dispatchable_operator",
                "exit_code": 1,
                "failed_at": "2026-08-28T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "_verified_frozen_scheduler_projection", lambda *_args: True)
    monkeypatch.setattr(gnd, "release_lease", lambda *_args, **_kwargs: True)
    gs.save_graph(graph_path, graph)
    restarted = gs.load_graph(graph_path)

    reconciled = gnd._reconcile_existing_dispatches(restarted, graph_path)

    node = next(item for item in restarted["nodes"] if item["id"] == "frozen")
    failure = restarted["node_results"]["frozen"]["last_operator_submission_failure"]
    assert any(item.get("source") == "durable_pm_submit_refusal" for item in reconciled)
    assert node["status"] == "queued"
    assert "assigned_to" not in node
    assert "dispatch_id" not in node
    assert failure["operator_id"] == "op.primary"
    assert failure["dispatch_id"] == dispatch_id
    assert failure["pm_task_id"] == "pm-refusal"
    assert failure["pm_dispatch_id"] == "dispatch-pm-refusal"
    assert failure["queue_item_id"] == "queue-refusal"
    assert failure["pm_task_json"] == str(refusal_path)


def test_restart_reconciliation_ignores_refusal_for_stale_assignment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([_node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)])])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    current_dispatch_id = "graph-frozen-sprint-frozen-new"
    graph["nodes"][0].update(
        {
            "status": "assigned",
            "assigned_to": "operator:op.fallback",
            "dispatch_id": current_dispatch_id,
        }
    )
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    pm_dir = tmp_path / "run" / "pm-inbox"
    pm_dir.mkdir(parents=True)
    (pm_dir / "pm-stale-refusal.json").write_text(
        json.dumps(
            {
                "task_id": "pm-stale-refusal",
                "sprint_id": "frozen-sprint",
                "node_id": "frozen",
                "selected_frozen_operator_id": "op.primary",
                "graph_dispatch_id": "graph-frozen-sprint-frozen-old",
                "requested_role": "builder",
                "status": "failed_no_dispatchable_operator",
                "exit_code": 1,
                "failed_at": "2026-08-28T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "_verified_frozen_scheduler_projection", lambda *_args: True)
    monkeypatch.setattr(gnd, "read_lease", lambda _pane: {"dispatch_id": current_dispatch_id, "expires_at": "2999-01-01T00:00:00Z"})
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda _pane: True)
    monkeypatch.setattr(gnd, "_pane_title", lambda _pane: "")
    monkeypatch.setattr(gnd, "_pane_tail", lambda _pane: "")
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda _pane: "")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda *_args: "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda _pane: "")
    gs.save_graph(graph_path, graph)
    restarted = gs.load_graph(graph_path)

    reconciled = gnd._reconcile_existing_dispatches(restarted, graph_path)

    node = next(item for item in restarted["nodes"] if item["id"] == "frozen")
    assert not any(item.get("source") == "durable_pm_submit_refusal" for item in reconciled)
    assert node["status"] == "assigned"
    assert node["assigned_to"] == "operator:op.fallback"
    assert node["dispatch_id"] == current_dispatch_id


def test_frozen_pm_submit_failure_invokes_exact_retryable_reconciliation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([_node("frozen", priority=5, candidates=[("op.primary", 1), ("op.fallback", 2)])])
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "0" * 64}
    node = graph["nodes"][0]
    dispatch_id = "graph-frozen-sprint-frozen-submit-failed"
    pane = "operator:op.primary"
    node.update({"status": "assigned", "assigned_to": pane, "dispatch_id": dispatch_id})
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "_builder_operator_pool_enabled", lambda: False)
    monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "release_lease", lambda *_args, **_kwargs: None)
    captured: list[str] = []

    def rejected(cmd, **_kwargs):
        captured.extend(cmd)
        return types.SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ERROR: no dispatchable authorized operator",
        )

    monkeypatch.setattr(gnd.subprocess, "run", rejected)
    gs.save_graph(graph_path, graph)
    payload = {
        "sprint_id": "frozen-sprint",
        "graph": str(graph_path),
        "node": node,
        "assignment": {
            "pane": pane,
            "operator_id": "op.primary",
            "candidate_rank": 1,
            "frozen_candidate": True,
            "dispatch_role": "builder",
        },
        "physical_plan_ir": {
            "plan_authority": "frozen_scheduler_input",
            "selected_operator_id": "op.primary",
        },
        "capsule_plan_ir": {"capsule_authority": "frozen_scheduler_input"},
        "dispatch_id": dispatch_id,
    }

    result = gnd._submit_builder_to_operator_pool(
        item={"sprint_id": "frozen-sprint", "payload": payload},
        payload=payload,
        sid="frozen-sprint",
        node=node,
        node_id="frozen",
        graph_path=str(graph_path),
        pane=pane,
        dispatch_id=dispatch_id,
        dry_run=False,
    )

    alternatives = [
        captured[index + 1]
        for index, value in enumerate(captured[:-1])
        if value == "--operator-alternative"
    ]
    persisted = gs.load_graph(graph_path)
    persisted_node = next(item for item in persisted["nodes"] if item["id"] == "frozen")
    assert alternatives == ["op.primary"]
    assert "op.fallback" not in captured
    assert result["ok"] is False
    assert result["retryable"] is True
    assert result["suppress_fallback"] is True
    assert result["reconciliation"]["updated"] is True
    assert persisted_node["status"] == "queued"
    assert "assigned_to" not in persisted_node
    assert "dispatch_id" not in persisted_node


def test_enqueue_ready_rejects_unverified_projection_before_queue_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _graph([_node("frozen", priority=5, candidates=[("op.primary", 1)])])
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        scheduler_input,
        "verify_runtime_projection",
        lambda *_args, **_kwargs: {"ok": False, "errors": ["TAMPERED"]},
    )
    queue = types.ModuleType("task_queue")
    queue.enqueue = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("queue write occurred"))
    monkeypatch.setitem(__import__("sys").modules, "task_queue", queue)

    with pytest.raises(ValueError, match="TAMPERED"):
        gs.enqueue_ready(graph, str(graph_path), [_worker("op.primary")], dry_run=False)


def _typed_prework_result(
    *,
    task_id: str = "pm-task-rank2",
    changed: bool = False,
    include_effects: bool = True,
) -> dict:
    payload = {
        "task_id": task_id,
        "operator_id": "op.rank2",
        "sprint_id": "frozen-sprint",
        "node_id": "frozen",
        "status": "failed",
        "exit_code": 1,
        "dispatch_id": "dispatch-pm-task-rank2",
        "attempt_id": "1",
        "correlation_id": "frozen-sprint:frozen",
        "graph_dispatch_id": "graph-frozen-rank2",
        "scheduler_input_sha256": "a" * 64,
        "frozen_candidate_ids": ["op.rank1", "op.rank2", "op.rank3"],
        "error": {
            "type": "provider_quota",
            "phase": "admission",
            "retryable": True,
            "retry_scope": "frozen_operator_alternative",
        },
        "failure_flow_control": {
            "runtime_state": "cooldown",
            "reason": "rate_limit",
            "expires_at": "2026-08-28T10:00:00Z",
        },
        "provider_invocation_receipt": {
            "provider_admission_refusal": True,
            "structured_stream": {
                "complete": True,
                "provider_admission_refusal": True,
                "terminal_failed": True,
                "turn_completed": False,
                "agent_message_observed": False,
                "tool_or_external_event_observed": False,
            },
            "final_assistant_message": {"present": False, "sha256": ""},
            "tool_evidence": {
                "observed": False,
                "complete": True,
                "basis": "provider_refusal_before_final_assistant_message",
            },
        },
    }
    if include_effects:
        payload["effects_receipt"] = {
            "observed": True,
            "complete": True,
            "unknown": False,
            "effects_started": changed,
            "outputs_changed": changed,
            "outputs_published": False,
            "publish_attempted": False,
            "changed_path_count": 1 if changed else 0,
        }
    return payload


def _prework_graph() -> dict:
    graph = _graph(
        [_node("frozen", priority=5, candidates=[("op.rank1", 1), ("op.rank2", 2), ("op.rank3", 3)])]
    )
    graph["scheduler_input_ref"] = {"path": "scheduler-input.json", "sha256": "a" * 64}
    node = graph["nodes"][0]
    node.update(
        {
            "effects": ["read", "write", "execute"],
            "status": "dispatched",
            "assigned_to": "operator:op.rank2",
            "dispatch_id": "graph-frozen-rank2",
            "execution_attempt": {
                "schema_version": "solar.node_attempt.v1",
                "phase": "execution",
                "sequence": 1,
                "repair_generation": 0,
                "task_id": "pm-task-rank2",
                "dispatch_id": "graph-frozen-rank2",
                "operator_id": "op.rank2",
                "source": "pm_dispatch",
                "logical_role": "builder",
                "status": "submitted",
                "requires_operator_result": True,
                "sprint_id": "frozen-sprint",
                "node_id": "frozen",
                "operator_dispatch_id": "dispatch-pm-task-rank2",
                "operator_attempt_id": "1",
                "operator_correlation_id": "frozen-sprint:frozen",
                "scheduler_input_sha256": "a" * 64,
                "frozen_candidate_ids": ["op.rank1", "op.rank2", "op.rank3"],
            },
            "pm_task_id": "pm-task-rank2",
            "operator_id": "op.rank2",
            "dispatched_via": "pm_dispatch",
        }
    )
    return graph


def _write_typed_result(tmp_path: Path, payload: dict) -> None:
    path = tmp_path / "run" / "operator-results" / "op.rank2" / str(payload["task_id"]) / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_typed_quota_before_work_requeues_rank2_for_ready_rank3(tmp_path: Path, monkeypatch) -> None:
    graph = _prework_graph()
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    _write_typed_result(tmp_path, _typed_prework_result())
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(
        gnd,
        "_scheduler_input_bound_physical_workers",
        lambda *_args: [
            _worker("op.rank1", unavailable_reason="operator_runtime_cooldown"),
            _worker("op.rank2", unavailable_reason="operator_runtime_cooldown"),
            _worker("op.rank3"),
        ],
    )
    monkeypatch.setattr(gnd, "release_lease", lambda *_args, **_kwargs: {"released": True})

    result = gnd._safe_frozen_prework_provider_fallback(
        "frozen-sprint", "frozen", graph["nodes"][0], graph, graph_path
    )

    node = graph["nodes"][0]
    assert result == {
        "handled": True,
        "reason": "frozen_provider_prework_refusal_requeued",
        "operator_id": "op.rank2",
        "next_candidate_id": "op.rank3",
        "result_json": str(
            tmp_path / "run" / "operator-results" / "op.rank2" / "pm-task-rank2" / "result.json"
        ),
    }
    assert node["status"] == "pending"
    assert "execution_attempt" not in node
    assert node.get("execution_attempt_history") in (None, [])
    assert node["pre_work_refusals"][-1]["next_candidate_id"] == "op.rank3"


@pytest.mark.parametrize("changed,include_effects", [(True, True), (False, False)])
def test_prework_fallback_requires_complete_zero_effects_receipt(
    tmp_path: Path,
    monkeypatch,
    changed: bool,
    include_effects: bool,
) -> None:
    graph = _prework_graph()
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    _write_typed_result(
        tmp_path,
        _typed_prework_result(changed=changed, include_effects=include_effects),
    )
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "_scheduler_input_bound_physical_workers", lambda *_args: [_worker("op.rank3")])

    result = gnd._safe_frozen_prework_provider_fallback(
        "frozen-sprint", "frozen", graph["nodes"][0], graph, graph_path
    )

    assert result is None
    assert graph["nodes"][0]["execution_attempt"]["task_id"] == "pm-task-rank2"


def test_prework_fallback_rejects_incomplete_structured_provider_stream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _prework_graph()
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    payload = _typed_prework_result()
    payload["provider_invocation_receipt"]["structured_stream"]["complete"] = False
    payload["provider_invocation_receipt"]["structured_stream"]["unknown_event_types"] = [
        "provider.work.maybe_started"
    ]
    _write_typed_result(tmp_path, payload)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(
        gnd,
        "_scheduler_input_bound_physical_workers",
        lambda *_args: [_worker("op.rank3")],
    )

    result = gnd._safe_frozen_prework_provider_fallback(
        "frozen-sprint", "frozen", graph["nodes"][0], graph, graph_path
    )

    assert result is None
    assert graph["nodes"][0]["execution_attempt"]["task_id"] == "pm-task-rank2"


def test_stale_typed_prework_result_cannot_clear_newer_attempt(tmp_path: Path, monkeypatch) -> None:
    graph = _prework_graph()
    graph["nodes"][0]["execution_attempt"]["task_id"] = "pm-task-newer"
    graph["nodes"][0]["pm_task_id"] = "pm-task-newer"
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    _write_typed_result(tmp_path, _typed_prework_result(task_id="pm-task-rank2"))
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)

    result = gnd._safe_frozen_prework_provider_fallback(
        "frozen-sprint", "frozen", graph["nodes"][0], graph, graph_path
    )

    assert result is None
    assert graph["nodes"][0]["execution_attempt"]["task_id"] == "pm-task-newer"


def test_all_frozen_candidates_capacity_blocked_releases_then_enters_bounded_scheduler_wait(
    tmp_path: Path,
    monkeypatch,
) -> None:
    graph = _prework_graph()
    graph_path = tmp_path / "frozen-sprint.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    _write_typed_result(tmp_path, _typed_prework_result())
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(
        gnd,
        "_scheduler_input_bound_physical_workers",
        lambda *_args: [
            _worker("op.rank1", unavailable_reason="operator_runtime_cooldown"),
            _worker("op.rank2", unavailable_reason="operator_runtime_cooldown"),
            _worker("op.rank3", unavailable_reason="operator_runtime_cooldown"),
        ],
    )
    monkeypatch.setattr(gnd, "release_lease", lambda *_args, **_kwargs: {"released": True})

    reconciled = gnd._reconcile_existing_dispatches(graph, graph_path)

    fallback = next(
        item
        for item in reconciled
        if item.get("reason") == "frozen_provider_prework_refusal_released_for_bounded_wait"
    )
    assert fallback["handled"] is True
    assert len(fallback["candidate_observations"]) == 2
    node = graph["nodes"][0]
    assert node["status"] == "pending"
    assert "execution_attempt" not in node
    assert node.get("execution_attempt_history") in (None, [])

    scheduler_result = gs.enqueue_ready(
        graph,
        str(graph_path),
        [
            _worker("op.rank1", unavailable_reason="operator_runtime_cooldown"),
            _worker("op.rank2", unavailable_reason="operator_runtime_cooldown"),
            _worker("op.rank3", unavailable_reason="operator_runtime_cooldown"),
        ],
        max_parallel=1,
        dry_run=True,
    )

    assert scheduler_result["enqueued"] == []
    assert scheduler_result["queued"][0]["retryable"] is True
    assert scheduler_result["queued"][0]["wait_classification"] == "transient"
    assert scheduler_result["queued"][0]["candidate_wait_attempts"] == 1
    runtime_result = graph["node_results"]["frozen"]
    assert runtime_result["status"] == "queued"
    assert runtime_result["pre_work_refusal"]["error"]["type"] == "provider_quota"


@pytest.mark.parametrize(
    "graph",
    [
        {
            "schema_version": "solar.scheduler_runtime_projection.v1",
            "planning_authority": "frozen_execution_plan_v1",
            "nodes": [],
        },
        {"planning_authority": "frozen_execution_plan_v1", "nodes": []},
    ],
)
def test_dispatcher_does_not_auto_enrich_frozen_planner_graph(graph, monkeypatch) -> None:
    def forbidden_enrichment(*_args, **_kwargs):
        raise AssertionError("dispatcher rewrote frozen planner output")

    monkeypatch.setattr(gnd, "auto_enrich_graph", forbidden_enrichment)

    assert gnd._enrich_dispatch_graph_if_mutable(graph, "frozen.task_graph.json") is graph


def test_non_frozen_assign_ready_preserves_legacy_relaxed_matching(monkeypatch) -> None:
    graph = {
        "sprint_id": "legacy",
        "nodes": [{
            "id": "legacy-node",
            "depends_on": [],
            "required_skills": ["skill.implementation"],
            "required_capabilities": ["code_impl"],
            "effect_union": {},
            "proof_obligations": [],
            "write_scope": ["/tmp/legacy"],
        }],
    }
    enrichment_calls: list[bool] = []

    def legacy_enrichment(value, **_kwargs):
        enrichment_calls.append(True)
        return value

    monkeypatch.setattr(gs, "auto_enrich_graph", legacy_enrichment)
    result = gs.assign_ready(
        graph,
        [{
            "pane": "legacy-pane",
            "role": "builder",
            "skills": [],
            "capabilities": ["code_impl"],
            "busy": False,
        }],
    )

    assert enrichment_calls == [True]
    assert result["assigned"][0]["node"] == "legacy-node"
    assert result["assigned"][0]["skills_relaxed"] is True
    assert result["capability_enrichment"]["auto"] is True
