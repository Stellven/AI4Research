#!/usr/bin/env python3
"""Artifact-first Elastic Planner admission and freeze boundary.

The module owns semantic planning plus pre-runtime capsule/physical binding and
contract freezing. It does not schedule, lease, dispatch, or mutate graph
runtime state. Model outputs are candidates; deterministic validation and an
independent fidelity review own admission.
"""

from __future__ import annotations

import json
import re
import copy
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

try:
    from referencing import Registry, Resource
except ModuleNotFoundError:  # Ubuntu's jsonschema 4.10.x predates referencing.
    Registry = None
    Resource = None

from intent_compiler import JsonModel, sha256_payload, write_json
import workflow_contract as workflow_contract
import apo_plan_compiler
import capsule_composition
import evaluation_budget
import evaluation_plan as evaluation_planning
import plan_validator
from capability_capsules import (
    iter_registry_entries,
    load_capability_capsule_manifest,
)
from executable_node import dispatch_role as executable_dispatch_role


HARNESS_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = HARNESS_DIR / "schemas" / "planning"
CONFIG_DIR = HARNESS_DIR / "config"
WORKFLOWS_DIR = CONFIG_DIR / "workflows"
LOGICAL_OPERATORS_PATH = CONFIG_DIR / "logical-operators.json"
CAPSULE_REGISTRY_PATH = CONFIG_DIR / "capability-capsules.registry.yaml"
PHYSICAL_OPERATORS_PATH = CONFIG_DIR / "physical-operators.json"

CONTEXT_SCHEMA = SCHEMA_DIR / "planning-context.v1.schema.json"
CATALOG_SCHEMA = SCHEMA_DIR / "planning-catalog-snapshot.v1.schema.json"
DECISION_BODY_SCHEMA = SCHEMA_DIR / "planning-decision.semantic.v1.schema.json"
DECISION_SCHEMA = SCHEMA_DIR / "planning-decision.v1.schema.json"
PLAN_BODY_SCHEMA = SCHEMA_DIR / "plan-ir.semantic.v2.schema.json"
PLAN_SCHEMA = SCHEMA_DIR / "plan-ir.v2.schema.json"
VALIDATION_SCHEMA = SCHEMA_DIR / "plan-validation.v2.schema.json"
FIDELITY_REVIEW_SCHEMA = SCHEMA_DIR / "plan-fidelity.review.v1.schema.json"
FIDELITY_SCHEMA = SCHEMA_DIR / "plan-fidelity.v1.schema.json"
BINDING_TRACE_SCHEMA = SCHEMA_DIR / "binding-trace.v2.schema.json"
ACCEPTANCE_SCHEMA = SCHEMA_DIR / "plan-acceptance.v1.schema.json"
DIRECT_RESPONSE_BODY_SCHEMA = SCHEMA_DIR / "direct-response.semantic.v1.schema.json"
DIRECT_RESPONSE_SCHEMA = SCHEMA_DIR / "direct-response.v1.schema.json"
DIRECT_RESPONSE_REVIEW_BODY_SCHEMA = SCHEMA_DIR / "direct-response-review.semantic.v1.schema.json"
DIRECT_RESPONSE_REVIEW_SCHEMA = SCHEMA_DIR / "direct-response-review.v1.schema.json"
CAPSULE_PLAN_SCHEMA = SCHEMA_DIR / "capsule-plan.v1.schema.json"
CAPSULE_CANDIDATE_CATALOG_SCHEMA = SCHEMA_DIR / "capsule-candidate-catalog.v1.schema.json"
CAPSULE_SELECTION_BODY_SCHEMA = SCHEMA_DIR / "capsule-selection.semantic.v1.schema.json"
CAPSULE_SELECTION_SCHEMA = SCHEMA_DIR / "capsule-selection.v1.schema.json"
CAPSULE_SELECTION_VALIDATION_SCHEMA = SCHEMA_DIR / "capsule-selection-validation.v1.schema.json"
CAPSULE_FIT_REVIEW_BODY_SCHEMA = SCHEMA_DIR / "capsule-fit-review.semantic.v1.schema.json"
CAPSULE_FIT_REVIEW_SCHEMA = SCHEMA_DIR / "capsule-fit-review.v1.schema.json"
CAPSULE_BINDING_VALIDATION_SCHEMA = SCHEMA_DIR / "capsule-binding-validation.v1.schema.json"
PHYSICAL_PLAN_SCHEMA = SCHEMA_DIR / "physical-plan.v2.schema.json"
SCHEDULER_INPUT_SCHEMA = SCHEMA_DIR / "scheduler-input.v1.schema.json"
FROZEN_CONTRACT_SCHEMA = SCHEMA_DIR / "run-contract-frozen.v2.schema.json"
PLAN_COMPOSITION_CATALOG_SCHEMA = SCHEMA_DIR / "plan-composition-catalog.v1.schema.json"
COMPOSITION_SELECTION_BODY_SCHEMA = SCHEMA_DIR / "composition-selection.semantic.v1.schema.json"
COMPOSITION_SELECTION_SCHEMA = SCHEMA_DIR / "composition-selection.v1.schema.json"
COMPOSITION_SELECTION_VALIDATION_SCHEMA = SCHEMA_DIR / "composition-selection-validation.v1.schema.json"

MVP_DECISIONS = {"direct_response", "exact_reuse", "generate"}
MAX_REPAIRS = 1
_SYSTEM_WORKFLOW_INPUTS = {"sid", "sprint_id", "workspace_root", "resolved_root"}


class ElasticPlannerError(RuntimeError):
    """Typed failure at the semantic planning/admission boundary."""


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ElasticPlannerError(f"expected JSON object: {path}")
    return payload


def _schema_resources() -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    for path in SCHEMA_DIR.glob("*.schema.json"):
        content = _load_json(path)
        identifier = content.get("$id")
        if identifier:
            resources[str(identifier)] = content
    return resources


def _schema_errors(payload: dict[str, Any], schema_path: Path) -> list[dict[str, Any]]:
    schema = _load_json(schema_path)
    resources = _schema_resources()
    if Registry is not None and Resource is not None:
        registry = Registry()
        for identifier, content in resources.items():
            registry = registry.with_resource(identifier, Resource.from_contents(content))
        validator = Draft202012Validator(schema, registry=registry)
    else:
        # Keep the Planner runnable on supported distro packages that predate
        # the referencing API; this resolves the same local planning schemas.
        from jsonschema import RefResolver

        validator = Draft202012Validator(
            schema,
            resolver=RefResolver.from_schema(schema, store=resources),
        )
    errors: list[dict[str, Any]] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        errors.append(
            {
                "code": "SCHEMA_INVALID",
                "path": ".".join(str(part) for part in error.absolute_path) or "$",
                "message": error.message,
                "repairable": True,
            }
        )
    return errors


def _assert_schema(payload: dict[str, Any], schema_path: Path, label: str) -> None:
    errors = _schema_errors(payload, schema_path)
    if errors:
        first = errors[0]
        raise ElasticPlannerError(
            f"{label} violated its contract at {first['path']}: {first['message']}"
        )


def _requirement_id(requirement: dict[str, Any]) -> str:
    return str(
        requirement.get("id")
        or requirement.get("requirement_id")
        or requirement.get("obligation_id")
        or ""
    ).strip()


def requirements(requirement_ir: dict[str, Any]) -> list[dict[str, Any]]:
    rows = requirement_ir.get("requirements")
    if not isinstance(rows, list):
        rows = requirement_ir.get("obligations")
    if not isinstance(rows, list):
        rows = []
    normalized = [dict(row) for row in rows if isinstance(row, dict)]
    ids = [_requirement_id(row) for row in normalized]
    if not normalized or any(not item for item in ids):
        raise ElasticPlannerError("RequirementIR must contain identified requirements or obligations")
    if len(ids) != len(set(ids)):
        raise ElasticPlannerError("RequirementIR contains duplicate requirement identifiers")
    return normalized


def requirement_ir_id(requirement_ir: dict[str, Any]) -> str:
    value = str(
        requirement_ir.get("requirement_ir_id")
        or requirement_ir.get("id")
        or ""
    ).strip()
    if not value:
        raise ElasticPlannerError("RequirementIR has no stable identifier")
    return value


def _requirement_text(requirement: dict[str, Any]) -> str:
    return str(
        requirement.get("statement")
        or requirement.get("source_text")
        or requirement.get("description")
        or requirement.get("goal")
        or ""
    ).strip()


def _requirement_verifier(requirement: dict[str, Any]) -> str:
    check = requirement.get("check")
    if isinstance(check, dict):
        value = check.get("check_id") or check.get("id")
    else:
        value = check
    return str(
        value
        or requirement.get("verifier_id")
        or requirement.get("verification_method")
        or "not_machine_checkable"
    ).strip()


def _workflow_summaries(workflows_dir: Path = WORKFLOWS_DIR) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for contract in workflow_contract.load_all_contracts(workflows_dir, skip_invalid=True):
        placeholder_occurrences: dict[str, set[str]] = {}
        for value in _string_values(contract):
            for name in re.findall(r"<([A-Za-z][A-Za-z0-9_]*)>", value):
                if name in _SYSTEM_WORKFLOW_INPUTS:
                    continue
                placeholder_occurrences.setdefault(name, set()).add(value)
        summaries.append(
            {
                "workflow_id": str(contract.get("workflow_id") or ""),
                "version": str(contract.get("version") or ""),
                "title": str(contract.get("title") or ""),
                "stages_mode": str(contract.get("stages_mode") or "fixed"),
                "stage_count": len(contract.get("stages") or []),
                "stage_ids": [
                    str(stage.get("id") or "")
                    for stage in contract.get("stages") or []
                    if isinstance(stage, dict)
                ],
                "stages": [
                    {
                        "stage_id": str(stage.get("id") or ""),
                        "logical_operator": str(stage.get("logical_operator") or ""),
                        "depends_on": [str(value) for value in stage.get("depends_on") or []],
                        "outputs": [
                            {
                                "path": str(output.get("path") or ""),
                                "type": str(output.get("type") or "artifact"),
                            }
                            for output in stage.get("outputs") or []
                            if isinstance(output, dict)
                        ],
                        "gate_kind": str((stage.get("evaluator_gate") or {}).get("kind") or ""),
                    }
                    for stage in contract.get("stages") or []
                    if isinstance(stage, dict)
                ],
                "required_inputs": [
                    {
                        "name": name,
                        "occurrences": sorted(values),
                    }
                    for name, values in sorted(placeholder_occurrences.items())
                ],
                "description": str(contract.get("description") or ""),
            }
        )
    return sorted(summaries, key=lambda row: (row["workflow_id"], row["version"]))


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_values(item)


def _logical_operator_summaries(path: Path = LOGICAL_OPERATORS_PATH) -> list[dict[str, Any]]:
    payload = _load_json(path)
    rows = []
    for operator_id, spec in (payload.get("logical_operators") or {}).items():
        if not isinstance(spec, dict):
            continue
        rows.append(
            {
                "logical_operator": str(operator_id),
                "description": str(spec.get("description") or ""),
                "primary_role": str(spec.get("primary_role") or ""),
                "required_capabilities": sorted(
                    str(value) for value in (spec.get("required_capabilities") or {}).keys()
                ),
                "cost_hint": str(spec.get("cost_hint") or ""),
            }
        )
    return sorted(rows, key=lambda row: row["logical_operator"])


def _canonical_manifest_artifact(item: Any) -> str:
    """Return only an artifact identity explicitly declared by the manifest.

    ``composition.type`` is already a canonical artifact identifier.  Newer
    manifests sometimes use ``schema_ref`` instead; those are namespaced so a
    schema path can never be confused with a legacy ``type`` or contract field
    name.  We deliberately do not infer equivalence from similar names.
    """
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    declared_type = str(item.get("type") or "").strip()
    if declared_type:
        return declared_type
    schema_ref = str(item.get("schema_ref") or "").strip()
    return f"schema:{schema_ref}" if schema_ref else ""


def _manifest_contract_shapes(section: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in section or []:
        if isinstance(item, str):
            rows.append({"name": item, "type": "", "schema_ref": ""})
            continue
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "name": str(item.get("name") or ""),
                "type": str(item.get("type") or ""),
                "schema_ref": str(item.get("schema_ref") or ""),
                "cardinality": str(item.get("cardinality") or "one"),
            }
        )
    return rows


def _capsule_summaries(
    capsule_registry_path: Path = CAPSULE_REGISTRY_PATH,
    physical_operators_path: Path = PHYSICAL_OPERATORS_PATH,
) -> list[dict[str, Any]]:
    """Freeze bounded, canonical capsule facts for planning and selection."""
    physical_payload = _load_json(physical_operators_path)
    physical_rows = physical_payload.get("operators") or {}
    selectable_operator_ids = {
        str(operator_id)
        for operator_id, spec in physical_rows.items()
        if isinstance(spec, dict)
        and bool(spec.get("enabled", True))
        and not bool(spec.get("deprecated", False))
    }
    summaries: list[dict[str, Any]] = []
    for entry in iter_registry_entries(path=capsule_registry_path):
        if entry.capsule_kind != "capability":
            continue
        manifest_path = Path(entry.manifest_path)
        manifest = load_capability_capsule_manifest(manifest_path)
        composition = manifest.get("composition") if isinstance(manifest.get("composition"), dict) else {}
        contract = manifest.get("contract") if isinstance(manifest.get("contract"), dict) else {}
        inputs = contract.get("inputs") if isinstance(contract.get("inputs"), dict) else {}
        outputs = contract.get("outputs") if isinstance(contract.get("outputs"), dict) else {}
        effects = manifest.get("effects") if isinstance(manifest.get("effects"), dict) else {}
        verification = manifest.get("verification") if isinstance(manifest.get("verification"), dict) else {}
        compatibility = (
            manifest.get("operator_compatibility")
            if isinstance(manifest.get("operator_compatibility"), dict)
            else {}
        )
        bindings = manifest.get("bindings") if isinstance(manifest.get("bindings"), dict) else {}
        implementation = (
            manifest.get("implementation")
            if isinstance(manifest.get("implementation"), dict)
            else {}
        )
        trust_class = str(implementation.get("trust_class") or "unspecified")
        if trust_class not in capsule_composition.EXECUTION_TRUST_CLASSES:
            raise ElasticPlannerError(
                f"capsule {entry.capability_capsule_id!r} declares unknown execution trust {trust_class!r}"
            )
        skills = bindings.get("skills") if isinstance(bindings.get("skills"), dict) else {}
        preferred = sorted(str(value) for value in compatibility.get("preferred") or [] if str(value))
        declared_implementation = bool(
            preferred
            or effects.get("execute")
            or skills.get("required")
            or skills.get("optional")
        )
        summaries.append(
            {
                "capsule_id": entry.capability_capsule_id,
                "version": entry.version,
                "status": entry.status,
                "description": str((manifest.get("metadata") or {}).get("description") or ""),
                "task_types": sorted(
                    str(value)
                    for value in (manifest.get("applicability") or {}).get("task_types") or []
                    if str(value)
                ),
                "consumes": sorted(
                    value
                    for value in (
                        _canonical_manifest_artifact(item)
                        for item in composition.get("consumes") or []
                    )
                    if value
                ),
                "produces": sorted(
                    value
                    for value in (
                        _canonical_manifest_artifact(item)
                        for item in composition.get("produces") or []
                    )
                    if value
                ),
                "contract": {
                    "required_inputs": _manifest_contract_shapes(inputs.get("required")),
                    "optional_inputs": _manifest_contract_shapes(inputs.get("optional")),
                    "required_outputs": _manifest_contract_shapes(outputs.get("required")),
                    "optional_outputs": _manifest_contract_shapes(outputs.get("optional")),
                },
                "effects": {
                    key: sorted(str(value) for value in effects.get(key) or [] if str(value))
                    for key in ("read", "write", "execute", "network", "cost", "risk")
                },
                "verification": {
                    "self_checks": [str(value) for value in verification.get("self_check") or []],
                    "pass_conditions": [str(value) for value in verification.get("pass_conditions") or []],
                    "external_required": bool(
                        ((verification.get("external_verifier") or {}).get("required"))
                    ),
                },
                "implementation": {
                    "declared": declared_implementation,
                    "trust_class": trust_class,
                    "execute": [str(value) for value in effects.get("execute") or []],
                    "required_skills": [str(value) for value in skills.get("required") or []],
                },
                "operator_compatibility": {
                    "preferred": preferred,
                    "forbidden": sorted(
                        str(value) for value in compatibility.get("forbidden") or [] if str(value)
                    ),
                    "selectable_preferred": sorted(set(preferred) & selectable_operator_ids),
                },
                "manifest_sha256": _file_sha256(manifest_path),
            }
        )
    return sorted(summaries, key=lambda row: row["capsule_id"])


