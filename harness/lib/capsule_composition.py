"""Deterministic registry audit and bounded typed capsule composition search."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, deque
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from capability_admission import rejection_reasons


HARNESS_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = HARNESS_DIR / "config"
SCHEMA_DIR = HARNESS_DIR / "schemas" / "planning"
ARTIFACT_TYPES_PATH = CONFIG_DIR / "artifact-types.v1.json"
CONVERSIONS_PATH = CONFIG_DIR / "artifact-conversions.v1.json"
PHYSICAL_OPERATORS_PATH = CONFIG_DIR / "physical-operators.json"
ARTIFACT_TYPES_SCHEMA = SCHEMA_DIR / "artifact-type-registry.v1.schema.json"
CONVERSIONS_SCHEMA = SCHEMA_DIR / "artifact-conversion-registry.v1.schema.json"
AUDIT_SCHEMA = SCHEMA_DIR / "registry-graph-audit.v1.schema.json"
COMPOSITION_SCHEMA = SCHEMA_DIR / "composition-candidate-search.v1.schema.json"
COMPOSITION_EFFECTS = ("read", "write", "execute", "network")
EXECUTION_TRUST_CLASSES = {
    "measured_execution",
    "evidence_transform",
    "fixture_or_adapter_only",
    "unspecified",
}
PLANNER_EXECUTION_TRUST_RANK = {
    "any": 0,
    "evidence_transform": 1,
    "measured_execution": 2,
}
_NO_EFFECT_TOKENS = {"", "none", "none by default", "no network", "disabled", "forbidden"}


class CapsuleCompositionError(RuntimeError):
    """Raised when a static registry or composition artifact is malformed."""


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CapsuleCompositionError(f"expected JSON object: {path}")
    return payload


def _sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate(payload: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = _load_json(schema_path)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise CapsuleCompositionError(f"{label} schema validation failed: {detail}")


def load_artifact_type_registry(path: Path = ARTIFACT_TYPES_PATH) -> dict[str, Any]:
    payload = _load_json(path)
    _validate(payload, ARTIFACT_TYPES_SCHEMA, "artifact type registry")
    identities = [str(row.get("artifact_type") or "") for row in payload.get("artifact_types") or []]
    if len(identities) != len(set(identities)):
        raise CapsuleCompositionError("artifact type registry contains duplicate identities")
    return payload


def load_conversion_registry(path: Path = CONVERSIONS_PATH) -> dict[str, Any]:
    payload = _load_json(path)
    _validate(payload, CONVERSIONS_SCHEMA, "artifact conversion registry")
    identities = [str(row.get("conversion_id") or "") for row in payload.get("conversions") or []]
    if len(identities) != len(set(identities)):
        raise CapsuleCompositionError("artifact conversion registry contains duplicate ids")
    return payload


def minimum_execution_trust_for_artifacts(
    artifact_types: list[str] | set[str] | tuple[str, ...],
    artifact_registry: dict[str, Any],
) -> str:
    """Return the strongest canonical trust floor for exact output identities.

    Missing policies intentionally mean ``any`` for compatibility. Unknown
    artifact identities are rejected elsewhere by the exact type registry and
    are never fuzzy-normalized here.
    """
    policy_by_type = {
        str(row.get("artifact_type") or ""): str(
            row.get("minimum_execution_trust") or "any"
        )
        for row in artifact_registry.get("artifact_types") or []
        if isinstance(row, dict)
    }
    minimum = "any"
    for artifact_type in artifact_types:
        policy = policy_by_type.get(str(artifact_type), "any")
        if PLANNER_EXECUTION_TRUST_RANK[policy] > PLANNER_EXECUTION_TRUST_RANK[minimum]:
            minimum = policy
    return minimum


def _verification_present(capsule: dict[str, Any]) -> bool:
    verification = capsule.get("verification") if isinstance(capsule.get("verification"), dict) else {}
    return bool(
        verification.get("self_checks")
        or verification.get("pass_conditions")
        or verification.get("external_required")
    )


def _selectable_implementation(capsule: dict[str, Any]) -> bool:
    return bool(
        (capsule.get("implementation") or {}).get("declared")
        and (capsule.get("operator_compatibility") or {}).get("selectable_preferred")
    )


def _active_effects(capsule: dict[str, Any]) -> list[str]:
    effects = capsule.get("effects") if isinstance(capsule.get("effects"), dict) else {}
    return [
        effect
        for effect in COMPOSITION_EFFECTS
        if any(
            str(value).strip().lower() not in _NO_EFFECT_TOKENS
            for value in effects.get(effect) or []
        )
    ]


def _semantic_identity(artifact_type: str) -> str:
    value = str(artifact_type)
    if value.startswith("artifact."):
        return value.removeprefix("artifact.").replace("-", "_")
    if value.startswith("schema:"):
        name = Path(value.removeprefix("schema:")).name
        return re.sub(r"(?:\.v\d+)?\.schema\.json$", "", name).replace("-", "_")
    return value.replace("-", "_")


def _approved_conversion_edges(
    catalog: dict[str, Any],
    artifact_registry: dict[str, Any],
    conversion_registry: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    known_types = {
        str(row.get("artifact_type") or "") for row in artifact_registry.get("artifact_types") or []
    }
    capsules = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict)
    }
    edges: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []
    for conversion in conversion_registry.get("conversions") or []:
        if conversion.get("approval_status") != "approved":
            continue
        conversion_id = str(conversion.get("conversion_id") or "")
        source = str(conversion.get("source_type") or "")
        target = str(conversion.get("target_type") or "")
        capsule_id = str(conversion.get("capsule_id") or "")
        capsule = capsules.get(capsule_id)
        reasons: list[str] = []
        if source not in known_types or target not in known_types:
            reasons.append("CONVERSION_TYPE_UNREGISTERED")
        if capsule is None:
            reasons.append("CONVERSION_CAPSULE_UNKNOWN")
        elif source not in (capsule.get("consumes") or []) or target not in (capsule.get("produces") or []):
            reasons.append("CONVERSION_CAPSULE_CONTRACT_MISMATCH")
        elif rejection_reasons(capsule):
            reasons.append("CONVERSION_CAPSULE_NOT_EXECUTABLE")
        if reasons:
            defects.append(
                {
                    "code": "APPROVED_CONVERSION_INVALID",
                    "severity": "error",
                    "conversion_id": conversion_id,
                    "reason_codes": reasons,
                }
            )
            continue
        edges.append(
            {
                "edge_id": conversion_id,
                "edge_kind": "approved_conversion",
                "capsule_id": capsule_id,
                "consumes": [source],
                "produces": [target],
                "effects": _active_effects(capsule),
            }
        )
    return edges, defects


def build_registry_graph_audit(
    catalog: dict[str, Any],
    *,
    artifact_registry: dict[str, Any] | None = None,
    conversion_registry: dict[str, Any] | None = None,
    physical_operators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit the frozen capsule registry as an exact directed hypergraph."""
    artifact_registry = artifact_registry or load_artifact_type_registry()
    conversion_registry = conversion_registry or load_conversion_registry()
    physical_operators = physical_operators or _load_json(PHYSICAL_OPERATORS_PATH)
    registered_rows = artifact_registry.get("artifact_types") or []
    known_types = {str(row.get("artifact_type") or "") for row in registered_rows}
    controller_inputs = {
        str(row.get("artifact_type") or "")
        for row in registered_rows
        if row.get("controller_input") is True
    }
    capsules = [row for row in catalog.get("capsules") or [] if isinstance(row, dict)]
    producers: dict[str, list[str]] = {}
    consumers: dict[str, list[str]] = {}
    issues: list[dict[str, Any]] = []
    for capsule in capsules:
        capsule_id = str(capsule.get("capsule_id") or "")
        for artifact_type in capsule.get("consumes") or []:
            consumers.setdefault(str(artifact_type), []).append(capsule_id)
        for artifact_type in capsule.get("produces") or []:
            producers.setdefault(str(artifact_type), []).append(capsule_id)
        if not _verification_present(capsule):
            issues.append({"code": "EMPTY_VERIFICATION_CONTRACT", "severity": "error", "capsule_id": capsule_id})
        preferred = list((capsule.get("operator_compatibility") or {}).get("preferred") or [])
        selectable = set((capsule.get("operator_compatibility") or {}).get("selectable_preferred") or [])
        if (capsule.get("implementation") or {}).get("declared") and not selectable:
            issues.append({"code": "IMPLEMENTATION_OPERATOR_UNAVAILABLE", "severity": "error", "capsule_id": capsule_id, "preferred": preferred})
        for operator_id in preferred:
            operator = (physical_operators.get("operators") or {}).get(operator_id)
            if not isinstance(operator, dict):
                issues.append({"code": "PREFERRED_OPERATOR_MISSING", "severity": "error", "capsule_id": capsule_id, "operator_id": operator_id})
                continue
            execute = [str(value) for value in (capsule.get("effects") or {}).get("execute") or []]
            explicit_paths = [Path(value).name for value in execute if "/" in value or value.endswith(".py")]
            command = str(operator.get("command") or "")
            if explicit_paths and operator.get("backend") == "command" and not command:
                issues.append({"code": "EXECUTE_COMMAND_MISSING", "severity": "error", "capsule_id": capsule_id, "operator_id": operator_id, "declared_execute": execute})

    used_types = set(producers) | set(consumers)
    for artifact_type in sorted(used_types - known_types):
        issues.append({"code": "ARTIFACT_TYPE_UNREGISTERED", "severity": "error", "artifact_type": artifact_type})
    for artifact_type in sorted(set(consumers) - set(producers) - controller_inputs):
        issues.append({"code": "MISSING_PRODUCER", "severity": "error", "artifact_type": artifact_type, "consumers": sorted(consumers[artifact_type])})
    for artifact_type in sorted(set(producers) - set(consumers)):
        issues.append({"code": "MISSING_CONSUMER", "severity": "warning", "artifact_type": artifact_type, "producers": sorted(producers[artifact_type])})
    for artifact_type, capsule_ids in sorted(producers.items()):
        if len(capsule_ids) > 1:
            issues.append({"code": "MULTIPLE_PRODUCERS", "severity": "warning", "artifact_type": artifact_type, "producers": sorted(capsule_ids)})

    conversion_edges, conversion_defects = _approved_conversion_edges(
        catalog, artifact_registry, conversion_registry
    )
    issues.extend(conversion_defects)
    approved_pairs = {
        frozenset((edge["consumes"][0], edge["produces"][0])) for edge in conversion_edges
    }
    identity_groups: dict[str, list[str]] = {}
    for artifact_type in known_types:
        identity_groups.setdefault(_semantic_identity(artifact_type), []).append(artifact_type)
    for semantic_key, identities in sorted(identity_groups.items()):
        if len(identities) < 2:
            continue
        unresolved_pairs = [
            sorted((left, right))
            for index, left in enumerate(sorted(identities))
            for right in sorted(identities)[index + 1 :]
            if frozenset((left, right)) not in approved_pairs
        ]
        if unresolved_pairs:
            issues.append({"code": "FRAGMENTED_ARTIFACT_IDENTITY", "severity": "warning", "semantic_key": semantic_key, "identities": sorted(identities), "unapproved_pairs": unresolved_pairs})

    reachable = set(controller_inputs)
    graph_edges = [
        {
            "consumes": sorted(str(value) for value in capsule.get("consumes") or []),
            "produces": sorted(str(value) for value in capsule.get("produces") or []),
        }
        for capsule in capsules
    ] + conversion_edges
    changed = True
    while changed:
        changed = False
        for edge in graph_edges:
            if set(edge.get("consumes") or []).issubset(reachable):
                before = len(reachable)
                reachable.update(edge.get("produces") or [])
                changed = changed or len(reachable) > before
    for artifact_type in sorted(used_types - reachable - controller_inputs):
        issues.append({"code": "ARTIFACT_TYPE_UNREACHABLE", "severity": "warning", "artifact_type": artifact_type})

    counts = Counter(str(issue.get("code") or "") for issue in issues)
    artifact = {
        "schema_version": "solar.registry_graph_audit.v1",
        "artifact_role": "registry_audit_artifact",
        "catalog_ref": {"sha256": _sha256(catalog)},
        "artifact_registry_ref": {"sha256": _sha256(artifact_registry)},
        "conversion_registry_ref": {"sha256": _sha256(conversion_registry)},
        "controller_inputs": sorted(controller_inputs),
        "reachable_types": sorted(reachable),
        "issues": sorted(issues, key=lambda row: (str(row.get("code")), json.dumps(row, sort_keys=True))),
        "summary": {
            "capsule_count": len(capsules),
            "registered_artifact_type_count": len(known_types),
            "issue_count": len(issues),
            "error_count": sum(1 for issue in issues if issue.get("severity") == "error"),
            "warning_count": sum(1 for issue in issues if issue.get("severity") == "warning"),
            "issues_by_code": dict(sorted(counts.items())),
        },
        "verdict": "fail" if any(issue.get("severity") == "error" for issue in issues) else "pass",
    }
    _validate(artifact, AUDIT_SCHEMA, "registry graph audit")
    return artifact


