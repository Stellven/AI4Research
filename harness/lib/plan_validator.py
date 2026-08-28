#!/usr/bin/env python3
"""Plan validator for the generic path (Lane 1, design §1.3).

Applies the same compile-check core as workflow_contract — task_type admission
(R2a), obligation legality by node_kind (R2b), normalize-then-check artifact
root containment (R2c, the pm.generic.v1 root policy), and route resolvability
(R2d) — to planner-emitted task graphs. Error codes and the node-kind legality
table are imported from workflow_contract (single source), never redefined.

The env-gated graph-birth helper below wires that pure validator into the
generic acceptance seams: it stamps pm.generic.v1, persists PASS certificates,
tracks planner-bounce metadata in the errors artifact, and writes the approved
terminal status on exhaustion. Runtime imports remain local to that helper.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_contract as wc  # noqa: E402
import evaluation_budget  # noqa: E402
from executable_node import (  # noqa: E402
    canonical_executable_node,
    logical_operator as executable_logical_operator,
    physical_role as executable_physical_role,
    physical_role_is_compatible,
)
from physical_operator_catalog import is_operator_statically_selectable  # noqa: E402
from planner_operator_gate import operator_task_state  # noqa: E402

GENERIC_CONTRACT_ID = "pm.generic.v1"
AUTOSCI_CONTRACT_ID = "research.autosci.v1"

# Mirrors pm.generic.v1.workflow.json artifact_roots; used only when the
# contract file is unavailable so validation stays runnable standalone.
FALLBACK_ARTIFACT_ROOTS: Dict[str, Any] = {
    "canonical": "workspace/",
    "aliases": ["sprints/<sid>/workdir/", "workdir/"],
    "root_policy": "normalize_then_check",
}

ERRORS_ARTIFACT_SUFFIX = ".plan-compile-errors.json"

# --- P5 G1: planner-graph policy (P5-RUNBOOK owner defaults) ----------------

# R2(e): gate kinds a PLANNER may author. Contracts may waive evaluation with
# "none"; a planner may not — every planner node gets evaluated (llm_eval is
# the default when the gate is absent) unless it runs an allowlisted
# deterministic command.
PLANNABLE_GATE_KINDS = {"llm_eval", "deterministic_command"}

# Launch allowlist (owner decision 2): matched as a TOKEN prefix, not a
# substring — "python3 -m pytest2" must not ride on "python3 -m pytest"
# (vacuous/lookalike-gate hazard, P3 run-2 D2).
GATE_PYTEST_PREFIX = ("python3", "-m", "pytest")

GATE_COMMAND_ALLOWLIST = (
    GATE_PYTEST_PREFIX,
    ("python3", "scripts/validate_rsi_demo_report.py"),
)

# A matched allowlist prefix admits selection/reporting args only. Options
# that change WHAT the gate process imports or which config it loads are
# denied (review G1+G1b finding 3: `python3 -m pytest --co -p <module>`
# imports a caller-named module inside the gate process). Long options are
# matched exactly or as `--opt=value`; two-char short options also match with
# an attached value (`-psample`).
GATE_COMMAND_OPTION_DENYLIST = (
    "-p",              # pytest: load a plugin module by name
    "-c",              # pytest: alternate config file (can inject addopts)
    "-o",              # pytest: override ini values (can inject addopts)
    "--override-ini",
    "--confcutdir",
    "--rootdir",
    "--import-mode",
    "--pyargs",        # interpret args as importable module names
)


def _gate_command_denied_option(tokens: List[str]) -> Optional[str]:
    """First denied option token in an allowlisted command suffix, else None."""
    for token in tokens:
        if not token.startswith("-"):
            continue
        for denied in GATE_COMMAND_OPTION_DENYLIST:
            if token == denied or token.startswith(denied + "="):
                return token
            # attached-value short option: "-psample" (but not "--co" via "-c")
            if len(denied) == 2 and not token.startswith("--") and token.startswith(denied):
                return token
    return None


# Selection options that consume the NEXT token; their value must not be
# mistaken for a positional path. Attached forms (-kexpr, --deselect=x) need
# no entry here.
GATE_COMMAND_VALUE_OPTIONS = (
    "-k", "-m", "-W", "--deselect", "--ignore", "--ignore-glob", "--maxfail", "--tb",
)

# G3 run-9 fix (F-CLASS-16 class closure): the bare repo-tests root is NOT a
# legal generic gate target anymore. Run 5 failed on workspace/-vs-cwd, run 9
# on tests/-vs-workspace/tests — the same class: multiple legal path
# spellings that the planner samples nondeterministically while the builder
# anchors under the artifact root. Generic gate paths must resolve into the
# DECLARED ARTIFACT ROOTS only (canonical workspace/; the workdir aliases
# normalize onto the gate cwd at execution). Under the workdir-cwd execution
# convention a bare tests/ path never pointed at the repo tree anyway.
GATE_PYTEST_TESTS_ROOT = {"canonical": "tests/"}  # retained for reference; no longer consulted


def _gate_pytest_denied_path(tokens: List[str], artifact_roots: Dict[str, Any]) -> Optional[str]:
    """Path-hygiene check for a pytest gate suffix (G2b review finding 3).

    pytest treats every non-option token as a collection path and imports
    conftest.py along it, and a PATHLESS pytest collects the whole gate cwd
    (the harness dir). So positional paths are required, and each must
    normalize-then-check into the repo test root or a declared artifact root —
    the same containment rule as write_scope. Returns the offending token,
    "" when no positional path was given, or None when the suffix is clean.
    """
    positional: List[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            if token in GATE_COMMAND_VALUE_OPTIONS:
                skip_next = True
            continue
        positional.append(token)
    if not positional:
        return ""
    for token in positional:
        path_part = token.split("::", 1)[0]
        if wc.resolve_scope_path(path_part, artifact_roots) is None:
            return token
    return None

# R2(f): the repair-budget ceiling. instantiate stamps 0/1 from on_fail; 2 is
# headroom for future policies. Anything beyond is an unbounded repair loop.
MAX_REPAIR_ATTEMPTS_CEILING = 2

# on_fail -> budget, the workflow_contract.instantiate convention.
ON_FAIL_BUDGETS = {"fail": 0, "repair_once_then_fail": 1}

# R2(g): over-decomposition bound (epic-explosion hazard) when the contract
# does not carry plan_limits.max_nodes.
DEFAULT_MAX_NODES = 12

# Owner decision 2026-07-09 (REVIEW-FIXROUND2 finding 2, option B): operator
# selection is deliberately RUNTIME-owned — quota/auth-failure recovery
# rewrites preferred_profile after PASS (multi_task_runner
# recover_quota_failed_nodes), so these fields stay OUT of the certificate
# hash. The flip side: a planner may not author them either, so the channel
# is runtime-only by construction. Operator constraints a planner MAY
# declare live in allowed_operators (role/providers), which IS governed.
OPERATOR_SELECTION_RUNTIME_FIELDS = (
    "preferred_model",
    "preferred_profile",
    "preferred_operator",
    "operator_selector",
)

ERROR_PLAN_GATE_KIND_ILLEGAL = "PLAN_GATE_KIND_ILLEGAL"
ERROR_PLAN_OPERATOR_SELECTION_FORBIDDEN = "PLAN_OPERATOR_SELECTION_FORBIDDEN"
ERROR_PLAN_CAPABILITY_UNSATISFIABLE = "PLAN_CAPABILITY_UNSATISFIABLE"
ERROR_PLAN_LOGICAL_OPERATOR_MISSING = "PLAN_LOGICAL_OPERATOR_MISSING"
ERROR_PLAN_EXECUTION_ROLE_MISMATCH = "PLAN_EXECUTION_ROLE_MISMATCH"
ERROR_PLAN_EXECUTABLE_NODE_MISMATCH = "PLAN_EXECUTABLE_NODE_MISMATCH"


def _registry_capabilities(operator_registry: Dict[str, Dict[str, Any]]) -> set:
    """Union of capability strings advertised by enabled, non-deprecated
    operators — the only vocabulary a planner may draw
    required_capabilities from (G3 run-7 fix)."""
    available: set = set()
    for record in (operator_registry or {}).values():
        if not isinstance(record, dict):
            continue
        if not is_operator_statically_selectable(record):
            continue
        for cap in record.get("capabilities") or []:
            text = str(cap or "").strip()
            if text:
                available.add(text)
    return available
ERROR_PLAN_GATE_COMMAND_NOT_ALLOWLISTED = "PLAN_GATE_COMMAND_NOT_ALLOWLISTED"
ERROR_PLAN_GATE_OPTION_DENIED = "PLAN_GATE_OPTION_DENIED"
ERROR_PLAN_GATE_PATH_DENIED = "PLAN_GATE_PATH_DENIED"
ERROR_PLAN_READ_SCOPE_UNRESOLVED = "PLAN_READ_SCOPE_UNRESOLVED"
ERROR_PLAN_SPRINT_ID_MISMATCH = "PLAN_SPRINT_ID_MISMATCH"
ERROR_PLAN_REPAIR_BUDGET_MISSING = "PLAN_REPAIR_BUDGET_MISSING"
ERROR_PLAN_GRAPH_EMPTY = "PLAN_GRAPH_EMPTY"
ERROR_PLAN_GRAPH_TOO_LARGE = "PLAN_GRAPH_TOO_LARGE"
ERROR_PLAN_CERTIFICATE_MISSING = "PLAN_CERTIFICATE_MISSING"
ERROR_PLAN_CERTIFICATE_NOT_PASS = "PLAN_CERTIFICATE_NOT_PASS"
ERROR_PLAN_CERTIFICATE_HASH_MISMATCH = "PLAN_CERTIFICATE_HASH_MISMATCH"
ERROR_PLAN_GENERIC_CONTRACT_MISSING = "PLAN_GENERIC_CONTRACT_MISSING"
ERROR_PLAN_GRAPH_MISSING = "PLAN_GRAPH_MISSING"

PLAN_CERTIFICATE_SCHEMA = "solar.plan_certificate.v1"
REQUEST_GOVERNANCE_FIELDS = (
    "source_request_excerpt",
    "source_policy",
    "research_deliverable_contract",
    "pass_conditions",
    "planning_authority",
    "requirement_ir_ref",
    "plan_ir_ref",
    "capsule_plan_ref",
    "physical_plan_ref",
)

# canonical_executable_node is the single source for the GOVERNED node subset
# the certificate hashes. Runtime fields (status, pane, dispatch_id,
# repair_attempts, ...) mutate on every tick and stay outside that contract.
# OPERATOR_SELECTION_RUNTIME_FIELDS are deliberately NOT governed (owner
# decision, REVIEW-FIXROUND2 finding 2 option B): quota recovery must be able
# to rewrite preferred_profile after PASS without invalidating the
# certificate; validate_plan rejects planner-authored values instead.
def _generic_contract(workflows_dir: Optional[os.PathLike] = None) -> Optional[Dict[str, Any]]:
    try:
        return wc.find_contract(GENERIC_CONTRACT_ID, workflows_dir)
    except wc.ContractSchemaError:
        return None


def _node_task_type(node: Dict[str, Any]) -> str:
    for key in ("dispatch_task_type", "task_type", "type"):
        value = str(node.get(key) or "").strip()
        if value:
            return value
    return ""


def _node_role(node: Dict[str, Any]) -> str:
    return executable_physical_role(node)


def _scope_entries(raw: Any) -> List[str]:
    """Normalize the task-graph scope shapes without iterating strings."""
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def validate_plan(
    task_graph: Dict[str, Any],
    capsule_registry: Optional[Dict[str, Dict[str, Any]]],
    operator_registry: Optional[Dict[str, Dict[str, Any]]],
    provider_policy: Optional[Dict[str, Any]] = None,
    contract: Optional[Dict[str, Any]] = None,
    expected_sprint_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Compile-check a planner-emitted task graph. Empty list = plan compiles.

    Registry arguments set to None skip their check family (admission needs
    capsule_registry; routes need operator_registry) so callers can validate
    incrementally; the product call site passes both.
    """
    if contract is None:
        contract = _generic_contract()
    artifact_roots = dict((contract or {}).get("artifact_roots") or FALLBACK_ARTIFACT_ROOTS)
    sprint_id = str(task_graph.get("sprint_id") or "").strip()
    artifact_roots = wc.bind_scope_roots(artifact_roots, {"sid": sprint_id})
    control_read_policy = dict((contract or {}).get("control_plane_read_policy") or {})
    policy = provider_policy
    if policy is None:
        policy = (contract or {}).get("provider_policy")

    errors: List[Dict[str, Any]] = []
    if expected_sprint_id is not None and sprint_id != str(expected_sprint_id).strip():
        errors.append(wc.compile_error(
            ERROR_PLAN_SPRINT_ID_MISMATCH,
            "?",
            f"graph sprint_id {sprint_id!r} does not match the sprint being "
            f"compiled {str(expected_sprint_id).strip()!r}",
            declared=sprint_id,
            expected=str(expected_sprint_id).strip(),
        ))
    for node in task_graph.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "?")
        task_type = _node_task_type(node)

        # A governed planner node has one semantic identity.  Capsule, task,
        # role, scopes, proof gate, scheduler attribution, and UI projection
        # are compiled from this node; accepting an anonymous node lets every
        # downstream seam guess differently (live rc.10 research finding).
        if bool(task_graph.get("plan_compile_required")):
            operator = executable_logical_operator(node)
            if not operator:
                errors.append(wc.compile_error(
                    ERROR_PLAN_LOGICAL_OPERATOR_MISSING,
                    node_id,
                    f"node {node_id} has no logical_operator; every governed "
                    "planner node must declare its semantic operator before "
                    "capsule admission or physical binding",
                ))
            elif not physical_role_is_compatible(node):
                errors.append(wc.compile_error(
                    ERROR_PLAN_EXECUTION_ROLE_MISMATCH,
                    node_id,
                    f"node {node_id}: logical_operator {operator!r} is incompatible "
                    f"with allowed_operators.role={_node_role(node)!r}",
                    declared=_node_role(node),
                ))

            declared_contract = node.get("executable_node")
            expected_contract = canonical_executable_node(node)
            if isinstance(declared_contract, dict) and declared_contract != expected_contract:
                errors.append(wc.compile_error(
                    ERROR_PLAN_EXECUTABLE_NODE_MISMATCH,
                    node_id,
                    f"node {node_id}: executable_node does not match the canonical "
                    "planner fields; derived contracts may not override their source",
                ))

        # The active operator selection is runtime-owned, so a planner may not
        # pre-pin the legacy mutable selector fields. Frozen plans instead use
        # a certificate-governed approved candidate list; the scheduler may
        # choose only within that list as transient availability changes.
        forbidden = [field for field in OPERATOR_SELECTION_RUNTIME_FIELDS if field in node]
        if forbidden:
            errors.append(wc.compile_error(
                ERROR_PLAN_OPERATOR_SELECTION_FORBIDDEN, node_id,
                f"node {node_id} sets runtime-owned operator-selection fields "
                f"{forbidden}; these are not plannable (quota recovery rewrites "
                f"them after certification). Remediation: remove them and "
                f"constrain operators via allowed_operators (role/providers).",
                declared=forbidden,
            ))

        # R2(a): task_type admitted by the node's resolved capsule — the four
        # historical shapes (analysis / tests / implementationworker /
        # logical-op-map-vs-audit-capsule) all fail here (AC-R2.3).
        capsule_id = str(node.get("capability_capsule_id") or "").strip()

        # R2(a) precondition (round-3 Finding A): when a capsule registry is
        # provided, every planner-emitted node MUST bind a capsule. An empty/
        # missing capability_capsule_id skips admission AND leaves capsule_is_code
        # =None below, so the F2 node-kind ceiling never fires — a node declaring
        # node_kind:"code" with a lone workdir/tool.py write_scope would re-legalize
        # patch_diff obligations and compile clean. Reject the unbound node HERE,
        # before classify_node_kind, so it can never reach that ceiling-skip.
        if capsule_registry is not None and not capsule_id:
            errors.append(wc.compile_error(
                wc.ERROR_CAPSULE_UNBOUND, node_id,
                f"node {node_id} has no capability_capsule_id; every planner-emitted "
                f"node must bind a capsule in the registry (an unbound node has no "
                f"task_type admission and no node-kind ceiling, so it cannot be "
                f"compile-checked). Remediation: set capability_capsule_id to a "
                f"registered capsule.",
            ))
            continue

        capsule = capsule_registry.get(capsule_id) if (capsule_registry and capsule_id) else None
        # F2: the bound capsule is the node-kind authority. produces_patch tells
        # classify_node_kind whether the node is even allowed to be code; None
        # (no registry / unknown capsule) falls back to shape + declared narrowing.
        capsule_is_code = capsule.get("produces_patch") if capsule else None
        if capsule_registry is not None and capsule_id:
            if capsule is None:
                errors.append(wc.compile_error(
                    wc.ERROR_CAPSULE_NOT_REGISTERED, node_id,
                    f"node {node_id} references capsule {capsule_id} which is not in the capsule registry",
                    declared=capsule_id,
                ))
            else:
                admitted = sorted(capsule.get("task_type_in") or [])
                if task_type not in admitted:
                    errors.append(wc.compile_error(
                        wc.ERROR_TASK_TYPE_NOT_ADMITTED, node_id,
                        f"node {node_id}: task_type {task_type!r} is not admitted by capsule "
                        f"{capsule_id} (admitted: {admitted})",
                        declared=task_type, admitted=admitted,
                    ))

        # R2(b): obligation legality for the node's (derived) node_kind — the
        # v7 shape: patch_diff obligations on an artifact-authoring node
        # (AC-R2.1, corpus F-049). node_kind is capsule-anchored (F2): a decoy
        # code file or declared node_kind:"code" cannot re-legalize patch proofs.
        node_kind = wc.classify_node_kind(node, capsule_is_code=capsule_is_code)
        legal = wc.legal_proof_kinds(node_kind)
        for obligation in node.get("proof_obligations", []) or []:
            if not isinstance(obligation, dict):
                continue
            proof_kind = wc.classify_obligation(obligation)
            if proof_kind not in legal:
                errors.append(wc.compile_error(
                    wc.ERROR_OBLIGATION_UNSATISFIABLE, node_id,
                    f"node {node_id}: obligation "
                    f"{obligation.get('field') or obligation.get('requirement')!r} classifies as "
                    f"{proof_kind} which is unsatisfiable for node_kind={node_kind!r} "
                    f"(legal: {sorted(legal)}; write_scope has no code targets)",
                    declared=proof_kind, admitted=sorted(legal),
                ))

        # R2(c): normalize-then-check root containment — the v9 shape:
        # write_scope without any declared root prefix (AC-R2.2, corpus F-051).
        for scope_entry in _scope_entries(node.get("write_scope")):
            resolved = wc.resolve_scope_path(str(scope_entry), artifact_roots)
            if resolved is None:
                errors.append(wc.compile_error(
                    wc.ERROR_ARTIFACT_ROOT_UNRESOLVED, node_id,
                    f"node {node_id}: write_scope entry {scope_entry!r} resolves to no declared "
                    f"artifact root (canonical: {artifact_roots.get('canonical')!r}, aliases: "
                    f"{artifact_roots.get('aliases')!r}); a bare relative path is the v9 "
                    f"nondeterminism shape and is rejected, not guessed",
                    declared=str(scope_entry),
                ))

        # Current-sprint control artifacts (compiled requirements, planner
        # design/plan, and the governed graph) live beside the sprint rather
        # than below workspace/.  They are a separate read-only authority,
        # admitted by the generic workflow contract and exact sprint id.  All
        # other reads must resolve through the normal artifact roots; a graph
        # may never smuggle an arbitrary/foreign sprint file into evaluation.
        for scope_entry in _scope_entries(node.get("read_scope")):
            declared = str(scope_entry or "").strip()
            if wc.resolve_scope_path(declared, artifact_roots) is not None:
                continue
            if wc.resolve_current_sprint_control_read(
                declared,
                sprint_id,
                control_read_policy,
            ) is not None:
                continue
            errors.append(wc.compile_error(
                ERROR_PLAN_READ_SCOPE_UNRESOLVED,
                node_id,
                f"node {node_id}: read_scope entry {declared!r} is neither inside "
                "the current sprint's declared artifact roots nor an exact "
                "contract-admitted current-sprint control-plane input",
                declared=declared,
            ))

        # R2(e): gate legality — a planner may not waive evaluation ("none")
        # or run an arbitrary command; deterministic gates come from the
        # launch allowlist only, everything else is llm_eval.
        gate = node.get("evaluator_gate") if isinstance(node.get("evaluator_gate"), dict) else {}
        gate_kind = str(gate.get("kind") or "llm_eval").strip()
        policy_waiver = gate_kind == "none" and evaluation_budget.policy_allows_none(task_graph, node)
        if gate_kind not in PLANNABLE_GATE_KINDS and not policy_waiver:
            errors.append(wc.compile_error(
                ERROR_PLAN_GATE_KIND_ILLEGAL, node_id,
                f"node {node_id}: evaluator_gate.kind {gate_kind!r} is not plannable "
                f"(plannable: {sorted(PLANNABLE_GATE_KINDS)}; contracts may waive "
                f"evaluation, a planner may not)",
                declared=gate_kind, admitted=sorted(PLANNABLE_GATE_KINDS),
            ))
        elif gate_kind == "deterministic_command":
            command_tokens = str(gate.get("command") or "").split()
            matched_prefix = next(
                (
                    prefix
                    for prefix in GATE_COMMAND_ALLOWLIST
                    if command_tokens[: len(prefix)] == list(prefix)
                ),
                None,
            )
            if matched_prefix is None:
                errors.append(wc.compile_error(
                    ERROR_PLAN_GATE_COMMAND_NOT_ALLOWLISTED, node_id,
                    f"node {node_id}: deterministic_command {gate.get('command')!r} does not "
                    f"match the launch allowlist "
                    f"({[' '.join(p) for p in GATE_COMMAND_ALLOWLIST]}); use llm_eval or an "
                    f"allowlisted checker",
                    declared=str(gate.get("command") or ""),
                ))
            else:
                suffix_tokens = command_tokens[len(matched_prefix):]
                denied = _gate_command_denied_option(suffix_tokens)
                if denied is not None:
                    errors.append(wc.compile_error(
                        ERROR_PLAN_GATE_OPTION_DENIED, node_id,
                        f"node {node_id}: deterministic_command {gate.get('command')!r} carries "
                        f"denied option {denied!r} — import/config-control options "
                        f"({', '.join(GATE_COMMAND_OPTION_DENYLIST)}) are not plannable; "
                        f"pass test paths and selection/reporting flags only",
                        declared=denied,
                    ))
                if matched_prefix == GATE_PYTEST_PREFIX:
                    denied_path = _gate_pytest_denied_path(suffix_tokens, artifact_roots)
                    if denied_path == "":
                        errors.append(wc.compile_error(
                            ERROR_PLAN_GATE_PATH_DENIED, node_id,
                            f"node {node_id}: deterministic_command {gate.get('command')!r} names "
                            f"no test path — a pathless pytest collects the whole gate cwd; pass "
                            f"explicit paths under {GATE_PYTEST_TESTS_ROOT['canonical']!r} or a "
                            f"declared artifact root",
                            declared=str(gate.get("command") or ""),
                        ))
                    elif denied_path is not None:
                        errors.append(wc.compile_error(
                            ERROR_PLAN_GATE_PATH_DENIED, node_id,
                            f"node {node_id}: pytest gate path {denied_path!r} resolves to no "
                            f"trusted root — paths must normalize into "
                            f"{GATE_PYTEST_TESTS_ROOT['canonical']!r} or a declared artifact root "
                            f"(canonical: {artifact_roots.get('canonical')!r}, aliases: "
                            f"{[str(a) for a in artifact_roots.get('aliases') or []]}); absolute "
                            f"paths and '..' traversal never resolve",
                            declared=denied_path,
                        ))

        # R2(f): the repair budget is stamped at birth (contract-determined on
        # the fixed path; planner-declared here), never a runtime default.
        budget = node.get("max_repair_attempts")
        if budget is None:
            budget = ON_FAIL_BUDGETS.get(str(gate.get("on_fail") or ""))
        if not isinstance(budget, int) or not (0 <= budget <= MAX_REPAIR_ATTEMPTS_CEILING):
            errors.append(wc.compile_error(
                ERROR_PLAN_REPAIR_BUDGET_MISSING, node_id,
                f"node {node_id}: no stamped repair budget "
                f"(max_repair_attempts int in [0,{MAX_REPAIR_ATTEMPTS_CEILING}], or "
                f"evaluator_gate.on_fail in {sorted(ON_FAIL_BUDGETS)})",
                declared=repr(node.get("max_repair_attempts")),
            ))

        # R2(d): the node's role resolves under the provider policy.
        if operator_registry is not None:
            role = _node_role(node)
            providers = (node.get("allowed_operators") or {}).get("providers")
            if not wc.resolve_role_operators(role, providers, operator_registry, policy):
                errors.append(wc.compile_error(
                    wc.ERROR_ROUTE_UNRESOLVABLE, node_id,
                    f"node {node_id}: no enabled, healthy, non-deprecated operator resolves for "
                    f"role={role!r} under the provider policy. Remediation: enable a matching "
                    f"operator in harness/config/physical-operators.json or widen "
                    f"provider_policy.allowed_providers.",
                    resolved=[], declared=role,
                ))
            # R2(d) capability extension (G3 run 7,
            # p5-g3-live-rung-20260709T225219Z): the planner invented
            # required_capabilities no operator advertises and the CERTIFIED
            # graph wedged forever at dispatch (worker_blocked /
            # no_matching_worker) — "compiles" must imply "dispatchable".
            declared_caps = [
                str(cap) for cap in (node.get("required_capabilities") or [])
                if str(cap or "").strip()
            ]
            if declared_caps:
                available = _registry_capabilities(operator_registry)
                missing = sorted(set(declared_caps) - available)
                if missing:
                    errors.append(wc.compile_error(
                        ERROR_PLAN_CAPABILITY_UNSATISFIABLE, node_id,
                        f"node {node_id}: required_capabilities {missing} are not "
                        f"advertised by any enabled operator "
                        f"(registry vocabulary: {sorted(available) or '[]'}). "
                        f"Remediation: omit required_capabilities, or declare only "
                        f"values from the registry vocabulary.",
                        declared=missing, admitted=sorted(available),
                    ))

    # F3: graph structure — depends_on existence + acyclicity on the planner
    # path (the schema path already had these for fixed contracts). A cyclic or
    # dangling-dep graph must reject at compile, never hang the scheduler.
    errors.extend(_validate_graph_structure(task_graph))

    # R2(g): size bound — an empty plan does nothing; an epic explosion
    # (corpus hazard) is rejected at compile, not discovered at dispatch.
    node_count = len([n for n in task_graph.get("nodes", []) or [] if isinstance(n, dict)])
    max_nodes = ((contract or {}).get("plan_limits") or {}).get("max_nodes") or DEFAULT_MAX_NODES
    if node_count == 0:
        errors.append(wc.compile_error(
            ERROR_PLAN_GRAPH_EMPTY, "?",
            "planner graph has no nodes",
        ))
    elif node_count > int(max_nodes):
        errors.append(wc.compile_error(
            ERROR_PLAN_GRAPH_TOO_LARGE, "?",
            f"planner graph has {node_count} nodes; the bound is {max_nodes} "
            f"(plan_limits.max_nodes / DEFAULT_MAX_NODES) — decompose into epics "
            f"or raise the contract limit deliberately",
            declared=node_count, admitted=int(max_nodes),
        ))

    return errors


