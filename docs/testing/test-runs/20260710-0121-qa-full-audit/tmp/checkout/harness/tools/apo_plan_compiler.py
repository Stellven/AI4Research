"""apo_plan_compiler.py — explicit APO compile stages.

LogicalPlan -> CapsulePlan -> PhysicalPlan
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from capability_capsules import (
    CAPSULE_REGISTRY_PATH,
    classify_task_goal,
    expand_logical_workflow,
    resolve_skill_plan,
    resolve_mcp_plan,
    default_capability_plan_for_logical_operator,
    get_registry_entry,
    load_capability_capsule_manifest,
    query_capability_capsules,
)

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
LOGICAL_OPERATORS_PATH = HARNESS_DIR / "config" / "logical-operators.json"
PHYSICAL_OPERATORS_PATH = HARNESS_DIR / "config" / "physical-operators.json"
ARTIFACT_ADAPTER_REGISTRY_PATH = HARNESS_DIR / "config" / "artifact-adapter-capsules.registry.yaml"
EFFECT_KEYS = ("read", "write", "execute", "network", "cost", "risk")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return str(path)


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(data or {}) if isinstance(data, dict) else {}


def _logical_operator_def(logical_operator: str, path: Optional[Path] = None) -> Dict[str, Any]:
    payload = _load_json(path or LOGICAL_OPERATORS_PATH)
    return dict((payload.get("logical_operators") or {}).get(logical_operator, {}))


def logical_role_for_operator(logical_operator: str, path: Optional[Path] = None) -> str:
    entry = _logical_operator_def(logical_operator, path=path)
    return str(entry.get("primary_role") or "builder")


def _capsule_manifest(capsule_id: str, registry_path: Optional[Path] = None) -> Dict[str, Any]:
    entry = get_registry_entry(capsule_id, path=registry_path or CAPSULE_REGISTRY_PATH, include_nonstable=True)
    if entry is None:
        return {}
    return load_capability_capsule_manifest(Path(entry.manifest_path))


def _dedupe(values: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _resolve_manifest_path(base: Path, manifest_path: str) -> Path:
    path = Path(str(manifest_path or ""))
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _artifact_type_from_contract_item(item: Any) -> str:
    if isinstance(item, dict):
        art_type = str(item.get("type") or "").strip()
        if art_type:
            return art_type
        name = str(item.get("name") or "").strip()
        if name:
            return f"artifact.{name}"
    if isinstance(item, str) and item.strip():
        return item.strip()
    return ""


def _artifact_type_from_composition_item(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("type") or "").strip()
    if isinstance(item, str):
        return item.strip()
    return ""


def _contract_artifact_types(contract: Dict[str, Any]) -> Dict[str, List[str]]:
    inputs = contract.get("inputs") if isinstance(contract.get("inputs"), dict) else {}
    outputs = contract.get("outputs") if isinstance(contract.get("outputs"), dict) else {}
    required_inputs = _dedupe([_artifact_type_from_contract_item(item) for item in inputs.get("required", []) or []])
    optional_inputs = _dedupe([_artifact_type_from_contract_item(item) for item in inputs.get("optional", []) or []])
    required_outputs = _dedupe([_artifact_type_from_contract_item(item) for item in outputs.get("required", []) or []])
    optional_outputs = _dedupe([_artifact_type_from_contract_item(item) for item in outputs.get("optional", []) or []])
    return {
        "required_inputs": required_inputs,
        "optional_inputs": optional_inputs,
        "required_outputs": required_outputs,
        "optional_outputs": optional_outputs,
    }


def _composition_artifact_types(composition: Dict[str, Any]) -> Dict[str, List[str]]:
    consumes = _dedupe([_artifact_type_from_composition_item(item) for item in composition.get("consumes", []) or []])
    produces = _dedupe([_artifact_type_from_composition_item(item) for item in composition.get("produces", []) or []])
    return {"consumes": consumes, "produces": produces}


def _effect_profile(effects: Dict[str, Any]) -> Dict[str, List[str]]:
    return {
        key: _dedupe([str(item) for item in (effects.get(key) or [])])
        for key in EFFECT_KEYS
    }


def _union_effect_profiles(profiles: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {key: [] for key in EFFECT_KEYS}
    for profile in profiles:
        for key in EFFECT_KEYS:
            merged[key].extend(str(item) for item in (profile.get(key) or []))
    return {key: _dedupe(values) for key, values in merged.items()}


def _proof_obligations(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    verification = manifest.get("verification") if isinstance(manifest.get("verification"), dict) else {}
    contract = manifest.get("contract") if isinstance(manifest.get("contract"), dict) else {}
    capability_capsule_id = str(manifest.get("capability_capsule_id") or "")
    obligations: List[Dict[str, Any]] = []
    for check in verification.get("self_check", []) or []:
        obligations.append(
            {
                "kind": "self_check",
                "source_capsule_id": capability_capsule_id,
                "requirement": str(check),
            }
        )
    for condition in verification.get("pass_conditions", []) or []:
        obligations.append(
            {
                "kind": "pass_condition",
                "source_capsule_id": capability_capsule_id,
                "requirement": str(condition),
            }
        )
    for item in contract.get("postconditions", []) or []:
        if isinstance(item, dict):
            requirement = str(item.get("check") or item.get("field") or json.dumps(item, ensure_ascii=False))
        else:
            requirement = str(item)
        obligation = {
            "kind": "postcondition",
            "source_capsule_id": capability_capsule_id,
            "requirement": requirement,
        }
        if isinstance(item, dict):
            obligation["check"] = item.get("check")
            obligation["field"] = item.get("field")
            if "values" in item:
                obligation["values"] = list(item.get("values") or [])
        obligations.append(obligation)
    external = verification.get("external_verifier") if isinstance(verification.get("external_verifier"), dict) else {}
    if external.get("required"):
        obligations.append(
            {
                "kind": "external_verifier",
                "source_capsule_id": capability_capsule_id,
                "requirement": "external_verifier.required",
                "preferred_capsules": list(external.get("preferred_capsules", []) or []),
            }
        )
    return obligations


def _initial_node_artifacts(node: Dict[str, Any], request_type: str = "") -> List[str]:
    available = [
        "artifact.task_graph_node",
        "artifact.request_context",
    ]
    task_type = str(node.get("type") or request_type or "").strip().lower()
    if task_type in {"planning", "implementation", "debugging", "refactor", "verification", "review", "requirements", "research"}:
        available.append("artifact.requirement_ir")
    if node.get("requirement_ids"):
        available.append("artifact.requirement_ir")
    if node.get("design_md") or node.get("design_path"):
        available.append("artifact.design_md")
    if node.get("eval_json"):
        available.append("artifact.eval_json")
    return _dedupe(available)


def _stage_outputs(stage: Dict[str, Any]) -> List[str]:
    artifact_types = stage.get("artifact_types") if isinstance(stage.get("artifact_types"), dict) else {}
    outputs = list(artifact_types.get("produces", []) or [])
    outputs.extend(list(artifact_types.get("required_outputs", []) or []))
    outputs.extend(list(artifact_types.get("optional_outputs", []) or []))
    return _dedupe([str(item) for item in outputs])


def _stage_required_inputs(stage: Dict[str, Any]) -> List[str]:
    artifact_types = stage.get("artifact_types") if isinstance(stage.get("artifact_types"), dict) else {}
    required = list(artifact_types.get("required_inputs", []) or [])
    return _dedupe([str(item) for item in required])


def _rewrite_adapter_stages(
    stages: List[Dict[str, Any]],
    *,
    node: Dict[str, Any],
    request_type: str = "",
    adapter_registry_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    adapter_registry = _load_adapter_registry(adapter_registry_path or ARTIFACT_ADAPTER_REGISTRY_PATH)
    available = set(_initial_node_artifacts(node, request_type=request_type))
    rewritten: List[Dict[str, Any]] = []
    adapter_index = 0
    for stage in stages:
        required_inputs = _stage_required_inputs(stage)
        missing = [item for item in required_inputs if item not in available]
        if missing and str(stage.get("stage_kind") or "") in {"capability", "verifier"}:
            remaining = list(missing)
            while remaining:
                adapter_index += 1
                entry = _select_adapter_entry(
                    available_before=sorted(available),
                    missing_required_inputs=remaining,
                    registry=adapter_registry,
                )
                target_outputs = list(entry.get("matched_targets") or []) or [str(remaining[0])]
                source_inputs = list(entry.get("matched_sources") or []) or sorted(available)
                adapter_capsule_id = str(entry.get("adapter_capsule_id") or "adapter.artifact-type-bridge")
                manifest = _load_adapter_manifest(entry)
                bundle = _capsule_type_bundle(manifest) if manifest else {
                    "artifact_types": {},
                    "effect_profile": {key: [] for key in EFFECT_KEYS},
                    "proof_obligations": [],
                }
                adapter_stage = _make_stage(
                    stage_id=f"{node.get('id')}:adapter:{adapter_index}",
                    stage_kind="adapter",
                    capsule_id=adapter_capsule_id,
                    dispatch_mode="attached",
                    reason=str(entry.get("reason") or "type_mismatch_bridge"),
                    role=str(stage.get("role") or ""),
                    task_type=str(stage.get("task_type") or ""),
                    artifact_types={
                        "required_inputs": list(source_inputs),
                        "optional_inputs": [],
                        "required_outputs": list(target_outputs),
                        "optional_outputs": [],
                        "consumes": list(source_inputs),
                        "produces": list(target_outputs),
                    },
                    effect_profile=dict(bundle.get("effect_profile") or {key: [] for key in EFFECT_KEYS}),
                    proof_obligations=list(bundle.get("proof_obligations") or []) + [
                        {
                            "kind": "adapter_contract",
                            "source_capsule_id": adapter_capsule_id,
                            "requirement": "type_mismatch_bridge",
                            "target_stage_id": stage.get("stage_id"),
                            "missing_required_inputs": list(target_outputs),
                            "source_artifacts": list(source_inputs),
                        }
                    ],
                )
                adapter_stage["adapter_rule"] = {
                    "rule": "type_mismatch_to_adapter_capsule",
                    "adapter_capsule_id": adapter_capsule_id,
                    "target_stage_id": stage.get("stage_id"),
                    "missing_required_inputs": list(target_outputs),
                    "available_before": sorted(available),
                    "registry_match": {
                        "source_artifacts": list(entry.get("source_artifacts") or []),
                        "target_artifacts": list(entry.get("target_artifacts") or []),
                    },
                }
                rewritten.append(adapter_stage)
                available.update(target_outputs)
                remaining = [item for item in remaining if item not in set(target_outputs)]
        rewritten.append(stage)
        available.update(_stage_outputs(stage))
    return rewritten


def _load_adapter_registry(path: Path) -> Dict[str, Any]:
    payload = _load_yaml(path)
    entries: List[Dict[str, Any]] = []
    for item in list(payload.get("adapters") or []):
        if not isinstance(item, dict):
            continue
        resolved = dict(item)
        resolved["source_artifacts"] = _dedupe([str(v) for v in list(item.get("source_artifacts") or [])])
        resolved["target_artifacts"] = _dedupe([str(v) for v in list(item.get("target_artifacts") or [])])
        manifest_path = str(item.get("manifest_path") or "")
        resolved["manifest_path"] = str(_resolve_manifest_path(path.parent, manifest_path)) if manifest_path else ""
        entries.append(resolved)
    return {
        "version": payload.get("version", 1),
        "default_adapter_capsule_id": str(payload.get("default_adapter_capsule_id") or "adapter.artifact-type-bridge"),
        "entries": entries,
    }


def _load_adapter_manifest(entry: Dict[str, Any]) -> Dict[str, Any]:
    manifest_path = str(entry.get("manifest_path") or "")
    if not manifest_path:
        return {}
    try:
        return load_capability_capsule_manifest(Path(manifest_path))
    except Exception:
        return {}


def _select_adapter_entry(
    *,
    available_before: List[str],
    missing_required_inputs: List[str],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    available = set(str(item) for item in available_before)
    missing = set(str(item) for item in missing_required_inputs)
    ranked: List[Dict[str, Any]] = []
    for entry in list(registry.get("entries") or []):
        if str(entry.get("status") or "stable") == "revoked":
            continue
        sources = [str(item) for item in list(entry.get("source_artifacts") or [])]
        targets = [str(item) for item in list(entry.get("target_artifacts") or [])]
        matched_targets = [item for item in targets if item in missing]
        if not matched_targets:
            continue
        if sources and not set(sources).issubset(available):
            continue
        score = (len(matched_targets) * 10) + len(sources)
        ranked.append(
            {
                **entry,
                "matched_targets": matched_targets,
                "matched_sources": sources if sources else sorted(available),
                "_score": score,
            }
        )
    if ranked:
        ranked.sort(key=lambda item: (-int(item.get("_score", 0)), str(item.get("adapter_capsule_id") or "")))
        return ranked[0]

    fallback_id = str(registry.get("default_adapter_capsule_id") or "adapter.artifact-type-bridge")
    fallback = next(
        (entry for entry in list(registry.get("entries") or []) if str(entry.get("adapter_capsule_id") or "") == fallback_id),
        {},
    )
    return {
        **fallback,
        "adapter_capsule_id": fallback_id,
        "matched_targets": [str(missing_required_inputs[0])],
        "matched_sources": sorted(available),
    }


def _capsule_type_bundle(manifest: Dict[str, Any]) -> Dict[str, Any]:
    contract = manifest.get("contract") if isinstance(manifest.get("contract"), dict) else {}
    composition = manifest.get("composition") if isinstance(manifest.get("composition"), dict) else {}
    effects = manifest.get("effects") if isinstance(manifest.get("effects"), dict) else {}
    contract_types = _contract_artifact_types(contract)
    composition_types = _composition_artifact_types(composition)
    return {
        "artifact_types": {
            **contract_types,
            **composition_types,
        },
        "effect_profile": _effect_profile(effects),
        "proof_obligations": _proof_obligations(manifest),
    }


def _make_stage(
    *,
    stage_id: str,
    stage_kind: str,
    capsule_id: str,
    dispatch_mode: str,
    reason: str,
    role: str = "",
    task_type: str = "",
    operator_constraints: Optional[Dict[str, Any]] = None,
    artifact_types: Optional[Dict[str, Any]] = None,
    effect_profile: Optional[Dict[str, Any]] = None,
    proof_obligations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "stage_id": stage_id,
        "stage_kind": stage_kind,
        "capability_capsule_id": capsule_id,
        "dispatch_mode": dispatch_mode,
        "role": role,
        "task_type": task_type,
        "reason": reason,
        "operator_constraints": dict(operator_constraints or {}),
        "artifact_types": dict(artifact_types or {}),
        "effect_profile": dict(effect_profile or {}),
        "proof_obligations": list(proof_obligations or []),
    }


def build_capsule_plan_node(
    node: Dict[str, Any],
    *,
    request_type: str = "",
    lane_hint: str = "",
    registry_path: Optional[Path] = None,
    goal_text: str = "",
) -> Dict[str, Any]:
    logical_operator = str(node.get("logical_operator") or "")
    adapter_registry_path = (
        Path(registry_path).parent / "artifact-adapter-capsules.registry.yaml"
        if registry_path is not None
        else ARTIFACT_ADAPTER_REGISTRY_PATH
    )
    base_plan = dict(node.get("capsule_plan") or {})
    if not base_plan:
        base_plan = default_capability_plan_for_logical_operator(
            logical_operator,
            request_type=request_type,
            lane_hint=lane_hint,
            node=node,
            registry_path=registry_path or CAPSULE_REGISTRY_PATH,
            goal_text=goal_text or str(node.get("goal") or ""),
        )
    if not base_plan:
        return {
            "schema_version": "solar.capsule_plan_node.v1",
            "node_id": str(node.get("id") or ""),
            "logical_operator": logical_operator,
            "request_type": request_type,
            "lane_hint": lane_hint,
            "selected": False,
            "stages": [],
        }

    capsule_id = str(base_plan.get("capability_capsule_id") or "")
    manifest = _capsule_manifest(capsule_id, registry_path=registry_path)
    bindings = manifest.get("bindings", {})
    verification = manifest.get("verification", {})
    op_constraints = dict(base_plan.get("operator_constraints") or manifest.get("operator_compatibility") or {})
    task_type = str(base_plan.get("dispatch_task_type") or node.get("dispatch_task_type") or node.get("type") or "")
    role = logical_role_for_operator(logical_operator)

    stages: List[Dict[str, Any]] = []
    for index, guard_id in enumerate(bindings.get("required_guard_capsules", []) or [], start=1):
        guard_manifest = _capsule_manifest(str(guard_id), registry_path=registry_path)
        guard_bundle = _capsule_type_bundle(guard_manifest)
        stages.append(
            _make_stage(
                stage_id=f"{node.get('id')}:guard:{index}",
                stage_kind="guard",
                capsule_id=str(guard_id),
                dispatch_mode="attached",
                reason="required_guard_capsules",
                role=role,
                task_type=task_type,
                operator_constraints=guard_manifest.get("operator_compatibility", {}),
                artifact_types=guard_bundle["artifact_types"],
                effect_profile=guard_bundle["effect_profile"],
                proof_obligations=guard_bundle["proof_obligations"],
            )
        )

    for index, resource_id in enumerate(bindings.get("required_resource_capsules", []) or [], start=1):
        resource_manifest = _capsule_manifest(str(resource_id), registry_path=registry_path)
        resource_bundle = _capsule_type_bundle(resource_manifest)
        stages.append(
            _make_stage(
                stage_id=f"{node.get('id')}:resource:{index}",
                stage_kind="resource",
                capsule_id=str(resource_id),
                dispatch_mode="attached",
                reason="required_resource_capsules",
                role=role,
                task_type=task_type,
                operator_constraints=resource_manifest.get("operator_compatibility", {}),
                artifact_types=resource_bundle["artifact_types"],
                effect_profile=resource_bundle["effect_profile"],
                proof_obligations=resource_bundle["proof_obligations"],
            )
        )

    capability_bundle = _capsule_type_bundle(manifest)
    stages.append(
        _make_stage(
            stage_id=f"{node.get('id')}:capability",
            stage_kind="capability",
            capsule_id=capsule_id,
            dispatch_mode="execute",
            reason=str(base_plan.get("selection_mode") or "logical_operator_default"),
            role=role,
            task_type=task_type,
            operator_constraints=op_constraints,
            artifact_types=capability_bundle["artifact_types"],
            effect_profile=capability_bundle["effect_profile"],
            proof_obligations=capability_bundle["proof_obligations"],
        )
    )

    preferred_verifiers = list((verification.get("external_verifier") or {}).get("preferred_capsules", []) or [])
    if bool((verification.get("external_verifier") or {}).get("required")):
        for index, verifier_id in enumerate(preferred_verifiers, start=1):
            if str(verifier_id) == capsule_id:
                continue
            verifier_manifest = _capsule_manifest(str(verifier_id), registry_path=registry_path)
            verifier_bundle = _capsule_type_bundle(verifier_manifest)
            verifier_kind = str(verifier_manifest.get("capsule_kind") or "capability")
            dispatch_mode = "execute" if verifier_kind == "capability" else "attached"
            verifier_role = logical_role_for_operator("Verifier") if dispatch_mode == "execute" else role
            verifier_task_type = "verification" if dispatch_mode == "execute" else task_type
            stages.append(
                _make_stage(
                    stage_id=f"{node.get('id')}:verifier:{index}",
                    stage_kind="verifier",
                    capsule_id=str(verifier_id),
                    dispatch_mode=dispatch_mode,
                    reason="external_verifier.required",
                    role=verifier_role,
                    task_type=verifier_task_type,
                    operator_constraints=verifier_manifest.get("operator_compatibility", {}),
                    artifact_types=verifier_bundle["artifact_types"],
                    effect_profile=verifier_bundle["effect_profile"],
                    proof_obligations=verifier_bundle["proof_obligations"],
                )
            )

    stages = _rewrite_adapter_stages(
        stages,
        node=node,
        request_type=request_type,
        adapter_registry_path=adapter_registry_path,
    )

    effect_union = _union_effect_profiles([dict(stage.get("effect_profile") or {}) for stage in stages])
    proof_obligations = [
        obligation
        for stage in stages
        for obligation in list(stage.get("proof_obligations") or [])
        if isinstance(obligation, dict)
    ]
    node_artifact_types = {
        "required_inputs": _dedupe([
            value
            for stage in stages
            for value in list((stage.get("artifact_types") or {}).get("required_inputs", []) or [])
        ]),
        "optional_inputs": _dedupe([
            value
            for stage in stages
            for value in list((stage.get("artifact_types") or {}).get("optional_inputs", []) or [])
        ]),
        "required_outputs": _dedupe([
            value
            for stage in stages
            for value in list((stage.get("artifact_types") or {}).get("required_outputs", []) or [])
        ]),
        "optional_outputs": _dedupe([
            value
            for stage in stages
            for value in list((stage.get("artifact_types") or {}).get("optional_outputs", []) or [])
        ]),
        "consumes": _dedupe([
            value
            for stage in stages
            for value in list((stage.get("artifact_types") or {}).get("consumes", []) or [])
        ]),
        "produces": _dedupe([
            value
            for stage in stages
            for value in list((stage.get("artifact_types") or {}).get("produces", []) or [])
        ]),
    }

    return {
        "schema_version": "solar.capsule_plan_node.v1",
        "node_id": str(node.get("id") or ""),
        "logical_operator": logical_operator,
        "request_type": request_type,
        "lane_hint": lane_hint,
        "goal": str(node.get("goal") or ""),
        "selected": True,
        "capability_capsule_id": capsule_id,
        "dispatch_task_type": task_type,
        "role": role,
        "required_guard_capsules": list(bindings.get("required_guard_capsules", []) or []),
        "required_resource_capsules": list(bindings.get("required_resource_capsules", []) or []),
        "selected_skills": list(base_plan.get("selected_skills") or bindings.get("skills", {}).get("required", []) or []),
        "artifact_types": node_artifact_types,
        "effect_union": effect_union,
        "proof_obligations": proof_obligations,
        "stages": stages,
    }


def build_capsule_plan_ir(
    task_graph: Dict[str, Any],
    *,
    request_type: str = "",
    lane_hint: str = "",
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    nodes = [
        build_capsule_plan_node(
            dict(node),
            request_type=request_type,
            lane_hint=lane_hint,
            registry_path=registry_path,
        )
        for node in task_graph.get("nodes", []) or []
    ]
    return {
        "schema_version": "solar.capsule_plan_ir.v1",
        "sprint_id": task_graph.get("sprint_id", "N/A"),
        "request_type": request_type,
        "lane_hint": lane_hint,
        "dag_variant": task_graph.get("dag_variant"),
        "artifact_types": {
            "required_inputs": _dedupe([
                value for node in nodes for value in list((node.get("artifact_types") or {}).get("required_inputs", []) or [])
            ]),
            "required_outputs": _dedupe([
                value for node in nodes for value in list((node.get("artifact_types") or {}).get("required_outputs", []) or [])
            ]),
            "consumes": _dedupe([
                value for node in nodes for value in list((node.get("artifact_types") or {}).get("consumes", []) or [])
            ]),
            "produces": _dedupe([
                value for node in nodes for value in list((node.get("artifact_types") or {}).get("produces", []) or [])
            ]),
        },
        "effect_union": _union_effect_profiles([dict(node.get("effect_union") or {}) for node in nodes]),
        "proof_obligations": [
            obligation
            for node in nodes
            for obligation in list(node.get("proof_obligations") or [])
            if isinstance(obligation, dict)
        ],
        "nodes": nodes,
    }


def _is_dispatchable_runtime(operator_id: str) -> bool:
    try:
        from operator_runtime import get_operator_runtime_state
    except Exception:
        return True
    return get_operator_runtime_state(operator_id) == "idle"


def enumerate_physical_candidates(
    *,
    role: str,
    task_type: str = "",
    logical_operator: str = "",
    operator_constraints: Optional[Dict[str, Any]] = None,
    prefer_operator: str = "",
    require_dispatchable: bool = False,
    operators_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    registry = _load_json(operators_path or PHYSICAL_OPERATORS_PATH)
    operators = registry.get("operators", {}) or {}
    constraints = dict(operator_constraints or {})
    preferred_ops = set(constraints.get("preferred", []) or [])
    forbidden_ops = set(constraints.get("forbidden", []) or [])
    default_profile = str(constraints.get("default_operator_profile") or "")
    candidates: List[Dict[str, Any]] = []

    for op_id, spec in operators.items():
        if prefer_operator and op_id != prefer_operator:
            continue
        if op_id in forbidden_ops:
            continue
        enabled = bool(spec.get("enabled", False))
        available = bool(spec.get("available", False))
        if not enabled or not available:
            continue
        if require_dispatchable and not _is_dispatchable_runtime(op_id):
            continue
        roles = [str(r).lower() for r in spec.get("roles", [spec.get("role", "")])]
        if role and role.lower() not in roles:
            continue

        priority = 0
        kind = str(spec.get("launch_cmd_kind", "") or spec.get("backend", ""))
        if "print_once" in kind or "print" in kind:
            priority += 10
        elif "command" in kind:
            priority += 5
        else:
            priority += 1

        task_classes = [str(t).lower() for t in spec.get("task_classes", [])]
        if task_type and any(task_type.lower() in tc for tc in task_classes):
            priority += 3
        preferred_for = [str(item).lower() for item in spec.get("preferred_for", [])]
        if logical_operator and logical_operator.lower() in preferred_for:
            priority += 2
        if role.lower() in preferred_for:
            priority += 2
        if preferred_ops and op_id in preferred_ops:
            priority += 20
        if default_profile and (op_id == default_profile or str(spec.get("profile", "")) == default_profile):
            priority += 8
        candidates.append(
            {
                "operator_id": op_id,
                "priority": priority,
                "role": role,
                "task_type": task_type,
                "profile": spec.get("profile"),
                "model": spec.get("model"),
                "preferred_for": spec.get("preferred_for", []),
            }
        )

    candidates.sort(key=lambda item: (-int(item["priority"]), str(item["operator_id"])))
    return candidates


def build_physical_plan_for_capsule_node(
    capsule_plan_node: Dict[str, Any],
    *,
    prefer_operator: str = "",
    require_dispatchable: bool = False,
    operators_path: Optional[Path] = None,
) -> Dict[str, Any]:
    execute_stage = next((stage for stage in capsule_plan_node.get("stages", []) if stage.get("stage_kind") == "capability"), None)
    verifier_stages = [
        stage for stage in capsule_plan_node.get("stages", [])
        if stage.get("stage_kind") == "verifier" and stage.get("dispatch_mode") == "execute"
    ]
    attached_stages = [
        stage for stage in capsule_plan_node.get("stages", [])
        if stage.get("dispatch_mode") != "execute"
    ]

    selected_operator_id = ""
    execution_candidates: List[Dict[str, Any]] = []
    if execute_stage:
        execution_candidates = enumerate_physical_candidates(
            role=str(execute_stage.get("role") or capsule_plan_node.get("role") or ""),
            task_type=str(execute_stage.get("task_type") or capsule_plan_node.get("dispatch_task_type") or ""),
            logical_operator=str(capsule_plan_node.get("logical_operator") or ""),
            operator_constraints=dict(execute_stage.get("operator_constraints") or {}),
            prefer_operator=prefer_operator,
            require_dispatchable=require_dispatchable,
            operators_path=operators_path,
        )
        if execution_candidates:
            selected_operator_id = str(execution_candidates[0]["operator_id"])

    verifier_plans = []
    for stage in verifier_stages:
        candidates = enumerate_physical_candidates(
            role=str(stage.get("role") or "evaluator"),
            task_type=str(stage.get("task_type") or "verification"),
            logical_operator="Verifier",
            operator_constraints=dict(stage.get("operator_constraints") or {}),
            require_dispatchable=require_dispatchable,
            operators_path=operators_path,
        )
        verifier_plans.append(
            {
                "stage_id": stage.get("stage_id"),
                "capability_capsule_id": stage.get("capability_capsule_id"),
                "candidates": candidates,
                "selected_operator_id": str(candidates[0]["operator_id"]) if candidates else "",
            }
        )

    return {
        "schema_version": "solar.physical_plan_node.v1",
        "node_id": capsule_plan_node.get("node_id"),
        "logical_operator": capsule_plan_node.get("logical_operator"),
        "capability_capsule_id": capsule_plan_node.get("capability_capsule_id"),
        "dispatch_task_type": capsule_plan_node.get("dispatch_task_type"),
        "artifact_types": dict(capsule_plan_node.get("artifact_types") or {}),
        "effect_union": dict(capsule_plan_node.get("effect_union") or {}),
        "proof_obligations": list(capsule_plan_node.get("proof_obligations") or []),
        "selected_operator_id": selected_operator_id,
        "execution_candidates": execution_candidates,
        "attached_capsules": attached_stages,
        "verifier_plans": verifier_plans,
    }


def execution_plan_artifact_paths(
    sprint_id: str,
    node_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Dict[str, str]:
    root = Path(base_dir or (HARNESS_DIR / "sprints"))
    stem = f"{sprint_id}.{node_id}"
    return {
        "capsule_plan_ir_path": str(root / f"{stem}-capsule-plan.json"),
        "physical_plan_ir_path": str(root / f"{stem}-physical-plan.json"),
    }


def materialize_execution_plan_artifacts(
    sprint_id: str,
    node_id: str,
    *,
    capsule_plan: Dict[str, Any],
    physical_plan: Dict[str, Any],
    base_dir: Optional[Path] = None,
) -> Dict[str, str]:
    paths = execution_plan_artifact_paths(sprint_id, node_id, base_dir=base_dir)
    capsule_path = Path(paths["capsule_plan_ir_path"])
    physical_path = Path(paths["physical_plan_ir_path"])
    _write_json(capsule_path, capsule_plan)
    _write_json(physical_path, physical_plan)
    return paths


def compile_execution_plan_for_node(
    node: Dict[str, Any],
    *,
    request_type: str = "",
    lane_hint: str = "",
    prefer_operator: str = "",
    registry_path: Optional[Path] = None,
    require_dispatchable: bool = False,
    operators_path: Optional[Path] = None,
) -> Dict[str, Any]:
    goal_text = str(node.get("goal") or request_type or "")
    task_classification = classify_task_goal(goal_text)
    logical_workflow = expand_logical_workflow(task_classification)
    capsule_plan = build_capsule_plan_node(
        node,
        request_type=request_type,
        lane_hint=lane_hint,
        registry_path=registry_path,
        goal_text=goal_text,
    )
    physical_plan = build_physical_plan_for_capsule_node(
        capsule_plan,
        prefer_operator=prefer_operator,
        require_dispatchable=require_dispatchable,
        operators_path=operators_path,
    )
    selected_capsule_id = capsule_plan.get("capability_capsule_id") or capsule_plan.get("capsule_id")
    capsule_manifest = None
    if selected_capsule_id:
        try:
            entry = get_registry_entry(selected_capsule_id, path=registry_path, include_nonstable=True)
            if entry:
                capsule_manifest = load_capability_capsule_manifest(Path(entry.manifest_path))
        except Exception:
            pass
    skill_plan = resolve_skill_plan(logical_workflow, capsule_manifest)
    mcp_plan = resolve_mcp_plan(skill_plan, capsule_manifest)
    all_capsule_candidates = []
    if task_classification.get("primary_class"):
        signals = [s["signal"] for s in task_classification.get("signals_detected", []) if s.get("weight", 0) > 0]
        raw_candidates = query_capability_capsules(
            task_type=task_classification["primary_class"],
            signals=signals,
            capsule_kind="capability",
            registry_path=registry_path,
        )
        for cand in raw_candidates:
            cid = cand["entry"]["capability_capsule_id"]
            is_selected = cid == selected_capsule_id
            all_capsule_candidates.append({
                "capsule_id": cid,
                "score": cand["score"],
                "selected": is_selected,
                "selection_rationale": f"Score {cand['score']}" if is_selected else None,
                "rejection_rationale": f"Score {cand['score']} — outscored" if not is_selected else None,
            })
    fallback_used = capsule_plan.get("fallback_used", False)
    fallback_reason = capsule_plan.get("fallback_reason")
    evidence_policy: Dict[str, Any] = {
        "proof_obligations": [],
        "ledger_event_names": [],
        "verification_commands": [],
    }
    if capsule_manifest:
        pass_conditions = capsule_manifest.get("verification", {}).get("pass_conditions", [])
        evidence_policy["proof_obligations"] = [str(c) for c in pass_conditions]
        evidence_policy["ledger_event_names"] = [
            f"apo.{task_classification.get('primary_class', 'unknown')}.capsule_selected",
            f"apo.node.{node.get('id', 'unknown')}.plan_compiled",
        ]
    return {
        "logical_plan_node": {
            "node_id": node.get("id"),
            "logical_operator": node.get("logical_operator"),
            "goal": node.get("goal"),
            "depends_on": list(node.get("depends_on", []) or []),
        },
        "task_classification": task_classification,
        "logical_workflow": logical_workflow,
        "skill_plan": skill_plan,
        "mcp_plan": mcp_plan,
        "capsule_plan": capsule_plan,
        "capsule_plan_artifact": {
            "selected_capsule_id": selected_capsule_id,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "candidates": all_capsule_candidates,
            "rationale": (
                f"Goal-driven (class={task_classification.get('primary_class')}, "
                f"confidence={task_classification.get('confidence')})"
                if not fallback_used else f"Static fallback. Reason: {fallback_reason}"
            ),
        },
        "physical_plan": physical_plan,
        "evidence_policy": evidence_policy,
        "selection_rationale": {
            "classification_confidence": task_classification.get("confidence"),
            "primary_class": task_classification.get("primary_class"),
            "capsule_selected": selected_capsule_id,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
        },
    }
