"""Provider wire schemas are projections; the source contract stays authoritative.

Only schema nodes are traversed (never enum/default payloads or property names).
Unsupported constraints remain in the prompt and in mandatory local validation.
No defaults, resource requirements, or semantic repairs are invented here.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Any

from jsonschema import Draft202012Validator


class OutputContractError(ValueError):
    pass


def _type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    raise OutputContractError("Structured enum/const values require a JSON envelope")


def project_schema(source: dict[str, Any], profile: str = "openai") -> dict[str, Any]:
    """Compile to a conservative provider subset, without mutating source.

    OpenAI requires all keys; optional keys gain a nullable wire representation.
    Claude/Gemini retain optionality. Numeric/string/cardinality constraints are
    enforced on return, not assumed supported by every registered model version.
    Free-form objects and unsupported combinators fail before a provider call;
    callers may explicitly select json_object/prompt_json for those contracts.
    """
    if profile not in {"openai", "anthropic", "gemini"}:
        raise OutputContractError(f"Unknown schema profile: {profile}")
    Draft202012Validator.check_schema(source)
    validator = Draft202012Validator(source)

    def check_acyclic_refs(node: Any, chain: tuple[str, ...] = ()) -> None:
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            ref = node["$ref"]
            if ref in chain:
                mode = "json_object" if profile == "gemini" else "prompt_json"
                raise OutputContractError(f"{profile} native recursive schema is outside the supported adapter subset; use configured {mode} mode")
            if ref.startswith("#/"):
                target = source
                for part in ref[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
                check_acyclic_refs(target, (*chain, ref))
        for key in ("properties", "$defs", "definitions"):
            for child in node.get(key, {}).values():
                check_acyclic_refs(child, chain)
        for key in ("anyOf", "oneOf", "prefixItems"):
            for child in node.get(key, []):
                check_acyclic_refs(child, chain)
        check_acyclic_refs(node.get("items"), chain)

    if profile in {"gemini", "anthropic"}:
        check_acyclic_refs(source)

    def visit(node: Any, path: str) -> dict[str, Any]:
        if not isinstance(node, dict) or not node:
            raise OutputContractError(f"Unconstrained schema at {path}")
        unsupported = set(node) & {"allOf", "not", "if", "then", "else", "patternProperties",
                                    "dependentSchemas", "$dynamicRef", "$recursiveRef"}
        if unsupported:
            raise OutputContractError(f"Unsupported schema structure at {path}: {sorted(unsupported)}")
        out = {key: deepcopy(node[key]) for key in ("type", "description", "enum") if key in node}
        if "const" in node:
            out["enum"] = [deepcopy(node["const"])]
        if "enum" in out and "type" not in out:
            types = list(dict.fromkeys(_type(value) for value in out["enum"]))
            out["type"] = types[0] if len(types) == 1 else types
        if profile == "gemini" and "enum" in out and any(value is None or isinstance(value, bool) for value in out["enum"]):
            del out["enum"]  # Gemini supports string/number enums; source validation retains const/enum.
        if isinstance(out.get("type"), list):
            if "number" in out["type"] and "integer" in out["type"]:
                out["type"].remove("integer")
        if "$ref" in node:
            if not node["$ref"].startswith("#/"):
                raise OutputContractError(f"External schema reference at {path}")
            out["$ref"] = node["$ref"]
        for key in ("$defs", "definitions"):
            if key in node:
                out[key] = {name: visit(child, f"{path}/{key}/{name}") for name, child in node[key].items()}
        alternatives = node.get("anyOf", node.get("oneOf"))
        if alternatives is not None:
            out["anyOf"] = [visit(child, f"{path}/anyOf/{index}") for index, child in enumerate(alternatives)]
        if "properties" in node or node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                raise OutputContractError(f"Open object at {path}; select a validated JSON transport explicitly")
            out["type"] = node.get("type", "object")
            out["properties"] = {}
            required = node.get("required", [])
            for name, child in node.get("properties", {}).items():
                projected = visit(child, f"{path}/properties/{name}")
                if profile == "openai" and name not in required and not validator.evolve(schema=child).is_valid(None):
                    projected = {"anyOf": [projected, {"type": "null"}]}
                out["properties"][name] = projected
            out["required"] = list(out["properties"]) if profile == "openai" else list(required)
            out["additionalProperties"] = False
        if "items" in node or "prefixItems" in node or node.get("type") == "array":
            prefixes = node.get("prefixItems")
            if prefixes:
                variants = [visit(child, f"{path}/prefixItems/{i}") for i, child in enumerate(prefixes)]
                tail = node.get("items", True)
                if isinstance(tail, dict):
                    variants.append(visit(tail, f"{path}/items"))
                elif tail is not False:
                    raise OutputContractError(f"Unconstrained tuple tail at {path}")
                variants = list({json.dumps(child, sort_keys=True): child for child in variants}.values())
                out["items"] = variants[0] if len(variants) == 1 else {"anyOf": variants}
            else:
                out["items"] = visit(node.get("items"), f"{path}/items")
        if not any(key in out for key in ("type", "$ref", "anyOf")):
            raise OutputContractError(f"Missing schema type at {path}")
        return out

    result = visit(source, "#")
    if result.get("type") != "object":
        raise OutputContractError("Structured response root must be an object")
    Draft202012Validator.check_schema(result)
    return result


def restore_optional_nulls(payload: Any, source: dict[str, Any]) -> Any:
    """Decode OpenAI's optional-null encoding; preserve every other value.

    A null remains null if the original field admits null. Required fields are
    never removed. Branches are chosen by actual source validation, not by order.
    """
    validator = Draft202012Validator(source)

    def resolve(ref: str) -> Any:
        node = source
        if not ref.startswith("#/"):
            raise OutputContractError("External references are not allowed")
        for part in ref[2:].split("/"):
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node

    def visit(value: Any, schema: Any, depth: int = 0) -> Any:
        if depth > 100:
            raise OutputContractError("Structured response nesting exceeds 100")
        if not isinstance(schema, dict):
            return deepcopy(value)
        if "$ref" in schema:
            value = visit(value, resolve(schema["$ref"]), depth + 1)
        variants = schema.get("anyOf", schema.get("oneOf", []))
        if variants:
            candidates = []
            for variant in variants:
                candidate = visit(value, variant, depth + 1)
                if validator.evolve(schema=variant).is_valid(candidate):
                    candidates.append(candidate)
            if candidates:
                if any(candidate != candidates[0] for candidate in candidates[1:]):
                    raise OutputContractError("Ambiguous optional-null decoding")
                value = candidates[0]
        if isinstance(value, dict):
            result = deepcopy(value)
            for name, child in schema.get("properties", {}).items():
                if name not in result:
                    continue
                if result[name] is None and name not in schema.get("required", []) and not validator.evolve(schema=child).is_valid(None):
                    del result[name]
                else:
                    result[name] = visit(result[name], child, depth + 1)
            return result
        if isinstance(value, list):
            prefixes = schema.get("prefixItems", [])
            return [visit(item, prefixes[i] if i < len(prefixes) else schema.get("items"), depth + 1)
                    for i, item in enumerate(value)]
        return value

    return visit(payload, source)


def validate_output(payload: Any, source: dict[str, Any], *, profile: str = "") -> dict[str, Any]:
    result = restore_optional_nulls(payload, source) if profile == "openai" else deepcopy(payload)
    errors = list(Draft202012Validator(source).iter_errors(result))
    if errors:
        # Do not echo instance values (which may contain secrets) in diagnostics.
        error = errors[0]
        raise OutputContractError(f"Output violates source contract at {error.json_path} ({error.validator})")
    if not isinstance(result, dict):
        raise OutputContractError("Model output must be a JSON object")
    return result


def parse_json(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise OutputContractError("Duplicate JSON key in model output")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise OutputContractError("Non-finite JSON number in model output")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise OutputContractError("Non-finite JSON number in model output")
        return number

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant, parse_float=finite_float)
    except (ValueError, TypeError) as exc:
        raise OutputContractError("Model output is not strict JSON") from exc
