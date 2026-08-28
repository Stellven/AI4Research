"""Risk-bounded semantic-evaluation policy for Planner-generated DAGs.

The Planner may propose any valid topology, but it does not decide how many
independent model reviews Solar buys.  This module applies that deterministic
budget after semantic planning and before plan certification.
"""

from __future__ import annotations

import copy
from typing import Any


POLICY_ID = "risk_bounded_semantic_evaluation_v1"
POLICY_SCHEMA = "solar.evaluation_budget.v1"
PROOF_GATE_ID = "policy.proof_obligations.v1"

# One independent LLM evaluator is the global ceiling.  Deterministic schema,
# hash, proof-obligation, and coverage aggregation may still run on every node;
# risk changes what the final evaluator must inspect, not how many models vote.
_RISK_BUDGETS = {"low": 1, "medium": 1, "high": 1, "critical": 1}
_EVALUATOR_OPERATOR_MARKERS = ("critic", "verifier", "evaluator")
_HIGH_RISK_REQUESTS = {
    "research",
    "security_sensitive",
    "academic_critique",
    "root_cause_debug",
    "soft_hw_opt",
}


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def is_recursive_evaluator_node(node: dict[str, Any]) -> bool:
    """Return true when a node already *is* an evaluator/verifier."""
    operator = _text(node.get("logical_operator"))
    role = _text((node.get("allowed_operators") or {}).get("role"))
    return role == "evaluator" or any(marker in operator for marker in _EVALUATOR_OPERATOR_MARKERS)


def _declared_risk(requirement_ir: dict[str, Any], graph: dict[str, Any]) -> str:
    hints = requirement_ir.get("planner_hints") if isinstance(requirement_ir.get("planner_hints"), dict) else {}
    constraints = requirement_ir.get("constraints") if isinstance(requirement_ir.get("constraints"), dict) else {}
    policy = graph.get("risk_policy") if isinstance(graph.get("risk_policy"), dict) else {}
    for value in (
        requirement_ir.get("risk_tier"),
        hints.get("risk_tier"),
        constraints.get("risk_tier"),
        graph.get("risk_tier"),
        policy.get("risk_tier"),
    ):
        normalized = _text(value)
        if normalized in _RISK_BUDGETS:
            return normalized
    return ""


def risk_tier(requirement_ir: dict[str, Any], graph: dict[str, Any]) -> str:
    explicit = _declared_risk(requirement_ir, graph)
    if explicit:
        return explicit
    request_type = _text(requirement_ir.get("request_type"))
    nodes = [node for node in graph.get("nodes") or [] if isinstance(node, dict)]
    if request_type in _HIGH_RISK_REQUESTS or graph.get("research_mode") is True:
        return "high"
    effects = {
        _text(effect)
        for node in nodes
        for effect in ((node.get("operator_requirements") or {}).get("effects") or [])
    }
    if "irreversible" in effects or "security" in request_type:
        return "high"
    if len(nodes) >= 4 or effects & {"write", "execute", "network"}:
        return "medium"
    return "low"


def _descendant_counts(nodes: list[dict[str, Any]]) -> dict[str, int]:
    children: dict[str, list[str]] = {
        _text(node.get("id")): [] for node in nodes if _text(node.get("id"))
    }
    for node in nodes:
        node_id = _text(node.get("id"))
        for dependency in node.get("depends_on") or []:
            dependency_id = _text(dependency)
            if dependency_id in children:
                children[dependency_id].append(node_id)

    def visit(node_id: str, seen: set[str]) -> set[str]:
        found: set[str] = set()
        for child in children.get(node_id, []):
            if child in seen:
                continue
            found.add(child)
            found.update(visit(child, seen | {child}))
        return found

    return {node_id: len(visit(node_id, {node_id})) for node_id in children}


def _node_score(node: dict[str, Any], descendants: dict[str, int], index: int) -> tuple[int, int]:
    node_id = _text(node.get("id"))
    operator = _text(node.get("logical_operator"))
    goal = _text(node.get("goal"))
    outputs = " ".join(_text(value) for value in node.get("outputs") or [])
    combined = f"{operator} {goal} {outputs}"
    score = index
    if descendants.get(node_id, 0) == 0:
        score += 80
    if any(token in combined for token in ("final", "report", "deliver", "synthesi", "implementation")):
        score += 45
    if any(token in combined for token in ("audit", "contradiction", "evidence review", "critique")):
        score += 35
    if any(token in operator for token in ("scout", "architect", "planner")):
        score -= 30
    return score, index