# --- P5 G1: plan_certificate (governed graph birth) --------------------------

def plan_certificate_hash(task_graph: Dict[str, Any]) -> str:
    """sha256 over the governed subset — contract identity + per-node policy
    fields. Runtime fields (status/pane/dispatch_id/...) are excluded so
    dispatch cannot invalidate its own certificate."""
    import hashlib

    def governed_node(node: Dict[str, Any]) -> Dict[str, Any]:
        canonical = canonical_executable_node(node)
        materialized = node.get("executable_node")
        governed_record = {
            "canonical": canonical,
            # Stamp writes this projection into the graph so UI/evidence
            # readers consume the same identity.  Hash it independently from
            # the re-derived view: changing either side is tampering.
            "materialized": (
                copy.deepcopy(materialized)
                if isinstance(materialized, dict)
                else canonical
            ),
        }
        request_contract = {
            field: copy.deepcopy(node.get(field))
            for field in REQUEST_GOVERNANCE_FIELDS
            if field in node
        }
        if request_contract:
            governed_record["request_contract"] = request_contract
        return governed_record

    governed = {
        # sprint_id binds the certificate to ONE sprint — a PASS stamped for
        # sprint A must not validate a byte-identical graph smuggled into
        # sprint B (review G1+G1b finding 2).
        "sprint_id": str(task_graph.get("sprint_id") or ""),
        "workflow_contract_id": str(task_graph.get("workflow_contract_id") or ""),
        "workflow_contract_version": str(task_graph.get("workflow_contract_version") or ""),
        "plan_compile_required": task_graph.get("plan_compile_required") is True,
        "planner_stage": copy.deepcopy(task_graph.get("planner_stage") or {}),
        "graph_compiler_artifacts": copy.deepcopy(task_graph.get("graph_compiler_artifacts") or {}),
        "dag_variant": str(task_graph.get("dag_variant") or ""),
        "artifact_roots": copy.deepcopy(task_graph.get("artifact_roots") or {}),
        "required_gates": [str(item) for item in (task_graph.get("required_gates") or [])],
        "evidence_policy": copy.deepcopy(task_graph.get("evidence_policy") or {}),
        "nodes": [
            governed_node(node)
            for node in sorted(
                (n for n in task_graph.get("nodes", []) or [] if isinstance(n, dict)),
                key=lambda n: str(n.get("id") or ""),
            )
        ],
    }
    request_contract = {
        field: copy.deepcopy(task_graph.get(field))
        for field in REQUEST_GOVERNANCE_FIELDS
        if field in task_graph
    }
    if request_contract:
        governed["request_contract"] = request_contract
    canonical = json.dumps(governed, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stamp_plan_certificate(
    task_graph: Dict[str, Any],
    capsule_registry: Optional[Dict[str, Dict[str, Any]]] = None,
    operator_registry: Optional[Dict[str, Dict[str, Any]]] = None,
    contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate and stamp. Raises ValueError on a graph that does not compile —
    a certificate is a PASS verdict, never a participation trophy."""
    errors = validate_plan(task_graph, capsule_registry, operator_registry, contract=contract)
    if errors:
        raise ValueError(
            f"plan does not compile ({len(errors)} errors); refusing to stamp: "
            f"{[e.get('code') for e in errors]}"
        )
    return _stamp_validated_plan_certificate(task_graph)


def _stamp_validated_plan_certificate(task_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp a graph only after its owning compiler has returned no errors.

    Generic graphs call :func:`stamp_plan_certificate`; locked workflow
    proposals such as AutoSci first run their contract-specific compiler and
    then use this shared, private checksum writer.
    """
    import time

    for node in task_graph.get("nodes", []) or []:
        if isinstance(node, dict):
            node["executable_node"] = canonical_executable_node(node)

    certificate = {
        "schema": PLAN_CERTIFICATE_SCHEMA,
        "validator": "plan_validator",
        "verdict": "PASS",
        "graph_hash": plan_certificate_hash(task_graph),
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    task_graph["plan_certificate"] = certificate
    return certificate


def check_plan_certificate(task_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Re-derive the governed hash and compare against the stamped verdict.
    Empty list = the graph is certificate-covered and untampered."""
    certificate = task_graph.get("plan_certificate")
    if not isinstance(certificate, dict) or not certificate:
        return [wc.compile_error(
            ERROR_PLAN_CERTIFICATE_MISSING, "?",
            "planner graph carries no plan_certificate; it was never validated "
            "(or the certificate was stripped)",
        )]
    if str(certificate.get("verdict") or "") != "PASS":
        return [wc.compile_error(
            ERROR_PLAN_CERTIFICATE_NOT_PASS, "?",
            f"plan_certificate verdict is {certificate.get('verdict')!r}, not PASS",
            declared=str(certificate.get("verdict") or ""),
        )]
    expected = plan_certificate_hash(task_graph)
    stamped = str(certificate.get("graph_hash") or "")
    if stamped != expected:
        return [wc.compile_error(
            ERROR_PLAN_CERTIFICATE_HASH_MISMATCH, "?",
            "plan_certificate.graph_hash does not match the governed graph "
            "content — a governed field changed after validation "
            f"(stamped {stamped[:12]}..., recomputed {expected[:12]}...)",
            declared=stamped, admitted=expected,
        )]
    return []


def _graph_compiler_artifact_errors(
    task_graph: Dict[str, Any],
    *,
    sprints_dir: os.PathLike,
    sid: str,
) -> List[Dict[str, Any]]:
    """Verify Graph Compiler evidence files bound into an AutoSci certificate."""
    import hashlib

    declared = task_graph.get("graph_compiler_artifacts")
    if not isinstance(declared, dict):
        return [_error("AUTOSCI_GRAPH_COMPILER_ARTIFACTS_MISSING", "GC0", "graph_compiler_artifacts hash manifest is missing")]
    errors: List[Dict[str, Any]] = []
    for suffix in ("design.md", "plan.md"):
        path = Path(sprints_dir) / f"{sid}.{suffix}"
        try:
            payload = path.read_bytes()
        except OSError:
            payload = b""
        expected = str((declared.get(suffix) or {}).get("sha256") or "")
        actual = hashlib.sha256(payload).hexdigest() if payload else ""
        if not payload or actual != expected:
            errors.append(
                _error(
                    "AUTOSCI_GRAPH_COMPILER_ARTIFACT_HASH_MISMATCH",
                    "GC0",
                    f"Graph Compiler artifact {path.name} is missing, empty, or differs from its certificate manifest",
                    declared=expected,
                    admitted=actual,
                )
            )
    return errors


def _validate_graph_structure(task_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = [n for n in task_graph.get("nodes", []) or [] if isinstance(n, dict)]
    node_ids = {str(n.get("id")) for n in nodes if n.get("id") is not None}
    errors: List[Dict[str, Any]] = []
    deps_map: Dict[str, List[str]] = {}
    for node in nodes:
        if node.get("id") is None:
            continue
        node_id = str(node.get("id"))
        deps = [str(d) for d in (node.get("depends_on") or [])]
        deps_map[node_id] = deps
        for dep in deps:
            if dep not in node_ids:
                errors.append(wc.compile_error(
                    wc.ERROR_DEP_NOT_FOUND, node_id,
                    f"node {node_id} depends_on {dep!r} which is not a node in this graph",
                    declared=dep,
                ))
    cyclic = wc.first_cycle_node(deps_map)
    if cyclic is not None:
        errors.append(wc.compile_error(
            wc.ERROR_GRAPH_CYCLIC, cyclic,
            f"node {cyclic!r} is part of a depends_on cycle; the graph is not a DAG",
            declared=cyclic,
        ))
    return errors


def write_errors_artifact(
    sprints_dir: os.PathLike,
    sid: str,
    errors: List[Dict[str, Any]],
    *,
    bounce_count: Optional[int] = None,
    graph_hash: Optional[str] = None,
    exhausted: Optional[bool] = None,
    terminal: Optional[bool] = None,
) -> Path:
    """Write <sid>.plan-compile-errors.json atomically (design §1.3); the
    caller appends these to the planner re-dispatch prompt."""
    sprints = Path(sprints_dir)
    sprints.mkdir(parents=True, exist_ok=True)
    target = sprints / f"{sid}{ERRORS_ARTIFACT_SUFFIX}"
    payload = {
        "sid": sid,
        "error_count": len(errors),
        "errors": errors,
        "terminal_state_on_exhaustion": "PLAN_COMPILE_FAILED",
    }
    if bounce_count is not None:
        payload["bounce_count"] = int(bounce_count)
    if graph_hash is not None:
        payload["graph_hash"] = str(graph_hash)
    if exhausted is not None:
        payload["exhausted"] = bool(exhausted)
    if terminal is not None:
        payload["terminal"] = bool(terminal)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def _env_gate_enabled() -> bool:
    # G4 default-on: the validator is the runtime default; explicit 0 kills it.
    return str(os.environ.get("SOLAR_PLAN_VALIDATOR", "") or "").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _is_epic_graph(task_graph: Dict[str, Any]) -> bool:
    schema = str(task_graph.get("schema_version") or "")
    return schema.startswith("solar.epic.")


def _generic_graph_kind(
    task_graph: Dict[str, Any],
    workflows_dir: Optional[os.PathLike] = None,
) -> str:
    """Governed-vs-grandfathered classification (G4 blocker 2, owner decision
    2026-07-10: default-on with grandfathering).

    "generic" (governed — certificate demanded) iff the graph CLAIMS
    pm.generic.v1 (claiming the contract is never a free pass) OR carries
    the intake birth marker `plan_compile_required` (stamped by the
    requirement compiler on every template skeleton and restored from the
    runtime-owned sprint status before compile/dispatch). An uncontracted
    graph WITHOUT the marker is "legacy_uncontracted" — hand-authored
    graphs, direct multi-task CLI usage, old chain flows — and every guard
    skips it, keeping legacy behavior byte-identical under default-on."""
    contract_id = str(task_graph.get("workflow_contract_id") or "").strip()
    if _is_epic_graph(task_graph):
        return "epic_graph"
    if contract_id == GENERIC_CONTRACT_ID:
        return "generic"
    if task_graph.get("plan_compile_required"):
        if contract_id:
            try:
                contract = wc.find_contract(contract_id, workflows_dir)
            except wc.ContractSchemaError:
                contract = None
            if contract and contract.get("stages_mode") == getattr(wc, "STAGES_MODE_PLANNER", "planner_generated"):
                return "planner_generated_contract"
            if contract:
                return "non_generic_contract"
            return (
                "unregistered_planner_contract"
                if contract_id == AUTOSCI_CONTRACT_ID
                else "non_generic_contract"
            )
        return "generic"
    if contract_id:
        return "non_generic_contract"
    return "legacy_uncontracted"


def _planner_contract(
    task_graph: Dict[str, Any],
    *,
    workflows_dir: Optional[os.PathLike] = None,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Resolve the contract that owns Planner compilation for this graph."""
    contract_id = str(task_graph.get("workflow_contract_id") or "").strip()
    if not contract_id:
        contract_id = GENERIC_CONTRACT_ID
    try:
        return contract_id, wc.find_contract(contract_id, workflows_dir)
    except wc.ContractSchemaError:
        return contract_id, None


def _with_status_plan_provenance(
    task_graph: Dict[str, Any],
    *,
    sprints_dir: Optional[os.PathLike] = None,
    sid: str = "",
) -> Dict[str, Any]:
    """Restore compiler-owned governance after a planner replaces the graph.

    Planner output is not an authority for whether a request was born on the
    governed generic path.  That provenance is persisted in ``status.json``
    and overlaid onto a copy here, leaving genuinely hand-authored legacy
    graphs (which have no status marker) unchanged.
    """
    resolved_sid = str(sid or (task_graph or {}).get("sprint_id") or "").strip()
    if (
        not sprints_dir
        or not resolved_sid
        or (task_graph or {}).get("plan_compile_required") is True
    ):
        return task_graph
    try:
        status = json.loads(
            (Path(sprints_dir) / f"{resolved_sid}.status.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        return task_graph
    if not isinstance(status, dict) or status.get("plan_compile_required") is not True:
        return task_graph
    restored = copy.deepcopy(task_graph)
    restored["plan_compile_required"] = True
    return restored


def _error(code: str, node_id: str, message: str, **extra: Any) -> Dict[str, Any]:
    try:
        return wc.compile_error(code, node_id, message, **extra)
    except Exception:
        out = {"code": code, "node_id": node_id, "message": message}
        out.update(extra)
        return out


def _graph_hash_for_bounce(
    task_graph: Dict[str, Any],
    contract_version: str = "",
    contract_id: str = GENERIC_CONTRACT_ID,
) -> str:
    candidate = copy.deepcopy(task_graph)
    candidate["workflow_contract_id"] = contract_id
    candidate["workflow_contract_version"] = contract_version
    candidate.pop("plan_certificate", None)
    return plan_certificate_hash(candidate)


def _read_errors_artifact(sprints_dir: Path, sid: str) -> Dict[str, Any]:
    path = sprints_dir / f"{sid}{ERRORS_ARTIFACT_SUFFIX}"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


STATUS_BOUNCE_KEY = "plan_compile_bounces"


def _read_status_bounce(sprints_dir: Path, sid: str) -> Dict[str, Any]:
    try:
        data = json.loads((sprints_dir / f"{sid}.status.json").read_text(encoding="utf-8"))
        value = data.get(STATUS_BOUNCE_KEY)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _record_status_bounce(sprints_dir: Path, sid: str, bounce_count: int, graph_hash: str) -> None:
    """Mirror the bounce budget into <sid>.status.json (review G1+G1b finding
    4: the errors artifact was the ONLY store, and deleting it reset the retry
    budget so a graph never terminalized). Metadata merge only — status/phase
    are untouched, and transition_status preserves unknown keys, so the record
    survives later transitions.

    G2b review finding 4: the merge goes through the locked
    runtime_status.merge_status_fields — a stale full-object write here could
    revert a status transition that landed between read and write."""
    status_path = sprints_dir / f"{sid}.status.json"
    if not status_path.exists():
        return
    try:
        from runtime_status import merge_status_fields  # noqa: WPS433

        merge_status_fields(status_path, {
            STATUS_BOUNCE_KEY: {
                "bounce_count": int(bounce_count),
                "graph_hash": str(graph_hash),
            },
        })
    except Exception:
        pass


def _bounce_count_for_failure(sprints_dir: Path, sid: str, graph_hash: str) -> int:
    # Consult BOTH stores and trust the higher counter — the errors artifact
    # alone is deletable (finding 4).
    previous = max(
        (_read_errors_artifact(sprints_dir, sid), _read_status_bounce(sprints_dir, sid)),
        key=lambda record: int(record.get("bounce_count") or 0),
    )
    previous_count = int(previous.get("bounce_count") or 0)
    if previous.get("graph_hash") == graph_hash and previous_count > 0:
        return previous_count
    return previous_count + 1


def _plan_compile_config(contract: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict((contract or {}).get("plan_compile") or {})


def _max_planner_bounces(contract: Optional[Dict[str, Any]]) -> int:
    try:
        return int(_plan_compile_config(contract).get("max_planner_bounces") or 2)
    except Exception:
        return 2


def record_certificate_mismatch_refusal(
    sprints_dir: os.PathLike,
    task_graph: Dict[str, Any],
    errors: Optional[List[Any]],
) -> Dict[str, Any]:
    """Terminalize a sprint whose PASS-certified graph was refused at dispatch.

    Scope: ONLY PLAN_CERTIFICATE_HASH_MISMATCH. An uncertified refusal
    (PLAN_CERTIFICATE_MISSING) is the normal pre-planner / bounce state and
    must never terminalize (the E5 starvation class). A stamped graph whose
    governed content changed is unrecoverable at dispatch time — re-stamping
    here would launder the edit — so the sprint fails closed with a truthful
    terminal state. G3 live rung (p5-g3-live-rung-20260709T161420Z): without
    this, the guard re-refused every coordinator tick and the sprint sat
    drafting/spec for ~40 minutes until the run budget expired non-terminal.

    Best-effort and idempotent: callers invoke it from dispatch guards on
    every refusal; an already-failed sprint is left alone."""
    out: Dict[str, Any] = {"attempted": False}
    if not _env_gate_enabled():
        return out
    codes = {
        str(error.get("code") or "")
        for error in (errors or [])
        if isinstance(error, dict)
    }
    if ERROR_PLAN_CERTIFICATE_HASH_MISMATCH not in codes:
        return out
    sid = str((task_graph or {}).get("sprint_id") or "")
    if not sid:
        return out
    sprints = Path(sprints_dir)
    status_path = sprints / f"{sid}.status.json"
    if not status_path.exists():
        out["error"] = f"status_missing:{status_path}"
        return out
    current = _read_status_value(status_path)
    if current == "failed":
        return out
    try:
        from runtime_status import transition_status  # noqa: WPS433

        updated, message = transition_status(
            status_path,
            "failed",
            "plan_certificate_invalid",
            "plan_validator",
            extra={
                "reason": "PLAN_CERTIFICATE_HASH_MISMATCH",
                "status_fields": {
                    "phase": "plan_certificate_invalid",
                    "handoff_to": "",
                    "target_role": "",
                    "plan_compile_state": "PLAN_CERTIFICATE_INVALID",
                },
            },
        )
        out.update({"attempted": True, "ok": True, "status": updated, "message": message})
    except Exception as exc:
        out.update({"attempted": True, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    try:
        import gate_ledger  # noqa: WPS433

        gate_ledger.record_status_transition(
            sprints,
            sid,
            "__sprint__",
            from_status=current,
            to_status="plan_certificate_invalid",
            author_type="policy",
            writer="plan_validator",
            note="PLAN_CERTIFICATE_HASH_MISMATCH",
        )
    except Exception:
        pass
    return out


def _transition_plan_compile_failed(sprints_dir: Path, sid: str, from_status: str) -> Dict[str, Any]:
    status_path = sprints_dir / f"{sid}.status.json"
    out: Dict[str, Any] = {"attempted": False}
    if not status_path.exists():
        out["error"] = f"status_missing:{status_path}"
        return out
    try:
        from runtime_status import transition_status  # noqa: WPS433

        updated, message = transition_status(
            status_path,
            "failed",
            "plan_compile_failed",
            "plan_validator",
            extra={
                "reason": "PLAN_COMPILE_FAILED",
                "status_fields": {
                    "phase": "plan_compile_failed",
                    "handoff_to": "",
                    "target_role": "",
                    "plan_compile_state": "PLAN_COMPILE_FAILED",
                },
            },
        )
        out.update({"attempted": True, "ok": True, "status": updated, "message": message})
    except Exception as exc:
        out.update({"attempted": True, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    try:
        import gate_ledger  # noqa: WPS433

        gate_ledger.record_status_transition(
            sprints_dir,
            sid,
            "__sprint__",
            from_status=from_status,
            to_status="plan_compile_failed",
            author_type="policy",
            writer="plan_validator",
            note="PLAN_COMPILE_FAILED",
        )
    except Exception:
        pass
    return out


def compile_planner_graph(
    sprints_dir: os.PathLike,
    sid: str,
    *,
    config_dir: Optional[os.PathLike] = None,
    workflows_dir: Optional[os.PathLike] = None,
) -> Dict[str, Any]:
    """Env-gated generic graph compile/stamp helper for acceptance seams."""
    verdict: Dict[str, Any] = {
        "ok": True,
        "stamped": False,
        "skipped_reason": "",
        "errors": [],
        "bounce_count": 0,
        "exhausted": False,
        "terminal": False,
    }
    if not _env_gate_enabled():
        verdict["skipped_reason"] = "env_off"
        return verdict

    sprints = Path(sprints_dir)
    graph_path = sprints / f"{sid}.task_graph.json"
    if not graph_path.exists():
        error = _error(ERROR_PLAN_GRAPH_MISSING, "?", f"task_graph not found: {graph_path}")
        write_errors_artifact(sprints, sid, [error], bounce_count=0, exhausted=False, terminal=False)
        return {**verdict, "ok": False, "errors": [error], "skipped_reason": "graph_missing"}

    task_graph = _with_status_plan_provenance(
        json.loads(graph_path.read_text(encoding="utf-8")),
        sprints_dir=sprints,
        sid=sid,
    )
    graph_kind = _generic_graph_kind(task_graph, workflows_dir)
    if graph_kind not in {"generic", "planner_generated_contract"}:
        verdict["skipped_reason"] = graph_kind
        return verdict

    # Certification is a Solar lifecycle decision, not an action the bounded
    # Graph Compiler may take while it is still writing artifacts. Its
    # operator-pool task must publish a durable successful result before any
    # candidate graph can be stamped. Legacy pane compilation has no matching
    # PM task record and remains supported as ``unmanaged``.
    operator_gate = operator_task_state(
        sprints.parent,
        sid,
        "GC0",
        role="builder",
        closeout_kind="task_graph_compiler",
    )
    if not operator_gate["ready_for_compile"]:
        return {
            **verdict,
            "ok": False,
            "deferred": True,
            "skipped_reason": "graph_compiler_operator_not_complete",
            "operator_gate": operator_gate,
        }

    contract_id, contract = _planner_contract(task_graph, workflows_dir=workflows_dir)
    if contract is None:
        error = _error(
            ERROR_PLAN_GENERIC_CONTRACT_MISSING,
            "?",
            f"{contract_id} workflow contract is missing; refusing ungoverned planner acceptance",
        )
        graph_hash = _graph_hash_for_bounce(task_graph, contract_id=contract_id)
        bounce_count = _bounce_count_for_failure(sprints, sid, graph_hash)
        _record_status_bounce(sprints, sid, bounce_count, graph_hash)
        max_bounces = _max_planner_bounces(None)
        exhausted = bounce_count >= max_bounces
        terminal_status: Dict[str, Any] = {}
        if exhausted:
            current = _read_status_value(sprints / f"{sid}.status.json")
            terminal_status = _transition_plan_compile_failed(sprints, sid, current)
        write_errors_artifact(
            sprints,
            sid,
            [error],
            bounce_count=bounce_count,
            graph_hash=graph_hash,
            exhausted=exhausted,
            terminal=exhausted,
        )
        return {
            **verdict,
            "ok": False,
            "errors": [error],
            "bounce_count": bounce_count,
            "exhausted": exhausted,
            "terminal": exhausted,
            "terminal_status": terminal_status,
        }

    contract_version = str(contract.get("version") or "")
    existing_certificate_valid = False
    if (
        str(task_graph.get("workflow_contract_id") or "") == contract_id
        and str(task_graph.get("workflow_contract_version") or "") == contract_version
    ):
        cert_errors = check_plan_certificate(task_graph)
        if not cert_errors:
            # A certificate is a content checksum, not a signature.  A planner
            # can calculate it too, so the already-certified fast path is legal
            # only after the current semantic compiler independently accepts
            # the graph below.
            existing_certificate_valid = True

    directory = Path(config_dir) if config_dir else wc.default_config_dir()
    capsules = wc.load_capsule_registry(directory)
    operators = wc.load_operator_registry(directory / "physical-operators.json")
    candidate = copy.deepcopy(task_graph)
    candidate["workflow_contract_id"] = contract_id
    candidate["workflow_contract_version"] = contract_version
    candidate.pop("plan_certificate", None)

    if contract_id == AUTOSCI_CONTRACT_ID:
        import hashlib
        from autosci_intake_contract import validate_autosci_planner_graph  # noqa: WPS433

        errors: List[Dict[str, Any]] = []
        graph_compiler_artifacts: Dict[str, Any] = {}
        for suffix in ("design.md", "plan.md"):
            artifact_path = sprints / f"{sid}.{suffix}"
            try:
                artifact_bytes = artifact_path.read_bytes()
            except OSError:
                artifact_bytes = b""
            if not artifact_bytes.strip():
                errors.append(
                    _error(
                        "AUTOSCI_GRAPH_COMPILER_ARTIFACT_MISSING",
                        "GC0",
                        f"Graph Compiler artifact is missing or empty: {artifact_path}",
                    )
                )
            else:
                graph_compiler_artifacts[suffix] = {
                    "path": artifact_path.name,
                    "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                }
        planner_stage = dict(candidate.get("planner_stage") or {})
        planner_stage.update({"status": "requirements_handoff_complete", "completed_by": "planner_operator"})
        candidate["planner_stage"] = planner_stage
        candidate["graph_compiler_stage"] = {
            "role": "graph_compiler",
            "node_id": "GC0",
            "status": "compiled",
            "completed_by": "task_graph_compiler",
        }
        candidate["graph_compiler_artifacts"] = graph_compiler_artifacts
        requirement_ir_path = sprints / f"{sid}.requirement_ir.json"
        expected_request_text = ""
        try:
            requirement_ir = json.loads(requirement_ir_path.read_text(encoding="utf-8"))
            source_inputs = requirement_ir.get("source_inputs") if isinstance(requirement_ir, dict) else {}
            if isinstance(source_inputs, dict):
                expected_request_text = str(source_inputs.get("raw_request") or "").strip()
            if not expected_request_text and isinstance(requirement_ir, dict):
                expected_request_text = str(requirement_ir.get("user_intent") or "").strip()
        except (OSError, ValueError, TypeError):
            expected_request_text = ""
        if not expected_request_text:
            errors.append(
                _error(
                    "AUTOSCI_SOURCE_REQUEST_MISSING",
                    "N0",
                    f"Immutable AutoSci source request is missing from {requirement_ir_path}",
                )
            )
        errors.extend(validate_autosci_planner_graph(
            candidate,
            harness_dir=wc.harness_dir(),
            expected_sprint_id=sid,
            expected_request_text=expected_request_text,
        ))
    else:
        errors = validate_plan(
            candidate,
            capsules,
            operators,
            contract=contract,
            expected_sprint_id=sid,
        )
    if not errors:
        if existing_certificate_valid:
            verdict["skipped_reason"] = "already_certified"
            return verdict
        if contract_id == AUTOSCI_CONTRACT_ID:
            _stamp_validated_plan_certificate(candidate)
        else:
            stamp_plan_certificate(candidate, capsules, operators, contract=contract)
        _atomic_write_json(graph_path, candidate)
        return {**verdict, "stamped": True, "workflow_contract_id": contract_id}

    graph_hash = _graph_hash_for_bounce(candidate, contract_version, contract_id)
    bounce_count = _bounce_count_for_failure(sprints, sid, graph_hash)
    _record_status_bounce(sprints, sid, bounce_count, graph_hash)
    max_bounces = _max_planner_bounces(contract)
    exhausted = bounce_count >= max_bounces
    terminal_status = {}
    if exhausted:
        current = _read_status_value(sprints / f"{sid}.status.json")
        terminal_status = _transition_plan_compile_failed(sprints, sid, current)
    write_errors_artifact(
        sprints,
        sid,
        errors,
        bounce_count=bounce_count,
        graph_hash=graph_hash,
        exhausted=exhausted,
        terminal=exhausted,
    )
    return {
        **verdict,
        "ok": False,
        "errors": errors,
        "bounce_count": bounce_count,
        "exhausted": exhausted,
        "terminal": exhausted,
        "terminal_status": terminal_status,
    }


def _read_status_value(status_path: Path) -> str:
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        return str(data.get("status") or "")
    except Exception:
        return ""


def check_planner_graph_dispatchable(
    task_graph: Dict[str, Any],
    *,
    sprints_dir: Optional[os.PathLike] = None,
    sid: str = "",
) -> Dict[str, Any]:
    """Read-only dispatch-boundary check for generic planner graphs."""
    verdict: Dict[str, Any] = {"ok": True, "skipped_reason": "", "errors": []}
    if not _env_gate_enabled():
        verdict["skipped_reason"] = "env_off"
        return verdict
    effective_graph = _with_status_plan_provenance(
        task_graph or {}, sprints_dir=sprints_dir, sid=sid
    )
    graph_kind = _generic_graph_kind(effective_graph)
    if graph_kind == "unregistered_planner_contract":
        contract_id = str(effective_graph.get("workflow_contract_id") or "")
        return {
            "ok": False,
            "reason": "plan_validator_dispatch_refused",
            "errors": [
                _error(
                    ERROR_PLAN_GENERIC_CONTRACT_MISSING,
                    "?",
                    f"{contract_id} workflow contract is missing or not planner-generated",
                )
            ],
        }
    if graph_kind not in {"generic", "planner_generated_contract"}:
        verdict["skipped_reason"] = graph_kind
        return verdict
    contract_id, contract = _planner_contract(effective_graph)
    if contract is None:
        return {
            "ok": False,
            "reason": "plan_validator_dispatch_refused",
            "errors": [
                _error(
                    ERROR_PLAN_GENERIC_CONTRACT_MISSING,
                    "?",
                    f"{contract_id} workflow contract is missing; refusing planner-governed dispatch",
                )
            ],
        }
    graph_version = str(effective_graph.get("workflow_contract_version") or "")
    contract_version = str(contract.get("version") or "")
    if str(effective_graph.get("workflow_contract_id") or "") == contract_id and graph_version != contract_version:
        return {
            "ok": False,
            "reason": "plan_validator_dispatch_refused",
            "errors": [
                _error(
                    "WORKFLOW_CONTRACT_VERSION_MISMATCH",
                    "?",
                    f"{contract_id} version mismatch: graph={graph_version!r}, contract={contract_version!r}",
                    declared=graph_version,
                    admitted=contract_version,
                )
            ],
        }
    errors = check_plan_certificate(effective_graph)
    if not errors and contract_id == AUTOSCI_CONTRACT_ID:
        if not sprints_dir or not str(sid or effective_graph.get("sprint_id") or "").strip():
            errors = [
                _error(
                    "AUTOSCI_PLANNER_ARTIFACTS_UNCHECKABLE",
                    "N0",
                    "AutoSci dispatch requires sprints_dir and sid to verify Planner artifacts",
                )
            ]
        else:
            errors = _graph_compiler_artifact_errors(
                effective_graph,
                sprints_dir=sprints_dir,
                sid=str(sid or effective_graph.get("sprint_id") or ""),
            )
    if errors:
        return {
            "ok": False,
            "reason": "plan_validator_dispatch_refused",
            "errors": errors,
        }
    return verdict


_POLICY_BLOCK_MAX_ERRORS = 12


def planner_compile_policy_block(
    sprints_dir: Optional[os.PathLike] = None,
    sid: str = "",
    *,
    config_dir: Optional[os.PathLike] = None,
    workflows_dir: Optional[os.PathLike] = None,
) -> str:
    """Prompt block for planner dispatch: what a compilable graph must contain.

    G2 battery measurement (p5-g2-battery-20260708T205146Z): compile_rate 0.0,
    CAPSULE_UNBOUND x20, PLAN_REPAIR_BUDGET_MISSING x3 — the live planner was
    never told the compile rules, so it emitted bare nodes. This block is the
    single source both planner objective builders append.

    Env-gated like every generic-path seam: returns "" when
    SOLAR_PLAN_VALIDATOR is off, so legacy prompts stay byte-identical. The
    capsule list, gate allowlist, and size bound are rendered from the live
    registry/contract, never hardcoded. When sprints_dir+sid are given and a
    bounce artifact exists, the previous compile errors are appended so a
    bounced planner repairs the named defects instead of re-guessing."""
    if not _env_gate_enabled():
        return ""

    from research.source_pack import CANONICAL_SOURCE_TYPES

    if sprints_dir and sid:
        try:
            governed_graph = json.loads(
                (Path(sprints_dir) / f"{sid}.task_graph.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError):
            governed_graph = {}
        if str(governed_graph.get("workflow_contract_id") or "") == AUTOSCI_CONTRACT_ID:
            return "\n".join(
                [
                    f"## Plan compile policy ({AUTOSCI_CONTRACT_ID})",
                    "",
                    "This is an AutoSci graph PROPOSAL, not a Builder-ready graph.",
                    "You are the distinct Graph Compiler stage (GC0), downstream of Planner. Do not execute any Scientific* Builder node.",
                    "Read the Planner requirements/handoff plus PRD, contract, requirement IR, and proposed task graph; preserve the locked",
                    "Scientific* node set, dependencies, logical operators, capability capsules, scopes, and gates.",
                    "Produce design.md, plan.md, and a valid task_graph.json, finish every artifact write, then return from this bounded",
                    "Graph Compiler invocation. Do not execute graph nodes and do not edit lifecycle status.",
                    "After your durable operator result succeeds, Solar alone runs plan_validator, stamps any",
                    "PASS certificate, and transitions the sprint to planning_complete. Never self-declare it.",
                ]
            )

    contract = _generic_contract(workflows_dir)
    artifact_roots = dict((contract or {}).get("artifact_roots") or FALLBACK_ARTIFACT_ROOTS)
    artifact_roots = wc.bind_scope_roots(artifact_roots, {"sid": str(sid or "")})
    control_policy = dict((contract or {}).get("control_plane_read_policy") or {})
    max_nodes = ((contract or {}).get("plan_limits") or {}).get("max_nodes") or DEFAULT_MAX_NODES
    canonical_root = str(artifact_roots.get("canonical") or "workspace/")
    aliases = [str(a) for a in (artifact_roots.get("aliases") or [])]
    allowlist = [" ".join(prefix) for prefix in GATE_COMMAND_ALLOWLIST]
    control_sid = str(sid or "<sid>")
    control_reads = [
        f"sprints/{control_sid}.{str(suffix)}"
        for suffix in control_policy.get("suffixes", []) or []
        if str(suffix or "").strip()
    ]

    lines: List[str] = [
        "## Plan compile policy (pm.generic.v1)",
        "",
        "Your task_graph.json is compile-checked BEFORE any node is dispatched.",
        "A graph that violates any rule below is bounced back to you with error",
        "codes, and the sprint terminalizes after the bounce budget. Every node",
        "MUST satisfy:",
        "",
        "0. logical_operator — required. Every node declares one semantic",
        "   operator. The validator compiles that together with capsule, task",
        "   type, scopes, proof gate, and allowed physical role into one certified executable-node identity.",
        "   Do not omit it and do not encode semantic identity only in goal text.",
        "1. capability_capsule_id — bind one registered capsule from the list at",
        "   the end; an unbound node fails CAPSULE_UNBOUND.",
        "2. task_type / dispatch_task_type — must be in the bound capsule's",
        "   admitted task_type_in list (TASK_TYPE_NOT_ADMITTED otherwise).",
        "3. evaluator_gate — {\"kind\": \"llm_eval\", \"on_fail\": \"fail\" |",
        "   \"repair_once_then_fail\"}. \"none\" is not plannable",
        "   (PLAN_GATE_KIND_ILLEGAL). \"deterministic_command\" only with a",
        f"   command from the allowlist: {allowlist}; import/config-control",
        f"   options ({', '.join(GATE_COMMAND_OPTION_DENYLIST)}) are denied",
        "   (PLAN_GATE_OPTION_DENIED). A pytest gate must name explicit test",
        "   paths inside a DECLARED ARTIFACT ROOT — put suite files under",
        f"   {canonical_root!r} (e.g. {canonical_root}tests/test_x.py) and use",
        "   exactly that spelling in the gate command; bare tests/, pathless,",
        "   absolute, or traversing paths fail PLAN_GATE_PATH_DENIED. The gate",
        "   executes FROM the sprint workdir with --noconftest, so keep",
        "   fixtures inside the test files.",
        f"4. max_repair_attempts — integer 0..{MAX_REPAIR_ATTEMPTS_CEILING}, or",
        "   derivable from evaluator_gate.on_fail; a node with neither fails",
        "   PLAN_REPAIR_BUDGET_MISSING.",
        f"5. write_scope — every entry under a declared artifact root (canonical:",
        f"   {canonical_root!r}, aliases: {aliases}); a bare relative path fails",
        "   ARTIFACT_ROOT_UNRESOLVED.",
        "6. read_scope — each entry must be under the exact current sprint's",
        "   artifact roots, or one of the contract-admitted current-sprint control-plane",
        f"   inputs: {control_reads}. Foreign sprint ids, arbitrary suffixes, absolute",
        "   paths, traversal, and noncanonical spellings fail PLAN_READ_SCOPE_UNRESOLVED.",
        "7. proof_obligations — legal for the node kind the capsule defines",
        "   (patch_diff proofs only on patch-producing capsules;",
        "   OBLIGATION_UNSATISFIABLE otherwise).",
        "8. operator selection — do NOT set preferred_model, preferred_profile,",
        "   preferred_operator, or operator_selector; those fields are",
        "   runtime-owned (quota fallback rewrites them) and fail",
        "   PLAN_OPERATOR_SELECTION_FORBIDDEN. Constrain operators only via",
        "   allowed_operators (role/providers).",
        "9. required_capabilities — OMIT this field unless strictly needed.",
        "   If declared, every value must come from the registered operator",
        "   capability vocabulary listed at the end; an invented capability",
        "   fails PLAN_CAPABILITY_UNSATISFIABLE (no worker could ever match",
        "   it and the node would never dispatch).",
        "10. graph shape — non-empty, acyclic, depends_on only references node",
        f"   ids in this graph, at most {int(max_nodes)} nodes.",
        "",
        "## Rule of evidence (research prompts)",
        "",
        "Research planning is shape-free: there is no required research DAG.",
        "Use as many parallel retrieval, contradiction-check, synthesis, and",
        "verification nodes as the question needs, while obeying the graph rules",
        "above. The artifact contract, not a fixed node topology, is mandatory:",
        "- Retrieval nodes bind cap.research-retrieval and write a source pack",
        "  containing sources.jsonl, evidence.jsonl, and extracts/ with fetched",
        "  source text, provenance metadata, and verifying hashes.",
        "- Claim-producing nodes bind cap.requirement-research-synthesizer, consume",
        "  one or more verified source-pack directories through read_scope, and",
        "  write a solar.grounded_synthesis_plan.v2 synthesis_plan.json. It must",
        "  declare evidence_status=sufficient|insufficient and evidence_gaps.",
        "  Every publishable claim must provide evidence_links; each link names",
        "  an evidence_id, relation (supports, contradicts, qualifies, or",
        "  contextualizes), and an exact quote copied from that evidence row.",
        "  Each quote must be a focused 20-2000 character source span.",
        "  Claims with contradictory links must explain uncertainty. If evidence",
        "  is insufficient, declare the bounded gap and do not invent sections.",
        "  Minimal v2 shape:",
        '  {"schema_version":"solar.grounded_synthesis_plan.v2",',
        '   "evidence_status":"sufficient","evidence_gaps":[],"sections":[{',
        '   "section_id":"findings","title":"Findings","claims":[{',
        '   "text":"...","claim_type":"factual","confidence":0.8,',
        '   "evidence_links":[{"evidence_id":"ev_...","relation":"supports",',
        '   "quote":"exact text copied from evidence.jsonl"}]}]}]}',
        "  Each compiled section needs at least one cited claim and 220 rendered",
        "  characters; use substantive evidence-backed claims, not padding.",
        "- Publish the grounded bundle only through the deterministic boundary:",
        "  solar-harness research compile-grounded --source-pack <pack> [--source-pack <pack> ...]",
        "    --synthesis-plan <synthesis_plan.json> --output-dir <report-dir>",
        "    --question <research-question>",
        "  The compiler writes verified sources/evidence/extracts, claims.jsonl,",
        "  claim_evidence.jsonl, evidence_gaps.json, sections/checks, report_ast.json, bibliography,",
        "  research_eval.json, and cited final.md. Do not hand-author substitutes",
        "  for those governed artifacts. Never invent a citation, URL, quote,",
        "  source, or retrieved fact.",
        "- source_type must use the canonical vocabulary: "
        + ", ".join(CANONICAL_SOURCE_TYPES)
        + ".",
        "- If retrieval cannot obtain sufficient evidence, fail or state the",
        "  bounded evidence gap instead of replacing source text with model prose.",
        "",
        "Registered capsules (capability_capsule_id -> admitted task types):",
    ]
    try:
        directory = Path(config_dir) if config_dir else wc.default_config_dir()
        registry = wc.load_capsule_registry(directory)
    except Exception:
        registry = {}
    if registry:
        for capsule_id in sorted(registry):
            admitted = sorted((registry.get(capsule_id) or {}).get("task_type_in") or [])
            lines.append(f"- {capsule_id}: {admitted}")
    else:
        lines.append("- (capsule registry unavailable at prompt-render time; use")
        lines.append("  harness/config/capability-capsules/ ids verbatim)")

    # G3 run-7 fix: the vocabulary rule 8 references, rendered live.
    try:
        operator_registry = wc.load_operator_registry(directory / "physical-operators.json")
        vocabulary = sorted(_registry_capabilities(operator_registry))
    except Exception:
        vocabulary = []
    lines.append("")
    if vocabulary:
        lines.append(f"Registered operator capabilities (required_capabilities vocabulary): {vocabulary}")
    else:
        lines.append("Registered operator capabilities: NONE — omit required_capabilities entirely.")

    if sprints_dir is not None and sid:
        previous = _read_errors_artifact(Path(sprints_dir), sid)
        errors = previous.get("errors") if isinstance(previous.get("errors"), list) else []
        if errors:
            bounce_count = int(previous.get("bounce_count") or 0)
            lines += [
                "",
                f"## Previous compile errors (bounce {bounce_count}; fix these exactly)",
                "",
            ]
            for error in errors[:_POLICY_BLOCK_MAX_ERRORS]:
                if not isinstance(error, dict):
                    continue
                lines.append(
                    f"- {error.get('code')} [{error.get('node_id', '?')}]: "
                    f"{error.get('message', '')}"
                )
            if len(errors) > _POLICY_BLOCK_MAX_ERRORS:
                lines.append(f"- (+{len(errors) - _POLICY_BLOCK_MAX_ERRORS} more in {sid}{ERRORS_ARTIFACT_SUFFIX})")

    return "\n".join(lines)


def validate_plan_file(
    graph_path: os.PathLike,
    config_dir: Optional[os.PathLike] = None,
    workflows_dir: Optional[os.PathLike] = None,
) -> List[Dict[str, Any]]:
    task_graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    directory = Path(config_dir) if config_dir else wc.default_config_dir()
    capsules = wc.load_capsule_registry(directory)
    operators = wc.load_operator_registry(directory / "physical-operators.json")
    contract = _generic_contract(workflows_dir)
    return validate_plan(task_graph, capsules, operators, contract=contract)


def _main_compile_generic(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="plan_validator compile-generic")
    parser.add_argument("sid")
    parser.add_argument("--sprints-dir", required=True)
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--workflows-dir", default=None)
    args = parser.parse_args(argv)
    try:
        verdict = compile_planner_graph(
            args.sprints_dir,
            args.sid,
            config_dir=args.config_dir,
            workflows_dir=args.workflows_dir,
        )
    except Exception as exc:
        print(f"plan_validator: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, indent=2, sort_keys=True, ensure_ascii=True))
    if verdict.get("ok"):
        return 0
    if verdict.get("deferred"):
        return 5
    if verdict.get("terminal") or verdict.get("exhausted"):
        return 4
    return 3


def _main_check_generic_dispatch(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="plan_validator check-generic-dispatch")
    parser.add_argument("sid")
    parser.add_argument("--sprints-dir", required=True)
    args = parser.parse_args(argv)
    graph_path = Path(args.sprints_dir) / f"{args.sid}.task_graph.json"
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        verdict = check_planner_graph_dispatchable(
            graph, sprints_dir=args.sprints_dir, sid=args.sid
        )
    except Exception as exc:
        print(f"plan_validator: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, indent=2, sort_keys=True, ensure_ascii=True))
    return 0 if verdict.get("ok") else 3


def _main_planner_policy_block(argv: List[str]) -> int:
    """Print the planner compile-policy block for shell dispatch surfaces
    (solar-harness.sh wake, coordinator.sh drafting flow — G2b review finding
    5: those legacy planner dispatches never carried the policy). Env-gated
    like the library call: prints nothing and exits 0 when
    SOLAR_PLAN_VALIDATOR is off, so legacy dispatch text stays byte-identical."""
    parser = argparse.ArgumentParser(prog="plan_validator planner-policy-block")
    parser.add_argument("sid")
    parser.add_argument("--sprints-dir", required=True)
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--workflows-dir", default=None)
    args = parser.parse_args(argv)
    try:
        block = planner_compile_policy_block(
            args.sprints_dir,
            args.sid,
            config_dir=args.config_dir,
            workflows_dir=args.workflows_dir,
        )
    except Exception as exc:
        print(f"plan_validator: {exc}", file=sys.stderr)
        return 2
    if block:
        print(block)
    return 0


def _main_validate_file(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="plan_validator", description=__doc__)
    parser.add_argument("task_graph", help="path to a <sid>.task_graph.json")
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--workflows-dir", default=None)
    args = parser.parse_args(argv)
    try:
        errors = validate_plan_file(args.task_graph, args.config_dir, args.workflows_dir)
    except Exception as exc:
        print(f"plan_validator: {exc}", file=sys.stderr)
        return 2
    if errors:
        json.dump({"errors": errors}, sys.stdout, indent=2)
        print()
        return 3
    print("plan compiles")
    return 0


def _main_env_status(argv: List[str]) -> int:
    """G4 probe: print the RESOLVED governed-spine state and its source.

    With default-on the flags may be absent from every environment, so
    /proc-grep can no longer prove the spine — sandboxed runs capture this
    instead ({"enabled": bool, "source": "default"|"env"} per flag)."""
    argparse.ArgumentParser(prog="plan_validator env-status").parse_args(argv)
    def resolve(name: str, enabled: bool) -> Dict[str, Any]:
        return {"enabled": enabled, "source": "env" if os.environ.get(name) is not None else "default"}
    gate_ledger_on = str(os.environ.get("SOLAR_GATE_LEDGER", "") or "").strip().lower() not in {
        "0", "false", "no", "off",
    }
    json.dump(
        {
            "plan_validator": resolve("SOLAR_PLAN_VALIDATOR", _env_gate_enabled()),
            "gate_ledger": resolve("SOLAR_GATE_LEDGER", gate_ledger_on),
        },
        sys.stdout,
    )
    print()
    return 0


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "env-status":
        return _main_env_status(raw[1:])
    if raw and raw[0] == "compile-generic":
        return _main_compile_generic(raw[1:])
    if raw and raw[0] == "check-generic-dispatch":
        return _main_check_generic_dispatch(raw[1:])
    if raw and raw[0] == "planner-policy-block":
        return _main_planner_policy_block(raw[1:])
    return _main_validate_file(raw)


if __name__ == "__main__":
    sys.exit(main())
