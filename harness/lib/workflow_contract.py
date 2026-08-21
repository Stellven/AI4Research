#!/usr/bin/env python3
"""Workflow contract layer (Lane 1): load, schema-validate, compile-check,
instantiate, and trigger-match `harness/config/workflows/*.workflow.json`.

Spec: docs/product/opensolar-target-design.md §1.1-1.3, opensolar-requirements.md
R1-R3, workflow-contract-schema.example.json, spec-review dispositions C1+C2.

Contract identity is the NEW top-level `workflow_contract_id` key stamped on the
instantiated task graph. `dag_variant` is NOT overloaded: contracts declare a
value from the existing closed enum (short|standard|parallel_spec|
parallel_delivery|research) so the gate-backfill switches keep working.

Pure module: stdlib + yaml only. No runtime imports (graph_scheduler,
graph_node_dispatcher, capability_capsules are never imported here).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from physical_operator_catalog import is_operator_statically_selectable

try:
    import yaml
except ImportError:  # pragma: no cover - yaml ships with the harness deps
    yaml = None

SCHEMA_VERSION = "solar.workflow_contract.v1"
CONTRACT_FILE_SUFFIX = ".workflow.json"

# The existing closed enum consumed by the gate-backfill switches
# (graph_scheduler.py _ensure_required_gate_node_mapping and codex_pm_router).
DAG_VARIANT_ENUM = {"short", "standard", "parallel_spec", "parallel_delivery", "research"}

NODE_KINDS = {"artifact", "analysis", "code", "verify", "publish"}
EVALUATOR_GATE_KINDS = {"none", "deterministic_command", "llm_eval"}
ON_HUMAN_REVIEW_POLICIES = {"block_dependents", "warn_and_continue"}
STAGES_MODE_FIXED = "fixed"
STAGES_MODE_PLANNER = "planner_generated"

# ---------------------------------------------------------------------------
# Proof-kind vocabulary (schema v1.1 delta per review 5.1): obligations carry an
# explicit proof_kind so node-kind legality never string-matches field names.
# For legacy planner output without proof_kind, classify_obligation() derives it
# from a single mapping table. This module is the single source; the plan
# validator imports these symbols instead of redefining them.
# ---------------------------------------------------------------------------
PROOF_KIND_ARTIFACT_PRESENCE = "artifact_presence"
PROOF_KIND_PATCH_PROOF = "patch_proof"
PROOF_KIND_GATE = "gate"
PROOF_KINDS = {PROOF_KIND_ARTIFACT_PRESENCE, PROOF_KIND_PATCH_PROOF, PROOF_KIND_GATE}

# R2(b) node-kind legality table: patch proofs are legal ONLY on code stages.
NODE_KIND_LEGAL_PROOF_KINDS: Dict[str, frozenset] = {
    "code": frozenset({PROOF_KIND_ARTIFACT_PRESENCE, PROOF_KIND_PATCH_PROOF, PROOF_KIND_GATE}),
    "artifact": frozenset({PROOF_KIND_ARTIFACT_PRESENCE, PROOF_KIND_GATE}),
    "analysis": frozenset({PROOF_KIND_ARTIFACT_PRESENCE, PROOF_KIND_GATE}),
    "verify": frozenset({PROOF_KIND_ARTIFACT_PRESENCE, PROOF_KIND_GATE}),
    "publish": frozenset({PROOF_KIND_ARTIFACT_PRESENCE, PROOF_KIND_GATE}),
}

# Obligation text markers that identify a patch proof in legacy shapes
# (v7 emitted all three: field=patch_diff, check.patch_within_scope,
# "patch_diff exists" pass_conditions).
_PATCH_PROOF_MARKERS = ("patch_diff", "patch_within_scope", "resource_binding.workspace_root")

# Sidecar proof artifacts are produced by the dispatcher/evaluator machinery,
# not by stage outputs; obligations may reference them without declaring them.
SIDECAR_PROOF_FIELDS = {
    "patch_diff",
    "handoff_md",
    "eval_md",
    "eval_json",
    "guard_decision",
    "resource_binding",
    "test_log",
}

# write_scope suffixes that mark a code target (fe2a7d69 rule).
CODE_FILE_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".sh", ".bash", ".zsh", ".ps1",
    ".go", ".rs", ".java", ".kt", ".scala", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".rb", ".php", ".pl", ".lua",
}

# Structured-data / rendered-report deliverables. Their presence in write_scope
# marks a node as artifact-authoring even when a code file is ALSO declared —
# the decoy-`helper.py` resistance the F2 fix needs (a report/inventory node
# that drops a helper script is still artifact-authoring, not a code node).
# `.md` is deliberately excluded: it is a code node's common companion (README /
# handoff) and cannot signal artifact-authoring on its own.
STRUCTURED_ARTIFACT_SUFFIXES = {
    ".json", ".jsonl", ".ndjson", ".html", ".htm",
    ".csv", ".tsv", ".yaml", ".yml", ".xml", ".toml",
}

# node_kind ordering for the "declared node_kind may only narrow, never escalate
# to code" rule (F2). Only `code` legalizes patch proofs.
_NODE_KIND_LEVEL: Dict[str, int] = {
    "analysis": 0, "artifact": 1, "verify": 1, "publish": 1, "code": 2,
}

# Compile error codes (design §1.1). The first four are the required set; the
# remaining codes cover forbidden-block and registry lookups discovered at
# compile time.
ERROR_TASK_TYPE_NOT_ADMITTED = "TASK_TYPE_NOT_ADMITTED"
ERROR_OBLIGATION_UNSATISFIABLE = "OBLIGATION_UNSATISFIABLE_FOR_NODE_KIND"
ERROR_ARTIFACT_ROOT_UNRESOLVED = "ARTIFACT_ROOT_UNRESOLVED"
ERROR_ROUTE_UNRESOLVABLE = "ROUTE_UNRESOLVABLE"
ERROR_CAPSULE_NOT_REGISTERED = "CAPSULE_NOT_REGISTERED"
ERROR_CAPSULE_UNBOUND = "CAPSULE_UNBOUND"
ERROR_FORBIDDEN_CAPSULE = "FORBIDDEN_CAPSULE_IN_STAGE"
ERROR_FORBIDDEN_OBLIGATION = "FORBIDDEN_OBLIGATION_IN_STAGE"
ERROR_OBLIGATION_TARGET_UNDECLARED = "OBLIGATION_TARGET_UNDECLARED"
ERROR_GRAPH_CYCLIC = "GRAPH_CYCLIC"
ERROR_DEP_NOT_FOUND = "DEP_NOT_FOUND"

class ContractSchemaError(ValueError):
    """Raised when a contract document fails schema validation."""

    def __init__(self, source: str, errors: List[str]):
        self.source = source
        self.errors = list(errors)
        super().__init__(f"{source}: {len(self.errors)} schema error(s): " + "; ".join(self.errors))


class ContractInstantiationError(ValueError):
    """Raised when instantiate() is called on a non-instantiable contract."""


def compile_error(code: str, stage_id: Optional[str], message: str, **detail: Any) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "stage_id": stage_id, "message": message}
    for key, value in detail.items():
        if value is not None:
            err[key] = value
    return err


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def harness_dir() -> Path:
    env = os.environ.get("HARNESS_DIR", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1]


def default_workflows_dir() -> Path:
    return harness_dir() / "config" / "workflows"


def default_config_dir() -> Path:
    return harness_dir() / "config"


# ---------------------------------------------------------------------------
# Schema validation + loading
# ---------------------------------------------------------------------------

def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_contract_schema(doc: Any, source: str = "<memory>") -> List[str]:
    """Return schema errors for one contract document (empty list = valid)."""
    errors: List[str] = []
    if not isinstance(doc, dict):
        return [f"contract document must be a JSON object, got {type(doc).__name__}"]

    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}, got {doc.get('schema_version')!r}")
    if not _is_nonempty_str(doc.get("workflow_id")):
        errors.append("workflow_id is required and must be a non-empty string")
    if not _is_nonempty_str(doc.get("version")):
        errors.append("version is required and must be a non-empty string")

    trigger = doc.get("trigger")
    if not isinstance(trigger, dict):
        errors.append("trigger is required and must be an object")
    else:
        markers = trigger.get("explicit_markers", [])
        if not isinstance(markers, list) or any(not _is_nonempty_str(m) for m in markers):
            errors.append("trigger.explicit_markers must be a list of non-empty strings")
        for gate in trigger.get("env_gates", []) or []:
            if not isinstance(gate, dict) or not _is_nonempty_str(gate.get("env")) or "equals" not in gate:
                errors.append("trigger.env_gates entries must be objects with env + equals")

    policy = doc.get("provider_policy")
    if not isinstance(policy, dict):
        errors.append("provider_policy is required and must be an object")
    else:
        providers = policy.get("allowed_providers")
        if not isinstance(providers, list) or not providers or any(not _is_nonempty_str(p) for p in providers):
            errors.append("provider_policy.allowed_providers must be a non-empty list of strings")

    roots = doc.get("artifact_roots")
    if not isinstance(roots, dict) or not _is_nonempty_str(roots.get("canonical")):
        errors.append("artifact_roots.canonical is required and must be a non-empty string")
    else:
        aliases = roots.get("aliases", [])
        if not isinstance(aliases, list) or any(not _is_nonempty_str(a) for a in aliases):
            errors.append("artifact_roots.aliases must be a list of non-empty strings")

    dag_variant = doc.get("dag_variant")
    stages_mode = doc.get("stages_mode", STAGES_MODE_FIXED)
    if stages_mode not in {STAGES_MODE_FIXED, STAGES_MODE_PLANNER}:
        errors.append(f"stages_mode must be {STAGES_MODE_FIXED!r} or {STAGES_MODE_PLANNER!r}, got {stages_mode!r}")

    stages = doc.get("stages", [])
    if stages_mode == STAGES_MODE_PLANNER:
        if stages:
            errors.append("planner_generated contracts must declare an empty stages list")
    else:
        if dag_variant is not None and dag_variant not in DAG_VARIANT_ENUM:
            errors.append(
                f"dag_variant must stay in the closed enum {sorted(DAG_VARIANT_ENUM)}, got {dag_variant!r}"
                " (contract identity lives in workflow_contract_id, never in dag_variant)"
            )
        if not isinstance(stages, list) or not stages:
            errors.append("stages must be a non-empty list for fixed contracts")
        else:
            errors.extend(_validate_stages(stages))

    required_artifacts = doc.get("required_artifacts", [])
    if not isinstance(required_artifacts, list) or any(not _is_nonempty_str(a) for a in required_artifacts):
        errors.append("required_artifacts must be a list of non-empty strings")

    forbidden = doc.get("forbidden", {})
    if forbidden and not isinstance(forbidden, dict):
        errors.append("forbidden must be an object with capsules/proof_obligations lists")

    return errors


def _validate_stages(stages: List[Any]) -> List[str]:
    errors: List[str] = []
    seen_ids: Dict[str, int] = {}
    for index, stage in enumerate(stages):
        label = f"stages[{index}]"
        if not isinstance(stage, dict):
            errors.append(f"{label} must be an object")
            continue
        stage_id = stage.get("id")
        if not _is_nonempty_str(stage_id):
            errors.append(f"{label}.id is required")
            continue
        label = f"stage {stage_id}"
        if stage_id in seen_ids:
            errors.append(f"duplicate stage id {stage_id!r}")
        seen_ids[stage_id] = index

        if stage.get("node_kind") not in NODE_KINDS:
            errors.append(f"{label}.node_kind must be one of {sorted(NODE_KINDS)}, got {stage.get('node_kind')!r}")
        if not _is_nonempty_str(stage.get("task_type")):
            errors.append(f"{label}.task_type is required")
        capsules = stage.get("allowed_capsules")
        if not isinstance(capsules, list) or not capsules or any(not _is_nonempty_str(c) for c in capsules):
            errors.append(f"{label}.allowed_capsules must be a non-empty list of capsule ids")
        if not isinstance(stage.get("depends_on", []), list):
            errors.append(f"{label}.depends_on must be a list")
        outputs = stage.get("outputs", [])
        if not isinstance(outputs, list):
            errors.append(f"{label}.outputs must be a list")
        else:
            for out in outputs:
                if not isinstance(out, dict) or not _is_nonempty_str(out.get("path")) or not _is_nonempty_str(out.get("type")):
                    errors.append(f"{label}.outputs entries must be objects with path + type")
        obligations = stage.get("proof_obligations", [])
        if not isinstance(obligations, list):
            errors.append(f"{label}.proof_obligations must be a list")
        else:
            for ob in obligations:
                if not isinstance(ob, dict) or not _is_nonempty_str(ob.get("kind")) or not _is_nonempty_str(ob.get("requirement")):
                    errors.append(f"{label}.proof_obligations entries must be objects with kind + requirement")
                elif "proof_kind" in ob and ob.get("proof_kind") not in PROOF_KINDS:
                    errors.append(f"{label} obligation proof_kind must be one of {sorted(PROOF_KINDS)}")
        gate = stage.get("evaluator_gate")
        if not isinstance(gate, dict) or gate.get("kind") not in EVALUATOR_GATE_KINDS:
            errors.append(f"{label}.evaluator_gate.kind must be one of {sorted(EVALUATOR_GATE_KINDS)}")
        elif gate.get("on_human_review") is not None and gate.get("on_human_review") not in ON_HUMAN_REVIEW_POLICIES:
            errors.append(f"{label}.evaluator_gate.on_human_review must be one of {sorted(ON_HUMAN_REVIEW_POLICIES)}")
        timeouts = stage.get("timeouts")
        if not isinstance(timeouts, dict) or not isinstance(timeouts.get("result_timeout_sec"), int) or timeouts["result_timeout_sec"] <= 0:
            errors.append(f"{label}.timeouts.result_timeout_sec must be a positive integer")

    # dependency references + acyclicity
    ids = set(seen_ids)
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = stage.get("id")
        for dep in stage.get("depends_on", []) or []:
            if dep not in ids:
                errors.append(f"stage {stage_id} depends_on unknown stage {dep!r}")
    if not errors:
        errors.extend(_check_acyclic(stages))
    return errors


def first_cycle_node(deps: Dict[str, List[str]]) -> Optional[str]:
    """DFS cycle detection over a {node_id: [dep_ids]} map. Returns the id of a
    node involved in a dependency cycle, or None if the graph is acyclic. Shared
    by the schema path (_check_acyclic) and the plan validator (F3)."""
    state: Dict[str, int] = {}

    def visit(node: str) -> bool:
        if state.get(node) == 1:
            return False
        if state.get(node) == 2:
            return True
        state[node] = 1
        for dep in deps.get(node, []):
            if dep in deps and not visit(dep):
                return False
        state[node] = 2
        return True

    for node_id in deps:
        if not visit(node_id):
            return node_id
    return None


def _check_acyclic(stages: List[Dict[str, Any]]) -> List[str]:
    deps = {s["id"]: [d for d in (s.get("depends_on") or [])] for s in stages}
    cyclic = first_cycle_node(deps)
    if cyclic is not None:
        return [f"stage dependency cycle involving {cyclic!r}"]
    return []


def load_contract(path: os.PathLike) -> Dict[str, Any]:
    """Load + schema-validate one contract file. Raises ContractSchemaError."""
    contract_path = Path(path)
    try:
        doc = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractSchemaError(str(contract_path), [f"unreadable contract: {exc}"]) from exc
    errors = validate_contract_schema(doc, source=str(contract_path))
    if errors:
        raise ContractSchemaError(str(contract_path), errors)
    doc["_source_path"] = str(contract_path)
    return doc


def load_all_contracts(
    workflows_dir: Optional[os.PathLike] = None,
    skip_invalid: bool = False,
) -> List[Dict[str, Any]]:
    """Load every *.workflow.json in the registry dir, sorted by filename.

    With skip_invalid=True (the router path, F12), a malformed contract file is
    skipped and logged to stderr rather than aborting the whole load — one
    poisoned file must not break routing for every request. Strict callers
    (compile/instantiate of a named contract) keep the default and surface the
    ContractSchemaError.
    """
    directory = Path(workflows_dir) if workflows_dir else default_workflows_dir()
    contracts: List[Dict[str, Any]] = []
    if not directory.is_dir():
        return contracts
    for path in sorted(directory.glob(f"*{CONTRACT_FILE_SUFFIX}")):
        try:
            contracts.append(load_contract(path))
        except ContractSchemaError as exc:
            if not skip_invalid:
                raise
            print(
                f"workflow_contract: skipping malformed contract {path.name}: {exc}",
                file=sys.stderr,
            )
    return contracts


def find_contract(
    workflow_id: str,
    workflows_dir: Optional[os.PathLike] = None,
    skip_invalid: bool = True,
) -> Optional[Dict[str, Any]]:
    """Locate one contract by id. Malformed SIBLINGS are skipped (F12) so a
    poisoned file elsewhere in the registry can't hide a healthy target."""
    for contract in load_all_contracts(workflows_dir, skip_invalid=skip_invalid):
        if contract.get("workflow_id") == workflow_id:
            return contract
    return None


