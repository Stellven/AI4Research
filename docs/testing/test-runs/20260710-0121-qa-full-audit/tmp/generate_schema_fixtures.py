from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"external ref unsupported in fixture generator: {ref}")
    value: Any = root
    for part in ref[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def synthesize(schema: dict[str, Any], root: dict[str, Any], depth: int = 0) -> Any:
    if depth > 40:
        return None
    if "$ref" in schema:
        return synthesize(resolve_ref(root, schema["$ref"]), root, depth + 1)
    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    if schema.get("examples"):
        return schema["examples"][0]
    if schema.get("enum"):
        return schema["enum"][0]
    if schema.get("oneOf"):
        return synthesize(schema["oneOf"][0], root, depth + 1)
    if schema.get("anyOf"):
        return synthesize(schema["anyOf"][0], root, depth + 1)
    if schema.get("allOf"):
        combined: dict[str, Any] = {}
        for part in schema["allOf"]:
            resolved = resolve_ref(root, part["$ref"]) if "$ref" in part else part
            for key, value in resolved.items():
                if key == "properties":
                    combined.setdefault("properties", {}).update(value)
                elif key == "required":
                    combined["required"] = list(dict.fromkeys(combined.get("required", []) + value))
                else:
                    combined[key] = value
        return synthesize(combined, root, depth + 1)
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((value for value in schema_type if value != "null"), schema_type[0])
    if schema_type == "object" or "properties" in schema:
        result = {}
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            result[key] = synthesize(properties.get(key, {"type": "string"}), root, depth + 1)
        return result
    if schema_type == "array":
        count = max(0, int(schema.get("minItems", 0)))
        return [synthesize(schema.get("items", {}), root, depth + 1) for _ in range(count)]
    if schema_type == "boolean":
        return False
    if schema_type == "integer":
        return int(schema.get("minimum", 0))
    if schema_type == "number":
        return float(schema.get("minimum", 0))
    if schema_type == "null":
        return None
    if schema.get("format") == "date-time":
        return "2026-07-10T00:00:00Z"
    if schema.get("format") in {"uri", "uri-reference"}:
        return "https://example.invalid/fixture"
    pattern = schema.get("pattern", "")
    if re.search(r"\{64\}", pattern):
        return "0" * 64
    minimum = max(1, int(schema.get("minLength", 1)))
    return ("fixture" * ((minimum // 7) + 1))[:minimum]


def main() -> None:
    checkout = Path(sys.argv[1]).resolve()
    fixtures = Path(sys.argv[2]).resolve()
    schema_dir = checkout / "harness/schemas/evidence"
    output_dir = fixtures / "evidence/schemas"
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for schema_path in sorted(schema_dir.glob("*.v1.schema.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        candidate = synthesize(schema, schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        valid_errors = sorted(validator.iter_errors(candidate), key=lambda error: list(error.path))
        invalid_candidate = {}
        invalid_errors = list(validator.iter_errors(invalid_candidate))
        stem = schema_path.name.replace(".schema.json", "")
        valid_path = output_dir / f"{stem}.valid.json"
        invalid_path = output_dir / f"{stem}.invalid.json"
        valid_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
        invalid_path.write_text("{}\n", encoding="utf-8")
        results.append({
            "schema": schema_path.name,
            "schema_id": schema.get("$id"),
            "valid_fixture": str(valid_path.relative_to(fixtures)),
            "validates": not valid_errors,
            "valid_errors": [error.message for error in valid_errors[:10]],
            "invalid_fixture": str(invalid_path.relative_to(fixtures)),
            "invalid_rejected": bool(invalid_errors),
            "invalid_error_count": len(invalid_errors),
        })
    summary = {
        "schema": "ai4research_schema_fixture_validation.v1",
        "fixture_source": True,
        "schema_count": len(results),
        "valid_fixture_pass_count": sum(result["validates"] for result in results),
        "invalid_fixture_rejected_count": sum(result["invalid_rejected"] for result in results),
        "results": results,
    }
    (fixtures / "evidence/schema-fixture-validation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("schema_count", "valid_fixture_pass_count", "invalid_fixture_rejected_count")}))


if __name__ == "__main__":
    main()
