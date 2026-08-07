from __future__ import annotations

import sys
import json
import hashlib
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from random import Random

import jsonschema
import pytest


ROOT = (Path(__file__).resolve().parents[3] / 'harness')
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from research_orchestration.orchestrator import (  # noqa: E402
    ResearchOrchestrationError,
    ResearchOrchestrator,
    _path_parts_contained,
)
from research_orchestration.selection import (  # noqa: E402
    load_and_normalize_workflow,
    load_workflow_selection,
    select_research_workflow,
)
from research_orchestration.state_store import ResearchStateStore  # noqa: E402


HASH = "b" * 64


def task(
    *,
    run_id: str = "run-orch",
    workflow_kind: str = "research_synthesis",
    seed_kind: str = "topic",
    run_mode: str = "execute",
    supplied_evidence: list[dict] | None = None,
) -> dict:
    seed = {"seed_id": "seed", "seed_kind": seed_kind, "value": "offline research"}
    if seed_kind == "external_evidence":
        seed["artifact_ref"] = {
            "artifact_id": "imported",
            "path": "artifacts/imported.json",
            "provenance": {"source": "run-old", "captured_at": "2030-01-01T00:00:00Z"},
        }
    return {
        "schema": "research_task_contract.v1",
        "task_id": "task-orch",
        "run_id": run_id,
        "user_intent": "Run offline research orchestration.",
        "seed_inputs": [seed],
        "deliverable": {"kind": "research_brief", "description": "Offline brief."},
        "workflow_kind": workflow_kind,
        "run_mode": run_mode,
        "constraints": {"no_live_provider_without_approval": True, "no_secret_logging": True},
        "provider_requirements": [],
        "platform_requirements": [],
        "success_criteria": ["all required nodes accepted"],
        "supplied_evidence": supplied_evidence or [],
    }


def workflow(*, optional: bool = False) -> dict:
    nodes = [
        node("seed_fetch", []),
        node("source_discovery", ["seed_fetch"]),
        node("final_acceptance", ["source_discovery"]),
    ]
    if optional:
        nodes.append(node("optional_review", ["seed_fetch"], required=False))
    return {
        "workflow_id": "wf",
        "workflow_kind": "research_synthesis",
        "start_node": "seed_fetch",
        "nodes": nodes,
    }


def node(node_id: str, deps: list[str], *, required: bool = True) -> dict:
    return {
        "node_id": node_id,
        "depends_on": deps,
        "required_for_completion": required,
        "logical_operator": f"Logical{node_id}",
        "required_capabilities": [f"cap.{node_id}"],
        "read_scope": [f"inputs/{node_id}.json"],
        "write_scope": [f"outputs/{node_id}/"],
        "gate": f"G_{node_id.upper()}",
        "physical_operator": f"{node_id}_worker",
        "allow_network": False,
        "allow_live_provider": False,
        "timeout_seconds": 10,
        "max_attempts": 1,
    }