def build_planning_catalog_snapshot(
    *,
    workflows_dir: Path = WORKFLOWS_DIR,
    logical_operators_path: Path = LOGICAL_OPERATORS_PATH,
    capsule_registry_path: Path = CAPSULE_REGISTRY_PATH,
    physical_operators_path: Path = PHYSICAL_OPERATORS_PATH,
) -> dict[str, Any]:
    workflow_rows = _workflow_summaries(workflows_dir)
    logical_rows = _logical_operator_summaries(logical_operators_path)
    capsule_rows = _capsule_summaries(capsule_registry_path, physical_operators_path)
    physical_payload = _load_json(physical_operators_path)
    physical_rows = physical_payload.get("operators") or {}
    enabled_physical = sorted(
        str(operator_id)
        for operator_id, spec in physical_rows.items()
        if isinstance(spec, dict)
        and bool(spec.get("enabled", True))
        and not bool(spec.get("deprecated", False))
    )
    snapshot = {
        "schema_version": "solar.planning_catalog_snapshot.v1",
        "artifact_role": "runtime_artifact",
        "workflows": workflow_rows,
        "logical_operators": logical_rows,
        "capsules": capsule_rows,
        "registries": {
            "workflows_sha256": sha256_payload({"workflows": workflow_rows}),
            "logical_operators_sha256": sha256_payload({"logical_operators": logical_rows}),
            "capsule_registry_sha256": _file_sha256(capsule_registry_path),
            "physical_operators_sha256": _file_sha256(physical_operators_path),
        },
        "enabled_physical_operator_ids": enabled_physical,
    }
    snapshot["catalog_sha256"] = sha256_payload(snapshot)
    _assert_schema(snapshot, CATALOG_SCHEMA, "planning_catalog_snapshot")
    return snapshot


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize_planning_context(
    requirement_ir: dict[str, Any],
    upstream_artifacts: dict[str, dict[str, Any]] | None,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Freeze the accepted upstream artifact bundle consumed by planning."""
    artifacts: dict[str, dict[str, Any]] = {"requirement_ir": requirement_ir}
    for name, payload in (upstream_artifacts or {}).items():
        normalized_name = str(name or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", normalized_name):
            raise ElasticPlannerError(f"invalid planning input artifact name: {name!r}")
        if normalized_name == "requirement_ir":
            if payload != requirement_ir:
                raise ElasticPlannerError("upstream requirement_ir conflicts with the authoritative input")
            continue
        if not isinstance(payload, dict):
            raise ElasticPlannerError(f"planning input {normalized_name!r} must be a JSON object")
        artifacts[normalized_name] = copy.deepcopy(payload)

    rows: list[dict[str, str]] = []
    for name, payload in sorted(artifacts.items()):
        relative_path = "requirement_ir.json" if name == "requirement_ir" else f"inputs/{name}.json"
        write_json(output_dir / relative_path, payload)
        row = {
            "name": name,
            "relative_path": relative_path,
            "sha256": sha256_payload(payload),
        }
        explicit_artifact_type = payload.get("artifact_type")
        if explicit_artifact_type is not None:
            if not isinstance(explicit_artifact_type, str) or not explicit_artifact_type.strip():
                raise ElasticPlannerError(
                    f"planning input {name!r} has an invalid explicit artifact_type"
                )
            row["artifact_type"] = explicit_artifact_type.strip()
        rows.append(row)
    context = {
        "schema_version": "solar.planning_context.v1",
        "artifact_role": "runtime_artifact",
        "planning_context_id": f"planning-context-{requirement_ir_id(requirement_ir)}",
        "artifacts": rows,
    }
    _assert_schema(context, CONTEXT_SCHEMA, "planning_context")
    write_json(output_dir / "planning_context.json", context)
    return context, artifacts


def _planning_input_artifact_types(
    planning_inputs: dict[str, dict[str, Any]],
) -> set[str]:
    """Return only explicitly normalized upstream artifact identities.

    A schema version, filename, or fixture label is not an artifact identity.
    The input normalizer must state the exact registry identity when an
    attachment is intended to cross the Planner boundary as a typed input.
    """
    return {
        str(payload.get("artifact_type") or "").strip()
        for payload in planning_inputs.values()
        if isinstance(payload, dict)
        and isinstance(payload.get("artifact_type"), str)
        and str(payload.get("artifact_type") or "").strip()
    }


def _planning_context_artifact_types(planning_context: dict[str, Any]) -> set[str]:
    return {
        str(row.get("artifact_type") or "").strip()
        for row in planning_context.get("artifacts") or []
        if isinstance(row, dict) and str(row.get("artifact_type") or "").strip()
    }


def _decision_prompt(
    requirement_ir: dict[str, Any],
    catalog: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    *,
    generation: int,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> str:
    instruction = """
You are Solar's Elastic Planner strategy chooser. Choose the smallest sufficient MVP strategy.
Use direct_response only when no retrieval, external effect, execution, multi-artifact dependency,
long-running work, or workflow is required. Use exact_reuse only when one registered workflow covers
every requirement without topology changes. Otherwise use generate. Parameterize, extend, and compose
are not supported. List every RequirementIR identifier exactly once in requirement_ids.
When planner_hints.preferred_outcome is direct_answer and runtime_handoff_allowed is false, choose
direct_response unless the admitted requirements contradict those hints. Do not upgrade a bounded
answer into generate merely to obtain Builder execution or a TaskGraph.
Treat identifiers, hashes, filenames, paths, and fixture labels as opaque references. Never infer user
meaning, audience, domain, or scope from them; derive meaning only from admitted semantic content.
For exact_reuse, workflow_bindings must contain one record per requirement identifier with one or more
real stage IDs from the selected workflow. workflow_inputs must contain one name/value record per
required placeholder shown in required_inputs. Use the placeholder name without angle brackets and
the replacement value without a suffix already present in an occurrence (for `<tool>.py`, bind
`tool=slugify`, not `slugify.py`). For all other decisions both arrays must be empty.
Set workflow_ref to a registered workflow only for exact_reuse. For direct_response or generate,
workflow_ref must be null, even when the rationale discusses a similar workflow that was rejected.
If IntentIR/raw context is supplied and reveals that RequirementIR omitted a user obligation, record a
requirements_gap with source references; never silently add the missing obligation. A requirements gap
invalidates planning and returns to the Requirement Compiler. Do not create a DAG in this decision.
""".strip()
    payload: dict[str, Any] = {
        "instruction": instruction,
        "requirement_ir": requirement_ir,
        "upstream_artifacts": planning_inputs,
        "planning_catalog": {
            "workflows": catalog.get("workflows", []),
            "catalog_sha256": catalog.get("catalog_sha256"),
        },
    }
    if generation:
        payload.update(
            {
                "repair_instruction": "Correct only the listed defects; preserve unaffected decisions.",
                "previous": previous,
                "defects": defects or [],
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def compile_planning_decision(
    requirement_ir: dict[str, Any],
    catalog: dict[str, Any],
    planning_context: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    model: JsonModel,
    work_dir: Path,
    *,
    generation: int = 0,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    planner_hints = (
        requirement_ir.get("planner_hints")
        if isinstance(requirement_ir.get("planner_hints"), dict)
        else {}
    )
    direct_answer_required = (
        requirement_ir.get("request_type") == "direct_answer"
        and planner_hints.get("preferred_outcome") == "direct_answer"
        and planner_hints.get("runtime_handoff_allowed") is False
    )
    if direct_answer_required:
        # This is a Planner-owned policy decision, not an answer produced by
        # either compiler.  The Planner model still authors direct_response
        # below; avoiding a separate model call here removes latency without
        # transferring response authority upstream.
        body = {
            "decision": "direct_response",
            "rationale": [
                "The accepted RequirementIR requires a direct answer and explicitly forbids runtime handoff."
            ],
            "requirement_ids": [
                _requirement_id(row)
                for row in requirements(requirement_ir)
                if _requirement_id(row)
            ],
            "workflow_ref": None,
            "workflow_inputs": [],
            "workflow_bindings": [],
            "requirements_gap": None,
        }
        producer = {
            "method": "policy",
            "provider": "solar",
            "model": "planner-direct-route-v1",
            "role": "planner",
            "component": "elastic_planner",
        }
    else:
        body = model.generate(
            _decision_prompt(
                requirement_ir,
                catalog,
                planning_inputs,
                generation=generation,
                previous=previous,
                defects=defects,
            ),
            DECISION_BODY_SCHEMA,
            work_dir / "decision_call",
        )
        producer = {
            "method": "model",
            "provider": model.provider,
            "model": model.model or "configured_default",
            "role": "planner",
            "component": "elastic_planner",
        }
    rid = requirement_ir_id(requirement_ir)
    artifact = {
        "schema_version": "solar.planning_decision.v1",
        "artifact_role": "runtime_artifact",
        "planning_decision_id": f"planning-decision-{rid}-g{generation}",
        "generation": generation,
        "requirement_ir_ref": {
            "requirement_ir_id": rid,
            "sha256": sha256_payload(requirement_ir),
        },
        "planning_context_ref": {
            "planning_context_id": planning_context.get("planning_context_id"),
            "sha256": sha256_payload(planning_context),
        },
        "producer": producer,
        **body,
    }
    _assert_schema(artifact, DECISION_SCHEMA, "planning_decision")
    return artifact


def validate_planning_decision(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    catalog: dict[str, Any],
    planning_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    errors = _schema_errors(decision, DECISION_SCHEMA)
    rid = requirement_ir_id(requirement_ir)
    reference = decision.get("requirement_ir_ref") or {}
    if reference.get("requirement_ir_id") != rid or reference.get("sha256") != sha256_payload(
        requirement_ir
    ):
        errors.append(_error("REQUIREMENT_IR_REF_MISMATCH", "requirement_ir_ref", "Decision does not bind the exact RequirementIR."))
    if planning_context is not None:
        context_ref = decision.get("planning_context_ref") or {}
        if (
            context_ref.get("planning_context_id") != planning_context.get("planning_context_id")
            or context_ref.get("sha256") != sha256_payload(planning_context)
        ):
            errors.append(_error("PLANNING_CONTEXT_REF_MISMATCH", "planning_context_ref", "Decision does not bind the exact upstream planning context."))
    expected_ids = {_requirement_id(row) for row in requirements(requirement_ir)}
    actual_ids = {str(value) for value in decision.get("requirement_ids") or []}
    if actual_ids != expected_ids:
        errors.append(
            _error(
                "REQUIREMENT_SET_MISMATCH",
                "requirement_ids",
                f"Expected {sorted(expected_ids)}; received {sorted(actual_ids)}.",
            )
        )
    strategy = str(decision.get("decision") or "")
    if strategy not in MVP_DECISIONS:
        errors.append(_error("STRATEGY_UNSUPPORTED", "decision", f"Unsupported MVP strategy: {strategy!r}."))
    planner_hints = (
        requirement_ir.get("planner_hints")
        if isinstance(requirement_ir.get("planner_hints"), dict)
        else {}
    )
    if (
        planner_hints.get("preferred_outcome") == "direct_answer"
        and planner_hints.get("runtime_handoff_allowed") is False
        and strategy != "direct_response"
    ):
        errors.append(
            _error(
                "DIRECT_RESPONSE_ROUTE_VIOLATED",
                "decision",
                "RequirementIR requires a direct response and forbids runtime handoff.",
            )
        )
    workflow_ref = decision.get("workflow_ref")
    workflows = {
        (row["workflow_id"], row["version"])
        for row in catalog.get("workflows", [])
        if isinstance(row, dict)
    }
    if strategy == "exact_reuse":
        if not isinstance(workflow_ref, dict):
            errors.append(_error("WORKFLOW_REF_REQUIRED", "workflow_ref", "Exact reuse requires a frozen workflow id and version."))
        else:
            key = (str(workflow_ref.get("workflow_id") or ""), str(workflow_ref.get("version") or ""))
            if key not in workflows:
                errors.append(_error("WORKFLOW_REF_UNKNOWN", "workflow_ref", f"Workflow {key!r} is not in the planning snapshot."))
            else:
                workflow = next(
                    row
                    for row in catalog.get("workflows", [])
                    if isinstance(row, dict)
                    and (row.get("workflow_id"), row.get("version")) == key
                )
                if str(workflow.get("stages_mode") or "fixed") == "planner_generated":
                    errors.append(_error("WORKFLOW_NOT_REUSABLE", "workflow_ref", "A planner-generated workflow has no fixed topology to reuse."))
                required_inputs = {
                    str(row.get("name") or "")
                    for row in workflow.get("required_inputs") or []
                    if isinstance(row, dict) and str(row.get("name") or "")
                }
                input_map = _workflow_input_map(decision, errors)
                provided_inputs = set(input_map)
                missing_inputs = sorted(required_inputs - provided_inputs)
                unknown_inputs = sorted(provided_inputs - required_inputs)
                empty_inputs = sorted(name for name, value in input_map.items() if not value.strip())
                if missing_inputs:
                    errors.append(_error("WORKFLOW_INPUT_REQUIRED", "workflow_inputs", f"Missing required workflow inputs: {missing_inputs}."))
                if unknown_inputs:
                    errors.append(_error("WORKFLOW_INPUT_UNKNOWN", "workflow_inputs", f"Unknown workflow inputs: {unknown_inputs}."))
                if empty_inputs:
                    errors.append(_error("WORKFLOW_INPUT_EMPTY", "workflow_inputs", f"Workflow inputs must be non-empty: {empty_inputs}."))
                stage_ids = {str(value) for value in workflow.get("stage_ids") or []}
                known_operators = _known_logical_operators(catalog)
                unknown_operators = sorted(
                    {
                        str(stage.get("logical_operator") or "")
                        for stage in workflow.get("stages") or []
                        if isinstance(stage, dict)
                        and str(stage.get("logical_operator") or "")
                        not in known_operators
                    }
                )
                if unknown_operators:
                    errors.append(
                        _error(
                            "WORKFLOW_LOGICAL_OPERATOR_UNKNOWN",
                            "workflow_ref",
                            (
                                "Exact reuse is unavailable because the workflow contains "
                                f"unregistered logical operators: {unknown_operators}. Choose "
                                "generate unless a different fully registered workflow fits."
                            ),
                        )
                    )
                binding_rows = [
                    row
                    for row in decision.get("workflow_bindings") or []
                    if isinstance(row, dict)
                ]
                bindings = {
                    str(row.get("requirement_id") or ""): list(row.get("stage_ids") or [])
                    for row in binding_rows
                }
                if len(bindings) != len(binding_rows):
                    errors.append(_error("WORKFLOW_BINDING_DUPLICATE", "workflow_bindings", "Requirement binding identifiers must be unique."))
                if set(bindings) != expected_ids:
                    errors.append(_error("WORKFLOW_BINDING_REQUIREMENTS_MISMATCH", "workflow_bindings", "Exact reuse must bind every and only accepted requirement."))
                for req_id, owners in bindings.items():
                    unknown = sorted({str(value) for value in owners or []} - stage_ids)
                    if unknown:
                        errors.append(_error("WORKFLOW_BINDING_STAGE_UNKNOWN", f"workflow_bindings.{req_id}", f"Unknown workflow stages: {unknown}."))
                contract = workflow_contract.find_contract(key[0], WORKFLOWS_DIR)
                try:
                    workflow_contract.instantiate(
                        contract,
                        {
                            "sprint_id": "sprint-planning-validation",
                            "sid": "sprint-planning-validation",
                            "workspace_root": "workspace",
                            **input_map,
                        },
                    )
                    unresolved = sorted(
                        {
                            name
                            for value in _string_values(workflow_contract.instantiate(
                                contract,
                                {
                                    "sprint_id": "sprint-planning-validation",
                                    "sid": "sprint-planning-validation",
                                    "workspace_root": "workspace",
                                    **input_map,
                                },
                            ))
                            for name in re.findall(r"<([A-Za-z][A-Za-z0-9_]*)>", value)
                            if name not in _SYSTEM_WORKFLOW_INPUTS
                        }
                    )
                    if unresolved:
                        errors.append(_error("WORKFLOW_INPUTS_UNRESOLVED", "workflow_inputs", f"Unresolved workflow placeholders: {unresolved}."))
                except Exception as exc:
                    errors.append(_error("WORKFLOW_INPUTS_INVALID", "workflow_inputs", str(exc)))
    elif workflow_ref is not None:
        errors.append(_error("WORKFLOW_REF_FORBIDDEN", "workflow_ref", f"{strategy} must not claim exact workflow reuse."))
    if strategy != "exact_reuse" and decision.get("workflow_bindings"):
        errors.append(_error("WORKFLOW_BINDINGS_FORBIDDEN", "workflow_bindings", f"{strategy} must not bind registered workflow stages."))
    if strategy != "exact_reuse" and decision.get("workflow_inputs"):
        errors.append(_error("WORKFLOW_INPUTS_FORBIDDEN", "workflow_inputs", f"{strategy} must not bind registered workflow inputs."))
    if decision.get("requirements_gap") is not None:
        errors.append(
            {
                "code": "REQUIREMENTS_GAP",
                "path": "requirements_gap",
                "message": str((decision.get("requirements_gap") or {}).get("description") or "RequirementIR omitted a user obligation."),
                "repairable": False,
            }
        )
    return errors


def _workflow_input_map(
    decision: dict[str, Any],
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    rows = [
        row
        for row in decision.get("workflow_inputs") or []
        if isinstance(row, dict)
    ]
    result = {
        str(row.get("name") or ""): str(row.get("value") or "")
        for row in rows
    }
    if errors is not None and len(result) != len(rows):
        errors.append(_error("WORKFLOW_INPUT_DUPLICATE", "workflow_inputs", "Workflow input names must be unique."))
    return result


def _workflow_binding_map(decision: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(row.get("requirement_id") or ""): [
            str(value) for value in row.get("stage_ids") or []
        ]
        for row in decision.get("workflow_bindings") or []
        if isinstance(row, dict)
    }


def _error(code: str, path: str, message: str, *, repairable: bool = True) -> dict[str, Any]:
    return {"code": code, "path": path, "message": message, "repairable": repairable}


def compile_direct_response(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    model: JsonModel,
    work_dir: Path,
    *,
    generation: int,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    instruction = (
        "Answer the accepted RequirementIR directly. Do not claim execution, retrieval, or external "
        "effects. Cover every requirement identifier exactly once in requirement_ids. State any "
        "material limitation honestly. Treat identifiers, hashes, filenames, paths, and fixture labels "
        "as opaque references, never as user meaning. Requirement acceptance.required_values are "
        "semantic criteria to cover in answer or limitations; they are top-level JSON fields only when "
        "the supplied response schema explicitly defines them. Return only the schema-bound response body."
    )
    prompt: dict[str, Any] = {
        "instruction": instruction,
        "requirement_ir": requirement_ir,
        "upstream_artifacts": planning_inputs,
        "planning_decision": decision,
    }
    if generation:
        prompt.update(
            {
                "repair_instruction": "Repair only the independently reported defects.",
                "previous": previous,
                "defects": defects or [],
            }
        )
    body = model.generate(
        json.dumps(prompt, ensure_ascii=False, indent=2),
        DIRECT_RESPONSE_BODY_SCHEMA,
        work_dir / "direct_response_call",
    )
    expected_ids = {_requirement_id(row) for row in requirements(requirement_ir)}
    actual_ids = {str(value) for value in body.get("requirement_ids") or []}
    if actual_ids != expected_ids:
        raise ElasticPlannerError(
            f"direct response requirement set mismatch: expected {sorted(expected_ids)}, received {sorted(actual_ids)}"
        )
    rid = requirement_ir_id(requirement_ir)
    artifact = {
        "schema_version": "solar.direct_response.v1",
        "artifact_role": "runtime_artifact",
        "response_id": f"direct-response-{rid}-g{generation}",
        "generation": generation,
        "requirement_ir_ref": {
            "requirement_ir_id": rid,
            "sha256": sha256_payload(requirement_ir),
        },
        "planning_decision_ref": {
            "planning_decision_id": decision.get("planning_decision_id"),
            "sha256": sha256_payload(decision),
        },
        "producer": {
            "method": "model",
            "provider": model.provider,
            "model": model.model or "configured_default",
            "role": "planner",
            "component": "elastic_planner",
        },
        **body,
    }
    _assert_schema(artifact, DIRECT_RESPONSE_SCHEMA, "direct_response")
    return artifact


def review_direct_response(
    requirement_ir: dict[str, Any],
    response: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    reviewer: JsonModel,
    work_dir: Path,
) -> dict[str, Any]:
    prompt = {
        "instruction": (
            "Independently judge the direct answer. Return each required check exactly once. "
            "Fail omitted or weakened requirements, claims not supported by the admitted input, "
            "or language implying execution/retrieval that did not occur. Treat identifiers, hashes, "
            "filenames, paths, and fixture labels as opaque references, never as user meaning. "
            "Requirement acceptance.required_values are semantic criteria, not automatically top-level "
            "JSON fields; require a top-level field only if the direct-response schema defines it. "
            "Do not rewrite the answer."
        ),
        "required_checks": [
            "requirement_coverage",
            "answer_fidelity",
            "factual_restraint",
        ],
        "requirement_ir": requirement_ir,
        "upstream_artifacts": planning_inputs,
        "direct_response": response,
    }
    body = reviewer.generate(
        json.dumps(prompt, ensure_ascii=False, indent=2),
        DIRECT_RESPONSE_REVIEW_BODY_SCHEMA,
        work_dir / "direct_response_review_call",
    )
    required_kinds = {"requirement_coverage", "answer_fidelity", "factual_restraint"}
    actual = [str(row.get("kind") or "") for row in body.get("checks") or []]
    if len(actual) != len(required_kinds) or set(actual) != required_kinds:
        raise ElasticPlannerError(
            "direct response reviewer did not return every required check exactly once"
        )
    errors = list(body.get("errors") or [])
    if any(row.get("status") == "fail" for row in body.get("checks") or []) and not errors:
        raise ElasticPlannerError("direct response reviewer failed a check without a typed error")
    warnings = list(body.get("warnings") or [])
    artifact = {
        "schema_version": "solar.direct_response_review.v1",
        "artifact_role": "runtime_artifact",
        "review_id": f"direct-response-review-{response.get('response_id')}",
        "response_ref": {
            "response_id": response.get("response_id"),
            "generation": response.get("generation"),
            "sha256": sha256_payload(response),
        },
        "review_method": "independent_model_call",
        "reviewer": {
            "provider": reviewer.provider,
            "model": reviewer.model or "configured_default",
            "role": "evaluator",
            "component": "direct_response_reviewer",
        },
        "status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
        "checks": body.get("checks") or [],
        "errors": errors,
        "warnings": warnings,
    }
    _assert_schema(artifact, DIRECT_RESPONSE_REVIEW_SCHEMA, "direct_response_review")
    return artifact


def _plan_prompt(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    catalog: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    evaluation_registry: dict[str, Any],
    *,
    generation: int,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> str:
    instruction = """
You are Solar's semantic DAG planner. Produce the smallest sufficient PlanIR body.
Treat identifiers, hashes, filenames, paths, and fixture labels as opaque references. Never infer user
meaning, audience, domain, or scope from them; use only admitted semantic content.
Use only logical_operator values in the supplied registry. PlanIR describes meaning, dependencies,
typed artifact handoffs, requirement ownership, resource needs, and verification needs. It must not
name a capability capsule, model, profile, pane, or physical operator. Every RequirementIR identifier
must be owned by at least one node. Support nodes may have an empty requirement_ids list only when they
cannot be traced to an accepted requirement. A source- or literature-discovery node must own the
scope/evidence-coverage requirements that define what evidence it must retrieve; do not assign it a
final-answer, publication, or delivery requirement. Preserve the exact named subjects, comparison
dimensions, constraints, and required coverage values from those requirements in the discovery node's
objective for human understanding. When RequirementIR has semantic_contract, its requirement_roles
are authoritative (not substrings in check names). Set retrieval_contract_ref to discovery.contract_id
on a discovery node or a logical node requiring discovery in its implementation; otherwise use null.
Do NOT restate process/delivery constraints as research subjects or source filters. The physical operator
receives the exact structured retrieval contract, never a reinterpreted objective. Assign
a requirement only to a node whose produced artifact can actually be judged by that requirement's check.
Requirements whose acceptance contract calls for a finding, supporting evidence, and unresolved status
are resolution requirements, not discovery-scope requirements. A discovery node may retain those study
protocol questions as context only, not as search scope, and it must not own them when its output ABI promises
only a source shortlist. Assign their ownership to a downstream synthesis or report node whose artifact
can explicitly resolve the question or preserve it as unresolved with evidence.
Keep implementation-only support steps out of PlanIR. A single logical node may be implemented by a
multi-capsule chain, so declare that node's external input/output boundary and let capsule composition
insert internal artifacts such as a report plan. Add a separate logical node only when it represents a
distinct user-visible operation, independently owned requirement, effect boundary, or dependency.
For every requirement it owns, the matching produced artifact must list that requirement's exact
check/verification identifier in verifier_ids. For artifact_type checks, the output artifact_type must
appear in that check's artifact_types. Support outputs should use their compatible auto-apply artifact
check when one exists. Never invent, combine, rename, or weaken verifier identifiers.
The capsule ABI catalog is authoritative for executable artifact identities. Each produced artifact_type
must be copied exactly from at least one capsule's `produces`; each non-RequirementIR consumed type
must be copied exactly from an upstream node output. Design each logical node contract so either one
capsule or a typed composition of capsules can satisfy its declared inputs, outputs, effects, and network
policy. Do not name or select capsules in PlanIR; a later binding pass owns that decision.
`schema:<path>` and `artifact.<name>` are different identities unless a manifest explicitly declares
the same identity; never infer equivalence from similar words or filenames.
A produced artifact must declare how it materializes inside that node's isolated workspace: a safe
relative file or directory path. Never use an absolute path, '..', or a shared path owned by another
node. Code work must name a real code-file output, not only a patch/report placeholder.
When a compatible capsule contract marks an output as type `collection`, materialize that output as a
directory. The directory may contain multiple independently schema-valid artifacts of the declared
artifact_type; do not invent a collection wrapper schema.
A consumed artifact must either be copied exactly from `controller_input_artifact_types` or be produced
by a direct or transitive dependency. Use requirement_ir.v1 when the logical node itself reads the
compiled requirements. Use schema:request-envelope.schema.json when the selected capsule ABI needs the
controller's normalized request envelope. Every value in consumes is an artifact_type identifier, never
a materialization file path and never `node_id:path`.
materialization.path is only the relative file/directory location inside the producer node workspace.
Effects must be explicit. `operator_requirements.effects` is the permission envelope for the capsule
composition that will implement the node, not merely a description of the user's requested outcome.
For every viable capsule chain, include every `active_effects` value used by that chain. In particular,
include `execute` whenever a required capsule ABI lists `execute`, even for information-retrieval or
reporting nodes; include `network` in both `effects` and the network policy when network is required.
Omitting an active effect makes that capsule composition invalid rather than making the effect disappear.
Keep independent work parallel by declaring only real dependencies. Do not add work that no requirement
needs. Set operator_requirements.execution_trust to measured_execution
when the node must produce scientific results from a real dataset/code execution. Fixture, adapter,
lineage, schema, or exit-code-only evidence never satisfies measured_execution. Use evidence_transform
only when the catalog explicitly offers that trust class; otherwise use any when execution authenticity
is irrelevant.
Use at most one logical Critic, Verifier, or Evaluator node in the entire PlanIR, including high-risk
plans. It must be the final independent semantic review. Do not create separate Critic and Verifier
nodes or model-review quorums. Schema validation, hash binding, RequirementIR coverage aggregation,
and proof-obligation checks are deterministic controller gates and do not need additional LLM nodes.
""".strip()
    payload: dict[str, Any] = {
        "instruction": instruction,
        "requirement_ir": requirement_ir,
        "upstream_artifacts": planning_inputs,
        "planning_decision": decision,
        "logical_operators": catalog.get("logical_operators", []),
        "controller_input_artifact_types": sorted(
            _CONTROLLER_INPUT_TYPES | _planning_input_artifact_types(planning_inputs)
        ),
        # PlanIR needs semantic ABI information, not physical bindings, full
        # verification prose, manifest paths, or operator availability detail.
        # The complete snapshot remains frozen for deterministic validation and
        # later binding.
        "capability_capsule_abis": [
            {
                "capsule_id": str(row.get("capsule_id") or ""),
                "description": str(row.get("description") or ""),
                "task_types": list(row.get("task_types") or []),
                "consumes": list(row.get("consumes") or []),
                "produces": list(row.get("produces") or []),
                "active_effects": [
                    effect
                    for effect in ("read", "write", "execute", "network")
                    if _effect_is_active((row.get("effects") or {}).get(effect))
                ],
                "executable": bool((row.get("implementation") or {}).get("declared"))
                and bool(
                    (row.get("operator_compatibility") or {}).get(
                        "selectable_preferred"
                    )
                ),
                "execution_trust": str(
                    (row.get("implementation") or {}).get("trust_class") or "unspecified"
                ),
            }
            for row in catalog.get("capsules", [])
            if isinstance(row, dict)
        ],
        "evaluation_check_abis": [
            {
                "check_id": str(row.get("check_id") or ""),
                "mode": str(row.get("mode") or ""),
                "applies_to_kind": str(
                    (row.get("applies_to") or {}).get("kind") or ""
                ),
                "artifact_types": list(
                    (row.get("applies_to") or {}).get("artifact_types") or []
                ),
                "auto_apply": bool(
                    (row.get("applies_to") or {}).get("auto_apply") is True
                ),
            }
            for row in evaluation_registry.get("checks") or []
            if isinstance(row, dict)
        ],
    }
    if generation:
        payload.update(
            {
                "repair_instruction": (
                    "Correct only listed defects. Preserve unaffected node meaning and identifiers where possible. "
                    "Treat capsule exclusion reason codes literally: UNREQUESTED_<EFFECT>_EFFECT means the "
                    "node must declare <effect> in operator_requirements.effects when that capsule or chain is "
                    "needed for its exact artifact contract. Do not remove the required output or replace the "
                    "logical operation merely to avoid declaring the implementation's real effect. "
                    "Correct every listed defect together. "
                    "Do not delete or bypass an established dependency merely because its artifact identity is "
                    "not capsule-producible. Instead, keep the logical operation and dependency order while "
                    "replacing invalid consumed/produced artifact identities with exact identities from a viable "
                    "capsule chain. A dependency may be folded into another logical node only when the previous "
                    "support artifact is produced and consumed inside every admitted capsule composition."
                ),
                "previous": previous,
                "defects": defects or [],
            }
        )
    # This prompt carries the full semantic capsule/check ABI. Compact JSON
    # keeps registry growth from consuming the model context budget.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def compile_exact_reuse_plan(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    *,
    workflows_dir: Path = WORKFLOWS_DIR,
) -> dict[str, Any]:
    """Project a fixed registered workflow into semantic PlanIR without changing topology."""
    if decision.get("decision") != "exact_reuse":
        raise ElasticPlannerError("exact reuse compilation requires an exact_reuse decision")
    workflow_ref = decision.get("workflow_ref") or {}
    workflow_id = str(workflow_ref.get("workflow_id") or "")
    version = str(workflow_ref.get("version") or "")
    contract = workflow_contract.find_contract(workflow_id, workflows_dir)
    if contract is None or str(contract.get("version") or "") != version:
        raise ElasticPlannerError(f"selected workflow {workflow_id!r} v{version!r} is not registered")
    if str(contract.get("stages_mode") or "fixed") == "planner_generated":
        raise ElasticPlannerError("planner-generated workflow cannot be exact-reused")
    instantiated = workflow_contract.instantiate(
        contract,
        {
            "sprint_id": "sprint-plan-ir-projection",
            "sid": "sprint-plan-ir-projection",
            "workspace_root": "workspace",
            **_workflow_input_map(decision),
        },
    )
    unresolved = sorted(
        {
            name
            for value in _string_values(instantiated)
            for name in re.findall(r"<([A-Za-z][A-Za-z0-9_]*)>", value)
            if name not in _SYSTEM_WORKFLOW_INPUTS
        }
    )
    if unresolved:
        raise ElasticPlannerError(
            f"exact-reuse workflow has unresolved inputs: {unresolved}"
        )
    artifact_root = str((instantiated.get("artifact_roots") or {}).get("canonical") or "")

    def relative_materialization_path(path_text: str, fallback: str) -> str:
        value = str(path_text or fallback)
        if artifact_root and value.startswith(artifact_root):
            value = value[len(artifact_root) :]
        return value.lstrip("/") or fallback

    bindings = _workflow_binding_map(decision)
    requirement_verifiers = {
        _requirement_id(row): _requirement_verifier(row)
        for row in requirements(requirement_ir)
    }
    requirement_by_stage: dict[str, list[str]] = {}
    for req_id, stage_ids in bindings.items():
        for stage_id in stage_ids or []:
            requirement_by_stage.setdefault(str(stage_id), []).append(str(req_id))
    stage_by_id = {
        str(stage.get("id") or ""): stage
        for stage in instantiated.get("nodes") or []
        if isinstance(stage, dict) and str(stage.get("id") or "")
    }
    projected_outputs: dict[str, list[dict[str, Any]]] = {}
    for stage_id, stage in stage_by_id.items():
        stage_requirement_ids = requirement_by_stage.get(stage_id, [])
        stage_verifiers = sorted(
            {
                requirement_verifiers[requirement_id]
                for requirement_id in stage_requirement_ids
                if requirement_id in requirement_verifiers
            }
        ) or [str((stage.get("evaluator_gate") or {}).get("kind") or stage.get("gate_family") or "workflow_gate")]
        outputs = [
            {
                "artifact_type": (
                    f"workflow.{workflow_id}.{stage_id}.output.{index}."
                    f"{str(output.get('type') or 'artifact')}"
                ),
                "verifier_ids": stage_verifiers,
                "materialization": {
                    "kind": "directory" if str(output.get("path") or "").endswith("/") else "file",
                    "path": relative_materialization_path(
                        str(output.get("path") or ""), f"output-{index}.json"
                    ),
                },
            }
            for index, output in enumerate(stage.get("outputs") or [], start=1)
            if isinstance(output, dict)
        ]
        if not outputs:
            outputs.append(
                {
                    "artifact_type": f"workflow.{workflow_id}.{stage_id}.completion.v1",
                    "verifier_ids": stage_verifiers,
                    "materialization": {
                        "kind": "file",
                        "path": f"{_safe_name(stage_id)}-completion.md",
                    },
                }
            )
        projected_outputs[stage_id] = outputs

    def ancestor_ids(stage_id: str) -> list[str]:
        found: list[str] = []

        def visit(current: str) -> None:
            for dependency in (stage_by_id.get(current) or {}).get("depends_on") or []:
                dependency_id = str(dependency)
                visit(dependency_id)
                if dependency_id not in found:
                    found.append(dependency_id)

        visit(stage_id)
        return found

    request_network = _requirement_network_policy(requirement_ir)
    nodes: list[dict[str, Any]] = []
    for stage in instantiated.get("nodes") or []:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("id") or "")
        dependencies = [str(value) for value in stage.get("depends_on") or []]
        gate = stage.get("evaluator_gate") if isinstance(stage.get("evaluator_gate"), dict) else {}
        stage_requirement_ids = requirement_by_stage.get(stage_id, [])
        outputs = projected_outputs[stage_id]
        consumes = [
            output["artifact_type"]
            for ancestor_id in ancestor_ids(stage_id)
            for output in projected_outputs.get(ancestor_id, [])
        ] or ["requirement_ir.v1"]
        logical_operator = str(stage.get("logical_operator") or "")
        logical_spec = _load_json(LOGICAL_OPERATORS_PATH).get("logical_operators", {}).get(logical_operator, {})
        required_capabilities = sorted(
            str(value) for value in (logical_spec.get("required_capabilities") or {}).keys()
        )
        stage_text = json.dumps(stage, ensure_ascii=False).lower()
        stage_requires_network = (
            '"network": true' in stage_text or "source_discovery" in stage_text
        )
        if request_network == "forbidden" and stage_requires_network:
            raise ElasticPlannerError(
                f"exact-reuse stage {stage_id!r} requires network but RequirementIR forbids it"
            )
        network = (
            "required"
            if stage_requires_network
            else "forbidden" if request_network == "forbidden" else "optional"
        )
        nodes.append(
            {
                "node_id": stage_id,
                "logical_operator": logical_operator,
                "objective": str(stage.get("goal") or stage.get("dashboard_label") or f"Execute workflow stage {stage_id}."),
                "depends_on": dependencies,
                "consumes": consumes,
                "produces": outputs,
                "requirement_ids": sorted(set(stage_requirement_ids)),
                "operator_requirements": {
                    "capabilities": required_capabilities,
                    "network": network,
                    "execution_trust": "any",
                    "minimum_context_tokens": 0,
                    "effects": _stage_effects(stage),
                },
                "gate_requirement": str(gate.get("kind") or stage.get("gate_family") or "workflow_gate"),
            }
        )
    return _wrap_plan_ir(
        requirement_ir,
        decision,
        {"nodes": nodes},
        generation=0,
        producer={"method": "workflow_registry", "provider": "solar", "model": "deterministic_projection"},
    )


def _requirement_network_policy(requirement_ir: dict[str, Any]) -> str:
    values = [value.strip().lower() for value in _string_values(requirement_ir.get("scope") or {})]
    if any(value in {"forbidden", "none", "disabled", "network:none"} for value in values):
        return "forbidden"
    if any("required" in value for value in values):
        return "required"
    return "optional"


def _stage_effects(stage: dict[str, Any]) -> list[str]:
    effects = {"read"}
    if stage.get("outputs"):
        effects.add("write")
    serialized = json.dumps(stage, ensure_ascii=False).lower()
    if "command" in serialized or "execute" in serialized or "implementation" in serialized:
        effects.add("execute")
    if "network" in serialized or "source_discovery" in serialized:
        effects.add("network")
    return [name for name in ("read", "write", "execute", "network", "cost", "risk") if name in effects]


def compile_plan_candidate(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    catalog: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    evaluation_registry: dict[str, Any],
    model: JsonModel,
    work_dir: Path,
    *,
    generation: int = 0,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if decision.get("decision") != "generate":
        raise ElasticPlannerError("model PlanIR generation is legal only for the generate strategy")
    body = model.generate(
        _plan_prompt(
            requirement_ir,
            decision,
            catalog,
            planning_inputs,
            evaluation_registry,
            generation=generation,
            previous=previous,
            defects=defects,
        ),
        (SCHEMA_DIR / "plan-ir.semantic.structured.v2.schema.json") if requirement_ir.get("semantic_contract") else PLAN_BODY_SCHEMA,
        work_dir / "plan_call",
    )
    return _wrap_plan_ir(
        requirement_ir,
        decision,
        body,
        generation=generation,
        producer={
            "method": "model",
            "provider": model.provider,
            "model": model.model or "configured_default",
        },
    )


def _is_discovery_node(node: dict[str, Any]) -> bool:
    logical_operator = str(node.get("logical_operator") or "").lower()
    capabilities = {
        str(value).strip().lower()
        for value in ((node.get("operator_requirements") or {}).get("capabilities") or [])
        if str(value).strip()
    }
    return (
        "discover" in logical_operator
        or "source_discovery" in capabilities
        or "literature_discovery" in capabilities
    )


def _is_scope_coverage_requirement(requirement: dict[str, Any]) -> bool:
    acceptance = requirement.get("acceptance")
    acceptance = acceptance if isinstance(acceptance, dict) else {}
    kind = str(acceptance.get("kind") or "").strip().lower()
    check = _requirement_verifier(requirement).lower()
    return kind in {"evidence_coverage", "scope_coverage"} or any(
        token in check
        for token in ("constraint_coverage", "evidence_coverage", "scope_coverage")
    )


def _scope_requirement_text(requirement: dict[str, Any]) -> str:
    statement = _requirement_text(requirement).strip()
    acceptance = requirement.get("acceptance")
    acceptance = acceptance if isinstance(acceptance, dict) else {}
    required_values = [
        str(value).strip()
        for value in acceptance.get("required_values") or []
        if str(value).strip()
    ]
    if required_values:
        coverage = "; ".join(required_values)
        return f"{statement} Required coverage: {coverage}" if statement else f"Required coverage: {coverage}"
    return statement




def _wrap_plan_ir(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    body: dict[str, Any],
    *,
    generation: int,
    producer: dict[str, Any],
) -> dict[str, Any]:
    rid = requirement_ir_id(requirement_ir)
    artifact = {
        "schema_version": "solar.plan_ir.v2",
        "artifact_role": "runtime_artifact",
        "plan_ir_id": f"plan-ir-{rid}-g{generation}",
        "generation": generation,
        "requirement_ir_ref": {
            "requirement_ir_id": rid,
            "sha256": sha256_payload(requirement_ir),
        },
        "planning_decision_ref": {
            "planning_decision_id": decision.get("planning_decision_id"),
            "sha256": sha256_payload(decision),
        },
        "producer": producer,
        "nodes": body.get("nodes", []),
    }
    _assert_schema(artifact, PLAN_SCHEMA, "plan_ir")
    return artifact


def _known_logical_operators(catalog: dict[str, Any]) -> set[str]:
    return {
        str(row.get("logical_operator") or "")
        for row in catalog.get("logical_operators", [])
        if isinstance(row, dict)
    }


def _materialization_error(path_text: str, kind: str) -> str | None:
    path = Path(path_text)
    if path.is_absolute():
        return "materialization path must be relative"
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        return "materialization path contains an empty, current, or parent segment"
    if path.parts[0] in {"workspace", "workdir", "sprints"}:
        return "materialization path must be relative to the node workspace, not a runtime root"
    if kind == "file" and path_text.endswith("/"):
        return "file materialization may not end with '/'"
    if kind == "directory" and path.suffix:
        return "directory materialization may not name a file suffix"
    return None


def _has_cycle(nodes: dict[str, dict[str, Any]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for dependency in nodes[node_id].get("depends_on") or []:
            if str(dependency) in nodes and visit(str(dependency)):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in nodes)


def _ancestors(node_id: str, nodes: dict[str, dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    stack = [str(value) for value in nodes[node_id].get("depends_on") or []]
    while stack:
        current = stack.pop()
        if current in found or current not in nodes:
            continue
        found.add(current)
        stack.extend(str(value) for value in nodes[current].get("depends_on") or [])
    return found


def _dependency_folded_into_admitted_composition(
    *,
    removed_dependency_id: str,
    repaired_node_id: str,
    previous_nodes: dict[str, dict[str, Any]],
    repaired_nodes: dict[str, dict[str, Any]],
    composition_catalog: dict[str, Any] | None,
) -> bool:
    """Prove that a removed support node survives inside capsule composition.

    A repair may collapse a requirement-free support node into another logical
    node only when the new node keeps the support node's upstream order and
    every admitted capsule path still materializes and consumes each of the
    support node's typed outputs internally.  Missing composition evidence
    fails closed.
    """
    removed = previous_nodes.get(removed_dependency_id)
    if removed is None or removed_dependency_id in repaired_nodes:
        return False
    if any(str(value) for value in removed.get("requirement_ids") or []):
        return False

    inherited_ancestors = _ancestors(repaired_node_id, repaired_nodes)
    upstream_dependencies = {
        str(value) for value in removed.get("depends_on") or [] if str(value)
    }
    if not upstream_dependencies.issubset(inherited_ancestors):
        return False

    removed_outputs = {
        str((output or {}).get("artifact_type") or "")
        for output in removed.get("produces") or []
        if isinstance(output, dict)
        and str((output or {}).get("artifact_type") or "")
    }
    if not removed_outputs or not isinstance(composition_catalog, dict):
        return False
    composition_row = next(
        (
            row
            for row in composition_catalog.get("nodes") or []
            if isinstance(row, dict)
            and str(row.get("node_id") or "") == repaired_node_id
        ),
        None,
    )
    if not composition_row:
        return False
    removed_trust = str(
        (removed.get("operator_requirements") or {}).get("execution_trust")
        or "any"
    )
    admitted_trust = str(composition_row.get("execution_trust") or "any")
    trust_rank = capsule_composition.PLANNER_EXECUTION_TRUST_RANK
    if (
        removed_trust not in trust_rank
        or admitted_trust not in trust_rank
        or trust_rank[admitted_trust] < trust_rank[removed_trust]
    ):
        return False
    admitted_ids = {
        str(value)
        for value in composition_row.get("admitted_candidate_ids") or []
        if str(value)
    }
    candidates = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in (composition_row.get("search") or {}).get("candidates") or []
        if isinstance(candidate, dict) and str(candidate.get("candidate_id") or "")
    }
    if not admitted_ids or not admitted_ids.issubset(candidates):
        return False

    for candidate_id in admitted_ids:
        steps = [
            step
            for step in candidates[candidate_id].get("steps") or []
            if isinstance(step, dict)
        ]
        for artifact_type in removed_outputs:
            produced_at = [
                index
                for index, step in enumerate(steps)
                if artifact_type
                in {str(value) for value in step.get("produces") or []}
            ]
            consumed_at = [
                index
                for index, step in enumerate(steps)
                if artifact_type
                in {str(value) for value in step.get("consumes") or []}
            ]
            if not any(
                producer_index < consumer_index
                for producer_index in produced_at
                for consumer_index in consumed_at
            ):
                return False
    return True


def _dependency_expanded_into_repaired_subgraph(
    *,
    removed_dependency_id: str,
    repaired_node_id: str,
    previous_nodes: dict[str, dict[str, Any]],
    repaired_nodes: dict[str, dict[str, Any]],
) -> bool:
    """Prove that repair decomposed one broad node without weakening it.

    The replacement must be made entirely of new ancestors of the downstream
    node, preserve every typed output and owned requirement, retain the old
    inputs and upstream ordering, and keep measured execution when the removed
    node required it.  Merely renaming or deleting a dependency cannot pass.
    """
    removed = previous_nodes.get(removed_dependency_id)
    if removed is None or removed_dependency_id in repaired_nodes:
        return False

    downstream = repaired_nodes.get(repaired_node_id)
    if downstream is None:
        return False
    downstream_ancestors = _ancestors(repaired_node_id, repaired_nodes)
    replacement_ids = downstream_ancestors - set(previous_nodes)
    if not replacement_ids:
        return False
    replacements = [repaired_nodes[node_id] for node_id in sorted(replacement_ids)]

    removed_outputs = {
        str((output or {}).get("artifact_type") or "")
        for output in removed.get("produces") or []
        if isinstance(output, dict)
        and str((output or {}).get("artifact_type") or "")
    }
    if not removed_outputs:
        return False
    produced_by_replacements = {
        str((output or {}).get("artifact_type") or "")
        for replacement in replacements
        for output in replacement.get("produces") or []
        if isinstance(output, dict)
        and str((output or {}).get("artifact_type") or "")
    }
    downstream_inputs = {
        str(value) for value in downstream.get("consumes") or [] if str(value)
    }
    if not removed_outputs.issubset(produced_by_replacements):
        return False
    if not removed_outputs.issubset(downstream_inputs):
        return False

    removed_inputs = {
        str(value) for value in removed.get("consumes") or [] if str(value)
    }
    replacement_inputs = {
        str(value)
        for replacement in replacements
        for value in replacement.get("consumes") or []
        if str(value)
    }
    if not removed_inputs.issubset(replacement_inputs):
        return False

    removed_upstream = {
        str(value) for value in removed.get("depends_on") or [] if str(value)
    }
    output_producer_ids = {
        node_id
        for node_id in replacement_ids
        if removed_outputs
        & {
            str((output or {}).get("artifact_type") or "")
            for output in repaired_nodes[node_id].get("produces") or []
            if isinstance(output, dict)
        }
    }
    if not output_producer_ids:
        return False
    for producer_id in output_producer_ids:
        if not removed_upstream.issubset(_ancestors(producer_id, repaired_nodes)):
            return False

    removed_requirements = {
        str(value) for value in removed.get("requirement_ids") or [] if str(value)
    }
    replacement_requirements = {
        str(value)
        for replacement in replacements
        for value in replacement.get("requirement_ids") or []
        if str(value)
    }
    if not removed_requirements.issubset(replacement_requirements):
        return False

    removed_trust = str(
        (removed.get("operator_requirements") or {}).get("execution_trust")
        or "any"
    )
    trust_rank = capsule_composition.PLANNER_EXECUTION_TRUST_RANK
    if removed_trust not in trust_rank:
        return False
    strongest_replacement_trust = max(
        (
            str(
                (repaired_nodes[node_id].get("operator_requirements") or {}).get(
                    "execution_trust"
                )
                or "any"
            )
            for node_id in output_producer_ids
        ),
        key=lambda value: trust_rank.get(value, -1),
    )
    if (
        strongest_replacement_trust not in trust_rank
        or trust_rank[strongest_replacement_trust] < trust_rank[removed_trust]
    ):
        return False
    return True


def _repair_preservation_errors(
    previous_plan: dict[str, Any] | None,
    repaired_plan: dict[str, Any],
    known_operators: set[str] | None = None,
    composition_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Reject repair-time semantic weakening used only to satisfy the registry."""
    if not previous_plan:
        return []
    previous_nodes = {
        str(row.get("node_id") or ""): row
        for row in previous_plan.get("nodes") or []
        if isinstance(row, dict) and str(row.get("node_id") or "")
    }
    repaired_nodes = {
        str(row.get("node_id") or ""): row
        for row in repaired_plan.get("nodes") or []
        if isinstance(row, dict) and str(row.get("node_id") or "")
    }
    repaired_requirement_owners: dict[str, set[str]] = {}
    for repaired_node_id, repaired_node in repaired_nodes.items():
        for requirement_id in repaired_node.get("requirement_ids") or []:
            repaired_requirement_owners.setdefault(str(requirement_id), set()).add(
                repaired_node_id
            )
    errors: list[dict[str, Any]] = []
    for node_id in sorted(set(previous_nodes) & set(repaired_nodes)):
        before = previous_nodes[node_id]
        after = repaired_nodes[node_id]
        removed_dependencies = sorted(
            set(str(value) for value in before.get("depends_on") or [])
            - set(str(value) for value in after.get("depends_on") or [])
        )
        unsafe_removed_dependencies = [
            dependency_id
            for dependency_id in removed_dependencies
            if not (
                _dependency_folded_into_admitted_composition(
                    removed_dependency_id=dependency_id,
                    repaired_node_id=node_id,
                    previous_nodes=previous_nodes,
                    repaired_nodes=repaired_nodes,
                    composition_catalog=composition_catalog,
                )
                or _dependency_expanded_into_repaired_subgraph(
                    removed_dependency_id=dependency_id,
                    repaired_node_id=node_id,
                    previous_nodes=previous_nodes,
                    repaired_nodes=repaired_nodes,
                )
            )
        ]
        if unsafe_removed_dependencies:
            errors.append(
                _error(
                    "REPAIR_DEPENDENCY_WEAKENED",
                    f"nodes.{node_id}.depends_on",
                    (
                        "Repair removed established dependencies "
                        f"{unsafe_removed_dependencies} from node {node_id!r} without "
                        "proving that every admitted capsule composition preserves their "
                        "typed outputs and upstream order. Registry fit may not weaken "
                        "semantic order."
                    ),
                    repairable=False,
                )
            )
        before_operator = str(before.get("logical_operator") or "")
        after_operator = str(after.get("logical_operator") or "")
        if (
            before_operator
            and after_operator != before_operator
            and before_operator in (known_operators or set())
        ):
            errors.append(
                _error(
                    "REPAIR_LOGICAL_OPERATOR_CHANGED",
                    f"nodes.{node_id}.logical_operator",
                    (
                        f"Repair changed node {node_id!r} from {before_operator!r} to "
                        f"{after_operator!r}. Capsule fit may not redefine the logical task."
                    ),
                    repairable=False,
                )
            )
        before_requirements = {
            str(value) for value in before.get("requirement_ids") or []
        }
        after_requirements = {
            str(value) for value in after.get("requirement_ids") or []
        }
        removed_requirements = before_requirements - after_requirements
        safely_reassigned = all(
            repaired_requirement_owners.get(requirement_id, set()) - {node_id}
            for requirement_id in removed_requirements
        )
        # A bounded repair may add requirement ownership when validation or the
        # independent fidelity reviewer identifies missing scope. Additions are
        # still governed by requirement-ownership, operator/capsule, artifact,
        # and fidelity checks. This preservation seam only blocks semantic loss.
        if removed_requirements and not safely_reassigned:
            errors.append(
                _error(
                    "REPAIR_REQUIREMENT_OWNERSHIP_CHANGED",
                    f"nodes.{node_id}.requirement_ids",
                    (
                        f"Repair removed requirement ownership from node {node_id!r} "
                        "without a safe reassignment: "
                        f"{sorted(before_requirements)} -> {sorted(after_requirements)}."
                    ),
                    repairable=False,
                )
            )
        before_trust = str(
            (before.get("operator_requirements") or {}).get("execution_trust")
            or "any"
        )
        after_trust = str(
            (after.get("operator_requirements") or {}).get("execution_trust")
            or "any"
        )
        if before_trust == "measured_execution" and after_trust != before_trust:
            errors.append(
                _error(
                    "REPAIR_EXECUTION_TRUST_WEAKENED",
                    f"nodes.{node_id}.operator_requirements.execution_trust",
                    (
                        f"Repair weakened node {node_id!r} execution trust from "
                        f"measured_execution to {after_trust!r}."
                    ),
                    repairable=False,
                )
            )
    return errors


def validate_plan_ir(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
    composition_catalog: dict[str, Any] | None = None,
    evaluation_registry: dict[str, Any] | None = None,
    previous_plan: dict[str, Any] | None = None,
    upstream_artifact_types: set[str] | None = None,
) -> dict[str, Any]:
    evaluation_registry = (
        evaluation_registry or evaluation_planning.load_evaluation_check_registry()
    )
    evaluation_checks = {
        str(row.get("check_id") or ""): row
        for row in evaluation_registry.get("checks") or []
        if isinstance(row, dict) and str(row.get("check_id") or "")
    }
    checks: dict[str, list[dict[str, Any]]] = {
        "schema": _schema_errors(plan_ir, PLAN_SCHEMA),
        "artifact_references": [],
        "node_identity": [],
        "logical_operator_registry": [],
        "capsule_contract_surface": [],
        "capsule_viability": [],
        "dependency_graph": [],
        "artifact_handoffs": [],
        "requirement_ownership": [],
        "verification_contract": [],
        "repair_preservation": [],
    }
    checks["repair_preservation"].extend(
        _repair_preservation_errors(
            previous_plan,
            plan_ir,
            _known_logical_operators(catalog),
            composition_catalog,
        )
    )
    if (plan_ir.get("requirement_ir_ref") or {}).get("sha256") != sha256_payload(requirement_ir):
        checks["artifact_references"].append(_error("REQUIREMENT_IR_REF_MISMATCH", "requirement_ir_ref", "PlanIR does not reference exact RequirementIR."))
    if (plan_ir.get("planning_decision_ref") or {}).get("sha256") != sha256_payload(decision):
        checks["artifact_references"].append(_error("PLANNING_DECISION_REF_MISMATCH", "planning_decision_ref", "PlanIR does not reference exact planning decision."))
    node_rows = [dict(row) for row in plan_ir.get("nodes") or [] if isinstance(row, dict)]
    semantic_contract = requirement_ir.get("semantic_contract") or {}
    discovery = semantic_contract.get("discovery")
    roles = semantic_contract.get("requirement_roles") or {}
    for row in node_rows:
        ref = row.get("retrieval_contract_ref")
        if ref and (not discovery or ref != discovery.get("contract_id")):
            checks["artifact_references"].append(_error("RETRIEVAL_CONTRACT_REF_MISMATCH", "nodes", "Use the exact accepted discovery contract_id."))
        if semantic_contract and _is_discovery_node(row):
            if not ref:
                checks["artifact_references"].append(_error("RETRIEVAL_CONTRACT_REF_REQUIRED", "nodes", "Discovery must bind the accepted structured retrieval contract."))
            if any(roles.get(rid) in {"process", "delivery", "outcome", "resolution"} for rid in row.get("requirement_ids", [])):
                checks["requirement_ownership"].append(_error("DISCOVERY_NON_SCOPE_OWNERSHIP", "nodes", "Assign workflow/delivery/resolution requirements to their actual artifact owner, not the shortlist."))
    node_ids = [str(row.get("node_id") or "") for row in node_rows]
    if len(node_ids) != len(set(node_ids)):
        checks["node_identity"].append(_error("DUPLICATE_NODE_ID", "nodes", "PlanIR node identifiers must be unique."))
    nodes = {str(row.get("node_id") or ""): row for row in node_rows}
    if decision.get("decision") == "generate":
        evaluator_nodes = [
            str(row.get("node_id") or "")
            for row in node_rows
            if any(
                marker in str(row.get("logical_operator") or "").strip().lower()
                for marker in ("critic", "verifier", "evaluator")
            )
        ]
        if len(evaluator_nodes) > 1:
            checks["dependency_graph"].append(
                _error(
                    "MULTIPLE_LLM_EVALUATOR_NODES",
                    "nodes",
                    (
                        "PlanIR may contain at most one Critic/Verifier/Evaluator "
                        f"node; found {evaluator_nodes}. Combine semantic review "
                        "and use deterministic acceptance aggregation."
                    ),
                )
            )
    known_ops = _known_logical_operators(catalog)
    requirement_rows = requirements(requirement_ir)
    known_requirements = {_requirement_id(row) for row in requirement_rows}
    verifier_by_requirement = {
        _requirement_id(row): _requirement_verifier(row) for row in requirement_rows
    }
    owned_requirements: set[str] = set()
    produced_by: dict[str, str] = {}
    canonical_capsule_outputs = {
        str(value)
        for capsule in catalog.get("capsules") or []
        if isinstance(capsule, dict)
        for value in capsule.get("produces") or []
        if str(value)
    }
    composition_by_node = {
        str(row.get("node_id") or ""): row
        for row in (composition_catalog or {}).get("nodes") or []
        if isinstance(row, dict)
    }
    capsule_by_id = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict) and str(row.get("capsule_id") or "")
    }
    materialized_by: dict[tuple[str, str], str] = {}
    admitted_upstream_types = _CONTROLLER_INPUT_TYPES | set(
        upstream_artifact_types or set()
    )
    for index, node in enumerate(node_rows):
        node_id = str(node.get("node_id") or "")
        logical = str(node.get("logical_operator") or "")
        if logical not in known_ops:
            checks["logical_operator_registry"].append(_error("LOGICAL_OPERATOR_UNKNOWN", f"nodes.{index}.logical_operator", f"Unknown logical operator: {logical!r}."))
        for dependency in node.get("depends_on") or []:
            if str(dependency) not in nodes:
                checks["dependency_graph"].append(_error("DEPENDENCY_UNKNOWN", f"nodes.{index}.depends_on", f"Unknown dependency: {dependency!r}."))
            if str(dependency) == node_id:
                checks["dependency_graph"].append(_error("SELF_DEPENDENCY", f"nodes.{index}.depends_on", "A node cannot depend on itself."))
        for req_id in node.get("requirement_ids") or []:
            req_id = str(req_id)
            if req_id not in known_requirements:
                checks["requirement_ownership"].append(_error("REQUIREMENT_UNKNOWN", f"nodes.{index}.requirement_ids", f"Unknown requirement: {req_id!r}."))
            else:
                owned_requirements.add(req_id)
        declared_node_verifiers: set[str] = set()
        compatible_auto_verifiers: set[str] = set()
        for output in node.get("produces") or []:
            artifact_type = str((output or {}).get("artifact_type") or "")
            if (
                decision.get("decision") == "generate"
                and artifact_type not in canonical_capsule_outputs
            ):
                checks["capsule_contract_surface"].append(
                    _error(
                        "ARTIFACT_TYPE_NOT_IN_CAPSULE_CATALOG",
                        f"nodes.{index}.produces",
                        f"Generated artifact {artifact_type!r} is not declared by any frozen capsule.",
                    )
                )
            verifier_ids = {
                str(value)
                for value in (output or {}).get("verifier_ids") or []
                if str(value)
            }
            declared_node_verifiers.update(verifier_ids)
            # Generated plans may use only the new frozen check registry.
            # Exact-reuse projections preserve legacy workflow-local verifier
            # labels, which remain governed by that workflow's frozen contract.
            for verifier_id in sorted(verifier_ids) if decision.get("decision") == "generate" else []:
                registered_check = evaluation_checks.get(verifier_id)
                if registered_check is None:
                    checks["verification_contract"].append(
                        _error(
                            "VERIFIER_UNREGISTERED",
                            f"nodes.{index}.produces",
                            f"Output {artifact_type!r} names unregistered verifier {verifier_id!r}.",
                        )
                    )
                    continue
                applies_to = registered_check.get("applies_to") or {}
                allowed_types = set(applies_to.get("artifact_types") or [])
                if (
                    applies_to.get("kind") == "artifact_type"
                    and applies_to.get("auto_apply") is True
                    and artifact_type in allowed_types
                ):
                    compatible_auto_verifiers.add(verifier_id)
                if (
                    applies_to.get("kind") == "artifact_type"
                    and artifact_type not in allowed_types
                ):
                    checks["verification_contract"].append(
                        _error(
                            "VERIFIER_ARTIFACT_TYPE_MISMATCH",
                            f"nodes.{index}.produces",
                            (
                                f"Verifier {verifier_id!r} cannot evaluate output "
                                f"{artifact_type!r}; allowed artifact types are "
                                f"{sorted(allowed_types)}."
                            ),
                        )
                    )
            if artifact_type in produced_by:
                checks["artifact_handoffs"].append(_error("ARTIFACT_PRODUCER_DUPLICATE", f"nodes.{index}.produces", f"Artifact {artifact_type!r} is produced by multiple nodes."))
            produced_by[artifact_type] = node_id
            if not verifier_ids:
                checks["verification_contract"].append(_error("VERIFIER_MISSING", f"nodes.{index}.produces", f"Artifact {artifact_type!r} has no verifier."))
            materialization = (output or {}).get("materialization") or {}
            kind = str(materialization.get("kind") or "")
            path_text = str(materialization.get("path") or "")
            defect = _materialization_error(path_text, kind)
            if defect:
                checks["artifact_handoffs"].append(
                    _error(
                        "ARTIFACT_MATERIALIZATION_INVALID",
                        f"nodes.{index}.produces",
                        f"Artifact {artifact_type!r}: {defect}.",
                    )
                )
            materialized_key = (node_id, path_text)
            if path_text and materialized_key in materialized_by:
                checks["artifact_handoffs"].append(
                    _error(
                        "ARTIFACT_MATERIALIZATION_DUPLICATE",
                        f"nodes.{index}.produces",
                        f"Node {node_id!r} materializes multiple artifacts at {path_text!r}.",
                    )
                )
            materialized_by[materialized_key] = artifact_type
            composition_row = composition_by_node.get(node_id) or {}
            admitted_candidate_ids = {
                str(value)
                for value in composition_row.get("admitted_candidate_ids") or []
                if str(value)
            }
            admitted_candidates = [
                candidate
                for candidate in (composition_row.get("search") or {}).get("candidates") or []
                if isinstance(candidate, dict)
                and str(candidate.get("candidate_id") or "") in admitted_candidate_ids
            ]
            collection_candidates: set[str] = set()
            for candidate in admitted_candidates:
                steps = [
                    step
                    for step in candidate.get("steps") or []
                    if isinstance(step, dict)
                ]
                terminal_capsule = capsule_by_id.get(
                    str((steps[-1] if steps else {}).get("capsule_id") or ""),
                    {},
                )
                terminal_outputs = (
                    (terminal_capsule.get("contract") or {}).get("required_outputs")
                    or []
                )
                if any(
                    (
                        f"schema:{str(shape.get('schema_ref') or '').strip()}"
                        if str(shape.get("schema_ref") or "").strip()
                        else str(shape.get("type") or "").strip()
                    )
                    == artifact_type
                    and str(shape.get("cardinality") or "one") == "many"
                    for shape in terminal_outputs
                    if isinstance(shape, dict)
                ):
                    collection_candidates.add(str(candidate.get("candidate_id") or ""))
            if (
                admitted_candidate_ids
                and collection_candidates == admitted_candidate_ids
                and kind != "directory"
            ):
                checks["artifact_handoffs"].append(
                    _error(
                        "COLLECTION_MATERIALIZATION_REQUIRES_DIRECTORY",
                        f"nodes.{index}.produces",
                        (
                            f"Artifact {artifact_type!r} is a collection in every admitted "
                            "capsule composition and must use directory materialization."
                        ),
                    )
                )
        owned_ids = {
            str(value)
            for value in node.get("requirement_ids") or []
            if str(value) in verifier_by_requirement
        }
        expected_node_verifiers = {
            verifier_by_requirement[requirement_id] for requirement_id in owned_ids
        }
        missing_verifiers = sorted(expected_node_verifiers - declared_node_verifiers)
        if missing_verifiers:
            checks["verification_contract"].append(
                _error(
                    "REQUIREMENT_VERIFIER_MISSING",
                    f"nodes.{index}.produces",
                    f"Node {node_id!r} does not expose required verifier IDs: {missing_verifiers}.",
                )
            )
        unrelated_verifiers = (
            sorted(
                declared_node_verifiers
                - expected_node_verifiers
                - compatible_auto_verifiers
            )
            if owned_ids
            else []
        )
        if unrelated_verifiers:
            checks["verification_contract"].append(
                _error(
                    "VERIFIER_NOT_OWNED",
                    f"nodes.{index}.produces",
                    f"Node {node_id!r} declares verifier IDs unrelated to its requirements: {unrelated_verifiers}.",
                )
            )
        if decision.get("decision") == "generate":
            candidate_row = _hard_capsule_candidate_row(node, catalog)
            composition_row = composition_by_node.get(node_id)
            if composition_row is None:
                composition_row = _node_composition_row(node, catalog)
            if not composition_row.get("admitted_candidate_ids"):
                ranked_exclusions = sorted(
                    candidate_row["exclusions"],
                    key=lambda row: (
                        len(row.get("reason_codes") or []),
                        len(row.get("missing_inputs") or [])
                        + len(row.get("unsupported_node_inputs") or [])
                        + len(row.get("missing_outputs") or []),
                        str(row.get("capsule_id") or ""),
                    ),
                )[:3]
                defect = _error(
                    "NO_FEASIBLE_CAPSULE_COMPOSITION",
                    f"nodes.{index}",
                    (
                        f"Generated node {node_id!r} has no admitted capsule composition "
                        "satisfying its exact input, terminal output, effect, network, "
                        "verification, implementation, and physical-selection contract."
                    ),
                )
                defect["node_id"] = node_id
                defect["closest_exclusions"] = ranked_exclusions
                defect["composition_status"] = composition_row.get("status")
                defect["unreachable_targets"] = list(
                    (composition_row.get("search") or {}).get("unreachable_targets") or []
                )
                defect["composition_errors"] = list(composition_row.get("errors") or [])
                defect["candidate_exclusions"] = list(
                    composition_row.get("candidate_exclusions") or []
                )
                checks["capsule_viability"].append(defect)
    if nodes and not checks["dependency_graph"] and _has_cycle(nodes):
        checks["dependency_graph"].append(_error("GRAPH_CYCLE", "nodes", "PlanIR dependency graph is cyclic."))
    for index, node in enumerate(node_rows):
        ancestors = _ancestors(str(node.get("node_id") or ""), nodes)
        for artifact_type in node.get("consumes") or []:
            artifact_type = str(artifact_type)
            if artifact_type in admitted_upstream_types:
                continue
            producer = produced_by.get(artifact_type)
            if not producer:
                available = sorted(
                    produced_type
                    for produced_type, producer_id in produced_by.items()
                    if producer_id in ancestors
                )
                checks["artifact_handoffs"].append(
                    _error(
                        "ARTIFACT_INPUT_UNRESOLVED",
                        f"nodes.{index}.consumes",
                        (
                            f"No node produces consumed artifact_type {artifact_type!r}. "
                            "consumes must copy an upstream produces.artifact_type exactly, "
                            "not a materialization path. "
                            f"Available upstream artifact_type values: "
                            f"{sorted(set(available) | admitted_upstream_types)}."
                        ),
                    )
                )
            elif producer not in ancestors:
                checks["artifact_handoffs"].append(_error("ARTIFACT_DEPENDENCY_MISSING", f"nodes.{index}.depends_on", f"Producer {producer!r} for {artifact_type!r} is not an ancestor."))
    missing = sorted(known_requirements - owned_requirements)
    if missing:
        checks["requirement_ownership"].append(_error("REQUIREMENTS_UNCOVERED", "nodes.requirement_ids", f"Uncovered requirements: {missing}."))
    errors = [error for rows in checks.values() for error in rows]
    artifact = {
        "schema_version": "solar.plan_validation.v2",
        "artifact_role": "runtime_artifact",
        "validation_id": f"plan-validation-{plan_ir.get('plan_ir_id')}",
        "plan_ir_ref": {
            "plan_ir_id": plan_ir.get("plan_ir_id"),
            "generation": plan_ir.get("generation"),
            "sha256": sha256_payload(plan_ir),
        },
        "status": "fail" if errors else "pass",
        "checks": [
            {
                "check_id": f"PV{index}",
                "kind": kind,
                "status": "fail" if rows else "pass",
            }
            for index, (kind, rows) in enumerate(checks.items(), start=1)
        ],
        "errors": errors,
        "warnings": [],
        "repair_count": int(plan_ir.get("generation") or 0),
    }
    _assert_schema(artifact, VALIDATION_SCHEMA, "plan_validation")
    return artifact


