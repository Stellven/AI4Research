#!/usr/bin/env python3
"""Artifact-first Intent Compiler used by the existing intent gateway.

The compiler owns only semantic interpretation and admission.  It does not
compile requirements, select workflows, or mutate runtime state.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


HARNESS_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = HARNESS_DIR / "schemas" / "compiler"
SEMANTIC_SCHEMA = SCHEMA_DIR / "intent-ir.semantic.v1.schema.json"
INTENT_SCHEMA = SCHEMA_DIR / "intent-ir.v3.schema.json"
FIDELITY_REVIEW_SCHEMA = SCHEMA_DIR / "intent-fidelity.review.v1.schema.json"
VALIDATION_SCHEMA = SCHEMA_DIR / "intent-validation.v1.schema.json"
FIDELITY_SCHEMA = SCHEMA_DIR / "intent-fidelity.v1.schema.json"
ACCEPTANCE_SCHEMA = SCHEMA_DIR / "intent-acceptance.v1.schema.json"


class IntentCompilerError(RuntimeError):
    """A typed failure at the model/compiler boundary."""


class JsonModel(Protocol):
    provider: str
    model: str

    def generate(self, prompt: str, schema_path: Path, work_dir: Path) -> dict[str, Any]: ...


def codex_compatible_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Project Solar's strict schema into the JSON-Schema subset Codex accepts.

    This copy constrains generation only. Solar validates the returned artifact
    against the original strict schema after the model call.
    """
    projected = deepcopy(schema)

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if not isinstance(value, dict):
            return
        value.pop("$schema", None)
        value.pop("$id", None)
        value.pop("uniqueItems", None)
        if "oneOf" in value:
            value["anyOf"] = value.pop("oneOf")
        declared_type = value.get("type")
        if isinstance(declared_type, list) and "number" in declared_type and "integer" in declared_type:
            value["type"] = [item for item in declared_type if item != "integer"]
        prefix_items = value.pop("prefixItems", None)
        if prefix_items is not None and value.get("items") is False:
            integer_minimums = [
                item.get("minimum", 0)
                for item in prefix_items
                if isinstance(item, dict) and item.get("type") == "integer"
            ]
            value["items"] = {
                "type": "integer",
                "minimum": min(integer_minimums) if integer_minimums else 0,
            }
        for child in value.values():
            visit(child)

    visit(projected)
    return projected


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_bytes(payload))
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise IntentCompilerError(f"expected JSON object: {path}")
    return payload


