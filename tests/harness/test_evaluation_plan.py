from __future__ import annotations

import copy

import pytest

from harness.lib import evaluation_plan
from harness.evaluators.scientific import experiment_approval_gate


PATCH = "artifact.patch_diff"
EXPERIMENT_PLAN = "schema:schemas/evidence/experiment_plan.v1.schema.json"
EXPERIMENT_APPROVAL = "schema:schemas/evidence/experiment_approval.v1.schema.json"


def _requirement_ir(
    *,
    check_id: str = "check.patch_within_scope",
    checkable: bool = True,
    machine_checkable: bool | None = None,
) -> dict:
    requirement = {
        "requirement_id": "R1",
        "statement": "Implement the requested change within the declared scope.",
        "check": check_id,
        "checkable": checkable,
    }
    if machine_checkable is not None:
        requirement["machine_checkable"] = machine_checkable
    return {
        "schema_version": "solar.requirement_ir.v2",
        "requirement_ir_id": "requirement-ir-evaluation-plan-test",
        "requirements": [requirement],
    }


def _plan_ir(*, output_type: str = PATCH, verifier_id: str = "check.patch_within_scope") -> dict:
    return {
        "schema_version": "solar.plan_ir.v2",
        "plan_ir_id": "plan-ir-evaluation-plan-test",
        "nodes": [
            {
                "node_id": "build",
                "objective": "Implement and verify the requested change.",
                "requirement_ids": ["R1"],
                "produces": [
                    {
                        "artifact_type": output_type,
                        "verifier_ids": [verifier_id],
                    }
                ],
            }
        ],
    }


def _capsule_plan(*, proof_obligations: list[dict] | None = None) -> dict:
    return {
        "schema_version": "solar.capsule_plan.v1",
        "nodes": [
            {
                "node_id": "build",
                "selected_capsule_id": "cap.requirement-compiler-implementation",
                "proof_obligations": proof_obligations or [],
            }
        ],
    }


def _task_graph(*, gate_kind: str = "llm_eval") -> dict:
    return {
        "sprint_id": "sprint-evaluation-plan-test",
        "nodes": [
            {
                "id": "build",
                "evaluator_gate": {
                    "kind": gate_kind,
                    "on_fail": "repair_once_then_fail",
                },
            }
        ],
    }


def _compile(
    requirement_ir: dict | None = None,
    plan_ir: dict | None = None,
    capsule_plan: dict | None = None,
    task_graph: dict | None = None,
) -> tuple[dict, dict]:
    requirement_ir = requirement_ir or _requirement_ir()
    plan_ir = plan_ir or _plan_ir()
    capsule_plan = capsule_plan or _capsule_plan()
    task_graph = task_graph or _task_graph()
    registry = evaluation_plan.load_evaluation_check_registry()
    compiled = evaluation_plan.compile_evaluation_plan(
        requirement_ir,
        plan_ir,
        capsule_plan,
        task_graph,
        registry=registry,
    )
    validation = evaluation_plan.validate_evaluation_plan(
        compiled,
        requirement_ir,
        plan_ir,
        capsule_plan,
        task_graph,
        registry=registry,
    )
    return compiled, validation


def test_registry_resolves_every_declared_deterministic_callable() -> None:
    registry = evaluation_plan.load_evaluation_check_registry()

    deterministic = [
        row for row in registry["checks"] if row["deterministic"] is not None
    ]
    assert deterministic
    assert any(row["check_id"] == "check.scientific.experiment_plan.v1" for row in deterministic)
    assert any(row["check_id"] == "check.scientific.experiment_approval.v1" for row in deterministic)


def test_checkable_semantic_requirement_routes_to_independent_review() -> None:
    compiled, validation = _compile()

    node = compiled["nodes"][0]
    assert compiled["verdict"] == "pass"
    assert validation["status"] == "pass"
    assert node["checks"][0]["check_id"] == "check.patch_within_scope"
    assert node["checks"][0]["mode"] == "semantic"
    assert node["semantic_review"]["required"] is True
    assert node["gate_policy"]["kind"] == "llm_eval"


def test_explicit_machine_checkable_semantic_only_check_fails_admission() -> None:
    requirement_ir = _requirement_ir(machine_checkable=True)

    compiled, validation = _compile(requirement_ir=requirement_ir)

    assert compiled["verdict"] == "fail"
    assert {
        row["code"] for row in compiled["unresolved"]
    } == {"MACHINE_CHECK_IMPLEMENTATION_MISSING"}
    assert validation["status"] == "fail"


