"""Execute explicit retrieval criteria without deriving semantics from prose."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def validate_contract(contract: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator
    schema = Path(__file__).resolve().parents[3] / "schemas/compiler/retrieval-contract.v1.schema.json"
    Draft202012Validator(json.loads(schema.read_text(encoding="utf-8"))).validate(contract)
    bounds = contract["time_range"]
    if bounds["start_year"] and bounds["end_year"] and bounds["start_year"] > bounds["end_year"]:
        raise ValueError("RETRIEVAL_DATE_RANGE_REVERSED")


def _text(candidate: dict[str, Any], field: str = "title_abstract") -> str:
    metadata = candidate.get("metadata") or {}
    if field == "publication_type":
        return str(candidate.get("publication_type") or metadata.get("publication_type") or "")
    return " ".join(str(candidate.get(key) or metadata.get(key) or "")
                    for key in ("title", "abstract", "content_summary", "summary"))


def _matches(text: str, terms: list[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I) for term in terms)


def filter_candidates(contract: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_contract(contract)
    accepted, decisions = [], []
    for candidate in candidates:
        reasons = []
        for rule in contract["inclusion_criteria"]:
            if not _matches(_text(candidate, rule["field"]), rule["any_of"]):
                reasons.append("inclusion_not_evidenced:" + ",".join(rule["any_of"]))
        for rule in contract["exclusion_criteria"]:
            if _matches(_text(candidate, rule["field"]), rule["any_of"]):
                reasons.append("explicit_exclusion:" + ",".join(rule["any_of"]))
        bounds = contract["time_range"]
        year = candidate.get("year") or (candidate.get("metadata") or {}).get("year")
        if bounds["start_year"] or bounds["end_year"]:
            try:
                year = int(str(year)[:4])
                if (bounds["start_year"] and year < bounds["start_year"]) or (bounds["end_year"] and year > bounds["end_year"]):
                    reasons.append("outside_publication_time_range")
            except (TypeError, ValueError):
                reasons.append("publication_year_unknown")
        if not _text(candidate).strip():
            reasons.append("candidate_text_missing")
        if not reasons:
            accepted.append(candidate)
        decisions.append({"candidate_id": str(candidate.get("source_id") or candidate.get("candidate_id") or candidate.get("title") or ""),
                          "accepted": not reasons, "reasons": reasons})
    aggregate = "\n".join(_text(row) for row in accepted)
    missing = [row for row in contract["coverage"] if not _matches(aggregate, row["any_of"])]
    blocking = ["required_coverage_missing:" + row["label"] for row in missing if row["required"]]
    if len(accepted) < contract["minimum_candidates"]:
        blocking.append("minimum_candidates_not_met")
    return accepted, {"schema": "solar.retrieval_audit.v1", "contract_id": contract["contract_id"],
                      "status": "passed" if not blocking else "failed", "candidate_count": len(accepted),
                      "decisions": decisions, "aggregate_coverage_missing": missing,
                      "blocking_reasons": blocking,
                      "limitations": ["No evidence retrieved for: " + row["label"] for row in missing]}
