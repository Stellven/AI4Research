from __future__ import annotations

from pathlib import Path
import sys


LIB = Path(__file__).resolve().parents[2] / "harness" / "lib"
sys.path.insert(0, str(LIB))

import evaluation_budget  # noqa: E402


def _node(node_id: str, operator: str, depends_on: list[str], goal: str = "") -> dict:
    return {
        "id": node_id,
        "logical_operator": operator,
        "depends_on": depends_on,
        "goal": goal or node_id,
        "outputs": [f"workspace/{node_id}.md"],
    }


def test_low_risk_dag_gets_one_final_semantic_review_and_never_reviews_verifier() -> None:
    graph = {
        "schema_version": "solar.task_graph.v1",
        "nodes": [
            _node("S1", "ImplementationWorker", [], "Produce the requested artifact"),
            _node("S2", "TestRunner", ["S1"], "Collect final execution evidence"),
            _node("S3", "Verifier", ["S2"], "Record the closeout decision"),
        ],
    }

    bounded = evaluation_budget.apply_evaluation_budget(
        graph, {"request_type": "short_implementation"}
    )

    policy = bounded["evaluation_policy"]
    assert policy["risk_tier"] == "low"
    assert policy["semantic_evaluation_budget"] == 1
    assert len(policy["semantic_evaluation_node_ids"]) == 1
    assert "S3" not in policy["semantic_evaluation_node_ids"]
    verifier = next(node for node in bounded["nodes"] if node["id"] == "S3")
    assert verifier["evaluator_gate"]["kind"] == "none"
    assert verifier["evaluation_policy"]["decision_reason"] == "no_recursive_evaluator"


def test_research_dag_reviews_only_the_final_report() -> None:
    graph = {
        "schema_version": "solar.task_graph.v1",
        "research_mode": True,
        "nodes": [
            _node("R1", "ResearchScout", [], "Retrieve source pack A"),
            _node("R2", "ResearchScout", [], "Retrieve source pack B"),
            _node("R3", "Critic", ["R1", "R2"], "Audit contradictions and evidence gaps"),
            _node("R4", "ResearchSynthesizer", ["R3"], "Compile synthesis plan"),
            {
                **_node("R5", "ResearchSynthesizer", ["R4"], "Write the cited final report"),
                "outputs": ["workspace/research/report/final.md"],
            },
            _node("R6", "Verifier", ["R5"], "Run deterministic final verification"),
        ],
    }

    bounded = evaluation_budget.apply_evaluation_budget(
        graph, {"request_type": "research"}
    )

    policy = bounded["evaluation_policy"]
    assert policy["risk_tier"] == "high"
    assert policy["semantic_evaluation_budget"] == 1
    assert policy["semantic_evaluation_node_ids"] == ["R5"]
    by_id = {node["id"]: node for node in bounded["nodes"]}
    assert {node_id for node_id, node in by_id.items() if node["evaluator_gate"]["kind"] == "llm_eval"} == {"R5"}
    assert by_id["R3"]["evaluation_policy"]["decision_reason"] == "no_recursive_evaluator"
    assert by_id["R6"]["evaluator_gate"]["kind"] == "none"
    assert evaluation_budget.policy_allows_none(bounded, by_id["R6"]) is True


def test_runtime_projection_accepts_only_hash_bound_node_policy_waiver() -> None:
    node = _node("V1", "Verifier", [], "Close out")
    bounded = evaluation_budget.apply_evaluation_budget(
        {"nodes": [node]}, {"request_type": "short_implementation"}
    )
    runtime_node = bounded["nodes"][0]

    assert evaluation_budget.policy_allows_none(
        {"schema_version": "solar.scheduler_runtime_projection.v1"}, runtime_node
    ) is True
    forged = {**runtime_node, "evaluation_policy": {}}
    assert evaluation_budget.policy_allows_none(
        {"schema_version": "solar.scheduler_runtime_projection.v1"}, forged
    ) is False