# ---------------------------------------------------------------------------
# Registry loaders (read-only views over the shipped config; no runtime imports)
# ---------------------------------------------------------------------------

def load_capsule_registry(config_dir: Optional[os.PathLike] = None) -> Dict[str, Dict[str, Any]]:
    """Map capability_capsule_id -> {"task_type_in": [...], "manifest_path": ...}.

    Admitted task types come from the capsule's contract.preconditions
    task_type_in check — the same field the runtime admission gate enforces —
    with applicability.task_types as fallback.
    """
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML is required to load the capsule registry")
    directory = Path(config_dir) if config_dir else default_config_dir()
    capsule_dir = directory / "capability-capsules"
    registry: Dict[str, Dict[str, Any]] = {}
    if not capsule_dir.is_dir():
        return registry
    for path in sorted(capsule_dir.glob("*.yaml")):
        try:
            manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(manifest, dict):
            continue
        capsule_id = str(manifest.get("capability_capsule_id") or "").strip()
        if not capsule_id or manifest.get("capsule_kind") not in (None, "capability"):
            continue
        registry[capsule_id] = {
            "capability_capsule_id": capsule_id,
            "task_type_in": sorted(capsule_admitted_task_types(manifest)),
            "produces_patch": capsule_produces_patch(manifest),
            "manifest_path": str(path),
        }
    return registry


