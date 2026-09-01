"""Compile one IntentIR artifact into one RequirementIR artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


class RequirementCompilationError(ValueError):
    """Raised when an IntentIR artifact cannot be compiled safely."""


def _require_object(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RequirementCompilationError(f"{name} must be an object")
    return payload


def _require_list(payload: dict[str, Any], name: str) -> list[Any]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise RequirementCompilationError(f"IntentIR.{name} must be an array")
    return value


def _require_text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RequirementCompilationError(f"IntentIR.{name} must be a non-empty string")
    return value.strip()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _expression_values(expression: Any) -> list[str]:
    """Recover explicit string values from the IntentIR expression language."""
    if not isinstance(expression, dict):
        return []
    values: list[str] = []
    set_values = expression.get("set")
    if isinstance(set_values, list):
        values.extend(value for value in set_values if isinstance(value, str) and value)
    literal = expression.get("literal")
    if isinstance(literal, str) and literal:
        values.append(literal)
    args = expression.get("args")
    if isinstance(args, list):
        for arg in args:
            values.extend(_expression_values(arg))
    return _dedupe(values)


def requirement_ir_id_for_intent(intent_ir_id: str) -> str:
    """Derive the stable RequirementIR identity from its admitted intent."""
    if intent_ir_id.startswith("intent-ir-"):
        return "requirement-ir-" + intent_ir_id.removeprefix("intent-ir-")
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", intent_ir_id).strip("-")
    return f"requirement-ir-{normalized}"


def _intent_acceptance_ref(intent_ir: dict[str, Any]) -> dict[str, str]:
    """Bind the accepted handoff identity without consuming evaluator output.

    The Intent Compiler admission gate deterministically names its evaluator
    artifact ``intent-acceptance-{raw_intent_id}``.  The Requirement Compiler
    records that identity, but it does not run or replace the admission gate.
    """
    raw_ref = _require_object(intent_ir.get("raw_intent_ref"), "IntentIR.raw_intent_ref")
    raw_intent_id = raw_ref.get("raw_intent_id")
    if not isinstance(raw_intent_id, str) or not raw_intent_id.strip():
        raise RequirementCompilationError(
            "IntentIR.raw_intent_ref.raw_intent_id must be a non-empty string"
        )
    return {
        "acceptance_id": f"intent-acceptance-{raw_intent_id.strip()}",
        "required_decision": "accepted",
    }


def _outcome_acceptance(outcome_class: str) -> tuple[list[str], str]:
    if outcome_class == "action":
        return (
            ["execution_record", "results", "failure_conditions", "tested_vs_not_tested"],
            "check.action_outcome_completeness.v1",
        )
    if outcome_class == "artifact":
        return (
            ["deliverable", "completeness", "supporting_evidence", "tested_vs_not_tested"],
            "check.artifact_outcome_completeness.v1",
        )
    return (
        ["answer", "supporting_evidence", "limitations"],
        "check.information_outcome_completeness.v1",
    )


def compile_requirement_ir(
    intent_ir: dict[str, Any],
    *,
    intent_ir_sha256: str,
) -> dict[str, Any]:
    """Return the RequirementIR structure defined by the Stage 3 template."""
    intent_ir = _require_object(intent_ir, "IntentIR")
    intent_ir_id = _require_text(intent_ir, "intent_ir_id")
    if not isinstance(intent_ir_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", intent_ir_sha256):
        raise RequirementCompilationError("intent_ir_sha256 must be a 64-character hexadecimal SHA-256")

    goals = [_require_object(row, "IntentIR.goals[]") for row in _require_list(intent_ir, "goals")]
    outcomes = [_require_object(row, "IntentIR.outcomes[]") for row in _require_list(intent_ir, "outcomes")]
    constraints = [_require_object(row, "IntentIR.constraints[]") for row in _require_list(intent_ir, "constraints")]
    ambiguities = [_require_object(row, "IntentIR.ambiguities[]") for row in _require_list(intent_ir, "ambiguities")]
    conflicts = [_require_object(row, "IntentIR.conflicts[]") for row in _require_list(intent_ir, "conflicts")]
    unknowns = [_require_object(row, "IntentIR.unknowns[]") for row in _require_list(intent_ir, "unknowns")]
    if not goals:
        raise RequirementCompilationError("IntentIR.goals must contain at least one goal")
    if not outcomes:
        raise RequirementCompilationError("IntentIR.outcomes must contain at least one outcome")

    goal_ids = [_require_text(row, "goal_id") for row in goals]
    all_intent_ids = set(goal_ids)
    for collection, id_field in (
        (outcomes, "outcome_id"),
        (constraints, "constraint_id"),
        (ambiguities, "ambiguity_id"),
        (conflicts, "conflict_id"),
        (unknowns, "unknown_id"),
    ):
        for row in collection:
            all_intent_ids.add(_require_text(row, id_field))

    requirements: list[dict[str, Any]] = []

    def append_requirement(
        *,
        origin: str,
        statement: str,
        source_refs: list[str],
        acceptance_kind: str,
        required_values: list[str],
        check: str,
    ) -> None:
        refs = _dedupe(source_refs)
        missing_refs = sorted(set(refs) - all_intent_ids)
        if missing_refs:
            raise RequirementCompilationError(f"Unknown IntentIR source_refs: {missing_refs}")
        requirements.append(
            {
                "requirement_id": f"R{len(requirements) + 1}",
                "origin": origin,
                "statement": statement,
                "priority": "must",
                "source_refs": refs,
                "acceptance": {
                    "kind": acceptance_kind,
                    "required_values": _dedupe(required_values),
                },
                "check": check,
                "checkable": True,
                "disposition": None,
            }
        )

    for outcome in outcomes:
        outcome_id = _require_text(outcome, "outcome_id")
        description = _require_text(outcome, "description")
        outcome_class = _require_text(outcome, "class")
        required_values, check = _outcome_acceptance(outcome_class)
        append_requirement(
            origin=f"user:{outcome_id}",
            statement=f"Produce the requested outcome: {description}",
            source_refs=goal_ids + [outcome_id],
            acceptance_kind="artifact_fields",
            required_values=required_values,
            check=check,
        )

    for constraint in constraints:
        constraint_id = _require_text(constraint, "constraint_id")
        statement = _require_text(constraint, "statement")
        values = _expression_values(constraint.get("expression"))
        if not values:
            values = ["constraint_satisfied", "supporting_evidence"]
        append_requirement(
            origin=f"user:{constraint_id}",
            statement=statement,
            source_refs=[constraint_id],
            acceptance_kind="coverage",
            required_values=values,
            check="check.intent_constraint_coverage.v1",
        )

    for unknown in unknowns:
        unknown_id = _require_text(unknown, "unknown_id")
        question = _require_text(unknown, "question")
        derived_from = unknown.get("derived_from")
        if not isinstance(derived_from, list):
            derived_from = []
        append_requirement(
            origin="user:derived",
            statement=f"Resolve or explicitly report the unresolved question: {question}",
            source_refs=[unknown_id] + [ref for ref in derived_from if isinstance(ref, str)],
            acceptance_kind="artifact_fields",
            required_values=["finding", "supporting_evidence", "unresolved_status"],
            check="check.unknown_resolution_trace.v1",
        )

    assumptions: list[dict[str, str]] = []
    for ambiguity in ambiguities:
        ambiguity_id = _require_text(ambiguity, "ambiguity_id")
        question = _require_text(ambiguity, "question")
        assumptions.append(
            {
                "source_ref": ambiguity_id,
                "statement": f"The RequirementIR must disclose how this ambiguity is resolved: {question}",
            }
        )
        append_requirement(
            origin=f"user:{ambiguity_id}",
            statement=f"Resolve or explicitly disclose the assumption for: {question}",
            source_refs=[ambiguity_id],
            acceptance_kind="artifact_fields",
            required_values=["assumption", "impact", "tested_vs_not_tested"],
            check="check.ambiguity_disclosure.v1",
        )

    referenced_goals = {ref for requirement in requirements for ref in requirement["source_refs"]}
    for goal in goals:
        goal_id = _require_text(goal, "goal_id")
        if goal_id in referenced_goals:
            continue
        append_requirement(
            origin=f"user:{goal_id}",
            statement=f"Satisfy the user goal: {_require_text(goal, 'statement')}",
            source_refs=[goal_id],
            acceptance_kind="artifact_fields",
            required_values=["goal_satisfaction", "supporting_evidence", "limitations"],
            check="check.goal_satisfaction.v1",
        )

    action_authorized = any(str(outcome.get("class")) == "action" for outcome in outcomes)
    scope = {
        "research": {
            "allowed": (
                ["source_discovery", "source_linked_analysis", "controlled_execution", "artifact_generation"]
                if action_authorized
                else ["source_discovery", "source_linked_analysis", "content_generation"]
            ),
            "forbidden": (
                ["production_deployment_without_approval", "unscoped_external_side_effects"]
                if action_authorized
                else ["unrequested_domain_experiment_execution", "production_deployment"]
            ),
            "network": "allowed_if_required_by_requirement",
        }
    }

    return {
        "schema_version": "solar.requirement_ir.v2",
        "requirement_ir_id": requirement_ir_id_for_intent(intent_ir_id),
        "intent_ir_ref": {
            "intent_ir_id": intent_ir_id,
            "sha256": intent_ir_sha256.lower(),
        },
        "intent_acceptance_ref": _intent_acceptance_ref(intent_ir),
        "requirements": requirements,
        "scope": scope,
        "assumptions": assumptions,
        "conflict_scan": {
            "result": "clean" if not conflicts else "conflict",
            "detail": None if not conflicts else "IntentIR contains unresolved conflicts.",
        },
        "approvals": [],
        "rollback": None,
    }


def compile_requirement_file(input_path: Path, output_path: Path) -> dict[str, Any]:
    encoded = input_path.read_bytes()
    intent_ir = json.loads(encoded.decode("utf-8"))
    requirement_ir = compile_requirement_ir(
        intent_ir,
        intent_ir_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(requirement_ir, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return requirement_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile IntentIR JSON into RequirementIR JSON")
    parser.add_argument("--input", required=True, type=Path, help="Path to intent_ir.json")
    parser.add_argument("--output", required=True, type=Path, help="Path for requirement_ir.json")
    parser.add_argument("--json", action="store_true", help="Print the RequirementIR artifact")
    args = parser.parse_args(argv)
    payload = compile_requirement_file(args.input, args.output)
    if args.json:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
