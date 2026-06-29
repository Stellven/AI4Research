#!/usr/bin/env python3
"""capability_capsules.py — Capability Capsule registry, compatibility loader, and runtime gate.

Capability Capsules are distinct from the existing State Capsule
(`schemas/capsule-schema.yaml`). They bundle capability intent, contract,
composition, effects, bindings, verification, and operator compatibility into
one governance unit that can be selected and resolved before dispatch.

This module keeps one migration cycle of compatibility with the older
Execution Capsule / ECapsule naming. New manifests must use
``capability_capsule_id``. Legacy payloads that only carry
``execution_capsule_id`` are normalized into the new shape.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
CAPSULE_REGISTRY_PATH = HARNESS_DIR / "config" / "capability-capsules.registry.yaml"
CAPSULE_SCHEMA_PATH = HARNESS_DIR / "schemas" / "draft" / "capability-capsule.v1.draft.json"

HIGH_RISK_EFFECTS = {"secrets_access", "destructive_shell", "git_push"}
UNDERSTAND_ANYTHING_SIGNAL_TOKENS = {
    "understand-anything",
    "knowledge graph",
    "knowledge-graph",
    "codebase index",
    "codebase-index",
    "codebase indexing",
    "codebase-indexing",
    "code understanding",
    "code-understanding",
    "repository understanding",
    "repo understanding",
    "repo map",
    "architecture map",
    "onboarding",
}

DEFAULT_CAPSULE_BY_LOGICAL_OPERATOR = {
    "DeepArchitect": "cap.requirement-compiler-planner",
    "ImplementationWorker": "cap.requirement-compiler-implementation",
    "PatchWorker": "cap.requirement-compiler-implementation",
    "TestRunner": "cap.requirement-compiler-verification",
    "Verifier": "cap.requirement-compiler-verification",
    "Critic": "cap.requirement-compiler-verification",
    "ResearchScout": "cap.requirement-research-scout",
    "ResearchSynthesizer": "cap.requirement-research-synthesizer",
    "ArtifactCurator": "cap.requirement-research-synthesizer",
}

DEFAULT_TASK_TYPE_BY_LOGICAL_OPERATOR = {
    "DeepArchitect": "planning",
    "ImplementationWorker": "implementation",
    "PatchWorker": "implementation",
    "TestRunner": "tests",
    "Verifier": "verification",
    "Critic": "review",
    "ResearchScout": "knowledge-extraction",
    "ResearchSynthesizer": "research",
    "ArtifactCurator": "evidence",
}

READ_ONLY_AUDIT_TASK_TYPES = {
    "audit",
    "audit_inventory",
    "inventory",
    "documentation",
    "docs",
    "report",
    "reporting",
    "packaging_audit",
    "packaging_inventory",
}

READ_ONLY_AUDIT_TASK_TYPE_ALIASES = {
    "audit": "audit_inventory",
    "audit_inventory": "audit_inventory",
    "inventory": "audit_inventory",
    "packaging_audit": "audit_inventory",
    "packaging_inventory": "audit_inventory",
    "documentation": "documentation",
    "docs": "documentation",
    "report": "reporting",
    "reporting": "reporting",
    "evidence": "evidence",
}

READ_ONLY_AUDIT_SIGNALS = {
    "audit",
    "inventory",
    "document",
    "documentation",
    "report",
    "readiness",
    "packaging",
    "inspect",
}


def _skill_driven_override(
    logical_operator: str,
    *,
    registry_env: str = "SOLAR_SKILL_OPERATOR_REGISTRY",
) -> Dict[str, str]:
    registry_hint = str(os.environ.get(registry_env, "") or "").strip()
    if not registry_hint:
        return {}
    try:
        from skill_operator_registry import DEFAULT_BINDINGS_PATH, lookup_by_logical_operator
    except Exception:
        return {}
    binding_path = DEFAULT_BINDINGS_PATH if registry_hint in {"1", "true", "TRUE", "yes"} else Path(registry_hint)
    binding = lookup_by_logical_operator(str(logical_operator or ""), path=binding_path)
    if binding is None:
        return {}
    return {
        "capsule_id": binding.capsule_id,
        "dispatch_task_type": "knowledge-extraction",
        "physical_operator": binding.physical_operator,
        "actor": binding.actor,
        "semantic_backend": binding.semantic_backend or "",
    }


def _looks_like_understand_anything_task(
    logical_operator: str,
    *,
    request_type: str = "",
    lane_hint: str = "",
    node: Optional[Dict[str, Any]] = None,
) -> bool:
    if str(logical_operator or "") not in {"ResearchScout", "ResearchSynthesizer", "ArtifactCurator", "DeepArchitect"}:
        return False
    text_parts = [
        str(request_type or ""),
        str(lane_hint or ""),
        str((node or {}).get("goal", "")),
        str((node or {}).get("title", "")),
        str((node or {}).get("type", "")),
    ]
    haystack = " ".join(text_parts).lower()
    return any(token in haystack for token in UNDERSTAND_ANYTHING_SIGNAL_TOKENS)


def _looks_like_read_only_audit_task(
    logical_operator: str,
    *,
    request_type: str = "",
    lane_hint: str = "",
    node: Optional[Dict[str, Any]] = None,
    goal_text: str = "",
) -> bool:
    if str(logical_operator or "") != "ImplementationWorker":
        return False
    node_payload = node or {}
    policy = node_payload.get("architecture_policy") if isinstance(node_payload.get("architecture_policy"), dict) else {}
    task_markers = {
        str(node_payload.get("type") or "").lower(),
        str(node_payload.get("dispatch_task_type") or "").lower(),
        str(request_type or "").lower(),
        str(lane_hint or "").lower(),
    }
    skills = {str(skill).lower() for skill in (node_payload.get("required_skills") or [])}
    write_scope = [str(item) for item in (node_payload.get("write_scope") or [])]
    writes_only_sprint_artifacts = bool(write_scope) and all(
        item.startswith(("harness/sprints/", "sprints/")) for item in write_scope
    )
    core_patch_denied = policy.get("core_patch_allowed") is False
    text_parts = [
        goal_text,
        str(node_payload.get("goal", "")),
        str(node_payload.get("title", "")),
        str(node_payload.get("type", "")),
        str(node_payload.get("dispatch_task_type", "")),
        " ".join(skills),
    ]
    haystack = " ".join(text_parts).lower().replace("_", " ").replace("-", " ")
    explicit_audit_type = bool(task_markers.intersection(READ_ONLY_AUDIT_TASK_TYPES))
    audit_signal = explicit_audit_type or any(signal in haystack for signal in READ_ONLY_AUDIT_SIGNALS)
    docs_skill = bool(skills.intersection({"documentation", "reporting", "harness.reporting"}))
    non_mutating_policy = core_patch_denied or writes_only_sprint_artifacts or explicit_audit_type
    return bool((audit_signal or docs_skill) and non_mutating_policy)


def _canonical_read_only_audit_task_type(node: Optional[Dict[str, Any]] = None) -> str:
    """Map planner freeform read-only audit labels onto the capsule's admitted task types.

    Planners may emit broad labels such as `analysis` for scope/inspection nodes. Once the
    read-only audit heuristic has selected the audit capsule, keep admission strict by using
    one of that capsule's canonical task types instead of adding every freeform synonym to
    the capsule manifest.
    """
    node_payload = node or {}
    for key in ("dispatch_task_type", "type"):
        raw = str(node_payload.get(key) or "").strip().lower()
        if raw in READ_ONLY_AUDIT_TASK_TYPE_ALIASES:
            return READ_ONLY_AUDIT_TASK_TYPE_ALIASES[raw]
    return "audit_inventory"


class CapsuleError(RuntimeError):
    """Base error for capsule failures."""


class CapsuleRegistryError(CapsuleError):
    """Raised when registry or manifest loading fails."""


class CapsuleResolutionError(CapsuleError):
    """Raised when runtime gate cannot resolve a usable capability capsule."""


@dataclass
class RegistryEntry:
    capability_capsule_id: str
    version: str
    capsule_kind: str
    status: str
    schema_ref: str
    manifest_path: str
    tags: List[str]
    owner: str
    default_operator_profile: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_capsule_id": self.capability_capsule_id,
            "version": self.version,
            "capsule_kind": self.capsule_kind,
            "status": self.status,
            "schema_ref": self.schema_ref,
            "manifest_path": self.manifest_path,
            "tags": list(self.tags),
            "owner": self.owner,
            "default_operator_profile": self.default_operator_profile,
        }


def _read_yaml_or_json(path: Path) -> Any:
    if not path.exists():
        raise CapsuleRegistryError(f"capsule file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - parser-specific messaging
        raise CapsuleRegistryError(f"failed to parse capsule file {path}: {exc}") from exc
    return data


def _load_schema(path: Optional[Path] = None) -> Dict[str, Any]:
    schema_path = Path(path or CAPSULE_SCHEMA_PATH)
    if not schema_path.exists():
        raise CapsuleRegistryError(f"capability capsule schema missing: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _flatten_registry(raw: Dict[str, Any], registry_path: Path) -> List[RegistryEntry]:
    capsules = raw.get("capsules", {})
    entries: List[RegistryEntry] = []
    for capsule_kind in ("capability", "guard", "resource"):
        for item in capsules.get(capsule_kind, []) or []:
            manifest_path = Path(item["manifest_path"])
            if not manifest_path.is_absolute():
                manifest_path = (registry_path.parent / manifest_path).resolve()
            entries.append(
                RegistryEntry(
                    capability_capsule_id=item["capability_capsule_id"],
                    version=str(item["version"]),
                    capsule_kind=item.get("capsule_kind", capsule_kind),
                    status=item["status"],
                    schema_ref=item.get("schema_ref", "draft/capability-capsule.v1.draft.json"),
                    manifest_path=str(manifest_path),
                    tags=list(item.get("tags", [])),
                    owner=item.get("owner", "unknown"),
                    default_operator_profile=item.get("default_operator_profile"),
                )
            )
    return entries


def load_capability_capsule_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    registry_path = Path(path or CAPSULE_REGISTRY_PATH)
    raw = _read_yaml_or_json(registry_path)
    if not isinstance(raw, dict):
        raise CapsuleRegistryError(f"invalid capsule registry format: {registry_path}")
    entries = _flatten_registry(raw, registry_path)
    return {
        "version": raw.get("version", 1),
        "path": str(registry_path),
        "entries": [entry.to_dict() for entry in entries],
    }


def iter_registry_entries(
    *,
    path: Optional[Path] = None,
    include_deprecated: bool = False,
    include_draft: bool = False,
    include_revoked: bool = False,
) -> List[RegistryEntry]:
    payload = load_capability_capsule_registry(path=path)
    entries = [RegistryEntry(**entry) for entry in payload["entries"]]
    filtered: List[RegistryEntry] = []
    for entry in entries:
        if entry.status == "stable":
            filtered.append(entry)
            continue
        if entry.status == "deprecated" and include_deprecated:
            filtered.append(entry)
            continue
        if entry.status == "draft" and include_draft:
            filtered.append(entry)
            continue
        if entry.status == "revoked" and include_revoked:
            filtered.append(entry)
    return filtered


def get_registry_entry(
    capability_capsule_id: str,
    *,
    path: Optional[Path] = None,
    include_nonstable: bool = True,
) -> Optional[RegistryEntry]:
    entries = iter_registry_entries(
        path=path,
        include_deprecated=include_nonstable,
        include_draft=include_nonstable,
        include_revoked=include_nonstable,
    )
    for entry in entries:
        if entry.capability_capsule_id == capability_capsule_id:
            return entry
    return None


def _normalize_list_of_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _normalize_mcp_bindings(bindings: Any) -> Dict[str, List[str]]:
    if isinstance(bindings, dict):
        out: Dict[str, List[str]] = {}
        for key, value in bindings.items():
            out[str(key)] = _normalize_list_of_strings(value)
        return out
    if isinstance(bindings, list):
        return {token: [] for token in _normalize_list_of_strings(bindings)}
    return {}


def _default_section_dict() -> Dict[str, Any]:
    return {}


def normalize_capability_capsule(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize new Capability Capsule manifests and legacy ECapsule payloads."""
    data = deepcopy(payload)
    if not isinstance(data, dict):
        raise CapsuleRegistryError("capability capsule payload must be an object")

    capability_capsule_id = data.get("capability_capsule_id") or data.get("execution_capsule_id")
    if not capability_capsule_id:
        raise CapsuleRegistryError("capability_capsule_id or execution_capsule_id is required")

    if "capability_capsule_id" not in data:
        data["capability_capsule_id"] = capability_capsule_id
    if "capsule_kind" not in data:
        data["capsule_kind"] = "capability"

    if "execution_capsule_id" in data:
        data.setdefault("compatibility", {})["legacy_execution_capsule_id"] = data["execution_capsule_id"]

    # Legacy ECapsule translation.
    if "metadata" not in data:
        data["metadata"] = {
            "name": capability_capsule_id,
            "description": "Legacy execution capsule compatibility wrapper.",
        }
    if "applicability" not in data:
        data["applicability"] = {
            "task_types": _normalize_list_of_strings(data.get("task_type")),
            "positive_signals": [],
            "negative_signals": [],
        }
    if "contract" not in data:
        data["contract"] = {
            "inputs": {"required": [], "optional": []},
            "outputs": {"required": [], "optional": []},
            "preconditions": [],
            "postconditions": [],
            "invariants": [],
        }
    if "composition" not in data:
        data["composition"] = {
            "consumes": [],
            "produces": [],
            "compatible_with": [],
            "incompatible_with": [],
            "requires_after": [],
        }
    if "effects" not in data:
        data["effects"] = {
            "read": [],
            "write": [],
            "execute": [],
            "network": [],
            "cost": [],
            "risk": [],
        }
    if "bindings" not in data:
        data["bindings"] = {
            "skills": {
                "required": _normalize_list_of_strings(data.get("skill_id")),
                "optional": [],
            },
            "mcp_capabilities": _normalize_mcp_bindings(data.get("mcp_bindings")),
            "data_refs": [],
            "secret_refs": [],
            "required_guard_capsules": [],
            "required_resource_capsules": [],
        }
    if "verification" not in data:
        verification_rules = data.get("verification_rules", [])
        data["verification"] = {
            "self_check": [rule.get("check_name") for rule in verification_rules if isinstance(rule, dict) and rule.get("check_name")],
            "external_verifier": {"required": bool(data.get("contract"))},
            "pass_conditions": [guard.get("policy_id") for guard in data.get("policy_guard", []) if isinstance(guard, dict) and guard.get("result") == "pass" and guard.get("policy_id")],
        }
    if "operator_compatibility" not in data:
        data["operator_compatibility"] = {
            "preferred": _normalize_list_of_strings(data.get("operator_id")),
            "forbidden": [],
        }
    if "provenance" not in data:
        data["provenance"] = {
            "owner": data.get("owner", "unknown"),
            "created_at": data.get("created_at"),
            "source_sprint_id": data.get("sprint_id"),
            "source_node_id": data.get("node_id"),
        }

    data["metadata"] = data.get("metadata") or {}
    data["applicability"] = data.get("applicability") or {}
    data["contract"] = data.get("contract") or {}
    data["composition"] = data.get("composition") or {}
    data["effects"] = data.get("effects") or {}
    data["bindings"] = data.get("bindings") or {}
    data["verification"] = data.get("verification") or {}
    data["operator_compatibility"] = data.get("operator_compatibility") or {}
    data["provenance"] = data.get("provenance") or {}

    bindings = data["bindings"]
    bindings.setdefault("skills", {"required": [], "optional": []})
    bindings["skills"].setdefault("required", [])
    bindings["skills"].setdefault("optional", [])
    bindings.setdefault("mcp_capabilities", {})
    bindings.setdefault("data_refs", [])
    bindings.setdefault("secret_refs", [])
    bindings.setdefault("required_guard_capsules", [])
    bindings.setdefault("required_resource_capsules", [])

    contract = data["contract"]
    contract.setdefault("inputs", {"required": [], "optional": []})
    contract.setdefault("outputs", {"required": [], "optional": []})
    contract.setdefault("preconditions", [])
    contract.setdefault("postconditions", [])
    contract.setdefault("invariants", [])

    composition = data["composition"]
    composition.setdefault("consumes", [])
    composition.setdefault("produces", [])
    composition.setdefault("compatible_with", [])
    composition.setdefault("incompatible_with", [])
    composition.setdefault("requires_after", [])

    effects = data["effects"]
    for key in ("read", "write", "execute", "network", "cost", "risk"):
        effects.setdefault(key, [])

    verification = data["verification"]
    verification.setdefault("self_check", [])
    verification.setdefault("external_verifier", {"required": False})
    verification.setdefault("pass_conditions", [])

    op_compat = data["operator_compatibility"]
    op_compat.setdefault("preferred", [])
    op_compat.setdefault("forbidden", [])

    applicability = data["applicability"]
    applicability.setdefault("task_types", [])
    applicability.setdefault("positive_signals", [])
    applicability.setdefault("negative_signals", [])

    return data


