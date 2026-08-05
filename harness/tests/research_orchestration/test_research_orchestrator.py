from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from random import Random

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from research_orchestration.orchestrator import (  # noqa: E402
    ResearchOrchestrationError,
    ResearchOrchestrator,
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


def result_for(request: dict, status: str = "completed") -> dict:
    errors = []
    evidence = []
    if status == "completed":
        evidence = [{"evidence_id": f"ev-{request['node_id']}", "kind": "fake", "summary": "accepted"}]
    if status == "failed":
        errors = [{"error_id": "err", "error_type": "FakeFailure", "message": "failed"}]
    return {
        "schema": "research_node_result.v1",
        "task_id": request["task_id"],
        "run_id": request["run_id"],
        "workflow_id": request["workflow_id"],
        "node_id": request["node_id"],
        "status": status,
        "status_is_terminal": status in {"completed", "failed", "blocked", "cancelled"},
        "output_artifacts": [
            {
                "artifact_id": f"artifact-{request['node_id']}",
                "path": f"artifacts/{request['run_id']}/{request['node_id']}.json",
                "sha256": HASH,
            }
        ],
        "evidence": evidence,
        "hashes": [{"hash_id": "h", "algorithm": "sha256", "value": HASH}],
        "model_provider_usage": [{"provider": "none", "model": "none", "usage_kind": "none"}],
        "errors": errors,
        "limitations": [],
        "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
    }


class FakeDispatch:
    def __init__(self, statuses: dict[str, str] | None = None, fail_on: str | None = None) -> None:
        self.statuses = statuses or {}
        self.fail_on = fail_on
        self.requests: list[dict] = []

    def __call__(self, request: dict) -> dict:
        self.requests.append(deepcopy(request))
        if request["node_id"] == self.fail_on:
            raise RuntimeError("boom")
        return result_for(request, self.statuses.get(request["node_id"], "completed"))


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
    dispatch = kwargs.pop("dispatch", FakeDispatch())
    evaluator = kwargs.pop("evaluator", FakeEvaluator())
    orch = ResearchOrchestrator(
        task_contract=kwargs.pop("task_contract", task()),
        workflow_selector=wf or workflow(),
        state_store=ResearchStateStore(tmp_path / "states"),
        dispatch_callable=dispatch,
        evaluator_callable=evaluator,
        clock=lambda: "2030-01-01T00:00:00Z",
    )
    return orch, dispatch, evaluator


def test_url_synthesis_full_offline_fake_dispatch_flow(tmp_path: Path) -> None:
    selection = load_workflow_selection(ROOT / "config" / "research-workflow-selection.v1.json")
    selected = select_research_workflow({"workflow_kind": "research_synthesis"}, selection, ROOT)
    wf = load_and_normalize_workflow(selected, ROOT)
    orch, dispatch, evaluator = orchestrator(tmp_path, wf, task_contract=task(seed_kind="url"))

    state = orch.run_until_blocked(max_steps=20)

    assert state["final_status"] == "completed"
    assert len(dispatch.requests) == len(wf["nodes"])
    assert len(evaluator.calls) == len(wf["nodes"])


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

    with pytest.raises(ResearchOrchestrationError, match="execute mode"):
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

    with pytest.raises(ResearchOrchestrationError, match="invalid status"):
        orch.step()


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
