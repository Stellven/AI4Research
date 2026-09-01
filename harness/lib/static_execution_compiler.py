#!/usr/bin/env python3
"""Compile an accepted Planner bundle into frozen scheduler authority.

The Elastic Planner owns semantic topology (PlanIR).  This module performs the
deterministic work that follows it: validate the Planner/evaluator artifacts,
bind capability capsules, rank statically admitted physical operators, bind
output checks, and emit the one immutable ``scheduler_input.json`` consumed by
the runtime scheduler.

No runtime availability, lease, attempt, or selected-operator state is written
here.  Those decisions remain scheduler-owned and live in separate ledgers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import jsonschema


SOURCE_HARNESS_DIR = Path(__file__).resolve().parents[1]
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR") or SOURCE_HARNESS_DIR).resolve()
SCHEMA_DIR = HARNESS_DIR / "schemas" / "planning"
CAPSULE_REGISTRY = HARNESS_DIR / "config" / "capability-capsules.registry.yaml"
PHYSICAL_OPERATORS = HARNESS_DIR / "config" / "physical-operators.json"

# apo_plan_compiler resolves a few defaults at import time.
os.environ.setdefault("HARNESS_DIR", str(HARNESS_DIR))
from apo_plan_compiler import (  # noqa: E402
    build_capsule_plan_node,
    build_physical_plan_for_capsule_node,
)
from capability_capsules import (  # noqa: E402
    iter_registry_entries,
    load_capability_capsule_manifest,
)
import scheduler_input as scheduler_input_runtime  # noqa: E402


class StaticExecutionCompileError(ValueError):
    """The Planner bundle cannot be admitted for runtime execution."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StaticExecutionCompileError(f"ARTIFACT_UNREADABLE:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise StaticExecutionCompileError(f"ARTIFACT_ROOT_NOT_OBJECT:{path}")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _schema(name: str) -> dict[str, Any]:
    return _read_json(SCHEMA_DIR / name)


def _validate_schema(value: dict[str, Any], schema_name: str) -> None:
    schema = _schema(schema_name)
    # Two schemas deliberately use URN-like sibling $refs.  Validate their
    # semantic portions independently, then validate the outer artifact with
    # those refs replaced by the sibling definitions.
    if schema_name == "plan-ir.v2.schema.json":
        semantic = _schema("plan-ir.semantic.v2.schema.json")
        jsonschema.Draft202012Validator(semantic).validate({"nodes": value.get("nodes")})
        schema = json.loads(json.dumps(schema))
        schema["$defs"] = semantic["$defs"]
        schema["properties"]["nodes"]["items"] = semantic["$defs"]["node"]
    elif schema_name == "planning-decision.v1.schema.json":
        semantic = _schema("planning-decision.semantic.v1.schema.json")
        semantic_view = {
            key: value.get(key)
            for key in semantic.get("properties", {})
        }
        jsonschema.Draft202012Validator(semantic).validate(semantic_view)
        schema = json.loads(json.dumps(schema))
        for key in ("workflow_ref", "workflow_inputs", "workflow_bindings", "requirements_gap"):
            schema["properties"][key] = semantic["properties"][key]
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "$"
        raise StaticExecutionCompileError(
            f"SCHEMA_INVALID:{schema_name}:{location}:{exc.message}"
        ) from exc


def _require_ref(value: dict[str, Any], field: str, artifact_id: str, digest: str) -> None:
    ref = value.get(field) if isinstance(value.get(field), dict) else {}
    observed_id = next((str(ref.get(key) or "") for key in (
        "requirement_ir_id", "planning_decision_id", "plan_ir_id"
    ) if ref.get(key)), "")
    if observed_id != artifact_id:
        raise StaticExecutionCompileError(f"REFERENCE_ID_MISMATCH:{field}:{observed_id}:{artifact_id}")
    if str(ref.get("sha256") or "") != digest:
        raise StaticExecutionCompileError(f"REFERENCE_HASH_MISMATCH:{field}")


