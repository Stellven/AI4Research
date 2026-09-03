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


def frozen_evaluation_check_ids(graph: dict[str, Any]) -> set[str]:
    """Load check identities from the hash-bound registry frozen for this run.

    ``semantic_evaluator_ids`` is a historical mixed-identity field: current
    planners put evaluation-check IDs in it, while older SchedulerInput
    fixtures may contain physical evaluator IDs.  Prefix inspection is not a
    valid discriminator because registered checks such as
    ``structured_output_parses`` intentionally have no ``check.`` prefix.
    """
    run_contract_ref = graph.get("run_contract_ref")
    if not isinstance(run_contract_ref, dict):
        return set()
    run_contract_path = Path(str(run_contract_ref.get("path") or ""))
    expected_contract_sha = str(run_contract_ref.get("sha256") or "")
    if not run_contract_path.is_file() or not expected_contract_sha:
        raise ValueError("GRAPH_EVAL_CHECK_REGISTRY_INVALID")
    if hashlib.sha256(run_contract_path.read_bytes()).hexdigest() != expected_contract_sha:
        raise ValueError("GRAPH_EVAL_CHECK_REGISTRY_INVALID")
    try:
        run_contract = json.loads(run_contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("GRAPH_EVAL_CHECK_REGISTRY_INVALID") from exc
    registry_ref = run_contract.get("evaluation_check_registry_ref")
    if not isinstance(registry_ref, dict):
        raise ValueError("GRAPH_EVAL_CHECK_REGISTRY_INVALID")
    expected_registry_sha = str(registry_ref.get("sha256") or "")
    registry_path = run_contract_path.parent / "evaluation_check_registry.snapshot.json"
    if not registry_path.is_file() or not expected_registry_sha:
        raise ValueError("GRAPH_EVAL_CHECK_REGISTRY_INVALID")
    if hashlib.sha256(registry_path.read_bytes()).hexdigest() != expected_registry_sha:
        raise ValueError("GRAPH_EVAL_CHECK_REGISTRY_INVALID")
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("GRAPH_EVAL_CHECK_REGISTRY_INVALID") from exc
    return {
        str(row.get("check_id") or "").strip()
        for row in registry.get("checks") or []
        if isinstance(row, dict) and str(row.get("check_id") or "").strip()
    }


def _validate_graph_evaluation_envelope(
    envelope: dict[str, Any],
    node: dict[str, Any],
    *,
    graph: dict[str, Any],
    graph_path: Path,
    current_operator: dict[str, Any] | None = None,
) -> None:
    """Validate the phase-specific authority carried by a graph evaluator.

    An evaluator reviews a frozen node but does not execute that node's
    capability.  Its physical operator therefore cannot be admitted through
    the node's builder ``execution_authority``.  The frozen evaluation binding
    and plan are the semantic authority; the live evaluator registry remains
    the physical pool authority for rubric-backed ``check.*`` bindings.
    """
    if envelope.get("execution_authority"):
        raise ValueError("GRAPH_EVAL_EXECUTION_AUTHORITY_FORBIDDEN")
    if str(envelope.get("requested_role") or "").strip().lower() != "evaluator":
        raise ValueError("GRAPH_EVAL_ROLE_MISMATCH")
    if str(envelope.get("logical_operator") or "").strip() != "Verifier":
        raise ValueError("GRAPH_EVAL_LOGICAL_OPERATOR_MISMATCH")
    if str(envelope.get("capability_capsule_id") or "").strip() != "cap.requirement-compiler-verification":
        raise ValueError("GRAPH_EVAL_CAPSULE_MISMATCH")

    evaluation_binding = node.get("evaluation_binding")
    evaluation_plan = node.get("evaluation_plan")
    if not isinstance(evaluation_binding, dict) or not isinstance(evaluation_plan, dict):
        raise ValueError("GRAPH_EVAL_FROZEN_BINDING_MISSING")
    if envelope.get("evaluation_binding") != evaluation_binding:
        raise ValueError("GRAPH_EVAL_BINDING_MISMATCH")
    if envelope.get("evaluation_plan") != evaluation_plan:
        raise ValueError("GRAPH_EVAL_PLAN_MISMATCH")
    expected_execution_sha = str((node.get("execution_authority") or {}).get("sha256") or "")
    if str(envelope.get("evaluated_execution_authority_sha256") or "") != expected_execution_sha:
        raise ValueError("GRAPH_EVAL_EVALUATED_AUTHORITY_MISMATCH")

    evaluator_ids = [
        str(value or "").strip()
        for value in evaluation_binding.get("semantic_evaluator_ids") or []
        if str(value or "").strip()
    ]
    if not evaluator_ids:
        raise ValueError("GRAPH_EVAL_SEMANTIC_BINDING_MISSING")
    operator_id = str(envelope.get("operator_id") or "").strip()
    registered_check_ids = frozen_evaluation_check_ids(graph)
    physical_ids = [
        value
        for value in evaluator_ids
        if value not in registered_check_ids and not value.startswith("check.")
    ]
    if physical_ids and operator_id not in physical_ids:
        raise ValueError("GRAPH_EVAL_OPERATOR_NOT_ADMITTED")

    if current_operator is not None:
        roles = {
            str(value or "").strip().lower()
            for value in current_operator.get("roles") or []
            if str(value or "").strip()
        }
        for field in ("role", "persona"):
            value = str(current_operator.get(field) or "").strip().lower()
            if value:
                roles.add(value)
        task_classes = {
            str(value or "").strip().lower()
            for value in current_operator.get("task_classes") or []
            if str(value or "").strip()
        }
        if "evaluator" not in roles or "graph_eval" not in task_classes:
            raise ValueError("GRAPH_EVAL_OPERATOR_CLASS_MISMATCH")

    expected_artifacts = envelope.get("expected_artifacts")
    if not isinstance(expected_artifacts, list) or len(expected_artifacts) != 2:
        raise ValueError("GRAPH_EVAL_ARTIFACT_PAIR_INVALID")
    expected_parent = graph_path.resolve().parent
    stems: set[str] = set()
    suffixes: set[str] = set()
    prefix = f"{envelope.get('sprint_id')}.{envelope.get('node_id')}-eval"
    for value in expected_artifacts:
        path = Path(str(value or ""))
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise ValueError("GRAPH_EVAL_ARTIFACT_PAIR_INVALID") from exc
        if resolved.parent != expected_parent:
            raise ValueError("GRAPH_EVAL_ARTIFACT_SCOPE_MISMATCH")
        suffixes.add(resolved.suffix)
        stems.add(resolved.stem)
        if not (resolved.name.startswith(prefix) and resolved.suffix in {".md", ".json"}):
            raise ValueError("GRAPH_EVAL_ARTIFACT_PAIR_INVALID")
    if suffixes != {".md", ".json"} or len(stems) != 1:
        raise ValueError("GRAPH_EVAL_ARTIFACT_PAIR_INVALID")


def from_envelope(
    envelope: dict[str, Any],
    *,
    current_operator: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
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
    if str(envelope.get("task_type") or "").strip().lower() == "graph_eval":
        _validate_graph_evaluation_envelope(
            envelope,
            node,
            graph=graph,
            graph_path=Path(graph_path),
            current_operator=current_operator,
        )
        return None
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
