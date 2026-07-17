"""rc.10 — one certified node identity across planning and execution.

The live research graph certified capsule/task/physical-role constraints while
omitting ``logical_operator``.  Validation accepted it, scheduling defaulted
some work to builder, APO derived a different role, and the UI had no semantic
operator to display.  These tests pin the class-level convergence contract.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


HARNESS = Path(__file__).resolve().parents[2]
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import apo_plan_compiler as apo  # noqa: E402
import executable_node as en  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import plan_validator as pv  # noqa: E402


def _governed_retrieval_graph() -> dict:
    return {
        "sprint_id": "sprint-node-authority",
        "plan_compile_required": True,
        "nodes": [
            {
                "id": "R1",
                "goal": "Retrieve a provenance-complete source pack.",
                "depends_on": [],
                "capability_capsule_id": "cap.research-retrieval",
                "dispatch_task_type": "knowledge-extraction",
                "allowed_operators": {"role": "builder"},
                "read_scope": [],
                "write_scope": ["workspace/research/source-pack/"],
                "proof_obligations": [],
                "evaluator_gate": {
                    "kind": "llm_eval",
                    "on_fail": "repair_once_then_fail",
                },
            }
        ],
    }


def test_governed_planner_node_requires_logical_operator() -> None:
    errors = pv.validate_plan(_governed_retrieval_graph(), None, None)
    assert pv.ERROR_PLAN_LOGICAL_OPERATOR_MISSING in {
        str(item.get("code") or "") for item in errors
    }


def test_logical_operator_is_covered_by_plan_certificate() -> None:
    research = _governed_retrieval_graph()
    research["nodes"][0]["logical_operator"] = "ResearchScout"
    implementation = copy.deepcopy(research)
    implementation["nodes"][0]["logical_operator"] = "ImplementationWorker"

    assert pv.plan_certificate_hash(research) != pv.plan_certificate_hash(implementation)


def test_materialized_executable_node_is_covered_by_plan_certificate() -> None:
    graph = _governed_retrieval_graph()
    graph["nodes"][0]["logical_operator"] = "ResearchScout"
    pv.stamp_plan_certificate(graph)

    graph["nodes"][0]["executable_node"]["logical_operator"] = "ImplementationWorker"

    assert [item["code"] for item in pv.check_plan_certificate(graph)] == [
        "PLAN_CERTIFICATE_HASH_MISMATCH"
    ]


def test_runtime_plan_views_do_not_invalidate_the_node_certificate() -> None:
    graph = _governed_retrieval_graph()
    graph["nodes"][0]["logical_operator"] = "ResearchScout"
    pv.stamp_plan_certificate(graph)

    graph["nodes"][0]["capsule_plan_ir"] = {
        "logical_operator": "ResearchScout",
        "role": "builder",
    }
    graph["nodes"][0]["physical_plan_ir"] = {
        "logical_operator": "ResearchScout",
        "selected_operator_id": "runtime-owned",
    }

    assert pv.check_plan_certificate(graph) == []


def test_critic_semantics_drive_evaluator_dispatch_role() -> None:
    node = {
        "id": "R3",
        "logical_operator": "Critic",
        "allowed_operators": {"role": "evaluator"},
        "write_scope": ["workspace/research/evidence-review/"],
    }

    assert gs.node_dispatch_role(node) == "evaluator"


def test_one_canonical_view_separates_semantics_from_physical_binding() -> None:
    node = _governed_retrieval_graph()["nodes"][0]
    node["logical_operator"] = "ResearchScout"

    contract = en.canonical_executable_node(node)

    assert contract["schema_version"] == "solar.executable_node.v1"
    assert contract["logical_operator"] == "ResearchScout"
    assert contract["dispatch_role"] == "builder"
    assert contract["physical_role"] == "builder"
    assert contract["capability_capsule_id"] == "cap.research-retrieval"
    assert contract["dispatch_task_type"] == "knowledge-extraction"
    assert "status" not in contract
    assert "selected_operator_id" not in contract


def test_canonical_view_conforms_to_its_cross_runtime_schema() -> None:
    import json
    import jsonschema

    node = _governed_retrieval_graph()["nodes"][0]
    node["logical_operator"] = "ResearchScout"
    schema_path = HARNESS / "schemas" / "executable-node.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(en.canonical_executable_node(node))


def test_dashboard_card_projects_the_certified_executable_node() -> None:
    import importlib.util

    status_server = HARNESS / "status-server"
    if str(status_server) not in sys.path:
        sys.path.insert(0, str(status_server))
    route_path = status_server / "routes" / "orchestration_routes.py"
    spec = importlib.util.spec_from_file_location("rc10_node_authority_routes", route_path)
    assert spec is not None and spec.loader is not None
    routes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes)
    node = {
        "id": "R3",
        "executable_node": {
            "schema_version": "solar.executable_node.v1",
            "node_id": "R3",
            "goal": "Audit the evidence.",
            "depends_on": ["R1", "R2"],
            "logical_operator": "Critic",
            "dispatch_role": "evaluator",
            "physical_role": "builder",
            "dispatch_task_type": "review",
            "capability_capsule_id": "cap.requirement-compiler-verification",
            "required_capabilities": [],
            "required_skills": [],
            "read_scope": ["workspace/research/source-pack/"],
            "write_scope": ["workspace/research/evidence-review/"],
        },
    }

    card = routes._build_node_cards("sprint-node-authority", [node], {}, [])[0]

    assert card["executable_node"] == node["executable_node"]
    assert card["logical_operator"] == "Critic"
    assert card["requested_role"] == "evaluator"
    assert card["dispatch_task_type"] == "review"
    assert card["capability_capsule_id"] == "cap.requirement-compiler-verification"


def test_apo_honors_planner_capsule_and_physical_role_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(apo, "LOGICAL_OPERATORS_PATH", HARNESS / "config" / "logical-operators.json")
    node = {
        "id": "R1",
        "goal": "Retrieve a provenance-complete source pack.",
        "logical_operator": "ResearchScout",
        "capability_capsule_id": "cap.research-retrieval",
        "dispatch_task_type": "knowledge-extraction",
        "allowed_operators": {"role": "builder"},
    }

    compiled = apo.build_capsule_plan_node(
        node,
        request_type="research",
        registry_path=HARNESS / "config" / "capability-capsules.registry.yaml",
    )

    assert compiled["selected"] is True
    assert compiled["logical_operator"] == "ResearchScout"
    assert compiled["capability_capsule_id"] == "cap.research-retrieval"
    assert compiled["dispatch_task_type"] == "knowledge-extraction"
    assert compiled["role"] == "builder"


def test_planner_policy_teaches_the_single_node_identity() -> None:
    policy = pv.planner_compile_policy_block(
        HARNESS / "config" / "workflows",
        "sprint-node-authority",
        config_dir=HARNESS / "config",
    )

    assert "logical_operator — required" in policy
    assert "one certified executable-node identity" in policy
