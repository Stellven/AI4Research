from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
ROUTER_PATH = REPO / "harness" / "tools" / "codex_pm_router.py"
HARNESS_LIB = REPO / "harness" / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_scheduler  # noqa: E402


def _load_router():
    for module_name in (
        "codex_pm_router",
        "capability_capsules",
        "requirement_coverage",
        "apo_plan_compiler",
    ):
        sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location("codex_pm_router", ROUTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_atomic_constraint_resolution__resource() -> None:
    router = _load_router()
    payload = router.build_pm_intake(
        "Build a requirement compiler that produces PRD, contracts, and task graphs.",
        sprint_id="phase22-constraint-resource",
        target_system="solar-harness",
    )

    validation = router.validate_compiled_package(payload)
    nodes = payload["compiled_artifacts"]["task_dag"]["nodes"]
    by_id = {node["id"]: node for node in nodes}
    contracts = payload["compiled_artifacts"]["contracts_bundle"]["contracts"]
    agent_contract = contracts["agent_execution"]

    assert validation["ok"] is True
    assert by_id["S2"]["logical_operator"] == "ImplementationWorker"
    assert by_id["S2"]["capsule_plan"]["required_resource_capsules"] == ["resource.repo-workspace"]
    assert by_id["S2"]["capsule_plan"]["dispatch_task_type"] == "implementation"
    assert "harness/**" in agent_contract["allowed_paths"]
    assert ".env*" in agent_contract["forbidden_paths"]
    assert all(node["validation"] for node in nodes)


def test_atomic_constraint_resolution__cost() -> None:
    router = _load_router()
    payload = router.build_pm_intake(
        "Build a requirement compiler that produces PRD, contracts, and task graphs.",
        sprint_id="phase22-constraint-cost",
        target_system="solar-harness",
    )
    graph = payload["compiled_artifacts"]["task_dag"]

    validation = router.validate_compiled_package(payload)
    costs_by_id = {node["id"]: node["estimated_cost"] for node in graph["nodes"]}
    critical_path = graph_scheduler.critical_path(graph)

    assert validation["ok"] is True
    assert costs_by_id == {"S1": 2, "S2": 3, "S3": 2, "S4": 2}
    assert critical_path == {"cost": 9.0, "path": ["S1", "S2", "S3", "S4"]}
    assert critical_path["cost"] == sum(float(costs_by_id[node_id]) for node_id in critical_path["path"])
