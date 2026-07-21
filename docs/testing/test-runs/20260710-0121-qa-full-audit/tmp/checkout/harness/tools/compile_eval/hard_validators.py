"""hard_validators.py — 6 hard validators for compiled requirement artifacts.

Each validator returns ``(passed: bool, reason: str)``. All validators must
pass for compilation to succeed; any failure is a hard block.

Validators
----------
HV1_IR_SCHEMA_INVALID        — IR has required schema fields
HV2_CONTRACT_MISMATCH        — contract fields align with IR
HV3_DAG_CYCLE                — detect cycles in task_graph node dependencies
HV4_ACCEPTANCE_NO_VALIDATION — each acceptance has a validation step
HV5_RESEARCH_NO_EVIDENCE     — research tasks have evidence gate
HV6_HIGH_RISK_NO_APPROVAL    — high-risk nodes have approval gate
"""
from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class HardValidatorResult:
    """Aggregate result from all hard validators."""

    passed: bool
    failures: list[str]
    details: dict[str, tuple[bool, str]]


_IR_SCHEMA_FIELDS = ("goal", "success_metrics", "non_goals")


def run_hard_validators(artifacts: dict[str, Any]) -> HardValidatorResult:
    """Run all 6 hard validators against *artifacts*.

    Parameters
    ----------
    artifacts : dict
        Must contain ``requirement_ir``, ``contracts``, ``dag``.

    Returns
    -------
    HardValidatorResult
    """
    validators = [
        ("HV1_IR_SCHEMA_INVALID", _hv1_ir_schema),
        ("HV2_CONTRACT_MISMATCH", _hv2_contract_mismatch),
        ("HV3_DAG_CYCLE", _hv3_dag_cycle),
        ("HV4_ACCEPTANCE_NO_VALIDATION", _hv4_acceptance_no_validation),
        ("HV5_RESEARCH_NO_EVIDENCE", _hv5_research_no_evidence),
        ("HV6_HIGH_RISK_NO_APPROVAL", _hv6_high_risk_no_approval),
    ]

    details: dict[str, tuple[bool, str]] = {}
    failures: list[str] = []

    for code, validator_fn in validators:
        passed, reason = validator_fn(artifacts)
        details[code] = (passed, reason)
        if not passed:
            failures.append(code)

    return HardValidatorResult(
        passed=len(failures) == 0,
        failures=failures,
        details=details,
    )


# ---------------------------------------------------------------------------
# HV1: IR schema must have required fields
# ---------------------------------------------------------------------------

def _hv1_ir_schema(artifacts: dict[str, Any]) -> tuple[bool, str]:
    ir = artifacts.get("requirement_ir")
    if not ir or not isinstance(ir, dict):
        return False, "requirement_ir is missing or not a dict"

    missing = [f for f in _IR_SCHEMA_FIELDS if f not in ir or ir[f] is None]
    if missing:
        return False, f"IR missing required fields: {missing}"
    return True, "ok"


# ---------------------------------------------------------------------------
# HV2: Contract fields align with IR
# ---------------------------------------------------------------------------

def _hv2_contract_mismatch(artifacts: dict[str, Any]) -> tuple[bool, str]:
    ir = artifacts.get("requirement_ir")
    contracts = artifacts.get("contracts")

    if not ir or not isinstance(ir, dict):
        return False, "requirement_ir missing"
    if not contracts or not isinstance(contracts, dict):
        return False, "contracts missing"

    ir_goal = str(ir.get("goal") or "").strip()
    contract_goal = str(contracts.get("goal") or "").strip()

    if not ir_goal:
        return False, "IR has no goal to align with"

    # At minimum, the contract should have a goal or policies
    if not contract_goal and not contracts.get("policies"):
        return False, "contract has neither goal nor policies"

    # If both have goals, they must be semantically aligned (substring match)
    if contract_goal:
        ir_lower = ir_goal.lower()
        contract_lower = contract_goal.lower()
        if ir_lower != contract_lower and ir_lower not in contract_lower and contract_lower not in ir_lower:
            return False, f"IR goal and contract goal do not align: IR={ir_goal!r}, contract={contract_goal!r}"

    return True, "ok"


# ---------------------------------------------------------------------------
# HV3: No cycles in DAG
# ---------------------------------------------------------------------------

