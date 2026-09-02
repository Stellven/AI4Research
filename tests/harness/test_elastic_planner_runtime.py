from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "harness" / "lib"
TESTS = ROOT / "tests" / "harness"
for value in (LIB, TESTS):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import elastic_planner  # noqa: E402
import elastic_planner_runtime as runtime  # noqa: E402
import elastic_planner_operator  # noqa: E402
import graph_node_dispatcher  # noqa: E402
import operatord  # noqa: E402
import pm_dispatch  # noqa: E402
import workflow_guard  # noqa: E402
import workspace_binding  # noqa: E402
from test_elastic_planner import ScriptedModel, _catalog, _requirement_ir  # noqa: E402


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup(tmp_path: Path, sprint_id: str) -> tuple[Path, Path, Path]:
    sprints = tmp_path / "sprints"
    requirement = _write(sprints / f"{sprint_id}.requirement_ir.json", _requirement_ir())
    runtime.claim_owner(sprints, sprint_id, f"intent-{sprint_id}", requirement)
    runtime.initialize_status(sprints, sprint_id, f"intent-{sprint_id}")
    return sprints, requirement, runtime.elastic_planner_root(sprints, sprint_id)


def _operator_result(sprint_id: str, requirement: Path, output_root: Path, status: str) -> Path:
    return _write(
        output_root / "planner_operator_result.json",
        {
            "schema_version": runtime.RESULT_SCHEMA,
            "artifact_role": "operator_result",
            "task_id": f"pm-{sprint_id}",
            "sprint_id": sprint_id,
            "status": status,
            "requirement_ir_ref": {"path": str(requirement.resolve()), "sha256": _sha(requirement)},
            "output_root": str(output_root.resolve()),
            "verification_errors": [],
            "completed_at": "2026-08-28T00:00:00Z",
        },
    )


def test_workspace_authority_freezes_only_explicit_source_pack_files(tmp_path: Path) -> None:
    sprint_id = "sprint-source-inventory"
    sprints = tmp_path / "sprints"
    workspace = tmp_path / "workspace"
    binding_harness = tmp_path / "harness"
    (workspace / "demo_inputs" / "papers").mkdir(parents=True)
    (workspace / "demo_outputs").mkdir()
    first = workspace / "demo_inputs" / "papers" / "first.pdf"
    second = workspace / "demo_inputs" / "papers" / "second.md"
    ignored = workspace / "demo_outputs" / "report.md"
    first.write_bytes(b"pdf-one")
    second.write_text("paper two", encoding="utf-8")
    ignored.write_text("old output", encoding="utf-8")
    requirement = {
        "schema_version": "solar.requirement_ir.v2",
        "requirement_ir_id": "requirement-source-inventory",
        "requirements": [
            {
                "requirement_id": "R-source",
                "statement": "First inspect ./demo_inputs/papers/ and ingest every valid source.",
                "acceptance": {"kind": "process", "required_values": []},
                "check": "check.source_packs_verified",
            },
            {
                "requirement_id": "R-output",
                "statement": "Write the report under ./demo_outputs/.",
                "acceptance": {"kind": "delivery", "required_values": []},
                "check": "check.artifact_outcome_completeness.v1",
            },
        ],
    }
    _write(
        sprints / f"{sprint_id}.raw_intent.json",
        {"context": {"repo": str(workspace), "cwd": str(workspace)}, "raw": {"text": "research"}},
    )
    _write(sprints / f"{sprint_id}.intent_ir.json", {"schema_version": "solar.intent_ir.v3"})
    _write(sprints / f"{sprint_id}.requirement_ir.json", requirement)
    binding_harness.mkdir()
    workspace_binding.bind_active_workspace(binding_harness, workspace, source="test")

    authority_path = workspace_binding.freeze_sprint_workspace_authority(
        sprints,
        sprint_id,
        harness_dir=binding_harness,
    )
    authority = workspace_binding.verify_sprint_workspace_authority(
        authority_path,
        sprints_dir=sprints,
        harness_dir=binding_harness,
    )

    inventory = authority["declared_source_inventory"]
    assert inventory["schema_version"] == "solar.workspace_source_inventory.v1"
    assert [row["relative_path"] for row in inventory["files"]] == [
        "demo_inputs/papers/first.pdf",
        "demo_inputs/papers/second.md",
    ]
    assert all(row["requirement_ids"] == ["R-source"] for row in inventory["files"])
    assert ignored.name not in {Path(row["relative_path"]).name for row in inventory["files"]}

    first.write_bytes(b"changed")
    with pytest.raises(ValueError, match="workspace source inventory (size|hash) mismatch"):
        workspace_binding.verify_sprint_workspace_authority(
            authority_path,
            sprints_dir=sprints,
            harness_dir=binding_harness,
        )


