"""Contract tests for frozen SchedulerInput -> mutable scheduler runtime."""
from __future__ import annotations

import hashlib
import io
import json
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


def _node(node_id: str, *, depends_on: list[str] | None = None, consumes: list[str] | None = None,
          produces: list[str] | None = None, priority: int = 10) -> dict:
    return {
        "id": node_id,
        "goal": f"Complete {node_id}",
        "logical_operator": "ResearchWorker",
        "dispatch_task_type": "research",
        "depends_on": depends_on or [],
        "requirement_ids": [f"REQ-{node_id}"],
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
    graph_scheduler.save_graph(graph_path, graph)
    assert source.read_bytes() == before
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated["nodes"]["collect"]["status"] == "dispatched"
    assert updated["nodes"]["collect"]["attempt"] == 1
    assert updated["revision"] == 1
    reloaded = graph_scheduler.load_graph(graph_path)
    assert reloaded["nodes"][0]["execution_attempt"]["task_id"] == "dispatch-1"
    static_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "execution_attempt" not in static_graph["nodes"][0]


def test_verified_runtime_projection_inherits_containing_active_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "scheduler_input.json"
    _write(source, _scheduler_input())
    graph_path = scheduler_input.prepare_runtime_graph(source, workspace / "runtime")
    graph = graph_scheduler.load_graph(graph_path)
    Path(graph["runtime_work_dir"]).mkdir(parents=True)

    assert graph_node_dispatcher._scheduler_projection_workspace(graph, workspace) == workspace.resolve()


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

    graph_node_dispatcher._emit_guard_resource_sidecars(sid, node)

    sidecar = json.loads(
        (runtime_dir / f"{sid}.{node['id']}-resource_binding.json").read_text(encoding="utf-8")
    )
    assert sidecar["workspace_root"] == str(workspace.resolve())
    assert sidecar["bound"] is True
    assert sidecar["in_scope"] is True


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
    monkeypatch.setattr(scheduler_input, "write_dispatch_records", lambda *_args, **_kwargs: {})
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
