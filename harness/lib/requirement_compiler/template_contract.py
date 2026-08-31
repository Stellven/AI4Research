"""Program-owned Requirement template; models may supply values, not definitions."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "schemas/compiler/requirement-semantic-contract.v1.json"


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
    if contract.get("contract_id") != "solar.requirement_semantic_contract" or contract.get("version") != 1:
        raise ValueError("UNSUPPORTED_REQUIREMENT_CONTRACT")
    output_schema = _schema(contract["compiler_output_schema"])
    review_schema = _schema(contract["reviewer_output_schema"])
    Draft202012Validator.check_schema(output_schema)
    Draft202012Validator.check_schema(review_schema)
    properties = output_schema["properties"]
    if set(properties) != {"requirements", "assumptions", "discovery"}:
        raise ValueError("REQUIREMENT_EDITABLE_SURFACE_MISMATCH")
    discovery_schema = next(row for row in properties["discovery"]["anyOf"] if row.get("type") == "object")
    policy = contract["policies"]["discovery_nonempty_handoff"]
    count_schema = discovery_schema["properties"]["minimum_candidates"]
    if count_schema.get("minimum") != policy["default"]:
        raise ValueError("REQUIREMENT_COUNT_POLICY_SCHEMA_MISMATCH")
    discovery_template = _blank(discovery_schema)
    discovery_template["minimum_candidates"] = policy["default"]
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