def test_unknown_requirement_check_fails_before_runtime() -> None:
    requirement_ir = _requirement_ir(check_id="check.unknown.v1")
    plan_ir = _plan_ir(verifier_id="check.unknown.v1")

    compiled, validation = _compile(requirement_ir=requirement_ir, plan_ir=plan_ir)

    assert compiled["verdict"] == "fail"
    assert compiled["unresolved"][0]["code"] == "CHECK_UNREGISTERED"
    assert validation["status"] == "fail"


def test_scientific_artifact_gets_existing_deterministic_gate_automatically() -> None:
    requirement_ir = _requirement_ir(check_id="not_machine_checkable", checkable=False)
    plan_ir = _plan_ir(output_type=EXPERIMENT_PLAN, verifier_id="not_machine_checkable")

    compiled, validation = _compile(requirement_ir=requirement_ir, plan_ir=plan_ir)

    checks = {row["check_id"]: row for row in compiled["nodes"][0]["checks"]}
    assert compiled["verdict"] == "pass"
    assert validation["status"] == "pass"
    assert checks["check.scientific.experiment_plan.v1"]["source"] == "artifact_auto"
    assert checks["check.scientific.experiment_plan.v1"]["mode"] == "deterministic"
    assert checks["check.scientific.experiment_plan.v1"]["deterministic"]["implementation_ref"] == (
        "evaluators.scientific.experiment_plan_gate:evaluate"
    )


def test_experiment_approval_artifact_gets_exact_deterministic_gate() -> None:
    requirement_ir = _requirement_ir(check_id="not_machine_checkable", checkable=False)
    plan_ir = _plan_ir(output_type=EXPERIMENT_APPROVAL, verifier_id="not_machine_checkable")

    compiled, validation = _compile(requirement_ir=requirement_ir, plan_ir=plan_ir)

    checks = {row["check_id"]: row for row in compiled["nodes"][0]["checks"]}
    assert compiled["verdict"] == "pass"
    assert validation["status"] == "pass"
    assert checks["check.scientific.experiment_approval.v1"]["source"] == "artifact_auto"
    assert checks["check.scientific.experiment_approval.v1"]["deterministic"]["implementation_ref"] == (
        "evaluators.scientific.experiment_approval_gate:evaluate"
    )


def _approval_evidence(*, approved: bool = True) -> dict:
    return {
        "schema": "experiment_approval.v1",
        "task_id": "task-approval",
        "sprint_id": "sprint-approval",
        "node_id": "experiment-approval",
        "status": "completed" if approved else "inconclusive",
        "inputs": {},
        "outputs": {
            "approval": {
                "experiment_id": "exp-001",
                "decision": "approved" if approved else "awaiting_human",
                "approval_ref": "approval:user:001" if approved else "",
                "plan_sha256": "a" * 64,
                "approved_capabilities": ["execute_experiment"] if approved else [],
                "sandbox": {
                    "mode": "isolated",
                    "network": False,
                    "write_scope": ["artifacts/scientific/run/"],
                },
                "reasons": [],
            }
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "autosci-experiment-approval-gate-physical",
            "operator_version": "1",
            "implementation_package": "plugins.autosci.operators.scientific_lifecycle.action.experiment",
            "timestamp": "2026-08-26T00:00:00Z",
            "input_sha256": "b" * 64,
            "output_sha256": "c" * 64,
        },
        "limitations": [] if approved else ["Human approval is required."],
    }


def test_experiment_approval_gate_accepts_only_explicit_safe_approval() -> None:
    passed = experiment_approval_gate.evaluate(_approval_evidence())
    blocked = experiment_approval_gate.evaluate(_approval_evidence(approved=False))

    assert passed.ok is True
    assert passed.status == "passed"
    assert blocked.ok is False
    assert blocked.status == "failed"
    assert "outputs.approval.decision must be approved" in blocked.reasons