def _composition_edges(
    catalog: dict[str, Any], conversion_registry: dict[str, Any], artifact_registry: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for capsule in catalog.get("capsules") or []:
        if not isinstance(capsule, dict):
            continue
        reasons = rejection_reasons(capsule)
        capsule_id = str(capsule.get("capsule_id") or "")
        if reasons:
            excluded.append({"capsule_id": capsule_id, "reason_codes": reasons})
            continue
        edges.append(
            {
                "edge_id": capsule_id,
                "edge_kind": "capability_capsule",
                "capsule_id": capsule_id,
                "consumes": sorted(str(value) for value in capsule.get("consumes") or []),
                "produces": sorted(str(value) for value in capsule.get("produces") or []),
                "effects": _active_effects(capsule),
            }
        )
    conversions, defects = _approved_conversion_edges(catalog, artifact_registry, conversion_registry)
    excluded.extend(
        {"capsule_id": str(row.get("conversion_id") or ""), "reason_codes": list(row.get("reason_codes") or [])}
        for row in defects
    )
    edges.extend(conversions)
    return sorted(edges, key=lambda row: row["edge_id"]), sorted(excluded, key=lambda row: row["capsule_id"])


def search_composition_candidates(
    catalog: dict[str, Any],
    *,
    available_inputs: list[str],
    target_outputs: list[str],
    artifact_registry: dict[str, Any] | None = None,
    conversion_registry: dict[str, Any] | None = None,
    max_depth: int = 12,
    max_states: int = 500,
    max_candidates: int = 20,
    allowed_effects: list[str] | None = None,
    required_trust_by_output: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Enumerate bounded exact-type compositions over multi-input hyperedges."""
    artifact_registry = artifact_registry or load_artifact_type_registry()
    conversion_registry = conversion_registry or load_conversion_registry()
    if not (1 <= max_depth <= 32 and 1 <= max_states <= 10000 and 1 <= max_candidates <= 200):
        raise CapsuleCompositionError("composition search bounds are outside the admitted range")
    known_types = {
        str(row.get("artifact_type") or "") for row in artifact_registry.get("artifact_types") or []
    }
    lineage_family_by_type = {
        str(row.get("artifact_type") or ""): str(row.get("lineage_family") or "")
        for row in artifact_registry.get("artifact_types") or []
        if isinstance(row, dict) and str(row.get("lineage_family") or "")
    }
    requested = set(available_inputs) | set(target_outputs)
    unknown = sorted(requested - known_types)
    if unknown:
        raise CapsuleCompositionError(f"composition request contains unregistered artifact types: {unknown}")
    admitted_effects = set(COMPOSITION_EFFECTS if allowed_effects is None else allowed_effects)
    unknown_effects = sorted(admitted_effects - set(COMPOSITION_EFFECTS))
    if unknown_effects:
        raise CapsuleCompositionError(
            f"composition policy contains unknown effects: {unknown_effects}"
        )
    trust_requirements = {
        str(artifact_type): sorted(set(str(value) for value in values if str(value)))
        for artifact_type, values in (required_trust_by_output or {}).items()
    }
    invalid_trust_classes = sorted(
        {
            value
            for values in trust_requirements.values()
            for value in values
            if value not in EXECUTION_TRUST_CLASSES
        }
    )
    if invalid_trust_classes or any(not values for values in trust_requirements.values()):
        raise CapsuleCompositionError(
            "composition trust policy contains empty or unknown trust classes: "
            f"{invalid_trust_classes}"
        )
    unknown_trust_types = sorted(set(trust_requirements) - known_types)
    if unknown_trust_types:
        raise CapsuleCompositionError(
            f"composition trust policy contains unregistered artifact types: {unknown_trust_types}"
        )
    all_edges, excluded = _composition_edges(catalog, conversion_registry, artifact_registry)
    capsule_by_id = {
        str(row.get("capsule_id") or ""): row
        for row in catalog.get("capsules") or []
        if isinstance(row, dict)
    }
    policy_eligible_edges: list[dict[str, Any]] = []
    for edge in all_edges:
        disallowed = sorted(set(edge.get("effects") or []) - admitted_effects)
        if disallowed:
            excluded.append(
                {
                    "capsule_id": edge["capsule_id"],
                    "reason_codes": ["EFFECT_POLICY_DISALLOWED"],
                    "disallowed_effects": disallowed,
                }
            )
            continue
        trust_class = str(
            ((capsule_by_id.get(str(edge.get("capsule_id") or ""), {}).get("implementation") or {}).get("trust_class"))
            or "unspecified"
        )
        trust_mismatches = [
            artifact_type
            for artifact_type in edge.get("produces") or []
            if artifact_type in trust_requirements
            and trust_class not in trust_requirements[artifact_type]
        ]
        if trust_mismatches:
            excluded.append(
                {
                    "capsule_id": edge["capsule_id"],
                    "reason_codes": ["EXECUTION_TRUST_UNSATISFIED"],
                    "trust_class": trust_class,
                    "trust_required_for": sorted(trust_mismatches),
                }
            )
            continue
        policy_eligible_edges.append(edge)
    all_edges = policy_eligible_edges
    excluded = sorted(
        excluded,
        key=lambda row: (str(row.get("capsule_id") or ""), json.dumps(row, sort_keys=True)),
    )

    relevant_types = set(target_outputs)
    relevant_edges: set[str] = set()
    changed = True
    while changed:
        changed = False
        for edge in all_edges:
            if set(edge["produces"]) & relevant_types and edge["edge_id"] not in relevant_edges:
                relevant_edges.add(edge["edge_id"])
                before = len(relevant_types)
                relevant_types.update(edge["consumes"])
                changed = changed or len(relevant_types) > before
    edges = [edge for edge in all_edges if edge["edge_id"] in relevant_edges]
    initial = frozenset(available_inputs)
    initial_lineage = frozenset(
        (
            artifact_type,
            f"input:{lineage_family_by_type[artifact_type]}",
        )
        for artifact_type in initial
        if artifact_type in lineage_family_by_type
    )
    targets = set(target_outputs)
    queue: deque[
        tuple[
            frozenset[str],
            tuple[dict[str, Any], ...],
            frozenset[str],
            frozenset[tuple[str, str]],
        ]
    ] = deque(
        [(initial, tuple(), frozenset(), initial_lineage)]
    )
    # Artifact availability alone is not a sufficient state identity: two
    # different capsule paths may produce the same types and remain legitimate
    # semantic alternatives. Preserve distinct bounded edge-set signatures,
    # while still collapsing order-only permutations of independent steps.
    visited: set[
        tuple[frozenset[str], frozenset[str], frozenset[tuple[str, str]]]
    ] = {(initial, frozenset(), initial_lineage)}
    candidates: list[dict[str, Any]] = []
    explored = 0
    bound_exhausted = False
    reachable_union = set(initial)
    while queue and len(candidates) < max_candidates:
        if explored >= max_states:
            bound_exhausted = True
            break
        artifacts, steps, used_edges, lineage_state = queue.popleft()
        explored += 1
        reachable_union.update(artifacts)
        if targets.issubset(artifacts):
            lineage_by_type = dict(lineage_state)
            target_tokens_by_family: dict[str, set[str]] = {}
            for artifact_type in targets:
                family = lineage_family_by_type.get(artifact_type)
                token = lineage_by_type.get(artifact_type)
                if family and token:
                    target_tokens_by_family.setdefault(family, set()).add(token)
            if any(len(tokens) > 1 for tokens in target_tokens_by_family.values()):
                continue
            candidates.append(
                {
                    "candidate_id": f"composition-{len(candidates) + 1:03d}",
                    "steps": list(steps),
                    "produced_types": sorted(artifacts - initial),
                    "step_count": len(steps),
                    "aggregate_effects": sorted(
                        {
                            effect
                            for step in steps
                            for effect in step.get("effects") or []
                        }
                    ),
                }
            )
            continue
        if len(steps) >= max_depth:
            continue
        for edge in edges:
            edge_id = edge["edge_id"]
            if edge_id in used_edges or not set(edge["consumes"]).issubset(artifacts):
                continue
            lineage_by_type = dict(lineage_state)
            consumed_tokens_by_family: dict[str, set[str]] = {}
            for artifact_type in edge["consumes"]:
                family = lineage_family_by_type.get(artifact_type)
                token = lineage_by_type.get(artifact_type)
                if family and token:
                    consumed_tokens_by_family.setdefault(family, set()).add(token)
            if any(len(tokens) > 1 for tokens in consumed_tokens_by_family.values()):
                continue
            next_lineage = dict(lineage_by_type)
            lineage_conflict = False
            for artifact_type in edge["produces"]:
                family = lineage_family_by_type.get(artifact_type)
                if not family:
                    continue
                consumed_tokens = consumed_tokens_by_family.get(family, set())
                token = (
                    next(iter(consumed_tokens))
                    if consumed_tokens
                    else f"producer:{edge_id}:{family}"
                )
                existing = next_lineage.get(artifact_type)
                if existing and existing != token:
                    lineage_conflict = True
                    break
                next_lineage[artifact_type] = token
            if lineage_conflict:
                continue
            next_artifacts = frozenset(set(artifacts) | set(edge["produces"]))
            if next_artifacts == artifacts:
                continue
            next_used_edges = used_edges | {edge_id}
            next_lineage_state = frozenset(next_lineage.items())
            state_signature = (next_artifacts, next_used_edges, next_lineage_state)
            if state_signature in visited:
                continue
            visited.add(state_signature)
            step = {
                "edge_id": edge_id,
                "edge_kind": edge["edge_kind"],
                "capsule_id": edge["capsule_id"],
                "consumes": edge["consumes"],
                "produces": edge["produces"],
                "effects": edge.get("effects") or [],
            }
            queue.append(
                (
                    next_artifacts,
                    steps + (step,),
                    next_used_edges,
                    next_lineage_state,
                )
            )

    unreachable = sorted(targets - reachable_union)
    blocking_frontiers: list[dict[str, Any]] = []
    if not candidates and not bound_exhausted:
        closure = set(initial)
        changed = True
        while changed:
            changed = False
            for edge in edges:
                if set(edge["consumes"]).issubset(closure):
                    before = len(closure)
                    closure.update(edge["produces"])
                    changed = changed or len(closure) > before
        eligible_producers = {
            artifact_type
            for edge in edges
            for artifact_type in edge["produces"]
        }
        raw_frontiers: list[dict[str, Any]] = []
        for edge in edges:
            missing = sorted(set(edge["consumes"]) - closure)
            if not missing:
                continue
            raw_frontiers.append(
                {
                    "edge_id": edge["edge_id"],
                    "capsule_id": edge["capsule_id"],
                    "produces": edge["produces"],
                    "missing_inputs": [
                        {
                            "artifact_type": artifact_type,
                            "reason_code": (
                                "UPSTREAM_UNREACHABLE"
                                if artifact_type in eligible_producers
                                else "NO_ELIGIBLE_PRODUCER"
                            ),
                        }
                        for artifact_type in missing
                    ],
                }
            )
        blocking_frontiers = sorted(
            raw_frontiers,
            key=lambda row: (len(row["missing_inputs"]), row["edge_id"]),
        )[:20]
    verdict = "candidates_found" if candidates else "search_bound_exhausted" if bound_exhausted else "unsatisfiable"
    artifact = {
        "schema_version": "solar.composition_candidate_search.v1",
        "artifact_role": "planner_candidate_artifact",
        "catalog_ref": {"sha256": _sha256(catalog)},
        "conversion_registry_ref": {"sha256": _sha256(conversion_registry)},
        "available_inputs": sorted(set(available_inputs)),
        "target_outputs": sorted(targets),
        "effect_policy": {"allowed_effects": sorted(admitted_effects)},
        "execution_trust_policy": {
            "required_by_output": [
                {
                    "artifact_type": artifact_type,
                    "allowed_trust_classes": allowed,
                }
                for artifact_type, allowed in sorted(trust_requirements.items())
            ]
        },
        "bounds": {"max_depth": max_depth, "max_states": max_states, "max_candidates": max_candidates},
        "hyperedges": edges,
        "excluded_capsules": excluded,
        "candidates": candidates,
        "unreachable_targets": unreachable,
        "blocking_frontiers": blocking_frontiers,
        "search_stats": {"explored_states": explored, "visited_states": len(visited), "relevant_edge_count": len(edges), "bound_exhausted": bound_exhausted},
        "verdict": verdict,
    }
    _validate(artifact, COMPOSITION_SCHEMA, "composition candidate search")
    return artifact


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
