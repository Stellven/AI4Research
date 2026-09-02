"""Contract tests for frozen SchedulerInput -> mutable scheduler runtime."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import types
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness" / "lib"))

import graph_scheduler
import graph_node_dispatcher
import multi_task_runner
import operator_runtime
import scheduler_input
import workspace_binding


def _node(node_id: str, *, depends_on: list[str] | None = None, consumes: list[str] | None = None,
          produces: list[str] | None = None, priority: int = 10) -> dict:
    return {
        "id": node_id,
        "goal": f"Complete {node_id}",
        "logical_operator": "ResearchWorker",
        "dispatch_task_type": "research",
        "depends_on": depends_on or [],
        "requirement_ids": [f"REQ-{node_id}"],
        "capability_capsule_id": "cap.research-source-validation",
        "capsule_binding": {
            "capsule_ids": ["cap.research-source-validation"],
            "composition_id": None,
            "contract_sha256": "1" * 64,
        },
        "physical_candidates": [
            {"operator_id": "operator-primary", "rank": 1, "admission_state": "ELIGIBLE"},
            {"operator_id": "operator-fallback", "rank": 2, "admission_state": "ELIGIBLE"},
        ],
        "artifact_contract": {
            "consumes": consumes or ["artifact.request.v1"],
            "produces": produces or [f"artifact.{node_id}.v1"],
        },
        "output_routes": [
            {
                "artifact_type": artifact_type,
                "route_kind": "sprint_private",
                "relative_path": f"{node_id}/{index}.json",
                "materialization_kind": "file",
            }
            for index, artifact_type in enumerate(
                produces or [f"artifact.{node_id}.v1"], start=1
            )
        ],
        "workspace_reads": [],
        "evaluation_binding": {
            "deterministic_gate_ids": ["gate.schema.v1"],
            "semantic_evaluator_ids": ["evaluator.fidelity.v1"],
        },
        "resource_requirements": {
            "cpu_cores_min": 1,
            "memory_mb_min": 128,
            "gpu_required": False,
            "network": "optional",
        },
        "effects": ["read", "write"],
        "priority": priority,
        "failure_policy": {"max_attempts": 2, "on_exhausted": "block_dependents"},
    }


def _scheduler_input() -> dict:
    first = _node("collect", produces=["artifact.evidence.v1"], priority=20)
    second = _node(
        "synthesize",
        depends_on=["collect"],
        consumes=["artifact.evidence.v1"],
        produces=["artifact.report.v1"],
    )
    return {
        "schema_version": "solar.scheduler_input.v1",
        "artifact_role": "runtime_execution_authority",
        "scheduler_input_id": "scheduler-input-test",
        "sprint_id": "sprint-test",
        "planning_authority": "frozen_execution_plan_v1",
        "graph": {"graph_id": "graph-test", "nodes": [first, second]},
    }


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _attach_workspace_authority(
    tmp_path: Path,
    value: dict,
    *,
    workspace: Path | None = None,
) -> tuple[Path, Path]:
    workspace = workspace or (tmp_path / "workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    authority_path = tmp_path / f"{value['sprint_id']}.workspace_authority.json"
    authority = {
        "schema_version": "solar.workspace_authority.v1",
        "artifact_role": "controller_frozen_authority",
        "authority_id": f"workspace-authority-{value['sprint_id']}",
        "path": str(authority_path.resolve()),
        "sprint_id": value["sprint_id"],
        "workspace_root": str(workspace.resolve()),
    }
    canonical_inputs = {
        name: tmp_path / f"{value['sprint_id']}.{name}.json"
        for name in ("raw_intent", "intent_ir", "requirement_ir")
    }
    if all(path.is_file() for path in canonical_inputs.values()):
        authority["cwd"] = {
            "captured": str(workspace.resolve()),
            "effective_relative": ".",
            "normalized_to_workspace": False,
        }
        authority["inputs"] = {
            name: {
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in canonical_inputs.items()
        }
    _write(authority_path, authority)
    value["workspace_authority_ref"] = {
        "authority_id": authority["authority_id"],
        "path": str(authority_path.resolve()),
        "sha256": scheduler_input.file_sha256(authority_path),
        "workspace_root": str(workspace.resolve()),
    }
    return workspace, authority_path


def test_deterministic_validation_rejects_cross_field_defects() -> None:
    value = _scheduler_input()
    value["graph"]["nodes"][1]["physical_candidates"][1]["rank"] = 1
    value["graph"]["nodes"][1]["depends_on"] = []
    value["graph"]["nodes"][0]["status"] = "pending"

    result = scheduler_input.validate(value, require_runtime_authority=True)

    assert result["ok"] is False
    assert "DUPLICATE_CANDIDATE_RANK:synthesize" in result["errors"]
    assert "MUTABLE_FIELD_IN_FROZEN_NODE:collect:status" in result["errors"]
    assert "ARTIFACT_PRODUCER_NOT_ANCESTOR:synthesize:artifact.evidence.v1:collect" in result["errors"]


def test_primary_capsule_must_be_in_frozen_capsule_binding() -> None:
    value = _scheduler_input()
    value["graph"]["nodes"][0]["capability_capsule_id"] = "cap.not-in-binding"

    result = scheduler_input.validate(value, require_runtime_authority=True)

    assert result["ok"] is False
    assert (
        "PRIMARY_CAPSULE_NOT_IN_BINDING:collect:cap.not-in-binding"
        in result["errors"]
    )


def test_workspace_routes_reject_traversal_and_duplicate_public_destination(
    tmp_path: Path,
) -> None:
    value = _scheduler_input()
    _attach_workspace_authority(tmp_path, value)
    value["graph"]["nodes"][0]["output_routes"][0].update(
        {"route_kind": "workspace_publish", "relative_path": "../escape.md"}
    )
    traversal = scheduler_input.validate(value, require_runtime_authority=True)
    assert any("OUTPUT_ROUTE_PATH_INVALID:collect" in row for row in traversal["errors"])

    value = _scheduler_input()
    _attach_workspace_authority(tmp_path / "duplicate", value)
    for node in value["graph"]["nodes"]:
        node["output_routes"][0].update(
            {"route_kind": "workspace_publish", "relative_path": "RESULT.md"}
        )
    duplicate = scheduler_input.validate(value, require_runtime_authority=True)
    assert "WORKSPACE_OUTPUT_PATH_CONFLICT:RESULT.md:collect:synthesize" in duplicate["errors"]


def test_duplicate_private_artifact_types_are_node_scoped(tmp_path: Path) -> None:
    value = _scheduler_input()
    second = value["graph"]["nodes"][1]
    second["depends_on"] = []
    second["artifact_contract"]["consumes"] = ["artifact.request.v1"]
    for node in value["graph"]["nodes"]:
        node["artifact_contract"]["produces"] = ["artifact.shared.v1"]
        node["output_routes"] = [
            {
                "artifact_type": "artifact.shared.v1",
                "route_kind": "sprint_private",
                "relative_path": "result.json",
                "materialization_kind": "file",
            }
        ]
    source = tmp_path / "scheduler_input.json"
    _write(source, value)

    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    paths = [
        node["artifact_routes"]["produces"]["artifact.shared.v1"]
        for node in graph["nodes"]
    ]
    assert paths[0] != paths[1]
    assert all("/private/" in path.replace("\\", "/") for path in paths)


def test_ordered_composition_collection_outputs_share_explicit_private_scope(
    tmp_path: Path,
) -> None:
    artifact_type = "artifact.paper.v1"
    remote = _node("remote", consumes=["artifact.request.v1"], produces=[artifact_type])
    local = _node(
        "local",
        depends_on=["remote"],
        consumes=["artifact.request.v1"],
        produces=[artifact_type],
    )
    assess = _node(
        "assess",
        depends_on=["remote", "local"],
        consumes=[artifact_type],
        produces=["artifact.assessment.v1"],
    )
    for node in (remote, local):
        node["output_routes"] = [
            {
                "artifact_type": artifact_type,
                "route_kind": "sprint_private",
                "relative_path": "evidence/research_papers",
                "materialization_kind": "directory",
                "private_scope": "source_ingestion_assessment",
            }
        ]
    value = {
        "schema_version": "solar.scheduler_input.v1",
        "artifact_role": "runtime_execution_authority",
        "scheduler_input_id": "scheduler-input-collection",
        "sprint_id": "sprint-collection",
        "planning_authority": "frozen_execution_plan_v1",
        "graph": {"graph_id": "graph-collection", "nodes": [remote, local, assess]},
    }
    source = tmp_path / "scheduler_input.json"
    _write(source, value)

    assert scheduler_input.validate(value, require_runtime_authority=True)["ok"] is True
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    nodes = {node["id"]: node for node in graph["nodes"]}
    remote_path = nodes["remote"]["artifact_routes"]["produces"][artifact_type]
    local_path = nodes["local"]["artifact_routes"]["produces"][artifact_type]
    assert remote_path == local_path
    assert nodes["assess"]["artifact_routes"]["consumes"][artifact_type] == local_path


def test_private_scope_is_forbidden_on_workspace_publish_route(tmp_path: Path) -> None:
    value = _scheduler_input()
    _attach_workspace_authority(tmp_path, value)
    value["graph"]["nodes"][0]["output_routes"][0].update(
        {
            "route_kind": "workspace_publish",
            "relative_path": "RESULT.md",
            "private_scope": "not-applicable",
        }
    )

    result = scheduler_input.validate(value, require_runtime_authority=True)

    assert "PRIVATE_SCOPE_ON_WORKSPACE_ROUTE:collect:RESULT.md" in result["errors"]


def test_workspace_exact_file_read_is_hash_bound_and_source_immutable(
    tmp_path: Path,
) -> None:
    value = _scheduler_input()
    workspace, _authority = _attach_workspace_authority(tmp_path, value)
    source_file = workspace / "README.md"
    source_file.write_text("protected input\n", encoding="utf-8")
    before = source_file.read_bytes()
    value["graph"]["nodes"][0]["workspace_reads"] = [
        {
            "kind": "file",
            "relative_path": "README.md",
            "sha256": scheduler_input.file_sha256(source_file),
        }
    ]
    value["graph"]["nodes"][0]["output_routes"][0].update(
        {"route_kind": "workspace_publish", "relative_path": "RESULT.md"}
    )
    source = tmp_path / "scheduler_input.json"
    _write(source, value)

    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    first = graph["nodes"][0]
    assert str(source_file.resolve()) in first["read_scope"]
    assert first["write_scope"][0].replace("\\", "/").endswith(
        "/workdir/workspace/RESULT.md"
    )
    assert source_file.read_bytes() == before

    source_file.write_text("tampered\n", encoding="utf-8")
    verification = scheduler_input.verify_runtime_projection(graph, graph_path=graph_path)
    assert verification == {
        "ok": False,
        "errors": ["WORKSPACE_READ_HASH_MISMATCH:README.md"],
    }


def test_workspace_read_rejects_symlink_and_forged_authority(tmp_path: Path) -> None:
    value = _scheduler_input()
    workspace, authority_path = _attach_workspace_authority(tmp_path, value)
    target = workspace / "actual.md"
    target.write_text("source\n", encoding="utf-8")
    linked = workspace / "README.md"
    try:
        linked.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    value["graph"]["nodes"][0]["workspace_reads"] = [
        {
            "kind": "file",
            "relative_path": "README.md",
            "sha256": scheduler_input.file_sha256(target),
        }
    ]
    source = tmp_path / "scheduler_input.json"
    _write(source, value)
    with pytest.raises(scheduler_input.SchedulerInputError, match="WORKSPACE_READ_SYMLINK"):
        scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")

    value = _scheduler_input()
    _workspace, authority_path = _attach_workspace_authority(tmp_path / "forged", value)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["sprint_id"] = "foreign-sprint"
    _write(authority_path, authority)
    value["workspace_authority_ref"]["sha256"] = scheduler_input.file_sha256(authority_path)
    forged = tmp_path / "forged" / "scheduler_input.json"
    _write(forged, value)
    with pytest.raises(
        scheduler_input.SchedulerInputError,
        match="WORKSPACE_AUTHORITY_REFERENCE_TAMPERED",
    ):
        scheduler_input.prepare_runtime_graph(forged, tmp_path / "forged" / "runtime")


def test_workspace_io_requires_authority_and_directory_reads_are_refused(
    tmp_path: Path,
) -> None:
    value = _scheduler_input()
    value["graph"]["nodes"][0]["output_routes"][0].update(
        {"route_kind": "workspace_publish", "relative_path": "RESULT.md"}
    )
    missing = scheduler_input.validate(value, require_runtime_authority=True)
    assert "WORKSPACE_AUTHORITY_REQUIRED" in missing["errors"]

    _workspace, _authority_path = _attach_workspace_authority(tmp_path, value)
    value["graph"]["nodes"][0]["workspace_reads"] = [
        {"kind": "directory", "relative_path": "docs", "sha256": "0" * 64}
    ]
    unsupported = scheduler_input.validate(value, require_runtime_authority=True)
    assert "WORKSPACE_DIRECTORY_READ_UNSUPPORTED:collect:docs" in unsupported["errors"]

    value["graph"]["nodes"][0]["workspace_reads"] = []
    value["workspace_authority_ref"]["sha256"] = "f" * 64
    source = tmp_path / "scheduler_input.json"
    _write(source, value)
    with pytest.raises(
        scheduler_input.SchedulerInputError,
        match="WORKSPACE_AUTHORITY_SOURCE_HASH_MISMATCH",
    ):
        scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")


def test_runtime_projection_uses_primary_capsule_not_binding_order() -> None:
    node = _node("collect")
    node["capsule_binding"]["capsule_ids"] = [
        "guard.secret-leak-guard",
        "cap.research-source-validation",
    ]

    projected = scheduler_input._runtime_node(node)

    assert projected["capability_capsule_id"] == "cap.research-source-validation"
    assert projected["required_capabilities"] == [
        "guard.secret-leak-guard",
        "cap.research-source-validation",
    ]


def test_projection_keeps_source_immutable_and_state_separate(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    value = _scheduler_input()
    _write(source, value)
    before = source.read_bytes()

    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    state_path = graph_path.parent / "sprint-test.task_graph_state.json"

    assert source.read_bytes() == before
    assert state_path.is_file()
    assert not (graph_path.parent / "sprint-test.task_dag.state.json").exists()
    assert [node["id"] for node in graph_scheduler.ready_nodes(graph)] == ["collect"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["artifact_role"] == "mutable_execution_ledger"
    assert state["ready_nodes"] == ["collect"]
    assert state["nodes"]["synthesize"]["blocked_by"] == ["collect"]
    assert scheduler_input.verify_runtime_projection(graph)["ok"] is True

    graph_scheduler.set_node_status(graph, "collect", "dispatched", dispatch_id="dispatch-1")
    graph["nodes"][0]["execution_attempt"] = {"sequence": 1, "task_id": "dispatch-1"}
    graph["nodes"][0].update({
        "blocking_reason": "frozen_physical_candidates_temporarily_unavailable",
        "candidate_wait_attempts": 1,
        "dispatch_failure_streak": 2,
        "dispatch_retry_reason": "frozen_operator_submit_refused",
        "evaluation_plan_requested": {"review_mode": "single"},
        "evaluation_plan_runtime": {
            "review_mode": "single",
            "required_evaluators": 1,
        },
        "evaluation_plan_updated_at": "2026-08-28T11:59:59Z",
        "eval_artifact_snapshot": {
            "schema": "solar.eval_artifact_snapshot.v1",
            "path": str(graph_path.parent / "sprint-test.collect-eval-snapshot.json"),
            "snapshot_digest": "a" * 64,
        },
        "eval_assignments": [
            {
                "pane": "operator:evaluator-1",
                "dispatch_id": "graph-eval-sprint-test-collect-q1",
                "pm_task_id": "pm-eval-1",
                "role": "primary",
                "eval_md_path": str(graph_path.parent / "sprint-test.collect-eval.md"),
                "eval_json_path": str(graph_path.parent / "sprint-test.collect-eval.json"),
                "dispatched_at": "2026-08-28T12:00:01Z",
            }
        ],
        "eval_assigned_to": "operator:evaluator-1",
        "eval_dispatch_id": "graph-eval-sprint-test-collect-q1",
        "eval_pm_task_id": "pm-eval-1",
        "eval_dispatched_at": "2026-08-28T12:00:01Z",
        "eval_dispatch_group_id": "eval-group-1",
        "last_operator_submission_failure": {"graph_dispatch_id": "dispatch-1"},
        "last_dispatch_failure_reason": "stale_submit_ack_without_live_lease",
        "last_dispatch_failure_at": "2026-08-28T11:59:58Z",
        "next_action": "Wait for a frozen candidate to become ready.",
        "retry_after": "2026-08-28T12:00:00Z",
        "retryable": True,
        "wait_classification": "transient",
    })
    graph_scheduler.save_graph(graph_path, graph)
    assert source.read_bytes() == before
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated["nodes"]["collect"]["status"] == "dispatched"
    assert updated["nodes"]["collect"]["attempt"] == 1
    assert updated["revision"] == 1
    reloaded = graph_scheduler.load_graph(graph_path)
    assert reloaded["nodes"][0]["execution_attempt"]["task_id"] == "dispatch-1"
    assert reloaded["nodes"][0]["candidate_wait_attempts"] == 1
    assert reloaded["nodes"][0]["dispatch_failure_streak"] == 2
    assert reloaded["nodes"][0]["last_dispatch_failure_reason"] == "stale_submit_ack_without_live_lease"
    assert reloaded["nodes"][0]["last_dispatch_failure_at"] == "2026-08-28T11:59:58Z"
    assert reloaded["nodes"][0]["evaluation_plan_runtime"]["required_evaluators"] == 1
    assert reloaded["nodes"][0]["evaluation_plan_updated_at"] == "2026-08-28T11:59:59Z"
    assert reloaded["nodes"][0]["eval_assignments"][0]["pm_task_id"] == "pm-eval-1"
    assert reloaded["nodes"][0]["eval_assigned_to"] == "operator:evaluator-1"
    assert reloaded["nodes"][0]["eval_dispatch_id"] == "graph-eval-sprint-test-collect-q1"
    assert reloaded["nodes"][0]["eval_pm_task_id"] == "pm-eval-1"
    assert reloaded["nodes"][0]["eval_dispatched_at"] == "2026-08-28T12:00:01Z"
    assert reloaded["nodes"][0]["eval_dispatch_group_id"] == "eval-group-1"
    assert reloaded["nodes"][0]["last_operator_submission_failure"]["graph_dispatch_id"] == "dispatch-1"
    assert scheduler_input.verify_runtime_projection(reloaded, graph_path=graph_path)["ok"] is True
    static_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "execution_attempt" not in static_graph["nodes"][0]
    assert "evaluation_plan_runtime" not in static_graph["nodes"][0]


def test_runtime_projection_save_preserves_frozen_retrieval_and_execution_authority() -> None:
    graph = {
        "schema_version": "solar.scheduler_runtime_projection.v1",
        "nodes": [
            {
                "id": "discover",
                "goal": "Discover traceable literature.",
                "retrieval_contract": {
                    "contract_id": "discovery-v1",
                    "minimum_candidates": 6,
                },
                "execution_authority": {
                    "schema_version": "solar.node_execution_authority.v1",
                    "sha256": "a" * 64,
                },
                "status": "pending",
            }
        ],
    }

    static_graph = graph_scheduler._graph_spec_payload(graph)

    assert static_graph["nodes"][0]["retrieval_contract"] == {
        "contract_id": "discovery-v1",
        "minimum_candidates": 6,
    }
    assert static_graph["nodes"][0]["execution_authority"] == {
        "schema_version": "solar.node_execution_authority.v1",
        "sha256": "a" * 64,
    }
    assert "status" not in static_graph["nodes"][0]


def test_prepare_runtime_graph_resumes_without_resetting_existing_state(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_dir = tmp_path / "runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_dir)
    graph = graph_scheduler.load_graph(graph_path)
    graph_scheduler.set_node_status(graph, "collect", "passed")
    graph_scheduler.save_graph(graph_path, graph)
    state_path = runtime_dir / "sprint-test.task_graph_state.json"
    graph_before = graph_path.read_bytes()
    state_before = state_path.read_bytes()

    resumed_path = scheduler_input.prepare_runtime_graph(source, runtime_dir)

    assert resumed_path == graph_path
    assert graph_path.read_bytes() == graph_before
    assert state_path.read_bytes() == state_before
    resumed = graph_scheduler.load_graph(resumed_path)
    assert graph_scheduler.node_status(resumed, "collect") == "passed"


def test_prepare_runtime_graph_rejects_conflicting_input_without_overwrite(tmp_path: Path) -> None:
    first_source = tmp_path / "first.scheduler_input.json"
    second_source = tmp_path / "second.scheduler_input.json"
    first = _scheduler_input()
    second = deepcopy(first)
    second["graph"]["nodes"][0]["goal"] = "A conflicting frozen goal"
    _write(first_source, first)
    _write(second_source, second)
    runtime_dir = tmp_path / "runtime"
    graph_path = scheduler_input.prepare_runtime_graph(first_source, runtime_dir)
    state_path = runtime_dir / "sprint-test.task_graph_state.json"
    graph_before = graph_path.read_bytes()
    state_before = state_path.read_bytes()

    with pytest.raises(scheduler_input.SchedulerInputError, match="SCHEDULER_RUNTIME_INPUT_CONFLICT"):
        scheduler_input.prepare_runtime_graph(second_source, runtime_dir)

    assert graph_path.read_bytes() == graph_before
    assert state_path.read_bytes() == state_before


@pytest.mark.parametrize("missing_name", ["graph", "state"])
def test_prepare_runtime_graph_recovers_exact_incomplete_runtime_pair(
    tmp_path: Path,
    missing_name: str,
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_dir = tmp_path / "runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_dir)
    state_path = runtime_dir / "sprint-test.task_graph_state.json"
    if missing_name == "graph":
        graph = graph_scheduler.load_graph(graph_path)
        graph_scheduler.set_node_status(graph, "collect", "passed")
        graph_scheduler.save_graph(graph_path, graph)
    missing_path = graph_path if missing_name == "graph" else state_path
    missing_path.unlink()
    surviving_path = state_path if missing_name == "graph" else graph_path
    survivor_before = surviving_path.read_bytes()

    resumed = scheduler_input.prepare_runtime_graph(source, runtime_dir)

    assert resumed == graph_path
    assert missing_path.is_file()
    assert surviving_path.read_bytes() == survivor_before
    assert scheduler_input.verify_runtime_pair(graph_path)["ok"] is True
    if missing_name == "graph":
        recovered = graph_scheduler.load_graph(graph_path)
        assert graph_scheduler.node_status(recovered, "collect") == "passed"


def test_prepare_runtime_graph_rejects_tampered_graph_only_half(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_dir = tmp_path / "runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_dir)
    state_path = runtime_dir / "sprint-test.task_graph_state.json"
    state_path.unlink()
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["scheduler_input_ref"]["sha256"] = "0" * 64
    _write(graph_path, graph)
    graph_before = graph_path.read_bytes()

    with pytest.raises(
        scheduler_input.SchedulerInputError,
        match="SCHEDULER_RUNTIME_PROJECTION_INVALID",
    ):
        scheduler_input.prepare_runtime_graph(source, runtime_dir)

    assert graph_path.read_bytes() == graph_before
    assert not state_path.exists()


def test_prepare_runtime_graph_rejects_tampered_state_only_half(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_dir = tmp_path / "runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_dir)
    state_path = runtime_dir / "sprint-test.task_graph_state.json"
    graph_path.unlink()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["scheduler_input_ref"]["sha256"] = "0" * 64
    _write(state_path, state)
    state_before = state_path.read_bytes()

    with pytest.raises(
        scheduler_input.SchedulerInputError,
        match="SCHEDULER_RUNTIME_STATE_INVALID",
    ):
        scheduler_input.prepare_runtime_graph(source, runtime_dir)

    assert state_path.read_bytes() == state_before
    assert not graph_path.exists()


def test_prepare_runtime_graph_rejects_tampered_state_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_dir = tmp_path / "runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_dir)
    state_path = runtime_dir / "sprint-test.task_graph_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["scheduler_input_ref"]["sha256"] = "0" * 64
    _write(state_path, state)
    graph_before = graph_path.read_bytes()
    state_before = state_path.read_bytes()

    with pytest.raises(scheduler_input.SchedulerInputError, match="SCHEDULER_RUNTIME_STATE_INVALID"):
        scheduler_input.prepare_runtime_graph(source, runtime_dir)

    assert graph_path.read_bytes() == graph_before
    assert state_path.read_bytes() == state_before


def test_projection_verifier_rejects_root_and_extra_node_authority_drift(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    original = json.loads(graph_path.read_text(encoding="utf-8"))

    planning_drift = deepcopy(original)
    planning_drift["planning_authority"] = "legacy_mutable_plan"
    assert scheduler_input.verify_runtime_projection(planning_drift)["errors"] == [
        "SCHEDULER_RUNTIME_ROOT_TAMPERED"
    ]

    contract_drift = deepcopy(original)
    contract_drift["run_contract_ref"]["sha256"] = "0" * 64
    assert scheduler_input.verify_runtime_projection(contract_drift)["errors"] == [
        "RUN_CONTRACT_REFERENCE_TAMPERED"
    ]

    node_drift = deepcopy(original)
    node_drift["nodes"][0]["preferred_profile"] = "legacy-recovery-profile"
    assert scheduler_input.verify_runtime_projection(node_drift)["errors"] == [
        "SCHEDULER_RUNTIME_PROJECTION_TAMPERED"
    ]

    state_drift = deepcopy(original)
    state_drift["runtime_state_filename"] = "other-sprint.task_graph_state.json"
    assert scheduler_input.verify_runtime_projection(state_drift)["errors"] == [
        "SCHEDULER_RUNTIME_ROOT_TAMPERED"
    ]

    extra_root = deepcopy(original)
    extra_root["legacy_runtime_authority"] = {"enabled": True}
    assert scheduler_input.verify_runtime_projection(extra_root)["errors"] == [
        "SCHEDULER_RUNTIME_ROOT_FIELDS_TAMPERED"
    ]


def test_projection_state_overlay_drops_unallowlisted_legacy_routing_keys(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    state_path = graph_path.parent / graph["runtime_state_filename"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["node_results"]["collect"].update({
        "status": "pending",
        "execution_attempt": {"sequence": 1, "task_id": "dispatch-1"},
        "scheduler_candidate_observations": [
            {"operator_id": "operator-primary", "state": "UNAVAILABLE", "rank": 1},
            {"operator_id": "operator-fallback", "state": "READY", "rank": 2},
        ],
        "preferred_profile": "legacy-recovery-profile",
        "quota_failure_reason": "force-generic-fallback",
    })
    _write(state_path, state)

    loaded = graph_scheduler.load_graph(graph_path)

    assert loaded["nodes"][0]["execution_attempt"]["task_id"] == "dispatch-1"
    assert loaded["nodes"][0]["scheduler_candidate_observations"][1]["state"] == "READY"
    assert "preferred_profile" not in loaded["nodes"][0]
    assert "quota_failure_reason" not in loaded["nodes"][0]


def test_verified_runtime_projection_does_not_inherit_mutable_active_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, workspace / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    Path(graph["runtime_work_dir"]).mkdir(parents=True)

    assert graph_node_dispatcher._scheduler_projection_workspace(graph, workspace) is None


def test_runtime_projection_cannot_bind_foreign_active_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    source = workspace / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, workspace / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    Path(graph["runtime_work_dir"]).mkdir(parents=True)

    assert graph_node_dispatcher._scheduler_projection_workspace(graph, foreign) is None


def test_resource_sidecar_uses_verified_runtime_projection_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_dir = workspace / "runtime"
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_dir)
    graph = graph_scheduler.load_graph(graph_path)
    Path(graph["runtime_work_dir"]).mkdir(parents=True)
    node = graph["nodes"][0]
    sid = graph["sprint_id"]
    (runtime_dir / f"{sid}.{node['id']}-handoff.md").write_text(
        "# Handoff\nNo sensitive values.\n",
        encoding="utf-8",
    )

    binding = types.SimpleNamespace(
        read_active_workspace=lambda _harness: workspace.resolve(),
        sprint_workspace_root=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", runtime_dir)
    monkeypatch.setattr(graph_node_dispatcher, "_workspace_binding", binding)

    graph_node_dispatcher._emit_guard_resource_sidecars(sid, node, graph)

    sidecar = json.loads(
        (runtime_dir / f"{sid}.{node['id']}-resource_binding.json").read_text(encoding="utf-8")
    )
    assert sidecar["workspace_root"] == graph["runtime_work_dir"]
    assert sidecar["staging_root"] == graph["runtime_work_dir"]
    assert sidecar["runtime_graph_path"] == str(graph_path.resolve())
    assert sidecar["bound"] is True
    assert sidecar["in_scope"] is True


def test_resource_binding_from_different_runtime_root_is_not_accepted(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    first_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime-a")
    second_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime-b")
    first = graph_scheduler.load_graph(first_path)
    second = graph_scheduler.load_graph(second_path)
    Path(first["runtime_work_dir"]).mkdir(parents=True)
    Path(second["runtime_work_dir"]).mkdir(parents=True)
    node = first["nodes"][0]
    sid = first["sprint_id"]

    graph_node_dispatcher._emit_guard_resource_sidecars(sid, node, first)
    foreign_sidecar = first_path.parent / f"{sid}.{node['id']}-resource_binding.json"
    local_sidecar = second_path.parent / f"{sid}.{node['id']}-resource_binding.json"
    local_sidecar.write_bytes(foreign_sidecar.read_bytes())

    presence = graph_node_dispatcher._proof_artifact_presence(
        sid,
        second["nodes"][0],
        graph=second,
    )

    assert presence["resource_binding"] is False


def test_projection_does_not_fall_back_to_legacy_same_sprint_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(runtime_path)
    Path(graph["runtime_work_dir"]).mkdir(parents=True)
    node = graph["nodes"][0]
    sid = graph["sprint_id"]

    legacy_root = tmp_path / "legacy-sprints"
    legacy_root.mkdir()
    legacy_resource = legacy_root / f"{sid}.{node['id']}-resource_binding.json"
    _write(
        legacy_resource,
        {
            "node_id": node["id"],
            "workspace_root": str(legacy_root),
            "staging_root": str(legacy_root / sid / "workdir"),
            "bound": True,
            "in_scope": True,
        },
    )
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", legacy_root)

    presence = graph_node_dispatcher._proof_artifact_presence(sid, node, graph=graph)

    assert presence["resource_binding"] is False


def test_unverified_projection_does_not_use_legacy_resource_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    node = graph["nodes"][0]
    sid = graph["sprint_id"]
    graph["planning_authority"] = "tampered"

    legacy_root = tmp_path / "legacy-sprints"
    legacy_root.mkdir()
    _write(
        legacy_root / f"{sid}.{node['id']}-resource_binding.json",
        {
            "node_id": node["id"],
            "workspace_root": str(legacy_root),
            "staging_root": str(legacy_root / sid / "workdir"),
            "bound": True,
            "in_scope": True,
        },
    )
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", legacy_root)

    presence = graph_node_dispatcher._proof_artifact_presence(sid, node, graph=graph)

    assert presence["guard_decision"] is False
    assert presence["resource_binding"] is False


def test_runtime_projection_clears_stale_worker_block_and_live_claim(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    state_path = graph_path.parent / "sprint-test.task_graph_state.json"

    graph = graph_scheduler.load_graph(graph_path)
    node = graph["nodes"][0]
    node.update(
        {
            "status": "worker_blocked",
            "blocking_reason": "no_matching_worker",
            "worker_match_details": {"any_worker_seen": False},
            "assigned_to": "operator:old-worker",
            "dispatch_id": "dispatch-old",
        }
    )
    graph["node_results"]["collect"] = {
        key: deepcopy(value)
        for key, value in node.items()
        if key in {
            "status",
            "blocking_reason",
            "worker_match_details",
            "assigned_to",
            "dispatch_id",
        }
    }
    graph_scheduler.save_graph(graph_path, graph)
    blocked_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert blocked_state["node_results"]["collect"]["blocking_reason"] == "no_matching_worker"

    # Reproduce the dispatcher transition that changes status in place while
    # the loaded projection still contains the old routing fields.
    graph = graph_scheduler.load_graph(graph_path)
    graph["nodes"][0]["status"] = "reviewing"
    graph["node_results"]["collect"]["status"] = "reviewing"
    graph_scheduler.save_graph(graph_path, graph)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    result = state["node_results"]["collect"]
    assert result["status"] == "reviewing"
    assert "blocking_reason" not in result
    assert "worker_match_details" not in result
    assert "queued_pane" not in result
    assert "assigned_to" not in result
    assert "dispatch_id" not in result
    assert state["leases"] == {}
    assert state["dispatch_ids"] == {}


def test_source_or_projection_tampering_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    value = _scheduler_input()
    _write(source, value)
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)

    graph["nodes"][0]["goal"] = "redesigned at runtime"
    assert scheduler_input.verify_runtime_projection(graph)["errors"] == [
        "SCHEDULER_RUNTIME_PROJECTION_TAMPERED"
    ]

    _write(source, {**value, "scheduler_input_id": "changed"})
    graph = graph_scheduler.load_graph(graph_path)
    assert scheduler_input.verify_runtime_projection(graph)["errors"] == [
        "SCHEDULER_INPUT_SOURCE_HASH_MISMATCH"
    ]


def test_ranked_candidate_fallback_never_escapes_frozen_list(monkeypatch: pytest.MonkeyPatch) -> None:
    node = _node("collect")
    registry = {
        "operator-primary": {"operator_id": "operator-primary", "backend": "command"},
        "operator-fallback": {"operator_id": "operator-fallback", "backend": "command"},
        "operator-unlisted": {"operator_id": "operator-unlisted", "backend": "command"},
    }
    monkeypatch.setattr(multi_task_runner, "resolve_operator", lambda operator_id: deepcopy(registry.get(operator_id, {})))
    monkeypatch.setattr(
        multi_task_runner,
        "operator_dispatchable",
        lambda operator: (False, "leased") if operator.get("operator_id") == "operator-primary" else (True, ""),
    )
    monkeypatch.setattr(multi_task_runner, "_operator_backend_runnable", lambda _operator: True)
    monkeypatch.setattr(multi_task_runner, "operator_in_failure_cooldown", lambda _operator_id: False)

    selected, reason = multi_task_runner.select_operator(node, {"name": "builder"})

    assert reason == ""
    assert selected["operator_id"] == "operator-fallback"
    assert selected["scheduler_candidate_rank"] == 2
    assert [item["operator_id"] for item in selected["scheduler_candidate_observations"]] == [
        "operator-primary", "operator-fallback"
    ]
    assert "operator-unlisted" not in json.dumps(selected)


def test_operator_envelope_carries_frozen_handoff_contract() -> None:
    node = scheduler_input._runtime_node(_node("collect"))
    profile = {
        "operator_id": "operator-primary",
        "role": "builder",
        "name": "builder",
        "scheduler_candidate_rank": 1,
    }
    payload = {
        "write_scope": node["write_scope"],
        "handoff": "handoff.md",
        "dispatch_file": "dispatch.md",
        "graph": "graph.json",
        "work_dir": "work",
    }

    envelope = multi_task_runner._build_operator_envelope(
        "dispatch-1", "sprint-test", "collect", node, profile, payload
    )

    assert envelope["task_type"] == "research"
    assert envelope["artifact_contract"] == node["artifact_contract"]
    assert envelope["evaluation_binding"] == node["evaluation_binding"]
    assert envelope["capsule_binding"] == node["capsule_binding"]
    assert envelope["physical_candidate_rank"] == 1


def test_dispatch_and_lease_records_are_runtime_artifacts(tmp_path: Path) -> None:
    value = _scheduler_input()
    source = tmp_path / "scheduler_input.json"
    _write(source, value)
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    node = graph["nodes"][0]
    profile = {
        "operator_id": "operator-fallback",
        "scheduler_candidate_observations": [
            {"operator_id": "operator-primary", "state": "UNAVAILABLE", "rank": 1, "reason": "leased"},
            {"operator_id": "operator-fallback", "state": "READY", "rank": 2},
        ],
    }
    paths = scheduler_input.write_dispatch_records(
        tmp_path / "records",
        graph=graph,
        node=node,
        profile=profile,
        submit_result={
            "operator_id": "operator-fallback",
            "lease_id": "lease-1",
            "submitted_at": "2026-08-26T12:00:00Z",
            "expires_at": "2026-08-26T12:15:00Z",
        },
        dispatch_id="dispatch-1",
    )

    dispatch = json.loads(Path(paths["dispatch_record"]).read_text(encoding="utf-8"))
    lease = json.loads(Path(paths["lease_record"]).read_text(encoding="utf-8"))
    assert dispatch["selected_operator"] == "operator-fallback"
    assert dispatch["excluded"][0]["operator_id"] == "operator-primary"
    assert lease["fencing_token"] == 1
    assert lease["expires_at"] == "2026-08-26T12:15:00Z"


def test_dispatch_record_paths_bound_long_user_ids_deterministically(tmp_path: Path) -> None:
    value = _scheduler_input()
    source = tmp_path / "scheduler_input.json"
    _write(source, value)
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    graph["sprint_id"] = "e2e-battery-live-v8-20260827-" + "planner-sprint-" * 12
    node = graph["nodes"][0]
    node["id"] = "discovery-ingest-and-evidence-normalization-" + "node-" * 18
    dispatch_id = "dispatch-research-operator-registry-" + "attempt-" * 18
    profile = {"operator_id": "discovery_ingest_worker"}
    submit_result = {"operator_id": "discovery_ingest_worker", "lease_id": "lease-1"}

    first = scheduler_input.write_dispatch_records(
        tmp_path / "scheduler-records",
        graph=graph,
        node=node,
        profile=profile,
        submit_result=submit_result,
        dispatch_id=dispatch_id,
    )
    second = scheduler_input.write_dispatch_records(
        tmp_path / "scheduler-records",
        graph=graph,
        node=node,
        profile=profile,
        submit_result=submit_result,
        dispatch_id=dispatch_id,
    )

    assert first == second
    dispatch_path = Path(first["dispatch_record"])
    assert dispatch_path.is_file()
    components = dispatch_path.relative_to(tmp_path / "scheduler-records").parts[:-1]
    assert len(components) == 3
    assert all(len(component) <= 24 for component in components)
    assert components[0].startswith("e2e-battery")
    assert components[1].startswith("discovery-i")
    assert components[2].startswith("dispatch-re")


def test_source_digest_is_raw_file_digest(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    assert scheduler_input.file_sha256(source) == hashlib.sha256(source.read_bytes()).hexdigest()


def test_runtime_input_binding_is_hashed_routed_and_tamper_evident(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    input_artifact = tmp_path / "inputs" / "request.json"
    input_artifact.parent.mkdir()
    input_artifact.write_text('{"request":"test"}\n', encoding="utf-8")
    _write(source, _scheduler_input())

    graph_path = scheduler_input.prepare_runtime_graph(
        source,
        tmp_path / "runtime",
        artifact_bindings={"artifact.request.v1": str(input_artifact)},
    )
    graph = graph_scheduler.load_graph(graph_path)

    binding = graph["runtime_input_bindings"]["artifact.request.v1"]
    assert binding["path"] == str(input_artifact.resolve())
    assert binding["sha256"] == hashlib.sha256(input_artifact.read_bytes()).hexdigest()
    assert graph["nodes"][0]["artifact_routes"]["consumes"]["artifact.request.v1"] == str(input_artifact.resolve())
    assert graph["nodes"][0]["read_scope"] == [str(input_artifact.resolve())]
    assert scheduler_input.verify_runtime_projection(graph)["ok"] is True

    input_artifact.write_text('{"request":"changed"}\n', encoding="utf-8")
    assert scheduler_input.verify_runtime_projection(graph)["errors"] == [
        "RUNTIME_INPUT_ARTIFACT_HASH_MISMATCH:artifact.request.v1"
    ]


def test_runner_scheduler_runtime_dir_aligns_all_runtime_consumers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_root = (tmp_path / "custom-runtime").resolve()
    stale_root = tmp_path / "stale-sprints"
    monkeypatch.setattr(multi_task_runner, "SPRINTS_DIR", stale_root)
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", stale_root)
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", stale_root)
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(stale_root))
    monkeypatch.setenv("SOLAR_HARNESS_SPRINTS_DIR", str(stale_root))
    args = types.SimpleNamespace(
        scheduler_input=[str(source)],
        scheduler_runtime_dir=str(runtime_root),
        artifact_binding=[],
        run_contract="",
        graph=[],
    )

    graphs = multi_task_runner.prepare_scheduler_input_args(args)

    assert graphs == [str(runtime_root / "sprint-test.task_graph.json")]
    assert multi_task_runner.SPRINTS_DIR == runtime_root
    assert graph_scheduler.SPRINTS_DIR == runtime_root
    assert graph_node_dispatcher.SPRINTS_DIR == runtime_root
    assert os.environ["HARNESS_SPRINTS_DIR"] == str(runtime_root)
    assert os.environ["SOLAR_HARNESS_SPRINTS_DIR"] == str(runtime_root)


def test_runner_explicit_projection_graph_restores_its_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    runtime_root = (tmp_path / "published-runtime").resolve()
    graph_path = scheduler_input.prepare_runtime_graph(source, runtime_root)
    stale_root = tmp_path / "global-sprints"
    monkeypatch.setattr(multi_task_runner, "SPRINTS_DIR", stale_root)
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", stale_root)
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", stale_root)
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(stale_root))
    monkeypatch.setenv("SOLAR_HARNESS_SPRINTS_DIR", str(stale_root))
    args = types.SimpleNamespace(scheduler_input=[], graph=[str(graph_path)])

    graphs = multi_task_runner.prepare_scheduler_input_args(args)

    assert graphs == [str(graph_path)]
    assert multi_task_runner.SPRINTS_DIR == runtime_root
    assert graph_scheduler.SPRINTS_DIR == runtime_root
    assert graph_node_dispatcher.SPRINTS_DIR == runtime_root
    assert os.environ["HARNESS_SPRINTS_DIR"] == str(runtime_root)
    assert os.environ["SOLAR_HARNESS_SPRINTS_DIR"] == str(runtime_root)


def test_request_envelope_controller_input_routes_to_operator_dispatch_envelope(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scheduler_input.json"
    value = _scheduler_input()
    value["graph"]["nodes"][0]["artifact_contract"]["consumes"] = [
        "schema:request-envelope.schema.json"
    ]
    _write(source, value)

    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    node = graph["nodes"][0]

    assert node["artifact_routes"]["consumes"] == {
        "schema:request-envelope.schema.json": "dispatch/envelope.json"
    }
    assert node["read_scope"] == ["dispatch/envelope.json"]
    assert scheduler_input.verify_runtime_projection(graph)["ok"] is True


def test_scheduler_projection_manifest_anchor_covers_runtime_inputs_and_outputs(tmp_path: Path) -> None:
    source = tmp_path / "scheduler_input.json"
    input_artifact = tmp_path / "inputs" / "request.json"
    input_artifact.parent.mkdir()
    input_artifact.write_text('{"request":"test"}\n', encoding="utf-8")
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(
        source,
        tmp_path / "runtime",
        artifact_bindings={"artifact.request.v1": str(input_artifact)},
    )
    graph = graph_scheduler.load_graph(graph_path)
    node = graph["nodes"][0]
    output_dir = Path(node["write_scope"][0])
    output_dir.mkdir(parents=True)
    (output_dir / "result.json").write_text("{}\n", encoding="utf-8")

    base_dir, roots, write_scope = graph_node_dispatcher._manifest_anchor(
        "sprint-test", graph, node
    )

    assert base_dir == Path(graph["runtime_work_dir"])
    assert roots["canonical"] == graph["runtime_work_dir"]
    assert str(input_artifact.parent.resolve()) in roots.values()
    assert write_scope is None
    input_row = graph_node_dispatcher._artifact_manifest.snapshot_declared_path(
        node["read_scope"][0], base_dir=base_dir, roots=roots
    )
    output_row = graph_node_dispatcher._artifact_manifest.snapshot_declared_path(
        node["write_scope"][0], base_dir=base_dir, roots=roots
    )
    assert input_row["resolved_root"].startswith("input_")
    assert input_row["exists"] is True
    assert output_row["resolved_root"] == "canonical"
    assert output_row["exists"] is True


def _workspace_publish_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    public_and_private: bool = True,
) -> tuple[Path, dict, dict, Path, Path]:
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    workspace = tmp_path / "project"
    harness = tmp_path / "harness"
    harness.mkdir()
    value = _scheduler_input()
    first = value["graph"]["nodes"][0]
    first["artifact_contract"]["produces"] = ["artifact.evidence.v1"]
    first["output_routes"] = [
        {
            "artifact_type": "artifact.evidence.v1",
            "route_kind": (
                "workspace_publish" if public_and_private else "sprint_private"
            ),
            "relative_path": (
                "ARCHITECTURE_SUMMARY.md" if public_and_private else "evidence.json"
            ),
            "materialization_kind": "file",
        }
    ]
    if public_and_private:
        first["artifact_contract"]["produces"].append("artifact.eval_receipt.v1")
        first["output_routes"].append(
            {
                "artifact_type": "artifact.eval_receipt.v1",
                "route_kind": "sprint_private",
                "relative_path": "evaluation.json",
                "materialization_kind": "file",
            }
        )
    _write(
        sprints / "sprint-test.raw_intent.json",
        {"context": {"repo": str(workspace.resolve())}},
    )
    _write(sprints / "sprint-test.intent_ir.json", {"intent_ir_id": "intent-test"})
    _write(
        sprints / "sprint-test.requirement_ir.json",
        {"source_inputs": {"workspace_root": str(workspace.resolve())}},
    )
    _attach_workspace_authority(sprints, value, workspace=workspace)
    workspace_binding.bind_active_workspace(harness, workspace)
    source = sprints / "scheduler_input.json"
    _write(source, value)
    graph_path = scheduler_input.prepare_runtime_graph(source, sprints)
    graph = graph_scheduler.load_graph(graph_path)
    node = graph["nodes"][0]
    public = Path(node["artifact_routes"]["produces"]["artifact.evidence.v1"])
    private = Path(
        node["artifact_routes"]["produces"].get(
            "artifact.eval_receipt.v1", node["artifact_routes"]["produces"]["artifact.evidence.v1"]
        )
    )
    public.parent.mkdir(parents=True, exist_ok=True)
    private.parent.mkdir(parents=True, exist_ok=True)
    public.write_text("# Verified summary\n", encoding="utf-8")
    private.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    manifest = graph_node_dispatcher._artifact_manifest.write_manifest(
        sprints,
        "sprint-test",
        node,
        generation=0,
        base_dir=Path(graph["runtime_work_dir"]),
        roots={"canonical": graph["runtime_work_dir"]},
    )
    assert manifest is not None
    monkeypatch.setattr(graph_node_dispatcher, "HARNESS_DIR", harness)
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", sprints)
    return sprints, graph, node, public, private


def test_passed_gate_publishes_only_frozen_public_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sprints, graph, node, public, private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )

    result = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )

    assert result["ok"] is True, result
    project = tmp_path / "project"
    assert (project / "ARCHITECTURE_SUMMARY.md").read_bytes() == public.read_bytes()
    assert not (project / "evaluation.json").exists()
    assert {Path(row["from"]) for row in result["published"]} == {public}
    assert private.is_file(), "private evidence remains in sprint staging"


def test_frozen_workspace_authority_cannot_be_redirected_by_later_active_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sprints, graph, node, public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    project_a = tmp_path / "project"
    project_b = tmp_path / "project-b"
    project_b.mkdir()
    workspace_binding.bind_active_workspace(tmp_path / "harness", project_b)

    result = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )

    assert result["ok"] is True, result
    assert result["workspace_root"] == str(project_a.resolve())
    assert result["active_binding_matches"] is False
    assert (project_a / "ARCHITECTURE_SUMMARY.md").read_bytes() == public.read_bytes()
    assert not (project_b / "ARCHITECTURE_SUMMARY.md").exists()


def _write_private_manifest_for_second_node(
    sprints: Path,
    graph: dict,
) -> dict:
    node = graph["nodes"][1]
    output = Path(node["artifact_routes"]["produces"]["artifact.report.v1"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("# Private verifier result\n", encoding="utf-8")
    manifest = graph_node_dispatcher._artifact_manifest.write_manifest(
        sprints,
        "sprint-test",
        node,
        generation=0,
        base_dir=Path(graph["runtime_work_dir"]),
        roots={"canonical": graph["runtime_work_dir"]},
    )
    assert manifest is not None
    return node


def test_downstream_failure_leaves_passed_producer_output_staged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, graph, producer, _public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    verifier = _write_private_manifest_for_second_node(sprints, graph)

    deferred = graph_node_dispatcher._publish_terminal_graph_outputs(
        "sprint-test", producer, graph
    )
    assert deferred["deferred"] is True
    producer["status"] = "passed"
    eval_path = sprints / "sprint-test.synthesize-eval.json"
    _write(eval_path, {"node_id": "synthesize", "verdict": "FAIL"})

    result = graph_node_dispatcher._finalize_node_pass(
        "sprint-test", verifier, graph, eval_json=eval_path
    )

    assert result["ok"] is False
    assert not (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").exists()


def test_terminal_green_barrier_publishes_requested_output_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, graph, producer, public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    verifier = _write_private_manifest_for_second_node(sprints, graph)
    producer["status"] = "passed"
    verifier["status"] = "passed"
    graph_scheduler.save_graph(sprints / "sprint-test.task_graph.json", graph)
    graph = graph_scheduler.load_graph(sprints / "sprint-test.task_graph.json")
    verifier = graph["nodes"][1]
    calls = 0
    real_publish = graph_node_dispatcher._artifact_manifest.publish_workspace_outputs

    def counted_publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(
        graph_node_dispatcher._artifact_manifest,
        "publish_workspace_outputs",
        counted_publish,
    )

    first = graph_node_dispatcher._publish_terminal_graph_outputs(
        "sprint-test", verifier, graph
    )
    second = graph_node_dispatcher._publish_terminal_graph_outputs(
        "sprint-test", verifier, graph
    )

    assert first["ok"] is True, first
    assert second["ok"] is True, second
    assert calls == 1
    assert (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").read_bytes() == public.read_bytes()
    journal = json.loads(
        (sprints / "sprint-test.collect-publish.json").read_text(encoding="utf-8")
    )
    assert journal["state"] == "COMMITTED"


def test_parent_terminal_status_requires_committed_graph_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, graph, producer, public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    verifier = _write_private_manifest_for_second_node(sprints, graph)
    producer["status"] = "passed"
    verifier["status"] = "passed"
    graph_path = sprints / "sprint-test.task_graph.json"
    graph_scheduler.save_graph(graph_path, graph)
    durable = graph_scheduler.load_graph(graph_path)
    parent = graph_scheduler.parent_ready_check(durable)
    _write(
        sprints / "sprint-test.status.json",
        {"status": "active", "phase": "running", "history": []},
    )

    updated = graph_node_dispatcher._mark_parent_sprint_passed_if_ready(
        "sprint-test", parent, False, graph_path=graph_path
    )

    assert updated is True
    status = json.loads(
        (sprints / "sprint-test.status.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "passed"
    assert status["phase"] == "completed"
    assert (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").read_bytes() == public.read_bytes()
    journal = json.loads(
        (sprints / "sprint-test.collect-publish.json").read_text(encoding="utf-8")
    )
    assert journal["state"] == "COMMITTED"


def test_graph_save_failure_after_publish_is_restart_reconcilable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, graph, producer, public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    verifier = _write_private_manifest_for_second_node(sprints, graph)
    producer["status"] = "passed"
    verifier["status"] = "passed"
    graph_path = sprints / "sprint-test.task_graph.json"
    graph_scheduler.save_graph(graph_path, graph)
    parent = graph_scheduler.parent_ready_check(graph_scheduler.load_graph(graph_path))
    status_path = sprints / "sprint-test.status.json"
    _write(status_path, {"status": "active", "phase": "running", "history": []})
    real_save = graph_node_dispatcher.save_graph
    monkeypatch.setattr(
        graph_node_dispatcher,
        "save_graph",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("state replace failed")),
    )

    updated = graph_node_dispatcher._mark_parent_sprint_passed_if_ready(
        "sprint-test", parent, False, graph_path=graph_path
    )

    assert updated is False
    assert json.loads(status_path.read_text(encoding="utf-8"))["status"] == "active"
    journal_path = sprints / "sprint-test.collect-publish.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["state"] == "COMMITTED"
    assert (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").read_bytes() == public.read_bytes()

    monkeypatch.setattr(graph_node_dispatcher, "save_graph", real_save)
    reconciled = graph_node_dispatcher._mark_parent_sprint_passed_if_ready(
        "sprint-test", parent, False, graph_path=graph_path
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert reconciled is True
    assert status["status"] == "passed"
    assert sum(row.get("event") == "graph_parent_ready_passed" for row in status["history"]) == 1


@pytest.mark.parametrize(
    ("status", "phase", "expected"),
    [
        ("passed", "completed", True),
        ("passed", "running", False),
        ("active", "completed", False),
    ],
)
def test_terminal_status_requires_consistent_status_phase_pair(
    status: str,
    phase: str,
    expected: bool,
) -> None:
    assert graph_node_dispatcher._status_is_terminal_pass(
        {"status": status, "phase": phase}
    ) is expected


def test_terminal_publication_block_event_is_deduplicated_across_ticks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, graph, producer, _public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    verifier = _write_private_manifest_for_second_node(sprints, graph)
    producer["status"] = "passed"
    verifier["status"] = "passed"
    graph_path = sprints / "sprint-test.task_graph.json"
    graph_scheduler.save_graph(graph_path, graph)
    parent = graph_scheduler.parent_ready_check(graph_scheduler.load_graph(graph_path))
    _write(
        sprints / "sprint-test.status.json",
        {"status": "active", "phase": "running", "history": []},
    )
    monkeypatch.setattr(
        graph_node_dispatcher,
        "_publish_terminal_graph_outputs",
        lambda *_args, **_kwargs: {
            "required": True,
            "ok": False,
            "reason": "terminal_graph_publication_failed",
            "failed_node": "collect",
        },
    )

    assert graph_node_dispatcher._mark_parent_sprint_passed_if_ready(
        "sprint-test", parent, False, graph_path=graph_path
    ) is False
    assert graph_node_dispatcher._mark_parent_sprint_passed_if_ready(
        "sprint-test", parent, False, graph_path=graph_path
    ) is False

    events = [
        json.loads(line)
        for line in (sprints / "sprint-test.events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert sum(
        row.get("event") == "graph_terminal_publication_blocked" for row in events
    ) == 1
    block = json.loads(
        (sprints / "sprint-test.terminal-publication-block.json").read_text(encoding="utf-8")
    )
    assert block["state"] == "BLOCKED"
    assert block["retryable"] is True


def test_publication_prepare_failure_mutates_no_workspace_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sprints, graph, node, _public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        graph_node_dispatcher,
        "_atomic_workspace_publish_journal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("journal replace failed")),
    )

    result = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )

    assert result["reason"] == "workspace_publish_prepare_failed"
    assert not (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").exists()


def test_prepared_publication_recovers_and_commits_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, graph, node, public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    real_journal = graph_node_dispatcher._atomic_workspace_publish_journal
    writes = 0

    def fail_commit(path, payload):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("commit replace failed")
        real_journal(path, payload)

    monkeypatch.setattr(
        graph_node_dispatcher,
        "_atomic_workspace_publish_journal",
        fail_commit,
    )
    interrupted = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )
    assert interrupted["reason"] == "workspace_publish_commit_failed"
    journal_path = sprints / "sprint-test.collect-publish.json"
    assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] == "PREPARED"
    assert (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").read_bytes() == public.read_bytes()

    monkeypatch.setattr(
        graph_node_dispatcher,
        "_atomic_workspace_publish_journal",
        real_journal,
    )
    recovered = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )
    replay = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )

    assert recovered["state"] == "COMMITTED"
    assert replay["journal_id"] == recovered["journal_id"]
    assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] == "COMMITTED"
    assert (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").read_bytes() == public.read_bytes()


def test_committed_publication_revalidates_and_repairs_tampered_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sprints, graph, node, public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    first = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )
    assert first["state"] == "COMMITTED"
    destination = tmp_path / "project" / "ARCHITECTURE_SUMMARY.md"
    destination.write_text("tampered after commit\n", encoding="utf-8")
    calls = 0
    real_publish = graph_node_dispatcher._artifact_manifest.publish_workspace_outputs

    def counted_publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(
        graph_node_dispatcher._artifact_manifest,
        "publish_workspace_outputs",
        counted_publish,
    )

    repaired = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )

    assert repaired["state"] == "COMMITTED"
    assert calls == 1
    assert destination.read_bytes() == public.read_bytes()


def test_failed_gate_never_reaches_workspace_publisher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, graph, node, _public, _private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    eval_path = sprints / "sprint-test.collect-eval.json"
    _write(eval_path, {"node_id": "collect", "verdict": "FAIL"})
    monkeypatch.setattr(
        graph_node_dispatcher,
        "_publish_verified_node_outputs",
        lambda *_args, **_kwargs: pytest.fail("failed gate reached publisher"),
    )

    result = graph_node_dispatcher._finalize_node_pass(
        "sprint-test", node, graph, eval_json=eval_path
    )

    assert result["ok"] is False
    assert not (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").exists()


def test_private_only_node_never_calls_workspace_publisher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sprints, graph, node, _public, _private = _workspace_publish_runtime(
        tmp_path,
        monkeypatch,
        public_and_private=False,
    )
    monkeypatch.setattr(
        graph_node_dispatcher._artifact_manifest,
        "publish_workspace_outputs",
        lambda *_args, **_kwargs: pytest.fail("private row reached publisher"),
    )

    result = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )

    assert result == {
        "required": False,
        "ok": True,
        "skipped": "private_outputs_only",
    }


@pytest.mark.parametrize("manifest_shape", ["missing", "duplicate"])
def test_public_scope_requires_exactly_one_verified_manifest_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_shape: str,
) -> None:
    sprints, graph, node, public, private = _workspace_publish_runtime(
        tmp_path, monkeypatch
    )
    manifest_path = graph_node_dispatcher._artifact_manifest.manifest_path(
        sprints, "sprint-test", "collect"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    public_row = next(
        row for row in manifest["rows"] if Path(str(row["path"])) == public
    )
    if manifest_shape == "missing":
        public_row["path"] = str(private)
    else:
        manifest["rows"].append(deepcopy(public_row))
    manifest["content_digest"] = graph_node_dispatcher._artifact_manifest.manifest_content_digest(
        manifest
    )
    _write(manifest_path, manifest)

    result = graph_node_dispatcher._publish_verified_node_outputs(
        "sprint-test", node, graph
    )

    assert result["ok"] is False
    assert result["reason"] == "workspace_publish_scope_manifest_mismatch"
    assert result["match_count"] == (0 if manifest_shape == "missing" else 2)
    assert not (tmp_path / "project" / "ARCHITECTURE_SUMMARY.md").exists()


def test_windows_cp1252_console_is_reconfigured_before_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    binary = io.BytesIO()
    console = io.TextIOWrapper(binary, encoding="cp1252")
    monkeypatch.setattr(multi_task_runner.sys, "stdout", console)

    multi_task_runner._configure_utf8_console()
    print("模型组合", file=console, flush=True)

    assert console.encoding.lower().replace("-", "") == "utf8"
    assert "模型组合" in binary.getvalue().decode("utf-8")


def test_failure_policy_fail_run_is_applied_at_exact_attempt_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scheduler_input.json"
    value = _scheduler_input()
    value["graph"]["nodes"][0]["failure_policy"] = {
        "max_attempts": 1,
        "on_exhausted": "fail_run",
    }
    _write(source, value)
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    node = graph["nodes"][0]
    node.update(
        {
            "status": "dispatched",
            "assigned_to": "operator:operator-primary",
            "dispatch_id": "dispatch-1",
            "execution_attempt": {
                "sequence": 1,
                "task_id": "dispatch-1",
                "status": "submitted",
            },
        }
    )
    monkeypatch.setattr(graph_node_dispatcher, "release_lease", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_node_dispatcher, "_append_dispatch_ledger", lambda *_args, **_kwargs: None)

    result = graph_node_dispatcher._requeue_node_after_operator_closeout(
        "sprint-test",
        "collect",
        node,
        graph,
        "dispatched",
        {"reason": "operator_failed", "operator_status": "failed"},
    )

    assert result["reason"] == "failure_policy_attempt_budget_exhausted"
    assert graph_scheduler.node_status(graph, "collect") == "failed"
    assert graph_scheduler.node_status(graph, "synthesize") == "cancelled"
    assert node["failure_policy_exhausted"]["on_exhausted"] == "fail_run"


def test_launch_attaches_attempt_to_authoritative_graph_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    ready_copy = graph_scheduler.ready_nodes(graph)[0]
    profile = {
        "name": "builder",
        "role": "builder",
        "persona": "builder",
        "backend": "command",
        "model": "test",
        "command": "test-command",
        "operator_id": "operator-primary",
        "approval_mode": "default",
        "scheduler_candidate_rank": 1,
        "scheduler_candidate_observations": [
            {"operator_id": "operator-primary", "state": "READY", "rank": 1}
        ],
    }
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(multi_task_runner, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(multi_task_runner, "SPRINTS_DIR", tmp_path / "runtime")
    monkeypatch.setattr(multi_task_runner, "select_profile", lambda *_args, **_kwargs: deepcopy(profile))
    monkeypatch.setattr(multi_task_runner, "capability_for_profile", lambda _profile: {"status": "ok", "provider": "test"})
    monkeypatch.setattr(multi_task_runner, "build_dispatch_text", lambda *_args, **_kwargs: "dispatch")
    monkeypatch.setattr(multi_task_runner, "set_last_launch", lambda: None)
    dispatch_record_roots: list[Path] = []

    def capture_dispatch_record_root(output_root, **_kwargs):
        dispatch_record_roots.append(Path(output_root))
        return {}

    monkeypatch.setattr(scheduler_input, "write_dispatch_records", capture_dispatch_record_root)
    monkeypatch.setattr(
        __import__("operator_runtime"),
        "submit",
        lambda envelope: {
            "task_id": envelope["task_id"],
            "operator_id": "operator-primary",
            "lease_id": "lease-1",
            "status": "submitted",
            "submitted_at": "2026-08-26T12:00:00Z",
            "expires_at": "2026-08-26T13:00:00Z",
        },
    )

    multi_task_runner.launch_node(
        graph_path,
        graph,
        ready_copy,
        type("Args", (), {"profile": "", "model": "", "backend": ""})(),
    )

    authoritative = graph["nodes"][0]
    assert authoritative["execution_attempt"]["sequence"] == 1
    assert authoritative["execution_attempt"]["operator_id"] == "operator-primary"
    assert "execution_attempt" not in ready_copy
    assert dispatch_record_roots == [graph_path.parent / "scheduler-records"]


def test_cancel_terminalizes_task_when_tmux_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_id = "task-windows-no-tmux"
    run_dir = tmp_path / "multi-task"
    task_dir = run_dir / task_id
    task_dir.mkdir(parents=True)
    status = {
        "id": task_id,
        "status": "submitted",
        "window": "legacy-window",
        "graph": str(tmp_path / "missing-graph.json"),
        "node_id": "node-1",
    }
    _write(task_dir / "status.json", status)
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)
    monkeypatch.setattr(multi_task_runner, "list_task_rows", lambda: [dict(status)])
    monkeypatch.setattr(multi_task_runner.shutil, "which", lambda _name: None)

    assert multi_task_runner.cancel(task_id) == 0
    saved = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
    assert saved["status"] == "cancelled"


def test_windows_pid_probes_do_not_broadcast_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []
    fake_winapi = types.SimpleNamespace(
        OpenProcess=lambda _access, _inherit, pid: calls.append(("open", pid)) or 123,
        GetExitCodeProcess=lambda handle: calls.append(("status", handle)) or 259,
        CloseHandle=lambda handle: calls.append(("close", handle)),
    )
    monkeypatch.setitem(sys.modules, "_winapi", fake_winapi)
    monkeypatch.setattr(operator_runtime.os, "name", "nt")
    monkeypatch.setattr(
        operator_runtime.os,
        "kill",
        lambda *_args: pytest.fail("os.kill(pid, 0) broadcasts CTRL_C_EVENT on Windows"),
    )

    assert operator_runtime._pid_exists(101) is True
    assert multi_task_runner._pid_is_alive(202) is True
    assert calls == [
        ("open", 101), ("status", 123), ("close", 123),
        ("open", 202), ("status", 123), ("close", 123),
    ]


def test_scheduler_input_binding_exposes_only_exact_evaluator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = _scheduler_input()
    for node in value["graph"]["nodes"]:
        node["evaluation_binding"]["semantic_evaluator_ids"] = ["evaluator-frozen"]
    source = tmp_path / "scheduler_input.json"
    _write(source, value)
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    monkeypatch.setattr(
        operator_runtime,
        "get_operator_config",
        lambda operator_id: {"operator_id": operator_id, "enabled": True, "model": "cheap-model"},
    )
    monkeypatch.setattr(
        graph_node_dispatcher,
        "_operator_runtime_state_for_graph",
        lambda _operator_id: "idle",
    )

    evaluators = graph_node_dispatcher._scheduler_input_bound_evaluators(graph)

    assert [item["operator_id"] for item in evaluators] == ["evaluator-frozen"]
    assert evaluators[0]["pane"] == "operator-pool:evaluator:evaluator-frozen"
    assert evaluators[0]["busy"] is False


def test_scheduler_input_semantic_check_resolves_to_evaluator_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = _scheduler_input()
    for node in value["graph"]["nodes"]:
        node["evaluation_binding"]["semantic_evaluator_ids"] = [
            "check.unknown_resolution_trace.v1"
        ]
    source = tmp_path / "scheduler_input.json"
    _write(source, value)
    graph_path = scheduler_input.prepare_runtime_graph(source, tmp_path / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    monkeypatch.setattr(operator_runtime, "get_operator_config", lambda _operator_id: None)
    monkeypatch.setattr(
        graph_node_dispatcher,
        "_evaluator_operator_pool_workers",
        lambda: [
            {
                "pane": "operator-pool:evaluator.0",
                "models": ["gpt-5.5"],
                "skills": ["review"],
                "busy": False,
            }
        ],
    )

    evaluators = graph_node_dispatcher._scheduler_input_bound_evaluators(graph)

    assert [item["pane"] for item in evaluators] == ["operator-pool:evaluator.0"]
    assert evaluators[0]["semantic_check_ids"] == [
        "check.unknown_resolution_trace.v1"
    ]
    assert evaluators[0]["resolution_source"] == (
        "evaluation_check_registry_to_operator_pool"
    )


def test_eval_broker_child_uses_the_scheduler_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(graph_node_dispatcher, "SPRINTS_DIR", runtime_root)
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(tmp_path / "wrong-harness-root"))
    monkeypatch.setenv("SOLAR_HARNESS_SPRINTS_DIR", str(tmp_path / "wrong-solar-root"))

    env = graph_node_dispatcher._broker_env("sprint-test")

    assert env["HARNESS_SPRINTS_DIR"] == str(runtime_root)
    assert env["SOLAR_HARNESS_SPRINTS_DIR"] == str(runtime_root)
    assert env["SOLAR_BROKER_SPRINT_ID"] == "sprint-test"


def test_operator_pool_submit_failure_is_bounded_and_gui_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = {
        "sprint_id": "sprint-test",
        "nodes": [{"id": "collect", "status": "reviewing"}],
        "node_results": {"collect": {"status": "reviewing"}},
    }
    monkeypatch.setattr(graph_node_dispatcher, "GRAPH_NODE_EVAL_MAX_DISPATCH_FAILURES", 1)
    monkeypatch.setattr(graph_node_dispatcher, "_append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph_node_dispatcher, "_record_node_runstate", lambda *_args, **_kwargs: None)

    terminalized = graph_node_dispatcher._account_eval_dispatch_failures(
        graph,
        "sprint-test",
        [{"node": "collect", "reason": "operator_pool_eval_submit_failed"}],
        False,
    )

    node = graph["nodes"][0]
    assert terminalized[0]["status"] == "needs_human_review"
    assert node["eval_dispatch_failures"] == 1
    assert node["last_eval_dispatch_failure_reason"] == "operator_pool_eval_submit_failed"
    assert "operator_pool_eval_submit_failed" in node["eval_blocked_reason"]


def test_evaluator_dispatch_skips_when_another_scheduler_owns_the_graph_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        graph_node_dispatcher,
        "_try_acquire_scheduler_tick_lock",
        lambda _graph_path: None,
    )
    monkeypatch.setattr(
        graph_node_dispatcher,
        "_dispatch_node_evals_unlocked",
        lambda *_args, **_kwargs: pytest.fail("contending dispatcher must not submit"),
    )

    result = graph_node_dispatcher.dispatch_node_evals("runtime.task_graph.json")

    assert result["ok"] is True
    assert result["reason"] == "scheduler_tick_in_progress"
    assert result["dispatched"] == []