def build_binding_trace(requirement_ir: dict[str, Any], plan_ir: dict[str, Any]) -> dict[str, Any]:
    bindings: dict[str, dict[str, list[str]]] = {}
    for requirement in requirements(requirement_ir):
        req_id = _requirement_id(requirement)
        owners: list[str] = []
        artifacts: list[str] = []
        verifiers: list[str] = []
        expected_verifier = _requirement_verifier(requirement)
        for node in plan_ir.get("nodes") or []:
            if req_id not in (node.get("requirement_ids") or []):
                continue
            owners.append(str(node.get("node_id") or ""))
            for output in node.get("produces") or []:
                if expected_verifier not in ((output or {}).get("verifier_ids") or []):
                    continue
                artifacts.append(str((output or {}).get("artifact_type") or ""))
                verifiers.append(expected_verifier)
        if owners and artifacts and verifiers:
            bindings[req_id] = {
                "owners": sorted(set(owners)),
                "artifacts": sorted(set(value for value in artifacts if value)),
                "verifiers": sorted(set(value for value in verifiers if value)),
            }
    expected = {_requirement_id(row) for row in requirements(requirement_ir)}
    uncovered = sorted(expected - set(bindings))
    artifact = {
        "schema_version": "solar.binding_trace.v2",
        "artifact_role": "runtime_artifact",
        "binding_trace_id": f"binding-trace-{plan_ir.get('plan_ir_id')}",
        "requirement_ir_ref": {
            "requirement_ir_id": requirement_ir_id(requirement_ir),
            "sha256": sha256_payload(requirement_ir),
        },
        "plan_ir_ref": {
            "plan_ir_id": plan_ir.get("plan_ir_id"),
            "sha256": sha256_payload(plan_ir),
        },
        "bindings": bindings,
        "uncovered": uncovered,
        "verdict": "fail" if uncovered else "pass",
    }
    _assert_schema(artifact, BINDING_TRACE_SCHEMA, "binding_trace")
    return artifact


