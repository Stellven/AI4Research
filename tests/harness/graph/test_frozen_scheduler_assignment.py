"""Frozen SchedulerInput authority on the legacy graph-scheduler bridge."""

from __future__ import annotations

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


def test_enqueue_ready_keeps_unavailable_frozen_node_queued_not_worker_blocked(tmp_path: Path) -> None:
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
    assert result["queued"][0]["reason"] == "frozen_physical_candidates_unavailable"
    assert result["worker_blocked"] == []
    assert graph["nodes"][0]["status"] == "queued"
    assert graph["node_results"]["frozen"]["blocking_reason"] == "frozen_physical_candidates_unavailable"


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