def test_capsule_field_obligation_is_recorded_as_runtime_proof() -> None:
    capsule_plan = _capsule_plan(
        proof_obligations=[
            {
                "source_capsule_id": "cap.requirement-compiler-implementation",
                "kind": "postcondition",
                "requirement": "patch_diff_present",
                "field": "patch_diff",
            }
        ]
    )

    compiled, validation = _compile(capsule_plan=capsule_plan)

    assert validation["status"] == "pass"
    assert compiled["nodes"][0]["capsule_contract_criteria"] == [
        {
            "source_capsule_id": "cap.requirement-compiler-implementation",
            "kind": "postcondition",
            "text": "patch_diff_present",
            "field": "patch_diff",
            "disposition": "runtime_proof",
        }
    ]


def test_known_capsule_presence_checks_do_not_become_llm_rubric_text() -> None:
    capsule_plan = _capsule_plan(
        proof_obligations=[
            {
                "source_capsule_id": "guard.secret-leak-guard",
                "kind": "self_check",
                "requirement": "check.guard_decision_written",
            },
            {
                "source_capsule_id": "cap.requirement-compiler-implementation",
                "kind": "external_verifier",
                "requirement": "external_verifier.required",
            },
            {
                "source_capsule_id": "cap.requirement-compiler-verification",
                "kind": "self_check",
                "requirement": "check.coverage_reviewed",
            },
        ]
    )

    compiled, validation = _compile(capsule_plan=capsule_plan)

    assert validation["status"] == "pass"
    node = compiled["nodes"][0]
    criteria = node["capsule_contract_criteria"]
    assert [(row["text"], row["field"], row["disposition"]) for row in criteria] == [
        ("check.guard_decision_written", "guard_decision", "runtime_proof"),
        ("external_verifier.required", "eval_json", "runtime_proof"),
    ]
    assert any(
        row["check_id"] == "check.coverage_reviewed"
        and row["source"] == "capsule_contract"
        for row in node["checks"]
    )
    semantic = node["semantic_review"]["criteria"]
    assert "check.guard_decision_written" not in semantic
    assert "external_verifier.required" not in semantic
    assert "check.coverage_reviewed" not in semantic
    assert any("Every requirement owned by the node" in value for value in semantic)


def test_semantic_check_without_llm_evaluator_gate_fails_admission() -> None:
    compiled, validation = _compile(task_graph=_task_graph(gate_kind="deterministic_command"))

    assert compiled["verdict"] == "fail"
    assert any(row["code"] == "SEMANTIC_REVIEW_GATE_MISSING" for row in compiled["unresolved"])
    assert validation["status"] == "fail"


def test_gate_repair_contract_normalizes_missing_on_fail_action() -> None:
    task_graph = _task_graph()
    gate = task_graph["nodes"][0]["evaluator_gate"]
    gate.pop("on_fail")
    gate["repair"] = {"max_attempts": 1}

    compiled, validation = _compile(task_graph=task_graph)

    assert validation["status"] == "pass"
    assert compiled["nodes"][0]["gate_policy"] == {
        "kind": "llm_eval",
        "on_fail": "repair_once_then_fail",
        "maximum_repairs": 1,
    }


def test_validation_detects_tampered_hash_chain() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _plan_ir()
    capsule_plan = _capsule_plan()
    compiled, _ = _compile(
        requirement_ir=requirement_ir,
        plan_ir=plan_ir,
        capsule_plan=capsule_plan,
    )
    tampered = copy.deepcopy(compiled)
    tampered["plan_ir_ref"]["sha256"] = "0" * 64

    registry = evaluation_plan.load_evaluation_check_registry()
    validation = evaluation_plan.validate_evaluation_plan(
        tampered,
        requirement_ir,
        plan_ir,
        capsule_plan,
        _task_graph(),
        registry=registry,
    )

    assert validation["status"] == "fail"
    assert any(row["check"] == "plan_ref" and row["status"] == "fail" for row in validation["checks"])


def test_registry_rejects_non_callable_deterministic_implementation(tmp_path) -> None:
    registry = evaluation_plan.load_evaluation_check_registry()
    broken = copy.deepcopy(registry)
    row = next(item for item in broken["checks"] if item["deterministic"] is not None)
    row["deterministic"]["implementation_ref"] = "evaluators.scientific.experiment_plan_gate:missing"
    path = tmp_path / "registry.json"
    path.write_text(__import__("json").dumps(broken), encoding="utf-8")

    with pytest.raises(evaluation_plan.EvaluationPlanError, match="implementation is not callable"):
        evaluation_plan.load_evaluation_check_registry(path)