def result_for(request: dict, status: str = "completed", artifact_root: Path | None = None) -> dict:
    errors = []
    evidence = []
    if status == "completed":
        evidence = [
            {
                "evidence_id": f"ev-{request['node_id']}",
                "kind": "fake",
                "summary": "accepted",
                "artifact_id": f"artifact-{request['node_id']}",
            }
        ]
    if status == "failed":
        errors = [{"error_id": "err", "error_type": "FakeFailure", "message": "failed"}]
    output_artifacts = []
    if status == "completed":
        if artifact_root is None:
            raise AssertionError("completed fake result requires artifact_root")
        root = Path(artifact_root).resolve()
        node_payload = request.get("typed_inputs", {}).get("payload", {}).get("node") or {}
        declared_outputs = list(node_payload.get("expected_output_artifacts") or [])
        if node_payload.get("gate_deliverable"):
            declared_outputs.append(node_payload["gate_deliverable"])
        declared_outputs = list(dict.fromkeys(declared_outputs))
        if not declared_outputs:
            declared_outputs = [request["write_scope"][0]]
        elif request["node_id"] not in {"report_draft", "report_revision"}:
            # The generic fake intentionally emits one artifact so tests can
            # verify that missing declared outputs fail closed. Report draft
            # and report revision are production multi-output cases (JSON
            # plus usable Markdown).
            declared_outputs = declared_outputs[:1]
        for index, raw_output in enumerate(declared_outputs):
            raw_scope = str(raw_output).replace("\\", "/")
            scoped = Path(raw_scope)
            scope_path = scoped if scoped.is_absolute() else root / scoped
            artifact_path = scope_path if scope_path.suffix else scope_path / f"{request['node_id']}.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_id = f"artifact-{request['node_id']}" + (f"-{index + 1}" if index else "")
            if artifact_path.suffix.lower() == ".md":
                artifact_schema = "text/markdown"
                payload = f"# {request['node_id']} fake artifact\n".encode("utf-8")
            else:
                artifact_schema = f"{request['node_id']}.artifact.v1"
                payload = json.dumps(
                    {
                        "schema": artifact_schema,
                        "task_id": request["task_id"],
                        "run_id": request["run_id"],
                        "workflow_id": request["workflow_id"],
                        "node_id": request["node_id"],
                        "artifact_id": artifact_id,
                        "status": status,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            artifact_path.write_bytes(payload)
            try:
                declared_path = artifact_path.resolve().relative_to(root).as_posix()
            except ValueError:
                declared_path = str(artifact_path.resolve())
            output_artifacts.append(
                {
                    "artifact_id": artifact_id,
                    "path": declared_path,
                    "schema": artifact_schema,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
            if index:
                evidence.append(
                    {
                        "evidence_id": f"ev-{request['node_id']}-{index + 1}",
                        "kind": "fake",
                        "summary": "accepted",
                        "artifact_id": artifact_id,
                    }
                )
    return {
        "schema": "research_node_result.v1",
        "task_id": request["task_id"],
        "run_id": request["run_id"],
        "workflow_id": request["workflow_id"],
        "node_id": request["node_id"],
        "status": status,
        "status_is_terminal": status in {"completed", "failed", "blocked", "cancelled"},
        "output_artifacts": output_artifacts,
        "evidence": evidence,
        "hashes": [{"hash_id": "h", "algorithm": "sha256", "value": HASH}],
        "model_provider_usage": [{"provider": "none", "model": "none", "usage_kind": "none"}],
        "errors": errors,
        "limitations": [],
        "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
    }


class FakeDispatch:
    def __init__(
        self,
        statuses: dict[str, str] | None = None,
        fail_on: str | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.statuses = statuses or {}
        self.fail_on = fail_on
        self.artifact_root = artifact_root
        self.requests: list[dict] = []

    def __call__(self, request: dict) -> dict:
        self.requests.append(deepcopy(request))
        if request["node_id"] == self.fail_on:
            raise RuntimeError("boom")
        return result_for(request, self.statuses.get(request["node_id"], "completed"), self.artifact_root)


class FakeEvaluator:
    def __init__(self, decisions: dict[str, dict] | None = None) -> None:
        self.decisions = decisions or {}
        self.calls: list[tuple[dict, dict, dict]] = []

    def __call__(self, request: dict, result: dict, state: dict) -> dict:
        self.calls.append((deepcopy(request), deepcopy(result), deepcopy(state)))
        if request["node_id"] in self.decisions:
            return deepcopy(self.decisions[request["node_id"]])
        status = result["status"]
        return {
            "accepted": status == "completed",
            "status": status,
            "evidence_refs": [item["evidence_id"] for item in result.get("evidence", [])],
            "errors": result.get("errors", []),
            "limitations": result.get("limitations", []),
        }


def orchestrator(tmp_path: Path, wf: dict | None = None, **kwargs) -> tuple[ResearchOrchestrator, FakeDispatch, FakeEvaluator]:
    selected_workflow = wf or workflow()
    dispatch = kwargs.pop("dispatch", None) or FakeDispatch(artifact_root=tmp_path)
    if isinstance(dispatch, FakeDispatch) and dispatch.artifact_root is None:
        dispatch.artifact_root = tmp_path
    evaluator = kwargs.pop("evaluator", FakeEvaluator())
    if "authorization" in kwargs:
        authorization = kwargs.pop("authorization")
    else:
        authorization = {
            "approved_capabilities": sorted({
                capability
                for item in selected_workflow.get("nodes") or []
                for capability in item.get("required_capabilities") or []
            }),
            "allow_network": any(item.get("allow_network") for item in selected_workflow.get("nodes") or []),
            "allow_live_provider": False,
        }
    orch = ResearchOrchestrator(
        task_contract=kwargs.pop("task_contract", task()),
        workflow_selector=selected_workflow,
        state_store=ResearchStateStore(tmp_path / "states"),
        dispatch_callable=dispatch,
        evaluator_callable=evaluator,
        authorization=authorization,
        artifact_root=kwargs.pop("artifact_root", tmp_path),
        clock=lambda: "2030-01-01T00:00:00Z",
    )
    return orch, dispatch, evaluator


def test_url_synthesis_full_offline_fake_dispatch_flow(tmp_path: Path) -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow({"workflow_kind": "research_synthesis"}, selection, ROOT)
    wf = load_and_normalize_workflow(selected, ROOT)
    orch, dispatch, evaluator = orchestrator(
        tmp_path,
        wf,
        task_contract=task(seed_kind="url"),
        authorization={
            "approved_capabilities": sorted({cap for item in wf["nodes"] for cap in item["required_capabilities"]}),
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "approval-test-001",
        },
    )

    state = orch.run_until_blocked(max_steps=20)

    assert state["final_status"] == "completed"
    assert len(dispatch.requests) == len(wf["nodes"])
    assert len(evaluator.calls) == len(wf["nodes"])
    assert all(
        request["authorization"]["allow_network"] is True
        for request in dispatch.requests
        if request["authorization"]["allow_live_provider"]
    )


def test_topic_synthesis_flow(tmp_path: Path) -> None:
    orch, dispatch, _evaluator = orchestrator(tmp_path)

    state = orch.run_until_blocked()

    assert state["final_status"] == "completed"
    assert [request["node_id"] for request in dispatch.requests] == [
        "seed_fetch",
        "source_discovery",
        "final_acceptance",
    ]


def test_scientific_lifecycle_selection_can_run_offline_first_nodes(tmp_path: Path) -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow({"workflow_kind": "scientific_lifecycle"}, selection, ROOT)
    wf = load_and_normalize_workflow(selected, ROOT)
    wf["nodes"] = wf["nodes"][:2]
    wf["nodes"][1]["depends_on"] = [wf["nodes"][0]["node_id"]]
    orch, _dispatch, _evaluator = orchestrator(
        tmp_path,
        wf,
        task_contract=task(workflow_kind="scientific_lifecycle"),
    )

    assert orch.run_until_blocked(max_steps=5)["final_status"] == "completed"


def test_workflow_evolution_selection_runs_independent_capability(tmp_path: Path) -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow({"workflow_kind": "workflow_evolution"}, selection, ROOT)
    wf = load_and_normalize_workflow(selected, ROOT)
    orch, dispatch, _evaluator = orchestrator(
        tmp_path,
        wf,
        task_contract=task(workflow_kind="workflow_evolution"),
    )

    state = orch.run_until_blocked(max_steps=3)

    assert state["final_status"] == "completed"
    assert [request["node_id"] for request in dispatch.requests] == ["workflow_evolve"]


def test_evaluator_rejects_worker_self_reported_completed(tmp_path: Path) -> None:
    evaluator = FakeEvaluator(
        {"seed_fetch": {"accepted": False, "status": "failed", "evidence_refs": [], "errors": [{"message": "bad evidence"}], "limitations": []}}
    )
    orch, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=evaluator)

    state = orch.step()

    assert state["node_states"]["seed_fetch"]["status"] == "failed"
    assert state["final_status"] == "failed"


def test_dependency_not_satisfied_does_not_dispatch(tmp_path: Path) -> None:
    orch, dispatch, _evaluator = orchestrator(tmp_path)
    state = orch.initialize()

    assert state["ready_nodes"] == ["seed_fetch"]
    assert "source_discovery" not in state["ready_nodes"]
    assert dispatch.requests == []


@pytest.mark.parametrize("status", ["awaiting_human", "awaiting_external"])
def test_awaiting_status_stops_run_until_blocked(tmp_path: Path, status: str) -> None:
    evaluator = FakeEvaluator(
        {"seed_fetch": {"accepted": False, "status": status, "evidence_refs": [], "errors": [], "limitations": []}}
    )
    orch, dispatch, _evaluator = orchestrator(tmp_path, evaluator=evaluator)

    state = orch.run_until_blocked()

    assert state["final_status"] == status
    assert len(dispatch.requests) == 1


def test_required_node_failure_fails_run(tmp_path: Path) -> None:
    orch, _dispatch, _evaluator = orchestrator(tmp_path, dispatch=FakeDispatch({"source_discovery": "failed"}))

    state = orch.run_until_blocked()

    assert state["node_states"]["source_discovery"]["status"] == "failed"
    assert state["final_status"] == "failed"


def test_required_node_blocked_blocks_run(tmp_path: Path) -> None:
    evaluator = FakeEvaluator(
        {"source_discovery": {"accepted": False, "status": "blocked", "evidence_refs": [], "errors": [], "limitations": []}}
    )
    orch, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=evaluator)

    state = orch.run_until_blocked()

    assert state["final_status"] == "blocked"


def test_optional_node_cancellation_does_not_mask_required_nodes(tmp_path: Path) -> None:
    evaluator = FakeEvaluator(
        {"optional_review": {"accepted": False, "status": "cancelled", "evidence_refs": [], "errors": [], "limitations": []}}
    )
    orch, _dispatch, _evaluator = orchestrator(tmp_path, workflow(optional=True), evaluator=evaluator)

    state = orch.run_until_blocked(max_steps=10)

    assert state["node_states"]["optional_review"]["status"] == "cancelled"
    assert state["final_status"] == "completed"


def test_resume_after_crash_uses_persisted_state(tmp_path: Path) -> None:
    first, dispatch, _evaluator = orchestrator(tmp_path)
    first.step()
    second, _dispatch2, _evaluator2 = orchestrator(tmp_path)

    resumed = second.resume()

    assert resumed["node_states"]["seed_fetch"]["status"] == "completed"
    assert len(dispatch.requests) == 1


def test_completed_node_not_rerun_on_resume(tmp_path: Path) -> None:
    first, _dispatch, _evaluator = orchestrator(tmp_path)
    first.step()
    second_dispatch = FakeDispatch()
    second, _dispatch2, _evaluator2 = orchestrator(tmp_path, dispatch=second_dispatch)

    second.resume()
    second.run_until_blocked()

    assert [request["node_id"] for request in second_dispatch.requests] == [
        "source_discovery",
        "final_acceptance",
    ]


def test_duplicate_replayed_result_is_idempotent(tmp_path: Path) -> None:
    orch, dispatch, _evaluator = orchestrator(tmp_path)
    first = orch.run_until_blocked()
    second = orch.run_until_blocked()

    assert first == second
    assert len(dispatch.requests) == 3


def test_corrupt_state_file_is_not_overwritten(tmp_path: Path) -> None:
    orch, _dispatch, _evaluator = orchestrator(tmp_path)
    orch.initialize()
    path = tmp_path / "states" / "run-orch.research_run_state.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(Exception):
        orch.resume()
    assert path.read_text(encoding="utf-8") == "{broken"


def test_graph_cycle_fails_explicitly(tmp_path: Path) -> None:
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": [node("a", ["b"]), node("b", ["a"])]}
    orch, _dispatch, _evaluator = orchestrator(tmp_path, wf)

    state = orch.initialize()

    assert state["final_status"] == "blocked"
    assert "cycle detected" in state["current_blockers"][0]["reason"]


def test_missing_dependency_fails_explicitly(tmp_path: Path) -> None:
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": [node("a", ["missing"])]}
    orch, _dispatch, _evaluator = orchestrator(tmp_path, wf)

    state = orch.initialize()

    assert state["final_status"] == "blocked"
    assert "missing node" in state["current_blockers"][0]["reason"]


def test_max_steps_blocks_infinite_progress(tmp_path: Path) -> None:
    evaluator = FakeEvaluator(
        {"seed_fetch": {"accepted": False, "status": "awaiting_external", "evidence_refs": [], "errors": [], "limitations": []}}
    )
    orch, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=evaluator)

    state = orch.run_until_blocked(max_steps=1)

    assert state["final_status"] == "awaiting_external"


def test_max_steps_blocks_when_not_finished(tmp_path: Path) -> None:
    orch, _dispatch, _evaluator = orchestrator(tmp_path)

    state = orch.run_until_blocked(max_steps=1)

    assert state["final_status"] == "blocked"
    assert state["current_blockers"][0]["blocker_id"] == "max_steps_exceeded"


def test_execute_mode_rejects_forged_imported_evidence(tmp_path: Path) -> None:
    forged = task(seed_kind="external_evidence", supplied_evidence=[{"artifact_id": "x"}])
    orch, _dispatch, _evaluator = orchestrator(tmp_path, task_contract=forged)

    with pytest.raises(ResearchOrchestrationError, match="execute mode|frozen Phase 0 schema"):
        orch.initialize()


def test_resume_import_preserves_provenance(tmp_path: Path) -> None:
    imported = {
        "artifact_id": "imported-result",
        "path": "artifacts/imported.json",
        "provenance": {"source": "run-old", "captured_at": "2030-01-01T00:00:00Z"},
    }
    orch, _dispatch, _evaluator = orchestrator(
        tmp_path,
        task_contract=task(run_mode="resume", seed_kind="external_evidence", supplied_evidence=[imported]),
    )

    state = orch.initialize()

    assert state["resume_import_provenance"]["imported_evidence_refs"] == ["imported-result", "imported"]
    assert "run-old" in state["resume_import_provenance"]["source_run_ids"]


def test_completed_run_satisfies_phase0_run_state_schema(tmp_path: Path) -> None:
    orch, _dispatch, _evaluator = orchestrator(tmp_path)
    state = orch.run_until_blocked()
    schema = jsonschema.Draft202012Validator(
        __import__("json").loads((ROOT / "schemas/evidence/research_run_state.v1.schema.json").read_text(encoding="utf-8"))
    )

    schema.validate(state)
    assert state["final_status"] == "completed"
    assert state["current_blockers"] == []
    assert state["final_status_evidence_refs"]


def test_dispatch_exception_is_normalized_through_evaluator(tmp_path: Path) -> None:
    orch, _dispatch, evaluator = orchestrator(tmp_path, dispatch=FakeDispatch(fail_on="seed_fetch"))

    state = orch.step()

    assert state["final_status"] == "failed"
    assert evaluator.calls[0][1]["errors"][0]["error_id"] == "dispatch_exception"


def test_malformed_evaluator_response_is_rejected(tmp_path: Path) -> None:
    class BadEvaluator:
        def __call__(self, request: dict, result: dict, state: dict) -> dict:
            return {"accepted": True, "status": "green", "evidence_refs": []}

    orch, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=BadEvaluator())

    state = orch.step()

    assert state["final_status"] == "failed"
    assert "invalid status" in state["current_blockers"][0]["reason"]


def test_string_accepted_flag_cannot_green_a_worker_result(tmp_path: Path) -> None:
    class StringBooleanEvaluator:
        def __call__(self, request: dict, result: dict, state: dict) -> dict:
            return {"accepted": "false", "status": "completed", "evidence_refs": ["fake-green"]}

    orch, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=StringBooleanEvaluator())

    state = orch.step()

    assert state["final_status"] == "failed"
    assert "must be boolean" in state["current_blockers"][0]["reason"]


