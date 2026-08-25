#!/usr/bin/env python3
"""Deterministically validate the compiler contract examples in this directory."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def load(name: str) -> dict[str, Any]:
    value = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain one JSON object")
    return value


def file_sha256(name: str) -> str:
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []
    raw = load("raw_intent.json")
    intent = load("intent_ir.json")
    intent_validation = load("intent_validation.json")
    fidelity = load("intent_fidelity.json")
    requirement = load("requirement_ir.json")
    requirement_validation = load("requirement_validation.json")
    coverage = load("requirement_coverage.json")
    registry = load("artifact_registry.json")
    field_matrix = load("field_consumer_matrix.json")
    generalization = load("generalization_cases.json")
    trace = load("compilation_trace.json")

    raw_text = str((raw.get("raw") or {}).get("text") or "")
    raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    require(raw.get("schema_version") == "solar.raw_intent.v2", "raw schema version", errors)
    require(raw_digest == (raw.get("raw") or {}).get("sha256"), "raw text digest", errors)
    require(
        (intent.get("raw_intent_ref") or {}).get("raw_intent_id") == raw.get("raw_intent_id"),
        "intent raw id reference",
        errors,
    )
    require(
        (intent.get("raw_intent_ref") or {}).get("raw_text_sha256") == raw_digest,
        "intent raw digest reference",
        errors,
    )

    intent_collections = (
        "objectives",
        "requested_outcomes",
        "intent_constraints",
        "ambiguities",
        "contradictions",
        "unknowns",
        "assumptions",
        "policy_signals",
    )
    id_fields = {
        "objectives": "objective_id",
        "requested_outcomes": "outcome_id",
        "intent_constraints": "constraint_id",
        "ambiguities": "ambiguity_id",
        "contradictions": "contradiction_id",
        "unknowns": "unknown_id",
        "assumptions": "assumption_id",
        "policy_signals": "signal_id",
    }
    intent_ids: set[str] = set()
    for collection in intent_collections:
        for row in intent.get(collection) or []:
            item_id = str(row.get(id_fields[collection]) or "")
            require(bool(item_id), f"{collection} item id", errors)
            require(item_id not in intent_ids, f"duplicate intent id: {item_id}", errors)
            intent_ids.add(item_id)
            quote = str((row.get("provenance") or {}).get("raw_quote") or "")
            require(bool(quote) and quote in raw_text, f"provenance quote for {item_id}", errors)

    require(intent.get("status") == "candidate", "intent example remains candidate", errors)
    require(bool(intent.get("objectives")), "at least one objective", errors)
    require(bool(intent.get("requested_outcomes")), "at least one requested outcome", errors)
    classification = intent.get("classification") or {}
    require(bool(classification.get("task_family")), "classification task family", errors)
    require(bool(classification.get("domain")), "classification domain", errors)
    for row in intent.get("objectives") or []:
        require(row.get("priority") in {"primary", "secondary"}, "objective priority", errors)
    for row in intent.get("intent_constraints") or []:
        require(row.get("operator") in {"require", "prohibit", "limit", "prefer"}, "constraint operator", errors)
        require(row.get("strength") in {"hard", "soft"}, "constraint strength", errors)
    for collection in ("ambiguities", "unknowns"):
        for row in intent.get(collection) or []:
            require(
                row.get("materiality") in {"blocking", "non_blocking", "workflow_relevant"},
                f"{collection} materiality",
                errors,
            )

    for ref in (classification.get("provenance") or {}).get("basis_refs") or []:
        require(str(ref) in intent_ids, f"classification basis ref: {ref}", errors)

    requirements = requirement.get("requirements") or []
    requirement_ids = [str(row.get("requirement_id") or "") for row in requirements]
    require(len(requirement_ids) == len(set(requirement_ids)), "requirement ids unique", errors)
    for row in requirements:
        requirement_id = str(row.get("requirement_id") or "")
        require(bool(requirement_id), "requirement id present", errors)
        for ref in row.get("source_refs") or []:
            require(str(ref) in intent_ids, f"requirement {requirement_id} source ref: {ref}", errors)
        require(bool(row.get("expected_evidence")), f"requirement {requirement_id} evidence", errors)
        require(
            bool((row.get("verification") or {}).get("registered")),
            f"requirement {requirement_id} verifier binding",
            errors,
        )

    covered_intent: set[str] = set()
    covered_requirements: set[str] = set()
    for row in coverage.get("coverage") or []:
        intent_ref = str(row.get("intent_ref") or "")
        require(intent_ref in intent_ids, f"coverage intent ref: {intent_ref}", errors)
        covered_intent.add(intent_ref)
        for ref in row.get("requirement_refs") or []:
            require(str(ref) in requirement_ids, f"coverage requirement ref: {ref}", errors)
            covered_requirements.add(str(ref))
    require(covered_intent == intent_ids, "complete intent coverage", errors)
    require(covered_requirements == set(requirement_ids), "all requirements used", errors)
    require(not coverage.get("uncovered_intent_refs"), "no declared coverage gaps", errors)
    require(float(coverage.get("coverage_rate") or 0.0) == 1.0, "coverage rate", errors)

    require(
        all(bool(row.get("passed")) for row in intent_validation.get("checks") or []),
        "intent validation claims pass",
        errors,
    )
    require(fidelity.get("status") == "pending_review", "fidelity remains pending", errors)
    dependency = requirement_validation.get("dependency") or {}
    require(dependency.get("current_status") == "pending_review", "requirement dependency status", errors)
    require(
        requirement_validation.get("status") == "structurally_valid_pending_dependency",
        "requirement status",
        errors,
    )
    requirement_checks = {
        str(row.get("check_id") or ""): bool(row.get("passed"))
        for row in requirement_validation.get("checks") or []
    }
    require(all(requirement_checks.get(key) for key in ("RV1", "RV2", "RV3", "RV4")), "requirement structural checks", errors)
    require(requirement_checks.get("RV5") is False, "intent dependency remains unsatisfied", errors)

    registry_names = {str(row.get("name") or "") for row in registry.get("artifacts") or []}
    for name in registry_names:
        require(bool(name) and (ROOT / name).is_file(), f"registry artifact exists: {name}", errors)
    support_names = {str(row.get("name") or "") for row in registry.get("design_support") or []}
    for name in support_names:
        require(bool(name) and (ROOT / name).is_file(), f"design support exists: {name}", errors)

    require(
        (field_matrix.get("integration_status") or {}).get("production_consumer") is False,
        "field matrix does not claim production wiring",
        errors,
    )
    matrix_rows = field_matrix.get("fields") or []
    matrix_fields: set[str] = set()
    for row in matrix_rows:
        field = str(row.get("field") or "")
        require(bool(field), "field matrix field name", errors)
        require(field not in matrix_fields, f"duplicate matrix field: {field}", errors)
        matrix_fields.add(field)
        require(field in intent, f"matrix field exists in IntentIR: {field}", errors)
        require(bool(row.get("source")), f"matrix source: {field}", errors)
        require(bool(row.get("consumers")), f"matrix consumers: {field}", errors)
        require(bool(row.get("decision")), f"matrix decision: {field}", errors)
        require(bool(row.get("failure_if_missing")), f"matrix failure: {field}", errors)

    cases = generalization.get("cases") or []
    acceptance_rules = generalization.get("acceptance_rules") or {}
    require(
        generalization.get("status") == "design_fixtures_not_yet_run_through_a_live_compiler",
        "generalization corpus remains honestly labelled",
        errors,
    )
    require(len(cases) >= int(acceptance_rules.get("minimum_cases") or 0), "generalization case count", errors)
    case_ids: set[str] = set()
    strategies: set[str] = set()
    exercised_fields: set[str] = set()
    blocking_values: set[bool] = set()
    categories: set[str] = set()
    for case in cases:
        case_id = str(case.get("case_id") or "")
        require(bool(case_id), "generalization case id", errors)
        require(case_id not in case_ids, f"duplicate generalization case: {case_id}", errors)
        case_ids.add(case_id)
        categories.add(str(case.get("category") or ""))
        require(bool(str(case.get("raw_text") or "").strip()), f"case raw text: {case_id}", errors)
        expected = case.get("expected") or {}
        strategy = str(expected.get("planner_strategy") or "")
        require(bool(strategy), f"case planner strategy: {case_id}", errors)
        strategies.add(strategy)
        blocking_values.add(bool(expected.get("blocking_issue")))
        fields = {str(value) for value in case.get("fields_exercised") or []}
        require(fields <= matrix_fields, f"case fields known: {case_id}", errors)
        exercised_fields.update(fields)
        require(bool(case.get("downstream_decision")), f"case downstream decision: {case_id}", errors)
        assertions = case.get("decision_assertions") or []
        require(bool(assertions), f"case decision assertions: {case_id}", errors)
        for assertion in assertions:
            require(bool(assertion.get("stage")), f"case assertion stage: {case_id}", errors)
            require(bool(assertion.get("decision")), f"case assertion decision: {case_id}", errors)
        if bool(expected.get("blocking_issue")):
            require(
                any(row.get("stage") == "intent_acceptance_gate" for row in assertions),
                f"blocking case has intent gate decision: {case_id}",
                errors,
            )
    require(len(categories) >= 10, "generalization category diversity", errors)
    require(blocking_values == {False, True}, "blocking and non-blocking cases", errors)
    require(
        set(acceptance_rules.get("required_strategies") or []) <= strategies,
        "required planner strategies exercised",
        errors,
    )
    require(
        set(acceptance_rules.get("required_issue_fields") or []) <= exercised_fields,
        "required issue fields exercised",
        errors,
    )
    semantic_fields = {
        "objectives",
        "requested_outcomes",
        "intent_constraints",
        "classification",
        "ambiguities",
        "contradictions",
        "unknowns",
        "assumptions",
        "policy_signals",
        "context_refs",
        "compilation",
    }
    require(semantic_fields <= exercised_fields, "all semantic IntentIR fields exercised", errors)

    trace_artifacts = trace.get("artifacts") or []
    for row in trace_artifacts:
        name = str(row.get("name") or "")
        require((ROOT / name).is_file(), f"trace artifact exists: {name}", errors)
        require(file_sha256(name) == row.get("sha256"), f"trace digest: {name}", errors)
    require(trace.get("status") == "awaiting_semantic_acceptance", "trace status", errors)

    summary = {
        "ok": not errors,
        "intent_items": len(intent_ids),
        "requirements": len(requirement_ids),
        "coverage_rows": len(coverage.get("coverage") or []),
        "field_consumer_rows": len(matrix_rows),
        "generalization_cases": len(cases),
        "generalization_categories": len(categories),
        "trace_artifacts": len(trace_artifacts),
        "fidelity_status": fidelity.get("status"),
        "errors": errors,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
