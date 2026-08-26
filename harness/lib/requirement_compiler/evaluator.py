"""Deterministic RequirementIR format evaluation against the metadata template."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "metadata"
    / "3-requirements compiler output"
    / "requirement_ir"
    / "requirement_ir.json"
)


def _shape_defects(template: Any, payload: Any, path: str = "$") -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    if isinstance(template, dict):
        if not isinstance(payload, dict):
            return [{"path": path, "code": "TYPE_MISMATCH", "expected": "object", "actual": type(payload).__name__}]
        missing = sorted(set(template) - set(payload))
        extra = sorted(set(payload) - set(template))
        if missing:
            defects.append({"path": path, "code": "MISSING_FIELDS", "fields": missing})
        if extra:
            defects.append({"path": path, "code": "EXTRA_FIELDS", "fields": extra})
        for key in sorted(set(template) & set(payload)):
            defects.extend(_shape_defects(template[key], payload[key], f"{path}.{key}"))
        return defects
    if isinstance(template, list):
        if not isinstance(payload, list):
            return [{"path": path, "code": "TYPE_MISMATCH", "expected": "array", "actual": type(payload).__name__}]
        if path == "$.requirements" and template and not payload:
            defects.append({"path": path, "code": "EMPTY_REQUIRED_COLLECTION"})
        if template:
            for index, item in enumerate(payload):
                defects.extend(_shape_defects(template[0], item, f"{path}[{index}]"))
        return defects
    if template is None:
        if payload is not None:
            defects.append({"path": path, "code": "TYPE_MISMATCH", "expected": "null", "actual": type(payload).__name__})
        return defects
    if isinstance(template, bool):
        expected_type = bool
    elif isinstance(template, int):
        expected_type = int
    elif isinstance(template, float):
        expected_type = (int, float)
    elif isinstance(template, str):
        expected_type = str
    else:
        expected_type = type(template)
    if not isinstance(payload, expected_type):
        defects.append(
            {
                "path": path,
                "code": "TYPE_MISMATCH",
                "expected": type(template).__name__,
                "actual": type(payload).__name__,
            }
        )
    return defects


def evaluate_requirement_ir_format(
    requirement_ir: dict[str, Any],
    *,
    intent_ir: dict[str, Any] | None = None,
    intent_ir_sha256: str | None = None,
    intent_acceptance: dict[str, Any] | None = None,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
) -> dict[str, Any]:
    template = json.loads(template_path.read_text(encoding="utf-8"))
    defects = _shape_defects(template, requirement_ir)

    schema_version = requirement_ir.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        defects.append({"path": "$.schema_version", "code": "NONEMPTY_STRING_REQUIRED"})

    requirements = requirement_ir.get("requirements")
    if isinstance(requirements, list):
        requirement_ids = [row.get("requirement_id") for row in requirements if isinstance(row, dict)]
        if len(requirement_ids) != len(set(requirement_ids)):
            defects.append({"path": "$.requirements", "code": "DUPLICATE_REQUIREMENT_ID"})
        for index, requirement in enumerate(requirements):
            if not isinstance(requirement, dict):
                continue
            acceptance = requirement.get("acceptance")
            if isinstance(acceptance, dict) and not acceptance.get("required_values"):
                defects.append(
                    {
                        "path": f"$.requirements[{index}].acceptance.required_values",
                        "code": "EMPTY_REQUIRED_VALUES",
                    }
                )

    if intent_ir is not None:
        expected_id = intent_ir.get("intent_ir_id")
        actual_ref = requirement_ir.get("intent_ir_ref")
        if not isinstance(actual_ref, dict) or actual_ref.get("intent_ir_id") != expected_id:
            defects.append({"path": "$.intent_ir_ref.intent_ir_id", "code": "INTENT_REFERENCE_MISMATCH"})
        if intent_ir_sha256 is not None and (
            not isinstance(actual_ref, dict) or actual_ref.get("sha256") != intent_ir_sha256.lower()
        ):
            defects.append({"path": "$.intent_ir_ref.sha256", "code": "INTENT_DIGEST_MISMATCH"})

        raw_ref = intent_ir.get("raw_intent_ref")
        raw_intent_id = raw_ref.get("raw_intent_id") if isinstance(raw_ref, dict) else None
        expected_acceptance_id = (
            f"intent-acceptance-{raw_intent_id}"
            if isinstance(raw_intent_id, str) and raw_intent_id
            else None
        )
        acceptance_ref = requirement_ir.get("intent_acceptance_ref")
        if (
            not isinstance(acceptance_ref, dict)
            or acceptance_ref.get("acceptance_id") != expected_acceptance_id
        ):
            defects.append(
                {
                    "path": "$.intent_acceptance_ref.acceptance_id",
                    "code": "INTENT_ACCEPTANCE_REFERENCE_MISMATCH",
                }
            )
        if (
            not isinstance(acceptance_ref, dict)
            or acceptance_ref.get("required_decision") != "accepted"
        ):
            defects.append(
                {
                    "path": "$.intent_acceptance_ref.required_decision",
                    "code": "ACCEPTED_DECISION_REQUIRED",
                }
            )

        if intent_acceptance is not None:
            if (
                intent_acceptance.get("decision") != "accepted"
                or intent_acceptance.get("requirement_compiler_handoff_allowed") is not True
            ):
                defects.append(
                    {
                        "path": "$.intent_acceptance_ref",
                        "code": "INTENT_ACCEPTANCE_GATE_NOT_OPEN",
                    }
                )
            if (
                not isinstance(acceptance_ref, dict)
                or acceptance_ref.get("acceptance_id")
                != intent_acceptance.get("acceptance_id")
            ):
                defects.append(
                    {
                        "path": "$.intent_acceptance_ref.acceptance_id",
                        "code": "INTENT_ACCEPTANCE_ARTIFACT_MISMATCH",
                    }
                )
            admitted_intent_ref = intent_acceptance.get("intent_ir_ref")
            if not isinstance(admitted_intent_ref, dict) or (
                admitted_intent_ref.get("intent_ir_id") != expected_id
                or (
                    intent_ir_sha256 is not None
                    and admitted_intent_ref.get("sha256") != intent_ir_sha256.lower()
                )
            ):
                defects.append(
                    {
                        "path": "$.intent_acceptance_ref",
                        "code": "INTENT_ACCEPTANCE_BINDING_MISMATCH",
                    }
                )

        intent_ids = set()
        for collection, id_field in (
            ("goals", "goal_id"),
            ("outcomes", "outcome_id"),
            ("constraints", "constraint_id"),
            ("ambiguities", "ambiguity_id"),
            ("conflicts", "conflict_id"),
            ("unknowns", "unknown_id"),
        ):
            for row in intent_ir.get(collection, []):
                if isinstance(row, dict) and isinstance(row.get(id_field), str):
                    intent_ids.add(row[id_field])
        for index, requirement in enumerate(requirement_ir.get("requirements", [])):
            if not isinstance(requirement, dict):
                continue
            refs = requirement.get("source_refs")
            if not isinstance(refs, list) or not refs:
                defects.append({"path": f"$.requirements[{index}].source_refs", "code": "SOURCE_REFS_REQUIRED"})
                continue
            unknown_refs = sorted(set(refs) - intent_ids)
            if unknown_refs:
                defects.append(
                    {
                        "path": f"$.requirements[{index}].source_refs",
                        "code": "UNKNOWN_INTENT_REFERENCE",
                        "refs": unknown_refs,
                    }
                )

    checks = [
        {
            "check_id": "RF1",
            "kind": "template_recursive_shape",
            "status": "pass" if not [item for item in defects if item["code"] in {"TYPE_MISMATCH", "MISSING_FIELDS", "EXTRA_FIELDS", "EMPTY_REQUIRED_COLLECTION"}] else "fail",
        },
        {
            "check_id": "RF2",
            "kind": "requirement_identifier_and_acceptance_integrity",
            "status": "pass" if not [item for item in defects if item["code"] in {"DUPLICATE_REQUIREMENT_ID", "EMPTY_REQUIRED_VALUES"}] else "fail",
        },
        {
            "check_id": "RF3",
            "kind": "intent_reference_integrity",
            "status": "pass" if not [item for item in defects if "REFERENCE" in item["code"] or "DIGEST" in item["code"] or item["code"] == "SOURCE_REFS_REQUIRED"] else "fail",
        },
        {
            "check_id": "RF4",
            "kind": "intent_acceptance_handoff_integrity",
            "status": "pass" if not [item for item in defects if item["code"] in {"INTENT_ACCEPTANCE_REFERENCE_MISMATCH", "ACCEPTED_DECISION_REQUIRED", "INTENT_ACCEPTANCE_GATE_NOT_OPEN", "INTENT_ACCEPTANCE_ARTIFACT_MISMATCH", "INTENT_ACCEPTANCE_BINDING_MISMATCH"}] else "fail",
        },
    ]
    return {
        "schema_version": "solar.requirement_ir_format_evaluation.v1",
        "template": str(template_path),
        "status": "pass" if not defects else "fail",
        "checks": checks,
        "defects": defects,
    }
