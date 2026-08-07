"""Structured claim/evidence scope comparison for scientific verdicts."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping


SCOPE_DIMENSIONS = (
    "population",
    "environment",
    "time_range",
    "input_domain",
    "metric",
    "confidence_uncertainty",
)

_ALIASES = {
    "population": ("population", "cohort", "subjects"),
    "environment": ("environment", "environments", "setting", "platform"),
    "time_range": ("time_range", "time_period", "date_range", "temporal_scope"),
    "input_domain": ("input_domain", "domain", "inputs", "dataset_scope"),
    "metric": ("metric", "metrics", "outcome_metric"),
    "confidence_uncertainty": (
        "confidence_uncertainty",
        "confidence",
        "uncertainty",
        "confidence_interval",
    ),
}

_BROAD_LANGUAGE = re.compile(
    r"\b(all|any|always|every|future|global|universal|worldwide)\b|100%|"
    r"所有|任何环境|始终|百分之百",
    flags=re.IGNORECASE,
)
_UNIVERSAL_VALUE = re.compile(
    r"^(all|any|every|global|universal|worldwide|unbounded|所有|任何环境|始终|百分之百|100%)$",
    flags=re.IGNORECASE,
)


def _scope_mapping(payload: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    for key in ("scope", "claim_scope", "evidence_scope", "applicability"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return payload


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    if isinstance(value, (list, tuple, set)):
        return json.dumps(sorted(_normalize_value(item) for item in value), ensure_ascii=False)
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip().lower()


def normalize_scope(payload: Mapping[str, Any] | None) -> dict[str, str]:
    source = _scope_mapping(payload)
    normalized: dict[str, str] = {}
    for dimension, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in source:
                value = _normalize_value(source.get(alias))
                if value:
                    normalized[dimension] = value
                    break
    return normalized


def _claim_text(claim: Mapping[str, Any]) -> str:
    return " ".join(
        str(claim.get(key) or "")
        for key in ("text", "claim_text", "title", "summary")
    ).strip()


def compare_claim_evidence_scope(
    claim: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare six scientific applicability dimensions.

    Lexical broad-scope terms are only a guardrail. A verdict risk is created
    from them only when structured scope evidence is absent or disagrees.
    """
    claim_scope = normalize_scope(claim)
    evidence_scope = normalize_scope(evidence)
    dimensions: dict[str, dict[str, str]] = {}
    mismatches: list[str] = []
    missing_evidence: list[str] = []

    for dimension in SCOPE_DIMENSIONS:
        claim_value = claim_scope.get(dimension, "")
        evidence_value = evidence_scope.get(dimension, "")
        if not claim_value:
            state = "not_claimed"
        elif not evidence_value:
            state = "missing_evidence"
            missing_evidence.append(dimension)
        elif dimension == "confidence_uncertainty":
            state = "available"
        elif claim_value == evidence_value:
            state = "aligned"
        elif _UNIVERSAL_VALUE.fullmatch(claim_value) and not _UNIVERSAL_VALUE.fullmatch(evidence_value):
            state = "claim_broader_than_evidence"
            mismatches.append(dimension)
        else:
            state = "different_scope"
            mismatches.append(dimension)
        dimensions[dimension] = {
            "claim": claim_value,
            "evidence": evidence_value,
            "state": state,
        }

    broad_language_detected = bool(_BROAD_LANGUAGE.search(_claim_text(claim)))
    lexical_guardrail_unresolved = broad_language_detected and not claim_scope
    risks: list[str] = []
    if mismatches:
        risks.append("Structured claim scope exceeds or differs from evidence scope: " + ", ".join(mismatches) + ".")
    if missing_evidence:
        risks.append("Structured evidence scope is missing for: " + ", ".join(missing_evidence) + ".")
    if lexical_guardrail_unresolved:
        risks.append("Broad-scope language requires structured applicability evidence before support.")

    if mismatches:
        status = "mismatch"
    elif missing_evidence or lexical_guardrail_unresolved:
        status = "insufficient"
    elif claim_scope:
        status = "aligned"
    else:
        status = "unscoped"

    return {
        "schema_version": "solar.claim_evidence_scope_comparison.v1",
        "status": status,
        "dimensions": dimensions,
        "mismatched_dimensions": mismatches,
        "missing_evidence_dimensions": missing_evidence,
        "lexical_guardrail": {
            "broad_language_detected": broad_language_detected,
            "unresolved_without_structured_scope": lexical_guardrail_unresolved,
        },
        "risks": risks,
    }