def test_owner_requires_exact_canonical_requirement_ir_path(tmp_path: Path) -> None:
    sprint_id = "sprint-canonical-requirement"
    sprints = tmp_path / "sprints"
    noncanonical = _write(
        sprints / sprint_id / "requirement_ir.json",
        _requirement_ir(),
    )

    with pytest.raises(
        runtime.ElasticPlannerRuntimeError,
        match="^ELASTIC_PLANNER_REQUIREMENT_PATH_NOT_CANONICAL$",
    ):
        runtime.claim_owner(
            sprints,
            sprint_id,
            f"intent-{sprint_id}",
            noncanonical,
        )


def test_concurrent_finalizers_are_serialized_per_sprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_id = "sprint-concurrent-finalizer"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    result = elastic_planner.run_elastic_planning_request(
        _requirement_ir(),
        output_root,
        ScriptedModel(decision="direct_response"),
        ScriptedModel(),
        sprint_id=sprint_id,
        catalog=_catalog(),
    )
    assert result["status"] == "direct_response"
    operator_result = _operator_result(
        sprint_id,
        requirement,
        output_root,
        "direct_response",
    )
    original = runtime._finalize_planner_result_locked
    activity_lock = threading.Lock()
    active = 0
    max_active = 0

    def observed_locked(*args, **kwargs):
        nonlocal active, max_active
        with activity_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.03)
            return original(*args, **kwargs)
        finally:
            with activity_lock:
                active -= 1

    monkeypatch.setattr(runtime, "_finalize_planner_result_locked", observed_locked)
    start = threading.Barrier(2)

    def finalize() -> dict:
        start.wait(timeout=5)
        return runtime.finalize_planner_result(
            sprints,
            sprint_id,
            result_path=operator_result,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _index: finalize(), range(2)))

    status = json.loads(
        (sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8")
    )
    assert receipts[0] == receipts[1]
    assert max_active == 1
    assert sum(
        row.get("event") == "elastic_planner_direct_response_published"
        for row in status["history"]
    ) == 1


def test_direct_result_terminalizes_without_graph_and_repeat_is_exact(tmp_path: Path) -> None:
    sprint_id = "sprint-direct-runtime"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    result = elastic_planner.run_elastic_planning_request(
        _requirement_ir(),
        output_root,
        ScriptedModel(decision="direct_response"),
        ScriptedModel(),
        sprint_id=sprint_id,
        catalog=_catalog(),
    )
    assert result["status"] == "direct_response"
    operator_result = _operator_result(sprint_id, requirement, output_root, "direct_response")

    first = runtime.finalize_planner_result(sprints, sprint_id, result_path=operator_result)
    status_path = sprints / f"{sprint_id}.status.json"
    first_status = json.loads(status_path.read_text(encoding="utf-8"))
    # Crash-window replay: publication landed, but the finalization receipt did
    # not. Reconciliation must finish the receipt without duplicating history.
    (output_root / "finalization.json").unlink()
    second = runtime.finalize_planner_result(sprints, sprint_id, result_path=operator_result)
    second_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert first == second
    assert first["published"]["graph"] is None
    assert not (sprints / f"{sprint_id}.task_graph.json").exists()
    assert first_status["status"] == "passed"
    assert first_status["phase"] == "direct_response_complete"
    assert second_status["history"] == first_status["history"]
    assert Path(first_status["direct_response_ref"]["path"]).read_text(encoding="utf-8").strip()


def test_pm_failure_projects_once_and_reconcile_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprint_id = "sprint-elastic-terminal-failure"
    task_id = "pm-elastic-terminal-failure"
    sprints, _requirement, _output_root = _setup(tmp_path, sprint_id)
    runtime.update_owner(
        sprints,
        sprint_id,
        state="submitted",
        planner_task_id=task_id,
    )
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", tmp_path / "pm-inbox")
    pm_dispatch.write_pm_task_record(
        task_id,
        {
            "task_id": task_id,
            "sprint_id": sprint_id,
            "node_id": "elastic-planner",
            "closeout_kind": "elastic_planner",
            "status": "submitted",
        },
    )

    assert pm_dispatch.cmd_fail(
        argparse.Namespace(
            task_id=task_id,
            status="failed_contract_closeout",
            reason="planner contract invalid",
        )
    ) == 0
    first_status = json.loads(
        (sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8")
    )
    first_owner = json.loads(
        runtime.owner_path(sprints, sprint_id).read_text(encoding="utf-8")
    )
    assert first_status["status"] == "failed"
    assert first_status["phase"] == "elastic_planner_failed"
    assert first_status["handoff_to"] == ""
    assert first_status["target_role"] == ""
    assert first_owner["state"] == "failed"
    assert first_owner["failure"]["retryable"] is False
    assert first_owner["failure"]["record_ref"]["path"] == str(
        (tmp_path / "pm-inbox" / f"{task_id}.json").resolve()
    )

    assert pm_dispatch.cmd_reconcile(
        argparse.Namespace(max_age_minutes=60, apply=True, json=True, limit=40)
    ) == 0
    second_status = json.loads(
        (sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8")
    )
    assert second_status["history"] == first_status["history"]
    assert sum(
        row.get("event") == "elastic_planner_failed"
        for row in second_status["history"]
    ) == 1


def test_stale_failure_cannot_overwrite_newer_attempt(tmp_path: Path) -> None:
    sprint_id = "sprint-elastic-stale-failure"
    sprints, _requirement, _output_root = _setup(tmp_path, sprint_id)
    runtime.update_owner(
        sprints,
        sprint_id,
        state="submitted",
        planner_task_id="pm-current-attempt",
    )

    projection = runtime.project_planner_failure(
        sprints,
        sprint_id,
        task_id="pm-stale-attempt",
        failure_status="failed_contract_closeout",
        failure_reason="old failure",
    )

    assert projection["projected"] is False
    assert projection["reason"] == "stale_planner_attempt"
    owner = json.loads(runtime.owner_path(sprints, sprint_id).read_text(encoding="utf-8"))
    status = json.loads((sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8"))
    assert owner["planner_task_id"] == "pm-current-attempt"
    assert owner["state"] == "submitted"
    assert status["status"] == "active"


def test_retryable_capacity_failure_does_not_terminalize_sprint(tmp_path: Path) -> None:
    sprint_id = "sprint-elastic-capacity-failure"
    task_id = "pm-elastic-capacity-failure"
    sprints, _requirement, _output_root = _setup(tmp_path, sprint_id)
    runtime.update_owner(
        sprints,
        sprint_id,
        state="submitted",
        planner_task_id=task_id,
    )

    projection = runtime.project_planner_failure(
        sprints,
        sprint_id,
        task_id=task_id,
        failure_status="failed_backpressure",
        failure_reason="both bounded planner workers are busy",
    )

    owner = json.loads(runtime.owner_path(sprints, sprint_id).read_text(encoding="utf-8"))
    status = json.loads((sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8"))
    assert projection["failure"]["retryable"] is True
    assert owner["state"] == "retryable_failure"
    assert status["status"] == "active"
    assert status["phase"] == "elastic_planning"


def test_typed_retry_safe_failure_overrides_generic_pm_failed_status(tmp_path: Path) -> None:
    sprint_id = "sprint-elastic-typed-retry"
    task_id = "pm-elastic-typed-retry"
    sprints, _requirement, output_root = _setup(tmp_path, sprint_id)
    runtime.update_owner(
        sprints,
        sprint_id,
        state="submitted",
        planner_task_id=task_id,
    )
    _write(
        output_root / "planner_failure.json",
        {
            "schema_version": "solar.planner_failure.v1",
            "artifact_role": "control_plane_receipt",
            "stage": "fidelity",
            "code": "provider_quota",
            "detail": "Provider capacity was unavailable before execution.",
            "node_id": None,
            "receipt_ref": "semantic/generation-0/fidelity_call/model_call_receipt.json",
            "retry_safe": True,
            "before_execution": True,
        },
    )

    projection = runtime.project_planner_failure(
        sprints,
        sprint_id,
        task_id=task_id,
        failure_status="failed",
        failure_reason="generic PM closeout status",
    )

    owner = json.loads(runtime.owner_path(sprints, sprint_id).read_text(encoding="utf-8"))
    status = json.loads((sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8"))
    assert projection["failure"]["retryable"] is True
    assert projection["failure"]["error"]["code"] == "provider_quota"
    assert owner["state"] == "retryable_failure"
    assert status["status"] == "active"
    assert status["phase"] == "elastic_planning"


def test_failure_wins_race_and_late_success_is_rejected(tmp_path: Path) -> None:
    sprint_id = "sprint-elastic-failure-wins"
    task_id = f"pm-{sprint_id}"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    result = elastic_planner.run_elastic_planning_request(
        _requirement_ir(),
        output_root,
        ScriptedModel(decision="direct_response"),
        ScriptedModel(),
        sprint_id=sprint_id,
        catalog=_catalog(),
    )
    assert result["status"] == "direct_response"
    operator_result = _operator_result(sprint_id, requirement, output_root, "direct_response")
    runtime.update_owner(
        sprints,
        sprint_id,
        state="submitted",
        planner_task_id=task_id,
    )
    runtime.project_planner_failure(
        sprints,
        sprint_id,
        task_id=task_id,
        failure_status="failed_contract_closeout",
        failure_reason="closeout contract failed",
    )

    with pytest.raises(
        runtime.ElasticPlannerRuntimeError,
        match="^ELASTIC_PLANNER_RESULT_AFTER_FAILURE$",
    ):
        runtime.finalize_planner_result(
            sprints,
            sprint_id,
            result_path=operator_result,
        )


def test_failure_record_must_be_authoritative_and_match_task(tmp_path: Path) -> None:
    sprint_id = "sprint-elastic-failure-record-guard"
    task_id = "pm-elastic-failure-record-guard"
    sprints, _requirement, _output_root = _setup(tmp_path, sprint_id)
    runtime.update_owner(sprints, sprint_id, state="submitted", planner_task_id=task_id)
    inbox = tmp_path / "pm-inbox"
    forged = _write(
        inbox / f"{task_id}.json",
        {
            "task_id": "pm-other-task",
            "sprint_id": sprint_id,
            "closeout_kind": "elastic_planner",
            "status": "failed_contract_closeout",
        },
    )

    with pytest.raises(
        runtime.ElasticPlannerRuntimeError,
        match="^ELASTIC_PLANNER_FAILURE_RECORD_IDENTITY_MISMATCH$",
    ):
        runtime.project_planner_failure(
            sprints,
            sprint_id,
            task_id=task_id,
            failure_status="failed_contract_closeout",
            failure_reason="forged",
            record_path=forged,
            record_root=inbox,
        )


def test_accepted_result_projects_frozen_graph_and_preserves_ledger_on_repeat(tmp_path: Path) -> None:
    sprint_id = "sprint-accepted-runtime"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    result = elastic_planner.run_elastic_planning_request(
        _requirement_ir(),
        output_root,
        ScriptedModel(),
        ScriptedModel(),
        sprint_id=sprint_id,
        catalog=_catalog(),
    )
    assert result["status"] == "accepted"
    operator_result = _operator_result(sprint_id, requirement, output_root, "accepted")

    first = runtime.finalize_planner_result(sprints, sprint_id, result_path=operator_result)
    graph_path = Path(first["published"]["graph"])
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    state_path = sprints / graph["runtime_state_filename"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["revision"] = 7
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    first_status = json.loads((sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8"))

    (output_root / "finalization.json").unlink()
    second = runtime.finalize_planner_result(sprints, sprint_id, result_path=operator_result)
    second_status = json.loads((sprints / f"{sprint_id}.status.json").read_text(encoding="utf-8"))

    assert first == second
    assert graph["runtime_state_filename"] == f"{sprint_id}.task_graph_state.json"
    assert json.loads(state_path.read_text(encoding="utf-8"))["revision"] == 7
    assert second_status["history"] == first_status["history"]
    assert sum(
        row.get("event") == "elastic_planner_execution_published"
        for row in second_status["history"]
    ) == 1
    assert graph["runtime_input_bindings"]["requirement_ir.v1"]["path"] == str(requirement.resolve())


def test_finalizer_rejects_result_outside_owned_output_root(tmp_path: Path) -> None:
    sprint_id = "sprint-path-guard"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    outside = _operator_result(sprint_id, requirement, tmp_path / "outside", "direct_response")
    try:
        runtime.finalize_planner_result(sprints, sprint_id, result_path=outside)
    except runtime.ElasticPlannerRuntimeError as exc:
        assert str(exc) == "ELASTIC_PLANNER_RESULT_PATH_OUTSIDE_OUTPUT_ROOT"
    else:
        raise AssertionError("outside operator result was accepted")


def test_pm_complete_is_the_single_planner_result_publisher(tmp_path: Path, monkeypatch) -> None:
    sprint_id = "sprint-pm-closeout"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    result = elastic_planner.run_elastic_planning_request(
        _requirement_ir(),
        output_root,
        ScriptedModel(decision="direct_response"),
        ScriptedModel(),
        sprint_id=sprint_id,
        catalog=_catalog(),
    )
    assert result["status"] == "direct_response"
    operator_result = _operator_result(sprint_id, requirement, output_root, "direct_response")
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", tmp_path / "pm-inbox")
    task_id = "pm-elastic-closeout"
    pm_dispatch.write_pm_task_record(
        task_id,
        {
            "task_id": task_id,
            "sprint_id": sprint_id,
            "node_id": "elastic-planner",
            "requested_role": "elastic-planner",
            "task_type": "elastic_planning",
            "closeout_kind": "elastic_planner",
            "expected_artifacts": [str(operator_result)],
            "result_path": str(tmp_path / "pm-result.md"),
            "status": "submitted",
        },
    )

    assert pm_dispatch.cmd_complete(argparse.Namespace(task_id=task_id)) == 0
    record = pm_dispatch.read_pm_task_record(task_id)
    assert record and record["status"] == "completed"
    assert record["closeout_status"]["finalization"]["published"]["kind"] == "direct_response"
    status_path = sprints / f"{sprint_id}.status.json"
    first_status = json.loads(status_path.read_text(encoding="utf-8"))
    assert first_status["status"] == "passed"

    # Simulate a restart after PM completion/status publication but before the
    # durable finalization receipt survived. PM reconcile must restore it
    # without publishing the answer or status transition a second time.
    (output_root / "finalization.json").unlink()
    assert pm_dispatch.cmd_reconcile(
        argparse.Namespace(max_age_minutes=60, apply=True, json=True, limit=40)
    ) == 0
    second_status = json.loads(status_path.read_text(encoding="utf-8"))
    assert second_status["history"] == first_status["history"]
    assert (output_root / "finalization.json").is_file()


def test_operator_honors_real_operatord_staged_publish_contract(tmp_path: Path) -> None:
    sprint_id = "sprint-staged-operator"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    binding_harness = tmp_path / "binding-harness"
    binding_harness.mkdir()
    _write(
        sprints / f"{sprint_id}.raw_intent.json",
        {
            "schema_version": "solar.raw_intent.v1",
            "intent_id": f"intent-{sprint_id}",
            "context": {"repo": str(workspace), "cwd": str(workspace)},
            "raw": {"text": "Explain the bounded request."},
        },
    )
    _write(
        sprints / f"{sprint_id}.intent_ir.json",
        {
            "schema_version": "solar.intent_ir.v3",
            "intent_ir_id": f"intent-ir-{sprint_id}",
            "goals": [],
            "outcomes": [],
            "constraints": [],
            "ambiguities": [],
            "conflicts": [],
            "unknowns": [],
        },
    )
    workspace_binding.bind_active_workspace(binding_harness, workspace, source="test")
    authority_path = workspace_binding.freeze_sprint_workspace_authority(
        sprints,
        sprint_id,
        harness_dir=binding_harness,
    )
    result = elastic_planner.run_elastic_planning_request(
        _requirement_ir(),
        output_root,
        ScriptedModel(decision="direct_response"),
        ScriptedModel(),
        sprint_id=sprint_id,
        catalog=_catalog(),
    )
    assert result["status"] == "direct_response"
    canonical = output_root / "planner_operator_result.json"
    result_dir = tmp_path / "harness" / "run" / "operator-results" / "elastic" / "task"
    result_dir.mkdir(parents=True)
    pm_result = result_dir / "pm-result.md"
    operatord.HARNESS_DIR = tmp_path / "harness"
    operatord.SPRINTS_DIR = sprints
    exec_env = operatord._materialize_envelope_context(
        result_dir,
        {
            "task_id": "pm-staged-elastic",
            "sprint_id": sprint_id,
            "node_id": "elastic-planner",
            "task_type": "elastic_planning",
            "work_dir": str(sprints / sprint_id / "workdir"),
            "result_path": str(pm_result),
            "expected_artifacts": [str(canonical)],
        },
    )
    process_env = dict(os.environ)
    process_env.update(exec_env)
    process_env["SOLAR_WORKSPACE_BINDING_HARNESS_DIR"] = str(binding_harness)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "harness" / "tools" / "elastic_planner_operator.py"),
            "--envelope",
            exec_env["SOLAR_OPERATOR_ENVELOPE_JSON"],
        ],
        text=True,
        capture_output=True,
        env=process_env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    mapping = json.loads(exec_env["SOLAR_OPERATOR_OUTPUT_PUBLISH_MAP_JSON"])[0]
    staged = Path(mapping["write_path"])
    assert staged.stat().st_size > 0
    assert canonical.stat().st_size == 0
    assert operatord._publish_staged_outputs(exec_env) == [str(canonical)]
    published = json.loads(canonical.read_text(encoding="utf-8"))
    assert published["status"] == "direct_response"
    assert published["workspace_authority_ref"]["path"] == str(authority_path)
    assert published["workspace_authority_ref"]["workspace_root"] == str(workspace.resolve())


def test_accepted_pm_closeout_hands_verified_graph_to_dispatcher_not_generic_builder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sprint_id = "sprint-accepted-closeout"
    sprints, requirement, output_root = _setup(tmp_path, sprint_id)
    result = elastic_planner.run_elastic_planning_request(
        _requirement_ir(),
        output_root,
        ScriptedModel(),
        ScriptedModel(),
        sprint_id=sprint_id,
        catalog=_catalog(),
    )
    assert result["status"] == "accepted"
    operator_result = _operator_result(sprint_id, requirement, output_root, "accepted")
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(pm_dispatch, "PM_INBOX_DIR", tmp_path / "pm-inbox")
    dispatched: list[str] = []

    def fake_dispatch_ready(graph_path: str, **_kwargs):
        dispatched.append(str(Path(graph_path).resolve()))
        return {"ok": True, "dispatched": [{"node": "S1"}], "skipped": []}

    monkeypatch.setattr(graph_node_dispatcher, "dispatch_ready", fake_dispatch_ready)
    task_id = "pm-elastic-accepted-closeout"
    pm_dispatch.write_pm_task_record(
        task_id,
        {
            "task_id": task_id,
            "sprint_id": sprint_id,
            "node_id": "elastic-planner",
            "requested_role": "elastic-planner",
            "task_type": "elastic_planning",
            "closeout_kind": "elastic_planner",
            "expected_artifacts": [str(operator_result)],
            "result_path": str(tmp_path / "pm-result.md"),
            "status": "submitted",
        },
    )

    assert pm_dispatch.cmd_complete(argparse.Namespace(task_id=task_id)) == 0
    graph_path = sprints / f"{sprint_id}.task_graph.json"
    assert dispatched == [str(graph_path.resolve())]
    authority = runtime.frozen_scheduler_authority(sprints, sprint_id)
    assert authority["ok"] is True
    nodes, meta = pm_dispatch._builder_ready_nodes_for_sprint(sprint_id)
    assert nodes == []
    assert meta["reason"] == "frozen_scheduler_owned_by_graph_dispatcher"
    workflow_guard.SPRINTS_DIR = sprints
    route = workflow_guard.route(sprint_id)
    assert route["ok"] is True, {
        "violations": route["violations"],
        "authority": route["elastic_scheduler_authority"],
    }
    assert route["route_role"] == "builder_main"
    assert route["reason"] == "elastic_frozen_scheduler_authority_ready"
    assert route["artifacts"]["prd"] is False
    assert route["artifacts"]["design"] is False
    assert route["artifacts"]["plan"] is False

    monitor_path = ROOT / "harness" / "tools" / "solar-autopilot-monitor.py"
    spec = importlib.util.spec_from_file_location("elastic_autopilot_runtime_test", monitor_path)
    monitor = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = monitor
    spec.loader.exec_module(monitor)
    monitor.SPRINTS = sprints
    monitor.workflow_route = workflow_guard.route
    monitor._ensure_graph_status_caches = lambda: None
    monitor.epic_child_dependency_ready = lambda _sid: (True, [])
    monitor.graph_status = lambda _sid: {"valid": True, "parent_ready": False}
    findings = monitor.inspect_sprints()
    finding_types = {item["type"] for item in findings}
    assert "graph_ready_nodes" in finding_types
    assert "ready_for_builder" not in finding_types
    assert "active_without_handoff" not in finding_types

    ready_calls: list[str] = []
    monitor.no_dispatch_enabled = lambda: False
    monitor.graph_dispatch_node_evals = lambda *_args, **_kwargs: {
        "ok": True,
        "dispatched": [],
        "skipped": [],
    }
    monitor.graph_dispatch_ready = lambda graph, **_kwargs: (
        ready_calls.append(str(Path(graph).resolve()))
        or {"ok": True, "dispatched": [{"node": "S1"}], "skipped": []}
    )
    scheduler_dispatch = monitor.dispatch_ready_graph_nodes(sprint_id)
    assert scheduler_dispatch["ok"] is True
    assert ready_calls == [str(graph_path.resolve())]
