from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
ROUTER_PATH = REPO / "harness" / "tools" / "codex_pm_router.py"


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


def test_atomic_poc_implementation_environment_preparation__resource() -> None:
    router = _load_router()
    payload = router.build_pm_intake(
        (
            "Build a POC implementation environment plan that prepares runtime dependencies, "
            "data access permissions, compute resources, configs, and verification gates before coding."
        ),
        sprint_id="phase22-poc-environment-resource",
        target_system="solar-harness",
    )

    validation = router.validate_compiled_package(payload)
    graph = payload["compiled_artifacts"]["task_dag"]
    nodes = graph["nodes"]
    by_id = {node["id"]: node for node in nodes}
    agent_contract = payload["compiled_artifacts"]["contracts_bundle"]["contracts"]["agent_execution"]

    assert validation["ok"] is True
    assert by_id["S2"]["logical_operator"] == "ImplementationWorker"
    assert by_id["S2"]["capsule_plan"]["required_resource_capsules"] == ["resource.repo-workspace"]
    assert by_id["S2"]["capsule_plan"]["dispatch_task_type"] == "implementation"
    assert all(float(node["estimated_cost"]) > 0 for node in nodes)
    assert {"inspect", "test"}.issubset(set(agent_contract["commands"]))
    assert "network access" in agent_contract["approval_required_when"]
    assert {node["id"] for node in nodes if node.get("approval_gate")} == {"S4", "S5"}