def load_capability_capsule_manifest(path: Path) -> Dict[str, Any]:
    raw = _read_yaml_or_json(path)
    if not isinstance(raw, dict):
        raise CapsuleRegistryError(f"invalid capability capsule manifest: {path}")
    normalized = normalize_capability_capsule(raw)
    normalized.setdefault("provenance", {})
    normalized["provenance"].setdefault("manifest_path", str(path))
    return normalized


def validate_capability_capsule_semantics(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    capsule_kind = payload.get("capsule_kind")
    contract = payload.get("contract", {})
    effects = payload.get("effects", {})
    bindings = payload.get("bindings", {})
    verification = payload.get("verification", {})
    composition = payload.get("composition", {})

    for key in ("preconditions", "postconditions", "invariants"):
        if not contract.get(key):
            errors.append(f"contract.{key} must be non-empty")

    for key in ("read", "write", "execute", "network"):
        if key not in effects:
            errors.append(f"effects.{key} must exist")

    secret_refs = bindings.get("secret_refs", []) or []
    if secret_refs:
        guard_refs = bindings.get("required_guard_capsules", []) or []
        requires_after = composition.get("requires_after", []) or []
        guard_like = [item for item in list(guard_refs) + list(requires_after) if str(item).startswith("guard.")]
        if not guard_like:
            errors.append("secret_refs require at least one guard capsule reference")

    if capsule_kind == "resource" and effects.get("execute"):
        errors.append("resource capsule must not declare effects.execute")

    if capsule_kind == "guard":
        pass_conditions = verification.get("pass_conditions", []) or []
        policy_guard = payload.get("policy_guard", []) or []
        if not pass_conditions and not policy_guard:
            errors.append("guard capsule must declare pass_conditions or policy_guard")

    return errors


def validate_capability_capsule(
    payload: Dict[str, Any],
    *,
    schema_path: Optional[Path] = None,
) -> List[str]:
    normalized = normalize_capability_capsule(payload)
    errors: List[str] = []
    try:
        import jsonschema
    except Exception:
        jsonschema = None  # type: ignore[assignment]
    if jsonschema is not None:
        schema = _load_schema(schema_path)
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(normalized), key=lambda e: list(e.path)):
            path = ".".join(str(part) for part in err.path)
            if path:
                errors.append(f"{path}: {err.message}")
            else:
                errors.append(err.message)
    errors.extend(validate_capability_capsule_semantics(normalized))
    return errors


