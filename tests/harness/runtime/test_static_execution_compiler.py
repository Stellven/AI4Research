from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "harness" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import scheduler_input  # noqa: E402
import static_execution_compiler as compiler  # noqa: E402


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _planner_bundle(tmp_path: Path) -> dict[str, Path]:
    requirement = {
        "schema_version": "solar.requirement_ir.v2",
        "requirement_ir_id": "requirement-test",
        "intent_ir_ref": {"intent_ir_id": "intent-test", "sha256": "1" * 64},
        "intent_acceptance_ref": {"acceptance_id": "accept-test", "required_decision": "accepted"},
        "requirements": [{
            "requirement_id": "R1",
            "origin": "user:G1",
            "statement": "Produce a source-linked scientific report.",
            "priority": "must",
            "source_refs": ["G1"],
            "acceptance": {"kind": "artifact_fields", "required_values": ["answer", "evidence"]},
            "check": "check.information_outcome_completeness.v1",
            "checkable": True,
            "disposition": None,
        }],
        "scope": {"research": {"allowed": ["source_discovery", "artifact_generation"], "forbidden": [], "network": "allowed_if_required_by_requirement"}},
        "assumptions": [],
        "conflict_scan": {"result": "clean", "detail": None},
        "approvals": [],
        "rollback": None,
    }
    requirement_path = _write(tmp_path / "requirement_ir.json", requirement)

    decision = {
        "schema_version": "solar.planning_decision.v1",
        "artifact_role": "runtime_artifact",
        "planning_decision_id": "decision-test",
        "generation": 0,
        "requirement_ir_ref": {"requirement_ir_id": "requirement-test", "sha256": _sha(requirement_path)},
        "planning_context_ref": {"planning_context_id": "context-test", "sha256": "2" * 64},
        "producer": {"method": "model", "provider": "test", "model": "test"},
        "decision": "generate",
        "rationale": ["The request needs evidence collection followed by report drafting."],
        "requirement_ids": ["R1"],
        "workflow_ref": None,
        "workflow_inputs": [],
        "workflow_bindings": [],
        "requirements_gap": None,
    }
    decision_path = _write(tmp_path / "planning_decision.json", decision)

    plan = {
        "schema_version": "solar.plan_ir.v2",
        "artifact_role": "runtime_artifact",
        "plan_ir_id": "plan-test",
        "generation": 0,
        "requirement_ir_ref": {"requirement_ir_id": "requirement-test", "sha256": _sha(requirement_path)},
        "planning_decision_ref": {"planning_decision_id": "decision-test", "sha256": _sha(decision_path)},
        "producer": {"method": "model", "provider": "test", "model": "test"},
        "nodes": [
            {
                "node_id": "discover",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "objective": "Discover a traceable shortlist of scientific literature.",
                "depends_on": [],
                "consumes": ["solar.requirement_ir.v2"],
                "produces": [{
                    "artifact_type": "schemas/evidence/literature_discovery.v1.schema.json",
                    "verifier_ids": ["check.discovery.v1"],
                    "materialization": {"kind": "directory", "path": "artifacts/discovery"},
                }],
                "requirement_ids": [],
                "operator_requirements": {
                    "capabilities": ["literature-discovery"],
                    "network": "required",
                    "execution_trust": "evidence_transform",
                    "minimum_context_tokens": 1000,
                    "effects": ["read", "write", "network"],
                },
                "gate_requirement": "check.discovery.v1",
            },
            {
                "node_id": "draft",
                "logical_operator": "ScientificReportDrafter",
                "objective": "Draft a source-linked scientific report from accepted evidence.",
                "depends_on": ["discover"],
                "consumes": ["schemas/evidence/literature_discovery.v1.schema.json"],
                "produces": [{
                    "artifact_type": "schemas/evidence/scientific_report.v1.schema.json",
                    "verifier_ids": ["check.report.v1"],
                    "materialization": {"kind": "directory", "path": "artifacts/report"},
                }],
                "requirement_ids": ["R1"],
                "operator_requirements": {
                    "capabilities": ["report-drafting"],
                    "network": "forbidden",
                    "execution_trust": "evidence_transform",
                    "minimum_context_tokens": 1000,
                    "effects": ["read", "write"],
                },
                "gate_requirement": "check.report.v1",
            },
        ],
    }
    plan_path = _write(tmp_path / "plan_ir.json", plan)
    plan_ref = {"plan_ir_id": "plan-test", "generation": 0, "sha256": _sha(plan_path)}

    validation = {
        "schema_version": "solar.plan_validation.v2",
        "artifact_role": "runtime_artifact",
        "validation_id": "validation-test",
        "plan_ir_ref": plan_ref,
        "status": "pass",
        "checks": [{"check_id": "dag", "kind": "deterministic", "status": "pass"}],
        "errors": [],
        "warnings": [],
        "repair_count": 0,
    }
    fidelity = {
        "schema_version": "solar.plan_fidelity.v1",
        "artifact_role": "runtime_artifact",
        "fidelity_id": "fidelity-test",
        "requirement_ir_ref": {"requirement_ir_id": "requirement-test", "sha256": _sha(requirement_path)},
        "plan_ir_ref": {"plan_ir_id": "plan-test", "sha256": _sha(plan_path)},
        "status": "pass",
        "review_method": "independent_model_call",
        "reviewer": {"provider": "test", "model": "test-reviewer"},
        "checks": [{"status": "pass"} for _ in range(4)],
        "errors": [],
        "warnings": [],
    }
    binding = {
        "schema_version": "solar.binding_trace.v2",
        "artifact_role": "runtime_artifact",
        "binding_trace_id": "binding-test",
        "requirement_ir_ref": {"requirement_ir_id": "requirement-test", "sha256": _sha(requirement_path)},
        "plan_ir_ref": {"plan_ir_id": "plan-test", "sha256": _sha(plan_path)},
        "bindings": {
            "R1": {
                "owners": ["draft"],
                "artifacts": ["schemas/evidence/scientific_report.v1.schema.json"],
                "verifiers": ["check.information_outcome_completeness.v1"],
            }
        },
        "uncovered": [],
        "verdict": "pass",
    }
    return {
        "requirement": requirement_path,
        "decision": decision_path,
        "plan": plan_path,
        "validation": _write(tmp_path / "plan_validation.json", validation),
        "fidelity": _write(tmp_path / "plan_fidelity.json", fidelity),
        "binding": _write(tmp_path / "binding_trace.json", binding),
    }