def _normalized_artifact(value: str) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\.v\d+(?:\.schema)?(?:\.json)?$", "", text)
    text = text.replace("artifact.", "").replace("research.", "")
    text = text.replace("schemas/evidence/", "").replace("schema_ref:", "")
    return re.sub(r"[^a-z0-9]+", "", text)


def _manifest_artifacts(manifest: dict[str, Any], direction: str) -> set[str]:
    values: list[str] = []
    composition = manifest.get("composition") if isinstance(manifest.get("composition"), dict) else {}
    for item in composition.get(direction) or []:
        if isinstance(item, dict):
            values.extend(str(item.get(key) or "") for key in ("type", "schema_ref", "name"))
        else:
            values.append(str(item))
    contract = manifest.get("contract") if isinstance(manifest.get("contract"), dict) else {}
    contract_direction = "outputs" if direction == "produces" else "inputs"
    contract_items = contract.get(contract_direction) if isinstance(contract.get(contract_direction), dict) else {}
    for group in ("required", "optional"):
        for item in contract_items.get(group) or []:
            if isinstance(item, dict):
                values.extend(str(item.get(key) or "") for key in ("type", "schema_ref", "name"))
            else:
                values.append(str(item))
    return {_normalized_artifact(value) for value in values if _normalized_artifact(value)}


