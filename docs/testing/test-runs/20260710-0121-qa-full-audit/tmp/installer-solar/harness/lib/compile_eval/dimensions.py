"""dimensions.py — 7 evaluation dimensions for compiled requirement artifacts.

Each dimension returns a float in [0.0, 1.0].

Dimensions
----------
1. ir_schema_compliance        — RequirementIR has required fields
2. contract_completeness       — all 6 policies present + acceptance mapping
3. dag_executability           — no cycles, nodes have write_scope, gates have acceptance
4. acceptance_coverage         — each acceptance criterion has >= 1 validation step
5. prd_contract_dag_alignment  — PRD/contract/DAG goals consistent
6. trace_consistency           — planner/builder/evaluator traces mutually consistent
7. coverage_score              — delegates to requirement_coverage patterns
"""
from __future__ import annotations

from typing import Any


def evaluate(artifacts: dict[str, Any], expected: dict[str, Any]) -> dict[str, float]:
    """Evaluate compiled artifacts across 7 dimensions.

    Parameters
    ----------
    artifacts : dict
        Must contain keys: ``requirement_ir``, ``contracts``, ``dag``,
        and optionally ``traces``.
    expected : dict
        Expected values / ground truth for comparison.

    Returns
    -------
    dict[str, float]
        Mapping of dimension name → score in [0.0, 1.0].
    """
    return {
        "ir_schema_compliance": _ir_schema_compliance(artifacts, expected),
        "contract_completeness": _contract_completeness(artifacts, expected),
        "dag_executability": _dag_executability(artifacts, expected),
        "acceptance_coverage": _acceptance_coverage(artifacts, expected),
        "prd_contract_dag_alignment": _prd_contract_dag_alignment(artifacts, expected),
        "trace_consistency": _trace_consistency(artifacts, expected),
        "coverage_score": _coverage_score(artifacts, expected),
    }


# ---------------------------------------------------------------------------
# Internal dimension implementations
# ---------------------------------------------------------------------------

_IR_REQUIRED_FIELDS = ("goal", "success_metrics", "non_goals")
_CONTRACT_POLICY_KEYS = (
    "intake_policy", "requirement_ir_policy", "contract_compiler_policy",
    "dag_compiler_policy", "evidence_policy", "handoff_policy",
)


def _ir_schema_compliance(artifacts: dict[str, Any], _expected: dict[str, Any]) -> float:
    """Check RequirementIR has required fields (goal, success_metrics, non_goals)."""
    ir = artifacts.get("requirement_ir")
    if not ir or not isinstance(ir, dict):
        return 0.0
    present = sum(1 for f in _IR_REQUIRED_FIELDS if f in ir and ir[f] is not None)
    return present / len(_IR_REQUIRED_FIELDS)


def _contract_completeness(artifacts: dict[str, Any], _expected: dict[str, Any]) -> float:
    """Check all 6 policies present + acceptance mapping exists."""
    contracts = artifacts.get("contracts")
    if not contracts or not isinstance(contracts, dict):
        return 0.0

    score_parts = 0.0
    total_parts = 7.0  # 6 policies + 1 acceptance mapping

    policies = contracts.get("policies")
    if isinstance(policies, dict):
        present = sum(1 for k in _CONTRACT_POLICY_KEYS if k in policies)
        score_parts += present / 6.0 * 6.0

    acceptance = contracts.get("acceptance")
    if isinstance(acceptance, dict) and len(acceptance) > 0:
        score_parts += 1.0

    return score_parts / total_parts


def _dag_executability(artifacts: dict[str, Any], _expected: dict[str, Any]) -> float:
    """Check no cycles, nodes have write_scope, gates have acceptance."""
    dag = artifacts.get("dag")
    if not dag or not isinstance(dag, dict):
        return 0.0

    nodes = dag.get("nodes") or []
    if not nodes:
        return 0.0

    checks = 0.0
    total = 3.0

    # Check 1: no cycles via DFS
    if not _has_cycle(nodes):
        checks += 1.0

    # Check 2: nodes have write_scope
    scope_count = sum(1 for n in nodes if n.get("write_scope"))
    checks += scope_count / len(nodes)

    # Check 3: gates have acceptance
    gate_nodes = [n for n in nodes if n.get("type") == "gate"]
    if gate_nodes:
        acc_count = sum(1 for g in gate_nodes if g.get("acceptance"))
        checks += acc_count / len(gate_nodes)
    else:
        checks += 1.0  # no gates = trivially satisfied

    return checks / total


