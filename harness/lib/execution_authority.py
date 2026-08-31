"""Hash-bound capability definitions for the typed scheduler/dispatcher path."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


# Operational state and credentials are deliberately not frozen as semantics.
OPERATOR_FIELDS = ("backend", "provider", "vendor", "model", "profile", "command",
                   "launch_cmd_kind", "roles", "role", "persona", "execution_trust",
                   "runtime_binding", "resource_capacity", "context_window",
                   "context_tokens", "max_context_tokens", "resource_requirements",
                   "owner_host", "operator_class", "task_types", "capabilities")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def operator_definition(spec: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(spec[key]) for key in OPERATOR_FIELDS if key in spec}


def capture_definitions(registry_path: Path, operators_path: Path) -> dict[str, Any]:
    from capability_capsules import iter_registry_entries, load_capability_capsule_manifest

    capsules = {}
    for entry in iter_registry_entries(path=registry_path, include_draft=True,
                                       include_deprecated=True, include_revoked=True):
        manifest = deepcopy(load_capability_capsule_manifest(Path(entry.manifest_path)))
        # Loader provenance is a machine-local lookup path, not contract meaning.
        manifest.get("provenance", {}).pop("manifest_path", None)
        capsules[entry.capability_capsule_id] = {
            "manifest": manifest, "status": entry.status,
            "default_operator_profile": entry.default_operator_profile,
            "source_sha256": hashlib.sha256(Path(entry.manifest_path).read_bytes()).hexdigest(),
        }
    operators = json.loads(operators_path.read_text(encoding="utf-8"))["operators"]
    return {"capsules": capsules,
            "operators": {key: operator_definition(value) for key, value in operators.items()}}


def freeze_node(node: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    pending = list(node["capsule_binding"]["capsule_ids"])
    capsules: dict[str, Any] = {}
    while pending:
        cid = pending.pop()
        if cid in capsules:
            continue
        row = deepcopy(definitions.get("capsules", {}).get(cid))
        if not row or row.get("status") != "stable":
            raise ValueError(f"CAPSULE_DEFINITION_NOT_ADMITTED:{cid}")
        capsules[cid] = row
        bindings = row["manifest"].get("bindings") or {}
        pending.extend(bindings.get("required_guard_capsules") or [])
        pending.extend(bindings.get("required_resource_capsules") or [])
    operators = {}
    for candidate in node["physical_candidates"]:
        oid = candidate["operator_id"]
        if oid not in definitions.get("operators", {}):
            raise ValueError(f"OPERATOR_DEFINITION_MISSING:{oid}")
        operators[oid] = deepcopy(definitions["operators"][oid])
    value = {"schema_version": "solar.node_execution_authority.v1",
             "capsules": capsules, "operators": operators}
    return {**value, "sha256": digest(value)}


def validate(authority: dict[str, Any]) -> None:
    body = {key: value for key, value in authority.items() if key != "sha256"}
    if (body.get("schema_version") != "solar.node_execution_authority.v1"
            or digest(body) != authority.get("sha256")
            or not isinstance(body.get("capsules"), dict)
            or not isinstance(body.get("operators"), dict)):
        raise ValueError("EXECUTION_AUTHORITY_INVALID")


def check_live_definitions(scheduler_input: dict[str, Any], registry: Path, operators: Path) -> None:
    """Do not freeze a compilation made against definitions changed mid-plan."""
    authorities = [n["execution_authority"] for n in scheduler_input["graph"]["nodes"]
                   if "execution_authority" in n]
    if not authorities:
        return
    current = capture_definitions(registry, operators)
    for authority in authorities:
        for cid, row in authority["capsules"].items():
            if current["capsules"].get(cid) != row:
                raise ValueError(f"CAPSULE_CHANGED_DURING_PLANNING:{cid}")
        for oid, row in authority["operators"].items():
            if current["operators"].get(oid) != row:
                raise ValueError(f"OPERATOR_CHANGED_DURING_PLANNING:{oid}")


def check_operator(authority: dict[str, Any], operator_id: str,
                   current: dict[str, Any]) -> None:
    validate(authority)
    expected = authority["operators"].get(operator_id)
    if expected is None or expected != operator_definition(current):
        raise ValueError(f"FROZEN_OPERATOR_DEFINITION_CHANGED:{operator_id}")


def from_envelope(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """An envelope's self-declared hash is not authority: verify its frozen graph."""
    graph_path = envelope.get("graph_path")
    supplied = envelope.get("execution_authority")
    if not graph_path:
        if supplied:
            raise ValueError("EXECUTION_AUTHORITY_WITHOUT_GRAPH")
        return None
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    if graph.get("schema_version") != "solar.scheduler_runtime_projection.v1":
        if supplied:
            raise ValueError("EXECUTION_AUTHORITY_WITHOUT_TYPED_GRAPH")
        return None
    from scheduler_input import verify_runtime_projection
    verdict = verify_runtime_projection(graph, graph_path=graph_path)
    if not verdict.get("ok"):
        raise ValueError(f"EXECUTION_AUTHORITY_GRAPH_INVALID:{verdict.get('errors')}")
    node = next((row for row in graph["nodes"] if row["id"] == envelope.get("node_id")), None)
    if node is None or graph.get("sprint_id") != envelope.get("sprint_id"):
        raise ValueError("EXECUTION_AUTHORITY_NODE_MISMATCH")
    expected = node.get("execution_authority")
    if expected is None:  # Explicit compatibility for immutable historical runs.
        if supplied:
            raise ValueError("EXECUTION_AUTHORITY_NOT_IN_FROZEN_INPUT")
        return None
    validate(expected)
    if supplied != expected:
        raise ValueError("EXECUTION_AUTHORITY_ENVELOPE_MISMATCH")
    for field in ("capability_capsule_id", "capsule_binding", "artifact_contract",
                  "resource_requirements", "effects", "requirement_ids"):
        if envelope.get(field) != node.get(field):
            raise ValueError(f"EXECUTION_AUTHORITY_FIELD_MISMATCH:{field}")
    if envelope.get("operator_id") not in expected["operators"]:
        raise ValueError("EXECUTION_AUTHORITY_OPERATOR_NOT_ADMITTED")
    approved_operator = expected["operators"][envelope["operator_id"]]
    for field in ("backend", "model", "command", "runtime_binding"):
        if field in approved_operator and envelope.get(field) != approved_operator[field]:
            raise ValueError(f"EXECUTION_AUTHORITY_OPERATOR_OVERRIDE:{field}")
    return deepcopy(expected)