def _select_capsule(node: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    wanted_outputs = {
        _normalized_artifact(item.get("artifact_type"))
        for item in node.get("produces") or []
        if isinstance(item, dict)
    }
    wanted_inputs = {_normalized_artifact(item) for item in node.get("consumes") or []}
    objective_tokens = set(re.findall(r"[a-z0-9]+", str(node.get("objective") or "").lower()))
    capability_tokens = {
        token
        for item in (node.get("operator_requirements") or {}).get("capabilities") or []
        for token in re.findall(r"[a-z0-9]+", str(item).lower())
    }
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for entry in iter_registry_entries(path=CAPSULE_REGISTRY):
        manifest = load_capability_capsule_manifest(Path(entry.manifest_path))
        produced = _manifest_artifacts(manifest, "produces")
        consumed = _manifest_artifacts(manifest, "consumes")
        output_matches = len(wanted_outputs.intersection(produced))
        input_matches = len(wanted_inputs.intersection(consumed))
        text = " ".join([
            str(entry.capability_capsule_id),
            " ".join(entry.tags),
            str((manifest.get("metadata") or {}).get("name") or ""),
            " ".join((manifest.get("applicability") or {}).get("positive_signals") or []),
        ]).lower()
        text_tokens = set(re.findall(r"[a-z0-9]+", text))
        lexical = len((objective_tokens | capability_tokens).intersection(text_tokens))
        score = output_matches * 1000 + input_matches * 100 + lexical
        scored.append((score, entry.capability_capsule_id, manifest))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored or scored[0][0] <= 0:
        raise StaticExecutionCompileError(f"CAPSULE_UNSATISFIABLE:{node.get('node_id')}")
    return scored[0][1], scored[0][2]


def _request_type(requirement_ir: dict[str, Any]) -> str:
    scope = requirement_ir.get("scope") if isinstance(requirement_ir.get("scope"), dict) else {}
    if "research" in scope:
        return "research"
    return "general"


def _effects(node: dict[str, Any]) -> list[str]:
    requested = set((node.get("operator_requirements") or {}).get("effects") or [])
    return [item for item in ("read", "write", "execute", "network") if item in requested]


def _capsule_contract_hash(node: dict[str, Any]) -> str:
    return _canonical_sha256({
        "capsule_id": node.get("capability_capsule_id"),
        "artifact_types": node.get("artifact_types"),
        "effect_union": node.get("effect_union"),
        "proof_obligations": node.get("proof_obligations"),
        "stages": node.get("stages"),
    })


def _artifact_ref(path: Path, id_key: str, value: dict[str, Any]) -> dict[str, Any]:
    return {id_key: str(value.get(id_key) or ""), "sha256": _file_sha256(path)}


def _planner_bundle(
    requirement_path: Path,
    decision_path: Path,
    plan_path: Path,
    validation_path: Path,
    fidelity_path: Path,
    binding_path: Path,
) -> dict[str, dict[str, Any]]:
    paths = {
        "requirement": requirement_path,
        "decision": decision_path,
        "plan": plan_path,
        "validation": validation_path,
        "fidelity": fidelity_path,
        "binding": binding_path,
    }
    values = {name: _read_json(path) for name, path in paths.items()}
    _validate_schema(values["decision"], "planning-decision.v1.schema.json")
    _validate_schema(values["plan"], "plan-ir.v2.schema.json")
    _validate_schema(values["validation"], "plan-validation.v2.schema.json")
    _validate_schema(values["fidelity"], "plan-fidelity.v1.schema.json")
    _validate_schema(values["binding"], "binding-trace.v2.schema.json")

    requirement_id = str(values["requirement"].get("requirement_ir_id") or "")
    if values["requirement"].get("schema_version") != "solar.requirement_ir.v2" or not requirement_id:
        raise StaticExecutionCompileError("REQUIREMENT_IR_V2_REQUIRED")
    requirement_digest = _file_sha256(requirement_path)
    plan_id = str(values["plan"].get("plan_ir_id") or "")
    plan_digest = _file_sha256(plan_path)
    decision_id = str(values["decision"].get("planning_decision_id") or "")
    decision_digest = _file_sha256(decision_path)

    _require_ref(values["decision"], "requirement_ir_ref", requirement_id, requirement_digest)
    _require_ref(values["plan"], "requirement_ir_ref", requirement_id, requirement_digest)
    _require_ref(values["plan"], "planning_decision_ref", decision_id, decision_digest)
    _require_ref(values["validation"], "plan_ir_ref", plan_id, plan_digest)
    _require_ref(values["fidelity"], "requirement_ir_ref", requirement_id, requirement_digest)
    _require_ref(values["fidelity"], "plan_ir_ref", plan_id, plan_digest)
    _require_ref(values["binding"], "requirement_ir_ref", requirement_id, requirement_digest)
    _require_ref(values["binding"], "plan_ir_ref", plan_id, plan_digest)

    if values["decision"].get("decision") not in {"generate", "exact_reuse"}:
        raise StaticExecutionCompileError("PLANNING_DECISION_NOT_EXECUTABLE")
    if values["validation"].get("status") != "pass" or any(
        item.get("status") != "pass" for item in values["validation"].get("checks") or []
    ):
        raise StaticExecutionCompileError("PLAN_VALIDATION_NOT_PASSED")
    if values["fidelity"].get("status") not in {"pass", "pass_with_warnings"}:
        raise StaticExecutionCompileError("PLAN_FIDELITY_NOT_PASSED")
    if values["binding"].get("verdict") != "pass" or values["binding"].get("uncovered"):
        raise StaticExecutionCompileError("BINDING_TRACE_NOT_PASSED")

    requirement_ids = {
        str(item.get("requirement_id") or "")
        for item in values["requirement"].get("requirements") or []
        if isinstance(item, dict)
    }
    plan_nodes = {
        str(item.get("node_id") or ""): item
        for item in values["plan"].get("nodes") or []
        if isinstance(item, dict)
    }
    node_ids = set(plan_nodes)
    for node_id, node in plan_nodes.items():
        unknown = sorted(set(node.get("requirement_ids") or []).difference(requirement_ids))
        if unknown:
            raise StaticExecutionCompileError(f"UNKNOWN_NODE_REQUIREMENT:{node_id}:{','.join(unknown)}")
    for requirement_id, binding in (values["binding"].get("bindings") or {}).items():
        if requirement_id not in requirement_ids:
            raise StaticExecutionCompileError(f"UNKNOWN_BOUND_REQUIREMENT:{requirement_id}")
        if any(owner not in node_ids for owner in binding.get("owners") or []):
            raise StaticExecutionCompileError(f"UNKNOWN_BINDING_OWNER:{requirement_id}")
        for owner in binding.get("owners") or []:
            owner_node = plan_nodes[owner]
            if requirement_id not in owner_node.get("requirement_ids", []):
                raise StaticExecutionCompileError(f"BINDING_OWNER_MISSING_REQUIREMENT:{requirement_id}:{owner}")
            produced = {
                str(item.get("artifact_type") or "")
                for item in owner_node.get("produces") or []
                if isinstance(item, dict)
            }
            missing_artifacts = sorted(set(binding.get("artifacts") or []).difference(produced))
            if missing_artifacts:
                raise StaticExecutionCompileError(
                    f"BINDING_ARTIFACT_NOT_PRODUCED:{requirement_id}:{owner}:{','.join(missing_artifacts)}"
                )
            admitted_verifiers = {
                str(owner_node.get("gate_requirement") or ""),
                *[
                    str(verifier)
                    for item in owner_node.get("produces") or []
                    if isinstance(item, dict)
                    for verifier in item.get("verifier_ids") or []
                ],
            }
            requirement = next(
                (
                    item
                    for item in values["requirement"].get("requirements") or []
                    if isinstance(item, dict) and item.get("requirement_id") == requirement_id
                ),
                {},
            )
            if requirement.get("check"):
                admitted_verifiers.add(str(requirement["check"]))
            missing_verifiers = sorted(set(binding.get("verifiers") or []).difference(admitted_verifiers))
            if missing_verifiers:
                raise StaticExecutionCompileError(
                    f"BINDING_VERIFIER_NOT_ADMITTED:{requirement_id}:{owner}:{','.join(missing_verifiers)}"
                )
    if set((values["binding"].get("bindings") or {}).keys()) != requirement_ids:
        raise StaticExecutionCompileError("BINDING_TRACE_REQUIREMENT_SET_MISMATCH")
    return values


def compile_bundle(
    *,
    requirement_ir_path: str | Path,
    planning_decision_path: str | Path,
    plan_ir_path: str | Path,
    plan_validation_path: str | Path,
    plan_fidelity_path: str | Path,
    binding_trace_path: str | Path,
    output_dir: str | Path,
    sprint_id: str = "",
) -> dict[str, str]:
    source_paths = {
        "requirement": Path(requirement_ir_path).resolve(),
        "decision": Path(planning_decision_path).resolve(),
        "plan": Path(plan_ir_path).resolve(),
        "validation": Path(plan_validation_path).resolve(),
        "fidelity": Path(plan_fidelity_path).resolve(),
        "binding": Path(binding_trace_path).resolve(),
    }
    bundle = _planner_bundle(
        source_paths["requirement"], source_paths["decision"], source_paths["plan"],
        source_paths["validation"], source_paths["fidelity"], source_paths["binding"],
    )
    requirement_ir = bundle["requirement"]
    plan_ir = bundle["plan"]
    sid = sprint_id or f"sprint-{plan_ir['plan_ir_id']}"
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    capsule_nodes: list[dict[str, Any]] = []
    capsule_manifests: dict[str, dict[str, Any]] = {}
    physical_nodes: list[dict[str, Any]] = []
    scheduler_nodes: list[dict[str, Any]] = []
    request_type = _request_type(requirement_ir)
    requirement_by_id = {
        item["requirement_id"]: item
        for item in requirement_ir.get("requirements") or []
        if isinstance(item, dict) and item.get("requirement_id")
    }

    for index, plan_node in enumerate(plan_ir["nodes"]):
        capsule_id, manifest = _select_capsule(plan_node)
        capsule_manifests[str(plan_node["node_id"])] = manifest
        task_types = list((manifest.get("applicability") or {}).get("task_types") or [])
        legacy_node = {
            "id": plan_node["node_id"],
            "goal": plan_node["objective"],
            "logical_operator": plan_node["logical_operator"],
            "depends_on": list(plan_node["depends_on"]),
            "capability_capsule_id": capsule_id,
            "dispatch_task_type": str(task_types[0] if task_types else "execution"),
            "write_scope": [item["artifact_type"] for item in plan_node["produces"]],
            "requirement_ids": list(plan_node["requirement_ids"]),
        }
        capsule_node = build_capsule_plan_node(
            legacy_node,
            request_type=request_type,
            registry_path=CAPSULE_REGISTRY,
            goal_text=plan_node["objective"],
        )
        if not capsule_node.get("selected"):
            raise StaticExecutionCompileError(f"CAPSULE_BINDING_FAILED:{plan_node['node_id']}")
        capsule_node["approved_fallback_capsule_ids"] = []
        capsule_node["capsule_selection_rationale"] = "deterministic artifact-contract and capability fit"
        capsule_nodes.append(capsule_node)

        physical = build_physical_plan_for_capsule_node(
            capsule_node,
            operators_path=PHYSICAL_OPERATORS,
            require_dispatchable=False,
        )
        ranked = [
            {
                "operator_id": str(candidate["operator_id"]),
                "rank": rank,
                "rank_score": int(candidate.get("priority") or 0),
                "admission_state": "READY",
            }
            for rank, candidate in enumerate(physical.get("execution_candidates") or [], start=1)
        ]
        if not ranked:
            raise StaticExecutionCompileError(f"PHYSICAL_CANDIDATES_UNSATISFIABLE:{plan_node['node_id']}")
        physical_node = {
            **physical,
            "selected_operator_id": "",
            "execution_candidates": ranked,
            "execution_excluded": [],
        }
        physical_nodes.append(physical_node)

        requirement_checks = [
            str(requirement_by_id[req_id].get("check") or "")
            for req_id in plan_node["requirement_ids"]
            if req_id in requirement_by_id and requirement_by_id[req_id].get("check")
        ]
        output_verifiers = [
            str(verifier)
            for produced in plan_node["produces"]
            for verifier in produced.get("verifier_ids") or []
        ]
        check_ids = list(dict.fromkeys([
            str(plan_node["gate_requirement"]), *output_verifiers, *requirement_checks,
        ]))
        network = str(plan_node["operator_requirements"]["network"])
        scheduler_nodes.append({
            "id": plan_node["node_id"],
            "goal": plan_node["objective"],
            "logical_operator": plan_node["logical_operator"],
            "dispatch_task_type": capsule_node["dispatch_task_type"],
            "depends_on": list(plan_node["depends_on"]),
            "requirement_ids": list(plan_node["requirement_ids"]),
            "capability_capsule_id": capsule_id,
            "capsule_binding": {
                "capsule_ids": [capsule_id],
                "composition_id": None,
                "contract_sha256": _capsule_contract_hash(capsule_node),
            },
            "physical_candidates": [
                {"operator_id": item["operator_id"], "rank": item["rank"], "admission_state": "ELIGIBLE"}
                for item in ranked
            ],
            "artifact_contract": {
                "consumes": list(plan_node["consumes"]),
                "produces": [item["artifact_type"] for item in plan_node["produces"]],
            },
            "evaluation_binding": {
                "deterministic_gate_ids": [],
                "semantic_evaluator_ids": check_ids,
            },
            "resource_requirements": {
                "cpu_cores_min": 1,
                "memory_mb_min": 512,
                "gpu_required": "gpu" in plan_node["operator_requirements"]["capabilities"],
                "network": network,
            },
            "effects": _effects(plan_node),
            "priority": max(1, 100 - index),
            "failure_policy": {"max_attempts": 2, "on_exhausted": "fail_run"},
        })

    capsule_plan = {
        "schema_version": "solar.capsule_plan_ir.v1",
        "sprint_id": sid,
        "request_type": request_type,
        "lane_hint": "",
        "artifact_types": {
            "required_inputs": sorted({item for node in plan_ir["nodes"] for item in node["consumes"]}),
            "required_outputs": sorted({item["artifact_type"] for node in plan_ir["nodes"] for item in node["produces"]}),
        },
        "effect_union": {
            key: sorted({str(value) for node in capsule_nodes for value in (node.get("effect_union") or {}).get(key, [])})
            for key in ("read", "write", "execute", "network", "cost", "risk")
        },
        "proof_obligations": [item for node in capsule_nodes for item in node.get("proof_obligations") or []],
        "nodes": capsule_nodes,
        "unsatisfiable_nodes": [],
        "verdict": "pass",
    }
    capsule_path = output / "capsule_plan.json"
    _write_json(capsule_path, capsule_plan)
    _validate_schema(capsule_plan, "capsule-plan.v1.schema.json")

    physical_plan = {
        "schema_version": "solar.physical_plan_ir.v2",
        "sprint_id": sid,
        "capsule_plan_ref": {"sha256": _file_sha256(capsule_path)},
        "availability_boundary": {
            "mode": "static_admission_only",
            "runtime_selection_owner": "graph_scheduler",
        },
        "nodes": physical_nodes,
        "unsatisfiable_nodes": [],
        "verdict": "pass",
    }
    physical_path = output / "physical_plan.json"
    _write_json(physical_path, physical_plan)
    _validate_schema(physical_plan, "physical-plan.v2.schema.json")

    check_specs: dict[str, dict[str, Any]] = {}
    for plan_node in plan_ir["nodes"]:
        node_id = str(plan_node["node_id"])
        outputs = [item["artifact_type"] for item in plan_node["produces"]]
        gate_id = str(plan_node["gate_requirement"])
        check_specs.setdefault(gate_id, {
            "check_id": gate_id,
            "mode": "semantic",
            "applies_to": {"kind": "artifact_type", "artifact_types": outputs, "auto_apply": False},
            "decision": f"Evaluate the Planner gate requirement for node {node_id}.",
            "deterministic": None,
            "semantic": {"rubric": [str(plan_node["gate_requirement"])]},
        })
        for produced in plan_node["produces"]:
            artifact_type = str(produced["artifact_type"])
            for verifier_id in produced.get("verifier_ids") or []:
                check_specs.setdefault(str(verifier_id), {
                    "check_id": str(verifier_id),
                    "mode": "semantic",
                    "applies_to": {"kind": "artifact_type", "artifact_types": [artifact_type], "auto_apply": False},
                    "decision": f"Evaluate the declared verifier for {artifact_type}.",
                    "deterministic": None,
                    "semantic": {"rubric": [f"Verify {artifact_type} against {verifier_id}."]},
                })
        for requirement_id in plan_node["requirement_ids"]:
            requirement = requirement_by_id.get(requirement_id) or {}
            check_id = str(requirement.get("check") or "")
            if check_id:
                check_specs.setdefault(check_id, {
                    "check_id": check_id,
                    "mode": "semantic",
                    "applies_to": {"kind": "bound_output"},
                    "decision": f"Evaluate accepted RequirementIR obligation {requirement_id}.",
                    "deterministic": None,
                    "semantic": {"rubric": [str(requirement.get("statement") or requirement_id)]},
                })
    check_registry = {
        "schema_version": "solar.evaluation_check_registry.v1",
        "artifact_role": "runtime_registry",
        "registry_id": f"evaluation-check-registry-{plan_ir['plan_ir_id']}",
        "checks": list(check_specs.values()),
    }
    check_registry_path = output / "evaluation_check_registry.json"
    _write_json(check_registry_path, check_registry)
    _validate_schema(check_registry, "evaluation-check-registry.v1.schema.json")

    evaluation_nodes: list[dict[str, Any]] = []
    for plan_node in plan_ir["nodes"]:
        produced = [item["artifact_type"] for item in plan_node["produces"]]
        check_ids = scheduler_nodes[len(evaluation_nodes)]["evaluation_binding"]["semantic_evaluator_ids"]
        manifest = capsule_manifests[str(plan_node["node_id"])]
        criteria = [
            {
                "source_capsule_id": str(manifest.get("capability_capsule_id")),
                "kind": "invariant",
                "text": str(text),
                "field": None,
                "disposition": "semantic_review",
            }
            for text in (manifest.get("contract") or {}).get("invariants") or []
            if str(text).strip()
        ]
        evaluation_nodes.append({
            "node_id": plan_node["node_id"],
            "placement": "after_node_output",
            "requirement_ids": list(plan_node["requirement_ids"]),
            "produced_artifacts": produced,
            "checks": [
                {
                    "check_id": check_id,
                    "source": "requirement" if check_id in {
                        str(requirement_by_id[item].get("check") or "")
                        for item in plan_node["requirement_ids"] if item in requirement_by_id
                    } else "artifact_auto",
                    "mode": "semantic",
                    "applies_to_outputs": produced,
                    "decision": check_specs[check_id]["decision"],
                    "deterministic": None,
                    "semantic": check_specs[check_id]["semantic"],
                }
                for check_id in check_ids
            ],
            "capsule_contract_criteria": criteria,
            "gate_policy": {"kind": "llm_eval", "on_fail": "fail_node", "maximum_repairs": 1},
            "semantic_review": {
                "required": True,
                "evaluator_role": "evaluator",
                "criteria": list(dict.fromkeys([item["text"] for item in criteria] or [str(plan_node["gate_requirement"])])),
            },
        })

    plan_path = source_paths["plan"]
    requirement_path = source_paths["requirement"]
    evaluation_plan = {
        "schema_version": "solar.evaluation_plan.v1",
        "artifact_role": "runtime_artifact",
        "evaluation_plan_id": f"evaluation-plan-{plan_ir['plan_ir_id']}",
        "requirement_ir_ref": _artifact_ref(requirement_path, "requirement_ir_id", requirement_ir),
        "plan_ir_ref": _artifact_ref(plan_path, "plan_ir_id", plan_ir),
        "capsule_plan_ref": {"sha256": _file_sha256(capsule_path)},
        "task_graph_ref": {"plan_ir_id": plan_ir["plan_ir_id"], "sha256": _file_sha256(plan_path)},
        "registry_ref": {"registry_id": check_registry["registry_id"], "sha256": _file_sha256(check_registry_path)},
        "nodes": evaluation_nodes,
        "unresolved": [],
        "verdict": "pass",
    }
    evaluation_path = output / "evaluation_plan.json"
    _write_json(evaluation_path, evaluation_plan)
    _validate_schema(evaluation_plan, "evaluation-plan.v1.schema.json")

    capsule_validation = {
        "schema_version": "solar.capsule_binding_validation.v1",
        "artifact_role": "runtime_artifact",
        "validation_id": f"capsule-binding-validation-{plan_ir['plan_ir_id']}",
        "capsule_plan_ref": {"sha256": _file_sha256(capsule_path)},
        "status": "pass",
        "checks": [],
        "errors": [],
    }
    capsule_validation_path = output / "capsule_binding_validation.json"
    _write_json(capsule_validation_path, capsule_validation)
    _validate_schema(capsule_validation, "capsule-binding-validation.v1.schema.json")

    evaluation_validation = {
        "schema_version": "solar.evaluation_plan_validation.v1",
        "artifact_role": "runtime_artifact",
        "validation_id": f"evaluation-plan-validation-{plan_ir['plan_ir_id']}",
        "evaluation_plan_ref": {"evaluation_plan_id": evaluation_plan["evaluation_plan_id"], "sha256": _file_sha256(evaluation_path)},
        "registry_ref": {"registry_id": check_registry["registry_id"], "sha256": _file_sha256(check_registry_path)},
        "checks": [{"check_id": "all_checks_registered", "status": "pass"}],
        "errors": [],
        "status": "pass",
    }
    evaluation_validation_path = output / "evaluation_plan_validation.json"
    _write_json(evaluation_validation_path, evaluation_validation)
    _validate_schema(evaluation_validation, "evaluation-plan-validation.v1.schema.json")

    scheduler_value = {
        "schema_version": "solar.scheduler_input.v1",
        "artifact_role": "runtime_execution_authority",
        "scheduler_input_id": f"scheduler-input-{plan_ir['plan_ir_id']}",
        "sprint_id": sid,
        "planning_authority": "frozen_execution_plan_v1",
        "graph": {"graph_id": f"graph-{plan_ir['plan_ir_id']}", "nodes": scheduler_nodes},
    }
    scheduler_verdict = scheduler_input_runtime.validate(scheduler_value, require_runtime_authority=True)
    if not scheduler_verdict["ok"]:
        raise StaticExecutionCompileError("SCHEDULER_INPUT_INVALID:" + ";".join(scheduler_verdict["errors"]))
    scheduler_path = output / "scheduler_input.json"
    _write_json(scheduler_path, scheduler_value)

    refs = {
        "requirement_ir_ref": _artifact_ref(requirement_path, "requirement_ir_id", requirement_ir),
        "planning_decision_ref": _artifact_ref(source_paths["decision"], "planning_decision_id", bundle["decision"]),
        "plan_ir_ref": _artifact_ref(plan_path, "plan_ir_id", plan_ir),
        "capsule_plan_ref": {"sha256": _file_sha256(capsule_path)},
        "capsule_binding_validation_ref": {"sha256": _file_sha256(capsule_validation_path)},
        "physical_plan_ref": {"sha256": _file_sha256(physical_path)},
        "evaluation_check_registry_ref": {"registry_id": check_registry["registry_id"], "sha256": _file_sha256(check_registry_path)},
        "evaluation_plan_ref": {"evaluation_plan_id": evaluation_plan["evaluation_plan_id"], "sha256": _file_sha256(evaluation_path)},
        "evaluation_plan_validation_ref": {"sha256": _file_sha256(evaluation_validation_path)},
        "scheduler_input_ref": {"scheduler_input_id": scheduler_value["scheduler_input_id"], "sha256": _file_sha256(scheduler_path)},
    }
    run_contract = {
        "schema_version": "solar.run_contract.frozen.v2",
        "artifact_role": "runtime_artifact",
        "sprint_id": sid,
        "planning_authority": "frozen_execution_plan_v1",
        **refs,
        "plan_certificate": {
            "planner_validation": bundle["validation"]["status"],
            "planner_fidelity": bundle["fidelity"]["status"],
            "binding_trace": bundle["binding"]["verdict"],
            "static_compilation": "pass",
        },
        "contract_sha256": "0" * 64,
    }
    run_contract["contract_sha256"] = _canonical_sha256({
        key: value for key, value in run_contract.items() if key != "contract_sha256"
    })
    run_contract_path = output / "run_contract.frozen.json"
    _write_json(run_contract_path, run_contract)
    _validate_schema(run_contract, "run-contract-frozen.v2.schema.json")

    return {
        "capsule_plan": str(capsule_path),
        "capsule_binding_validation": str(capsule_validation_path),
        "physical_plan": str(physical_path),
        "evaluation_check_registry": str(check_registry_path),
        "evaluation_plan": str(evaluation_path),
        "evaluation_plan_validation": str(evaluation_validation_path),
        "scheduler_input": str(scheduler_path),
        "run_contract": str(run_contract_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="static_execution_compiler.py")
    parser.add_argument("--requirement-ir", required=True)
    parser.add_argument("--planning-decision", required=True)
    parser.add_argument("--plan-ir", required=True)
    parser.add_argument("--plan-validation", required=True)
    parser.add_argument("--plan-fidelity", required=True)
    parser.add_argument("--binding-trace", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sprint-id", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = compile_bundle(
            requirement_ir_path=args.requirement_ir,
            planning_decision_path=args.planning_decision,
            plan_ir_path=args.plan_ir,
            plan_validation_path=args.plan_validation,
            plan_fidelity_path=args.plan_fidelity,
            binding_trace_path=args.binding_trace,
            output_dir=args.output_dir,
            sprint_id=args.sprint_id,
        )
    except StaticExecutionCompileError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    payload = {"ok": True, "artifacts": result}
    print(json.dumps(payload, ensure_ascii=True if args.json else False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
