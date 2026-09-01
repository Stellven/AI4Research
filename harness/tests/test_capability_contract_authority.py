"""Offline regression for capability admission, bounded planning and frozen dispatch."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import capability_admission as admission
import capability_capsules as capsules
import elastic_planner as planner
import execution_authority as authority
import execution_resources as resources
import scheduler_input as scheduler


@pytest.fixture(scope="module")
def catalog():
    return planner.build_planning_catalog_snapshot()


def test_catalog_prompt_and_candidate_admission_share_compact_contract(catalog):
    payload = json.loads(planner._plan_prompt({"requirements": []}, {"decision": "generate"},
                                            catalog, {}, {"checks": []}, generation=0))
    rows = {row["capsule_id"]: row for row in payload["capability_capsule_abis"]}
    assert len(rows) == len(catalog["capsules"])
    unavailable = 0
    for row in catalog["capsules"]:
        model = rows[row["capsule_id"]]
        assert model["executable"] == (not admission.rejection_reasons(row))
        assert set(model) == {
            "capsule_id",
            "description",
            "task_types",
            "consumes",
            "produces",
            "active_effects",
            "execution_trust",
            "executable",
        }
        unavailable += not model["executable"]
    assert unavailable > 0  # All registered entries are visible, not all are executable.
    edges, exclusions = planner.capsule_composition._composition_edges(catalog, {"conversions": []}, {"artifact_types": []})
    assert {e["capsule_id"] for e in edges} == {cid for cid, r in rows.items() if r["executable"]}
    rows[next(iter(rows))]["description"] = "tampered"
    assert all(row.get("description") != "tampered" for row in catalog["capsules"])


@pytest.mark.parametrize("field,code", [
    ("verification", "VERIFICATION_CONTRACT_MISSING"),
    ("implementation", "IMPLEMENTATION_UNDECLARED"),
    ("operator_compatibility", "NO_SELECTABLE_PHYSICAL_OPERATOR"),
    ("task_types", "TASK_TYPE_UNDECLARED"),
])
def test_admission_ignores_stale_optimistic_flag(catalog, field, code):
    row = copy.deepcopy(next(r for r in catalog["capsules"] if not admission.rejection_reasons(r)))
    row[field] = [] if field == "task_types" else {}
    row["executable"] = True
    result = admission.model_contract(row)
    assert result["executable"] is False and code in result["unavailability_reasons"]


def test_freeze_captures_guard_closure_and_excludes_dynamic_operator_state():
    definitions = {"capsules": {
        "cap.a": {"status": "stable", "manifest": {"bindings": {"required_guard_capsules": ["guard.a"]}}},
        "guard.a": {"status": "stable", "manifest": {}}},
        "operators": {"op": {"model": "model-v1"}}}
    node = {"capsule_binding": {"capsule_ids": ["cap.a"]}, "physical_candidates": [{"operator_id": "op"}]}
    frozen = authority.freeze_node(node, definitions)
    assert set(frozen["capsules"]) == {"cap.a", "guard.a"}
    authority.check_operator(frozen, "op", {"model": "model-v1", "state": "busy", "quota": 0})
    with pytest.raises(ValueError, match="FROZEN_OPERATOR"):
        authority.check_operator(frozen, "op", {"model": "model-v2"})
    frozen["capsules"]["cap.a"]["status"] = "revoked"
    with pytest.raises(ValueError, match="AUTHORITY_INVALID"):
        authority.validate(frozen)


@pytest.mark.parametrize("requirements,operator,capacity,expected", [
    ({"minimum_context_tokens": 4096}, {}, {}, ["CONTEXT_CAPACITY_UNKNOWN"]),
    ({"minimum_context_tokens": 4096}, {"context_window": 2048}, {}, ["CONTEXT_CAPACITY_INSUFFICIENT"]),
    ({"minimum_context_tokens": 4096}, {"resource_capacity": {"context_tokens": 8192}}, {}, []),
    ({"cpu_cores_min": 4, "memory_mb_min": 2048}, {}, {"cpu_cores": 2, "memory_mb": 1024}, ["CPU_CORES_INSUFFICIENT", "MEMORY_MB_INSUFFICIENT"]),
    ({"gpu_required": True}, {}, {}, ["GPU_CAPACITY_UNKNOWN"]),
    ({"gpu_required": True}, {}, {"gpu_available": True}, []),
    ({}, {}, {}, []),
])
def test_resource_limits(requirements, operator, capacity, expected):
    assert resources.check(requirements, operator, capacity=capacity) == expected


def test_remote_unknown_capacity_does_not_use_local_host(monkeypatch):
    monkeypatch.setattr(resources, "local_capacity", lambda: pytest.fail("remote used local capacity"))
    assert resources.check({"memory_mb_min": 1}, {"runtime_binding": {"kind": "ssh", "host": "remote"}}) == ["MEMORY_MB_UNKNOWN"]


def test_compiler_preserves_context_cpu_memory_gpu_and_freezes_definitions():
    needs = {"minimum_context_tokens": 4096, "cpu_cores_min": 2, "memory_mb_min": 1024,
             "gpu_required": True, "network": "optional"}
    graph = {"sprint_id": "sprint-fixture", "nodes": [{"id": "N", "goal": "Do work", "logical_operator": "Worker", "dispatch_task_type": "implementation",
                        "requirement_ids": ["R1"], "artifact_types": {"consumes": [], "produces": ["artifact.report"]},
                        "operator_requirements": needs, "capability_capsule_id": "cap.a"}]}
    definitions = {"capsules": {"cap.a": {"status": "stable", "manifest": {}}}, "operators": {"op": {"model": "fixture"}}}
    result = planner.compile_scheduler_input(graph, {"nodes": []}, {"nodes": [{"node_id": "N", "execution_candidates": [{"operator_id": "op"}]}]},
                                             {"nodes": [{"node_id": "N", "checks": [{"check_id": "gate.fixture", "mode": "deterministic"}]}]},
                                             sprint_id="sprint-fixture", execution_definitions=definitions)
    node = result["graph"]["nodes"][0]
    assert node["resource_requirements"] == needs
    assert node["execution_authority"]["operators"] == definitions["operators"]
    assert scheduler.semantic_errors(result) == []


def test_scheduler_uses_ranked_frozen_candidates_and_blocks_static_drift(monkeypatch):
    spec = importlib.util.spec_from_file_location("authority_test_runner", ROOT / "lib/multi_task_runner.py")
    runner = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, runner)
    spec.loader.exec_module(runner)
    specs = {"first": {"operator_id": "first", "model": "changed", "context_window": 8192},
             "second": {"operator_id": "second", "model": "approved", "context_window": 8192}}
    frozen = {"schema_version": "solar.node_execution_authority.v1", "capsules": {},
              "operators": {key: {"model": "approved", "context_window": 8192} for key in specs}}
    frozen["sha256"] = authority.digest(frozen)
    node = {"physical_candidates": [{"operator_id": "first", "rank": 1}, {"operator_id": "second", "rank": 2}],
            "execution_authority": frozen, "resource_requirements": {"minimum_context_tokens": 4096}}
    monkeypatch.setattr(runner, "resolve_operator", lambda oid: specs[oid])
    monkeypatch.setattr(runner, "operator_dispatchable", lambda op: (True, ""))
    monkeypatch.setattr(runner, "_operator_backend_runnable", lambda op: True)
    monkeypatch.setattr(runner, "operator_in_failure_cooldown", lambda oid: False)
    selected, reason = runner.select_operator(node, {})
    assert selected["operator_id"] == "second" and reason == ""
    assert "FROZEN_OPERATOR_DEFINITION_CHANGED" in selected["scheduler_candidate_observations"][0]["reason"]
    node["resource_requirements"]["minimum_context_tokens"] = 16384
    assert runner.select_operator(node, {})[0] is None


def test_frozen_capsule_uses_snapshot_but_honors_live_revocation(monkeypatch):
    entry = SimpleNamespace(status="stable", manifest_path="must-not-read", default_operator_profile="op")
    monkeypatch.setattr(capsules, "get_registry_entry", lambda *a, **k: entry)
    monkeypatch.setattr(capsules, "load_capability_capsule_manifest", lambda *a: pytest.fail("live manifest read"))
    monkeypatch.setattr(capsules, "_resolve_bindings", lambda *a: {"selected_skills": ["frozen.skill"], "mcp_capabilities": {}})
    frozen = {"cap.a": {"manifest": {"capability_capsule_id": "cap.a", "verification": {"pass_conditions": ["frozen condition"]}}, "default_operator_profile": "op"}}
    result = capsules.resolve_capability_capsule_for_task({"capability_capsule_id": "cap.a"}, frozen_definitions=frozen)
    assert result["verification_hooks"]["pass_conditions"] == ["frozen condition"]
    entry.status = "revoked"
    with pytest.raises(capsules.CapsuleResolutionError, match="revoked"):
        capsules.resolve_capability_capsule_for_task({"capability_capsule_id": "cap.a"}, frozen_definitions=frozen)


def test_scheduler_projection_transports_frozen_authority_and_envelope_tampering(tmp_path):
    value = json.loads((ROOT / "metadata/5-taskgraph compiler and validator output/scheduler_input/scheduler_input.json").read_text())
    value["artifact_role"] = "runtime_execution_authority"
    for node in value["graph"]["nodes"]:
        node["capability_capsule_id"] = node["capsule_binding"]["capsule_ids"][0]
        node["workspace_reads"] = []
        node["output_routes"] = [
            {
                "artifact_type": artifact_type,
                "route_kind": "sprint_private",
                "relative_path": f"{node['id']}-{index}.json",
                "materialization_kind": "file",
            }
            for index, artifact_type in enumerate(
                node["artifact_contract"]["produces"], start=1
            )
        ]
        definitions = {"capsules": {cid: {"status": "stable", "manifest": {}} for cid in node["capsule_binding"]["capsule_ids"]},
                       "operators": {op["operator_id"]: {"model": "fixture"} for op in node["physical_candidates"]}}
        node["execution_authority"] = authority.freeze_node(node, definitions)
    external = tmp_path / "input.json"
    external.write_text("{}")
    source = tmp_path / "scheduler_input.json"
    source.write_text(json.dumps(value))
    path = scheduler.prepare_runtime_graph(source, tmp_path / "runtime", artifact_bindings={"artifact.request.v1": str(external)})
    graph = json.loads(path.read_text())
    node = graph["nodes"][0]
    envelope = {**copy.deepcopy(node), "node_id": node["id"], "sprint_id": graph["sprint_id"],
                "graph_path": str(path), "operator_id": node["physical_candidates"][0]["operator_id"], "model": "fixture"}
    assert authority.from_envelope(envelope) == node["execution_authority"]
    envelope.pop("execution_authority")
    with pytest.raises(ValueError, match="ENVELOPE_MISMATCH"):
        authority.from_envelope(envelope)
    envelope["execution_authority"] = node["execution_authority"]
    envelope["effects"] = ["irreversible"]
    with pytest.raises(ValueError, match="FIELD_MISMATCH:effects"):
        authority.from_envelope(envelope)


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_binding_failure_replans_dag_once_preserving_requirements(tmp_path, monkeypatch, repair_succeeds):
    # Exercise the actual planning loop; isolate models/schema gates already covered separately.
    req = {"requirement_ir_id": "r-test", "requirements": [{"requirement_id": "R1", "statement": "Preserve protocol before search"}]}
    original = copy.deepcopy(req)
    monkeypatch.setattr(planner, "materialize_planning_context", lambda *a: ({"artifacts": []}, {"requirement_ir": req}))
    monkeypatch.setattr(planner, "compile_planning_decision", lambda *a, **k: {"decision": "generate"})
    monkeypatch.setattr(planner, "validate_planning_decision", lambda *a: [])
    monkeypatch.setattr(planner.evaluation_planning, "load_evaluation_check_registry", lambda: {})
    monkeypatch.setattr(planner.capsule_composition, "load_artifact_type_registry", lambda: {})
    monkeypatch.setattr(planner.capsule_composition, "load_conversion_registry", lambda: {})
    calls = []
    def candidate(*args, **kwargs):
        calls.append(kwargs)
        return {"plan_ir_id": "p", "generation": kwargs["generation"], "nodes": []}
    monkeypatch.setattr(planner, "compile_plan_candidate", candidate)
    monkeypatch.setattr(planner, "build_plan_composition_catalog", lambda *a, **k: {"nodes": [{"node_id": "protocol", "candidates": []}]})
    monkeypatch.setattr(planner, "validate_plan_ir", lambda *a, **k: {"status": "pass", "errors": []})
    monkeypatch.setattr(planner, "build_binding_trace", lambda *a: {})
    monkeypatch.setattr(planner, "review_plan_fidelity", lambda *a: {"status": "pass", "errors": []})
    binding_calls = []
    def binding(*args, **kwargs):
        binding_calls.append(kwargs["maximum_repairs"])
        return {"accepted": repair_succeeds and len(binding_calls) == 2,
                "fit_review": {"errors": [{"code": "SEMANTIC_METHOD_MISMATCH"}]}}
    monkeypatch.setattr(planner, "run_generated_composition_binding", binding)
    monkeypatch.setattr(planner, "decide_plan_acceptance", lambda *a, **k: {"decision": "failed" if k["failure"] else "accepted"})
    result = planner.run_semantic_planning_pipeline(req, tmp_path, object(), object(), catalog={"capsules": []})
    assert len(calls) == 2 and binding_calls == [0, 0]
    assert calls[1]["defects"][0]["code"] == "CAPABILITY_IMPLEMENTATION_MISMATCH"
    assert calls[1]["defects"][0]["binding_errors"][0]["code"] == "SEMANTIC_METHOD_MISMATCH"
    assert req == original
    assert result["plan_acceptance"]["decision"] == ("accepted" if repair_succeeds else "failed")
    repair = json.loads((tmp_path / "repair_record.json").read_text())
    assert repair["status"] == ("completed" if repair_succeeds else "failed")
    assert not (tmp_path / "scheduler_input.json").exists()


@pytest.mark.parametrize("tampered", [False, True])
def test_freeze_reuses_binding_without_second_selector(tmp_path, monkeypatch, tampered):
    selection = {"nodes": []}
    cached = {"accepted": True, "binding_kind": "capsule_composition", "selection": selection,
              "composition_catalog": {}, "selection_validation": {"status": "pass"},
              "artifact_type_registry": {}, "artifact_conversion_registry": {},
              "fit_review": {"status": "pass", "selection_ref": {"sha256": planner.sha256_payload(selection)}}}
    if tampered:
        cached["selection"]["nodes"].append({"node_id": "changed"})
    semantic = {"plan_acceptance": {"decision": "accepted"}, "planning_decision": {"decision": "generate"},
                "plan_ir": {}, "planning_context": {}, "planning_catalog_snapshot": {},
                "prevalidated_composition_binding": cached}
    monkeypatch.setattr(planner, "run_generated_capsule_binding", lambda *a: pytest.fail("second selector call"))
    monkeypatch.setattr(planner, "run_generated_composition_binding", lambda *a: pytest.fail("second composition call"))
    monkeypatch.setattr(planner, "validate_composition_selection", lambda *a, **k: {"status": "pass"})
    class ReachedGraphCompiler(Exception):
        pass
    def stop(*a, **k):
        raise ReachedGraphCompiler()
    monkeypatch.setattr(planner, "_generated_composition_task_graph_proposal", stop)
    with pytest.raises(planner.ElasticPlannerError if tampered else ReachedGraphCompiler):
        planner.compile_and_freeze_execution_bundle({}, semantic, tmp_path, sprint_id="sprint-fixture",
                                                    planner_model=object(), reviewer_model=object())
    assert (tmp_path / "composition_selection.json").exists() is (not tampered)
