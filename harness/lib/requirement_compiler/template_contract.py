"""Program-owned Requirement template; models may supply values, not definitions."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "schemas/compiler/requirement-semantic-contract.v3.json"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _schema(relative: str) -> dict[str, Any]:
    path = (ROOT / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(ROOT):
        raise ValueError("CONTRACT_SCHEMA_PATH_OUTSIDE_RUNTIME")
    return json.loads(path.read_text(encoding="utf-8"))


def _blank(schema: dict[str, Any]) -> Any:
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    if schema.get("type") == "object":
        return {key: _blank(value) for key, value in schema["properties"].items()}
    if schema.get("type") == "array":
        return []
    return None


def make_template(intent: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("contract_id") != "solar.requirement_semantic_contract" or contract.get("version") != 3:
        raise ValueError("UNSUPPORTED_REQUIREMENT_CONTRACT")
    output_schema = _schema(contract["compiler_output_schema"])
    review_schema = _schema(contract["reviewer_output_schema"])
    Draft202012Validator.check_schema(output_schema)
    Draft202012Validator.check_schema(review_schema)
    properties = output_schema["properties"]
    if set(properties) != {
        "requirements",
        "assumptions",
        "discovery",
        "selection_authority",
        "delivery_manifest",
    }:
        raise ValueError("REQUIREMENT_EDITABLE_SURFACE_MISMATCH")
    # Freeze allowed identities into the schema actually sent to the provider.
    source_ids = sorted({row[key] for collection, key in (
        ("goals", "goal_id"), ("outcomes", "outcome_id"), ("constraints", "constraint_id"),
        ("unknowns", "unknown_id"), ("ambiguities", "ambiguity_id"), ("conflicts", "conflict_id")
    ) for row in intent.get(collection, [])})
    check_ids = sorted({row["check_id"] for row in registry.get("checks", [])})
    if not source_ids or not check_ids:
        raise ValueError("REQUIREMENT_EMPTY_SOURCE_OR_CHECK_REGISTRY")
    properties["requirements"]["items"]["properties"]["check"]["enum"] = check_ids

    def bind_refs(node):
        if isinstance(node, dict):
            fields = node.get("properties", {})
            if "source_refs" in fields:
                fields["source_refs"]["items"]["enum"] = source_ids
            if "source_ref" in fields:
                fields["source_ref"]["enum"] = source_ids
            for value in node.values():
                bind_refs(value)
        elif isinstance(node, list):
            for value in node:
                bind_refs(value)

    bind_refs(output_schema)
    review_fields = review_schema["properties"]["errors"]["items"]["properties"]
    review_fields["rule_id"]["enum"] = [row["id"] for row in contract["fidelity_rules"]]
    review_fields["evidence_refs"]["items"]["enum"] = source_ids + [
        row["policy_id"] for row in contract["policies"].values()]
    Draft202012Validator.check_schema(output_schema)
    Draft202012Validator.check_schema(review_schema)
    discovery_schema = next(row for row in properties["discovery"]["anyOf"] if row.get("type") == "object")
    policy = contract["policies"]["discovery_nonempty_handoff"]
    count_schema = discovery_schema["properties"]["minimum_candidates"]
    if count_schema.get("minimum") != policy["default"]:
        raise ValueError("REQUIREMENT_COUNT_POLICY_SCHEMA_MISMATCH")
    discovery_template = _blank(discovery_schema)
    discovery_template["minimum_candidates"] = policy["default"]
    delivery_schema = next(
        row for row in properties["delivery_manifest"]["anyOf"] if row.get("type") == "object"
    )
    fixed = {
        "contract": contract,
        "compiler_output_schema": output_schema,
        "reviewer_output_schema": review_schema,
        "evaluation_check_registry": copy.deepcopy(registry),
        "source_constraints": copy.deepcopy(intent.get("constraints", [])),
        "item_templates": {
            "requirements": _blank(properties["requirements"]["items"]),
            "assumptions": _blank(properties["assumptions"]["items"]),
            "discovery": discovery_template,
            "selection_authority": _blank(properties["selection_authority"]["items"]),
            "delivery_manifest_file": _blank(delivery_schema["properties"]["files"]["items"]),
        },
    }
    return {
        "contract_ref": {"contract_id": contract["contract_id"], "version": contract["version"],
                         "definition_sha256": _digest(contract), "snapshot_sha256": _digest(fixed)},
        "read_only": fixed,
        "values": _blank(output_schema),
    }


def fill_template(template: dict[str, Any], values: Any) -> dict[str, Any]:
    """Reject extra/protected fields; never deep-merge arbitrary model objects."""
    fixed = template["read_only"]
    if _digest(fixed) != template["contract_ref"]["snapshot_sha256"]:
        raise ValueError("REQUIREMENT_READ_ONLY_TEMPLATE_CHANGED")
    errors = list(Draft202012Validator(fixed["compiler_output_schema"]).iter_errors(values))
    if errors:
        raise ValueError("REQUIREMENT_VALUES_INVALID: " + "; ".join(
            f"{list(error.path)}: {error.message}" for error in errors
        ))
    filled = copy.deepcopy(template)
    filled["values"] = copy.deepcopy(values)
    return filled


def selection_authority_defects(values: dict[str, Any]) -> list[str]:
    """Check identity/target completeness, never infer authority from topic words."""
    discovery = values.get("discovery") or {}
    required = {}
    for name in ("inclusion_criteria", "exclusion_criteria"):
        for index, row in enumerate(discovery.get(name, [])):
            required[f"/discovery/{name}/{index}"] = set(row["source_refs"])
    for index, row in enumerate(discovery.get("coverage", [])):
        if row["required"]:
            required[f"/discovery/coverage/{index}/required"] = set()
    for name, value in discovery.get("time_range", {}).items():
        if value is not None:
            required[f"/discovery/time_range/{name}"] = set()
    if discovery.get("minimum_candidates", 1) > 1:
        required["/discovery/minimum_candidates"] = set()
    authorizations = values.get("selection_authority", [])
    targets = [row["field_path"] for row in authorizations]
    errors = []
    if len(targets) != len(set(targets)) or set(targets) != set(required):
        errors.append("SELECTION_AUTHORITY_TARGET_MISMATCH: missing=" + str(sorted(set(required)-set(targets)))
                      + " extra=" + str(sorted(set(targets)-set(required))))
    for row in authorizations:
        if not required.get(row["field_path"], set()).issubset(row["source_refs"]):
            errors.append("SELECTION_AUTHORITY_SOURCE_MISMATCH: " + row["field_path"])
    return errors


def delivery_manifest_defects(values: dict[str, Any]) -> list[str]:
    """Validate deterministic path, identity, and serialization invariants."""

    manifest = values.get("delivery_manifest")
    if manifest is None:
        return []
    errors: list[str] = []

    def safe_relative(raw: Any, label: str) -> str:
        original = str(raw or "").replace("\\", "/")
        value = original.strip("/")
        path = Path(value)
        if (
            not value
            or original.startswith("/")
            or re.match(r"^[A-Za-z]:", original)
            or Path(str(raw or "")).is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            errors.append(f"DELIVERY_PATH_UNSAFE: {label}")
        return value

    safe_relative(manifest.get("output_root"), "/delivery_manifest/output_root")
    rows = manifest.get("files") or []
    paths = [safe_relative(row.get("relative_path"), f"/delivery_manifest/files/{index}/relative_path")
             for index, row in enumerate(rows)]
    file_ids = [str(row.get("file_id") or "") for row in rows]
    if len(paths) != len(set(paths)):
        errors.append("DELIVERY_FILE_PATH_DUPLICATE")
    if len(file_ids) != len(set(file_ids)):
        errors.append("DELIVERY_FILE_ID_DUPLICATE")
    suffixes = {
        "text/markdown": {".md", ".markdown"},
        "text/csv": {".csv"},
        "application/json": {".json"},
        "text/html": {".html", ".htm"},
        "text/plain": {".txt"},
    }
    for index, row in enumerate(rows):
        suffix = Path(paths[index]).suffix.lower()
        media_type = str(row.get("media_type") or "")
        if suffix not in suffixes.get(media_type, set()):
            errors.append(f"DELIVERY_MEDIA_TYPE_EXTENSION_MISMATCH: /delivery_manifest/files/{index}")
        if row.get("required_fields") and media_type not in {"text/csv", "application/json"}:
            errors.append(f"DELIVERY_REQUIRED_FIELDS_UNSUPPORTED: /delivery_manifest/files/{index}")
    return errors


def review_defects(template: dict[str, Any], review: Any, values: dict[str, Any]) -> list[str]:
    errors = [f"REVIEW_SCHEMA_INVALID: {list(e.path)}: {e.message}" for e in
              Draft202012Validator(template["read_only"]["reviewer_output_schema"]).iter_errors(review)]
    if errors:
        return errors
    if review["accepted"] != (not review["errors"]):
        errors.append("REVIEW_VERDICT_INCONSISTENT")
    for defect in review["errors"]:
        pointer = defect["field_path"]
        try:
            if not pointer.startswith("/"):
                raise ValueError("not a JSON pointer")
            value = values
            for raw in pointer[1:].split("/"):
                key = raw.replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
        except (KeyError, ValueError, TypeError, IndexError):
            errors.append("REVIEW_FIELD_NOT_FOUND: " + pointer)
        errors.append(json.dumps(defect, ensure_ascii=False, sort_keys=True))
    return errors
