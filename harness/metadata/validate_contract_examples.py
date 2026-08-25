#!/usr/bin/env python3
"""Deterministically validate the compiler metadata examples."""

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


def validate_spans(
    spans: Any,
    raw_text: str,
    label: str,
    errors: list[str],
) -> None:
    require(isinstance(spans, list) and bool(spans), f"{label}: source spans", errors)
    if not isinstance(spans, list):
        return
    for index, span in enumerate(spans):
        valid_shape = (
            isinstance(span, list)
            and len(span) == 2
            and all(isinstance(value, int) and not isinstance(value, bool) for value in span)
        )
        require(valid_shape, f"{label}: span {index} shape", errors)
        if not valid_shape:
            continue
        start, end = span
        valid_bounds = 0 <= start < end <= len(raw_text)
        require(valid_bounds, f"{label}: span {index} bounds", errors)
        if valid_bounds:
            require(bool(raw_text[start:end].strip()), f"{label}: span {index} content", errors)


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
    raw_text_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    require(raw.get("schema_version") == "solar.raw_intent.v2", "raw schema version", errors)
    require(raw_text_digest == (raw.get("raw") or {}).get("sha256"), "raw text hash", errors)

    require(intent.get("schema_version") == "solar.intent_ir.v2", "intent schema version", errors)
    raw_ref = intent.get("raw_intent_ref") or {}
    require(raw_ref.get("raw_intent_id") == raw.get("raw_intent_id"), "intent raw id", errors)
    require(raw_ref.get("raw_text_sha256") == raw_text_digest, "intent raw text hash", errors)
    require(bool(intent.get("goals")), "intent has goals", errors)
    require(bool(intent.get("outcomes")), "intent has outcomes", errors)

    id_fields = {
        "goals": "goal_id",
        "outcomes": "outcome_id",
        "constraints": "constraint_id",
        "ambiguities": "ambiguity_id",
        "conflicts": "conflict_id",
        "unknowns": "unknown_id",
    }
    intent_ids: set[str] = set()
    rows_by_collection: dict[str, list[dict[str, Any]]] = {}
    for collection, id_field in id_fields.items():
        rows = intent.get(collection) or []
        require(isinstance(rows, list), f"intent {collection} is a list", errors)
        typed_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        require(len(typed_rows) == len(rows), f"intent {collection} objects", errors)
        rows_by_collection[collection] = typed_rows
        for row in typed_rows:
            item_id = str(row.get(id_field) or "")
            require(bool(item_id), f"{collection} id", errors)
            require(item_id not in intent_ids, f"duplicate intent id: {item_id}", errors)
            intent_ids.add(item_id)

    for collection in ("goals", "outcomes", "constraints", "ambiguities"):
        for row in rows_by_collection[collection]:
            item_id = str(row.get(id_fields[collection]) or collection)
            validate_spans(row.get("source_spans"), raw_text, item_id, errors)

    for row in rows_by_collection["goals"]:
        require(bool(str(row.get("statement") or "").strip()), f"goal statement: {row.get('goal_id')}", errors)
    for row in rows_by_collection["outcomes"]:
        outcome_id = str(row.get("outcome_id") or "")
        require(row.get("class") in {"information", "artifact", "action"}, f"outcome class: {outcome_id}", errors)
        require(bool(str(row.get("description") or "").strip()), f"outcome description: {outcome_id}", errors)
    for row in rows_by_collection["constraints"]:
        constraint_id = str(row.get("constraint_id") or "")
        require(
            row.get("category") in {"scope", "content", "limit", "prohibition", "preference", "format", "temporal"},
            f"constraint category: {constraint_id}",
            errors,
        )
        require(row.get("operator") in {"require", "prohibit", "limit", "prefer"}, f"constraint operator: {constraint_id}", errors)
        require(bool(str(row.get("statement") or "").strip()), f"constraint statement: {constraint_id}", errors)
    for row in rows_by_collection["ambiguities"]:
        ambiguity_id = str(row.get("ambiguity_id") or "")
        require(isinstance(row.get("blocking"), bool), f"ambiguity blocking: {ambiguity_id}", errors)
        require(bool(str(row.get("question") or "").strip()), f"ambiguity question: {ambiguity_id}", errors)
    for row in rows_by_collection["conflicts"]:
        conflict_id = str(row.get("conflict_id") or "")
        refs = [str(ref) for ref in row.get("refs") or []]
        require(len(refs) >= 2, f"conflict refs: {conflict_id}", errors)
        for ref in refs:
            require(ref in intent_ids, f"conflict ref {conflict_id}: {ref}", errors)
    for row in rows_by_collection["unknowns"]:
        unknown_id = str(row.get("unknown_id") or "")
        refs = [str(ref) for ref in row.get("derived_from") or []]
        require(bool(refs), f"unknown derivation: {unknown_id}", errors)
        for ref in refs:
            require(ref in intent_ids, f"unknown ref {unknown_id}: {ref}", errors)

    intent_hash = file_sha256("intent_ir.json")
    intent_validation_ref = intent_validation.get("intent_ir_ref") or {}
    require(intent_validation_ref.get("intent_ir_id") == intent.get("intent_ir_id"), "intent validation id", errors)
    require(intent_validation_ref.get("sha256") == intent_hash, "intent validation hash", errors)
    require(intent_validation.get("status") == "pass", "intent validation status", errors)
    require(
        all(row.get("status") == "pass" for row in intent_validation.get("checks") or []),
        "intent validation checks",
        errors,
    )

    fidelity_ref = fidelity.get("intent_ir_ref") or {}
    require(fidelity_ref.get("intent_ir_id") == intent.get("intent_ir_id"), "fidelity intent id", errors)
    require(fidelity_ref.get("sha256") == intent_hash, "fidelity intent hash", errors)
    require(fidelity.get("status") == "pass", "intent fidelity status", errors)
    require(all(row.get("status") == "pass" for row in fidelity.get("checks") or []), "intent fidelity checks", errors)

    require(requirement.get("schema_version") == "solar.requirement_ir.v2", "requirement schema version", errors)
    requirement_intent_ref = requirement.get("intent_ir_ref") or {}
    require(requirement_intent_ref.get("intent_ir_id") == intent.get("intent_ir_id"), "requirement intent id", errors)
    require(requirement_intent_ref.get("sha256") == intent_hash, "requirement intent hash", errors)
    requirement_rows = requirement.get("requirements") or []
    requirement_ids: set[str] = set()
    for row in requirement_rows:
        requirement_id = str(row.get("requirement_id") or "")
        require(bool(requirement_id), "requirement id", errors)
        require(requirement_id not in requirement_ids, f"duplicate requirement id: {requirement_id}", errors)
        requirement_ids.add(requirement_id)
        require(bool(str(row.get("statement") or "").strip()), f"requirement statement: {requirement_id}", errors)
        require(row.get("priority") in {"must", "should", "may"}, f"requirement priority: {requirement_id}", errors)
        refs = [str(ref) for ref in row.get("source_refs") or []]
        require(bool(refs), f"requirement source refs: {requirement_id}", errors)
        for ref in refs:
            require(ref in intent_ids, f"requirement ref {requirement_id}: {ref}", errors)
        acceptance = row.get("acceptance") or {}
        require(bool(acceptance.get("kind")), f"requirement acceptance kind: {requirement_id}", errors)
        require(bool(acceptance.get("required_values")), f"requirement acceptance values: {requirement_id}", errors)
        require(bool(row.get("required_evidence")), f"requirement evidence: {requirement_id}", errors)
        require(bool((row.get("verification") or {}).get("method")), f"requirement verifier: {requirement_id}", errors)

    requirement_hash = file_sha256("requirement_ir.json")
    requirement_validation_ref = requirement_validation.get("requirement_ir_ref") or {}
    require(requirement_validation_ref.get("requirement_ir_id") == requirement.get("requirement_ir_id"), "requirement validation id", errors)
    require(requirement_validation_ref.get("sha256") == requirement_hash, "requirement validation hash", errors)
    require(requirement_validation.get("status") == "pass", "requirement validation status", errors)
    require(
        all(row.get("status") == "pass" for row in requirement_validation.get("checks") or []),
        "requirement validation checks",
        errors,
    )
    dependency_status = {
        "intent_validation.json": intent_validation.get("status"),
        "intent_fidelity.json": fidelity.get("status"),
    }
    for dependency in requirement_validation.get("dependencies") or []:
        name = str(dependency.get("artifact") or "")
        require(dependency_status.get(name) == dependency.get("required_status"), f"requirement dependency: {name}", errors)

    coverage_ref = coverage.get("requirement_ir_ref") or {}
    require(coverage_ref.get("requirement_ir_id") == requirement.get("requirement_ir_id"), "coverage requirement id", errors)
    require(coverage_ref.get("sha256") == requirement_hash, "coverage requirement hash", errors)
    covered_intent: set[str] = set()
    covered_requirements: set[str] = set()
    for row in coverage.get("coverage") or []:
        intent_ref = str(row.get("intent_ref") or "")
        require(intent_ref in intent_ids, f"coverage intent ref: {intent_ref}", errors)
        covered_intent.add(intent_ref)
        refs = [str(ref) for ref in row.get("requirement_refs") or []]
        require(bool(refs), f"coverage requirement refs: {intent_ref}", errors)
        for ref in refs:
            require(ref in requirement_ids, f"coverage requirement ref: {ref}", errors)
            covered_requirements.add(ref)
    require(covered_intent == intent_ids, "complete intent coverage", errors)
    require(covered_requirements == requirement_ids, "all requirements used", errors)
    require(not coverage.get("uncovered_intent_refs"), "no declared coverage gaps", errors)
    require(coverage.get("coverage_rate") == 1.0, "coverage rate", errors)
    require(coverage.get("status") == "pass", "coverage status", errors)

    require(registry.get("integration_status") == "metadata_contract_only_not_wired_to_runtime", "registry integration status", errors)
    for row in registry.get("artifacts") or []:
        name = str(row.get("name") or "")
        require(bool(name) and (ROOT / name).is_file(), f"registered artifact: {name}", errors)
    for row in registry.get("design_support") or []:
        name = str(row.get("name") or "")
        require(bool(name) and (ROOT / name).is_file(), f"design support: {name}", errors)

    matrix_paths: set[str] = set()
    for row in field_matrix.get("fields") or []:
        path = str(row.get("path") or "")
        require(bool(path), "field matrix path", errors)
        require(path not in matrix_paths, f"duplicate matrix path: {path}", errors)
        matrix_paths.add(path)
        require(bool(row.get("consumers")), f"field consumers: {path}", errors)
        require(bool(row.get("decision")), f"field decision: {path}", errors)

    cases = generalization.get("cases") or []
    rules = generalization.get("acceptance_rules") or {}
    require(
        generalization.get("status") == "design_fixtures_not_yet_run_through_a_live_compiler",
        "generalization status",
        errors,
    )
    require(len(cases) >= int(rules.get("minimum_cases") or 0), "generalization case count", errors)
    case_ids: set[str] = set()
    categories: set[str] = set()
    outcome_classes: set[str] = set()
    exercised_fields: set[str] = set()
    blocking_values: set[bool] = set()
    planner_strategies: set[str] = set()
    for case in cases:
        case_id = str(case.get("case_id") or "")
        require(bool(case_id), "generalization case id", errors)
        require(case_id not in case_ids, f"duplicate generalization case: {case_id}", errors)
        case_ids.add(case_id)
        categories.add(str(case.get("category") or ""))
        require(bool(str(case.get("raw_text") or "").strip()), f"generalization raw text: {case_id}", errors)
        classes = {str(value) for value in case.get("expected_outcome_classes") or []}
        require(bool(classes), f"generalization outcome classes: {case_id}", errors)
        require(classes <= {"information", "artifact", "action"}, f"generalization outcome vocabulary: {case_id}", errors)
        outcome_classes.update(classes)
        blocking_values.add(bool(case.get("expected_blocking_issue")))
        strategy = str(case.get("expected_planner_strategy") or "")
        require(
            strategy in {
                "direct_response",
                "workflow_capsule_or_compose",
                "clarify_before_planning",
                "recompile_from_context",
            },
            f"generalization planner strategy: {case_id}",
            errors,
        )
        planner_strategies.add(strategy)
        fields = {str(value) for value in case.get("fields_exercised") or []}
        require(bool(fields), f"generalization fields: {case_id}", errors)
        exercised_fields.update(fields)
        decisions = case.get("downstream_decisions") or []
        require(bool(decisions), f"generalization decisions: {case_id}", errors)
        for decision in decisions:
            require(bool(decision.get("stage")), f"decision stage: {case_id}", errors)
            require(bool(decision.get("decision")), f"decision action: {case_id}", errors)
        if strategy == "direct_response":
            require(
                any(decision.get("stage") == "direct_response_evaluator" for decision in decisions),
                f"direct response evaluator: {case_id}",
                errors,
            )
    require(len(categories) >= 10, "generalization category diversity", errors)
    require(set(rules.get("required_outcome_classes") or []) <= outcome_classes, "required outcome classes", errors)
    require(set(rules.get("required_semantic_fields") or []) <= exercised_fields, "required semantic fields", errors)
    require(blocking_values == {False, True}, "blocking and non-blocking cases", errors)
    require("memoized_dag" not in planner_strategies, "runtime DAGs are not memoized", errors)
    require(
        bool(rules.get("reusable_work_uses_workflow_capsules_not_runtime_dags")),
        "workflow capsule reuse invariant",
        errors,
    )

    trace_artifacts = trace.get("artifacts") or []
    for row in trace_artifacts:
        name = str(row.get("name") or "")
        require((ROOT / name).is_file(), f"trace artifact: {name}", errors)
        require(file_sha256(name) == row.get("sha256"), f"trace hash: {name}", errors)
    require(trace.get("status") == "metadata_contract_verified", "trace status", errors)
    require(trace.get("integration_status") == "not_wired_to_runtime", "trace integration status", errors)

    summary = {
        "ok": not errors,
        "raw_text_characters": len(raw_text),
        "intent_items": len(intent_ids),
        "requirements": len(requirement_ids),
        "coverage_rows": len(coverage.get("coverage") or []),
        "field_consumer_rows": len(matrix_paths),
        "generalization_cases": len(cases),
        "generalization_categories": len(categories),
        "trace_artifacts": len(trace_artifacts),
        "errors": errors,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