def capsule_produces_patch(manifest: Dict[str, Any]) -> bool:
    """True when a capsule's OWN contract declares a code patch as a produced
    output — i.e. it is a code capsule (F2 node-kind authority). Read from the
    capsule's declared outputs / produced artifacts / patch self-check, never
    from planner-controlled node fields."""
    contract = manifest.get("contract") or {}
    outputs = contract.get("outputs") or {}
    for output in outputs.get("required", []) or []:
        if not isinstance(output, dict):
            continue
        if str(output.get("name") or "") == "patch_diff" or str(output.get("type") or "") == "diff":
            return True
    composition = manifest.get("composition") or {}
    for produced in composition.get("produces", []) or []:
        if isinstance(produced, dict) and str(produced.get("type") or "") == "artifact.patch_diff":
            return True
    verification = manifest.get("verification") or {}
    for check in verification.get("self_check", []) or []:
        if "patch_within_scope" in str(check) or "patch_diff" in str(check):
            return True
    return False


def capsule_admitted_task_types(manifest: Dict[str, Any]) -> set:
    admitted: set = set()
    contract = manifest.get("contract") or {}
    for condition in contract.get("preconditions", []) or []:
        if isinstance(condition, dict) and condition.get("check") == "task_type_in":
            admitted.update(str(v) for v in condition.get("values", []) or [])
    if not admitted:
        applicability = manifest.get("applicability") or {}
        admitted.update(str(v) for v in applicability.get("task_types", []) or [])
    return admitted