def _query_capability_providers(capability: str, min_level: int = 3) -> List[Dict[str, Any]]:
    from capability_registry import get_active_providers

    return get_active_providers(capability, min_level=min_level)


def _signals_from_task(task_envelope: Dict[str, Any]) -> List[str]:
    explicit = task_envelope.get("signals")
    if isinstance(explicit, list):
        return [str(x).lower() for x in explicit]
    objective = str(task_envelope.get("objective", "")).lower()
    return [token for token in objective.replace("/", " ").replace(",", " ").split() if token]


TAXONOMY_PATH = HARNESS_DIR / "config" / "task-taxonomy.json"
OPERATORS_PATH = HARNESS_DIR / "config" / "logical-operators.json"
SKILL_BINDINGS_PATH = HARNESS_DIR / "config" / "skill-operator-bindings.yaml"


def _load_taxonomy() -> Dict[str, Any]:
    try:
        return json.loads(TAXONOMY_PATH.read_text())
    except Exception:
        return {}


def _load_operators_config() -> Dict[str, Any]:
    try:
        return json.loads(OPERATORS_PATH.read_text())
    except Exception:
        return {}


def _load_skill_bindings() -> Dict[str, Any]:
    try:
        return yaml.safe_load(SKILL_BINDINGS_PATH.read_text()) or {}
    except Exception:
        return {}