def _fidelity_prompt(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    plan_ir: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
) -> str:
    instruction = """
You are an independent PlanIR semantic reviewer. Judge but do not rewrite.
Treat identifiers, hashes, filenames, paths, and fixture labels as opaque references. Never infer user
meaning, audience, domain, or scope from them; use only admitted semantic content.
Check each required check kind exactly once. Fail material omission or weakening of RequirementIR,
unnecessary nodes or dependencies, dependency order that cannot produce the declared artifacts, and
unrequested effects. Do not judge registry identifiers, cycles, hashes, or schema shape; deterministic
validation owns those. An efficient plan may use one node for several requirements when the artifact
and verifier contract truthfully covers them. Fail execution-trust weakening: a request for experiments
on real datasets, reproduced measurements, or scientific effect validation requires measured_execution;
fixture, adapter, lineage-only, schema-only, and exit-code-only paths are not equivalent evidence.
When semantic_contract exists, use its requirement_roles and discovery contract as the semantic
authority. A node's retrieval_contract_ref binds that exact scope, search queries, inclusion/exclusion
criteria and time range. Never require process/delivery wording in retrieval scope or duplicate it in
the objective. Judge semantic coverage through the explicit contract reference, not objective wording.
For historical plans without semantic_contract, fail a genericized objective that drops named subjects, comparison
dimensions, constraints, or required coverage values from the RequirementIR. The discovery node must
retain the applicable scope/evidence-coverage requirement IDs and checks, but must not claim ownership
of a final-answer, publication, or delivery requirement merely because it supplies upstream evidence.
If a requirement is already owned
and verifiable on a downstream non-discovery artifact, do not fail discovery merely for omitting its ID.
Also fail a discovery node that owns a resolution requirement requiring a finding, supporting evidence,
and unresolved status when its declared output is only a source shortlist. The protocol question may
remain in the discovery objective as a constraint, but ownership must be assigned to a downstream
synthesis or report artifact that can truthfully emit the required resolution trace.
Judge unrequested effects by the semantic action added to the plan, such as a domain experiment,
deployment, external mutation, or publication. The generic `execute` effect means registered operator
code must run; it does not itself mean scientific experiment execution and is not an unrequested effect.
PlanIR is logical, not a listing of capsule internals. Do not call a support node unnecessary solely
because it has no direct RequirementIR owner or because capsule composition could internalize it.
A support node is semantically necessary when it produces a distinct artifact consumed downstream or
changes authorization, execution status, claim evaluation, or final synthesis. It is redundant only
when removing it leaves the artifact, effect, verification, and dependency contract unchanged and no
downstream node consumes a unique output from it. An implementation-only step may instead remain
inside one logical node's capsule composition; do not reject that internal step merely because it has
no direct RequirementIR owner.
Honor the declared artifact ABI. A downstream evidence-bearing artifact can carry the semantic content
needed by the next node. In particular, claim_verdict.v1 carries verified claim_text and evidence_ids;
do not demand a redundant raw-claims input when the report node consumes that verdict artifact.
""".strip()
    return json.dumps(
        {
            "instruction": instruction,
            "requirement_ir": requirement_ir,
            "upstream_artifacts": planning_inputs,
            "planning_decision": decision,
            "plan_ir": plan_ir,
        },
        ensure_ascii=False,
        indent=2,
    )