def load_operator_registry(path: Optional[os.PathLike] = None) -> Dict[str, Dict[str, Any]]:
    registry_path = Path(path) if path else default_config_dir() / "physical-operators.json"
    doc = json.loads(registry_path.read_text(encoding="utf-8"))
    operators = doc.get("operators") if isinstance(doc, dict) else None
    return operators if isinstance(operators, dict) else {}


def resolve_role_operators(
    role: str,
    providers: Optional[Iterable[str]],
    operator_registry: Dict[str, Dict[str, Any]],
    provider_policy: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Enabled + healthy + non-deprecated operators for a role under policy (R2d).

    Provider constraint (R2d): the effective allowed-provider set is stage∩policy
    when both are declared, else whichever is declared. F1 (round-2): an EMPTY
    effective set that arose from a NON-empty constraint (e.g. stage=[openai] under
    policy=[anthropic]) means no provider satisfies both — it must resolve to
    ZERO operators (=> ROUTE_UNRESOLVABLE), never fall through a falsy-empty-set
    short-circuit and "resolve all". Only the genuinely-unconstrained case (no
    stage providers AND no policy) skips the provider filter.
    """
    stage_allowed = set(providers or [])
    policy_allowed = set((provider_policy or {}).get("allowed_providers") or [])
    if stage_allowed and policy_allowed:
        allowed = stage_allowed & policy_allowed
        constrained = True
    elif stage_allowed:
        allowed = stage_allowed
        constrained = True
    elif policy_allowed:
        allowed = policy_allowed
        constrained = True
    else:
        allowed = set()
        constrained = False
    resolved: List[str] = []
    for operator_id, operator in sorted((operator_registry or {}).items()):
        if not isinstance(operator, dict):
            continue
        if not is_operator_statically_selectable(operator):
            continue
        roles = {str(operator.get("role") or "")}
        roles.update(str(r) for r in operator.get("roles", []) or [])
        if role not in roles:
            continue
        if constrained and str(operator.get("provider") or "") not in allowed:
            continue
        resolved.append(operator_id)
    return resolved


# ---------------------------------------------------------------------------
# Obligation / node-kind classification (single source; plan_validator imports)
# ---------------------------------------------------------------------------

def classify_obligation(obligation: Dict[str, Any]) -> str:
    """Return the obligation's proof_kind. Explicit proof_kind wins; legacy
    shapes are classified from one marker table (never scattered string
    matching at the call sites)."""
    explicit = obligation.get("proof_kind")
    if explicit in PROOF_KINDS:
        return explicit
    kind = str(obligation.get("kind") or "").strip().lower()
    if kind in {"gate", "external_verifier"}:
        return PROOF_KIND_GATE
    haystack = " ".join(
        str(obligation.get(key) or "") for key in ("field", "requirement")
    ).lower()
    for marker in _PATCH_PROOF_MARKERS:
        if marker in haystack:
            return PROOF_KIND_PATCH_PROOF
    return PROOF_KIND_ARTIFACT_PRESENCE


def _shape_node_kind(write_scope: Iterable[Any]) -> str:
    """Decoy-resistant write_scope shape (F2). A structured-data/report
    deliverable marks artifact-authoring even when a code file is also declared,
    so a lone decoy `helper.py` cannot escalate an inventory/report node to code.
    No write targets => analysis."""
    suffixes = [Path(str(p).rstrip("/")).suffix.lower() for p in write_scope or []]
    if not suffixes:
        return "analysis"
    if any(s in STRUCTURED_ARTIFACT_SUFFIXES for s in suffixes):
        return "artifact"
    if any(s in CODE_FILE_SUFFIXES for s in suffixes):
        return "code"
    return "artifact"


def classify_node_kind(node: Dict[str, Any], capsule_is_code: Optional[bool] = None) -> str:
    """Effective node_kind for a planner-emitted node (F2 authority correction).

    The bound capsule is the authority — the planner does NOT own node_kind:
      1. shape: decoy-resistant write_scope classification (_shape_node_kind);
      2. declared node_kind may only NARROW (an explicit `code` never escalates
         an artifact shape);
      3. capsule ceiling: a non-code capsule (capsule_is_code=False) can never
         yield a code node, regardless of shape or declared node_kind.
    `capsule_is_code=None` (unknown / no registry) skips the ceiling and relies
    on shape + declared narrowing alone.
    """
    result = _shape_node_kind(node.get("write_scope"))
    declared = node.get("node_kind")
    if declared in NODE_KINDS:
        # narrow only: keep declared when it is at or below the shape's level.
        if _NODE_KIND_LEVEL.get(declared, 1) <= _NODE_KIND_LEVEL.get(result, 1):
            result = declared
    if capsule_is_code is False and _NODE_KIND_LEVEL.get(result, 1) > _NODE_KIND_LEVEL["artifact"]:
        result = "artifact"
    return result


def legal_proof_kinds(node_kind: str) -> frozenset:
    return NODE_KIND_LEGAL_PROOF_KINDS.get(node_kind, NODE_KIND_LEGAL_PROOF_KINDS["artifact"])


# ---------------------------------------------------------------------------
# Root containment
# ---------------------------------------------------------------------------

def _split_segments(path_text: str) -> List[str]:
    return [seg for seg in path_text.replace("\\", "/").split("/") if seg not in ("", ".")]


def _root_matches(path_segments: List[str], root: str) -> bool:
    """Prefix match with `<placeholder>` segments matching any one segment."""
    root_segments = _split_segments(root)
    if len(path_segments) < len(root_segments):
        return False
    for expected, actual in zip(root_segments, path_segments):
        if expected.startswith("<") and expected.endswith(">"):
            continue
        if expected != actual:
            return False
    return True


def resolve_scope_path(path_text: str, artifact_roots: Dict[str, Any]) -> Optional[str]:
    """Normalize-then-check (AC-R2.2): return the matched root name
    ("canonical" or the alias string) or None when the path escapes every
    declared root. Absolute paths and `..` traversal never resolve."""
    raw = str(path_text or "").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", raw):
        return None
    segments = _split_segments(raw)
    if ".." in segments:
        return None
    canonical = str(artifact_roots.get("canonical") or "")
    if canonical and _root_matches(segments, canonical):
        return "canonical"
    for alias in artifact_roots.get("aliases", []) or []:
        if _root_matches(segments, str(alias)):
            return str(alias)
    return None


def bind_scope_roots(
    artifact_roots: Dict[str, Any], substitutions: Dict[str, str]
) -> Dict[str, Any]:
    """Bind contract placeholders before normalize-then-check validation.

    Generic contracts use ``sprints/<sid>/workdir/`` as a compatibility alias.
    Treating ``<sid>`` as an arbitrary segment let a graph name another
    sprint's workdir and still compile.  Bind only caller-supplied, simple
    placeholder values.  Any root that still contains a placeholder after
    binding is removed: ``resolve_scope_path`` deliberately supports
    placeholders for unbound contracts, so leaving one here would restore the
    wildcard this function is meant to eliminate.
    """
    bound = dict(artifact_roots or {})

    def replace(value: Any) -> str:
        text = str(value or "")
        for key, replacement in (substitutions or {}).items():
            token = f"<{str(key)}>"
            safe = str(replacement or "")
            if not re.fullmatch(r"[A-Za-z0-9._-]+", safe) or safe in {".", ".."}:
                continue
            text = text.replace(token, safe)
        return "" if re.search(r"<[^/<>]+>", text) else text

    bound["canonical"] = replace(bound.get("canonical"))
    bound["aliases"] = [
        resolved
        for item in bound.get("aliases", []) or []
        if (resolved := replace(item))
    ]
    return bound


def resolve_current_sprint_control_read(
    path_text: str,
    sprint_id: str,
    policy: Dict[str, Any],
) -> Optional[str]:
    """Return the admitted control-artifact suffix, or ``None``.

    This is intentionally lexical rather than path-normalizing: the contract
    admits exactly ``sprints/<sid>.<suffix>`` for the current sprint.  Absolute
    paths, backslashes, ``./``, traversal, foreign sprint ids, nested paths,
    and trailing slashes are different declarations and fail closed.
    """
    sid = str(sprint_id or "").strip()
    declared = str(path_text or "").strip()
    if (
        not re.fullmatch(r"[A-Za-z0-9._-]+", sid)
        or sid in {".", ".."}
        or str((policy or {}).get("root_policy") or "")
        != "exact_current_sprint_file"
        or str((policy or {}).get("namespace") or "") != "sprints/<sid>."
        or "\\" in declared
    ):
        return None
    prefix = f"sprints/{sid}."
    suffixes = {
        str(item or "").strip()
        for item in (policy or {}).get("suffixes", []) or []
        if str(item or "").strip()
    }
    for suffix in suffixes:
        if "/" in suffix or "\\" in suffix or suffix in {".", ".."}:
            continue
        if declared == f"{prefix}{suffix}":
            return suffix
    return None


def _contained_relative_output(path_text: str) -> bool:
    """Contract stage outputs are canonical-root-relative: they must stay
    relative and traversal-free so canonical_root + path cannot escape."""
    raw = str(path_text or "").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", raw):
        return False
    return ".." not in _split_segments(raw)


# ---------------------------------------------------------------------------
# Compile checks (R2 a-d)
# ---------------------------------------------------------------------------

def _forbidden_sets(contract: Dict[str, Any]) -> tuple:
    forbidden = contract.get("forbidden") or {}
    capsules = {str(c) for c in forbidden.get("capsules", []) or []}
    obligations = {str(o).lower() for o in forbidden.get("proof_obligations", []) or []}
    return capsules, obligations


def _obligation_targets(stage: Dict[str, Any]) -> set:
    targets = {str(out.get("path") or "") for out in stage.get("outputs", []) or []}
    gate = stage.get("evaluator_gate") or {}
    targets.update(str(p) for p in gate.get("inputs_produced_by_this_gate", []) or [])
    return {t for t in targets if t}


def compile_checks(
    contract: Dict[str, Any],
    capsule_registry: Dict[str, Dict[str, Any]],
    operator_registry: Dict[str, Dict[str, Any]],
    provider_policy: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """R2(a-d) over one contract. Empty list = the contract compiles.

    Registry resolvability only — live capacity is R7's bounded-wait territory
    (review disposition 2.1), never a compile concern.
    """
    errors: List[Dict[str, Any]] = []
    policy = provider_policy if provider_policy is not None else (contract.get("provider_policy") or {})
    forbidden_capsules, forbidden_obligations = _forbidden_sets(contract)

    for role in contract.get("required_roles", []) or []:
        resolved = resolve_role_operators(str(role), None, operator_registry, policy)
        if not resolved:
            errors.append(_route_error(None, str(role), (policy or {}).get("allowed_providers")))

    for stage in contract.get("stages", []) or []:
        stage_id = str(stage.get("id"))
        task_type = str(stage.get("task_type") or "")
        node_kind = str(stage.get("node_kind") or "")
        allowed_capsules = [str(c) for c in stage.get("allowed_capsules", []) or []]

        # forbidden capsules (contract-local hard exclusions, e.g. the RSI lock
        # forbidding the implementation capsule on report stages)
        for capsule_id in allowed_capsules:
            if capsule_id in forbidden_capsules:
                errors.append(compile_error(
                    ERROR_FORBIDDEN_CAPSULE, stage_id,
                    f"stage {stage_id} admits capsule {capsule_id} which the contract forbids",
                    declared=capsule_id,
                ))

        # R2(a): task_type admitted by EVERY allowed capsule
        for capsule_id in allowed_capsules:
            capsule = (capsule_registry or {}).get(capsule_id)
            if capsule is None:
                errors.append(compile_error(
                    ERROR_CAPSULE_NOT_REGISTERED, stage_id,
                    f"stage {stage_id} references capsule {capsule_id} which is not in the capsule registry",
                    declared=capsule_id,
                ))
                continue
            admitted = sorted(capsule.get("task_type_in") or [])
            if task_type not in admitted:
                errors.append(compile_error(
                    ERROR_TASK_TYPE_NOT_ADMITTED, stage_id,
                    f"stage {stage_id}: task_type {task_type!r} is not admitted by capsule "
                    f"{capsule_id} (admitted: {admitted})",
                    declared=task_type, admitted=admitted,
                ))

        # R2(b): obligation kinds legal for node_kind; targets declared
        targets = _obligation_targets(stage)
        legal = legal_proof_kinds(node_kind)
        for obligation in stage.get("proof_obligations", []) or []:
            haystack = " ".join(
                str(obligation.get(key) or "") for key in ("field", "requirement")
            ).lower()
            for marker in forbidden_obligations:
                if marker and marker in haystack:
                    errors.append(compile_error(
                        ERROR_FORBIDDEN_OBLIGATION, stage_id,
                        f"stage {stage_id} carries proof obligation matching forbidden marker {marker!r}",
                        declared=obligation.get("field") or obligation.get("requirement"),
                    ))
            proof_kind = classify_obligation(obligation)
            if proof_kind not in legal:
                errors.append(compile_error(
                    ERROR_OBLIGATION_UNSATISFIABLE, stage_id,
                    f"stage {stage_id}: obligation "
                    f"{obligation.get('field') or obligation.get('requirement')!r} classifies as "
                    f"{proof_kind} which is unsatisfiable for node_kind={node_kind!r} "
                    f"(legal: {sorted(legal)})",
                    declared=proof_kind, admitted=sorted(legal),
                ))
                continue
            field = str(obligation.get("field") or "")
            if proof_kind == PROOF_KIND_ARTIFACT_PRESENCE and field:
                if field not in targets and field not in SIDECAR_PROOF_FIELDS:
                    errors.append(compile_error(
                        ERROR_OBLIGATION_TARGET_UNDECLARED, stage_id,
                        f"stage {stage_id}: obligation references {field!r} which is neither a "
                        f"declared output nor a gate-produced input nor a runtime sidecar",
                        declared=field, admitted=sorted(targets | SIDECAR_PROOF_FIELDS),
                    ))

        # R2(c): outputs contained in declared roots
        for output in stage.get("outputs", []) or []:
            path_text = str(output.get("path") or "")
            if not _contained_relative_output(path_text):
                errors.append(compile_error(
                    ERROR_ARTIFACT_ROOT_UNRESOLVED, stage_id,
                    f"stage {stage_id}: output path {path_text!r} escapes the declared artifact roots "
                    f"(canonical: {contract.get('artifact_roots', {}).get('canonical')!r})",
                    declared=path_text,
                ))

        # R2(d): role resolves to >=1 enabled, healthy, non-deprecated operator
        allowed_operators = stage.get("allowed_operators") or {}
        role = str(allowed_operators.get("role") or "builder")
        providers = allowed_operators.get("providers")
        if not resolve_role_operators(role, providers, operator_registry, policy):
            errors.append(_route_error(stage_id, role, providers or (policy or {}).get("allowed_providers")))
        gate = stage.get("evaluator_gate") or {}
        if gate.get("kind") == "llm_eval":
            eval_role = str(gate.get("role") or "evaluator")
            if not resolve_role_operators(eval_role, None, operator_registry, policy):
                errors.append(_route_error(stage_id, eval_role, (policy or {}).get("allowed_providers")))

    return errors


def _route_error(stage_id: Optional[str], role: str, providers: Any) -> Dict[str, Any]:
    provider_text = sorted(str(p) for p in providers) if providers else "any"
    return compile_error(
        ERROR_ROUTE_UNRESOLVABLE, stage_id,
        f"{'stage ' + stage_id if stage_id else 'contract'}: no enabled, healthy, non-deprecated "
        f"operator resolves for role={role!r} providers={provider_text}. Remediation: enable a "
        f"matching operator in harness/config/physical-operators.json or widen the contract's "
        f"provider_policy.allowed_providers.",
        resolved=[], declared=role,
    )


# ---------------------------------------------------------------------------
# Instantiation (R3): byte-identical for identical inputs
# ---------------------------------------------------------------------------

def _substitute(value: Any, inputs: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        for key in sorted(inputs):
            value = value.replace(f"<{key}>", str(inputs[key]))
        return value
    if isinstance(value, list):
        return [_substitute(item, inputs) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, inputs) for key, item in value.items()}
    return value


def _acceptance_lines(stage: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for obligation in stage.get("proof_obligations", []) or []:
        if str(obligation.get("kind")) != "acceptance":
            continue
        requirement = str(obligation.get("requirement") or "")
        if "value" in obligation:
            lines.append(f"{requirement}={json.dumps(obligation['value'], sort_keys=True)}")
        else:
            lines.append(requirement)
    return lines


def instantiate(contract: Dict[str, Any], inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Emit the existing task-graph format from a fixed contract.

    Deterministic: no timestamps, no sampling; run identity (sprint_id) is a
    caller-provided input. Identical (contract, inputs) => identical bytes via
    canonical_graph_json().
    """
    if contract.get("stages_mode", STAGES_MODE_FIXED) == STAGES_MODE_PLANNER:
        raise ContractInstantiationError(
            f"contract {contract.get('workflow_id')!r} declares planner-generated stages; "
            "its graphs come from the LLM planner and are checked by plan_validator, not instantiated"
        )
    substitutions = dict(inputs or {})
    canonical_root = _substitute(
        str(contract.get("artifact_roots", {}).get("canonical") or ""), substitutions
    )
    # <resolved_root> = the resolved WORKSPACE dir that CONTAINS the canonical
    # artifact dir (its parent), derived here so contract-level commands like
    # `validate_rsi_demo_report.py --workspace <resolved_root>` substitute
    # deterministically (that validator's ROOT constant is the artifact dir
    # basename, so --workspace must be the parent; P3 rehearsal blocker:
    # intake failed closed on UNRESOLVED_PLACEHOLDERS ['resolved_root']).
    # Caller-provided inputs win via setdefault.
    if canonical_root:
        parent = Path(canonical_root.rstrip("/")).parent.as_posix()
        substitutions.setdefault("resolved_root", "" if parent == "." else parent)

    nodes: List[Dict[str, Any]] = []
    required_gates: List[str] = []
    for stage in contract.get("stages", []) or []:
        gate_family = stage.get("gate_family")
        if gate_family and gate_family not in required_gates:
            required_gates.append(gate_family)
        outputs = []
        write_scope = []
        for output in stage.get("outputs", []) or []:
            rel_path = _substitute(str(output.get("path") or ""), substitutions)
            full_path = _join_root(canonical_root, rel_path)
            entry = {"path": full_path, "type": output.get("type")}
            if output.get("demo_artifact"):
                entry["demo_artifact"] = True
            if output.get("evidence_schema"):
                entry["evidence_schema"] = str(output["evidence_schema"])
            outputs.append(entry)
            write_scope.append(full_path)
        obligations = []
        for obligation in stage.get("proof_obligations", []) or []:
            stamped = _substitute(copy.deepcopy(obligation), substitutions)
            stamped["proof_kind"] = classify_obligation(obligation)
            obligations.append(stamped)
        gate = _substitute(copy.deepcopy(stage.get("evaluator_gate") or {"kind": "none"}), substitutions)
        node: Dict[str, Any] = {
            "id": stage["id"],
            "goal": stage.get("goal") or stage.get("dashboard_label") or stage["id"],
            "depends_on": list(stage.get("depends_on", []) or []),
            "gate_family": gate_family,
            "node_kind": stage.get("node_kind"),
            "logical_operator": stage.get("logical_operator"),
            "task_type": stage.get("task_type"),
            "dispatch_task_type": stage.get("task_type"),
            "capability_capsule_id": (stage.get("allowed_capsules") or [None])[0],
            "allowed_capsules": list(stage.get("allowed_capsules", []) or []),
            "allowed_operators": copy.deepcopy(stage.get("allowed_operators")),
            "write_scope": write_scope,
            "outputs": outputs,
            "proof_obligations": obligations,
            "acceptance": _acceptance_lines(stage),
            "evaluator_gate": gate,
            "dashboard_label": stage.get("dashboard_label"),
            "timeouts": copy.deepcopy(stage.get("timeouts") or {}),
            "status": "pending",
        }
        on_human_review = (stage.get("evaluator_gate") or {}).get("on_human_review")
        if on_human_review:
            node["on_human_review"] = on_human_review
        # The gate's on_fail policy IS the node's repair budget: "fail" means
        # no repair cycle (the D6 publish gate), "repair_once_then_fail" means
        # exactly one — consumed by the existing _node_repair_max_attempts
        # lookup. Stamped at instantiation so it is contract-determined and
        # golden-visible, not a runtime default.
        on_fail = str((stage.get("evaluator_gate") or {}).get("on_fail") or "")
        if on_fail == "fail":
            node["max_repair_attempts"] = 0
        elif on_fail == "repair_once_then_fail":
            node["max_repair_attempts"] = 1
        nodes.append(node)

    graph: Dict[str, Any] = {
        "sprint_id": str(substitutions.get("sprint_id", "")),
        "workflow_contract_id": contract.get("workflow_id"),
        "workflow_contract_version": contract.get("version"),
        "dag_variant": contract.get("dag_variant"),
        "title": contract.get("title"),
        "required_gates": required_gates,
        "provider_policy": copy.deepcopy(contract.get("provider_policy") or {}),
        "artifact_roots": _substitute(copy.deepcopy(contract.get("artifact_roots") or {}), substitutions),
        "validator_command": _substitute(contract.get("validator_command"), substitutions),
        "required_artifacts": _substitute(list(contract.get("required_artifacts", []) or []), substitutions),
        "nodes": nodes,
        "node_results": {},
        "gate_results": {},
    }
    if contract.get("source_mode") is not None:
        graph["source_mode"] = copy.deepcopy(contract.get("source_mode"))
    if contract.get("dashboard") is not None:
        graph["dashboard"] = copy.deepcopy(contract.get("dashboard"))
    graph["workflow_contract_hash"] = graph_contract_hash(graph)
    return graph


def _join_root(root: str, rel_path: str) -> str:
    if not root:
        return rel_path
    return root.rstrip("/") + "/" + rel_path.lstrip("/")


_VOLATILE_GRAPH_KEYS = {"sprint_id", "workflow_contract_hash", "node_results", "gate_results", "intent_binding"}
_VOLATILE_NODE_KEYS = {
    # Scheduler/dispatch projection.
    "status",
    "updated_at",
    "assigned_to",
    "pane",
    "dispatch_id",
    "dispatched_via",
    "pm_task_id",
    "operator_id",
    # Runtime-owned selection and recovery state.
    "preferred_model",
    "preferred_profile",
    "preferred_operator",
    "operator_selector",
    "quota_fallback_from",
    "quota_fallback_reason",
    "quota_failure_task_id",
    "quota_recovery_task_ids",
    "repair_attempts",
    "dispatch_retry_reason",
    "dispatch_failure_streak",
    "last_dispatch_failure_reason",
    "last_dispatch_failure_at",
    "dispatch_blocked_reason",
    "last_operator_closeout_failure",
    "last_operator_cooldown_after_closeout",
    "next_action",
    # Execution/evaluation identities and generated evidence references.
    "execution_attempt",
    "execution_attempt_error",
    "execution_attempt_history",
    "eval_assignments",
    "eval_dispatch_id",
    "eval_pm_task_id",
    "eval_json",
    "last_eval_result",
    "last_eval_reason",
}


def _hashable_view(graph: Dict[str, Any]) -> Dict[str, Any]:
    view = {k: v for k, v in graph.items() if k not in _VOLATILE_GRAPH_KEYS}
    view["nodes"] = [
        {k: v for k, v in node.items() if k not in _VOLATILE_NODE_KEYS}
        for node in graph.get("nodes", []) or []
    ]
    return view


def graph_contract_hash(graph: Dict[str, Any]) -> str:
    """Hash of the contract-determined portion of a graph (run identity and
    runtime-mutable fields excluded) — the dispatcher guard's comparison key."""
    payload = json.dumps(_hashable_view(graph), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_graph_json(graph: Dict[str, Any]) -> str:
    return json.dumps(graph, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


# ---------------------------------------------------------------------------
# Trigger matching (R1)
# ---------------------------------------------------------------------------

def match_trigger(
    text: str,
    env: Optional[Dict[str, str]] = None,
    requirement_type: Optional[str] = None,
    contracts: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Resolve free intake text to a workflow_id or None.

    Match paths (F6, round-2): a trigger fires ONLY on an explicit marker in the
    text or the caller-supplied requirement-compiler type. `env_gates` may
    CONSTRAIN a match (an unsatisfied gate, when the contract opts in with
    `env_gates_required`, suppresses an otherwise-firing contract) but never
    CONSTITUTE one — an env gate is never a standalone match path, so demo-mode
    env can no longer route arbitrary text (the f7febf00 bypass fired on ANY
    text). The demo driver is unaffected: its prompts carry the markers. Generic
    words are insufficient by construction: only declared markers match, and the
    longest marker wins across contracts.

    Contracts with a trigger.selection key (explicit-only workflows, the
    pm.generic.v1 fallback) never match free text.
    """
    if contracts is None:
        contracts = load_all_contracts()
    environment = os.environ if env is None else env
    text_lower = str(text or "").lower()

    marker_hits: List[tuple] = []
    requirement_hits: List[str] = []
    for contract in contracts:
        trigger = contract.get("trigger") or {}
        if trigger.get("selection"):
            continue
        workflow_id = str(contract.get("workflow_id") or "")

        # env_gates constrain, never constitute (F6): unsatisfied gates can only
        # SUPPRESS a marker/requirement match, and only when the contract opts in
        # via env_gates_required. A contract whose markers must fire ungated
        # (the RSI demo) simply leaves env_gates permissive.
        env_gates = trigger.get("env_gates", []) or []
        if env_gates and _env_gates_suppress(env_gates, environment, trigger):
            continue

        if text_lower:
            for marker in trigger.get("explicit_markers", []) or []:
                marker_lower = str(marker).lower()
                if marker_lower and marker_lower in text_lower:
                    marker_hits.append((-len(marker_lower), workflow_id))
        declared_type = trigger.get("requirement_compiler_type")
        if requirement_type and declared_type and str(requirement_type) == str(declared_type):
            requirement_hits.append(workflow_id)

    if marker_hits:
        return sorted(marker_hits)[0][1]
    if requirement_hits:
        return sorted(requirement_hits)[0]
    return None


def _env_gates_suppress(
    env_gates: List[Dict[str, Any]], environment: Dict[str, str], trigger: Dict[str, Any]
) -> bool:
    """True when declared env_gates should SUPPRESS this contract's match.

    Default: an env gate is permissive (the f7febf00 demo bypass was additive),
    so it suppresses nothing — it just can no longer fire on its own. A contract
    that genuinely wants its markers gated opts in with
    `trigger.env_gates_required: true`, and then every gate must hold for its
    marker/requirement match to survive.
    """
    if not trigger.get("env_gates_required"):
        return False
    return not all(
        str(environment.get(str(gate.get("env")), "")) == str(gate.get("equals"))
        for gate in env_gates
    )