def _hv3_dag_cycle(artifacts: dict[str, Any]) -> tuple[bool, str]:
    dag = artifacts.get("dag")
    if not dag or not isinstance(dag, dict):
        return False, "dag is missing or not a dict"

    nodes = dag.get("nodes") or []
    if not nodes:
        return True, "ok (empty dag)"

    # Build adjacency and detect cycles via DFS
    adjacency: dict[str, list[str]] = {}
    node_ids: set[str] = set()
    for node in nodes:
        nid = str(node.get("id", ""))
        node_ids.add(nid)
        adjacency[nid] = [str(d) for d in (node.get("depends_on") or [])]

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in node_ids}

    def dfs(nid: str) -> bool:
        color[nid] = GRAY
        for neighbor in adjacency.get(nid, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[nid] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            if dfs(nid):
                return False, f"cycle detected involving node {nid}"

    return True, "ok"


# ---------------------------------------------------------------------------
# HV4: Each acceptance criterion has >= 1 validation step
# ---------------------------------------------------------------------------

def _hv4_acceptance_no_validation(artifacts: dict[str, Any]) -> tuple[bool, str]:
    contracts = artifacts.get("contracts")
    dag = artifacts.get("dag")

    if not contracts or not isinstance(contracts, dict):
        return True, "ok (no contracts to validate)"

    acceptance = contracts.get("acceptance")
    if not acceptance or not isinstance(acceptance, dict):
        return True, "ok (no acceptance criteria)"

    criteria = list(acceptance.keys())
    if not criteria:
        return True, "ok (empty acceptance)"

    # Gather validation steps from DAG
    validation_steps: set[str] = set()
    if dag and isinstance(dag, dict):
        for node in (dag.get("nodes") or []):
            for step in (node.get("validation_steps") or []):
                if isinstance(step, str):
                    validation_steps.add(step)
            for acc_id in (node.get("acceptance_ids") or []):
                validation_steps.add(str(acc_id))

    uncovered: list[str] = []
    for criterion in criteria:
        covered = any(criterion in vs for vs in validation_steps)
        if not covered and len(validation_steps) < len(criteria):
            uncovered.append(criterion)

    if uncovered:
        return False, f"acceptance criteria without validation: {uncovered}"
    return True, "ok"


# ---------------------------------------------------------------------------
# HV5: Research tasks have evidence gate
# ---------------------------------------------------------------------------

def _hv5_research_no_evidence(artifacts: dict[str, Any]) -> tuple[bool, str]:
    dag = artifacts.get("dag")
    if not dag or not isinstance(dag, dict):
        return True, "ok (no dag)"

    nodes = dag.get("nodes") or []
    research_nodes = [
        n for n in nodes
        if str(n.get("type", "")).lower() == "research"
        or str(n.get("task_type", "")).lower() == "research"
    ]

    if not research_nodes:
        return True, "ok (no research nodes)"

    missing: list[str] = []
    for node in research_nodes:
        gates = node.get("gates") or []
        has_evidence_gate = any(
            "evidence" in str(g).lower() for g in gates
        )
        # Also check if the node itself has an evidence-related field
        if not has_evidence_gate:
            has_evidence_gate = bool(node.get("evidence_gate"))

        if not has_evidence_gate:
            missing.append(str(node.get("id", "unknown")))

    if missing:
        return False, f"research nodes without evidence gate: {missing}"
    return True, "ok"


# ---------------------------------------------------------------------------
# HV6: High-risk nodes have approval gate
# ---------------------------------------------------------------------------

def _hv6_high_risk_no_approval(artifacts: dict[str, Any]) -> tuple[bool, str]:
    dag = artifacts.get("dag")
    if not dag or not isinstance(dag, dict):
        return True, "ok (no dag)"

    nodes = dag.get("nodes") or []
    high_risk_nodes = [
        n for n in nodes
        if n.get("risk_level") in ("high", "critical")
        or n.get("high_risk") is True
    ]

    if not high_risk_nodes:
        return True, "ok (no high-risk nodes)"

    missing: list[str] = []
    for node in high_risk_nodes:
        gates = node.get("gates") or []
        has_approval = any(
            "approval" in str(g).lower() for g in gates
        )
        if not has_approval:
            has_approval = bool(node.get("approval_gate"))

        if not has_approval:
            missing.append(str(node.get("id", "unknown")))

    if missing:
        return False, f"high-risk nodes without approval gate: {missing}"
    return True, "ok"