@dataclass
class CodexJsonModel:
    """Fresh, schema-bound Codex invocation for one semantic boundary."""

    model: str
    timeout_seconds: int = 180
    provider: str = "codex"

    def generate(self, prompt: str, schema_path: Path, work_dir: Path) -> dict[str, Any]:
        # Codex resolves --output-schema and --output-last-message relative to
        # its subprocess cwd.  Normalize the managed directory first so a
        # caller may safely provide a relative output root.
        work_dir = work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        output_path = work_dir / "model_output.json"
        provider_schema_path = work_dir / "model_output.schema.json"
        write_json(provider_schema_path, codex_compatible_schema(_load_json(schema_path)))
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--output-schema",
            str(provider_schema_path),
            "--output-last-message",
            str(output_path),
        ]
        if self.model:
            command.extend(["--model", self.model])
        command.append("-")
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                cwd=work_dir,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise IntentCompilerError(
                f"{self.provider} model call timed out after {self.timeout_seconds}s"
            ) from exc
        if process.returncode != 0:
            detail = " ".join(
                str(process.stderr or process.stdout or "").strip().split()
            )[-2000:]
            raise IntentCompilerError(
                f"{self.provider} model call failed with exit {process.returncode}"
                + (f": {detail}" if detail else "")
            )
        if not output_path.exists():
            raise IntentCompilerError(f"{self.provider} model call produced no structured output")
        payload = _load_json(output_path)
        receipt = {
            "provider": self.provider,
            "model": self.model or "configured_default",
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
        write_json(work_dir / "model_call_receipt.json", receipt)
        return payload


def model_from_environment(role: str) -> JsonModel:
    provider = os.environ.get(f"SOLAR_INTENT_{role.upper()}_PROVIDER", "codex").strip().lower()
    if provider != "codex":
        raise IntentCompilerError(
            f"unsupported {role} provider {provider!r}; this increment currently supports codex"
        )
    model = os.environ.get(f"SOLAR_INTENT_{role.upper()}_MODEL", "").strip()
    timeout = int(os.environ.get("SOLAR_INTENT_MODEL_TIMEOUT_SEC", "180") or "180")
    return CodexJsonModel(model=model, timeout_seconds=timeout)


def normalize_input(raw: dict[str, Any]) -> dict[str, Any]:
    """Project current gateway RawIntent or v2 metadata into one canonical input."""
    raw_block = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}
    text = str(raw_block.get("text") or "")
    if not text.strip():
        raise IntentCompilerError("input.raw.text must be non-empty")
    raw_id = str(raw.get("raw_intent_id") or raw.get("intent_id") or "").strip()
    if not raw_id:
        raise IntentCompilerError("input must contain raw_intent_id or intent_id")
    actual_hash = sha256_text(text)
    declared_hash = str(raw_block.get("sha256") or actual_hash)
    if declared_hash != actual_hash:
        raise IntentCompilerError("input raw text sha256 does not match raw.text")
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    actor_ref = str(source.get("actor_ref") or source.get("actor") or "unknown")
    context = raw.get("context") if isinstance(raw.get("context"), dict) else {}
    context_refs = list(raw.get("context_refs") or [])
    for prefix, value in (
        ("session", source.get("session_id")),
        ("thread", source.get("thread_ref")),
    ):
        if str(value or "").strip():
            context_refs.append(f"{prefix}:{str(value).strip()}")
    for value in context.get("related_sprints") or []:
        if str(value or "").strip():
            context_refs.append(f"sprint:{str(value).strip()}")
    context_refs = list(dict.fromkeys(str(value) for value in context_refs if str(value).strip()))
    attachments = raw.get("attachments")
    if not isinstance(attachments, list):
        attachments = raw_block.get("attachments") if isinstance(raw_block.get("attachments"), list) else []
    return {
        "schema_version": "solar.raw_intent.v2",
        "raw_intent_id": raw_id,
        "raw": {
            "text": text,
            "encoding": str(raw_block.get("encoding") or "utf-8"),
            "sha256": actual_hash,
            "received_at": str(raw_block.get("received_at") or ""),
        },
        "source": {
            "channel": str(source.get("channel") or "unknown"),
            "actor_ref": actor_ref,
        },
        "context_refs": context_refs,
        "attachments": attachments,
    }


def _schema_errors(payload: dict[str, Any], schema_path: Path) -> list[dict[str, Any]]:
    schema = _load_json(schema_path)
    registry = Registry()
    for candidate in SCHEMA_DIR.glob("*.schema.json"):
        content = _load_json(candidate)
        identifier = content.get("$id")
        if identifier:
            registry = registry.with_resource(str(identifier), Resource.from_contents(content))
    validator = Draft202012Validator(schema, registry=registry)
    errors: list[dict[str, Any]] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(
            {
                "code": "SCHEMA_INVALID",
                "path": path,
                "message": error.message,
                "repairable": True,
            }
        )
    return errors


def _assert_schema(payload: dict[str, Any], schema_path: Path, label: str) -> None:
    errors = _schema_errors(payload, schema_path)
    if errors:
        first = errors[0]
        raise IntentCompilerError(
            f"{label} violated its own contract at {first['path']}: {first['message']}"
        )


def _all_semantic_ids(intent_ir: dict[str, Any]) -> list[str]:
    keys = (
        ("goals", "goal_id"),
        ("outcomes", "outcome_id"),
        ("constraints", "constraint_id"),
        ("ambiguities", "ambiguity_id"),
        ("conflicts", "conflict_id"),
        ("unknowns", "unknown_id"),
    )
    return [
        str(item.get(id_key) or "")
        for collection, id_key in keys
        for item in intent_ir.get(collection, [])
        if isinstance(item, dict)
    ]


def _iter_spans(intent_ir: dict[str, Any]):
    for collection in ("goals", "outcomes", "constraints", "ambiguities", "conflicts"):
        for index, item in enumerate(intent_ir.get(collection, [])):
            if not isinstance(item, dict):
                continue
            for span_index, span in enumerate(item.get("source_spans", [])):
                yield f"{collection}.{index}.source_spans.{span_index}", span