def test_scoped_node_request_matches_contract_schema(tmp_path: Path) -> None:
    orch, dispatch, _evaluator = orchestrator(tmp_path)
    request_schema = __import__("json").loads(
        (ROOT / "schemas/draft/research_node_request.v1.schema.json").read_text(encoding="utf-8")
    )

    orch.step()

    jsonschema.Draft202012Validator(request_schema).validate(dispatch.requests[0])


def test_random_dag_readiness_matches_completed_dependencies(tmp_path: Path) -> None:
    rng = Random(7)
    nodes = []
    for index in range(12):
        deps = [f"n{earlier}" for earlier in range(index) if rng.choice([True, False, False])]
        nodes.append(node(f"n{index}", deps))
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": nodes}
    orch, _dispatch, _evaluator = orchestrator(tmp_path, wf)

    state = orch.initialize()
    ready = set(state["ready_nodes"])

    expected = {item["node_id"] for item in nodes if not item["depends_on"]}
    assert ready == expected


def test_repeated_resume_is_deterministic(tmp_path: Path) -> None:
    orch, _dispatch, _evaluator = orchestrator(tmp_path)
    orch.step()

    first, _dispatch1, _evaluator1 = orchestrator(tmp_path)
    second, _dispatch2, _evaluator2 = orchestrator(tmp_path)

    assert first.resume() == second.resume()


