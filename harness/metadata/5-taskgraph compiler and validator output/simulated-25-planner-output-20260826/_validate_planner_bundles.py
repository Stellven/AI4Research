#!/usr/bin/env python3
"""Deterministically evaluate the simulated planner bundles against metadata templates."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[2]
STAGE2 = HARNESS / "metadata" / "2-intent compiler output" / "live-25-prompt-pipeline-20260826"
STAGE3 = HARNESS / "metadata" / "3-requirements compiler output" / "live-25-prompt-pipeline-20260826"
STAGE4 = HARNESS / "metadata" / "4-elastic planner output" / "simulated-25-planner-output-20260826"
STAGE5 = HERE
REPORT = STAGE5 / "evaluations" / "planner_contract_evaluation.json"

STRATEGY_KEYS = {
    "schema_version", "strategy_id", "requirement_ir_ref", "strategy", "base_workflow",
    "base_version", "parameters", "topology_changes", "smallest_sufficient_reason", "artifact_role",
}
PLAN_KEYS = {
    "schema_version", "plan_ir_id", "strategy_ref", "planning_catalog_ref", "nodes", "artifact_role",
}
NODE_KEYS = {
    "id", "logical_operator", "capsule", "alternatives", "depends_on", "consumes", "produces",
    "obligation_ids", "gate",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _registered_capsules() -> set[str]:
    paths = [
        HARNESS / "config" / "capability-capsules.registry.yaml",
        *list((HARNESS / "capability-capsules").glob("*.yaml")),
        *list((HARNESS / "config" / "capability-capsules").glob("*.yaml")),
    ]
    found: set[str] = set()
    pattern = re.compile(r"^\s*capability_capsule_id:\s*['\"]?([^'\"\s]+)", re.MULTILINE)
    for path in paths:
        if path.is_file():
            found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def _evaluate_planned(case_id: str, operators: dict[str, Any], capsules: set[str]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    strategy_path = STAGE4 / case_id / "strategy.json"
    plan_path = STAGE5 / case_id / "plan_ir.json"
    requirement_path = STAGE3 / case_id / "requirement_ir.json"
    if not all(path.is_file() for path in (strategy_path, plan_path, requirement_path)):
        return {"case_id": case_id, "result": "FAIL", "errors": ["required planner artifact missing"]}
    strategy = _read(strategy_path)
    plan = _read(plan_path)
    requirement = _read(requirement_path)
    if set(strategy) != STRATEGY_KEYS:
        errors.append("strategy.json top-level keys differ from the metadata template")
    if set(plan) != PLAN_KEYS:
        errors.append("plan_ir.json top-level keys differ from the metadata template")
    if strategy.get("schema_version") != "solar.workflow_strategy.v1":
        errors.append("strategy schema_version mismatch")
    if plan.get("schema_version") != "solar.plan_ir.v1":
        errors.append("plan_ir schema_version mismatch")
    if strategy.get("requirement_ir_ref", {}).get("sha256") != _sha(requirement_path):
        errors.append("requirement_ir_ref hash mismatch")
    if plan.get("strategy_ref", {}).get("sha256") != _sha(strategy_path):
        errors.append("strategy_ref hash mismatch")
    nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
    node_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(node_ids) != len(set(node_ids)):
        errors.append("duplicate node id")
    seen: set[str] = set()
    covered: set[str] = set()
    unregistered: set[str] = set()
    unavailable: set[str] = set()
    for node in nodes:
        if set(node) != NODE_KEYS:
            errors.append(f"node {node.get('id')} keys differ from the metadata template")
        dependencies = set(node.get("depends_on") or [])
        if not dependencies <= seen:
            errors.append(f"node {node.get('id')} has a missing or forward dependency")
        seen.add(str(node.get("id")))
        covered.update(str(item) for item in node.get("obligation_ids") or [])
        capsule = str(node.get("capsule") or "")
        if capsule not in capsules:
            unregistered.add(capsule)
        alternatives = node.get("alternatives") or []
        if not alternatives:
            errors.append(f"node {node.get('id')} has no ordered operator alternatives")
        for operator_id in alternatives:
            operator = operators.get(operator_id)
            if not operator or not operator.get("enabled") or not operator.get("available") or operator.get("deprecated"):
                unavailable.add(str(operator_id))
    expected = {str(item["requirement_id"]) for item in requirement["requirements"]}
    if covered != expected:
        errors.append(f"obligation coverage mismatch: expected={sorted(expected)} actual={sorted(covered)}")
    direct_response = case_id.startswith(("21-", "22-", "23-", "24-", "25-"))
    if direct_response:
        if unregistered != {"cap.unregistered.direct-response"}:
            errors.append("direct-response capability gap was not represented exactly")
        warnings.append("not dispatchable: no registered direct-response capability capsule")
    elif unregistered:
        errors.append(f"unregistered capability capsules: {sorted(unregistered)}")
    if unavailable:
        errors.append(f"operator alternatives are unavailable or missing: {sorted(unavailable)}")
    return {
        "case_id": case_id,
        "result": "FAIL" if errors else "PASS_WITH_KNOWN_LIMITATION" if warnings else "PASS",
        "dispatchable": not direct_response and not errors,
        "errors": errors,
        "warnings": warnings,
    }


def _evaluate_halt(case_id: str) -> dict[str, Any]:
    errors: list[str] = []
    halt_path = STAGE4 / case_id / "planning_halt.json"
    acceptance_path = STAGE2 / case_id / "intent_acceptance.json"
    if not halt_path.is_file() or not acceptance_path.is_file():
        errors.append("clarification halt or acceptance artifact missing")
    else:
        halt = _read(halt_path)
        acceptance = _read(acceptance_path)
        if acceptance.get("decision") != "needs_clarification":
            errors.append("planning halt does not follow a needs_clarification decision")
        if halt.get("dispatch_allowed") is not False:
            errors.append("planning halt incorrectly permits dispatch")
        if halt.get("intent_acceptance_ref", {}).get("sha256") != _sha(acceptance_path):
            errors.append("intent_acceptance_ref hash mismatch")
        if (STAGE3 / case_id / "requirement_ir.json").exists():
            errors.append("RequirementIR must not exist after clarification halt")
    return {
        "case_id": case_id,
        "result": "FAIL" if errors else "PASS",
        "dispatchable": False,
        "errors": errors,
        "warnings": [],
    }


def main() -> int:
    run_manifest = _read(STAGE4 / "run_manifest.json")
    operators = _read(HARNESS / "config" / "physical-operators.json")["operators"]
    capsules = _registered_capsules()
    results = []
    for case in run_manifest["cases"]:
        case_id = str(case["case_id"])
        if case["terminal_status"] == "planning_not_entered":
            results.append(_evaluate_halt(case_id))
        else:
            results.append(_evaluate_planned(case_id, operators, capsules))
    report = {
        "schema_version": "solar.planner_contract_evaluation.v1",
        "artifact_role": "evaluator_output_not_planner_output",
        "case_count": len(results),
        "pass_count": sum(item["result"] == "PASS" for item in results),
        "pass_with_known_limitation_count": sum(
            item["result"] == "PASS_WITH_KNOWN_LIMITATION" for item in results
        ),
        "fail_count": sum(item["result"] == "FAIL" for item in results),
        "dispatchable_count": sum(bool(item["dispatchable"]) for item in results),
        "checks": [
            "metadata template field shape", "content-addressed references", "DAG ordering",
            "requirement obligation coverage", "registered capability binding", "ordered operator availability",
            "clarification halt enforcement",
        ],
        "cases": results,
    }
    _write(REPORT, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["fail_count"] == 0 and report["case_count"] == 25 else 1


if __name__ == "__main__":
    raise SystemExit(main())
