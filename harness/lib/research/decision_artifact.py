"""Construct evidence-bound decision artifacts without asserting human approval."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


EVIDENCE_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "evidence"


class DecisionArtifactError(ValueError):
    """Raised when a decision request cannot be supported by its evidence."""


@lru_cache(maxsize=2)
def _typed_evidence_validator(evidence_type: str) -> jsonschema.Draft202012Validator:
    schema_path = EVIDENCE_SCHEMA_DIR / f"{evidence_type}.v1.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise DecisionArtifactError(f"typed evidence schema is unavailable: {schema_path}") from exc
    return jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )


def _validate_typed_evidence_schema(payload: Any, evidence_type: str, evidence_id: str) -> None:
    try:
        _typed_evidence_validator(evidence_type).validate(payload)
    except jsonschema.ValidationError as exc:
        location = "/" + "/".join(str(part) for part in exc.absolute_path)
        raise DecisionArtifactError(
            f"evidence {evidence_id} fails {evidence_type}.v1 schema at {location}: {exc.message}"
        ) from exc


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
        if re.search(r"~(?:[^01]|$)", raw_token):
            raise DecisionArtifactError(f"JSON pointer contains an invalid escape: {pointer}")
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise DecisionArtifactError(f"JSON pointer has a non-canonical array index: {pointer}")
            try:
                current = current[int(token)]
            except IndexError as exc:
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
    semantics: dict[str, dict[str, Any]] = {}
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
            evidence_bytes = source_path.read_bytes()
        except OSError as exc:
            raise DecisionArtifactError(f"evidence is not readable: {raw_path}") from exc
        expected_sha256 = _require_text(
            entry.get("expected_sha256"), f"evidence[{evidence_id}].expected_sha256"
        ).lower()
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise DecisionArtifactError(f"evidence[{evidence_id}].expected_sha256 is invalid")
        actual_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
        if actual_sha256 != expected_sha256:
            raise DecisionArtifactError(
                f"evidence {evidence_id} hash mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        try:
            payload = json.loads(evidence_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DecisionArtifactError(f"evidence is not readable JSON: {raw_path}") from exc
        evidence_type = _require_text(
            entry.get("evidence_type"), f"evidence[{evidence_id}].evidence_type"
        )
        if evidence_type not in {"claim_verdict", "experiment_result"}:
            raise DecisionArtifactError(f"unknown evidence type for {evidence_id}: {evidence_type}")
        allowed_fields = {
            "evidence_id",
            "evidence_type",
            "source_path",
            "expected_sha256",
            "summary",
        }
        if evidence_type == "claim_verdict":
            allowed_fields.add("claim_id")
            allowed_fields.add("supporting_experiment_evidence_id")
        unexpected_fields = sorted(set(entry) - allowed_fields)
        if unexpected_fields:
            raise DecisionArtifactError(
                f"evidence[{evidence_id}] contains unsupported fields: {', '.join(unexpected_fields)}"
            )
        _validate_typed_evidence_schema(payload, evidence_type, evidence_id)
        if evidence_type == "claim_verdict":
            if payload.get("status") != "completed":
                raise DecisionArtifactError(f"evidence {evidence_id} claim verdict is not completed")
            claim_id = _require_text(entry.get("claim_id"), f"evidence[{evidence_id}].claim_id")
            verdicts = payload.get("outputs", {}).get("verdicts", [])
            matches = [
                (index, verdict)
                for index, verdict in enumerate(verdicts)
                if isinstance(verdict, dict) and verdict.get("claim_id") == claim_id
            ] if isinstance(verdicts, list) else []
            if len(matches) != 1:
                raise DecisionArtifactError(
                    f"evidence {evidence_id} must contain exactly one verdict for claim {claim_id}"
                )
            verdict_index, _ = matches[0]
            pointer = f"/outputs/verdicts/{verdict_index}/verdict"
            observed = _resolve_json_pointer(payload, pointer)
            expected = "supported"
            verdict = matches[0][1]
            supporting_experiment_evidence_id = _require_text(
                entry.get("supporting_experiment_evidence_id"),
                f"evidence[{evidence_id}].supporting_experiment_evidence_id",
            )
            experiment_evidence_ids_raw = verdict.get("experiment_evidence_ids")
            if not isinstance(experiment_evidence_ids_raw, list) or not experiment_evidence_ids_raw:
                raise DecisionArtifactError(
                    f"evidence[{evidence_id}].verdict.experiment_evidence_ids must not be empty"
                )
            experiment_evidence_ids = {
                _require_text(value, f"evidence[{evidence_id}].verdict.experiment_evidence_ids")
                for value in experiment_evidence_ids_raw
            }
            verdict_evidence_ids = {
                _require_text(value, f"evidence[{evidence_id}].verdict.evidence_ids")
                for value in verdict.get("evidence_ids", [])
            }
            if not experiment_evidence_ids.issubset(verdict_evidence_ids):
                raise DecisionArtifactError(
                    f"evidence[{evidence_id}].verdict.experiment_evidence_ids are not in verdict evidence_ids"
                )
            semantics[evidence_id] = {
                "type": evidence_type,
                "experiment_evidence_id": supporting_experiment_evidence_id,
                "experiment_id": _require_text(
                    verdict.get("experiment_id"), f"evidence[{evidence_id}].verdict.experiment_id"
                ),
                "experiment_evidence_ids": experiment_evidence_ids,
            }
        elif evidence_type == "experiment_result":
            if payload.get("status") != "completed":
                raise DecisionArtifactError(f"evidence {evidence_id} experiment is not completed")
            pointer = "/outputs/result/outcome"
            observed = _resolve_json_pointer(payload, pointer)
            expected = "supports"
            result = payload["outputs"]["result"]
            semantics[evidence_id] = {
                "type": evidence_type,
                "experiment_id": result["experiment_id"],
                "evidence_ids": set(result["evidence_ids"]),
            }
        else:  # pragma: no cover - guarded by the typed policy check above
            raise DecisionArtifactError(f"unknown evidence type for {evidence_id}: {evidence_type}")
        if observed != expected:
            raise DecisionArtifactError(
                f"evidence {evidence_id} is not supportive: expected {expected!r}, observed {observed!r} at {pointer}"
            )
        loaded.append(
            {
                "evidence_id": evidence_id,
                "evidence_type": evidence_type,
                "source_path": str(source_path),
                "sha256": actual_sha256,
                "semantic_locator": pointer,
                "observed_support": observed,
                "summary": _require_text(entry.get("summary"), f"evidence[{evidence_id}].summary"),
            }
        )
    loaded_by_id = {item["evidence_id"]: item for item in loaded}
    for evidence_id, semantic in semantics.items():
        if semantic["type"] != "claim_verdict":
            continue
        experiment_evidence_id = semantic["experiment_evidence_id"]
        experiment_semantic = semantics.get(experiment_evidence_id)
        if not experiment_semantic or experiment_semantic["type"] != "experiment_result":
            raise DecisionArtifactError(
                f"evidence {evidence_id} references missing typed experiment evidence: {experiment_evidence_id}"
            )
        if semantic["experiment_id"] != experiment_semantic["experiment_id"]:
            raise DecisionArtifactError(
                f"evidence {evidence_id} experiment_id does not match {experiment_evidence_id}"
            )
        if not semantic["experiment_evidence_ids"] & experiment_semantic["evidence_ids"]:
            raise DecisionArtifactError(
                f"evidence {evidence_id} has no provenance overlap with {experiment_evidence_id}"
            )
        loaded_by_id[evidence_id]["supporting_evidence_ids"] = [experiment_evidence_id]
    return loaded, indexed


def _validate_refs(values: Any, allowed: set[str], field: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise DecisionArtifactError(f"{field} must contain at least one reference")
    refs = [_require_text(value, field) for value in values]
    if len(refs) != len(set(refs)):
        raise DecisionArtifactError(f"{field} contains duplicate references")
    missing = sorted(set(refs) - allowed)
    if missing:
        raise DecisionArtifactError(f"{field} contains unknown references: {', '.join(missing)}")
    return refs


def construct_decision_artifact(
    request: dict[str, Any], *, request_path: Path, source_root: Path
) -> dict[str, Any]:
    """Validate a request and return a canonical, review-required decision artifact."""

    request_path = request_path.resolve()
    try:
        request_bytes = request_path.read_bytes()
        request_on_disk = json.loads(request_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecisionArtifactError(f"request_path is not readable decision JSON: {request_path}") from exc
    if not isinstance(request, dict) or request_on_disk != request:
        raise DecisionArtifactError("request object does not match request_path content")
    request_sha256 = hashlib.sha256(request_bytes).hexdigest()
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

    expected_assessment_pairs = {
        (alternative_id, criterion_id)
        for alternative_id in alternative_ids
        for criterion_id in criterion_ids
    }
    missing_matrix_pairs = sorted(expected_assessment_pairs - assessment_pairs)
    if missing_matrix_pairs:
        raise DecisionArtifactError(
            "assessment matrix is incomplete: "
            + ", ".join(f"{alternative_id}/{criterion_id}" for alternative_id, criterion_id in missing_matrix_pairs)
        )

    recommended_id = _require_text(recommendation.get("alternative_id"), "recommendation.alternative_id")
    if recommended_id not in alternative_ids:
        raise DecisionArtifactError("recommendation references an unknown alternative")
    recommendation_criteria = _validate_refs(
        recommendation.get("criterion_ids"), criterion_ids, "recommendation.criterion_ids"
    )
    if set(recommendation_criteria) != criterion_ids:
        raise DecisionArtifactError("recommendation.criterion_ids must cover every decision criterion")
    recommendation_evidence = _validate_refs(
        recommendation.get("evidence_ids"), evidence_ids, "recommendation.evidence_ids"
    )
    loaded_evidence_by_id = {item["evidence_id"]: item for item in loaded_evidence}
    missing_linked_recommendation_evidence = sorted(
        linked_id
        for evidence_id in recommendation_evidence
        for linked_id in loaded_evidence_by_id[evidence_id].get("supporting_evidence_ids", [])
        if linked_id not in recommendation_evidence
    )
    if missing_linked_recommendation_evidence:
        raise DecisionArtifactError(
            "recommendation.evidence_ids omit typed supporting evidence: "
            + ", ".join(missing_linked_recommendation_evidence)
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
    required_recommendation_evidence = {
        evidence_id
        for assessment in normalized_assessments
        if assessment["alternative_id"] == recommended_id
        and assessment["criterion_id"] in recommendation_criteria
        for evidence_id in assessment["evidence_ids"]
    }
    missing_recommendation_evidence = sorted(
        required_recommendation_evidence - set(recommendation_evidence)
    )
    if missing_recommendation_evidence:
        raise DecisionArtifactError(
            "recommendation.evidence_ids do not cover recommendation assessments: "
            + ", ".join(missing_recommendation_evidence)
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
            "request_sha256": request_sha256,
            "source_root": str(source_root),
        },
    }
