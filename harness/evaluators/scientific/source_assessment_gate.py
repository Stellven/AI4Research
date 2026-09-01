#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import finish, outputs, require_non_empty_list, run_cli, validate_schema

SCHEMA = "research_source_assessment.v1"


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    values = outputs(payload)
    assessments = require_non_empty_list(values.get("assessments"), "outputs.assessments", reasons)
    by_id: dict[str, dict[str, Any]] = {}
    for index, assessment in enumerate(assessments):
        if not isinstance(assessment, dict):
            reasons.append(f"assessments[{index}] must be an object")
            continue
        source_id = str(assessment.get("source_id") or "")
        if not source_id or source_id in by_id:
            reasons.append(f"assessments[{index}].source_id must be unique and non-empty")
            continue
        by_id[source_id] = assessment
        decision = str(assessment.get("decision") or "")
        relevance = assessment.get("relevance") if isinstance(assessment.get("relevance"), dict) else {}
        credibility = assessment.get("credibility") if isinstance(assessment.get("credibility"), dict) else {}
        ingestion = assessment.get("ingestion") if isinstance(assessment.get("ingestion"), dict) else {}
        if decision == "selected" and (
            relevance.get("status") != "relevant"
            or credibility.get("status") != "credible"
            or ingestion.get("status") not in {"parsed", "partial"}
        ):
            reasons.append(
                f"assessments[{index}] selected a source without relevant, credible, parsed/partial evidence"
            )

    expected = {
        "selected": set(values.get("selected_source_ids") or []),
        "excluded": set(values.get("excluded_source_ids") or []),
        "unresolved": set(values.get("unresolved_source_ids") or []),
    }
    for decision, source_ids in expected.items():
        actual = {source_id for source_id, row in by_id.items() if row.get("decision") == decision}
        if source_ids != actual:
            reasons.append(f"outputs.{decision}_source_ids does not match assessment decisions")
    if expected["unresolved"] and not values.get("unresolved_questions"):
        reasons.append("unresolved source decisions require outputs.unresolved_questions")
    return finish(payload, reasons, warnings, path=path)


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