def _acceptance_coverage(artifacts: dict[str, Any], _expected: dict[str, Any]) -> float:
    """Each acceptance criterion has >= 1 validation step."""
    contracts = artifacts.get("contracts")
    dag = artifacts.get("dag")

    if not contracts or not isinstance(contracts, dict):
        return 0.0

    acceptance = contracts.get("acceptance")
    if not acceptance or not isinstance(acceptance, dict):
        return 0.0

    criteria = list(acceptance.keys())
    if not criteria:
        return 1.0  # nothing to cover

    # Gather validation steps from DAG nodes
    validation_steps: set[str] = set()
    if dag and isinstance(dag, dict):
        for node in (dag.get("nodes") or []):
            for step in (node.get("validation_steps") or []):
                if isinstance(step, str):
                    validation_steps.add(step)
            for acc_id in (node.get("acceptance_ids") or []):
                validation_steps.add(acc_id)

    covered = 0
    for criterion in criteria:
        # Check if any validation step references this criterion
        if any(criterion in vs for vs in validation_steps):
            covered += 1
        elif len(validation_steps) >= len(criteria):
            covered += 1  # at least as many steps as criteria

    if len(criteria) == 0:
        return 1.0
    return covered / len(criteria)


def _prd_contract_dag_alignment(artifacts: dict[str, Any], _expected: dict[str, Any]) -> float:
    """PRD goals match contract goals match DAG goals."""
    ir = artifacts.get("requirement_ir") or {}
    contracts = artifacts.get("contracts") or {}
    dag = artifacts.get("dag") or {}

    ir_goal = str(ir.get("goal") or "").strip().lower()
    contract_goal = str(contracts.get("goal") or "").strip().lower()

    dag_goals: list[str] = []
    for node in (dag.get("nodes") or []):
        g = str(node.get("goal") or "").strip().lower()
        if g:
            dag_goals.append(g)

    if not ir_goal:
        return 0.0

    checks = 0.0
    total = 2.0

    # IR goal vs contract goal
    if contract_goal and ir_goal in contract_goal or contract_goal in ir_goal:
        checks += 1.0
    elif contract_goal == ir_goal:
        checks += 1.0

    # IR goal vs DAG goals
    if dag_goals:
        if any(ir_goal in dg or dg in ir_goal for dg in dag_goals):
            checks += 1.0
    else:
        checks += 0.5  # no DAG goals = partial

    return checks / total


def _trace_consistency(artifacts: dict[str, Any], _expected: dict[str, Any]) -> float:
    """Planner/builder/evaluator traces mutually consistent."""
    traces = artifacts.get("traces")
    if not traces or not isinstance(traces, dict):
        return 0.5  # no traces = neutral score

    roles = ("planner", "builder", "evaluator")
    present_roles = [r for r in roles if r in traces]
    if len(present_roles) < 2:
        return 0.5  # insufficient data

    # Check that referenced nodes overlap
    node_sets: dict[str, set[str]] = {}
    for role in present_roles:
        role_trace = traces[role]
        if isinstance(role_trace, dict):
            nodes = set(str(n) for n in (role_trace.get("nodes") or []))
        elif isinstance(role_trace, list):
            nodes = set(str(n) for n in role_trace)
        else:
            nodes = set()
        node_sets[role] = nodes

    # Pairwise overlap check
    pairs_checked = 0
    pairs_overlap = 0
    role_list = list(node_sets.keys())
    for i in range(len(role_list)):
        for j in range(i + 1, len(role_list)):
            pairs_checked += 1
            a, b = node_sets[role_list[i]], node_sets[role_list[j]]
            if a and b and (a & b):
                pairs_overlap += 1

    if pairs_checked == 0:
        return 0.5
    return pairs_overlap / pairs_checked


def _coverage_score(artifacts: dict[str, Any], expected: dict[str, Any]) -> float:
    """Delegate to requirement_coverage patterns.

    Uses the same logic as lib/requirement_coverage.py: derive requirements
    from the IR, check mapped nodes in the DAG, and compute coverage ratio.
    """
    ir = artifacts.get("requirement_ir") or {}
    dag = artifacts.get("dag") or {}
    nodes = dag.get("nodes") or []

    if not nodes:
        return 0.0

    # Derive requirements (mirroring requirement_coverage._derive_requirements)
    requirements = ir.get("requirements") or []
    if not requirements:
        # Fallback: single default requirement
        requirements = [{"id": "REQ-000"}]

    req_ids = [r.get("id", f"REQ-{i}") for i, r in enumerate(requirements)]
    results = dag.get("node_results") or {}

    total_reqs = len(req_ids)
    done_count = 0
    for req_id in req_ids:
        mapped = [
            n for n in nodes
            if req_id in (n.get("requirement_ids") or [])
        ]
        if not mapped:
            mapped = nodes  # fallback: all nodes

        statuses = [
            str((results.get(str(n.get("id"))) or {}).get("status") or n.get("status") or "pending")
            for n in mapped
        ]
        if statuses and all(s == "passed" for s in statuses):
            done_count += 1

    return done_count / total_reqs if total_reqs > 0 else 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_cycle(nodes: list[dict[str, Any]]) -> bool:
    """Detect cycles in a DAG defined by node ``depends_on`` edges."""
    adjacency: dict[str, list[str]] = {}
    node_ids: set[str] = set()
    for node in nodes:
        nid = str(node.get("id", ""))
        node_ids.add(nid)
        adjacency[nid] = [str(d) for d in (node.get("depends_on") or [])]

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in node_ids}

    def dfs(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency.get(node_id, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node_id] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            if dfs(nid):
                return True
    return False