def _research_targets(nodes: list[dict[str, Any]], eligible: list[dict[str, Any]]) -> list[str]:
    """Prefer the final report, then an evidence audit if policy ever expands."""
    targets: list[str] = []
    for node in reversed(eligible):
        combined = " ".join(
            [
                _text(node.get("goal")),
                " ".join(_text(value) for value in node.get("outputs") or []),
            ]
        )
        if "final.md" in combined or "final report" in combined or "cited report" in combined:
            node_id = str(node.get("id"))
            if node_id not in targets:
                targets.append(node_id)
            break
    for node in eligible:
        combined = " ".join(
            [
                _text(node.get("id")),
                _text(node.get("goal")),
                " ".join(_text(value) for value in node.get("outputs") or []),
            ]
        )
        if any(token in combined for token in ("evidence audit", "contradiction", "unsupported assumption", "gaps.md")):
            node_id = str(node.get("id"))
            if node_id not in targets:
                targets.append(node_id)
            break
    return targets


def select_semantic_targets(
    requirement_ir: dict[str, Any], graph: dict[str, Any], *, tier: str
) -> list[str]:
    nodes = [node for node in graph.get("nodes") or [] if isinstance(node, dict)]
    eligible = [node for node in nodes if not is_recursive_evaluator_node(node)]
    if not eligible:
        return []
    budget = _RISK_BUDGETS[tier]
    request_type = _text(requirement_ir.get("request_type"))
    is_research = request_type == "research" or graph.get("research_mode") is True
    selected = _research_targets(nodes, eligible) if is_research else []
    if not selected:
        descendants = _descendant_counts(nodes)
        ranked = sorted(
            enumerate(eligible),
            key=lambda item: _node_score(item[1], descendants, item[0]),
            reverse=True,
        )
        selected = [str(node.get("id")) for _, node in ranked[:budget]]
    return selected[:budget]


def apply_evaluation_budget(
    graph: dict[str, Any], requirement_ir: dict[str, Any]
) -> dict[str, Any]:
    """Return a copy with a certified semantic-review budget applied."""
    bounded = copy.deepcopy(graph)
    nodes = [node for node in bounded.get("nodes") or [] if isinstance(node, dict)]
    tier = risk_tier(requirement_ir, bounded)
    budget = _RISK_BUDGETS[tier]
    semantic_node_ids = select_semantic_targets(requirement_ir, bounded, tier=tier)
    semantic_set = set(semantic_node_ids)
    recursive_ids: list[str] = []
    deterministic_ids: list[str] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        recursive = is_recursive_evaluator_node(node)
        semantic = node_id in semantic_set and not recursive
        if recursive:
            recursive_ids.append(node_id)
        if semantic:
            node["evaluator_gate"] = {
                "kind": "llm_eval",
                "on_fail": "repair_once_then_fail",
            }
            node["max_repair_attempts"] = min(1, int(node.get("max_repair_attempts") or 1))
            reason = "targeted_semantic_review"
        else:
            node["evaluator_gate"] = {"kind": "none", "on_fail": "fail"}
            node["max_repair_attempts"] = 0
            deterministic_ids.append(node_id)
            reason = "no_recursive_evaluator" if recursive else "covered_by_bounded_final_review"
        node["evaluation_policy"] = {
            "policy_id": POLICY_ID,
            "risk_tier": tier,
            "semantic_review_required": semantic,
            "decision_reason": reason,
        }
    bounded["evaluation_policy"] = {
        "schema_version": POLICY_SCHEMA,
        "policy_id": POLICY_ID,
        "risk_tier": tier,
        "semantic_evaluation_budget": budget,
        "semantic_evaluation_node_ids": semantic_node_ids,
        "deterministic_only_node_ids": deterministic_ids,
        "recursive_evaluator_node_ids": recursive_ids,
    }
    return bounded


def policy_allows_none(graph: dict[str, Any], node: dict[str, Any]) -> bool:
    graph_policy = graph.get("evaluation_policy") if isinstance(graph.get("evaluation_policy"), dict) else {}
    node_policy = node.get("evaluation_policy") if isinstance(node.get("evaluation_policy"), dict) else {}
    node_id = str(node.get("id") or "")
    node_policy_valid = bool(
        node_policy.get("policy_id") == POLICY_ID
        and node_policy.get("semantic_review_required") is False
        and str((node.get("evaluator_gate") or {}).get("kind") or "") == "none"
    )
    if not node_policy_valid:
        return False
    if graph_policy:
        return bool(
            graph_policy.get("policy_id") == POLICY_ID
            and node_id in set(graph_policy.get("deterministic_only_node_ids") or [])
        )
    # SchedulerInput is hash-bound runtime authority and carries the certified
    # node policy even though its compact runtime projection omits graph-level
    # planning metadata.
    return str(graph.get("schema_version") or "") == "solar.scheduler_runtime_projection.v1"