def classify_task_goal(
    goal: str,
    *,
    context_hints: Optional[List[str]] = None,
    taxonomy_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Score a goal string against the task taxonomy and return task_classification artifact."""
    taxonomy_data = (
        json.loads(Path(taxonomy_path).read_text()) if taxonomy_path else _load_taxonomy()
    )
    task_classes = taxonomy_data.get("task_classes", {})
    weights = taxonomy_data.get("signal_weights", {"primary": 2, "secondary": 1, "negative": -3})
    thresholds = taxonomy_data.get("confidence_thresholds", {"high": 6, "medium": 3, "low": 1})

    tokens = set(goal.lower().replace("/", " ").replace(",", " ").split())
    if context_hints:
        for hint in context_hints:
            tokens.update(hint.lower().split())

    scores: Dict[str, float] = {}
    detected_signals_per_class: Dict[str, List[Dict[str, Any]]] = {}

    for class_id, class_def in task_classes.items():
        score = 0.0
        signals_detected = []
        for sig in class_def.get("primary_signals", []):
            if sig.lower() in tokens:
                score += weights["primary"]
                signals_detected.append({"signal": sig, "weight": weights["primary"], "source": "goal_text"})
        for sig in class_def.get("secondary_signals", []):
            if sig.lower() in tokens:
                score += weights["secondary"]
                signals_detected.append({"signal": sig, "weight": weights["secondary"], "source": "goal_text"})
        for sig in class_def.get("negative_signals", []):
            if sig.lower() in tokens:
                score += weights["negative"]
                signals_detected.append({"signal": sig, "weight": weights["negative"], "source": "goal_text"})
        scores[class_id] = score
        detected_signals_per_class[class_id] = signals_detected

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    selected = [(cid, sc) for cid, sc in ranked if sc >= task_classes.get(cid, {}).get("min_signal_score", 1)]
    rejected = [(cid, sc) for cid, sc in ranked if sc < task_classes.get(cid, {}).get("min_signal_score", 1)]

    if not selected:
        # No class cleared threshold — emit fallback with empty selection
        return {
            "selected_classes": [],
            "primary_class": None,
            "confidence": "low",
            "signal_score": 0,
            "signals_detected": [],
            "rejected_classes": [
                {"class_id": cid, "score": sc, "reason": "below_min_signal_score"}
                for cid, sc in ranked
            ],
            "classifier_version": "v1",
        }

    primary_class_id, primary_score = selected[0]
    if primary_score >= thresholds["high"]:
        confidence = "high"
    elif primary_score >= thresholds["medium"]:
        confidence = "medium"
    else:
        confidence = "low"

    all_detected = []
    seen = set()
    for cid, _ in selected:
        for sig_entry in detected_signals_per_class[cid]:
            key = sig_entry["signal"]
            if key not in seen:
                seen.add(key)
                all_detected.append(sig_entry)

    rejected_list = []
    for cid, sc in ranked:
        if cid not in {c for c, _ in selected}:
            rejected_list.append({"class_id": cid, "score": sc, "reason": "below_min_signal_score"})
    for cid, sc in selected[1:]:
        rejected_list.append({"class_id": cid, "score": sc, "reason": "outscored_by_primary"})

    return {
        "selected_classes": [cid for cid, _ in selected],
        "primary_class": primary_class_id,
        "confidence": confidence,
        "signal_score": primary_score,
        "signals_detected": all_detected,
        "rejected_classes": rejected_list,
        "classifier_version": "v1",
    }


def expand_logical_workflow(
    task_classification: Dict[str, Any],
    *,
    operators_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Select a workflow template based on primary_class and expand it into stages."""
    ops_config = (
        json.loads(Path(operators_path).read_text()) if operators_path else _load_operators_config()
    )
    workflow_vocab = ops_config.get("workflow_vocabulary", {})
    workflow_templates = ops_config.get("workflow_templates", {})

    primary_class = task_classification.get("primary_class")
    if not primary_class:
        return {"template": "none", "stages": [], "rationale": "No task class detected; no workflow expanded."}

    # Find matching template
    selected_template_id = None
    selected_template = None
    for tmpl_id, tmpl in workflow_templates.items():
        if primary_class in tmpl.get("applicable_task_classes", []):
            selected_template_id = tmpl_id
            selected_template = tmpl
            break

    if not selected_template:
        return {
            "template": "none",
            "stages": [],
            "rationale": f"No workflow template matches task class {primary_class}.",
        }

    stages = []
    for pos, stage_name in enumerate(selected_template.get("stages", []), start=1):
        stage_def = workflow_vocab.get(stage_name, {})
        operators = stage_def.get("maps_to_operators", [])
        stages.append({
            "stage_name": stage_name,
            "logical_operators": operators,
            "rationale": stage_def.get("description", ""),
            "position": pos,
        })

    return {
        "template": selected_template_id,
        "stages": stages,
        "rationale": f"Workflow template '{selected_template_id}' selected because primary task class is {primary_class}. {selected_template.get('description', '')}",
    }


def resolve_skill_plan(
    logical_workflow: Dict[str, Any],
    capsule_manifest: Optional[Dict[str, Any]] = None,
    *,
    skill_bindings_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """For each workflow stage, identify candidate and selected skills."""
    bindings_data = (
        yaml.safe_load(Path(skill_bindings_path).read_text()) if skill_bindings_path
        else _load_skill_bindings()
    )
    skill_meta_list = bindings_data.get("skill_capability_metadata", [])
    # index by applicable_workflow_stages
    stage_to_skills: Dict[str, List[Dict[str, Any]]] = {}
    for skill_meta in skill_meta_list:
        for stage in skill_meta.get("applicable_workflow_stages", []):
            stage_to_skills.setdefault(stage, []).append(skill_meta)

    # Also add capsule-mandated skills as candidates
    capsule_required_skills = set()
    if capsule_manifest:
        capsule_required_skills = set(
            capsule_manifest.get("bindings", {}).get("skills", {}).get("required", [])
        )

    skill_plan: Dict[str, Any] = {}
    for stage in logical_workflow.get("stages", []):
        stage_name = stage["stage_name"]
        candidates_raw = stage_to_skills.get(stage_name, [])
        candidates = []
        selected = None
        for meta in candidates_raw:
            skill_id = meta["skill_id"]
            tier = meta.get("readiness_tier", "draft")
            candidates.append({"skill_id": skill_id, "readiness_tier": tier, "rationale": meta.get("display_name", "")})
            if selected is None and tier in ("stable", "draft"):
                selected = skill_id
        # If capsule mandates a skill relevant to this stage, prefer it
        for mandated in capsule_required_skills:
            if mandated not in {c["skill_id"] for c in candidates}:
                candidates.append({"skill_id": mandated, "readiness_tier": "stable", "rationale": "capsule_required"})
            if selected is None:
                selected = mandated

        rejected = [
            {"skill_id": c["skill_id"], "reason": "lower_readiness_tier_or_outscored"}
            for c in candidates if c["skill_id"] != selected
        ]
        skill_plan[stage_name] = {
            "candidates": candidates,
            "selected": selected,
            "rejection_rationale": rejected,
        }

    return skill_plan


def resolve_mcp_plan(
    skill_plan: Dict[str, Any],
    capsule_manifest: Optional[Dict[str, Any]] = None,
    *,
    skill_bindings_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Aggregate MCP requirements from selected skills and capsule manifest."""
    bindings_data = (
        yaml.safe_load(Path(skill_bindings_path).read_text()) if skill_bindings_path
        else _load_skill_bindings()
    )
    skill_meta_by_id: Dict[str, Dict[str, Any]] = {
        m["skill_id"]: m for m in bindings_data.get("skill_capability_metadata", [])
    }

    seen_capabilities: Dict[str, Dict[str, Any]] = {}

    # Collect from selected skills
    for stage_name, stage_data in skill_plan.items():
        selected_skill_id = stage_data.get("selected")
        if not selected_skill_id:
            continue
        skill_meta = skill_meta_by_id.get(selected_skill_id, {})
        for mcp_req in skill_meta.get("mcp_requirements", []):
            cap = mcp_req.get("capability", "")
            if cap and cap not in seen_capabilities:
                seen_capabilities[cap] = {
                    "capability": cap,
                    "why_needed": mcp_req.get("why", f"Required by skill {selected_skill_id} in stage {stage_name}"),
                    "provider_candidates": [],
                    "selected_provider": None,
                }

    # Collect from capsule manifest mcp_capabilities
    if capsule_manifest:
        capsule_mcp = capsule_manifest.get("bindings", {}).get("mcp_capabilities", {})
        for cap, access_modes in capsule_mcp.items():
            if cap not in seen_capabilities:
                seen_capabilities[cap] = {
                    "capability": cap,
                    "why_needed": f"Required by capsule manifest (access: {access_modes})",
                    "provider_candidates": [],
                    "selected_provider": None,
                }

    return {
        "required_mcp": list(seen_capabilities.values()),
        "optional_mcp": [],
    }


def query_capability_capsules(
    *,
    task_type: Optional[str] = None,
    signals: Optional[Iterable[str]] = None,
    capsule_kind: Optional[str] = None,
    operator_id: Optional[str] = None,
    registry_path: Optional[Path] = None,
    include_deprecated: bool = False,
) -> List[Dict[str, Any]]:
    signal_set = {str(sig).lower() for sig in (signals or [])}
    candidates: List[Dict[str, Any]] = []
    for entry in iter_registry_entries(path=registry_path, include_deprecated=include_deprecated):
        if capsule_kind and entry.capsule_kind != capsule_kind:
            continue
        manifest = load_capability_capsule_manifest(Path(entry.manifest_path))
        if task_type:
            task_types = {str(v) for v in manifest.get("applicability", {}).get("task_types", [])}
            if task_types and task_type not in task_types:
                continue
        positives = {str(v).lower() for v in manifest.get("applicability", {}).get("positive_signals", [])}
        negatives = {str(v).lower() for v in manifest.get("applicability", {}).get("negative_signals", [])}
        if negatives and signal_set.intersection(negatives):
            continue
        if operator_id:
            forbidden = set(manifest.get("operator_compatibility", {}).get("forbidden", []))
            if operator_id in forbidden:
                continue
        score = 0
        if task_type and task_type in set(manifest.get("applicability", {}).get("task_types", [])):
            score += 10
        score += len(signal_set.intersection(positives))
        candidates.append({"entry": entry.to_dict(), "manifest": manifest, "score": score})
    candidates.sort(key=lambda item: (-item["score"], item["entry"]["capability_capsule_id"]))
    return candidates


def default_capability_plan_for_logical_operator(
    logical_operator: str,
    *,
    request_type: str = "",
    lane_hint: str = "",
    node: Optional[Dict[str, Any]] = None,
    registry_path: Optional[Path] = None,
    goal_text: str = "",
) -> Dict[str, Any]:
    # ── Priority 1: skill-driven override (understand-anything etc.) ──────────
    skill_override = _skill_driven_override(logical_operator)
    if skill_override:
        capsule_id = skill_override["capsule_id"]
        dispatch_task_type = skill_override["dispatch_task_type"]
        selection_mode = "skill_driven_override"
        fallback_used = False
        fallback_reason = None
    elif _looks_like_understand_anything_task(
        logical_operator,
        request_type=request_type,
        lane_hint=lane_hint,
        node=node,
    ):
        capsule_id = "cap.understand-anything-indexer"
        dispatch_task_type = "code-understanding"
        selection_mode = "understand_anything_heuristic"
        fallback_used = False
        fallback_reason = None
    elif _looks_like_read_only_audit_task(
        logical_operator,
        request_type=request_type,
        lane_hint=lane_hint,
        node=node,
        goal_text=goal_text,
    ):
        capsule_id = "cap.requirement-compiler-audit"
        dispatch_task_type = _canonical_read_only_audit_task_type(node)
        selection_mode = "read_only_audit_heuristic"
        fallback_used = False
        fallback_reason = None
    elif (
        str(request_type).strip().lower() == "research"
        or str(logical_operator).strip().lower()
        in {"researcher", "researchscout", "researchsynthesizer", "artifactcurator"}
        or str((node or {}).get("type", "")).strip().lower() == "research"
    ):
        # Research nodes must NOT bind code-capability capsules. Their goal text routinely
        # contains code keywords ("autocomplete latency", "refactoring", "benchmark",
        # "throughput") that mis-trigger the code-task classifier — e.g. the CAPABILITIES
        # research dimension pulled cap.flashmlx-performance-debugger, whose
        # root_cause_report/benchmark_report proof obligations a research node can never
        # produce → permanent eval FAIL → the research gate wedges (observed: S2a failed while
        # sibling S2b–S2e, identical Researcher nodes, passed with no capsule). Research
        # capability capsules are bound via the skill-driven override (Priority 1:
        # ResearchScout/Synthesizer/ArtifactCurator); a plain Researcher node correctly gets none.
        capsule_id = None
        dispatch_task_type = ""
        fallback_used = False
        fallback_reason = "research_node_skips_code_capability_classifier"
        selection_mode = "research_node_no_code_capsule"
    else:
        # ── Priority 2: goal-driven classifier → capsule query ─────────────
        effective_goal = goal_text or str((node or {}).get("goal", "")) or request_type
        capsule_id = None
        fallback_used = False
        fallback_reason = None
        selection_mode = "goal_driven_classifier"
        if effective_goal:
            classification = classify_task_goal(effective_goal)
            primary_class = classification.get("primary_class")
            signals = [s["signal"] for s in classification.get("signals_detected", []) if s["weight"] > 0]
            if primary_class and signals:
                candidates = query_capability_capsules(
                    task_type=primary_class,
                    signals=signals,
                    capsule_kind="capability",
                    registry_path=registry_path,
                )
                if candidates and candidates[0]["score"] > 0:
                    best = candidates[0]
                    capsule_id = best["entry"]["capability_capsule_id"]
                    dispatch_task_type = primary_class
                else:
                    fallback_reason = "no_capsule_matched_signals"
            else:
                fallback_reason = "classifier_score_below_threshold"
        else:
            fallback_reason = "no_goal_text_available"

        # ── Priority 3: static default (fallback only) ────────────────────
        if not capsule_id:
            capsule_id = DEFAULT_CAPSULE_BY_LOGICAL_OPERATOR.get(str(logical_operator or ""))
            dispatch_task_type = DEFAULT_TASK_TYPE_BY_LOGICAL_OPERATOR.get(str(logical_operator or ""), "")
            fallback_used = True
            selection_mode = "static_default_fallback"

    if not capsule_id:
        return {}
    entry = get_registry_entry(capsule_id, path=registry_path, include_nonstable=True)
    if entry is None or entry.status == "revoked":
        return {}
    manifest = load_capability_capsule_manifest(Path(entry.manifest_path))
    bindings = manifest.get("bindings", {})
    operator_compat = manifest.get("operator_compatibility", {})
    return {
        "capability_native": True,
        "capability_capsule_id": capsule_id,
        "dispatch_task_type": dispatch_task_type,
        "selection_mode": selection_mode,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "request_type": request_type,
        "lane_hint": lane_hint,
        "logical_operator": logical_operator,
        "node_goal": str((node or {}).get("goal", "")),
        "required_guard_capsules": list(bindings.get("required_guard_capsules", [])),
        "required_resource_capsules": list(bindings.get("required_resource_capsules", [])),
        "selected_skills": list(bindings.get("skills", {}).get("required", [])),
        "operator_constraints": {
            "preferred": list(operator_compat.get("preferred", [])),
            "forbidden": list(operator_compat.get("forbidden", [])),
            "default_operator_profile": entry.default_operator_profile,
        },
        "skill_driven_override": bool(skill_override),
        "semantic_backend": skill_override.get("semantic_backend", "") if skill_override else "",
    }


def _check_preconditions(task_envelope: Dict[str, Any], manifest: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for condition in manifest.get("contract", {}).get("preconditions", []):
        if not isinstance(condition, dict):
            continue
        check = condition.get("check")
        if check == "input_present":
            field = condition.get("field")
            if field and not task_envelope.get(field):
                failures.append(f"missing required input: {field}")
        elif check == "task_type_in":
            values = set(condition.get("values", []))
            if values and task_envelope.get("task_type") not in values:
                failures.append(f"task_type not allowed: {task_envelope.get('task_type')}")
        elif check == "operator_capability":
            required = condition.get("field")
            if required and not task_envelope.get(required):
                failures.append(f"operator capability flag missing: {required}")
        elif check == "custom_flag_true":
            field = condition.get("field")
            if field and task_envelope.get(field) is not True:
                failures.append(f"custom flag not true: {field}")
    return failures


def _resolve_bindings(manifest: Dict[str, Any]) -> Dict[str, Any]:
    bindings = manifest.get("bindings", {})
    resolved: Dict[str, Any] = {}
    providers: Dict[str, List[Dict[str, Any]]] = {}
    for token in bindings.get("mcp_capabilities", {}) or {}:
        found = _query_capability_providers(token, min_level=3)
        if not found:
            raise CapsuleResolutionError(f"missing capability provider for {token}")
        providers[token] = found
    resolved["mcp_capabilities"] = providers
    resolved["selected_skills"] = list(bindings.get("skills", {}).get("required", []))
    return resolved


def _attach_referenced_capsules(
    ids: Iterable[str],
    *,
    expected_kind: str,
    registry_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    attached: List[Dict[str, Any]] = []
    for capsule_id in ids:
        entry = get_registry_entry(str(capsule_id), path=registry_path, include_nonstable=True)
        if entry is None:
            raise CapsuleResolutionError(f"missing_{expected_kind}: {capsule_id}")
        if entry.status == "revoked":
            raise CapsuleResolutionError(f"revoked_{expected_kind}: {capsule_id}")
        manifest = load_capability_capsule_manifest(Path(entry.manifest_path))
        if manifest.get("capsule_kind") != expected_kind:
            raise CapsuleResolutionError(
                f"{capsule_id} expected kind {expected_kind}, got {manifest.get('capsule_kind')}"
            )
        attached.append(manifest)
    return attached


def _summarize_effects(manifest: Dict[str, Any]) -> Dict[str, Any]:
    effects = manifest.get("effects", {})
    risk_flags = [flag for flag in effects.get("risk", []) if flag in HIGH_RISK_EFFECTS]
    return {
        "read": list(effects.get("read", [])),
        "write": list(effects.get("write", [])),
        "execute": list(effects.get("execute", [])),
        "network": list(effects.get("network", [])),
        "cost": list(effects.get("cost", [])),
        "risk": list(effects.get("risk", [])),
        "high_risk_flags": risk_flags,
    }


def resolve_capability_capsule_for_task(
    task_envelope: Dict[str, Any],
    *,
    operator_id: Optional[str] = None,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    signals = _signals_from_task(task_envelope)
    explicit_id = task_envelope.get("capability_capsule_id") or task_envelope.get("execution_capsule_id")
    selected_manifest: Optional[Dict[str, Any]] = None
    selected_entry: Optional[RegistryEntry] = None

    if explicit_id:
        entry = get_registry_entry(str(explicit_id), path=registry_path, include_nonstable=True)
        if entry is None:
            raise CapsuleResolutionError(f"admission_failed: capsule {explicit_id} not found")
        if entry.status == "revoked":
            raise CapsuleResolutionError(f"policy_blocked: capsule {explicit_id} is revoked")
        selected_entry = entry
        selected_manifest = load_capability_capsule_manifest(Path(entry.manifest_path))
    else:
        candidates = query_capability_capsules(
            task_type=task_envelope.get("task_type"),
            signals=signals,
            capsule_kind="capability",
            operator_id=operator_id,
            registry_path=registry_path,
        )
        if not candidates:
            raise CapsuleResolutionError("admission_failed: no capability capsule candidate")
        first = candidates[0]
        selected_entry = RegistryEntry(**first["entry"])
        selected_manifest = first["manifest"]

    assert selected_manifest is not None
    assert selected_entry is not None

    failures = _check_preconditions(task_envelope, selected_manifest)
    if failures:
        raise CapsuleResolutionError(f"admission_failed: {'; '.join(failures)}")

    operator_compat = selected_manifest.get("operator_compatibility", {})
    if operator_id and operator_id in set(operator_compat.get("forbidden", [])):
        raise CapsuleResolutionError(f"operator_incompatible: {operator_id}")

    bindings = selected_manifest.get("bindings", {})
    attached_guards = _attach_referenced_capsules(
        bindings.get("required_guard_capsules", []),
        expected_kind="guard",
        registry_path=registry_path,
    )
    attached_resources = _attach_referenced_capsules(
        bindings.get("required_resource_capsules", []),
        expected_kind="resource",
        registry_path=registry_path,
    )

    effect_summary = _summarize_effects(selected_manifest)
    if bindings.get("secret_refs") and not attached_guards:
        raise CapsuleResolutionError("policy_blocked: secret_refs without guard capsule")
    if effect_summary["high_risk_flags"] and not attached_guards:
        raise CapsuleResolutionError("effect_escalation_requires_human")

    resolved_bindings = _resolve_bindings(selected_manifest)
    verification = selected_manifest.get("verification", {})
    verifier = verification.get("external_verifier", {}) or {}
    if verifier.get("required") and not verification.get("pass_conditions"):
        raise CapsuleResolutionError("policy_blocked: verifier required but no pass_conditions")

    return {
        "capability_capsule_id": selected_manifest["capability_capsule_id"],
        "capsule_kind": selected_manifest.get("capsule_kind", "capability"),
        "selected_skills": resolved_bindings["selected_skills"],
        "resolved_mcp_bindings": {
            token: providers[0]["provider"] for token, providers in resolved_bindings["mcp_capabilities"].items()
        },
        "resolved_mcp_binding_candidates": resolved_bindings["mcp_capabilities"],
        "attached_guard_capsules": [capsule["capability_capsule_id"] for capsule in attached_guards],
        "attached_resource_capsules": [capsule["capability_capsule_id"] for capsule in attached_resources],
        "effect_summary": effect_summary,
        "verification_hooks": {
            "self_check": list(verification.get("self_check", [])),
            "pass_conditions": list(verification.get("pass_conditions", [])),
            "external_verifier": verifier,
        },
        "operator_constraints": {
            "preferred": list(operator_compat.get("preferred", [])),
            "forbidden": list(operator_compat.get("forbidden", [])),
            "default_operator_profile": selected_entry.default_operator_profile,
        },
        "manifest_path": selected_entry.manifest_path,
        "status": selected_entry.status,
        "compatibility": selected_manifest.get("compatibility", {}),
    }


def resolve_capability_capsule_for_envelope(
    task_envelope: Dict[str, Any],
    *,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    operator_id = task_envelope.get("operator_id")
    resolved = resolve_capability_capsule_for_task(
        task_envelope,
        operator_id=operator_id,
        registry_path=registry_path,
    )
    return resolved