def test_compile_accepted_planner_bundle_to_scheduler_authority(tmp_path: Path) -> None:
    bundle = _planner_bundle(tmp_path)
    result = compiler.compile_bundle(
        requirement_ir_path=bundle["requirement"],
        planning_decision_path=bundle["decision"],
        plan_ir_path=bundle["plan"],
        plan_validation_path=bundle["validation"],
        plan_fidelity_path=bundle["fidelity"],
        binding_trace_path=bundle["binding"],
        output_dir=tmp_path / "compiled",
        sprint_id="sprint-test",
    )

    scheduler_value = json.loads(Path(result["scheduler_input"]).read_text(encoding="utf-8"))
    assert scheduler_input.validate(scheduler_value, require_runtime_authority=True) == {"ok": True, "errors": []}
    assert [node["id"] for node in scheduler_value["graph"]["nodes"]] == ["discover", "draft"]
    assert scheduler_value["graph"]["nodes"][0]["physical_candidates"][0]["operator_id"] == "autosci-literature-discover-worker"
    assert scheduler_value["graph"]["nodes"][1]["physical_candidates"][0]["operator_id"] == "autosci-report-worker"
    assert all("selected_operator" not in node for node in scheduler_value["graph"]["nodes"])
    assert Path(result["run_contract"]).is_file()

    runtime_graph_path = scheduler_input.prepare_runtime_graph(
        result["scheduler_input"],
        tmp_path / "runtime",
        run_contract_path=result["run_contract"],
        artifact_bindings={"solar.requirement_ir.v2": str(bundle["requirement"])},
    )
    runtime_graph = json.loads(runtime_graph_path.read_text(encoding="utf-8"))
    assert scheduler_input.verify_runtime_projection(runtime_graph) == {"ok": True, "errors": []}
    assert runtime_graph["nodes"][0]["physical_candidates"][0]["operator_id"] == "autosci-literature-discover-worker"


def test_rejects_failed_planner_evaluator_before_static_binding(tmp_path: Path) -> None:
    bundle = _planner_bundle(tmp_path)
    validation = json.loads(bundle["validation"].read_text(encoding="utf-8"))
    validation["status"] = "fail"
    validation["checks"][0]["status"] = "fail"
    _write(bundle["validation"], validation)

    with pytest.raises(compiler.StaticExecutionCompileError, match="PLAN_VALIDATION_NOT_PASSED"):
        compiler.compile_bundle(
            requirement_ir_path=bundle["requirement"],
            planning_decision_path=bundle["decision"],
            plan_ir_path=bundle["plan"],
            plan_validation_path=bundle["validation"],
            plan_fidelity_path=bundle["fidelity"],
            binding_trace_path=bundle["binding"],
            output_dir=tmp_path / "compiled",
        )


def test_rejects_plan_with_wrong_requirement_hash(tmp_path: Path) -> None:
    bundle = _planner_bundle(tmp_path)
    plan = json.loads(bundle["plan"].read_text(encoding="utf-8"))
    plan["requirement_ir_ref"]["sha256"] = "f" * 64
    _write(bundle["plan"], plan)

    with pytest.raises(compiler.StaticExecutionCompileError, match="REFERENCE_HASH_MISMATCH:requirement_ir_ref"):
        compiler.compile_bundle(
            requirement_ir_path=bundle["requirement"],
            planning_decision_path=bundle["decision"],
            plan_ir_path=bundle["plan"],
            plan_validation_path=bundle["validation"],
            plan_fidelity_path=bundle["fidelity"],
            binding_trace_path=bundle["binding"],
            output_dir=tmp_path / "compiled",
        )
