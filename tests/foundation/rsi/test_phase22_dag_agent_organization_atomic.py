from __future__ import annotations

import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HARNESS_LIB = REPO / "harness" / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import graph_scheduler  # noqa: E402


def _node(node_id: str, cost: float, depends_on: list[str] | None = None) -> dict[str, object]:
    return {
        "id": node_id,
        "status": "pending",
        "depends_on": depends_on or [],
        "estimated_cost": cost,
        "write_scope": [f"workspace/{node_id}.json"],
        "acceptance": [f"{node_id} completed"],
        "required_capabilities": ["planning"],
    }


def test_atomic_dag_and_agent_organization_aflow_mcts_adas__cost_comparison() -> None:
    high_cost_candidate = {
        "sprint_id": "phase22-dag-agent-cost-high",
        "nodes": [
            _node("plan", 1),
            _node("cheap_agent", 2, ["plan"]),
            _node("expensive_agent", 6, ["plan"]),
            _node("verify", 1, ["cheap_agent", "expensive_agent"]),
        ],
    }
    lower_cost_candidate = {
        "sprint_id": "phase22-dag-agent-cost-low",
        "nodes": [
            _node("plan", 1),
            _node("cheap_agent", 2, ["plan"]),
            _node("verify", 1, ["cheap_agent"]),
        ],
    }

    high_cost_path = graph_scheduler.critical_path(high_cost_candidate)
    lower_cost_path = graph_scheduler.critical_path(lower_cost_candidate)

    assert graph_scheduler.validate_graph(high_cost_candidate)["ok"] is True
    assert graph_scheduler.validate_graph(lower_cost_candidate)["ok"] is True
    assert high_cost_path == {"cost": 8.0, "path": ["plan", "expensive_agent", "verify"]}
    assert lower_cost_path == {"cost": 4.0, "path": ["plan", "cheap_agent", "verify"]}
    assert lower_cost_path["cost"] < high_cost_path["cost"]