def _iter_unknown_refs(value: Any):
    if isinstance(value, dict):
        if "unknown_ref" in value:
            yield str(value["unknown_ref"])
        for child in value.values():
            yield from _iter_unknown_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_unknown_refs(child)


_OPERATOR_ARITY: dict[str, tuple[int, int | None]] = {
    "all_of": (2, None),
    "any_of": (2, None),
    "not": (1, 1),
    "equals": (2, 2),
    "not_equals": (2, 2),
    "contains_all": (2, 2),
    "contains_any": (2, 2),
    "contains_none": (2, 2),
    "at_least": (2, 2),
    "at_most": (2, 2),
    "less_than": (2, 2),
    "less_than_or_equal": (2, 2),
    "greater_than": (2, 2),
    "greater_than_or_equal": (2, 2),
    "exactly": (2, 2),
    "select_by": (2, 2),
    "bounded_by": (2, 2),
    "before": (2, 2),
    "after": (2, 2),
    "implies": (2, 2),
    "triggers": (2, 2),
}


def _iter_operator_expressions(value: Any, path: str):
    if isinstance(value, dict):
        if "op" in value:
            yield path, value
        for key, child in value.items():
            yield from _iter_operator_expressions(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_operator_expressions(child, f"{path}.{index}")


def _expression_arity_errors(intent_ir: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index, constraint in enumerate(intent_ir.get("constraints", [])):
        expression = constraint.get("expression") if isinstance(constraint, dict) else None
        for path, node in _iter_operator_expressions(expression, f"constraints.{index}.expression"):
            operator = str(node.get("op") or "")
            arguments = node.get("args") if isinstance(node.get("args"), list) else []
            minimum, maximum = _OPERATOR_ARITY.get(operator, (1, None))
            if len(arguments) < minimum or (maximum is not None and len(arguments) > maximum):
                expected = str(minimum) if minimum == maximum else f"at least {minimum}"
                errors.append(
                    {
                        "code": "INVALID_EXPRESSION_ARITY",
                        "path": path,
                        "message": f"Operator {operator!r} requires {expected} argument(s).",
                        "repairable": True,
                    }
                )
    return errors


def validate_intent(
    raw_input: dict[str, Any], intent_ir: dict[str, Any], *, generation: int
) -> dict[str, Any]:
    checks = {
        "raw_intent_reference": [],
        "identifier_uniqueness": [],
        "source_span_integrity": [],
        "controlled_value_integrity": [],
        "derived_reference_integrity": [],
        "constraint_expression_integrity": [],
        "unknown_resolution_integrity": [],
    }
    schema_errors = _schema_errors(intent_ir, INTENT_SCHEMA)
    checks["controlled_value_integrity"].extend(schema_errors)
    raw_id = raw_input["raw_intent_id"]
    raw_hash = raw_input["raw"]["sha256"]
    raw_ref = intent_ir.get("raw_intent_ref", {})
    if raw_ref.get("raw_intent_id") != raw_id or raw_ref.get("raw_text_sha256") != raw_hash:
        checks["raw_intent_reference"].append(
            {
                "code": "RAW_INTENT_REFERENCE_MISMATCH",
                "path": "raw_intent_ref",
                "message": "IntentIR does not reference the exact canonical input.",
                "repairable": True,
            }
        )
    if intent_ir.get("generation") != generation:
        checks["raw_intent_reference"].append(
            {
                "code": "GENERATION_MISMATCH",
                "path": "generation",
                "message": f"Expected generation {generation}.",
                "repairable": True,
            }
        )
    ids = _all_semantic_ids(intent_ir)
    duplicate_ids = sorted({item for item in ids if item and ids.count(item) > 1})
    if duplicate_ids:
        checks["identifier_uniqueness"].append(
            {
                "code": "DUPLICATE_IDS",
                "path": "$",
                "message": "Duplicate semantic identifiers: " + ", ".join(duplicate_ids),
                "repairable": True,
            }
        )
    text_length = len(raw_input["raw"]["text"])
    for path, span in _iter_spans(intent_ir):
        if (
            not isinstance(span, list)
            or len(span) != 2
            or not all(isinstance(part, int) for part in span)
            or span[0] < 0
            or span[0] >= span[1]
            or span[1] > text_length
        ):
            checks["source_span_integrity"].append(
                {
                    "code": "INVALID_SOURCE_SPAN",
                    "path": path,
                    "message": f"Source span must fit within raw text length {text_length}.",
                    "repairable": True,
                }
            )
    valid_ids = set(ids)
    for collection in ("conflicts", "unknowns"):
        for index, item in enumerate(intent_ir.get(collection, [])):
            if not isinstance(item, dict):
                continue
            for reference in item.get("derived_from", []):
                if reference not in valid_ids:
                    checks["derived_reference_integrity"].append(
                        {
                            "code": "UNKNOWN_DERIVED_REFERENCE",
                            "path": f"{collection}.{index}.derived_from",
                            "message": f"Unknown IntentIR reference: {reference}",
                            "repairable": True,
                        }
                    )
    unknown_ids = {
        str(item.get("unknown_id"))
        for item in intent_ir.get("unknowns", [])
        if isinstance(item, dict)
    }
    for index, constraint in enumerate(intent_ir.get("constraints", [])):
        if not isinstance(constraint, dict):
            continue
        for reference in _iter_unknown_refs(constraint.get("expression")):
            if reference not in unknown_ids:
                checks["constraint_expression_integrity"].append(
                    {
                        "code": "UNKNOWN_EXPRESSION_REFERENCE",
                        "path": f"constraints.{index}.expression",
                        "message": f"Unknown unknown_ref: {reference}",
                        "repairable": True,
                    }
                )
    checks["constraint_expression_integrity"].extend(_expression_arity_errors(intent_ir))
    errors = [error for values in checks.values() for error in values]
    check_rows = [
        {
            "check_id": f"IV{index}",
            "kind": kind,
            "status": "fail" if values else "pass",
        }
        for index, (kind, values) in enumerate(checks.items(), start=1)
    ]
    result = {
        "schema_version": "solar.intent_validation.v1",
        "artifact_role": "runtime_artifact",
        "validation_id": f"intent-validation-{raw_id}-g{generation}",
        "intent_ir_ref": {
            "intent_ir_id": str(intent_ir.get("intent_ir_id") or ""),
            "generation": generation,
            "sha256": sha256_payload(intent_ir),
        },
        "attempt": generation + 1,
        "repair_count": generation,
        "status": "fail" if errors else "pass",
        "checks": check_rows,
        "errors": errors,
        "warnings": [],
        "limitations": [
            "Structural validation does not prove that normalized statements preserve the user's meaning."
        ],
        "failure_policy": "Return repairable defects for one bounded model repair; never repair user ambiguity.",
    }
    _assert_schema(result, VALIDATION_SCHEMA, "intent_validation")
    return result


def _compiler_prompt(
    raw_input: dict[str, Any], *, generation: int, previous: dict[str, Any] | None, defects: list[dict[str, Any]]
) -> str:
    instruction = """
You are Solar's Intent Compiler. Return only the semantic body required by the supplied JSON schema.
Represent what the user requested without choosing a workflow, DAG, capsule, worker, or implementation.
Every goal, outcome, constraint, ambiguity, and conflict must cite exact zero-based character spans [start,end]
from raw.text, with end exclusive. Unknown facts that later work can discover are unknowns, not user questions.
Only an ambiguity that changes the deliverable, scope, authorization, or irreversible effect is blocking.
If workflow discovery, analysis, or design can resolve a choice without changing those boundaries, record an unknown
with the correct resolution stage instead of a blocking ambiguity. A context reference may be resolved later; an
unreferenced missing object that defines the requested deliverable is blocking.
Use conflicts for mutually incompatible instructions. Use resolution=clarify when the user can choose and
resolution=reject only when the request is inherently impossible or forbidden. Do not invent execution.
The structured expression is the machine contract and must mean the same thing as the statement. Use before/after
for ordering, triggers/implies for condition-action rules, and strict comparison operators when the boundary is strict.
Use contains_none to prohibit any listed value from appearing in a set or collection.
Do not use all_of merely to represent an ordered approval or a conditional rollback.
""".strip()
    payload: dict[str, Any] = {"instruction": instruction, "input": raw_input}
    if generation:
        payload["repair_instruction"] = (
            "Correct only the listed errors. Preserve every unaffected meaning and do not add requirements."
        )
        payload["previous_intent_ir"] = previous
        payload["defects"] = defects
    return json.dumps(payload, ensure_ascii=False, indent=2)


def compile_candidate(
    raw_input: dict[str, Any], model: JsonModel, work_dir: Path, *, generation: int,
    previous: dict[str, Any] | None = None, defects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    semantic = model.generate(
        _compiler_prompt(raw_input, generation=generation, previous=previous, defects=defects or []),
        SEMANTIC_SCHEMA,
        work_dir / "compiler_call",
    )
    raw_id = raw_input["raw_intent_id"]
    suffix = raw_id.removeprefix("raw-intent-").removeprefix("intent-")
    return {
        "schema_version": "solar.intent_ir.v3",
        "artifact_role": "runtime_artifact",
        "intent_ir_id": f"intent-ir-{suffix}",
        "generation": generation,
        "raw_intent_ref": {
            "raw_intent_id": raw_id,
            "raw_text_sha256": raw_input["raw"]["sha256"],
        },
        "producer": {
            "method": "model",
            "provider": model.provider,
            "model": model.model or "configured_default",
        },
        **semantic,
    }


def _fidelity_prompt(raw_input: dict[str, Any], intent_ir: dict[str, Any]) -> str:
    instruction = """
You are an independent semantic reviewer. Compare the original input with IntentIR.
Report an error only when the IntentIR materially changes or omits a requested deliverable, scope,
constraint, authorization, or meaning. Awkward wording and harmless differences are warnings or passes.
Treat constraint.expression as authoritative machine meaning. If its logic differs from the statement or source,
report a repairable error even when the prose is correct. In particular, verify strict limits, ordering, conditions,
approval-before-action, and stop/rollback triggers.
Do not fail because a discoverable fact is unknown before the workflow. Do fail unrequested execution.
Do not report source-span bounds; the deterministic validator owns that mechanical check.
Check all six required check kinds exactly once. Every issue must cite raw-input character spans.
You may judge but may not rewrite the IntentIR.
""".strip()
    return json.dumps(
        {"instruction": instruction, "input": raw_input, "intent_ir": intent_ir},
        ensure_ascii=False,
        indent=2,
    )


def review_fidelity(
    raw_input: dict[str, Any], intent_ir: dict[str, Any], model: JsonModel, work_dir: Path
) -> dict[str, Any]:
    body = model.generate(
        _fidelity_prompt(raw_input, intent_ir),
        FIDELITY_REVIEW_SCHEMA,
        work_dir / "reviewer_call",
    )
    errors = list(body.get("errors") or [])
    warnings = list(body.get("warnings") or [])
    if any(
        str(issue.get("code") or "") in {"SOURCE_SPAN_OUT_OF_BOUNDS", "INVALID_SOURCE_SPAN"}
        for issue in [*errors, *warnings]
    ):
        errors = [
            issue
            for issue in errors
            if str(issue.get("code") or "") not in {"SOURCE_SPAN_OUT_OF_BOUNDS", "INVALID_SOURCE_SPAN"}
        ]
        warnings = [
            issue
            for issue in warnings
            if str(issue.get("code") or "") not in {"SOURCE_SPAN_OUT_OF_BOUNDS", "INVALID_SOURCE_SPAN"}
        ]
        warnings.append(
            {
                "code": "REVIEWER_MECHANICAL_CLAIM_REJECTED",
                "path": "intent_fidelity.reviewer_output",
                "message": (
                    "The reviewer made a source-span claim owned by the deterministic validator; "
                    "that commentary was rejected and did not affect admission."
                ),
                "source_spans": [],
            }
        )
    expected_checks = {
        "goals_supported_by_source",
        "outcomes_supported_by_source",
        "constraints_supported_by_source",
        "no_material_omissions",
        "no_unrequested_execution",
        "ambiguity_unknown_classification",
    }
    actual_checks = [str(item.get("kind") or "") for item in body.get("checks") or []]
    if len(actual_checks) != len(expected_checks) or set(actual_checks) != expected_checks:
        raise IntentCompilerError("independent reviewer did not return each required check exactly once")
    text_length = len(raw_input["raw"]["text"])
    for issue in [*errors, *warnings]:
        for span in issue.get("source_spans", []):
            if (
                not isinstance(span, list)
                or len(span) != 2
                or not all(isinstance(part, int) for part in span)
                or span[0] < 0
                or span[0] >= span[1]
                or span[1] > text_length
            ):
                raise IntentCompilerError("independent reviewer returned an invalid source span")
    status = "fail" if errors else ("pass_with_warnings" if warnings else "pass")
    generation = int(intent_ir["generation"])
    raw_id = raw_input["raw_intent_id"]
    result = {
        "schema_version": "solar.intent_fidelity.v1",
        "artifact_role": "runtime_artifact",
        "fidelity_id": f"intent-fidelity-{raw_id}-g{generation}",
        "raw_intent_ref": {
            "raw_intent_id": raw_id,
            "raw_text_sha256": raw_input["raw"]["sha256"],
        },
        "intent_ir_ref": {
            "intent_ir_id": intent_ir["intent_ir_id"],
            "generation": generation,
            "sha256": sha256_payload(intent_ir),
        },
        "status": status,
        "review_method": "independent_model_call",
        "reviewer": {
            "provider": model.provider,
            "model": model.model or "configured_default",
        },
        "checks": [
            {"check_id": f"IF{index}", **check}
            for index, check in enumerate(body.get("checks") or [], start=1)
        ],
        "decisions": [
            {"decision_id": f"FD{index}", **decision}
            for index, decision in enumerate(body.get("decisions") or [], start=1)
        ],
        "errors": errors,
        "warnings": warnings,
    }
    _assert_schema(result, FIDELITY_SCHEMA, "intent_fidelity")
    return result


def _artifact_ref(payload: dict[str, Any], id_key: str) -> dict[str, Any]:
    return {id_key: payload.get(id_key), "sha256": sha256_payload(payload)}


def decide_acceptance(
    raw_input: dict[str, Any], intent_ir: dict[str, Any] | None,
    validation: dict[str, Any] | None, fidelity: dict[str, Any] | None,
    *, repair_attempted: bool, failure: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    questions: list[dict[str, Any]] = []
    decision = "failed"
    if failure:
        reasons.append(failure)
    elif not intent_ir or not validation or not fidelity:
        reasons.append("Required Intent Compiler artifacts are missing.")
    elif validation.get("status") == "fail":
        reasons.append("IntentIR mechanical validation failed.")
    elif fidelity.get("status") == "fail":
        reasons.append("IntentIR meaning-preservation review failed.")
    else:
        blocking = [item for item in intent_ir.get("ambiguities", []) if item.get("blocking")]
        conflicts = list(intent_ir.get("conflicts") or [])
        rejected = [item for item in conflicts if item.get("resolution") == "reject"]
        if rejected:
            reasons.extend(str(item.get("description")) for item in rejected)
        elif blocking or conflicts:
            decision = "needs_clarification"
            questions.extend(
                {
                    "item_id": item.get("ambiguity_id"),
                    "question": item.get("question"),
                    "source_spans": item.get("source_spans", []),
                }
                for item in blocking
            )
            questions.extend(
                {
                    "item_id": item.get("conflict_id"),
                    "question": "Which conflicting instruction should take priority?",
                    "detail": item.get("description"),
                    "source_spans": item.get("source_spans", []),
                }
                for item in conflicts
            )
            reasons.append("The user must resolve a material ambiguity or conflict.")
        else:
            decision = "accepted"
            reasons.extend(
                ["Mechanical validation passed.", "Independent meaning-preservation review passed."]
            )
    raw_id = raw_input["raw_intent_id"]
    result = {
        "schema_version": "solar.intent_acceptance.v1",
        "artifact_role": "runtime_artifact",
        "acceptance_id": f"intent-acceptance-{raw_id}",
        "raw_intent_ref": {
            "raw_intent_id": raw_id,
            "sha256": sha256_payload(raw_input),
        },
        "intent_ir_ref": _artifact_ref(intent_ir, "intent_ir_id") if intent_ir else None,
        "validation_ref": _artifact_ref(validation, "validation_id") if validation else None,
        "fidelity_ref": _artifact_ref(fidelity, "fidelity_id") if fidelity else None,
        "decision": decision,
        "final_generation": intent_ir.get("generation") if intent_ir else None,
        "repair": {"attempted": repair_attempted, "maximum_attempts": 1},
        "reasons": reasons,
        "clarification_questions": questions,
        "requirement_compiler_handoff_allowed": decision == "accepted",
    }
    _assert_schema(result, ACCEPTANCE_SCHEMA, "intent_acceptance")
    return result


def _repairable_errors(*artifacts: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        error
        for artifact in artifacts
        if artifact
        for error in artifact.get("errors", [])
        if error.get("repairable") is True
    ]


def run_pipeline(
    raw: dict[str, Any], output_dir: Path, compiler_model: JsonModel, reviewer_model: JsonModel
) -> dict[str, Any]:
    """Run one bounded Intent Compiler request and persist content-addressed artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "intent_acceptance.json").exists():
        raise IntentCompilerError(f"refusing to overwrite completed intent compilation: {output_dir}")
    raw_input = normalize_input(raw)
    write_json(output_dir / "input.json", raw_input)
    intent_ir: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    fidelity: dict[str, Any] | None = None
    repair_attempted = False
    repair_completed = False
    try:
        for generation in (0, 1):
            generation_dir = output_dir / f"generation-{generation}"
            defects = _repairable_errors(validation, fidelity)
            if generation == 1:
                if not defects:
                    break
                repair_attempted = True
                write_json(
                    output_dir / "repair_record.json",
                    {
                        "schema_version": "solar.repair_record.v1",
                        "repair_id": f"intent-repair-{raw_input['raw_intent_id']}",
                        "target_artifact_id": intent_ir.get("intent_ir_id") if intent_ir else None,
                        "generation": 1,
                        "defects": defects,
                        "requested_from": "intent_compiler",
                        "result_artifact_id": None,
                        "status": "requested",
                        "budget": {"maximum_repairs_per_boundary": 1, "on_exhaustion": "clarify_or_reject"},
                    },
                )
            previous = intent_ir
            intent_ir = compile_candidate(
                raw_input,
                compiler_model,
                generation_dir,
                generation=generation,
                previous=previous,
                defects=defects,
            )
            if generation == 1:
                repair_completed = True
            write_json(generation_dir / "intent_ir.json", intent_ir)
            validation = validate_intent(raw_input, intent_ir, generation=generation)
            write_json(generation_dir / "intent_validation.json", validation)
            fidelity = None
            if validation["status"] != "fail":
                fidelity = review_fidelity(raw_input, intent_ir, reviewer_model, generation_dir)
                write_json(generation_dir / "intent_fidelity.json", fidelity)
            if not _repairable_errors(validation, fidelity):
                break
        acceptance = decide_acceptance(
            raw_input,
            intent_ir,
            validation,
            fidelity,
            repair_attempted=repair_attempted,
        )
    except IntentCompilerError as exc:
        acceptance = decide_acceptance(
            raw_input,
            intent_ir,
            validation,
            fidelity,
            repair_attempted=repair_attempted,
            failure=str(exc),
        )
    if repair_attempted and (output_dir / "repair_record.json").exists():
        repair_record = _load_json(output_dir / "repair_record.json")
        repair_record["result_artifact_id"] = (
            intent_ir.get("intent_ir_id") if repair_completed and intent_ir else None
        )
        repair_record["result_generation"] = 1 if repair_completed else None
        repair_record["status"] = "completed" if repair_completed else "failed"
        write_json(output_dir / "repair_record.json", repair_record)
    if intent_ir:
        write_json(output_dir / "intent_ir.json", intent_ir)
    if validation:
        write_json(output_dir / "intent_validation.json", validation)
    if fidelity:
        write_json(output_dir / "intent_fidelity.json", fidelity)
    write_json(output_dir / "intent_acceptance.json", acceptance)
    return {
        "input": raw_input,
        "intent_ir": intent_ir,
        "intent_validation": validation,
        "intent_fidelity": fidelity,
        "intent_acceptance": acceptance,
    }


def project_legacy_rewritten_intent(intent_ir: dict[str, Any], raw_text: str) -> dict[str, Any]:
    """Temporary adapter for the current RequirementIR compiler."""
    goals = [str(item.get("statement") or "") for item in intent_ir.get("goals", [])]
    outcomes = [str(item.get("description") or "") for item in intent_ir.get("outcomes", [])]
    constraints = [str(item.get("statement") or "") for item in intent_ir.get("constraints", [])]
    title = goals[0][:90] if goals else raw_text[:90]
    return {
        "schema_version": "solar.rewritten_intent.v1",
        "rewrite_method": "intent_ir_v3_compatibility_projection",
        "title": title,
        "problem": raw_text,
        "objective": " ".join(goals),
        "outcome": " ".join(outcomes),
        "constraints": constraints,
        "non_goals": [],
        "acceptance": outcomes,
        "suggested_lane": "delivery",
        "suggested_logical_operators": [],
        "intent_ir_ref": {
            "intent_ir_id": intent_ir["intent_ir_id"],
            "sha256": sha256_payload(intent_ir),
        },
        "compatibility_only": True,
    }


def requirement_handoff(intent_ir: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, Any]:
    if acceptance.get("decision") != "accepted" or not acceptance.get(
        "requirement_compiler_handoff_allowed"
    ):
        raise IntentCompilerError("only accepted IntentIR may reach the Requirement Compiler")
    reference = acceptance.get("intent_ir_ref") or {}
    if reference.get("intent_ir_id") != intent_ir.get("intent_ir_id") or reference.get(
        "sha256"
    ) != sha256_payload(intent_ir):
        raise IntentCompilerError("accepted IntentIR does not match the admission decision")
    return {
        "status": "received",
        "intent_ir_id": intent_ir["intent_ir_id"],
        "intent_ir_sha256": sha256_payload(intent_ir),
        "next_component": "requirement_compiler",
        "execution_started": False,
    }


def verify_artifact_chain(output_dir: Path) -> list[str]:
    """Recompute every content reference in a completed Intent Compiler directory."""
    errors: list[str] = []
    required = ("input.json", "intent_acceptance.json")
    for name in required:
        if not (output_dir / name).exists():
            errors.append(f"missing:{name}")
    if errors:
        return errors
    raw_input = _load_json(output_dir / "input.json")
    acceptance = _load_json(output_dir / "intent_acceptance.json")
    raw_ref = acceptance.get("raw_intent_ref") or {}
    if raw_ref.get("raw_intent_id") != raw_input.get("raw_intent_id"):
        errors.append("acceptance.raw_intent_ref.id_mismatch")
    if raw_ref.get("sha256") != sha256_payload(raw_input):
        errors.append("acceptance.raw_intent_ref.hash_mismatch")
    artifacts = (
        ("intent_ir.json", "intent_ir_ref", "intent_ir_id"),
        ("intent_validation.json", "validation_ref", "validation_id"),
        ("intent_fidelity.json", "fidelity_ref", "fidelity_id"),
    )
    loaded: dict[str, dict[str, Any]] = {}
    for filename, acceptance_key, id_key in artifacts:
        path = output_dir / filename
        reference = acceptance.get(acceptance_key)
        if reference is None:
            if path.exists():
                errors.append(f"acceptance.{acceptance_key}.missing")
            continue
        if not path.exists():
            errors.append(f"missing:{filename}")
            continue
        payload = _load_json(path)
        loaded[filename] = payload
        if reference.get(id_key) != payload.get(id_key):
            errors.append(f"acceptance.{acceptance_key}.id_mismatch")
        if reference.get("sha256") != sha256_payload(payload):
            errors.append(f"acceptance.{acceptance_key}.hash_mismatch")
    intent_ir = loaded.get("intent_ir.json")
    validation = loaded.get("intent_validation.json")
    fidelity = loaded.get("intent_fidelity.json")
    if intent_ir:
        intent_raw_ref = intent_ir.get("raw_intent_ref") or {}
        if intent_raw_ref.get("raw_intent_id") != raw_input.get("raw_intent_id"):
            errors.append("intent_ir.raw_intent_ref.id_mismatch")
        if intent_raw_ref.get("raw_text_sha256") != raw_input.get("raw", {}).get("sha256"):
            errors.append("intent_ir.raw_intent_ref.hash_mismatch")
    for filename, payload in (
        ("intent_validation", validation),
        ("intent_fidelity", fidelity),
    ):
        if not payload or not intent_ir:
            continue
        reference = payload.get("intent_ir_ref") or {}
        if reference.get("intent_ir_id") != intent_ir.get("intent_ir_id"):
            errors.append(f"{filename}.intent_ir_ref.id_mismatch")
        if reference.get("sha256") != sha256_payload(intent_ir):
            errors.append(f"{filename}.intent_ir_ref.hash_mismatch")
    return errors