def test_live_provider_never_fabricates_approval_and_stops_before_dispatch(tmp_path: Path) -> None:
    live_node = node("provider_node", [])
    live_node["allow_live_provider"] = True
    live_node["allow_network"] = True
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": [live_node]}
    orch, dispatch, _evaluator = orchestrator(tmp_path, wf)

    state = orch.run_until_blocked()

    assert state["final_status"] == "awaiting_external"
    assert state["node_states"]["provider_node"]["status"] == "awaiting_external"
    assert dispatch.requests == []
    persisted = json.dumps(state)
    assert "approved-by-task-contract" not in persisted
    assert state["current_blockers"][0]["blocker_id"] == "provider_node_authorization_required"
    run_schema = json.loads((ROOT / "schemas/evidence/research_run_state.v1.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(run_schema).validate(state)


def test_task_contract_rejects_nested_secret_value_before_state_or_dispatch(tmp_path: Path) -> None:
    compromised = task()
    compromised["constraints"]["api_key"] = "s" + "k-live-CONTRACTCANARY123"
    orch, dispatch, _evaluator = orchestrator(tmp_path, task_contract=compromised)

    with pytest.raises(ResearchOrchestrationError, match="secret references"):
        orch.initialize()

    assert dispatch.requests == []
    assert orch.state_store.load("run-orch") is None


def test_authorization_rejects_secret_value_disguised_as_secret_ref(tmp_path: Path) -> None:
    with pytest.raises(ResearchOrchestrationError, match="names, not secret values"):
        orchestrator(tmp_path, authorization={"secret_refs": ["s" + "k-live-REFCANARY12345"]})


def test_explicit_authorization_resumes_provider_node_after_restart(tmp_path: Path) -> None:
    live_node = node("provider_node", [])
    live_node["allow_live_provider"] = True
    live_node["allow_network"] = True
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": [live_node]}
    first, _dispatch, _evaluator = orchestrator(tmp_path, wf)
    assert first.run_until_blocked()["final_status"] == "awaiting_external"

    second_dispatch = FakeDispatch()
    second, _ignored, _evaluator2 = orchestrator(
        tmp_path,
        wf,
        dispatch=second_dispatch,
        authorization={
            "approved_capabilities": ["cap.provider_node"],
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "approval-user-042",
        },
    )
    state = second.resume(redispatch_node_id="provider_node")

    assert state["final_status"] == "completed"
    assert len(second_dispatch.requests) == 1
    assert second_dispatch.requests[0]["authorization"]["approval_ref"] == "approval-user-042"
    assert "approved-by-task-contract" not in json.dumps(second_dispatch.requests[0])


def test_explicit_human_approval_resumes_approval_gate_after_restart(tmp_path: Path) -> None:
    gate = node("experiment_approval_gate", [])
    gate["approval_gate"] = True
    gate["required_capabilities"] = ["execute_experiment"]
    wf = {
        "workflow_id": "experiment-gate-wf",
        "workflow_kind": "scientific_lifecycle",
        "nodes": [gate],
    }
    first, first_dispatch, _evaluator = orchestrator(
        tmp_path,
        wf,
        authorization={"approved_capabilities": []},
    )

    waiting = first.run_until_blocked()

    assert waiting["final_status"] == "awaiting_human"
    assert waiting["node_states"]["experiment_approval_gate"]["status"] == "awaiting_human"
    assert first_dispatch.requests == []

    second_dispatch = FakeDispatch(artifact_root=tmp_path)
    second, _ignored, _evaluator2 = orchestrator(
        tmp_path,
        wf,
        dispatch=second_dispatch,
        authorization={
            "approved_capabilities": ["execute_experiment"],
            "approval_ref": "approval-human-001",
        },
    )
    resumed = second.resume(redispatch_node_id="experiment_approval_gate")

    assert resumed["final_status"] == "completed"
    assert second_dispatch.requests[0]["authorization"] == {
        "scope_id": "run-orch:experiment_approval_gate",
        "approved_capabilities": ["execute_experiment"],
        "allow_network": False,
        "allow_live_provider": False,
        "secret_refs": [],
        "approval_ref": "approval-human-001",
    }


def test_plain_resume_does_not_relabel_awaiting_node(tmp_path: Path) -> None:
    evaluator = FakeEvaluator(
        {"seed_fetch": {"accepted": False, "status": "awaiting_external", "evidence_refs": ["receipt"], "errors": [], "limitations": []}}
    )
    first, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=evaluator)
    waiting = first.run_until_blocked()

    second, second_dispatch, _evaluator2 = orchestrator(tmp_path)
    resumed = second.resume()

    assert resumed == waiting
    assert resumed["node_states"]["seed_fetch"]["status"] == "awaiting_external"
    assert second_dispatch.requests == []


def test_imported_terminal_result_advances_persisted_awaiting_node(tmp_path: Path) -> None:
    dispatch = FakeDispatch({"seed_fetch": "awaiting_external"})
    first, _ignored, _evaluator = orchestrator(tmp_path, dispatch=dispatch)
    assert first.run_until_blocked()["final_status"] == "awaiting_external"
    completed = result_for(dispatch.requests[0], artifact_root=tmp_path)

    second, _dispatch2, _evaluator2 = orchestrator(tmp_path)
    resumed = second.resume(node_result=completed)

    assert resumed["node_states"]["seed_fetch"]["status"] == "completed"
    assert resumed["ready_nodes"] == ["source_discovery"]
    result_ref = resumed["node_states"]["seed_fetch"]["result_ref"]
    assert Path(result_ref).is_file()
    record = second.state_store.load_node_record(result_ref)
    assert record["evaluation"]["evidence_refs"] == ["ev-seed_fetch"]
    assert record["result"]["output_artifacts"][0]["artifact_id"] == "artifact-seed_fetch"
    run_schema = json.loads((ROOT / "schemas/evidence/research_run_state.v1.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(run_schema).validate(resumed)


@pytest.mark.parametrize("identity_field", ["task_id", "run_id", "workflow_id", "node_id"])
def test_resume_rejects_mismatched_result_identity(tmp_path: Path, identity_field: str) -> None:
    dispatch = FakeDispatch({"seed_fetch": "awaiting_external"})
    first, _ignored, _evaluator = orchestrator(tmp_path, dispatch=dispatch)
    waiting = first.run_until_blocked()
    mismatched = result_for(dispatch.requests[0], artifact_root=tmp_path)
    mismatched[identity_field] = "wrong-identity"

    second, _dispatch2, _evaluator2 = orchestrator(tmp_path)
    with pytest.raises(ResearchOrchestrationError, match="does not match|does not target"):
        second.resume(node_result=mismatched)

    assert second.state_store.load("run-orch") == waiting


def test_failed_worker_result_cannot_be_promoted_by_evaluator(tmp_path: Path) -> None:
    class UnsafeEvaluator:
        def __call__(self, request: dict, result: dict, state: dict) -> dict:
            return {"accepted": True, "status": "completed", "evidence_refs": ["fake-green"]}

    orch, _dispatch, _evaluator = orchestrator(
        tmp_path,
        dispatch=FakeDispatch({"seed_fetch": "failed"}),
        evaluator=UnsafeEvaluator(),
    )

    state = orch.step()

    assert state["node_states"]["seed_fetch"]["status"] == "failed"
    assert state["final_status"] == "failed"
    record = orch.state_store.load_node_record(state["node_states"]["seed_fetch"]["result_ref"])
    assert record["evaluation"]["accepted"] is False
    assert "fake-green" not in record["evaluation"]["evidence_refs"]


def test_malformed_worker_result_is_normalized_to_failed_evidence(tmp_path: Path) -> None:
    class MalformedDispatch:
        def __call__(self, request: dict) -> dict:
            return {"schema": "research_node_result.v1", "node_id": request["node_id"], "status": "completed"}

    orch, _dispatch, _evaluator = orchestrator(tmp_path, dispatch=MalformedDispatch())

    state = orch.step()

    assert state["final_status"] == "failed"
    record = orch.state_store.load_node_record(state["node_states"]["seed_fetch"]["result_ref"])
    assert record["result"]["status"] == "failed"
    assert record["result"]["errors"][0]["error_id"] == "dispatch_exception"


def test_nested_secret_canary_is_scrubbed_before_state_or_record_persistence(tmp_path: Path) -> None:
    canary = "s" + "k-live-NESTEDCANARY123456"

    class SecretDispatch:
        def __call__(self, request: dict) -> dict:
            raise RuntimeError({"outer": {"api_key": canary}, "authorization": f"Bearer {canary}"})

    orch, _dispatch, _evaluator = orchestrator(tmp_path, dispatch=SecretDispatch())
    state = orch.step()
    record_path = Path(state["node_states"]["seed_fetch"]["result_ref"])

    persisted = json.dumps(state) + record_path.read_text(encoding="utf-8")
    assert canary not in persisted
    assert "[REDACTED]" in persisted
    record = orch.state_store.load_node_record(str(record_path))
    assert record["result"]["secret_redaction_assertion"] == {
        "no_secrets_observed": True,
        "redaction_review": "passed",
    }


def test_nested_secret_in_worker_evidence_is_redacted_before_acceptance(tmp_path: Path) -> None:
    canary = "s" + "k-live-EVIDENCECANARY123"

    class LeakyCompletedDispatch:
        def __call__(self, request: dict) -> dict:
            result = result_for(request, artifact_root=tmp_path)
            result["evidence"][0]["debug"] = {"api_key": canary}
            return result

    orch, _dispatch, _evaluator = orchestrator(tmp_path, dispatch=LeakyCompletedDispatch())
    state = orch.step()
    record_path = Path(state["node_states"]["seed_fetch"]["result_ref"])

    assert state["node_states"]["seed_fetch"]["status"] == "completed"
    persisted = record_path.read_text(encoding="utf-8")
    assert canary not in persisted
    assert '"api_key": "[REDACTED]"' in persisted


def test_evaluator_exception_secret_is_scrubbed_before_persistence(tmp_path: Path) -> None:
    canary = "s" + "k-evaluator-CANARY123456"

    class SecretEvaluator:
        def __call__(self, request: dict, result: dict, state: dict) -> dict:
            raise RuntimeError({"password": canary})

    orch, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=SecretEvaluator())
    state = orch.step()
    record_path = Path(state["node_states"]["seed_fetch"]["result_ref"])

    persisted = json.dumps(state) + record_path.read_text(encoding="utf-8")
    assert canary not in persisted
    assert state["final_status"] == "failed"


def test_research_chain_receives_real_schema_discoverable_upstream_artifacts(tmp_path: Path) -> None:
    chain = [
        ("seed_fetch", [], []),
        ("source_discovery", ["seed_fetch"], ["seed_snapshot.v1"]),
        ("source_validation", ["source_discovery"], ["source_discovery.v1"]),
        ("evidence_synthesis", ["seed_fetch", "source_validation"], ["seed_snapshot.v1", "source_validation.v1"]),
        ("report_draft", ["evidence_synthesis"], ["evidence_synthesis.v1"]),
        ("independent_review", ["report_draft", "source_validation"], ["source_validation.v1", "report_draft.v1"]),
        ("report_revision", ["independent_review", "report_draft", "evidence_synthesis", "source_validation"], ["source_validation.v1", "evidence_synthesis.v1", "report_draft.v1", "independent_review.v1"]),
        ("final_acceptance", ["report_revision"], ["source_validation.v1", "evidence_synthesis.v1", "report_draft.v1", "independent_review.v1", "report_revision.v1"]),
    ]
    schemas = {
        "seed_fetch": "seed_snapshot.v1",
        "source_discovery": "source_discovery.v1",
        "source_validation": "source_validation.v1",
        "evidence_synthesis": "evidence_synthesis.v1",
        "report_draft": "report_draft.v1",
        "independent_review": "independent_review.v1",
        "report_revision": "report_revision.v1",
        "final_acceptance": "final_acceptance.v1",
    }
    paths = {node_id: str((tmp_path / "artifacts" / f"{node_id}.json").resolve()) for node_id in schemas}
    nodes = []
    for node_id, deps, expected_schemas in chain:
        item = node(node_id, deps)
        item["read_scope"] = [paths[upstream] for upstream in schemas if schemas[upstream] in expected_schemas]
        item["write_scope"] = [str((tmp_path / "artifacts").resolve()) + "/"]
        nodes.append(item)
    wf = {"workflow_id": "seven", "workflow_kind": "research_synthesis", "nodes": nodes}

    class SchemaDiscoveringPhysicalChain:
        def __init__(self) -> None:
            self.requests: list[dict] = []

        def __call__(self, request: dict) -> dict:
            self.requests.append(deepcopy(request))
            node_id = request["node_id"]
            expected = next(row[2] for row in chain if row[0] == node_id)
            received = request["input_artifact_refs"]
            assert [artifact.get("schema") for artifact in received] == expected
            for artifact in received:
                assert artifact["artifact_id"].startswith("real-")
                assert ":input:" not in artifact["artifact_id"]
            Path(paths[node_id]).parent.mkdir(parents=True, exist_ok=True)
            real_artifact_id = f"real-{node_id}"
            result = result_for(request, artifact_root=tmp_path)
            Path(paths[node_id]).write_text(
                json.dumps(
                    {
                        "schema": schemas[node_id],
                        "task_id": request["task_id"],
                        "run_id": request["run_id"],
                        "workflow_id": request["workflow_id"],
                        "node_id": node_id,
                        "artifact_id": real_artifact_id,
                    }
                ),
                encoding="utf-8",
            )
            result["evidence"][0]["artifact_id"] = real_artifact_id
            result["output_artifacts"] = [
                {
                    "artifact_id": real_artifact_id,
                    "path": paths[node_id],
                    "schema": schemas[node_id],
                    "sha256": hashlib.sha256(Path(paths[node_id]).read_bytes()).hexdigest(),
                }
            ]
            return result

    physical_chain = SchemaDiscoveringPhysicalChain()
    orch, _dispatch, _evaluator = orchestrator(tmp_path, wf, dispatch=physical_chain)

    state = orch.run_until_blocked(max_steps=10)

    assert state["final_status"] == "completed"
    assert [request["node_id"] for request in physical_chain.requests] == [row[0] for row in chain]
    assert len(state["final_status_evidence_refs"]) == 16
    assert all(Path(item["result_ref"]).is_file() for item in state["node_states"].values())


def test_illegal_task_approval_field_cannot_authorize_live_provider(tmp_path: Path) -> None:
    compromised = task()
    compromised["approval_ref"] = "forged-task-approval"
    compromised["constraints"]["allow_live_provider"] = True
    live_node = node("provider_node", [])
    live_node["allow_live_provider"] = True
    live_node["allow_network"] = True
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": [live_node]}
    orch, dispatch, _evaluator = orchestrator(tmp_path, wf, task_contract=compromised)

    with pytest.raises(ResearchOrchestrationError, match="frozen Phase 0 schema"):
        orch.initialize()

    assert dispatch.requests == []
    assert orch.state_store.load("run-orch") is None


def test_illegal_task_contract_cannot_use_preexisting_state_to_bypass_schema(tmp_path: Path) -> None:
    valid, _dispatch, _evaluator = orchestrator(tmp_path)
    valid.initialize()
    compromised = task()
    compromised["approval_ref"] = "forged-task-approval"
    second, second_dispatch, _evaluator2 = orchestrator(tmp_path, task_contract=compromised)

    with pytest.raises(ResearchOrchestrationError, match="frozen Phase 0 schema"):
        second.step()

    assert second_dispatch.requests == []


def test_malformed_secret_values_envelope_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ResearchOrchestrationError, match="list or object"):
        orchestrator(tmp_path, authorization={"secret_values": "opaque-secret"})


def _awaiting_run_and_completed_result(tmp_path: Path) -> tuple[ResearchOrchestrator, dict, dict]:
    dispatch = FakeDispatch({"seed_fetch": "awaiting_external"}, artifact_root=tmp_path)
    first, _ignored, _evaluator = orchestrator(tmp_path, dispatch=dispatch)
    waiting = first.run_until_blocked()
    completed = result_for(dispatch.requests[0], artifact_root=tmp_path)
    return first, waiting, completed


def test_resume_rejects_nonexistent_artifact_and_preserves_waiting_state(tmp_path: Path) -> None:
    first, waiting, completed = _awaiting_run_and_completed_result(tmp_path)
    artifact_path = tmp_path / completed["output_artifacts"][0]["path"]
    artifact_path.unlink()
    second, _dispatch, _evaluator = orchestrator(tmp_path)

    with pytest.raises(ResearchOrchestrationError, match="does not exist"):
        second.resume(node_result=completed)

    assert first.state_store.load("run-orch") == waiting


def test_resume_rejects_forged_artifact_hash_and_preserves_waiting_state(tmp_path: Path) -> None:
    first, waiting, completed = _awaiting_run_and_completed_result(tmp_path)
    completed["output_artifacts"][0]["sha256"] = "c" * 64
    second, _dispatch, _evaluator = orchestrator(tmp_path)

    with pytest.raises(ResearchOrchestrationError, match="does not match"):
        second.resume(node_result=completed)

    assert first.state_store.load("run-orch") == waiting


def test_resume_rejects_artifact_outside_write_scope(tmp_path: Path) -> None:
    first, waiting, completed = _awaiting_run_and_completed_result(tmp_path)
    outside_scope = tmp_path / "other-scope" / "artifact.json"
    outside_scope.parent.mkdir()
    outside_scope.write_text("outside declared write scope", encoding="utf-8")
    completed["output_artifacts"][0]["path"] = outside_scope.relative_to(tmp_path).as_posix()
    completed["output_artifacts"][0]["sha256"] = hashlib.sha256(outside_scope.read_bytes()).hexdigest()
    second, _dispatch, _evaluator = orchestrator(tmp_path)

    with pytest.raises(ResearchOrchestrationError, match="write_scope"):
        second.resume(node_result=completed)

    assert first.state_store.load("run-orch") == waiting


def test_resume_rejects_artifact_outside_workspace_root(tmp_path: Path) -> None:
    first, waiting, completed = _awaiting_run_and_completed_result(tmp_path)
    outside_root = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside_root.write_text("outside artifact root", encoding="utf-8")
    completed["output_artifacts"][0]["path"] = str(outside_root.resolve())
    completed["output_artifacts"][0]["sha256"] = hashlib.sha256(outside_root.read_bytes()).hexdigest()
    second, _dispatch, _evaluator = orchestrator(tmp_path)

    try:
        with pytest.raises(ResearchOrchestrationError, match="artifact_root|write_scope"):
            second.resume(node_result=completed)
    finally:
        outside_root.unlink(missing_ok=True)

    assert first.state_store.load("run-orch") == waiting


def test_resume_rejects_junction_or_symlink_escape(tmp_path: Path) -> None:
    first, waiting, completed = _awaiting_run_and_completed_result(tmp_path)
    target = tmp_path.parent / f"{tmp_path.name}-junction-target"
    target.mkdir()
    target_file = target / "artifact.json"
    target_file.write_text("junction escape", encoding="utf-8")
    link = tmp_path / "outputs" / "seed_fetch" / "linked"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            if created.returncode != 0:
                pytest.skip(f"junction creation unavailable: {created.stderr or created.stdout}")
        else:
            link.symlink_to(target, target_is_directory=True)
        escaped = link / "artifact.json"
        completed["output_artifacts"][0]["path"] = escaped.relative_to(tmp_path).as_posix()
        completed["output_artifacts"][0]["sha256"] = hashlib.sha256(target_file.read_bytes()).hexdigest()
        second, _dispatch, _evaluator = orchestrator(tmp_path)

        with pytest.raises(ResearchOrchestrationError, match="artifact_root|write_scope"):
            second.resume(node_result=completed)
    finally:
        if link.exists():
            if os.name == "nt":
                os.rmdir(link)
            else:
                link.unlink()
        target_file.unlink(missing_ok=True)
        target.rmdir()

    assert first.state_store.load("run-orch") == waiting


@pytest.mark.parametrize("failure_kind", ["missing", "forged_hash", "outside_scope"])
def test_normal_dispatch_cannot_commit_unverified_completed_artifact(tmp_path: Path, failure_kind: str) -> None:
    class UnvalidatedDispatch:
        def __call__(self, request: dict) -> dict:
            result = result_for(request, artifact_root=tmp_path)
            artifact = result["output_artifacts"][0]
            path = tmp_path / artifact["path"]
            if failure_kind == "missing":
                path.unlink()
            elif failure_kind == "forged_hash":
                artifact["sha256"] = "d" * 64
            else:
                escaped = tmp_path / "different-scope" / "artifact.json"
                escaped.parent.mkdir()
                escaped.write_text("different scope", encoding="utf-8")
                artifact["path"] = escaped.relative_to(tmp_path).as_posix()
                artifact["sha256"] = hashlib.sha256(escaped.read_bytes()).hexdigest()
            return result

    orch, _dispatch, _evaluator = orchestrator(tmp_path, dispatch=UnvalidatedDispatch())
    state = orch.step()

    assert state["final_status"] == "failed"
    record = orch.state_store.load_node_record(state["node_states"]["seed_fetch"]["result_ref"])
    assert record["result"]["status"] == "failed"
    assert record["result"]["output_artifacts"] == []


@pytest.mark.parametrize(
    ("identity_case", "expected_status"),
    [
        ("only_task_id", "failed"),
        ("only_schema", "failed"),
        ("all_except_node", "failed"),
        ("complete_valid", "completed"),
    ],
)
def test_json_artifact_requires_complete_embedded_identity(
    tmp_path: Path,
    identity_case: str,
    expected_status: str,
) -> None:
    identity_node = node("identity_node", [])
    identity_node["write_scope"] = ["artifacts/identity/"]
    wf = {"workflow_id": "identity-wf", "workflow_kind": "research_synthesis", "nodes": [identity_node]}

    class PartialIdentityDispatch:
        def __call__(self, request: dict) -> dict:
            result = result_for(request, artifact_root=tmp_path)
            artifact = result["output_artifacts"][0]
            complete = {
                "schema": artifact["schema"],
                "task_id": request["task_id"],
                "run_id": request["run_id"],
                "workflow_id": request["workflow_id"],
                "node_id": request["node_id"],
                "artifact_id": artifact["artifact_id"],
            }
            if identity_case == "only_task_id":
                embedded = {"task_id": complete["task_id"]}
            elif identity_case == "only_schema":
                embedded = {"schema": complete["schema"]}
            elif identity_case == "all_except_node":
                embedded = {key: value for key, value in complete.items() if key != "node_id"}
            else:
                embedded = complete
            path = tmp_path / artifact["path"]
            path.write_text(json.dumps(embedded), encoding="utf-8")
            artifact["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            return result

    orch, _dispatch, _evaluator = orchestrator(tmp_path, wf, dispatch=PartialIdentityDispatch())

    state = orch.step()

    assert state["node_states"]["identity_node"]["status"] == expected_status
    assert state["final_status"] == expected_status


def test_opaque_authorized_secret_is_never_persisted_or_sent_to_worker(tmp_path: Path) -> None:
    opaque = "opaque-value-that-has-no-provider-prefix-94721"

    class OpaqueDispatch(FakeDispatch):
        def __call__(self, request: dict) -> dict:
            result = super().__call__(request)
            result["evidence"][0]["opaque_debug"] = opaque
            return result

    class OpaqueEvaluator(FakeEvaluator):
        def __call__(self, request: dict, result: dict, state: dict) -> dict:
            decision = super().__call__(request, result, state)
            decision["limitations"] = [f"opaque evaluator content: {opaque}"]
            return decision

    dispatch = OpaqueDispatch(artifact_root=tmp_path)
    orch, _ignored, _evaluator = orchestrator(
        tmp_path,
        dispatch=dispatch,
        evaluator=OpaqueEvaluator(),
        authorization={
            "approved_capabilities": ["cap.seed_fetch"],
            "secret_refs": ["OPAQUE_TEST_SECRET"],
            "secret_values": [opaque],
        },
    )
    state = orch.step()
    record_path = Path(state["node_states"]["seed_fetch"]["result_ref"])

    assert state["node_states"]["seed_fetch"]["status"] == "completed"
    assert opaque not in json.dumps(dispatch.requests)
    assert opaque not in json.dumps(state)
    assert opaque not in record_path.read_text(encoding="utf-8")
    record = orch.state_store.load_node_record(str(record_path))
    assert record["result"]["secret_redaction_assertion"] == {
        "no_secrets_observed": True,
        "redaction_review": "passed",
    }
    assert "[REDACTED]" in json.dumps(record)


@pytest.mark.parametrize(
    ("authorization", "expected_reason"),
    [
        ({"approved_capabilities": [], "allow_network": False}, "required capabilities"),
        ({"approved_capabilities": ["cap.network_node"], "allow_network": False}, "requires network"),
        (
            {
                "approved_capabilities": ["cap.network_node"],
                "allow_network": False,
                "allow_live_provider": True,
                "approval_ref": "approval-without-network",
            },
            "requires network",
        ),
    ],
)
def test_authorization_envelope_is_upper_bound_and_denial_never_dispatches(
    tmp_path: Path,
    authorization: dict,
    expected_reason: str,
) -> None:
    restricted = node("network_node", [])
    restricted["allow_network"] = True
    restricted["allow_live_provider"] = True
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": [restricted]}
    orch, dispatch, _evaluator = orchestrator(tmp_path, wf, authorization=authorization)

    state = orch.run_until_blocked()

    assert state["final_status"] == "awaiting_external"
    assert dispatch.requests == []
    assert expected_reason in state["current_blockers"][0]["reason"]


def test_node_request_permissions_are_intersection_not_union(tmp_path: Path) -> None:
    offline = node("offline_node", [])
    wf = {"workflow_id": "wf", "workflow_kind": "research_synthesis", "nodes": [offline]}
    orch, dispatch, _evaluator = orchestrator(
        tmp_path,
        wf,
        authorization={
            "approved_capabilities": ["cap.offline_node", "cap.unrelated"],
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "approval-extra-permissions",
        },
    )

    assert orch.step()["final_status"] == "completed"
    request = dispatch.requests[0]
    assert request["authorization"]["approved_capabilities"] == ["cap.offline_node"]
    assert request["authorization"]["allow_network"] is False
    assert request["authorization"]["allow_live_provider"] is False
    assert "approval_ref" not in request["authorization"]


def test_normal_dispatch_completed_empty_outputs_fails_closed(tmp_path: Path) -> None:
    class EmptyOutputDispatch:
        def __call__(self, request: dict) -> dict:
            result = result_for(request, artifact_root=tmp_path)
            result["output_artifacts"] = []
            return result

    orch, _dispatch, _evaluator = orchestrator(tmp_path, dispatch=EmptyOutputDispatch())
    state = orch.step()

    assert state["final_status"] == "failed"
    record = orch.state_store.load_node_record(state["node_states"]["seed_fetch"]["result_ref"])
    assert record["result"]["status"] == "failed"
    assert "must produce an artifact" in record["result"]["errors"][0]["message"]


def test_resume_completed_empty_outputs_fails_closed_and_preserves_waiting_state(tmp_path: Path) -> None:
    first, waiting, completed = _awaiting_run_and_completed_result(tmp_path)
    completed["output_artifacts"] = []
    second, _dispatch, _evaluator = orchestrator(tmp_path)

    with pytest.raises(ResearchOrchestrationError, match="must produce an artifact"):
        second.resume(node_result=completed)

    assert first.state_store.load("run-orch") == waiting


def test_evaluator_must_accept_artifact_linked_evidence(tmp_path: Path) -> None:
    class UnlinkedEvaluator:
        def __call__(self, request: dict, result: dict, state: dict) -> dict:
            return {
                "accepted": True,
                "status": "completed",
                "evidence_refs": ["unrelated-evidence"],
                "errors": [],
                "limitations": [],
            }

    orch, _dispatch, _evaluator = orchestrator(tmp_path, evaluator=UnlinkedEvaluator())
    state = orch.step()

    assert state["final_status"] == "failed"
    assert "linked to every artifact" in state["current_blockers"][0]["reason"]


def test_every_workflow_declared_output_must_be_produced(tmp_path: Path) -> None:
    multi = node("multi_output", [])
    multi["write_scope"] = ["artifacts/multi/"]
    multi["expected_output_artifacts"] = [
        "artifacts/multi/first.json",
        "artifacts/multi/second.json",
    ]
    wf = {"workflow_id": "multi-wf", "workflow_kind": "research_synthesis", "nodes": [multi]}

    orch, _dispatch, _evaluator = orchestrator(tmp_path, wf)
    state = orch.step()

    assert state["final_status"] == "failed"
    assert "was not produced" in state["current_blockers"][0]["reason"]


def test_tampered_node_record_blocks_downstream_with_diagnostic(tmp_path: Path) -> None:
    first, _dispatch, _evaluator = orchestrator(tmp_path)
    state = first.step()
    record_path = Path(state["node_states"]["seed_fetch"]["result_ref"])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["evaluation"]["limitations"] = ["tampered"]
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    second, second_dispatch, _evaluator2 = orchestrator(tmp_path)
    blocked = second.step()

    assert blocked["final_status"] == "blocked"
    assert second_dispatch.requests == []
    assert "digest" in blocked["current_blockers"][0]["reason"]


def test_foreign_identity_node_record_blocks_downstream(tmp_path: Path) -> None:
    first, _dispatch, _evaluator = orchestrator(tmp_path)
    state = first.step()
    original = first.state_store.load_node_record(state["node_states"]["seed_fetch"]["result_ref"])
    foreign_ref = first.state_store.store_node_record(
        run_id="foreign-run",
        node_id="seed_fetch",
        result=original["result"],
        evaluation=original["evaluation"],
    )
    state["node_states"]["seed_fetch"]["result_ref"] = foreign_ref
    first.state_store.save(state)

    second, second_dispatch, _evaluator2 = orchestrator(tmp_path)
    blocked = second.step()

    assert blocked["final_status"] == "blocked"
    assert second_dispatch.requests == []
    assert "run_id does not match" in blocked["current_blockers"][0]["reason"]


def test_mutated_accepted_artifact_blocks_before_upstream_propagation(tmp_path: Path) -> None:
    first, _dispatch, _evaluator = orchestrator(tmp_path)
    state = first.step()
    record = first.state_store.load_node_record(state["node_states"]["seed_fetch"]["result_ref"])
    artifact = record["result"]["output_artifacts"][0]
    artifact_path = tmp_path / artifact["path"]
    artifact_path.write_text("mutated after acceptance", encoding="utf-8")

    second, second_dispatch, _evaluator2 = orchestrator(tmp_path)
    blocked = second.step()

    assert blocked["final_status"] == "blocked"
    assert second_dispatch.requests == []
    assert "sha256" in blocked["current_blockers"][0]["reason"]


def test_artifact_root_has_no_cwd_fallback(tmp_path: Path) -> None:
    class UnrootedStateStore:
        pass

    with pytest.raises(ResearchOrchestrationError, match="artifact_root must be explicit"):
        ResearchOrchestrator(
            task_contract=task(),
            workflow_selector=workflow(),
            state_store=UnrootedStateStore(),
            dispatch_callable=FakeDispatch(artifact_root=tmp_path),
            evaluator_callable=FakeEvaluator(),
        )
    with pytest.raises(ResearchOrchestrationError, match="non-empty stable path"):
        ResearchOrchestrator(
            task_contract=task(),
            workflow_selector=workflow(),
            state_store=ResearchStateStore(tmp_path / "states"),
            dispatch_callable=FakeDispatch(artifact_root=tmp_path),
            evaluator_callable=FakeEvaluator(),
            artifact_root="",
        )


def test_pure_containment_proof_respects_case_sensitivity() -> None:
    assert _path_parts_contained("/workspace/report.json", "/workspace", case_sensitive=True)
    assert not _path_parts_contained("/Workspace/report.json", "/workspace", case_sensitive=True)
    assert _path_parts_contained("C:/Workspace/report.json", "c:/workspace", case_sensitive=False)


def test_foreign_flavor_absolute_path_is_rejected(tmp_path: Path) -> None:
    orch, _dispatch, _evaluator = orchestrator(tmp_path)
    foreign = "/etc/passwd" if os.name == "nt" else "C:/Windows/System32/config/SAM"

    with pytest.raises(ResearchOrchestrationError, match="foreign"):
        orch._resolve_scoped_path(foreign, must_exist=False)
    with pytest.raises(ResearchOrchestrationError, match="drive-relative"):
        orch._resolve_scoped_path("C:relative-artifact.json", must_exist=False)


@pytest.mark.parametrize(
    "semantic_defect",
    ["wrong_expected_path", "missing_evidence_link", "wrong_embedded_node", "wrong_embedded_schema", "arbitrary_json"],
)
def test_hash_consistent_but_semantically_wrong_artifact_fails_closed(
    tmp_path: Path,
    semantic_defect: str,
) -> None:
    semantic_node = node("semantic_node", [])
    semantic_node["write_scope"] = ["artifacts/semantic/"]
    semantic_node["expected_output_artifacts"] = ["artifacts/semantic/expected.json"]
    wf = {"workflow_id": "semantic-wf", "workflow_kind": "research_synthesis", "nodes": [semantic_node]}

    class SemanticDefectDispatch:
        def __call__(self, request: dict) -> dict:
            result = result_for(request, artifact_root=tmp_path)
            artifact = result["output_artifacts"][0]
            if semantic_defect == "wrong_expected_path":
                path = tmp_path / "artifacts" / "semantic" / "other.json"
                embedded = {"node_id": "semantic_node"}
            else:
                path = tmp_path / artifact["path"]
                embedded = {"node_id": "semantic_node"}
            if semantic_defect == "missing_evidence_link":
                result["evidence"][0].pop("artifact_id")
            elif semantic_defect == "wrong_embedded_node":
                embedded["node_id"] = "foreign-node"
            elif semantic_defect == "wrong_embedded_schema":
                artifact["schema"] = "expected.v1"
                embedded["schema"] = "malicious.v1"
            elif semantic_defect == "arbitrary_json":
                embedded = {"message": "hash-consistent arbitrary payload"}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(embedded), encoding="utf-8")
            artifact["path"] = path.relative_to(tmp_path).as_posix()
            artifact["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            return result

    orch, _dispatch, _evaluator = orchestrator(tmp_path, wf, dispatch=SemanticDefectDispatch())
    state = orch.step()

    assert state["final_status"] == "failed"
    record = orch.state_store.load_node_record(state["node_states"]["semantic_node"]["result_ref"])
    assert record["result"]["status"] == "failed"
