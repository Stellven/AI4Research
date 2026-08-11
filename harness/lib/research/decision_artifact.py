"""Construct evidence-bound decision artifacts without asserting human approval."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DecisionArtifactError(ValueError):
    """Raised when a decision request cannot be supported by its evidence."""


def _require_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DecisionArtifactError(f"{field} must be a non-empty string")
    return text


def _require_unique(items: list[dict[str, Any]], key: str, field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise DecisionArtifactError(f"{field}[{index}] must be an object")
        item_id = _require_text(item.get(key), f"{field}[{index}].{key}")
        if item_id in indexed:
            raise DecisionArtifactError(f"duplicate {key}: {item_id}")
        indexed[item_id] = item
    return indexed


def _resolve_json_pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise DecisionArtifactError(f"JSON pointer must start with '/': {pointer}")
    current = payload
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise DecisionArtifactError(f"JSON pointer does not resolve: {pointer}") from exc
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise DecisionArtifactError(f"JSON pointer does not resolve: {pointer}")
    return current


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _load_evidence(
    entries: list[dict[str, Any]], *, source_root: Path
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    indexed = _require_unique(entries, "evidence_id", "evidence")
    loaded: list[dict[str, Any]] = []
    for evidence_id, entry in indexed.items():
        raw_path = _require_text(entry.get("source_path"), f"evidence[{evidence_id}].source_path")
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = source_root / source_path
        source_path = source_path.resolve()
        if not _inside(source_path, source_root):
            raise DecisionArtifactError(f"evidence path escapes source root: {raw_path}")
        if not source_path.is_file():
            raise DecisionArtifactError(f"evidence file is missing: {raw_path}")
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DecisionArtifactError(f"evidence is not readable JSON: {raw_path}") from exc
        pointer = _require_text(entry.get("support_pointer"), f"evidence[{evidence_id}].support_pointer")
        supported_values = entry.get("supported_values")
        if not isinstance(supported_values, list) or not supported_values:
            raise DecisionArtifactError(f"evidence[{evidence_id}].supported_values must be non-empty")
        observed = _resolve_json_pointer(payload, pointer)
        if observed not in supported_values:
            raise DecisionArtifactError(
                f"evidence {evidence_id} is not supportive: observed {observed!r} at {pointer}"
            )
        loaded.append(
            {
                "evidence_id": evidence_id,
                "source_path": str(source_path),
                "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "support_pointer": pointer,
                "observed_support": observed,
                "summary": _require_text(entry.get("summary"), f"evidence[{evidence_id}].summary"),
            }
        )
    return loaded, indexed


def _validate_refs(values: Any, allowed: set[str], field: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise DecisionArtifactError(f"{field} must contain at least one reference")
    refs = [_require_text(value, field) for value in values]
    missing = sorted(set(refs) - allowed)
    if missing:
        raise DecisionArtifactError(f"{field} contains unknown references: {', '.join(missing)}")
    return refs


def construct_decision_artifact(
    request: dict[str, Any], *, request_path: Path, source_root: Path
) -> dict[str, Any]:
    """Validate a request and return a canonical, review-required decision artifact."""

    if request.get("schema") != "decision_request.v1":
        raise DecisionArtifactError("schema must be decision_request.v1")
    forbidden_state = sorted({"decision_status", "review", "approval"} & set(request))
    if forbidden_state:
        raise DecisionArtifactError(
            "constructor input cannot assert review or approval state: " + ", ".join(forbidden_state)
        )
    source_root = source_root.resolve()
    alternatives = request.get("alternatives")
    criteria = request.get("criteria")
    evidence = request.get("evidence")
    assessments = request.get("assessments")
    risks = request.get("risks")
    recommendation = request.get("recommendation")
    if not isinstance(alternatives, list) or len(alternatives) < 2:
        raise DecisionArtifactError("alternatives must contain at least two options")
    if not isinstance(criteria, list) or not criteria:
        raise DecisionArtifactError("criteria must contain at least one criterion")
    if not isinstance(evidence, list) or not evidence:
        raise DecisionArtifactError("evidence must contain at least one source")
    if not isinstance(assessments, list) or not assessments:
        raise DecisionArtifactError("assessments must not be empty")
    if not isinstance(risks, list) or not risks:
        raise DecisionArtifactError("risks must not be empty")
    if not isinstance(recommendation, dict):
        raise DecisionArtifactError("recommendation must be an object")

    alternative_index = _require_unique(alternatives, "alternative_id", "alternatives")
    criterion_index = _require_unique(criteria, "criterion_id", "criteria")
    loaded_evidence, evidence_index = _load_evidence(evidence, source_root=source_root)
    evidence_ids = set(evidence_index)
    alternative_ids = set(alternative_index)
    criterion_ids = set(criterion_index)

    normalized_alternatives = [
        {
            "alternative_id": alternative_id,
            "title": _require_text(item.get("title"), f"alternatives[{alternative_id}].title"),
            "description": _require_text(item.get("description"), f"alternatives[{alternative_id}].description"),
        }
        for alternative_id, item in alternative_index.items()
    ]
    normalized_criteria = []
    total_weight = 0.0
    for criterion_id, item in criterion_index.items():
        weight = item.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or weight <= 0:
            raise DecisionArtifactError(f"criteria[{criterion_id}].weight must be positive")
        total_weight += float(weight)
        normalized_criteria.append(
            {
                "criterion_id": criterion_id,
                "name": _require_text(item.get("name"), f"criteria[{criterion_id}].name"),
                "weight": float(weight),
            }
        )
    if abs(total_weight - 1.0) > 1e-6:
        raise DecisionArtifactError("criterion weights must sum to 1.0")

    normalized_assessments = []
    assessment_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(assessments):
        if not isinstance(item, dict):
            raise DecisionArtifactError(f"assessments[{index}] must be an object")
        alternative_id = _require_text(item.get("alternative_id"), f"assessments[{index}].alternative_id")
        criterion_id = _require_text(item.get("criterion_id"), f"assessments[{index}].criterion_id")
        if alternative_id not in alternative_ids or criterion_id not in criterion_ids:
            raise DecisionArtifactError(f"assessments[{index}] references an unknown option or criterion")
        pair = (alternative_id, criterion_id)
        if pair in assessment_pairs:
            raise DecisionArtifactError(f"duplicate assessment: {alternative_id}/{criterion_id}")
        assessment_pairs.add(pair)
        score = item.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= float(score) <= 5:
            raise DecisionArtifactError(f"assessments[{index}].score must be between 0 and 5")
        normalized_assessments.append(
            {
                "alternative_id": alternative_id,
                "criterion_id": criterion_id,
                "score": float(score),
                "rationale": _require_text(item.get("rationale"), f"assessments[{index}].rationale"),
                "evidence_ids": _validate_refs(item.get("evidence_ids"), evidence_ids, f"assessments[{index}].evidence_ids"),
            }
        )

    recommended_id = _require_text(recommendation.get("alternative_id"), "recommendation.alternative_id")
    if recommended_id not in alternative_ids:
        raise DecisionArtifactError("recommendation references an unknown alternative")
    recommendation_criteria = _validate_refs(
        recommendation.get("criterion_ids"), criterion_ids, "recommendation.criterion_ids"
    )
    recommendation_evidence = _validate_refs(
        recommendation.get("evidence_ids"), evidence_ids, "recommendation.evidence_ids"
    )
    missing_assessments = sorted(
        criterion_id
        for criterion_id in recommendation_criteria
        if (recommended_id, criterion_id) not in assessment_pairs
    )
    if missing_assessments:
        raise DecisionArtifactError(
            "recommendation is missing criterion assessments: " + ", ".join(missing_assessments)
        )

    normalized_risks = []
    _require_unique(risks, "risk_id", "risks")
    for index, item in enumerate(risks):
        normalized_risks.append(
            {
                "risk_id": _require_text(item.get("risk_id"), f"risks[{index}].risk_id"),
                "description": _require_text(item.get("description"), f"risks[{index}].description"),
                "mitigation": _require_text(item.get("mitigation"), f"risks[{index}].mitigation"),
                "evidence_ids": _validate_refs(item.get("evidence_ids"), evidence_ids, f"risks[{index}].evidence_ids"),
            }
        )

    limitations = request.get("limitations")
    unresolved = request.get("unresolved_review_items")
    if not isinstance(limitations, list) or not limitations:
        raise DecisionArtifactError("limitations must not be empty")
    if not isinstance(unresolved, list) or not unresolved:
        raise DecisionArtifactError("unresolved_review_items must not be empty before human review")
    request_path = request_path.resolve()
    return {
        "schema": "decision_artifact.v1",
        "decision_id": _require_text(request.get("decision_id"), "decision_id"),
        "title": _require_text(request.get("title"), "title"),
        "problem": _require_text(request.get("problem"), "problem"),
        "decision_status": "review_required",
        "alternatives": normalized_alternatives,
        "criteria": normalized_criteria,
        "evidence_links": loaded_evidence,
        "assessments": normalized_assessments,
        "risks": normalized_risks,
        "recommendation": {
            "alternative_id": recommended_id,
            "rationale": _require_text(recommendation.get("rationale"), "recommendation.rationale"),
            "criterion_ids": recommendation_criteria,
            "evidence_ids": recommendation_evidence,
        },
        "limitations": [_require_text(item, "limitations") for item in limitations],
        "review": {
            "status": "pending",
            "unresolved_items": [_require_text(item, "unresolved_review_items") for item in unresolved],
            "reviewed_by": None,
            "review_evidence": [],
        },
        "approval": {
            "status": "not_requested",
            "approved_by": None,
            "approval_evidence": [],
        },
        "next_action": "Obtain independent review and explicit human approval before executing the recommendation.",
        "provenance": {
            "constructor": "harness.lib.research.decision_artifact.construct_decision_artifact",
            "constructed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request_path": str(request_path),
            "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
            "source_root": str(source_root),
        },
    }