def _filter_redundant_discovery_ownership_errors(
    plan_ir: dict[str, Any],
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject reviewer requests for duplicate downstream-owned requirements."""

    downstream_owned = {
        str(requirement_id)
        for node in plan_ir.get("nodes") or []
        if isinstance(node, dict) and not _is_discovery_node(node)
        for requirement_id in node.get("requirement_ids") or []
        if str(requirement_id)
    }
    kept: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for error in errors:
        code_and_message = f"{error.get('code') or ''} {error.get('message') or ''}".lower()
        requirement_ids = {
            str(value) for value in error.get("requirement_ids") or [] if str(value)
        }
        requests_missing_discovery_ownership = (
            "discover" in code_and_message
            and "requirement" in code_and_message
            and any(token in code_and_message for token in ("missing", "omit", "retain", "bind"))
        )
        if (
            requests_missing_discovery_ownership
            and requirement_ids
            and requirement_ids <= downstream_owned
        ):
            ignored.append(error)
            continue
        kept.append(error)
    return kept, ignored


def review_plan_fidelity(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    plan_ir: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    reviewer: JsonModel,
    work_dir: Path,
) -> dict[str, Any]:
    body = reviewer.generate(
        _fidelity_prompt(requirement_ir, decision, plan_ir, planning_inputs),
        FIDELITY_REVIEW_SCHEMA,
        work_dir / "fidelity_call",
    )
    required_kinds = {
        "requirement_preservation",
        "smallest_sufficient_plan",
        "dependency_soundness",
        "no_unrequested_effects",
    }
    actual = [str(row.get("kind") or "") for row in body.get("checks") or []]
    if len(actual) != len(required_kinds) or set(actual) != required_kinds:
        raise ElasticPlannerError("plan reviewer did not return every required check exactly once")
    if requirement_ir.get("semantic_contract"):
        errors, ignored_ownership_errors = list(body.get("errors") or []), []
    else:
        errors, ignored_ownership_errors = _filter_redundant_discovery_ownership_errors(
            plan_ir, list(body.get("errors") or []),
        )
    warnings = list(body.get("warnings") or [])
    checks = copy.deepcopy(body.get("checks") or [])
    if ignored_ownership_errors:
        warnings.append(
            {
                "code": "REDUNDANT_DISCOVERY_OWNERSHIP_REQUEST_IGNORED",
                "path": "plan_ir.nodes[*].requirement_ids",
                "message": (
                    "The independent reviewer requested duplicate discovery ownership for "
                    "requirements already owned by downstream non-discovery artifacts."
                ),
            }
        )
        if not errors:
            for check in checks:
                if check.get("kind") == "requirement_preservation" and check.get("status") == "fail":
                    check["status"] = "warning"
                    check["reason"] = (
                        "Scope text is preserved, while requirement ownership remains on "
                        "the downstream artifact that can verify it."
                    )
    failed_checks = [
        row for row in checks if row.get("status") == "fail"
    ]
    if failed_checks and not errors:
        errors.extend(
            {
                "code": "PLAN_FIDELITY_CHECK_FAILED",
                "message": str(
                    row.get("reason")
                    or f"Plan fidelity check {row.get('kind')!r} failed."
                ),
                "repairable": True,
            }
            for row in failed_checks
        )
    artifact = {
        "schema_version": "solar.plan_fidelity.v1",
        "artifact_role": "runtime_artifact",
        "fidelity_id": f"plan-fidelity-{plan_ir.get('plan_ir_id')}",
        "requirement_ir_ref": {
            "requirement_ir_id": requirement_ir_id(requirement_ir),
            "sha256": sha256_payload(requirement_ir),
        },
        "plan_ir_ref": {
            "plan_ir_id": plan_ir.get("plan_ir_id"),
            "generation": plan_ir.get("generation"),
            "sha256": sha256_payload(plan_ir),
        },
        "status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
        "review_method": "independent_model_call",
        "reviewer": {
            "provider": reviewer.provider,
            "model": reviewer.model or "configured_default",
        },
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }
    _assert_schema(artifact, FIDELITY_SCHEMA, "plan_fidelity")
    return artifact


def _repairable_errors(*artifacts: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        error
        for artifact in artifacts
        if artifact
        for error in artifact.get("errors", [])
        if error.get("repairable") is True
    ]


def decide_plan_acceptance(
    requirement_ir: dict[str, Any],
    planning_context: dict[str, Any],
    decision: dict[str, Any] | None,
    plan_ir: dict[str, Any] | None,
    validation: dict[str, Any] | None,
    fidelity: dict[str, Any] | None,
    binding_trace: dict[str, Any] | None,
    direct_response: dict[str, Any] | None,
    direct_response_review: dict[str, Any] | None,
    *,
    repair_attempted: bool,
    failure: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    outcome = "failed"
    if failure:
        reasons.append(failure)
    elif not decision:
        reasons.append("Planning decision is missing.")
    elif decision.get("requirements_gap") is not None:
        outcome = "requirements_gap"
        reasons.append(str((decision.get("requirements_gap") or {}).get("description") or "RequirementIR is incomplete."))
    elif decision.get("decision") == "direct_response":
        if not direct_response or not direct_response_review:
            reasons.append("Direct response or its independent review is missing.")
        elif direct_response_review.get("status") == "fail":
            reasons.append("Independent direct-response review failed.")
        else:
            outcome = "direct_response"
            reasons.append("The independently accepted answer requires no workflow runtime.")
    elif not plan_ir or not validation:
        reasons.append("Required plan admission artifacts are missing.")
    elif validation.get("status") == "fail":
        codes = sorted(
            {
                str(error.get("code") or "PLAN_VALIDATION_FAILED")
                for error in validation.get("errors") or []
            }
        )
        detail = f" ({', '.join(codes)})" if codes else ""
        reasons.append(f"Deterministic plan validation failed{detail}.")
    elif not fidelity or not binding_trace:
        reasons.append("Required plan admission artifacts are missing.")
    elif fidelity.get("status") == "fail":
        reasons.append("Independent plan fidelity failed.")
    elif binding_trace.get("verdict") != "pass":
        reasons.append("One or more requirements lack a truthful owner/artifact/verifier binding.")
    else:
        outcome = "accepted"
        reasons.extend(
            [
                "Deterministic plan validation passed.",
                "Independent plan fidelity passed.",
                "Every requirement has a truthful owner, artifact, and verifier.",
            ]
        )
    refs = {
        "requirement_ir": {"requirement_ir_id": requirement_ir_id(requirement_ir), "sha256": sha256_payload(requirement_ir)},
        "planning_context": {
            "planning_context_id": planning_context.get("planning_context_id"),
            "sha256": sha256_payload(planning_context),
        },
        "planning_decision": ({"planning_decision_id": decision.get("planning_decision_id"), "sha256": sha256_payload(decision)} if decision else None),
        "plan_ir": ({"plan_ir_id": plan_ir.get("plan_ir_id"), "sha256": sha256_payload(plan_ir)} if plan_ir else None),
        "plan_validation": ({"validation_id": validation.get("validation_id"), "sha256": sha256_payload(validation)} if validation else None),
        "plan_fidelity": ({"fidelity_id": fidelity.get("fidelity_id"), "sha256": sha256_payload(fidelity)} if fidelity else None),
        "binding_trace": ({"binding_trace_id": binding_trace.get("binding_trace_id"), "sha256": sha256_payload(binding_trace)} if binding_trace else None),
        "direct_response": ({"response_id": direct_response.get("response_id"), "sha256": sha256_payload(direct_response)} if direct_response else None),
        "direct_response_review": ({"review_id": direct_response_review.get("review_id"), "sha256": sha256_payload(direct_response_review)} if direct_response_review else None),
    }
    artifact = {
        "schema_version": "solar.plan_acceptance.v1",
        "artifact_role": "runtime_artifact",
        "acceptance_id": f"plan-acceptance-{requirement_ir_id(requirement_ir)}",
        "decision": outcome,
        "final_generation": (
            plan_ir.get("generation")
            if plan_ir
            else direct_response.get("generation") if direct_response else None
        ),
        "repair": {"attempted": repair_attempted, "maximum_attempts": MAX_REPAIRS},
        "refs": refs,
        "reasons": reasons,
        # This is semantic admission only.  Runtime authority is granted later,
        # after capsule binding, whole-request physical feasibility, Solar plan
        # validation, and the content-hashed run-contract freeze all succeed.
        "runtime_handoff_allowed": False,
    }
    _assert_schema(artifact, ACCEPTANCE_SCHEMA, "plan_acceptance")
    return artifact


def run_semantic_planning_pipeline(
    requirement_ir: dict[str, Any],
    output_dir: Path,
    planner_model: JsonModel,
    reviewer_model: JsonModel,
    *,
    catalog: dict[str, Any] | None = None,
    upstream_artifacts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run planning decision and generated-PlanIR admission with one repair."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "plan_acceptance.json").exists():
        raise ElasticPlannerError(f"refusing to overwrite completed planning run: {output_dir}")
    catalog = catalog or build_planning_catalog_snapshot()
    planning_context, planning_inputs = materialize_planning_context(
        requirement_ir, upstream_artifacts, output_dir
    )
    write_json(output_dir / "planning_catalog_snapshot.json", catalog)
    decision: dict[str, Any] | None = None
    plan_ir: dict[str, Any] | None = None
    composition_catalog: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    fidelity: dict[str, Any] | None = None
    binding_trace: dict[str, Any] | None = None
    direct_response: dict[str, Any] | None = None
    direct_response_review: dict[str, Any] | None = None
    artifact_type_registry: dict[str, Any] | None = None
    conversion_registry: dict[str, Any] | None = None
    evaluation_check_registry: dict[str, Any] | None = None
    repair_attempted = False
    failure: str | None = None
    try:
        decision_errors: list[dict[str, Any]] = []
        previous_decision: dict[str, Any] | None = None
        for decision_generation in (0, 1):
            decision = compile_planning_decision(
                requirement_ir,
                catalog,
                planning_context,
                planning_inputs,
                planner_model,
                output_dir / f"strategy-generation-{decision_generation}",
                generation=decision_generation,
                previous=previous_decision,
                defects=decision_errors,
            )
            write_json(
                output_dir
                / f"strategy-generation-{decision_generation}"
                / "planning_decision.json",
                decision,
            )
            decision_errors = validate_planning_decision(
                requirement_ir, decision, catalog, planning_context
            )
            if not decision_errors or any(
                error.get("code") == "REQUIREMENTS_GAP"
                for error in decision_errors
            ):
                break
            if decision_generation == 0 and all(
                error.get("repairable") is True for error in decision_errors
            ):
                repair_attempted = True
                write_json(
                    output_dir / "strategy_repair_record.json",
                    {
                        "schema_version": "solar.repair_record.v1",
                        "repair_id": (
                            "strategy-repair-"
                            f"{requirement_ir_id(requirement_ir)}"
                        ),
                        "generation": 1,
                        "defects": decision_errors,
                        "maximum_repairs": MAX_REPAIRS,
                        "status": "requested",
                    },
                )
                previous_decision = decision
                continue
            break
        write_json(output_dir / "planning_decision.json", decision)
        if repair_attempted and (output_dir / "strategy_repair_record.json").exists():
            strategy_repair = _load_json(output_dir / "strategy_repair_record.json")
            strategy_repair["status"] = (
                "completed" if not decision_errors else "failed"
            )
            strategy_repair["result_planning_decision_id"] = decision.get(
                "planning_decision_id"
            )
            write_json(output_dir / "strategy_repair_record.json", strategy_repair)
        if any(error.get("code") == "REQUIREMENTS_GAP" for error in decision_errors):
            pass
        elif decision_errors:
            failure = "; ".join(str(error.get("message") or "") for error in decision_errors)
        elif decision.get("decision") == "direct_response":
            for generation in (0, 1):
                defects = _repairable_errors(direct_response_review)
                if generation == 1:
                    if not defects:
                        break
                    repair_attempted = True
                    write_json(
                        output_dir / "repair_record.json",
                        {
                            "schema_version": "solar.repair_record.v1",
                            "repair_id": f"direct-response-repair-{requirement_ir_id(requirement_ir)}",
                            "generation": 1,
                            "defects": defects,
                            "maximum_repairs": MAX_REPAIRS,
                            "status": "requested",
                        },
                    )
                previous = direct_response
                direct_response = compile_direct_response(
                    requirement_ir,
                    decision,
                    planning_inputs,
                    planner_model,
                    output_dir / f"generation-{generation}",
                    generation=generation,
                    previous=previous,
                    defects=defects,
                )
                write_json(
                    output_dir / f"generation-{generation}" / "direct_response.json",
                    direct_response,
                )
                direct_response_review = review_direct_response(
                    requirement_ir,
                    direct_response,
                    planning_inputs,
                    reviewer_model,
                    output_dir / f"generation-{generation}",
                )
                write_json(
                    output_dir / f"generation-{generation}" / "direct_response_review.json",
                    direct_response_review,
                )
                if not _repairable_errors(direct_response_review):
                    break
        elif decision.get("decision") == "exact_reuse":
            evaluation_check_registry = (
                evaluation_planning.load_evaluation_check_registry()
            )
            write_json(
                output_dir / "evaluation_check_registry.snapshot.json",
                evaluation_check_registry,
            )
            plan_ir = compile_exact_reuse_plan(requirement_ir, decision)
            validation = validate_plan_ir(
                requirement_ir,
                decision,
                plan_ir,
                catalog,
                evaluation_registry=evaluation_check_registry,
                upstream_artifact_types=_planning_context_artifact_types(
                    planning_context
                ),
            )
            if validation.get("status") == "pass":
                binding_trace = build_binding_trace(requirement_ir, plan_ir)
            fidelity = review_plan_fidelity(
                requirement_ir,
                decision,
                plan_ir,
                planning_inputs,
                reviewer_model,
                output_dir / "generation-0",
            )
        else:
            evaluation_check_registry = (
                evaluation_planning.load_evaluation_check_registry()
            )
            write_json(
                output_dir / "evaluation_check_registry.snapshot.json",
                evaluation_check_registry,
            )
            artifact_type_registry = capsule_composition.load_artifact_type_registry()
            conversion_registry = capsule_composition.load_conversion_registry()
            write_json(
                output_dir / "artifact_type_registry.snapshot.json",
                artifact_type_registry,
            )
            write_json(
                output_dir / "artifact_conversion_registry.snapshot.json",
                conversion_registry,
            )
            for generation in (0, 1):
                defects = _repairable_errors(validation, fidelity)
                if generation == 1:
                    if not defects:
                        break
                    repair_attempted = True
                    write_json(
                        output_dir / "repair_record.json",
                        {
                            "schema_version": "solar.repair_record.v1",
                            "repair_id": f"plan-repair-{requirement_ir_id(requirement_ir)}",
                            "generation": 1,
                            "defects": defects,
                            "maximum_repairs": MAX_REPAIRS,
                            "status": "requested",
                        },
                    )
                previous = plan_ir
                plan_ir = compile_plan_candidate(
                    requirement_ir,
                    decision,
                    catalog,
                    planning_inputs,
                    evaluation_check_registry,
                    planner_model,
                    output_dir / f"generation-{generation}",
                    generation=generation,
                    previous=previous,
                    defects=defects,
                )
                write_json(output_dir / f"generation-{generation}" / "plan_ir.json", plan_ir)
                composition_catalog = build_plan_composition_catalog(
                    requirement_ir,
                    planning_context,
                    plan_ir,
                    catalog,
                    artifact_registry=artifact_type_registry,
                    conversion_registry=conversion_registry,
                )
                write_json(
                    output_dir
                    / f"generation-{generation}"
                    / "plan_composition_catalog.json",
                    composition_catalog,
                )
                validation = validate_plan_ir(
                    requirement_ir,
                    decision,
                    plan_ir,
                    catalog,
                    composition_catalog,
                    evaluation_registry=evaluation_check_registry,
                    previous_plan=previous if generation == 1 else None,
                    upstream_artifact_types=_planning_context_artifact_types(
                        planning_context
                    ),
                )
                write_json(output_dir / f"generation-{generation}" / "plan_validation.json", validation)
                binding_trace = None
                if validation.get("status") == "pass":
                    binding_trace = build_binding_trace(requirement_ir, plan_ir)
                    write_json(output_dir / f"generation-{generation}" / "binding_trace.json", binding_trace)
                fidelity = review_plan_fidelity(
                    requirement_ir,
                    decision,
                    plan_ir,
                    planning_inputs,
                    reviewer_model,
                    output_dir / f"generation-{generation}",
                )
                write_json(output_dir / f"generation-{generation}" / "plan_fidelity.json", fidelity)
                if not _repairable_errors(validation, fidelity):
                    break
    except ElasticPlannerError as exc:
        failure = str(exc)
    acceptance = decide_plan_acceptance(
        requirement_ir,
        planning_context,
        decision,
        plan_ir,
        validation,
        fidelity,
        binding_trace,
        direct_response,
        direct_response_review,
        repair_attempted=repair_attempted,
        failure=failure,
    )
    for filename, payload in (
        ("plan_ir.json", plan_ir),
        ("plan_composition_catalog.json", composition_catalog),
        ("plan_validation.json", validation),
        ("plan_fidelity.json", fidelity),
        ("binding_trace.json", binding_trace),
        ("direct_response.json", direct_response),
        ("direct_response_review.json", direct_response_review),
    ):
        if payload:
            write_json(output_dir / filename, payload)
    if repair_attempted and (output_dir / "repair_record.json").exists():
        repair = _load_json(output_dir / "repair_record.json")
        repaired_artifact = plan_ir if plan_ir and plan_ir.get("generation") == 1 else direct_response
        repair["status"] = "completed" if repaired_artifact and repaired_artifact.get("generation") == 1 else "failed"
        repair["result_plan_ir_id"] = plan_ir.get("plan_ir_id") if plan_ir else None
        repair["result_response_id"] = direct_response.get("response_id") if direct_response else None
        write_json(output_dir / "repair_record.json", repair)
    write_json(output_dir / "plan_acceptance.json", acceptance)
    return {
        "planning_catalog_snapshot": catalog,
        "planning_context": planning_context,
        "planning_inputs": planning_inputs,
        "planning_decision": decision,
        "plan_ir": plan_ir,
        "plan_composition_catalog": composition_catalog,
        "artifact_type_registry": artifact_type_registry,
        "artifact_conversion_registry": conversion_registry,
        "evaluation_check_registry": evaluation_check_registry,
        "plan_validation": validation,
        "plan_fidelity": fidelity,
        "binding_trace": binding_trace,
        "direct_response": direct_response,
        "direct_response_review": direct_response_review,
        "plan_acceptance": acceptance,
    }


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-.")[:80] or "artifact"


_CONTROLLER_INPUT_TYPES = {
    "requirement_ir.v1",
    "artifact.requirement_ir",
    "artifact.task_graph_node",
    "artifact.request_context",
    "schema:request-envelope.schema.json",
}
_NO_EFFECT_TOKENS = {"", "none", "none by default", "no network", "disabled", "forbidden"}


def _effect_is_active(values: Any) -> bool:
    return any(str(value).strip().lower() not in _NO_EFFECT_TOKENS for value in values or [])


def _node_composition_row(
    node: dict[str, Any],
    catalog: dict[str, Any],
    *,
    artifact_registry: dict[str, Any] | None = None,
    conversion_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prove exact typed composition feasibility for one semantic PlanIR node."""
    artifact_registry = artifact_registry or capsule_composition.load_artifact_type_registry()
    conversion_registry = conversion_registry or capsule_composition.load_conversion_registry()
    node_id = str(node.get("node_id") or "")
    available_inputs = sorted(
        _CONTROLLER_INPUT_TYPES
        | {str(value) for value in node.get("consumes") or [] if str(value)}
    )
    required_capsule_inputs = {
        str(value)
        for value in node.get("consumes") or []
        if str(value) and str(value) not in _CONTROLLER_INPUT_TYPES
    }
    target_outputs = sorted(
        {
            str((value or {}).get("artifact_type") or "")
            for value in node.get("produces") or []
            if str((value or {}).get("artifact_type") or "")
        }
    )
    operator_requirements = (
        node.get("operator_requirements")
        if isinstance(node.get("operator_requirements"), dict)
        else {}
    )
    requested_effects = {
        str(value)
        for value in operator_requirements.get("effects") or []
        if str(value) in capsule_composition.COMPOSITION_EFFECTS
    }
    network_policy = str(operator_requirements.get("network") or "optional")
    declared_trust = str(operator_requirements.get("execution_trust") or "any")
    minimum_trust = capsule_composition.minimum_execution_trust_for_artifacts(
        target_outputs, artifact_registry
    )
    trust_rank = capsule_composition.PLANNER_EXECUTION_TRUST_RANK
    minimum_trust_by_output = {
        artifact_type: capsule_composition.minimum_execution_trust_for_artifacts(
            [artifact_type], artifact_registry
        )
        for artifact_type in target_outputs
    }
    required_trust_by_output = {
        artifact_type: sorted(
            trust_class
            for trust_class, rank in trust_rank.items()
            if trust_class != "any" and rank >= trust_rank[minimum]
        )
        for artifact_type, minimum in minimum_trust_by_output.items()
        if minimum != "any"
    }
    effective_trust = (
        minimum_trust
        if trust_rank[minimum_trust] > trust_rank[declared_trust]
        else declared_trust
    )
    required_effects = set(requested_effects)
    if network_policy == "required":
        required_effects.add("network")
    if network_policy == "forbidden":
        requested_effects.discard("network")
        required_effects.discard("network")
    allowed_effects = set(requested_effects)
    if network_policy in {"required", "optional"}:
        allowed_effects.add("network")
    errors: list[dict[str, str]] = []
    if trust_rank[declared_trust] < trust_rank[minimum_trust]:
        errors.append(
            {
                "code": "EXECUTION_TRUST_BELOW_OUTPUT_MINIMUM",
                "message": (
                    f"node {node_id} declares execution_trust={declared_trust}, "
                    f"but its output contract requires at least {minimum_trust}"
                ),
            }
        )
    search: dict[str, Any] | None = None
    admitted: list[str] = []
    exclusions: list[dict[str, Any]] = []
    status = "invalid_request"
    try:
        search = capsule_composition.search_composition_candidates(
            catalog,
            available_inputs=available_inputs,
            target_outputs=target_outputs,
            artifact_registry=artifact_registry,
            conversion_registry=conversion_registry,
            allowed_effects=sorted(allowed_effects),
            required_trust_by_output=required_trust_by_output or None,
        )
    except capsule_composition.CapsuleCompositionError as exc:
        errors.append({"code": "COMPOSITION_REQUEST_INVALID", "message": str(exc)})
    if search is not None:
        for candidate in search.get("candidates") or []:
            candidate_id = str(candidate.get("candidate_id") or "")
            reasons: list[str] = []
            aggregate = set(candidate.get("aggregate_effects") or [])
            if not required_effects.issubset(aggregate):
                reasons.append("REQUIRED_EFFECTS_MISSING")
            steps = list(candidate.get("steps") or [])
            consumed_by_steps = {
                str(value)
                for step in steps
                for value in (step or {}).get("consumes") or []
                if str(value)
            }
            if not required_capsule_inputs.issubset(consumed_by_steps):
                reasons.append("DECLARED_NODE_INPUTS_UNUSED")
            capsule_by_id = {
                str(row.get("capsule_id") or ""): row
                for row in catalog.get("capsules") or []
                if isinstance(row, dict)
            }
            candidate_trust = max(
                (
                    trust_rank.get(
                        str(
                            (
                                capsule_by_id.get(
                                    str((step or {}).get("capsule_id") or ""), {}
                                ).get("implementation")
                                or {}
                            ).get("trust_class")
                            or "unspecified"
                        ),
                        0,
                    )
                    for step in steps
                ),
                default=0,
            )
            if candidate_trust < trust_rank[declared_trust]:
                reasons.append("DECLARED_EXECUTION_TRUST_UNSATISFIED")
            # The composition search already proves that every target output is
            # produced by the ordered chain.  Earlier outputs remain part of the
            # logical node's result envelope, so requiring the final capsule to
            # reproduce all of them rejects valid execute-then-monitor and
            # plan-then-draft compositions.  Completion is the end of the whole
            # admitted chain; evaluation checks the collected output set.
            if reasons:
                exclusions.append(
                    {
                        "candidate_id": candidate_id,
                        "reason_codes": sorted(set(reasons)),
                    }
                )
            else:
                admitted.append(candidate_id)
        if errors:
            admitted = []
            status = "invalid_request"
        elif admitted:
            status = "candidates_available"
        elif search.get("verdict") == "search_bound_exhausted":
            status = "search_bound_exhausted"
        else:
            status = "unsatisfiable"
    return {
        "node_id": node_id,
        "requirement_ids": [str(value) for value in node.get("requirement_ids") or []],
        "available_inputs": available_inputs,
        "target_outputs": target_outputs,
        "required_effects": sorted(required_effects),
        "network_policy": network_policy,
        "execution_trust": effective_trust,
        "declared_execution_trust": declared_trust,
        "minimum_execution_trust": minimum_trust,
        "search": search,
        "admitted_candidate_ids": sorted(admitted),
        "candidate_exclusions": sorted(exclusions, key=lambda row: row["candidate_id"]),
        "status": status,
        "errors": errors,
    }


def build_plan_composition_catalog(
    requirement_ir: dict[str, Any],
    planning_context: dict[str, Any],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
    *,
    artifact_registry: dict[str, Any] | None = None,
    conversion_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze deterministic composition proofs for every generated PlanIR node."""
    artifact_registry = (
        artifact_registry or capsule_composition.load_artifact_type_registry()
    )
    conversion_registry = (
        conversion_registry or capsule_composition.load_conversion_registry()
    )
    rows = [
        _node_composition_row(
            node,
            catalog,
            artifact_registry=artifact_registry,
            conversion_registry=conversion_registry,
        )
        for node in plan_ir.get("nodes") or []
        if isinstance(node, dict)
    ]
    statuses = {str(row.get("status") or "") for row in rows}
    if "invalid_request" in statuses:
        verdict = "invalid_request"
    elif "search_bound_exhausted" in statuses:
        verdict = "search_bound_exhausted"
    elif "unsatisfiable" in statuses:
        verdict = "unsatisfiable"
    else:
        verdict = "candidates_available"
    artifact = {
        "schema_version": "solar.plan_composition_catalog.v1",
        "artifact_role": "planner_candidate_artifact",
        "catalog_id": f"plan-compositions-{plan_ir.get('plan_ir_id')}",
        "requirement_ir_ref": {"sha256": sha256_payload(requirement_ir)},
        "planning_context_ref": {"sha256": sha256_payload(planning_context)},
        "plan_ir_ref": {"sha256": sha256_payload(plan_ir)},
        "planning_catalog_ref": {"sha256": sha256_payload(catalog)},
        "artifact_type_registry_ref": {"sha256": sha256_payload(artifact_registry)},
        "conversion_registry_ref": {"sha256": sha256_payload(conversion_registry)},
        "nodes": rows,
        "verdict": verdict,
    }
    _assert_schema(
        artifact, PLAN_COMPOSITION_CATALOG_SCHEMA, "plan_composition_catalog"
    )
    return artifact


def _hard_capsule_candidate_row(
    node: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    """Compute exact capsule compatibility for one PlanIR node without I/O."""
    node_id = str(node.get("node_id") or "")
    declared_node_inputs = {
        str(value) for value in node.get("consumes") or [] if str(value)
    }
    available_inputs = _CONTROLLER_INPUT_TYPES | declared_node_inputs
    required_capsule_inputs = declared_node_inputs - _CONTROLLER_INPUT_TYPES
    requested_outputs = {
        str((value or {}).get("artifact_type") or "")
        for value in node.get("produces") or []
        if str((value or {}).get("artifact_type") or "")
    }
    operator_requirements = (
        node.get("operator_requirements")
        if isinstance(node.get("operator_requirements"), dict)
        else {}
    )
    requested_effects = {
        str(value) for value in operator_requirements.get("effects") or [] if str(value)
    }
    network_policy = str(operator_requirements.get("network") or "optional")
    required_trust = str(operator_requirements.get("execution_trust") or "any")
    eligible: list[str] = []
    exclusions: list[dict[str, Any]] = []
    for capsule in catalog.get("capsules") or []:
        if not isinstance(capsule, dict):
            continue
        capsule_id = str(capsule.get("capsule_id") or "")
        reasons: list[str] = []
        capsule_inputs = set(capsule.get("consumes") or [])
        missing_inputs = sorted(capsule_inputs - available_inputs)
        unsupported_node_inputs = sorted(required_capsule_inputs - capsule_inputs)
        missing_outputs = sorted(requested_outputs - set(capsule.get("produces") or []))
        if missing_inputs:
            reasons.append("REQUIRED_INPUT_UNAVAILABLE")
        if unsupported_node_inputs:
            reasons.append("DECLARED_NODE_INPUT_UNSUPPORTED")
        if missing_outputs:
            reasons.append("REQUIRED_OUTPUT_UNAVAILABLE")
        capsule_effects = (
            capsule.get("effects") if isinstance(capsule.get("effects"), dict) else {}
        )
        for effect in ("read", "write", "execute"):
            active = _effect_is_active(capsule_effects.get(effect))
            if effect in requested_effects and not active:
                reasons.append(f"REQUIRED_{effect.upper()}_EFFECT_MISSING")
            if active and effect not in requested_effects:
                reasons.append(f"UNREQUESTED_{effect.upper()}_EFFECT")
        network_active = _effect_is_active(capsule_effects.get("network"))
        if network_policy == "forbidden" and network_active:
            reasons.append("NETWORK_FORBIDDEN")
        if network_policy == "required" and not network_active:
            reasons.append("NETWORK_REQUIRED_BUT_UNDECLARED")
        verification = (
            capsule.get("verification")
            if isinstance(capsule.get("verification"), dict)
            else {}
        )
        if not (
            verification.get("self_checks")
            or verification.get("pass_conditions")
            or verification.get("external_required")
        ):
            reasons.append("VERIFICATION_CONTRACT_MISSING")
        if not bool((capsule.get("implementation") or {}).get("declared")):
            reasons.append("IMPLEMENTATION_UNDECLARED")
        capsule_trust = str((capsule.get("implementation") or {}).get("trust_class") or "unspecified")
        if required_trust != "any" and capsule_trust != required_trust:
            reasons.append("EXECUTION_TRUST_UNSATISFIED")
        if not (capsule.get("task_types") or []):
            reasons.append("TASK_TYPE_UNDECLARED")
        if reasons:
            exclusions.append(
                {
                    "capsule_id": capsule_id,
                    "reason_codes": sorted(set(reasons)),
                    "missing_inputs": missing_inputs,
                    "unsupported_node_inputs": unsupported_node_inputs,
                    "missing_outputs": missing_outputs,
                }
            )
        else:
            eligible.append(capsule_id)
    return {
        "node_id": node_id,
        "requirement_ids": [str(value) for value in node.get("requirement_ids") or []],
        "eligible_candidate_ids": sorted(eligible),
        "exclusions": sorted(exclusions, key=lambda row: row["capsule_id"]),
    }


def build_capsule_candidate_catalog(
    requirement_ir: dict[str, Any],
    planning_context: dict[str, Any],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Hard-filter the frozen registry without making a semantic choice."""
    rows = [
        _hard_capsule_candidate_row(node, catalog)
        for node in plan_ir.get("nodes") or []
        if isinstance(node, dict)
    ]
    artifact = {
        "schema_version": "solar.capsule_candidate_catalog.v1",
        "artifact_role": "runtime_artifact",
        "candidate_catalog_id": f"capsule-candidates-{plan_ir.get('plan_ir_id')}",
        "planning_context_ref": {"sha256": sha256_payload(planning_context)},
        "requirement_ir_ref": {"sha256": sha256_payload(requirement_ir)},
        "plan_ir_ref": {"sha256": sha256_payload(plan_ir)},
        "planning_catalog_ref": {"sha256": sha256_payload(catalog)},
        "nodes": rows,
        "verdict": "unsatisfiable" if any(not row["eligible_candidate_ids"] for row in rows) else "candidates_available",
    }
    _assert_schema(artifact, CAPSULE_CANDIDATE_CATALOG_SCHEMA, "capsule_candidate_catalog")
    return artifact


def _capsule_selection_prompt(
    requirement_ir: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
    candidate_catalog: dict[str, Any],
    *,
    generation: int,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> str:
    candidate_ids = {
        value
        for row in candidate_catalog.get("nodes") or []
        for value in row.get("eligible_candidate_ids") or []
    }
    capsule_by_id = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict) and str(row.get("capsule_id") or "") in candidate_ids
    }
    payload: dict[str, Any] = {
        "instruction": (
            "Semantically bind each PlanIR logical node to the best capsule among that node's "
            "eligible candidates. Return every node exactly once. The selected capsule must "
            "meaningfully perform the node objective; ordered fallbacks must preserve the same "
            "meaning and contract. Do not invent IDs, adapters, artifact equivalences, or physical "
            "operators. Do not return a dispatch task type; the compiler derives it from the "
            "selected registered capsule set. "
            "Mechanical compatibility has already been filtered, but it does not prove "
            "semantic fit."
        ),
        "requirement_ir": requirement_ir,
        "upstream_artifacts": planning_inputs,
        "plan_ir": plan_ir,
        "candidate_catalog": candidate_catalog,
        "candidate_capsules": capsule_by_id,
    }
    if generation:
        payload.update(
            {
                "repair_instruction": "Correct only the listed capsule-selection defects; keep unaffected node selections stable.",
                "previous": previous,
                "defects": defects or [],
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def compile_capsule_selection(
    requirement_ir: dict[str, Any],
    planning_context: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
    candidate_catalog: dict[str, Any],
    model: JsonModel,
    work_dir: Path,
    *,
    generation: int = 0,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body = model.generate(
        _capsule_selection_prompt(
            requirement_ir,
            planning_inputs,
            plan_ir,
            catalog,
            candidate_catalog,
            generation=generation,
            previous=previous,
            defects=defects,
        ),
        CAPSULE_SELECTION_BODY_SCHEMA,
        work_dir / "capsule_selection_call",
    )
    matrix = {
        str(row.get("node_id") or ""): row
        for row in candidate_catalog.get("nodes") or []
        if isinstance(row, dict)
    }
    capsule_by_id = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict)
    }
    selections = []
    for row in body.get("nodes") or []:
        node_id = str(row.get("node_id") or "")
        candidate_row = matrix.get(node_id) or {}
        selected_ids = [
            str(row.get("selected_capsule_id") or ""),
            *[str(value) for value in row.get("fallback_capsule_ids") or []],
        ]
        admitted_sets = [
            {
                str(value)
                for value in (capsule_by_id.get(capsule_id) or {}).get("task_types")
                or []
                if str(value)
            }
            for capsule_id in selected_ids
            if capsule_id
        ]
        common_task_types = (
            set.intersection(*admitted_sets) if admitted_sets else set()
        )
        selections.append(
            {
                **row,
                "dispatch_task_type": (
                    sorted(common_task_types)[0]
                    if common_task_types
                    else "__unresolved__"
                ),
                "requirement_ids": list(candidate_row.get("requirement_ids") or []),
                "eligible_candidate_ids": list(candidate_row.get("eligible_candidate_ids") or []),
                "candidate_exclusions": copy.deepcopy(candidate_row.get("exclusions") or []),
            }
        )
    artifact = {
        "schema_version": "solar.capsule_selection.v1",
        "artifact_role": "runtime_artifact",
        "selection_id": f"capsule-selection-{plan_ir.get('plan_ir_id')}-g{generation}",
        "generation": generation,
        "planning_context_ref": {"sha256": sha256_payload(planning_context)},
        "requirement_ir_ref": {"sha256": sha256_payload(requirement_ir)},
        "plan_ir_ref": {"sha256": sha256_payload(plan_ir)},
        "candidate_catalog_ref": {"sha256": sha256_payload(candidate_catalog)},
        "producer": {"method": "model", "provider": model.provider, "model": model.model or "configured_default"},
        "nodes": selections,
    }
    _assert_schema(artifact, CAPSULE_SELECTION_SCHEMA, "capsule_selection")
    return artifact


def validate_capsule_selection(
    requirement_ir: dict[str, Any],
    planning_context: dict[str, Any],
    plan_ir: dict[str, Any],
    candidate_catalog: dict[str, Any],
    catalog: dict[str, Any],
    selection: dict[str, Any] | None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if selection is None:
        zero_nodes = [
            str(row.get("node_id") or "")
            for row in candidate_catalog.get("nodes") or []
            if not (row.get("eligible_candidate_ids") or [])
        ]
        for node_id in zero_nodes:
            errors.append(
                _error(
                    "NO_COMPATIBLE_CAPSULE",
                    f"nodes.{node_id}",
                    "No registered capsule satisfies this PlanIR node's exact inputs, outputs, effects, verification, and implementation contract.",
                    repairable=False,
                )
            )
        if not zero_nodes:
            errors.append(_error("CAPSULE_SELECTION_MISSING", "selection", "No capsule selection was produced.", repairable=False))
    else:
        errors.extend(_schema_errors(selection, CAPSULE_SELECTION_SCHEMA))
        refs = {
            "planning_context_ref": sha256_payload(planning_context),
            "requirement_ir_ref": sha256_payload(requirement_ir),
            "plan_ir_ref": sha256_payload(plan_ir),
            "candidate_catalog_ref": sha256_payload(candidate_catalog),
        }
        for field, expected in refs.items():
            if (selection.get(field) or {}).get("sha256") != expected:
                errors.append(_error("CAPSULE_SELECTION_REF_MISMATCH", field, f"{field} does not bind the authoritative artifact.", repairable=False))
        expected_nodes = {
            str(row.get("node_id") or ""): row
            for row in candidate_catalog.get("nodes") or []
            if isinstance(row, dict)
        }
        capsule_by_id = {
            str(row.get("capsule_id") or ""): row
            for row in catalog.get("capsules") or []
            if isinstance(row, dict)
        }
        actual_rows = [row for row in selection.get("nodes") or [] if isinstance(row, dict)]
        actual_ids = [str(row.get("node_id") or "") for row in actual_rows]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_nodes):
            errors.append(_error("CAPSULE_SELECTION_NODE_SET_MISMATCH", "nodes", "Selection must contain every PlanIR node exactly once."))
        for row in actual_rows:
            node_id = str(row.get("node_id") or "")
            expected = expected_nodes.get(node_id) or {}
            eligible = list(expected.get("eligible_candidate_ids") or [])
            selected = str(row.get("selected_capsule_id") or "")
            fallbacks = [str(value) for value in row.get("fallback_capsule_ids") or []]
            if selected not in eligible:
                errors.append(_error("CAPSULE_SELECTION_NOT_ELIGIBLE", f"nodes.{node_id}.selected_capsule_id", f"Selected capsule {selected!r} is not an eligible candidate."))
            task_type = str(row.get("dispatch_task_type") or "")
            selected_capsules = [selected, *fallbacks]
            if any(
                task_type
                not in ((capsule_by_id.get(capsule_id) or {}).get("task_types") or [])
                for capsule_id in selected_capsules
            ):
                errors.append(_error("CAPSULE_TASK_TYPE_INVALID", f"nodes.{node_id}.dispatch_task_type", "Compiler-derived dispatch_task_type must be declared by the selected capsule and every fallback."))
            if selected in fallbacks or len(fallbacks) != len(set(fallbacks)) or any(value not in eligible for value in fallbacks):
                errors.append(_error("CAPSULE_FALLBACK_INVALID", f"nodes.{node_id}.fallback_capsule_ids", "Fallbacks must be unique eligible candidates and must exclude the primary selection."))
            if row.get("requirement_ids") != expected.get("requirement_ids"):
                errors.append(_error("CAPSULE_REQUIREMENT_LINK_MISMATCH", f"nodes.{node_id}.requirement_ids", "Capsule selection changed the PlanIR requirement linkage.", repairable=False))
            if row.get("eligible_candidate_ids") != eligible or row.get("candidate_exclusions") != expected.get("exclusions"):
                errors.append(_error("CAPSULE_CANDIDATE_TRACE_MISMATCH", f"nodes.{node_id}", "Selection does not retain the frozen candidates and exclusions.", repairable=False))
    artifact = {
        "schema_version": "solar.capsule_selection_validation.v1",
        "artifact_role": "runtime_artifact",
        "validation_id": f"capsule-selection-validation-{plan_ir.get('plan_ir_id')}",
        "selection_ref": {"sha256": sha256_payload(selection)} if selection else None,
        "status": "fail" if errors else "pass",
        "errors": errors,
    }
    _assert_schema(artifact, CAPSULE_SELECTION_VALIDATION_SCHEMA, "capsule_selection_validation")
    return artifact


def run_generated_capsule_binding(
    requirement_ir: dict[str, Any],
    semantic_result: dict[str, Any],
    output_dir: Path,
    planner_model: JsonModel,
    reviewer_model: JsonModel,
) -> dict[str, Any]:
    """Select and independently admit capsules with one repair at most."""
    planning_context = semantic_result.get("planning_context") or {}
    planning_inputs = semantic_result.get("planning_inputs") or {}
    plan_ir = semantic_result.get("plan_ir") or {}
    catalog = semantic_result.get("planning_catalog_snapshot") or {}
    candidate_catalog = build_capsule_candidate_catalog(
        requirement_ir, planning_context, plan_ir, catalog
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "capsule_candidate_catalog.json", candidate_catalog)
    selection: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    fit_review: dict[str, Any] | None = None
    repair_attempted = False
    if candidate_catalog.get("verdict") == "candidates_available":
        for generation in (0, 1):
            defects = _repairable_errors(validation, fit_review)
            if generation == 1:
                if not defects:
                    break
                repair_attempted = True
            selection = compile_capsule_selection(
                requirement_ir,
                planning_context,
                planning_inputs,
                plan_ir,
                catalog,
                candidate_catalog,
                planner_model,
                output_dir / f"capsule-generation-{generation}",
                generation=generation,
                previous=selection,
                defects=defects,
            )
            validation = validate_capsule_selection(
                requirement_ir,
                planning_context,
                plan_ir,
                candidate_catalog,
                catalog,
                selection,
            )
            fit_review = None
            write_json(output_dir / f"capsule-generation-{generation}" / "capsule_selection.json", selection)
            write_json(output_dir / f"capsule-generation-{generation}" / "capsule_selection_validation.json", validation)
            if validation.get("status") == "pass":
                fit_review = review_capsule_fit(
                    requirement_ir,
                    planning_inputs,
                    plan_ir,
                    candidate_catalog,
                    selection,
                    catalog,
                    reviewer_model,
                    output_dir / f"capsule-generation-{generation}",
                )
                write_json(output_dir / f"capsule-generation-{generation}" / "capsule_fit_review.json", fit_review)
            if validation.get("status") == "pass" and fit_review and fit_review.get("status") != "fail":
                break
    if validation is None:
        validation = validate_capsule_selection(
            requirement_ir, planning_context, plan_ir, candidate_catalog, catalog, None
        )
    for filename, payload in (
        ("capsule_selection.json", selection),
        ("capsule_selection_validation.json", validation),
        ("capsule_fit_review.json", fit_review),
    ):
        if payload is not None:
            write_json(output_dir / filename, payload)
    accepted = bool(
        selection
        and validation.get("status") == "pass"
        and fit_review
        and fit_review.get("status") != "fail"
    )
    return {
        "binding_kind": "direct_capsule",
        "accepted": accepted,
        "repair_attempted": repair_attempted,
        "candidate_catalog": candidate_catalog,
        "selection": selection,
        "selection_validation": validation,
        "fit_review": fit_review,
    }


def _composition_selection_prompt(
    requirement_ir: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
    composition_catalog: dict[str, Any],
    *,
    generation: int,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> str:
    capsule_ids = {
        str(step.get("capsule_id") or "")
        for row in composition_catalog.get("nodes") or []
        for candidate in (row.get("search") or {}).get("candidates") or []
        if str(candidate.get("candidate_id") or "")
        in set(row.get("admitted_candidate_ids") or [])
        for step in candidate.get("steps") or []
    }
    capsule_by_id = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict) and str(row.get("capsule_id") or "") in capsule_ids
    }
    payload: dict[str, Any] = {
        "instruction": (
            "For each logical PlanIR node, choose exactly one candidate from that node's "
            "admitted_candidate_ids. Candidates have already passed deterministic exact-type, "
            "effect, policy, implementation, and physical-selectability proof. Choose the "
            "smallest candidate that faithfully performs the node objective. Return only each "
            "node's selected candidate and rationale. The compiler copies the candidate's exact "
            "capsule steps, frozen order, and registered dispatch task types. Do not invent "
            "capsules, candidates, steps, task types, conversions, or topology fallbacks."
        ),
        "requirement_ir": requirement_ir,
        "upstream_artifacts": planning_inputs,
        "plan_ir": plan_ir,
        "composition_catalog": composition_catalog,
        "candidate_capsules": capsule_by_id,
    }
    if generation:
        payload.update(
            {
                "repair_instruction": (
                    "Correct only the listed composition-selection defects. Keep unaffected "
                    "node selections stable and remain inside admitted candidates."
                ),
                "previous": previous,
                "defects": defects or [],
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def compile_composition_selection(
    requirement_ir: dict[str, Any],
    planning_context: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
    composition_catalog: dict[str, Any],
    model: JsonModel,
    work_dir: Path,
    *,
    generation: int = 0,
    previous: dict[str, Any] | None = None,
    defects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body = model.generate(
        _composition_selection_prompt(
            requirement_ir,
            planning_inputs,
            plan_ir,
            catalog,
            composition_catalog,
            generation=generation,
            previous=previous,
            defects=defects,
        ),
        COMPOSITION_SELECTION_BODY_SCHEMA,
        work_dir / "composition_selection_call",
    )
    rows = {
        str(row.get("node_id") or ""): row
        for row in composition_catalog.get("nodes") or []
        if isinstance(row, dict)
    }
    capsule_by_id = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict)
    }
    selections = []
    for row in body.get("nodes") or []:
        node_id = str(row.get("node_id") or "")
        proof = rows.get(node_id) or {}
        selected_candidate_id = str(row.get("selected_candidate_id") or "")
        candidate = next(
            (
                value
                for value in (proof.get("search") or {}).get("candidates") or []
                if str(value.get("candidate_id") or "") == selected_candidate_id
            ),
            None,
        )
        step_bindings = []
        for step in (candidate or {}).get("steps") or []:
            capsule_id = str(step.get("capsule_id") or "")
            task_types = sorted(
                str(value)
                for value in (capsule_by_id.get(capsule_id) or {}).get("task_types")
                or []
                if str(value)
            )
            step_bindings.append(
                {
                    "edge_id": str(step.get("edge_id") or ""),
                    "capsule_id": capsule_id,
                    "dispatch_task_type": (
                        task_types[0] if task_types else "__unresolved__"
                    ),
                }
            )
        selections.append(
            {
                **row,
                "step_bindings": step_bindings,
                "requirement_ids": list(proof.get("requirement_ids") or []),
                "admitted_candidate_ids": list(
                    proof.get("admitted_candidate_ids") or []
                ),
            }
        )
    artifact = {
        "schema_version": "solar.composition_selection.v1",
        "artifact_role": "planner_selection_artifact",
        "selection_id": f"composition-selection-{plan_ir.get('plan_ir_id')}-g{generation}",
        "generation": generation,
        "requirement_ir_ref": {"sha256": sha256_payload(requirement_ir)},
        "planning_context_ref": {"sha256": sha256_payload(planning_context)},
        "plan_ir_ref": {"sha256": sha256_payload(plan_ir)},
        "composition_catalog_ref": {"sha256": sha256_payload(composition_catalog)},
        "producer": {
            "method": "model",
            "provider": model.provider,
            "model": model.model or "configured_default",
        },
        "nodes": selections,
    }
    _assert_schema(artifact, COMPOSITION_SELECTION_SCHEMA, "composition_selection")
    return artifact


def validate_composition_selection(
    requirement_ir: dict[str, Any],
    planning_context: dict[str, Any],
    plan_ir: dict[str, Any],
    catalog: dict[str, Any],
    composition_catalog: dict[str, Any],
    selection: dict[str, Any] | None,
    *,
    artifact_registry: dict[str, Any] | None = None,
    conversion_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    checks: list[dict[str, str]] = []
    artifact_registry = (
        artifact_registry or capsule_composition.load_artifact_type_registry()
    )
    conversion_registry = (
        conversion_registry or capsule_composition.load_conversion_registry()
    )

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append(
            {"check": name, "status": "pass" if ok else "fail", "detail": detail}
        )

    if selection is None:
        errors.append(
            _error(
                "COMPOSITION_SELECTION_MISSING",
                "selection",
                "No semantic selection was produced from the proven composition candidates.",
                repairable=False,
            )
        )
    else:
        errors.extend(_schema_errors(selection, COMPOSITION_SELECTION_SCHEMA))
        for field, payload in (
            ("artifact_type_registry_ref", artifact_registry),
            ("conversion_registry_ref", conversion_registry),
        ):
            ok = (composition_catalog.get(field) or {}).get(
                "sha256"
            ) == sha256_payload(payload)
            record(field, ok)
            if not ok:
                errors.append(
                    _error(
                        "COMPOSITION_REGISTRY_REF_MISMATCH",
                        field,
                        f"{field} does not bind the frozen registry snapshot.",
                        repairable=False,
                    )
                )
        refs = {
            "requirement_ir_ref": sha256_payload(requirement_ir),
            "planning_context_ref": sha256_payload(planning_context),
            "plan_ir_ref": sha256_payload(plan_ir),
            "composition_catalog_ref": sha256_payload(composition_catalog),
        }
        for field, expected in refs.items():
            ok = (selection.get(field) or {}).get("sha256") == expected
            record(field, ok)
            if not ok:
                errors.append(
                    _error(
                        "COMPOSITION_SELECTION_REF_MISMATCH",
                        field,
                        f"{field} does not bind the authoritative artifact.",
                        repairable=False,
                    )
                )
        expected_rows = {
            str(row.get("node_id") or ""): row
            for row in composition_catalog.get("nodes") or []
            if isinstance(row, dict)
        }
        actual_rows = [
            row for row in selection.get("nodes") or [] if isinstance(row, dict)
        ]
        actual_ids = [str(row.get("node_id") or "") for row in actual_rows]
        node_set_ok = len(actual_ids) == len(set(actual_ids)) and set(actual_ids) == set(
            expected_rows
        )
        record("node_set", node_set_ok, json.dumps(actual_ids))
        if not node_set_ok:
            errors.append(
                _error(
                    "COMPOSITION_SELECTION_NODE_SET_MISMATCH",
                    "nodes",
                    "Selection must contain every PlanIR node exactly once.",
                )
            )
        capsule_by_id = {
            str(row.get("capsule_id") or ""): row
            for row in catalog.get("capsules") or []
            if isinstance(row, dict)
        }
        recomputed_rows = {
            str(row.get("node_id") or ""): row
            for row in build_plan_composition_catalog(
                requirement_ir,
                planning_context,
                plan_ir,
                catalog,
                artifact_registry=artifact_registry,
                conversion_registry=conversion_registry,
            ).get("nodes")
            or []
            if isinstance(row, dict)
        }
        for node_id, expected in expected_rows.items():
            recomputed_ok = sha256_payload(expected) == sha256_payload(
                recomputed_rows.get(node_id)
            )
            record(f"{node_id}.composition_recomputed", recomputed_ok)
            if not recomputed_ok:
                errors.append(
                    _error(
                        "COMPOSITION_PROOF_RECOMPUTE_MISMATCH",
                        f"nodes.{node_id}",
                        "Frozen composition candidates do not match deterministic recomputation.",
                        repairable=False,
                    )
                )
        for row in actual_rows:
            node_id = str(row.get("node_id") or "")
            expected = expected_rows.get(node_id) or {}
            admitted = list(expected.get("admitted_candidate_ids") or [])
            candidate_id = str(row.get("selected_candidate_id") or "")
            candidate = next(
                (
                    candidate
                    for candidate in (expected.get("search") or {}).get("candidates")
                    or []
                    if str(candidate.get("candidate_id") or "") == candidate_id
                ),
                None,
            )
            candidate_ok = candidate_id in admitted and candidate is not None
            record(f"{node_id}.candidate", candidate_ok, candidate_id)
            if not candidate_ok:
                errors.append(
                    _error(
                        "COMPOSITION_SELECTION_NOT_ADMITTED",
                        f"nodes.{node_id}.selected_candidate_id",
                        f"Candidate {candidate_id!r} is not in the deterministic admitted set.",
                    )
                )
                continue
            expected_steps = [
                (str(step.get("edge_id") or ""), str(step.get("capsule_id") or ""))
                for step in candidate.get("steps") or []
            ]
            actual_steps = [
                (str(step.get("edge_id") or ""), str(step.get("capsule_id") or ""))
                for step in row.get("step_bindings") or []
            ]
            chain_ok = actual_steps == expected_steps
            record(f"{node_id}.step_chain", chain_ok)
            if not chain_ok:
                errors.append(
                    _error(
                        "COMPOSITION_STEP_CHAIN_MISMATCH",
                        f"nodes.{node_id}.step_bindings",
                        "Step bindings must reproduce the selected deterministic candidate exactly.",
                    )
                )
            for index, step in enumerate(row.get("step_bindings") or []):
                capsule_id = str(step.get("capsule_id") or "")
                task_type = str(step.get("dispatch_task_type") or "")
                if task_type not in (capsule_by_id.get(capsule_id) or {}).get(
                    "task_types", []
                ):
                    errors.append(
                        _error(
                            "COMPOSITION_TASK_TYPE_INVALID",
                            f"nodes.{node_id}.step_bindings.{index}.dispatch_task_type",
                            f"Task type {task_type!r} is not declared by capsule {capsule_id!r}.",
                        )
                    )
            if row.get("requirement_ids") != expected.get("requirement_ids"):
                errors.append(
                    _error(
                        "COMPOSITION_REQUIREMENT_LINK_MISMATCH",
                        f"nodes.{node_id}.requirement_ids",
                        "Composition selection changed the PlanIR requirement linkage.",
                        repairable=False,
                    )
                )
            if row.get("admitted_candidate_ids") != admitted:
                errors.append(
                    _error(
                        "COMPOSITION_CANDIDATE_TRACE_MISMATCH",
                        f"nodes.{node_id}.admitted_candidate_ids",
                        "Selection does not retain the frozen admitted candidate set.",
                        repairable=False,
                    )
                )
    artifact = {
        "schema_version": "solar.composition_selection_validation.v1",
        "artifact_role": "planner_validation_artifact",
        "validation_id": f"composition-selection-validation-{plan_ir.get('plan_ir_id')}",
        "selection_ref": {"sha256": sha256_payload(selection)} if selection else None,
        "status": "fail" if errors else "pass",
        "checks": checks,
        "errors": errors,
    }
    _assert_schema(
        artifact,
        COMPOSITION_SELECTION_VALIDATION_SCHEMA,
        "composition_selection_validation",
    )
    return artifact


def _complete_fit_review_errors(
    body: dict[str, Any],
    *,
    code: str,
) -> list[dict[str, Any]]:
    """Turn every semantic node failure into a typed, repairable defect.

    Structured-output validation guarantees the reviewer returned a reason for
    each failed node, but a model can still omit the parallel error row.  The
    Planner must preserve that semantic failure and enter its bounded repair
    path instead of crashing or silently passing it.
    """
    errors = list(body.get("errors") or [])
    error_node_ids = {
        str(row.get("node_id") or "")
        for row in errors
        if isinstance(row, dict)
    }
    for row in body.get("nodes") or []:
        node_id = str((row or {}).get("node_id") or "")
        if (row or {}).get("status") != "fail" or node_id in error_node_ids:
            continue
        errors.append(
            {
                "code": code,
                "node_id": node_id,
                "message": str((row or {}).get("reason") or "Semantic fit failed."),
                "repairable": True,
            }
        )
        error_node_ids.add(node_id)
    return errors


def review_composition_fit(
    requirement_ir: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    plan_ir: dict[str, Any],
    composition_catalog: dict[str, Any],
    selection: dict[str, Any],
    catalog: dict[str, Any],
    reviewer: JsonModel,
    work_dir: Path,
) -> dict[str, Any]:
    body = reviewer.generate(
        json.dumps(
            {
                "instruction": (
                    "Independently judge whether each selected proven-feasible capsule chain "
                    "faithfully performs its logical PlanIR objective. Deterministic composition "
                    "already proves types, effects, and executable registration; you judge meaning. "
                    "Fail chains that are too narrow, add material unrequested work, omit an "
                    "essential semantic operation, or use an inappropriate method. When a requirement "
                    "explicitly permits either resolving a question or reporting it as unresolved, a "
                    "chain may satisfy that requirement by preserving the missing evidence, limitation, "
                    "and unresolved status truthfully and traceably; do not require an unregistered "
                    "resolution operation merely because resolution is one allowed alternative. Still "
                    "fail a chain that claims resolution without the necessary operation, or when the "
                    "requirement mandates resolution rather than allowing unresolved reporting. Do not "
                    "rewrite."
                ),
                "requirement_ir": requirement_ir,
                "upstream_artifacts": planning_inputs,
                "plan_ir": plan_ir,
                "composition_catalog": composition_catalog,
                "composition_selection": selection,
                "capsules": catalog.get("capsules") or [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        CAPSULE_FIT_REVIEW_BODY_SCHEMA,
        work_dir / "composition_fit_review_call",
    )
    expected_ids = {
        str(row.get("node_id") or "") for row in plan_ir.get("nodes") or []
    }
    actual_ids = [str(row.get("node_id") or "") for row in body.get("nodes") or []]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise ElasticPlannerError(
            "composition fit reviewer must return every PlanIR node exactly once"
        )
    errors = _complete_fit_review_errors(
        body,
        code="COMPOSITION_FIT_FAILURE_UNTYPED",
    )
    artifact = {
        "schema_version": "solar.capsule_fit_review.v1",
        "artifact_role": "runtime_artifact",
        "review_id": f"composition-fit-{selection.get('selection_id')}",
        "selection_ref": {"sha256": sha256_payload(selection)},
        "review_method": "independent_model_call",
        "reviewer": {
            "provider": reviewer.provider,
            "model": reviewer.model or "configured_default",
        },
        "status": "fail"
        if errors
        else ("pass_with_warnings" if body.get("warnings") else "pass"),
        "nodes": body.get("nodes") or [],
        "errors": errors,
        "warnings": body.get("warnings") or [],
    }
    _assert_schema(artifact, CAPSULE_FIT_REVIEW_SCHEMA, "composition_fit_review")
    return artifact


def run_generated_composition_binding(
    requirement_ir: dict[str, Any],
    semantic_result: dict[str, Any],
    output_dir: Path,
    planner_model: JsonModel,
    reviewer_model: JsonModel,
) -> dict[str, Any]:
    planning_context = semantic_result.get("planning_context") or {}
    planning_inputs = semantic_result.get("planning_inputs") or {}
    plan_ir = semantic_result.get("plan_ir") or {}
    catalog = semantic_result.get("planning_catalog_snapshot") or {}
    composition_catalog = semantic_result.get("plan_composition_catalog") or (
        build_plan_composition_catalog(
            requirement_ir, planning_context, plan_ir, catalog
        )
    )
    artifact_registry = semantic_result.get("artifact_type_registry") or (
        capsule_composition.load_artifact_type_registry()
    )
    conversion_registry = semantic_result.get("artifact_conversion_registry") or (
        capsule_composition.load_conversion_registry()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "plan_composition_catalog.json", composition_catalog)
    write_json(
        output_dir / "artifact_type_registry.snapshot.json", artifact_registry
    )
    write_json(
        output_dir / "artifact_conversion_registry.snapshot.json", conversion_registry
    )
    selection: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    fit_review: dict[str, Any] | None = None
    repair_attempted = False
    if composition_catalog.get("verdict") == "candidates_available":
        for generation in (0, 1):
            defects = _repairable_errors(validation, fit_review)
            if generation == 1:
                if not defects:
                    break
                repair_attempted = True
            selection = compile_composition_selection(
                requirement_ir,
                planning_context,
                planning_inputs,
                plan_ir,
                catalog,
                composition_catalog,
                planner_model,
                output_dir / f"composition-generation-{generation}",
                generation=generation,
                previous=selection,
                defects=defects,
            )
            validation = validate_composition_selection(
                requirement_ir,
                planning_context,
                plan_ir,
                catalog,
                composition_catalog,
                selection,
                artifact_registry=artifact_registry,
                conversion_registry=conversion_registry,
            )
            fit_review = None
            write_json(
                output_dir
                / f"composition-generation-{generation}"
                / "composition_selection.json",
                selection,
            )
            write_json(
                output_dir
                / f"composition-generation-{generation}"
                / "composition_selection_validation.json",
                validation,
            )
            if validation.get("status") == "pass":
                fit_review = review_composition_fit(
                    requirement_ir,
                    planning_inputs,
                    plan_ir,
                    composition_catalog,
                    selection,
                    catalog,
                    reviewer_model,
                    output_dir / f"composition-generation-{generation}",
                )
                write_json(
                    output_dir
                    / f"composition-generation-{generation}"
                    / "composition_fit_review.json",
                    fit_review,
                )
            if (
                validation.get("status") == "pass"
                and fit_review
                and fit_review.get("status") != "fail"
            ):
                break
    if validation is None:
        validation = validate_composition_selection(
            requirement_ir,
            planning_context,
            plan_ir,
            catalog,
            composition_catalog,
            None,
            artifact_registry=artifact_registry,
            conversion_registry=conversion_registry,
        )
    for filename, payload in (
        ("composition_selection.json", selection),
        ("composition_selection_validation.json", validation),
        ("composition_fit_review.json", fit_review),
    ):
        if payload is not None:
            write_json(output_dir / filename, payload)
    accepted = bool(
        selection
        and validation.get("status") == "pass"
        and fit_review
        and fit_review.get("status") != "fail"
    )
    return {
        "binding_kind": "capsule_composition",
        "accepted": accepted,
        "repair_attempted": repair_attempted,
        "composition_catalog": composition_catalog,
        "artifact_type_registry": artifact_registry,
        "artifact_conversion_registry": conversion_registry,
        "selection": selection,
        "selection_validation": validation,
        "fit_review": fit_review,
    }


def review_capsule_fit(
    requirement_ir: dict[str, Any],
    planning_inputs: dict[str, dict[str, Any]],
    plan_ir: dict[str, Any],
    candidate_catalog: dict[str, Any],
    selection: dict[str, Any],
    catalog: dict[str, Any],
    reviewer: JsonModel,
    work_dir: Path,
) -> dict[str, Any]:
    chosen_ids = {
        str(value)
        for row in selection.get("nodes") or []
        for value in [row.get("selected_capsule_id"), *(row.get("fallback_capsule_ids") or [])]
        if str(value)
    }
    chosen = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict) and str(row.get("capsule_id") or "") in chosen_ids
    }
    body = reviewer.generate(
        json.dumps(
            {
                "instruction": (
                    "Independently judge semantic capsule fit; do not rewrite. Return every PlanIR "
                    "node exactly once. Fail a primary or fallback that is too narrow, performs a "
                    "different kind of work, adds material unrequested behavior, or cannot honestly "
                    "fulfil the node objective even though its types are mechanically compatible."
                ),
                "requirement_ir": requirement_ir,
                "upstream_artifacts": planning_inputs,
                "plan_ir": plan_ir,
                "candidate_catalog": candidate_catalog,
                "capsule_selection": selection,
                "selected_capsules": chosen,
            },
            ensure_ascii=False,
            indent=2,
        ),
        CAPSULE_FIT_REVIEW_BODY_SCHEMA,
        work_dir / "capsule_fit_review_call",
    )
    expected_ids = {str(row.get("node_id") or "") for row in plan_ir.get("nodes") or []}
    actual_ids = [str(row.get("node_id") or "") for row in body.get("nodes") or []]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise ElasticPlannerError("capsule fit reviewer must return every PlanIR node exactly once")
    errors = _complete_fit_review_errors(
        body,
        code="CAPSULE_FIT_FAILURE_UNTYPED",
    )
    artifact = {
        "schema_version": "solar.capsule_fit_review.v1",
        "artifact_role": "runtime_artifact",
        "review_id": f"capsule-fit-{selection.get('selection_id')}",
        "selection_ref": {"sha256": sha256_payload(selection)},
        "review_method": "independent_model_call",
        "reviewer": {"provider": reviewer.provider, "model": reviewer.model or "configured_default"},
        "status": "fail" if errors else ("pass_with_warnings" if body.get("warnings") else "pass"),
        "nodes": body.get("nodes") or [],
        "errors": errors,
        "warnings": body.get("warnings") or [],
    }
    _assert_schema(artifact, CAPSULE_FIT_REVIEW_SCHEMA, "capsule_fit_review")
    return artifact


def _generated_task_graph_proposal(
    requirement_ir: dict[str, Any],
    plan_ir: dict[str, Any],
    capsule_selection: dict[str, Any],
    *,
    sprint_id: str,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    output_paths: dict[str, str] = {}
    for plan_node in plan_ir.get("nodes") or []:
        node_id = str(plan_node.get("node_id") or "")
        for output in plan_node.get("produces") or []:
            artifact_type = str((output or {}).get("artifact_type") or "")
            materialization = (output or {}).get("materialization") or {}
            relative_path = str(materialization.get("path") or "")
            output_paths[artifact_type] = (
                f"workspace/planning/{_safe_name(node_id)}/{relative_path}"
            )
    logical_catalog = {
        row["logical_operator"]: row
        for row in _logical_operator_summaries()
    }
    selection_by_node = {
        str(row.get("node_id") or ""): row
        for row in capsule_selection.get("nodes") or []
        if isinstance(row, dict)
    }
    for plan_node in plan_ir.get("nodes") or []:
        node_id = str(plan_node.get("node_id") or "")
        logical_operator = str(plan_node.get("logical_operator") or "")
        outputs = [
            output_paths[str((output or {}).get("artifact_type") or "")]
            for output in plan_node.get("produces") or []
        ]
        read_scope = [
            output_paths[str(artifact_type)]
            for artifact_type in plan_node.get("consumes") or []
            if str(artifact_type) != "requirement_ir.v1" and str(artifact_type) in output_paths
        ]
        node = {
                "id": node_id,
                "title": str(plan_node.get("objective") or node_id)[:120],
                "goal": str(plan_node.get("objective") or ""),
                "logical_operator": logical_operator,
                "depends_on": [str(value) for value in plan_node.get("depends_on") or []],
                "inputs": [str(value) for value in plan_node.get("consumes") or []],
                "outputs": outputs,
                "read_scope": read_scope,
                "write_scope": outputs,
                "requirement_ids": [str(value) for value in plan_node.get("requirement_ids") or []],
                "required_capabilities": [],
                "evaluator_gate": {"kind": "llm_eval", "on_fail": "repair_once_then_fail"},
                "max_repair_attempts": 1,
                "semantic_artifact_contract": {
                    "consumes": [str(value) for value in plan_node.get("consumes") or []],
                    "produces": copy.deepcopy(plan_node.get("produces") or []),
                },
                "operator_requirements": copy.deepcopy(plan_node.get("operator_requirements") or {}),
                "gate_requirement": str(plan_node.get("gate_requirement") or ""),
            }
        admitted = selection_by_node.get(node_id) or {}
        node["capability_capsule_id"] = str(
            admitted.get("selected_capsule_id") or ""
        )
        node["dispatch_task_type"] = str(admitted.get("dispatch_task_type") or "")
        node["type"] = node["dispatch_task_type"]
        node["approved_fallback_capsule_ids"] = [
            str(value) for value in admitted.get("fallback_capsule_ids") or []
        ]
        node["capsule_selection_rationale"] = str(admitted.get("rationale") or "")
        # Canonical executable-node logic translates semantic roles such as
        # knowledge-extractor/auditor into the host role the runtime actually
        # leases. Do not duplicate the role table in the planner.
        node["allowed_operators"] = {"role": executable_dispatch_role(node)}
        nodes.append(node)
    return {
        "schema_version": "solar.task_graph.v1",
        "sprint_id": sprint_id,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "plan_compile_required": True,
        "dag_variant": "elastic_generated",
        "planning_authority": "elastic_planner_v1",
        "requirement_ir_ref": {
            "requirement_ir_id": requirement_ir_id(requirement_ir),
            "sha256": sha256_payload(requirement_ir),
        },
        "plan_ir_ref": {
            "plan_ir_id": plan_ir.get("plan_ir_id"),
            "sha256": sha256_payload(plan_ir),
        },
        "nodes": nodes,
    }


def _composition_support_node_id(parent_node_id: str, step_index: int) -> str:
    """Create a stable TaskGraph-safe id for a non-terminal composition step."""
    digest = sha256_payload(parent_node_id)[:8]
    prefix = _safe_name(parent_node_id)[:44]
    return f"{prefix}__{digest}_c{step_index:02d}"


def _generated_composition_task_graph_proposal(
    requirement_ir: dict[str, Any],
    plan_ir: dict[str, Any],
    composition_catalog: dict[str, Any],
    composition_selection: dict[str, Any],
    planning_catalog: dict[str, Any],
    *,
    sprint_id: str,
) -> dict[str, Any]:
    """Expand each selected capsule chain into a static executable TaskGraph.

    PlanIR remains the semantic plan.  Expansion is a Planner compile step, not
    runtime repair: support steps receive deterministic ids and the terminal
    step retains the PlanIR node id so requirement ownership stays stable.
    """
    proof_by_node = {
        str(row.get("node_id") or ""): row
        for row in composition_catalog.get("nodes") or []
        if isinstance(row, dict)
    }
    selection_by_node = {
        str(row.get("node_id") or ""): row
        for row in composition_selection.get("nodes") or []
        if isinstance(row, dict)
    }
    capsule_by_id = {
        str(row.get("capsule_id") or ""): row
        for row in planning_catalog.get("capsules") or []
        if isinstance(row, dict)
    }
    final_output_paths: dict[str, str] = {}
    final_output_contracts: dict[tuple[str, str], dict[str, Any]] = {}
    for plan_node in plan_ir.get("nodes") or []:
        node_id = str(plan_node.get("node_id") or "")
        for output in plan_node.get("produces") or []:
            artifact_type = str((output or {}).get("artifact_type") or "")
            relative_path = str(((output or {}).get("materialization") or {}).get("path") or "")
            final_output_paths[artifact_type] = (
                f"workspace/planning/{_safe_name(node_id)}/{relative_path}"
            )
            final_output_contracts[(node_id, artifact_type)] = copy.deepcopy(output)

    nodes: list[dict[str, Any]] = []
    expansion_trace: list[dict[str, Any]] = []
    for plan_node in plan_ir.get("nodes") or []:
        parent_id = str(plan_node.get("node_id") or "")
        proof = proof_by_node.get(parent_id) or {}
        selected = selection_by_node.get(parent_id) or {}
        candidate_id = str(selected.get("selected_candidate_id") or "")
        candidate = next(
            (
                row
                for row in (proof.get("search") or {}).get("candidates") or []
                if str(row.get("candidate_id") or "") == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise ElasticPlannerError(
                f"composition selection for {parent_id!r} has no admitted candidate"
            )
        selected_steps = list(selected.get("step_bindings") or [])
        proven_steps = list(candidate.get("steps") or [])
        if len(selected_steps) != len(proven_steps):
            raise ElasticPlannerError(
                f"composition selection for {parent_id!r} changed the proven step count"
            )
        step_ids = [
            (
                parent_id
                if index == len(proven_steps) - 1
                else _composition_support_node_id(parent_id, index + 1)
            )
            for index in range(len(proven_steps))
        ]
        local_paths = dict(final_output_paths)
        producer_by_type: dict[str, str] = {}
        expanded_ids: list[str] = []
        for index, (proven_step, selected_step) in enumerate(
            zip(proven_steps, selected_steps)
        ):
            step_id = step_ids[index]
            capsule_id = str(proven_step.get("capsule_id") or "")
            capsule = capsule_by_id.get(capsule_id) or {}
            consumes = [str(value) for value in proven_step.get("consumes") or []]
            produces = [str(value) for value in proven_step.get("produces") or []]
            is_terminal = index == len(proven_steps) - 1
            internal_dependencies = {
                producer_by_type[artifact_type]
                for artifact_type in consumes
                if artifact_type in producer_by_type
            }
            output_contracts: list[dict[str, Any]] = []
            output_paths: list[str] = []
            for artifact_type in produces:
                final_contract = final_output_contracts.get((parent_id, artifact_type))
                if final_contract is not None:
                    path = final_output_paths[artifact_type]
                    contract = final_contract
                else:
                    filename = f"{index + 1:02d}-{_safe_name(artifact_type)}.json"
                    path = (
                        f"workspace/planning/{_safe_name(parent_id)}/composition/{filename}"
                    )
                    contract = {
                        "artifact_type": artifact_type,
                        "verifier_ids": [],
                        "materialization": {"kind": "file", "path": filename},
                    }
                local_paths[artifact_type] = path
                producer_by_type[artifact_type] = step_id
                output_paths.append(path)
                output_contracts.append(contract)
            # The terminal node is the completion barrier for the full selected
            # composition, including independent branches in the candidate.
            if is_terminal:
                internal_dependencies.update(expanded_ids)
            dependencies = list(
                dict.fromkeys(
                    [
                        *[str(value) for value in plan_node.get("depends_on") or []],
                        *sorted(internal_dependencies),
                    ]
                )
            )
            read_scope = [
                local_paths[artifact_type]
                for artifact_type in consumes
                if artifact_type in local_paths
            ]
            task_type = str(selected_step.get("dispatch_task_type") or "")
            capsule_description = str(capsule.get("description") or "").strip()
            parent_objective = str(plan_node.get("objective") or "").strip()
            support_objective = (
                f"{capsule_description}\n\nComposition parent objective:\n{parent_objective}"
                if capsule_description and parent_objective
                else capsule_description
                or parent_objective
                or f"Run {capsule_id} as part of {parent_id}."
            )
            objective = (
                parent_objective
                if is_terminal
                else support_objective
            )
            node = {
                "id": step_id,
                "title": objective[:120],
                "goal": objective,
                "logical_operator": str(plan_node.get("logical_operator") or ""),
                "depends_on": dependencies,
                "inputs": consumes,
                "outputs": output_paths,
                "read_scope": list(dict.fromkeys(read_scope)),
                "write_scope": output_paths,
                "requirement_ids": (
                    [str(value) for value in plan_node.get("requirement_ids") or []]
                    if is_terminal
                    else []
                ),
                "required_capabilities": [],
                "evaluator_gate": {"kind": "llm_eval", "on_fail": "fail"},
                "max_repair_attempts": 0,
                "semantic_artifact_contract": {
                    "consumes": consumes,
                    "produces": output_contracts,
                },
                "operator_requirements": copy.deepcopy(
                    plan_node.get("operator_requirements") or {}
                ),
                "gate_requirement": str(plan_node.get("gate_requirement") or ""),
                "capability_capsule_id": capsule_id,
                "dispatch_task_type": task_type,
                "type": task_type,
                "approved_fallback_capsule_ids": [],
                "capsule_selection_rationale": str(selected.get("rationale") or ""),
                "composition_parent_node_id": parent_id,
                "composition_candidate_id": candidate_id,
                "composition_step_index": index + 1,
                "composition_step_count": len(proven_steps),
            }
            node["allowed_operators"] = {"role": executable_dispatch_role(node)}
            nodes.append(node)
            expanded_ids.append(step_id)
        expansion_trace.append(
            {
                "plan_ir_node_id": parent_id,
                "selected_candidate_id": candidate_id,
                "task_graph_node_ids": step_ids,
                "terminal_node_id": parent_id,
            }
        )
    return {
        "schema_version": "solar.task_graph.v1",
        "sprint_id": sprint_id,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "plan_compile_required": True,
        "dag_variant": "elastic_generated_composed",
        "planning_authority": "elastic_planner_v1",
        "requirement_ir_ref": {
            "requirement_ir_id": requirement_ir_id(requirement_ir),
            "sha256": sha256_payload(requirement_ir),
        },
        "plan_ir_ref": {
            "plan_ir_id": plan_ir.get("plan_ir_id"),
            "sha256": sha256_payload(plan_ir),
        },
        "composition_selection_ref": {
            "selection_id": composition_selection.get("selection_id"),
            "sha256": sha256_payload(composition_selection),
        },
        "composition_expansion_trace": expansion_trace,
        "nodes": nodes,
    }


def _exact_reuse_task_graph(
    requirement_ir: dict[str, Any],
    decision: dict[str, Any],
    plan_ir: dict[str, Any],
    *,
    sprint_id: str,
    workspace_root: str,
) -> dict[str, Any]:
    workflow_ref = decision.get("workflow_ref") or {}
    workflow_id = str(workflow_ref.get("workflow_id") or "")
    contract = workflow_contract.find_contract(workflow_id, WORKFLOWS_DIR)
    if contract is None:
        raise ElasticPlannerError(f"exact-reuse workflow disappeared from registry: {workflow_id}")
    substitutions = {
        "sprint_id": sprint_id,
        "sid": sprint_id,
        "workspace_root": workspace_root,
        **_workflow_input_map(decision),
    }
    graph = workflow_contract.instantiate(contract, substitutions)
    plan_nodes = {str(node.get("node_id") or ""): node for node in plan_ir.get("nodes") or []}
    for node in graph.get("nodes") or []:
        semantic = plan_nodes.get(str(node.get("id") or "")) or {}
        node["requirement_ids"] = [str(value) for value in semantic.get("requirement_ids") or []]
        node["semantic_artifact_contract"] = {
            "consumes": [str(value) for value in semantic.get("consumes") or []],
            "produces": copy.deepcopy(semantic.get("produces") or []),
        }
        node["operator_requirements"] = copy.deepcopy(semantic.get("operator_requirements") or {})
        # Older registered workflows express the same bounded repair contract
        # inside evaluator_gate.repair.max_attempts, while Plan Validator reads
        # the normalized node-level field.  Preserve that declared value during
        # exact-reuse compilation; do not invent a default when it is absent.
        if node.get("max_repair_attempts") is None:
            declared_budget = (
                ((node.get("evaluator_gate") or {}).get("repair") or {}).get(
                    "max_attempts"
                )
            )
            if (
                isinstance(declared_budget, int)
                and not isinstance(declared_budget, bool)
                and 0 <= declared_budget <= 2
            ):
                node["max_repair_attempts"] = declared_budget
    graph["planning_authority"] = "elastic_planner_v1"
    graph["requirement_ir_ref"] = {
        "requirement_ir_id": requirement_ir_id(requirement_ir),
        "sha256": sha256_payload(requirement_ir),
    }
    graph["plan_ir_ref"] = {"plan_ir_id": plan_ir.get("plan_ir_id"), "sha256": sha256_payload(plan_ir)}
    return graph


def _merge_execution_plans_into_graph(
    graph: dict[str, Any],
    capsule_plan: dict[str, Any],
    physical_plan: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(graph)
    capsule_nodes = {
        str(node.get("node_id") or ""): node
        for node in capsule_plan.get("nodes") or []
        if isinstance(node, dict)
    }
    physical_nodes = {
        str(node.get("node_id") or ""): node
        for node in physical_plan.get("nodes") or []
        if isinstance(node, dict)
    }
    for node in merged.get("nodes") or []:
        node_id = str(node.get("id") or "")
        capsule = capsule_nodes.get(node_id) or {}
        physical = physical_nodes.get(node_id) or {}
        capability_stage = next(
            (
                stage
                for stage in capsule.get("stages") or []
                if isinstance(stage, dict) and stage.get("stage_kind") == "capability"
            ),
            {},
        )
        capsule_id = str(capsule.get("capability_capsule_id") or "")
        if capsule_id:
            node["capability_capsule_id"] = capsule_id
        dispatch_type = str(capsule.get("dispatch_task_type") or capability_stage.get("task_type") or "")
        if dispatch_type:
            node["dispatch_task_type"] = dispatch_type
            node["task_type"] = dispatch_type
        node["proof_obligations"] = copy.deepcopy(capsule.get("proof_obligations") or [])
        node["artifact_types"] = copy.deepcopy(capsule.get("artifact_types") or {})
        node["effect_union"] = copy.deepcopy(capsule.get("effect_union") or {})
        candidates = list(physical.get("execution_candidates") or [])
        node["planning_authority"] = "frozen_execution_plan_v1"
        node["approved_physical_operator_ids"] = [
            str(candidate.get("operator_id") or "") for candidate in candidates
        ]
        node["capsule_plan_ir"] = copy.deepcopy(capsule)
        node["physical_plan_ir"] = copy.deepcopy(physical)
        if candidates:
            providers = sorted(
                {
                    str(candidate.get("provider") or "").strip().lower()
                    for candidate in candidates
                    if str(candidate.get("provider") or "").strip()
                }
            )
            role = str(candidates[0].get("role") or (node.get("allowed_operators") or {}).get("role") or "builder")
            node["allowed_operators"] = {"role": role}
            if providers:
                node["allowed_operators"]["providers"] = providers
    merged["capsule_plan_ref"] = {
        "schema_version": capsule_plan.get("schema_version"),
        "sha256": sha256_payload(capsule_plan),
    }
    merged["physical_plan_ref"] = {
        "schema_version": physical_plan.get("schema_version"),
        "sha256": sha256_payload(physical_plan),
    }
    merged["planning_authority"] = "frozen_execution_plan_v1"
    _normalize_task_graph_schema_fields(merged)
    return merged


def _normalize_task_graph_schema_fields(graph: dict[str, Any]) -> None:
    """Materialize the TaskGraph fields required at the dispatch boundary."""
    for index, node in enumerate(graph.get("nodes") or [], start=1):
        if not isinstance(node, dict):
            continue
        acceptance = node.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance:
            derived = [
                str(row.get("requirement") or "").strip()
                for row in node.get("proof_obligations") or []
                if isinstance(row, dict) and str(row.get("requirement") or "").strip()
            ]
            node["acceptance"] = list(dict.fromkeys(derived)) or [
                f"Complete {node.get('id') or 'node'} and produce its declared outputs."
            ]
        priority = node.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, (int, float)):
            node["priority"] = index
        node.setdefault("required_phase", None)
        node.setdefault("required_node_id", None)
        node.setdefault("required_node_status", None)


def validate_capsule_bindings(capsule_plan: dict[str, Any]) -> dict[str, Any]:
    """Reject adapter coercions that have no declared source-to-target mapping."""
    checks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for node in capsule_plan.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id") or "")
        for stage in node.get("stages") or []:
            if not isinstance(stage, dict) or stage.get("stage_kind") != "adapter":
                continue
            rule = stage.get("adapter_rule") if isinstance(stage.get("adapter_rule"), dict) else {}
            registry_match = (
                rule.get("registry_match")
                if isinstance(rule.get("registry_match"), dict)
                else {}
            )
            declared_targets = [
                str(value)
                for value in registry_match.get("target_artifacts") or []
                if str(value)
            ]
            requested_targets = [
                str(value)
                for value in rule.get("missing_required_inputs") or []
                if str(value)
            ]
            stage_id = str(stage.get("stage_id") or "")
            adapter_id = str(stage.get("capability_capsule_id") or "")
            accepted = bool(declared_targets) and set(requested_targets).issubset(
                set(declared_targets)
            )
            checks.append(
                {
                    "node_id": node_id,
                    "stage_id": stage_id,
                    "status": "pass" if accepted else "fail",
                    "adapter_capsule_id": adapter_id,
                    "target_artifacts": requested_targets,
                }
            )
            if not accepted:
                errors.append(
                    {
                        "code": "UNREGISTERED_ADAPTER_COERCION",
                        "node_id": node_id,
                        "stage_id": stage_id,
                        "message": (
                            "The adapter registry does not declare this source-to-target "
                            "conversion; a generic sidecar cannot grant a typed input contract."
                        ),
                        "target_artifacts": requested_targets,
                    }
                )
    artifact = {
        "schema_version": "solar.capsule_binding_validation.v1",
        "artifact_role": "runtime_artifact",
        "validation_id": f"capsule-binding-validation-{capsule_plan.get('sprint_id') or 'request'}",
        "capsule_plan_ref": {"sha256": sha256_payload(capsule_plan)},
        "status": "fail" if errors else "pass",
        "checks": checks,
        "errors": errors,
    }
    _assert_schema(
        artifact, CAPSULE_BINDING_VALIDATION_SCHEMA, "capsule_binding_validation"
    )
    return artifact


def _scheduler_network_requirement(node: dict[str, Any]) -> str:
    requirements = node.get("operator_requirements")
    if isinstance(requirements, dict):
        declared = str(requirements.get("network") or "").strip().lower()
        if declared in {"required", "optional", "forbidden"}:
            return declared
    effects = requirements.get("effects") if isinstance(requirements, dict) else []
    return "optional" if "network" in set(effects or []) else "forbidden"


def _scheduler_attempt_budget(node: dict[str, Any]) -> int:
    policy = node.get("timeout_retry_policy")
    if not isinstance(policy, dict):
        return 1
    raw_attempts = policy.get("max_attempts")
    if raw_attempts is None and policy.get("max_retries") is not None:
        raw_attempts = int(policy["max_retries"]) + 1
    try:
        return max(1, int(raw_attempts or 1))
    except (TypeError, ValueError):
        return 1


def compile_scheduler_input(
    task_graph: dict[str, Any],
    capsule_plan: dict[str, Any],
    physical_plan: dict[str, Any],
    evaluation_plan: dict[str, Any],
    *,
    sprint_id: str,
) -> dict[str, Any]:
    """Serialize admitted Planner output into the scheduler's immutable input.

    This compiler performs no scheduling and reads no mutable operator state. It
    carries forward only topology, bindings, candidates, artifact ports, checks,
    declared resource needs, effects, and the terminal attempt policy already
    admitted by the Planner boundary.
    """
    capsule_nodes = {
        str(row.get("node_id") or ""): row
        for row in capsule_plan.get("nodes") or []
        if isinstance(row, dict)
    }
    physical_nodes = {
        str(row.get("node_id") or ""): row
        for row in physical_plan.get("nodes") or []
        if isinstance(row, dict)
    }
    evaluation_nodes = {
        str(row.get("node_id") or ""): row
        for row in evaluation_plan.get("nodes") or []
        if isinstance(row, dict)
    }
    compiled_nodes: list[dict[str, Any]] = []
    for node in task_graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        capsule_node = capsule_nodes.get(node_id) or {}
        physical_node = physical_nodes.get(node_id) or {}
        evaluation_node = evaluation_nodes.get(node_id) or {}
        stages = capsule_node.get("stages") or []
        capsule_ids = list(
            dict.fromkeys(
                str(row.get("capability_capsule_id") or "")
                for row in stages
                if isinstance(row, dict)
                and str(row.get("capability_capsule_id") or "")
            )
        )
        if not capsule_ids:
            capsule_id = str(
                capsule_node.get("capability_capsule_id")
                or node.get("capability_capsule_id")
                or ""
            )
            if capsule_id:
                capsule_ids = [capsule_id]
        checks = [row for row in evaluation_node.get("checks") or [] if isinstance(row, dict)]
        deterministic_gate_ids = [
            str(row.get("check_id") or "")
            for row in checks
            if row.get("mode") in {"deterministic", "deterministic_plus_semantic"}
            and str(row.get("check_id") or "")
        ]
        semantic_review_required = bool(
            (evaluation_node.get("semantic_review") or {}).get("required")
        )
        semantic_evaluator_ids = [
            str(row.get("check_id") or "")
            for row in checks
            if semantic_review_required
            and row.get("mode") in {"semantic", "deterministic_plus_semantic"}
            and str(row.get("check_id") or "")
        ]
        node_policy = node.get("evaluation_policy") if isinstance(node.get("evaluation_policy"), dict) else {}
        if node_policy.get("semantic_review_required") is False and not deterministic_gate_ids:
            deterministic_gate_ids = [evaluation_budget.PROOF_GATE_ID]
        candidates = [
            {
                "operator_id": str(row.get("operator_id") or ""),
                "rank": int(row.get("rank") or index),
                "admission_state": "ELIGIBLE",
            }
            for index, row in enumerate(
                physical_node.get("execution_candidates") or [], start=1
            )
            if isinstance(row, dict)
            and str(row.get("operator_id") or "")
            and str(row.get("admission_state") or "READY") in {"READY", "ELIGIBLE"}
        ]
        artifacts = node.get("artifact_types") if isinstance(node.get("artifact_types"), dict) else {}
        requirements = node.get("operator_requirements")
        requirements = requirements if isinstance(requirements, dict) else {}
        declared_effects = [
            str(value)
            for value in requirements.get("effects") or []
            if str(value) in {"read", "write", "execute", "network", "irreversible"}
        ]
        compiled_nodes.append(
            {
                "id": node_id,
                "goal": str(node.get("goal") or capsule_node.get("goal") or ""),
                "logical_operator": str(
                    node.get("logical_operator")
                    or capsule_node.get("logical_operator")
                    or ""
                ),
                "dispatch_task_type": str(
                    node.get("dispatch_task_type")
                    or capsule_node.get("dispatch_task_type")
                    or ""
                ),
                "depends_on": [str(value) for value in node.get("depends_on") or []],
                "requirement_ids": [
                    str(value) for value in node.get("requirement_ids") or []
                ],
                "capsule_binding": {
                    "capsule_ids": capsule_ids,
                    "composition_id": node.get("composition_candidate_id"),
                    "contract_sha256": sha256_payload(capsule_node),
                },
                "physical_candidates": candidates,
                "artifact_contract": {
                    "consumes": [str(value) for value in artifacts.get("consumes") or []],
                    "produces": [str(value) for value in artifacts.get("produces") or []],
                },
                "evaluation_binding": {
                    "deterministic_gate_ids": deterministic_gate_ids,
                    "semantic_evaluator_ids": semantic_evaluator_ids,
                },
                "evaluator_gate": copy.deepcopy(node.get("evaluator_gate") or {}),
                **({"retrieval_contract": copy.deepcopy(node["retrieval_contract"])} if node.get("retrieval_contract") else {}),
                "evaluation_policy": copy.deepcopy(node_policy),
                "resource_requirements": {
                    "cpu_cores_min": float(requirements.get("cpu_cores_min") or 0),
                    "memory_mb_min": int(requirements.get("memory_mb_min") or 0),
                    "gpu_required": bool(requirements.get("gpu_required", False)),
                    "network": _scheduler_network_requirement(node),
                },
                "effects": declared_effects,
                "priority": int(node.get("priority") or 0),
                "failure_policy": {
                    "max_attempts": _scheduler_attempt_budget(node),
                    "on_exhausted": str(
                        (node.get("failure_policy") or {}).get("on_exhausted")
                        if isinstance(node.get("failure_policy"), dict)
                        else "fail_run"
                    )
                    or "fail_run",
                },
            }
        )
    scheduler_input = {
        "schema_version": "solar.scheduler_input.v1",
        "artifact_role": "runtime_execution_authority",
        "scheduler_input_id": f"scheduler-input-{sprint_id}",
        "sprint_id": sprint_id,
        "planning_authority": "frozen_execution_plan_v1",
        "test_policy": copy.deepcopy(task_graph.get("test_policy") or {}),
        "graph": {
            "graph_id": str(
                task_graph.get("workflow_contract_id")
                or task_graph.get("sprint_id")
                or sprint_id
            ),
            "nodes": compiled_nodes,
        },
    }
    _assert_schema(scheduler_input, SCHEDULER_INPUT_SCHEMA, "scheduler_input")
    return scheduler_input


def _bind_retrieval_contracts(graph: dict[str, Any], requirement_ir: dict[str, Any],
                             plan_ir: dict[str, Any]) -> None:
    """Copy accepted semantics by explicit PlanIR reference; never infer a topic."""
    semantic = requirement_ir.get("semantic_contract")
    if not semantic:
        return
    contract = semantic.get("discovery")
    parents = {row["node_id"]: row for row in plan_ir.get("nodes", [])}
    for node in graph.get("nodes", []):
        parent = parents.get(node.get("composition_parent_node_id") or node["id"], {})
        if not parent:
            parent = next((parents.get(trace.get("plan_ir_node_id"), {})
                           for trace in graph.get("composition_expansion_trace", [])
                           if node["id"] in trace.get("task_graph_node_ids", [])), {})
        produces = (node.get("semantic_artifact_contract") or {}).get("produces", [])
        is_discovery = any("literature_discovery" in str(row.get("artifact_type", "")) for row in produces)
        is_discovery = is_discovery or _is_discovery_node(node)
        if not is_discovery:
            continue
        if not contract or parent.get("retrieval_contract_ref") != contract["contract_id"]:
            raise ElasticPlannerError("Discovery execution lacks an accepted PlanIR retrieval_contract_ref")
        node["retrieval_contract"] = copy.deepcopy(contract)


def compile_and_freeze_execution_bundle(
    requirement_ir: dict[str, Any],
    semantic_result: dict[str, Any],
    output_dir: Path,
    *,
    sprint_id: str,
    workspace_root: str = "workspace",
    planner_model: JsonModel | None = None,
    reviewer_model: JsonModel | None = None,
    test_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn admitted semantic planning into a physically feasible frozen graph."""
    semantic_acceptance = semantic_result.get("plan_acceptance") or {}
    if semantic_acceptance.get("decision") != "accepted":
        raise ElasticPlannerError("only semantically accepted workflow plans may be bound")
    requirement_decision = semantic_result.get("planning_decision") or {}
    plan_ir = semantic_result.get("plan_ir") or {}
    capsule_binding: dict[str, Any] | None = None
    direct_binding_attempt: dict[str, Any] | None = None
    composition_binding_attempt: dict[str, Any] | None = None
    if requirement_decision.get("decision") == "exact_reuse":
        graph = _exact_reuse_task_graph(
            requirement_ir,
            requirement_decision,
            plan_ir,
            sprint_id=sprint_id,
            workspace_root=workspace_root,
        )
        if str((test_policy or {}).get("mode") or "") == evaluation_budget.RAPID_SMOKE_MODE:
            graph = evaluation_budget.apply_evaluation_budget(
                graph,
                requirement_ir,
                test_policy=test_policy,
            )
    else:
        if planner_model is None or reviewer_model is None:
            raise ElasticPlannerError(
                "generated planning requires planner and independent capsule-fit reviewer models"
            )
        direct_binding_attempt = run_generated_capsule_binding(
            requirement_ir,
            semantic_result,
            output_dir,
            planner_model,
            reviewer_model,
        )
        if direct_binding_attempt.get("accepted"):
            capsule_binding = direct_binding_attempt
            graph = _generated_task_graph_proposal(
                requirement_ir,
                plan_ir,
                capsule_binding["selection"],
                sprint_id=sprint_id,
            )
        else:
            composition_binding_attempt = run_generated_composition_binding(
                requirement_ir,
                semantic_result,
                output_dir,
                planner_model,
                reviewer_model,
            )
            capsule_binding = composition_binding_attempt
        if not capsule_binding.get("accepted"):
            selection_validation = capsule_binding.get("selection_validation") or {}
            fit_review = capsule_binding.get("fit_review") or {}
            reasons = [
                str(row.get("code") or row.get("message") or "capsule selection failed")
                for row in [
                    *(selection_validation.get("errors") or []),
                    *(fit_review.get("errors") or []),
                ]
            ] or ["Capsule selection was not independently admitted."]
            acceptance = _capsule_selection_failure_acceptance(
                requirement_ir,
                semantic_result,
                capsule_binding,
                reasons,
            )
            write_json(output_dir / "plan_acceptance.json", acceptance)
            return {
                "binding_kind": capsule_binding.get("binding_kind"),
                "direct_binding_attempt": direct_binding_attempt,
                "composition_binding_attempt": composition_binding_attempt,
                "capsule_candidate_catalog": (
                    capsule_binding.get("candidate_catalog")
                    if capsule_binding.get("binding_kind") == "direct_capsule"
                    else None
                ),
                "capsule_selection": (
                    capsule_binding.get("selection")
                    if capsule_binding.get("binding_kind") == "direct_capsule"
                    else None
                ),
                "capsule_selection_validation": (
                    selection_validation
                    if capsule_binding.get("binding_kind") == "direct_capsule"
                    else None
                ),
                "capsule_fit_review": (
                    fit_review or None
                    if capsule_binding.get("binding_kind") == "direct_capsule"
                    else None
                ),
                "plan_composition_catalog": capsule_binding.get("composition_catalog"),
                "composition_selection": (
                    capsule_binding.get("selection")
                    if capsule_binding.get("binding_kind") == "capsule_composition"
                    else None
                ),
                "composition_selection_validation": (
                    selection_validation
                    if capsule_binding.get("binding_kind") == "capsule_composition"
                    else None
                ),
                "composition_fit_review": (
                    fit_review or None
                    if capsule_binding.get("binding_kind") == "capsule_composition"
                    else None
                ),
                "capsule_plan": None,
                "capsule_binding_validation": None,
                "physical_plan": None,
                "task_graph_contract": None,
                "run_contract_frozen": None,
                "plan_acceptance": acceptance,
            }
        if capsule_binding.get("binding_kind") == "capsule_composition":
            graph = _generated_composition_task_graph_proposal(
                requirement_ir,
                plan_ir,
                capsule_binding["composition_catalog"],
                capsule_binding["selection"],
                semantic_result.get("planning_catalog_snapshot") or {},
                sprint_id=sprint_id,
            )
        graph = evaluation_budget.apply_evaluation_budget(
            graph,
            requirement_ir,
            test_policy=test_policy,
        )
    execution = apo_plan_compiler.compile_whole_request_execution_plan(
        graph,
        request_type=str(requirement_ir.get("request_type") or ""),
        lane_hint=str(requirement_ir.get("lane_hint") or ""),
        registry_path=CAPSULE_REGISTRY_PATH,
        operators_path=PHYSICAL_OPERATORS_PATH,
    )
    capsule_plan = execution["capsule_plan"]
    physical_plan = execution["physical_plan"]
    binding_validation = validate_capsule_bindings(capsule_plan)
    _assert_schema(capsule_plan, CAPSULE_PLAN_SCHEMA, "capsule_plan")
    _assert_schema(physical_plan, PHYSICAL_PLAN_SCHEMA, "physical_plan")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "capsule_plan.json", capsule_plan)
    write_json(output_dir / "capsule_binding_validation.json", binding_validation)
    write_json(output_dir / "physical_plan.json", physical_plan)
    if execution.get("verdict") != "pass" or binding_validation.get("status") != "pass":
        reasons = [
            f"{row.get('node_id')}: {row.get('code')}"
            for row in physical_plan.get("unsatisfiable_nodes") or []
        ]
        reasons.extend(
            f"{row.get('node_id')}: {row.get('code')} ({', '.join(row.get('target_artifacts') or [])})"
            for row in binding_validation.get("errors") or []
        )
        reasons = reasons or ["Physical binding is unsatisfiable."]
        acceptance = _final_execution_acceptance(
            requirement_ir,
            semantic_result,
            capsule_plan,
            physical_plan,
            binding_validation=binding_validation,
            capsule_binding=capsule_binding,
            frozen_contract=None,
            decision="failed",
            reasons=reasons,
        )
        write_json(output_dir / "plan_acceptance.json", acceptance)
        return {
            "capsule_plan": capsule_plan,
            "capsule_binding_validation": binding_validation,
            "physical_plan": physical_plan,
            "task_graph_contract": None,
            "run_contract_frozen": None,
            "plan_acceptance": acceptance,
        }
    merged = _merge_execution_plans_into_graph(graph, capsule_plan, physical_plan)
    _bind_retrieval_contracts(merged, requirement_ir, plan_ir)
    capsule_registry = workflow_contract.load_capsule_registry(CONFIG_DIR)
    operator_registry = workflow_contract.load_operator_registry(PHYSICAL_OPERATORS_PATH)
    contract_id = str(merged.get("workflow_contract_id") or "pm.generic.v1")
    contract = workflow_contract.find_contract(contract_id, WORKFLOWS_DIR)
    validator_errors = plan_validator.validate_plan(
        merged,
        capsule_registry,
        operator_registry,
        contract=contract,
        expected_sprint_id=sprint_id,
    )
    if validator_errors:
        write_json(
            output_dir / "task_graph_validation.json",
            {"status": "fail", "errors": validator_errors},
        )
        acceptance = _final_execution_acceptance(
            requirement_ir,
            semantic_result,
            capsule_plan,
            physical_plan,
            binding_validation=binding_validation,
            capsule_binding=capsule_binding,
            frozen_contract=None,
            decision="failed",
            reasons=[f"{row.get('code')}: {row.get('message')}" for row in validator_errors],
        )
        write_json(output_dir / "plan_acceptance.json", acceptance)
        return {
            "capsule_plan": capsule_plan,
            "capsule_binding_validation": binding_validation,
            "physical_plan": physical_plan,
            "task_graph_contract": merged,
            "run_contract_frozen": None,
            "plan_acceptance": acceptance,
        }
    plan_validator.stamp_plan_certificate(
        merged,
        capsule_registry,
        operator_registry,
        contract=contract,
    )
    try:
        evaluation_registry = copy.deepcopy(
            semantic_result.get("evaluation_check_registry")
            or evaluation_planning.load_evaluation_check_registry()
        )
        evaluation_contract = evaluation_planning.compile_evaluation_plan(
            requirement_ir,
            plan_ir,
            capsule_plan,
            merged,
            registry=evaluation_registry,
        )
        evaluation_validation = evaluation_planning.validate_evaluation_plan(
            evaluation_contract,
            requirement_ir,
            plan_ir,
            capsule_plan,
            merged,
            registry=evaluation_registry,
        )
    except evaluation_planning.EvaluationPlanError as exc:
        acceptance = _final_execution_acceptance(
            requirement_ir,
            semantic_result,
            capsule_plan,
            physical_plan,
            binding_validation=binding_validation,
            capsule_binding=capsule_binding,
            frozen_contract=None,
            decision="failed",
            reasons=[f"Evaluation contract could not be compiled: {exc}"],
        )
        write_json(output_dir / "plan_acceptance.json", acceptance)
        return {
            "capsule_plan": capsule_plan,
            "capsule_binding_validation": binding_validation,
            "physical_plan": physical_plan,
            "evaluation_check_registry": None,
            "evaluation_plan": None,
            "evaluation_plan_validation": None,
            "task_graph_contract": merged,
            "run_contract_frozen": None,
            "plan_acceptance": acceptance,
        }
    write_json(
        output_dir / "evaluation_check_registry.snapshot.json",
        evaluation_registry,
    )
    write_json(output_dir / "evaluation_plan.json", evaluation_contract)
    write_json(
        output_dir / "evaluation_plan_validation.json", evaluation_validation
    )
    if (
        evaluation_contract.get("verdict") != "pass"
        or evaluation_validation.get("status") != "pass"
    ):
        reasons = [
            f"{row.get('node_id')}: {row.get('code')} ({row.get('detail')})"
            for row in evaluation_contract.get("unresolved") or []
        ] or ["Evaluation contract admission failed."]
        acceptance = _final_execution_acceptance(
            requirement_ir,
            semantic_result,
            capsule_plan,
            physical_plan,
            binding_validation=binding_validation,
            capsule_binding=capsule_binding,
            evaluation_registry=evaluation_registry,
            evaluation_contract=evaluation_contract,
            evaluation_validation=evaluation_validation,
            frozen_contract=None,
            decision="failed",
            reasons=reasons,
        )
        write_json(output_dir / "plan_acceptance.json", acceptance)
        return {
            "capsule_plan": capsule_plan,
            "capsule_binding_validation": binding_validation,
            "physical_plan": physical_plan,
            "evaluation_check_registry": evaluation_registry,
            "evaluation_plan": evaluation_contract,
            "evaluation_plan_validation": evaluation_validation,
            "task_graph_contract": merged,
            "run_contract_frozen": None,
            "plan_acceptance": acceptance,
        }
    write_json(output_dir / "task_graph.contract.json", merged)
    scheduler_input = compile_scheduler_input(
        merged,
        capsule_plan,
        physical_plan,
        evaluation_contract,
        sprint_id=sprint_id,
    )
    _assert_schema(scheduler_input, SCHEDULER_INPUT_SCHEMA, "scheduler_input")
    write_json(output_dir / "scheduler_input.json", scheduler_input)
    frozen = {
        "schema_version": "solar.run_contract.frozen.v2",
        "artifact_role": "runtime_artifact",
        "sprint_id": sprint_id,
        "planning_authority": "frozen_execution_plan_v1",
        "test_policy": copy.deepcopy(merged.get("test_policy") or {}),
        "requirement_ir_ref": {
            "requirement_ir_id": requirement_ir_id(requirement_ir),
            "sha256": sha256_payload(requirement_ir),
        },
        "planning_decision_ref": {
            "planning_decision_id": requirement_decision.get("planning_decision_id"),
            "sha256": sha256_payload(requirement_decision),
        },
        "plan_ir_ref": {"plan_ir_id": plan_ir.get("plan_ir_id"), "sha256": sha256_payload(plan_ir)},
        "capsule_candidate_catalog_ref": (
            {"sha256": sha256_payload(capsule_binding["candidate_catalog"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "capsule_selection_ref": (
            {"sha256": sha256_payload(capsule_binding["selection"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "capsule_selection_validation_ref": (
            {"sha256": sha256_payload(capsule_binding["selection_validation"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "capsule_fit_review_ref": (
            {"sha256": sha256_payload(capsule_binding["fit_review"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "plan_composition_catalog_ref": (
            {"sha256": sha256_payload(capsule_binding["composition_catalog"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "composition_selection_ref": (
            {"sha256": sha256_payload(capsule_binding["selection"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "composition_selection_validation_ref": (
            {"sha256": sha256_payload(capsule_binding["selection_validation"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "composition_fit_review_ref": (
            {"sha256": sha256_payload(capsule_binding["fit_review"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "artifact_type_registry_ref": (
            {"sha256": sha256_payload(capsule_binding["artifact_type_registry"])}
            if capsule_binding
            and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "artifact_conversion_registry_ref": (
            {
                "sha256": sha256_payload(
                    capsule_binding["artifact_conversion_registry"]
                )
            }
            if capsule_binding
            and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "capsule_plan_ref": {"sha256": sha256_payload(capsule_plan)},
        "capsule_binding_validation_ref": {
            "sha256": sha256_payload(binding_validation)
        },
        "physical_plan_ref": {"sha256": sha256_payload(physical_plan)},
        "evaluation_check_registry_ref": {
            "registry_id": evaluation_registry.get("registry_id"),
            "sha256": sha256_payload(evaluation_registry),
        },
        "evaluation_plan_ref": {
            "evaluation_plan_id": evaluation_contract.get("evaluation_plan_id"),
            "sha256": sha256_payload(evaluation_contract),
        },
        "evaluation_plan_validation_ref": {
            "validation_id": evaluation_validation.get("validation_id"),
            "sha256": sha256_payload(evaluation_validation),
        },
        "scheduler_input_ref": {
            "scheduler_input_id": scheduler_input.get("scheduler_input_id"),
            "sha256": sha256_payload(scheduler_input),
        },
        "plan_certificate": copy.deepcopy(merged.get("plan_certificate") or {}),
    }
    frozen["contract_sha256"] = sha256_payload(frozen)
    _assert_schema(frozen, FROZEN_CONTRACT_SCHEMA, "run_contract_frozen")
    write_json(output_dir / "run_contract.frozen.json", frozen)
    acceptance = _final_execution_acceptance(
        requirement_ir,
        semantic_result,
        capsule_plan,
        physical_plan,
        binding_validation=binding_validation,
        capsule_binding=capsule_binding,
        evaluation_registry=evaluation_registry,
        evaluation_contract=evaluation_contract,
        evaluation_validation=evaluation_validation,
        frozen_contract=frozen,
        decision="accepted",
        reasons=[
            "Semantic plan admission passed.",
            "Every node has an admitted capsule and physical candidate list.",
            "Every node has a registered and independently admitted evaluation contract.",
            "Solar Plan Validator passed and the executable contract was frozen.",
        ],
    )
    write_json(output_dir / "plan_acceptance.json", acceptance)
    return {
        "binding_kind": capsule_binding.get("binding_kind") if capsule_binding else "exact_reuse",
        "direct_binding_attempt": direct_binding_attempt,
        "composition_binding_attempt": composition_binding_attempt,
        "capsule_candidate_catalog": (
            capsule_binding.get("candidate_catalog")
            if capsule_binding and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "capsule_selection": (
            capsule_binding.get("selection")
            if capsule_binding and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "capsule_selection_validation": (
            capsule_binding.get("selection_validation")
            if capsule_binding and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "capsule_fit_review": (
            capsule_binding.get("fit_review")
            if capsule_binding and capsule_binding.get("binding_kind") == "direct_capsule"
            else None
        ),
        "plan_composition_catalog": (
            capsule_binding.get("composition_catalog")
            if capsule_binding and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "artifact_type_registry": (
            capsule_binding.get("artifact_type_registry")
            if capsule_binding and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "artifact_conversion_registry": (
            capsule_binding.get("artifact_conversion_registry")
            if capsule_binding and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "composition_selection": (
            capsule_binding.get("selection")
            if capsule_binding and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "composition_selection_validation": (
            capsule_binding.get("selection_validation")
            if capsule_binding and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "composition_fit_review": (
            capsule_binding.get("fit_review")
            if capsule_binding and capsule_binding.get("binding_kind") == "capsule_composition"
            else None
        ),
        "capsule_plan": capsule_plan,
        "capsule_binding_validation": binding_validation,
        "physical_plan": physical_plan,
        "evaluation_check_registry": evaluation_registry,
        "evaluation_plan": evaluation_contract,
        "evaluation_plan_validation": evaluation_validation,
        "scheduler_input": scheduler_input,
        "task_graph_contract": merged,
        "run_contract_frozen": frozen,
        "plan_acceptance": acceptance,
    }


def _capsule_selection_failure_acceptance(
    requirement_ir: dict[str, Any],
    semantic_result: dict[str, Any],
    binding: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    semantic = semantic_result.get("plan_acceptance") or {}
    refs = copy.deepcopy(semantic.get("refs") or {})
    refs.update(_capsule_binding_acceptance_refs(binding))
    artifact = {
        "schema_version": "solar.plan_acceptance.v1",
        "artifact_role": "runtime_artifact",
        "acceptance_id": f"plan-acceptance-{requirement_ir_id(requirement_ir)}",
        "decision": "failed",
        "final_generation": semantic.get("final_generation"),
        "repair": {
            "attempted": bool(binding.get("repair_attempted")),
            "maximum_attempts": MAX_REPAIRS,
        },
        "refs": refs,
        "reasons": reasons,
        "runtime_handoff_allowed": False,
    }
    _assert_schema(artifact, ACCEPTANCE_SCHEMA, "capsule_selection_failure_acceptance")
    return artifact


def _capsule_binding_acceptance_refs(
    binding: dict[str, Any],
) -> dict[str, dict[str, str] | None]:
    if binding.get("binding_kind") == "capsule_composition":
        values = {
            "plan_composition_catalog": binding.get("composition_catalog"),
            "artifact_type_registry": binding.get("artifact_type_registry"),
            "artifact_conversion_registry": binding.get(
                "artifact_conversion_registry"
            ),
            "composition_selection": binding.get("selection"),
            "composition_selection_validation": binding.get("selection_validation"),
            "composition_fit_review": binding.get("fit_review"),
        }
    else:
        values = {
            "capsule_candidate_catalog": binding.get("candidate_catalog"),
            "capsule_selection": binding.get("selection"),
            "capsule_selection_validation": binding.get("selection_validation"),
            "capsule_fit_review": binding.get("fit_review"),
        }
    return {
        name: ({"sha256": sha256_payload(payload)} if payload is not None else None)
        for name, payload in values.items()
    }


def _final_execution_acceptance(
    requirement_ir: dict[str, Any],
    semantic_result: dict[str, Any],
    capsule_plan: dict[str, Any],
    physical_plan: dict[str, Any],
    *,
    binding_validation: dict[str, Any],
    capsule_binding: dict[str, Any] | None = None,
    evaluation_registry: dict[str, Any] | None = None,
    evaluation_contract: dict[str, Any] | None = None,
    evaluation_validation: dict[str, Any] | None = None,
    frozen_contract: dict[str, Any] | None,
    decision: str,
    reasons: list[str],
) -> dict[str, Any]:
    semantic = semantic_result.get("plan_acceptance") or {}
    refs = copy.deepcopy(semantic.get("refs") or {})
    refs.update(
        {
            "capsule_plan": {"sha256": sha256_payload(capsule_plan)},
            "capsule_binding_validation": {
                "validation_id": binding_validation.get("validation_id"),
                "sha256": sha256_payload(binding_validation),
            },
            "physical_plan": {"sha256": sha256_payload(physical_plan)},
            "run_contract_frozen": (
                {"sha256": sha256_payload(frozen_contract)} if frozen_contract else None
            ),
        }
    )
    if capsule_binding:
        refs.update(_capsule_binding_acceptance_refs(capsule_binding))
    if evaluation_registry is not None:
        refs["evaluation_check_registry"] = {
            "registry_id": evaluation_registry.get("registry_id"),
            "sha256": sha256_payload(evaluation_registry),
        }
    if evaluation_contract is not None:
        refs["evaluation_plan"] = {
            "evaluation_plan_id": evaluation_contract.get("evaluation_plan_id"),
            "sha256": sha256_payload(evaluation_contract),
        }
    if evaluation_validation is not None:
        refs["evaluation_plan_validation"] = {
            "validation_id": evaluation_validation.get("validation_id"),
            "sha256": sha256_payload(evaluation_validation),
        }
    artifact = {
        "schema_version": "solar.plan_acceptance.v1",
        "artifact_role": "runtime_artifact",
        "acceptance_id": f"plan-acceptance-{requirement_ir_id(requirement_ir)}",
        "decision": decision,
        "final_generation": semantic.get("final_generation"),
        "repair": copy.deepcopy(semantic.get("repair") or {"attempted": False, "maximum_attempts": 1}),
        "refs": refs,
        "reasons": reasons,
        "runtime_handoff_allowed": decision == "accepted" and frozen_contract is not None,
    }
    _assert_schema(artifact, ACCEPTANCE_SCHEMA, "final_plan_acceptance")
    return artifact


def run_elastic_planning_request(
    requirement_ir: dict[str, Any],
    output_root: Path,
    planner_model: JsonModel,
    reviewer_model: JsonModel,
    *,
    sprint_id: str,
    workspace_root: str = "workspace",
    catalog: dict[str, Any] | None = None,
    upstream_artifacts: dict[str, dict[str, Any]] | None = None,
    test_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the complete static planning boundary for one accepted RequirementIR."""
    semantic_dir = output_root / "semantic"
    execution_dir = output_root / "execution"
    semantic = run_semantic_planning_pipeline(
        requirement_ir,
        semantic_dir,
        planner_model,
        reviewer_model,
        catalog=catalog,
        upstream_artifacts=upstream_artifacts,
    )
    semantic_decision = str((semantic.get("plan_acceptance") or {}).get("decision") or "")
    if semantic_decision == "direct_response":
        return {
            "status": "direct_response",
            "semantic": semantic,
            "execution": None,
            "verification_errors": verify_semantic_planning_chain(semantic_dir),
        }
    if semantic_decision != "accepted":
        return {
            "status": semantic_decision or "failed",
            "semantic": semantic,
            "execution": None,
            "verification_errors": verify_semantic_planning_chain(semantic_dir),
        }
    execution = compile_and_freeze_execution_bundle(
        requirement_ir,
        semantic,
        execution_dir,
        sprint_id=sprint_id,
        workspace_root=workspace_root,
        planner_model=planner_model,
        reviewer_model=reviewer_model,
        test_policy=test_policy,
    )
    verification_errors = verify_frozen_execution_chain(semantic_dir, execution_dir)
    accepted = (
        (execution.get("plan_acceptance") or {}).get("decision") == "accepted"
        and not verification_errors
    )
    return {
        "status": "accepted" if accepted else "failed",
        "semantic": semantic,
        "execution": execution,
        "verification_errors": verification_errors,
    }


def verify_semantic_planning_chain(output_dir: Path) -> list[str]:
    """Recompute the content references for a completed semantic planning run."""
    errors: list[str] = []
    for name in ("requirement_ir.json", "planning_context.json", "planning_catalog_snapshot.json", "planning_decision.json", "plan_acceptance.json"):
        if not (output_dir / name).exists():
            errors.append(f"missing:{name}")
    if errors:
        return errors
    requirement_ir = _load_json(output_dir / "requirement_ir.json")
    planning_context = _load_json(output_dir / "planning_context.json")
    planning_catalog = _load_json(output_dir / "planning_catalog_snapshot.json")
    decision = _load_json(output_dir / "planning_decision.json")
    acceptance = _load_json(output_dir / "plan_acceptance.json")
    unhashed_catalog = copy.deepcopy(planning_catalog)
    declared_catalog_hash = str(unhashed_catalog.pop("catalog_sha256", ""))
    if declared_catalog_hash != sha256_payload(unhashed_catalog):
        errors.append("planning_catalog_snapshot.catalog_sha256.hash_mismatch")
    if _schema_errors(planning_catalog, CATALOG_SCHEMA):
        errors.append("planning_catalog_snapshot.schema_invalid")
    if (decision.get("requirement_ir_ref") or {}).get("sha256") != sha256_payload(requirement_ir):
        errors.append("planning_decision.requirement_ir_ref.hash_mismatch")
    context_ref = decision.get("planning_context_ref") or {}
    if (
        context_ref.get("planning_context_id") != planning_context.get("planning_context_id")
        or context_ref.get("sha256") != sha256_payload(planning_context)
    ):
        errors.append("planning_decision.planning_context_ref.hash_mismatch")
    seen_context_names: set[str] = set()
    for row in planning_context.get("artifacts") or []:
        name = str((row or {}).get("name") or "")
        relative_path = str((row or {}).get("relative_path") or "")
        if not name or name in seen_context_names:
            errors.append(f"planning_context.artifacts.name_invalid:{name}")
            continue
        seen_context_names.add(name)
        path = output_dir / relative_path
        try:
            resolved = path.resolve()
            resolved.relative_to(output_dir.resolve())
        except (OSError, ValueError):
            errors.append(f"planning_context.artifacts.path_invalid:{name}")
            continue
        if not path.is_file():
            errors.append(f"planning_context.artifacts.missing:{name}")
            continue
        if (row or {}).get("sha256") != sha256_payload(_load_json(path)):
            errors.append(f"planning_context.artifacts.hash_mismatch:{name}")
    references = acceptance.get("refs") or {}
    expected_files = {
        "requirement_ir": ("requirement_ir.json", "requirement_ir_id"),
        "planning_context": ("planning_context.json", "planning_context_id"),
        "planning_decision": ("planning_decision.json", "planning_decision_id"),
        "plan_ir": ("plan_ir.json", "plan_ir_id"),
        "plan_validation": ("plan_validation.json", "validation_id"),
        "plan_fidelity": ("plan_fidelity.json", "fidelity_id"),
        "binding_trace": ("binding_trace.json", "binding_trace_id"),
        "direct_response": ("direct_response.json", "response_id"),
        "direct_response_review": ("direct_response_review.json", "review_id"),
    }
    for key, (filename, id_key) in expected_files.items():
        reference = references.get(key)
        path = output_dir / filename
        if reference is None:
            if path.exists():
                errors.append(f"acceptance.refs.{key}.missing")
            continue
        if not path.exists():
            errors.append(f"missing:{filename}")
            continue
        payload = _load_json(path)
        payload_id = (
            requirement_ir_id(payload)
            if key == "requirement_ir"
            else payload.get(id_key)
        )
        if reference.get(id_key) != payload_id:
            errors.append(f"acceptance.refs.{key}.id_mismatch")
        if reference.get("sha256") != sha256_payload(payload):
            errors.append(f"acceptance.refs.{key}.hash_mismatch")
    response_path = output_dir / "direct_response.json"
    review_path = output_dir / "direct_response_review.json"
    if response_path.exists() and review_path.exists():
        response = _load_json(response_path)
        review = _load_json(review_path)
        response_ref = review.get("response_ref") or {}
        if response_ref.get("response_id") != response.get("response_id"):
            errors.append("direct_response_review.response_ref.id_mismatch")
        if response_ref.get("sha256") != sha256_payload(response):
            errors.append("direct_response_review.response_ref.hash_mismatch")
    # A rejected strategy decision may legitimately stop before PlanIR and its
    # deterministic composition proof exist.  Once a PlanIR is referenced,
    # however, all composition snapshots are part of the semantic hash chain.
    if decision.get("decision") == "generate" and references.get("plan_ir") is not None:
        composition_files = {
            "catalog": output_dir / "plan_composition_catalog.json",
            "artifact_registry": output_dir / "artifact_type_registry.snapshot.json",
            "conversion_registry": output_dir
            / "artifact_conversion_registry.snapshot.json",
        }
        for name, path in composition_files.items():
            if not path.exists():
                errors.append(f"missing:composition_{name}")
        if all(path.exists() for path in composition_files.values()):
            composition_catalog = _load_json(composition_files["catalog"])
            artifact_registry = _load_json(composition_files["artifact_registry"])
            conversion_registry = _load_json(composition_files["conversion_registry"])
            if (composition_catalog.get("artifact_type_registry_ref") or {}).get(
                "sha256"
            ) != sha256_payload(artifact_registry):
                errors.append(
                    "plan_composition_catalog.artifact_type_registry_ref.hash_mismatch"
                )
            if (composition_catalog.get("conversion_registry_ref") or {}).get(
                "sha256"
            ) != sha256_payload(conversion_registry):
                errors.append(
                    "plan_composition_catalog.conversion_registry_ref.hash_mismatch"
                )
            if (composition_catalog.get("planning_catalog_ref") or {}).get(
                "sha256"
            ) != sha256_payload(planning_catalog):
                errors.append(
                    "plan_composition_catalog.planning_catalog_ref.hash_mismatch"
                )
            plan_path = output_dir / "plan_ir.json"
            if plan_path.exists():
                plan_ir = _load_json(plan_path)
                recomputed = build_plan_composition_catalog(
                    requirement_ir,
                    planning_context,
                    plan_ir,
                    planning_catalog,
                    artifact_registry=artifact_registry,
                    conversion_registry=conversion_registry,
                )
                if recomputed != composition_catalog:
                    errors.append("plan_composition_catalog.recomputed_mismatch")
    return errors


def verify_frozen_execution_chain(
    semantic_dir: Path, execution_dir: Path
) -> list[str]:
    """Recompute the admitted semantic-to-runtime content chain."""
    errors = [f"semantic:{value}" for value in verify_semantic_planning_chain(semantic_dir)]
    required = {
        "capsule_plan": execution_dir / "capsule_plan.json",
        "capsule_binding_validation": execution_dir / "capsule_binding_validation.json",
        "physical_plan": execution_dir / "physical_plan.json",
        "evaluation_registry": execution_dir / "evaluation_check_registry.snapshot.json",
        "evaluation_plan": execution_dir / "evaluation_plan.json",
        "evaluation_validation": execution_dir / "evaluation_plan_validation.json",
        "scheduler_input": execution_dir / "scheduler_input.json",
        "task_graph": execution_dir / "task_graph.contract.json",
        "frozen": execution_dir / "run_contract.frozen.json",
        "acceptance": execution_dir / "plan_acceptance.json",
    }
    for name, path in required.items():
        if not path.exists():
            errors.append(f"missing:{name}")
    if errors:
        return errors
    payloads = {name: _load_json(path) for name, path in required.items()}
    capsule = payloads["capsule_plan"]
    binding_validation = payloads["capsule_binding_validation"]
    physical = payloads["physical_plan"]
    evaluation_registry = payloads["evaluation_registry"]
    evaluation_contract = payloads["evaluation_plan"]
    evaluation_validation = payloads["evaluation_validation"]
    scheduler_input = payloads["scheduler_input"]
    graph = payloads["task_graph"]
    frozen = payloads["frozen"]
    acceptance = payloads["acceptance"]
    selection_ref = frozen.get("capsule_selection_ref")
    if selection_ref is not None:
        generated_paths = {
            "capsule_candidate_catalog": execution_dir / "capsule_candidate_catalog.json",
            "capsule_selection": execution_dir / "capsule_selection.json",
            "capsule_selection_validation": execution_dir / "capsule_selection_validation.json",
            "capsule_fit_review": execution_dir / "capsule_fit_review.json",
        }
        for name, path in generated_paths.items():
            if not path.exists():
                errors.append(f"missing:{name}")
        if not errors:
            generated_payloads = {
                name: _load_json(path) for name, path in generated_paths.items()
            }
            generated_refs = {
                "capsule_candidate_catalog_ref": generated_payloads["capsule_candidate_catalog"],
                "capsule_selection_ref": generated_payloads["capsule_selection"],
                "capsule_selection_validation_ref": generated_payloads["capsule_selection_validation"],
                "capsule_fit_review_ref": generated_payloads["capsule_fit_review"],
            }
            for ref_name, payload in generated_refs.items():
                if (frozen.get(ref_name) or {}).get("sha256") != sha256_payload(payload):
                    errors.append(f"frozen.{ref_name}.hash_mismatch")
            selection = generated_payloads["capsule_selection"]
            candidate_catalog = generated_payloads["capsule_candidate_catalog"]
            selection_validation = generated_payloads["capsule_selection_validation"]
            fit_review = generated_payloads["capsule_fit_review"]
            if (selection.get("candidate_catalog_ref") or {}).get("sha256") != sha256_payload(candidate_catalog):
                errors.append("capsule_selection.candidate_catalog_ref.hash_mismatch")
            if (selection_validation.get("selection_ref") or {}).get("sha256") != sha256_payload(selection):
                errors.append("capsule_selection_validation.selection_ref.hash_mismatch")
            if selection_validation.get("status") != "pass":
                errors.append("capsule_selection_validation.status_not_pass")
            if (fit_review.get("selection_ref") or {}).get("sha256") != sha256_payload(selection):
                errors.append("capsule_fit_review.selection_ref.hash_mismatch")
            if fit_review.get("status") == "fail":
                errors.append("capsule_fit_review.status_fail")
    composition_selection_ref = frozen.get("composition_selection_ref")
    if composition_selection_ref is not None:
        composition_paths = {
            "plan_composition_catalog": execution_dir / "plan_composition_catalog.json",
            "artifact_type_registry": execution_dir / "artifact_type_registry.snapshot.json",
            "artifact_conversion_registry": execution_dir / "artifact_conversion_registry.snapshot.json",
            "composition_selection": execution_dir / "composition_selection.json",
            "composition_selection_validation": execution_dir / "composition_selection_validation.json",
            "composition_fit_review": execution_dir / "composition_fit_review.json",
        }
        for name, path in composition_paths.items():
            if not path.exists():
                errors.append(f"missing:{name}")
        if not errors:
            composition_payloads = {
                name: _load_json(path) for name, path in composition_paths.items()
            }
            composition_refs = {
                "plan_composition_catalog_ref": composition_payloads["plan_composition_catalog"],
                "artifact_type_registry_ref": composition_payloads["artifact_type_registry"],
                "artifact_conversion_registry_ref": composition_payloads[
                    "artifact_conversion_registry"
                ],
                "composition_selection_ref": composition_payloads["composition_selection"],
                "composition_selection_validation_ref": composition_payloads["composition_selection_validation"],
                "composition_fit_review_ref": composition_payloads["composition_fit_review"],
            }
            for ref_name, payload in composition_refs.items():
                if (frozen.get(ref_name) or {}).get("sha256") != sha256_payload(payload):
                    errors.append(f"frozen.{ref_name}.hash_mismatch")
            composition_catalog = composition_payloads["plan_composition_catalog"]
            composition_selection = composition_payloads["composition_selection"]
            composition_validation = composition_payloads[
                "composition_selection_validation"
            ]
            composition_review = composition_payloads["composition_fit_review"]
            if (composition_selection.get("composition_catalog_ref") or {}).get(
                "sha256"
            ) != sha256_payload(composition_catalog):
                errors.append("composition_selection.composition_catalog_ref.hash_mismatch")
            if (composition_validation.get("selection_ref") or {}).get(
                "sha256"
            ) != sha256_payload(composition_selection):
                errors.append("composition_selection_validation.selection_ref.hash_mismatch")
            if composition_validation.get("status") != "pass":
                errors.append("composition_selection_validation.status_not_pass")
            if (composition_review.get("selection_ref") or {}).get(
                "sha256"
            ) != sha256_payload(composition_selection):
                errors.append("composition_fit_review.selection_ref.hash_mismatch")
            if composition_review.get("status") == "fail":
                errors.append("composition_fit_review.status_fail")
            recomputed = validate_composition_selection(
                _load_json(semantic_dir / "requirement_ir.json"),
                _load_json(semantic_dir / "planning_context.json"),
                _load_json(semantic_dir / "plan_ir.json"),
                _load_json(semantic_dir / "planning_catalog_snapshot.json"),
                composition_catalog,
                composition_selection,
                artifact_registry=composition_payloads["artifact_type_registry"],
                conversion_registry=composition_payloads[
                    "artifact_conversion_registry"
                ],
            )
            if recomputed != composition_validation:
                errors.append("composition_selection_validation.recomputed_mismatch")
            graph_composition_ref = graph.get("composition_selection_ref") or {}
            if graph_composition_ref.get("sha256") != sha256_payload(
                composition_selection
            ):
                errors.append("task_graph.composition_selection_ref.hash_mismatch")
    if (physical.get("capsule_plan_ref") or {}).get("sha256") != sha256_payload(capsule):
        errors.append("physical_plan.capsule_plan_ref.hash_mismatch")
    if (binding_validation.get("capsule_plan_ref") or {}).get("sha256") != sha256_payload(capsule):
        errors.append("capsule_binding_validation.capsule_plan_ref.hash_mismatch")
    if binding_validation.get("status") != "pass":
        errors.append("capsule_binding_validation.status_not_pass")
    try:
        loaded_registry = evaluation_planning.load_evaluation_check_registry(
            required["evaluation_registry"]
        )
    except evaluation_planning.EvaluationPlanError as exc:
        loaded_registry = None
        errors.append(f"evaluation_registry.invalid:{exc}")
    if loaded_registry is not None and loaded_registry != evaluation_registry:
        errors.append("evaluation_registry.snapshot_mismatch")
    if (evaluation_contract.get("registry_ref") or {}).get("sha256") != sha256_payload(
        evaluation_registry
    ):
        errors.append("evaluation_plan.registry_ref.hash_mismatch")
    if (evaluation_contract.get("task_graph_ref") or {}).get("sha256") != sha256_payload(graph):
        errors.append("evaluation_plan.task_graph_ref.hash_mismatch")
    if (evaluation_validation.get("evaluation_plan_ref") or {}).get("sha256") != sha256_payload(
        evaluation_contract
    ):
        errors.append("evaluation_plan_validation.evaluation_plan_ref.hash_mismatch")
    if evaluation_contract.get("verdict") != "pass":
        errors.append("evaluation_plan.verdict_not_pass")
    if evaluation_validation.get("status") != "pass":
        errors.append("evaluation_plan_validation.status_not_pass")
    if loaded_registry is not None:
        recomputed_evaluation_validation = evaluation_planning.validate_evaluation_plan(
            evaluation_contract,
            _load_json(semantic_dir / "requirement_ir.json"),
            _load_json(semantic_dir / "plan_ir.json"),
            capsule,
            graph,
            registry=loaded_registry,
        )
        if recomputed_evaluation_validation != evaluation_validation:
            errors.append("evaluation_plan_validation.recomputed_mismatch")
    recomputed_scheduler_input = compile_scheduler_input(
        graph,
        capsule,
        physical,
        evaluation_contract,
        sprint_id=str(graph.get("sprint_id") or ""),
    )
    if recomputed_scheduler_input != scheduler_input:
        errors.append("scheduler_input.recomputed_mismatch")
    expected_refs = {
        "capsule_plan_ref": capsule,
        "capsule_binding_validation_ref": binding_validation,
        "physical_plan_ref": physical,
        "evaluation_check_registry_ref": evaluation_registry,
        "evaluation_plan_ref": evaluation_contract,
        "evaluation_plan_validation_ref": evaluation_validation,
        "scheduler_input_ref": scheduler_input,
    }
    if composition_selection_ref is not None and not errors:
        expected_refs.update(
            {
                "plan_composition_catalog_ref": _load_json(
                    execution_dir / "plan_composition_catalog.json"
                ),
                "artifact_type_registry_ref": _load_json(
                    execution_dir / "artifact_type_registry.snapshot.json"
                ),
                "artifact_conversion_registry_ref": _load_json(
                    execution_dir / "artifact_conversion_registry.snapshot.json"
                ),
                "composition_selection_ref": _load_json(
                    execution_dir / "composition_selection.json"
                ),
                "composition_selection_validation_ref": _load_json(
                    execution_dir / "composition_selection_validation.json"
                ),
                "composition_fit_review_ref": _load_json(
                    execution_dir / "composition_fit_review.json"
                ),
            }
        )
    for ref_name, payload in expected_refs.items():
        if (frozen.get(ref_name) or {}).get("sha256") != sha256_payload(payload):
            errors.append(f"frozen.{ref_name}.hash_mismatch")
    unhashed_frozen = copy.deepcopy(frozen)
    declared_contract_hash = str(unhashed_frozen.pop("contract_sha256", ""))
    if declared_contract_hash != sha256_payload(unhashed_frozen):
        errors.append("frozen.contract_sha256.hash_mismatch")
    certificate_errors = plan_validator.check_plan_certificate(graph)
    if certificate_errors:
        errors.extend(
            f"task_graph.plan_certificate:{row.get('code')}"
            for row in certificate_errors
        )
    if frozen.get("plan_certificate") != graph.get("plan_certificate"):
        errors.append("frozen.plan_certificate.mismatch")
    nodes = {
        str(node.get("id") or ""): node
        for node in graph.get("nodes") or []
        if isinstance(node, dict)
    }
    for physical_node in physical.get("nodes") or []:
        node_id = str(physical_node.get("node_id") or "")
        candidate_ids = [
            str(row.get("operator_id") or "")
            for row in physical_node.get("execution_candidates") or []
            if isinstance(row, dict)
        ]
        if (nodes.get(node_id) or {}).get("approved_physical_operator_ids") != candidate_ids:
            errors.append(f"task_graph.nodes.{node_id}.approved_candidates.mismatch")
    frozen_ref = (acceptance.get("refs") or {}).get("run_contract_frozen") or {}
    if frozen_ref.get("sha256") != sha256_payload(frozen):
        errors.append("acceptance.refs.run_contract_frozen.hash_mismatch")
    binding_ref = (acceptance.get("refs") or {}).get("capsule_binding_validation") or {}
    if binding_ref.get("sha256") != sha256_payload(binding_validation):
        errors.append("acceptance.refs.capsule_binding_validation.hash_mismatch")
    acceptance_evaluation_refs = {
        "evaluation_check_registry": evaluation_registry,
        "evaluation_plan": evaluation_contract,
        "evaluation_plan_validation": evaluation_validation,
    }
    for ref_name, payload in acceptance_evaluation_refs.items():
        reference = (acceptance.get("refs") or {}).get(ref_name) or {}
        if reference.get("sha256") != sha256_payload(payload):
            errors.append(f"acceptance.refs.{ref_name}.hash_mismatch")
    if composition_selection_ref is not None:
        for ref_name, filename in (
            ("plan_composition_catalog", "plan_composition_catalog.json"),
            ("artifact_type_registry", "artifact_type_registry.snapshot.json"),
            (
                "artifact_conversion_registry",
                "artifact_conversion_registry.snapshot.json",
            ),
            ("composition_selection", "composition_selection.json"),
            (
                "composition_selection_validation",
                "composition_selection_validation.json",
            ),
            ("composition_fit_review", "composition_fit_review.json"),
        ):
            path = execution_dir / filename
            if path.exists():
                reference = (acceptance.get("refs") or {}).get(ref_name) or {}
                if reference.get("sha256") != sha256_payload(_load_json(path)):
                    errors.append(f"acceptance.refs.{ref_name}.hash_mismatch")
    if acceptance.get("decision") != "accepted" or not acceptance.get(
        "runtime_handoff_allowed"
    ):
        errors.append("acceptance.runtime_handoff_not_allowed")
    return errors


def requirement_summary(requirement_ir: dict[str, Any]) -> list[dict[str, str]]:
    """Small public helper used by tests and UI projections."""
    return [
        {
            "requirement_id": _requirement_id(row),
            "statement": _requirement_text(row),
            "verifier_id": _requirement_verifier(row),
        }
        for row in requirements(requirement_ir)
    ]


def iter_requirement_ids(requirement_ir: dict[str, Any]) -> Iterable[str]:
    for row in requirements(requirement_ir):
        yield _requirement_id(row)
