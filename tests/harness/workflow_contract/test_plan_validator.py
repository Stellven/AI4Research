"""The two mandatory rejection replays (AC-R2.1/AC-R2.2) + the four historical
admission shapes (AC-R2.3) + true-negatives, all against the REAL shipped
capsule/operator registries:

- preserved v7 graph (artifact node bound to the implementation capsule with
  patch_diff obligations, corpus F-049) => OBLIGATION_UNSATISFIABLE_FOR_NODE_KIND
- preserved v9 graph (write_scope without the workspace/ prefix, corpus F-051)
  => ARTIFACT_ROOT_UNRESOLVED
- analysis / tests / implementationworker / logical-op-map-vs-audit-capsule
  => TASK_TYPE_NOT_ADMITTED with the offending node id + admitted set
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import plan_validator as pv
import workflow_contract as wc

HARNESS_DIR = (Path(__file__).resolve().parents[3] / 'harness')
FIXTURES_DIR = (Path(__file__).resolve().parents[3] / 'tests' / 'harness' / 'workflow_contract') / "fixtures"

V7_FIXTURE = FIXTURES_DIR / "v7-rsi-demo-bf66d46b.task_graph.json"
V9_FIXTURE = FIXTURES_DIR / "v9-rsi-demo-fbce668c.task_graph.json"


def test_module_imports_from_this_checkout():
    """No installed-harness imports (R9)."""
    assert Path(pv.__file__).resolve().is_relative_to(HARNESS_DIR.resolve()), pv.__file__


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(graph, capsule_registry, operator_registry, shipped_contracts):
    # This file isolates the R2(a-d)+F3 families on corpus fixtures that
    # predate the P5 G1 gate/repair-budget/size checks (which have their own
    # suite, scenarios/test_p5_g1_plan_certificate.py). Stamp the current
    # TaskGraph schema fields and a compliant default gate on a COPY so the
    # exact-set assertions here remain isolated from fixture-era omissions.
    graph = copy.deepcopy(graph)
    for node in graph.get("nodes", []) or []:
        if isinstance(node, dict):
            node.setdefault("acceptance", ["fixture acceptance satisfied"])
            node.setdefault("priority", 1)
            node.setdefault("required_phase", "planning_complete")
            node.setdefault("required_node_id", node.get("id"))
            node.setdefault("required_node_status", "ready")
        if isinstance(node, dict) and node.get("max_repair_attempts") is None:
            gate = node.setdefault("evaluator_gate", {})
            if isinstance(gate, dict):
                gate.setdefault("kind", "llm_eval")
                gate.setdefault("on_fail", "repair_once_then_fail")
    return pv.validate_plan(
        graph, capsule_registry, operator_registry,
        contract=shipped_contracts["pm.generic.v1"],
    )


# ---------------------------------------------------------------------------
# AC-R2.1: the v7 replay
# ---------------------------------------------------------------------------

def test_v7_graph_rejected_with_obligation_unsatisfiable(
    capsule_registry, operator_registry, shipped_contracts
):
    errors = _validate(_load(V7_FIXTURE), capsule_registry, operator_registry, shipped_contracts)
    unsat = [e for e in errors if e["code"] == wc.ERROR_OBLIGATION_UNSATISFIABLE]
    # three patch-proof obligations on S1: field=patch_diff, check.patch_within_scope,
    # and the "patch_diff exists" pass_condition
    assert len(unsat) == 3, errors
    assert all(e["stage_id"] == "S1" for e in unsat)
    assert all(e["declared"] == wc.PROOF_KIND_PATCH_PROOF for e in unsat)


def test_v7_rejection_is_exactly_the_proof_contract_defect(
    capsule_registry, operator_registry, shipped_contracts
):
    """v7's S1 passed admission live (implementation IS admitted by the
    implementation capsule) and wrote workspace-prefixed paths — S1's LIVE
    defect was the unsatisfiable proof contract. Scoped to the S1-isolated
    graph: the full v7 record's skeletal downstream nodes (S2/S3/S4) carry no
    capsule binding and now (correctly) also trip CAPSULE_UNBOUND — see
    test_v7_full_graph_flags_unbound_downstream_nodes (round-3 Finding A).
    Since the G3 run-7 fix, S1's invented required_capabilities
    (local-file-read/artifact-write — never in any registry) also correctly
    trip PLAN_CAPABILITY_UNSATISFIABLE: the class that wedged run 7 at
    dispatch existed silently in the v7 record all along."""
    import plan_validator as pv

    errors = _validate(_v7_s1_graph(), capsule_registry, operator_registry, shipped_contracts)
    codes = {e["code"] for e in errors}
    assert codes == {
        wc.ERROR_OBLIGATION_UNSATISFIABLE,
        pv.ERROR_PLAN_CAPABILITY_UNSATISFIABLE,
    }, errors


def test_v7_s1_derives_artifact_node_kind():
    graph = _load(V7_FIXTURE)
    s1 = next(node for node in graph["nodes"] if node["id"] == "S1")
    assert wc.classify_node_kind(s1) == "artifact"


# ---------------------------------------------------------------------------
# F2 (round-2): the planner does NOT own node_kind. A decoy code file in
# write_scope, or an explicit node_kind:"code", must not flip an artifact-
# authoring node to code and re-legalize the v7 patch_diff obligations. The
# bound capsule is the authority; planner-declared node_kind may only narrow.
# ---------------------------------------------------------------------------

def _v7_s1_graph() -> dict:
    """The v7 defect isolated to S1 (the only node with a proof contract)."""
    graph = _load(V7_FIXTURE)
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] == "S1"]
    return graph


def test_v7_plus_decoy_code_file_still_rejects(
    capsule_registry, operator_registry, shipped_contracts
):
    """Reviewer probe: appending a decoy `helper.py` to the v7 artifact write_scope
    used to flip node_kind to code and compile clean. It must still reject."""
    graph = _v7_s1_graph()
    graph["nodes"][0]["write_scope"].append(
        "workspace/rsi-deep-research-report/helper.py"
    )
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    unsat = [e for e in errors if e["code"] == wc.ERROR_OBLIGATION_UNSATISFIABLE]
    assert unsat, f"decoy .py must not re-legalize patch proofs; got {errors}"
    assert all(e["stage_id"] == "S1" for e in unsat)
    assert all(e["declared"] == wc.PROOF_KIND_PATCH_PROOF for e in unsat)


def test_v7_plus_explicit_node_kind_code_still_rejects(
    capsule_registry, operator_registry, shipped_contracts
):
    """Reviewer probe: a planner-declared node_kind:'code' on the v7 artifact
    node must not escalate it to code — declared node_kind may only narrow."""
    graph = _v7_s1_graph()
    graph["nodes"][0]["node_kind"] = "code"
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    unsat = [e for e in errors if e["code"] == wc.ERROR_OBLIGATION_UNSATISFIABLE]
    assert unsat, f"declared node_kind:code must not re-legalize patch proofs; got {errors}"
    assert all(e["stage_id"] == "S1" for e in unsat)


def test_non_code_capsule_with_decoy_py_rejects_patch_obligation(
    capsule_registry, operator_registry, shipped_contracts
):
    """The capsule-authority layer: a node bound to the audit capsule (no
    patch_diff output) can never be a code node, even with a real .py write
    target and no structured-data deliverable to trip the shape heuristic."""
    graph = _graph_with({
        "id": "A1",
        "goal": "Author the audit report (with a smuggled helper script + patch proof).",
        "capability_capsule_id": "cap.requirement-compiler-audit",
        "dispatch_task_type": "reporting",
        "write_scope": ["workspace/audit/report.md", "workspace/audit/helper.py"],
        "node_kind": "code",
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "field": "patch_diff"},
        ],
        "depends_on": [],
    })
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    unsat = [e for e in errors if e["code"] == wc.ERROR_OBLIGATION_UNSATISFIABLE]
    assert unsat and unsat[0]["stage_id"] == "A1", errors
    assert unsat[0]["declared"] == wc.PROOF_KIND_PATCH_PROOF


def test_classify_node_kind_declared_code_cannot_escalate_artifact_shape():
    """Unit: declared node_kind narrows, never escalates."""
    artifact_node = {
        "write_scope": ["workspace/x/sources.json"],
        "node_kind": "code",
    }
    assert wc.classify_node_kind(artifact_node) == "artifact"


def test_classify_node_kind_decoy_py_does_not_beat_structured_data():
    """Unit: a structured-data deliverable marks artifact-authoring even with a
    code file present in write_scope."""
    node = {"write_scope": ["workspace/x/sources.json", "workspace/x/helper.py"]}
    assert wc.classify_node_kind(node) == "artifact"


def test_classify_node_kind_non_code_capsule_caps_at_artifact():
    """Unit: a non-code capsule caps the node below code regardless of shape."""
    node = {"write_scope": ["workspace/x/tool.py"], "node_kind": "code"}
    assert wc.classify_node_kind(node, capsule_is_code=True) == "code"
    assert wc.classify_node_kind(node, capsule_is_code=False) == "artifact"


# ---------------------------------------------------------------------------
# Round-3 Finding A: an empty/missing capability_capsule_id skipped capsule
# admission AND left capsule_is_code=None, so the F2 ceiling never fired — a
# node with node_kind:"code" + a lone workdir/tool.py write_scope re-legalized
# the patch_diff obligations and the graph compiled clean (the last hole in the
# node-kind-authority story above). When a capsule registry is provided, an
# unbound node is now a compile error (CAPSULE_UNBOUND), emitted BEFORE node-kind
# classification so it can never reach the capsule_is_code=None ceiling-skip.
# ---------------------------------------------------------------------------

def _unbound_code_relegalization_node() -> dict:
    """The reviewer's fourth shape: no capsule binding, declared node_kind:"code",
    a lone workdir/*.py write target, and patch_diff obligations."""
    return {
        "id": "U1",
        "goal": "Implement the tool with a patch proof but no capsule binding.",
        "capability_capsule_id": "",
        "dispatch_task_type": "implementation",
        "node_kind": "code",
        "write_scope": ["workdir/tool.py"],
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "field": "patch_diff"},
            {"kind": "self_check", "requirement": "check.patch_within_scope"},
        ],
        "depends_on": [],
    }


def test_unbound_capsule_id_rejected_with_capsule_unbound(
    capsule_registry, operator_registry, shipped_contracts
):
    """Empty capability_capsule_id => CAPSULE_UNBOUND on the offending node."""
    graph = _graph_with(_unbound_code_relegalization_node())
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    unbound = [e for e in errors if e["code"] == wc.ERROR_CAPSULE_UNBOUND]
    assert unbound and unbound[0]["stage_id"] == "U1", errors


def test_missing_capsule_id_key_rejected_with_capsule_unbound(
    capsule_registry, operator_registry, shipped_contracts
):
    """Same shape, but the capability_capsule_id key is absent entirely."""
    node = _unbound_code_relegalization_node()
    del node["capability_capsule_id"]
    errors = _validate(_graph_with(node), capsule_registry, operator_registry, shipped_contracts)
    assert any(
        e["code"] == wc.ERROR_CAPSULE_UNBOUND and e["stage_id"] == "U1" for e in errors
    ), errors


def test_unbound_code_node_does_not_relegalize_patch_diff(
    capsule_registry, operator_registry, shipped_contracts
):
    """The security invariant: an unbound node can never compile clean, so
    node_kind:"code" cannot re-legalize the patch_diff obligations. Before the
    fix this graph produced [] (clean compile); it must now reject."""
    graph = _graph_with(_unbound_code_relegalization_node())
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    assert errors, "an unbound node must never compile clean"
    assert any(e["code"] == wc.ERROR_CAPSULE_UNBOUND for e in errors), errors


def test_capsule_unbound_emitted_before_node_kind_classification(
    capsule_registry, operator_registry, shipped_contracts
):
    """The unbound node short-circuits before node-kind classification: it never
    reaches R2(b), so no OBLIGATION_UNSATISFIABLE is emitted for it — the single,
    root-cause error is CAPSULE_UNBOUND, not a downstream symptom."""
    graph = _graph_with(_unbound_code_relegalization_node())
    codes = {e["code"] for e in _validate(graph, capsule_registry, operator_registry, shipped_contracts)}
    assert codes == {wc.ERROR_CAPSULE_UNBOUND}, codes


def test_capsule_unbound_not_raised_when_registry_is_none(operator_registry, shipped_contracts):
    """Finding A is scoped to 'when a capsule registry is provided'. Incremental
    validation (capsule_registry=None) skips the admission family, so an unbound
    node must NOT trip CAPSULE_UNBOUND on that path."""
    graph = _graph_with(_unbound_code_relegalization_node())
    errors = pv.validate_plan(
        graph, None, operator_registry, contract=shipped_contracts["pm.generic.v1"]
    )
    assert not any(e["code"] == wc.ERROR_CAPSULE_UNBOUND for e in errors), errors


def test_bound_capsule_node_does_not_trip_capsule_unbound(
    capsule_registry, operator_registry, shipped_contracts
):
    """True-negative: a node WITH a registered capsule binding never trips
    CAPSULE_UNBOUND — a valid audit-capsule plan still compiles clean."""
    graph = _graph_with({
        "id": "S1",
        "goal": "Transform the source pack into sources.json.",
        "capability_capsule_id": "cap.requirement-compiler-audit",
        "dispatch_task_type": "audit_inventory",
        "write_scope": ["workspace/rsi-deep-research-report/sources.json"],
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "field": "sources.json"},
        ],
        "depends_on": [],
    })
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    assert not any(e["code"] == wc.ERROR_CAPSULE_UNBOUND for e in errors), errors


def test_v7_full_graph_flags_unbound_downstream_nodes(
    capsule_registry, operator_registry, shipped_contracts
):
    """On the real v7 corpus record the skeletal downstream nodes S2/S3/S4 carry
    no capsule binding; they are now (correctly) flagged CAPSULE_UNBOUND while
    S1's proof-contract defect (OBLIGATION_UNSATISFIABLE) is unchanged."""
    errors = _validate(_load(V7_FIXTURE), capsule_registry, operator_registry, shipped_contracts)
    unbound = {e["stage_id"] for e in errors if e["code"] == wc.ERROR_CAPSULE_UNBOUND}
    assert unbound == {"S2", "S3", "S4"}, errors


# ---------------------------------------------------------------------------
# AC-R2.2: the v9 replay
# ---------------------------------------------------------------------------

def test_v9_graph_rejected_with_artifact_root_unresolved(
    capsule_registry, operator_registry, shipped_contracts
):
    errors = _validate(_load(V9_FIXTURE), capsule_registry, operator_registry, shipped_contracts)
    unresolved = [e for e in errors if e["code"] == wc.ERROR_ARTIFACT_ROOT_UNRESOLVED]
    # S1 has one bare-relative write_scope entry, S2 has four
    assert len(unresolved) == 5, errors
    assert {e["stage_id"] for e in unresolved} == {"S1", "S2"}
    assert all("rsi-deep-research-report/" in e["declared"] for e in unresolved)


def test_v9_rejection_is_exactly_the_root_defect(
    capsule_registry, operator_registry, shipped_contracts
):
    """v9 ran green node-wise (audit capsule, admitted task types, no patch
    obligations) — the ONLY compile defect is the unresolved artifact root."""
    errors = _validate(_load(V9_FIXTURE), capsule_registry, operator_registry, shipped_contracts)
    codes = {e["code"] for e in errors}
    assert codes == {wc.ERROR_ARTIFACT_ROOT_UNRESOLVED}, errors


def test_workspace_prefixed_scope_resolves_canonical_and_workdir_resolves_alias(shipped_contracts):
    roots = shipped_contracts["pm.generic.v1"]["artifact_roots"]
    assert wc.resolve_scope_path("workspace/rsi-deep-research-report/report.md", roots) == "canonical"
    assert wc.resolve_scope_path("sprints/sprint-x-123/workdir/foo/report.md", roots) == "sprints/<sid>/workdir/"
    assert wc.resolve_scope_path("workdir/foo.py", roots) == "workdir/"
    assert wc.resolve_scope_path("rsi-deep-research-report/report.md", roots) is None
    assert wc.resolve_scope_path("/tmp/escape.md", roots) is None
    assert wc.resolve_scope_path("workspace/../escape.md", roots) is None


# ---------------------------------------------------------------------------
# AC-R2.3: the four historical admission shapes
# ---------------------------------------------------------------------------

def _graph_with(node: dict) -> dict:
    return {"sprint_id": "sprint-admission-shapes", "nodes": [node], "node_results": {}, "gate_results": {}}


_ADMISSION_SHAPES = {
    # F-019: audit/scope node persisted dispatch_task_type=analysis; the audit
    # capsule admits only its canonical read-only types
    "analysis": {
        "id": "A1",
        "goal": "Inventory packaging readiness (F-019 shape).",
        "capability_capsule_id": "cap.requirement-compiler-audit",
        "dispatch_task_type": "analysis",
        "write_scope": ["workspace/audit/readiness-report.md"],
        "depends_on": [],
    },
    # F-030: task_type=tests rejected by the implementation capsule
    "tests": {
        "id": "T1",
        "goal": "Author the test suite (F-030 shape).",
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "dispatch_task_type": "tests",
        "write_scope": ["workdir/tests/test_tool.py"],
        "depends_on": [],
    },
    # F-044: the logical-operator NAME leaked in as the task type
    "implementationworker": {
        "id": "B1",
        "goal": "Implement the tool (F-044 shape).",
        "logical_operator": "ImplementationWorker",
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "dispatch_task_type": "implementationworker",
        "write_scope": ["workdir/tool.py"],
        "depends_on": [],
    },
    # F-046 (v3): node resolved to the audit capsule but the logical-op map
    # produced implementation — non-admitted for the resolved capsule
    "logical-op-map-vs-audit-capsule": {
        "id": "S1",
        "goal": "Transform source-pack metadata into sources.json (F-046 shape).",
        "logical_operator": "ImplementationWorker",
        "capability_capsule_id": "cap.requirement-compiler-audit",
        "dispatch_task_type": "implementation",
        "write_scope": ["workspace/rsi-deep-research-report/sources.json"],
        "depends_on": [],
    },
}


def test_four_historical_admission_shapes_all_rejected(
    capsule_registry, operator_registry, shipped_contracts
):
    for label, node in _ADMISSION_SHAPES.items():
        errors = _validate(_graph_with(dict(node)), capsule_registry, operator_registry, shipped_contracts)
        hits = [e for e in errors if e["code"] == wc.ERROR_TASK_TYPE_NOT_ADMITTED]
        assert hits, f"{label}: expected TASK_TYPE_NOT_ADMITTED, got {errors}"
        err = hits[0]
        # AC-R2.3: the offending node id and the admitted set are in the message
        assert err["stage_id"] == node["id"], label
        assert node["id"] in err["message"], label
        assert err["admitted"], label
        assert all(str(t) in err["message"] for t in err["admitted"]), label


# ---------------------------------------------------------------------------
# True-negatives: valid generic plans must NOT be rejected
# ---------------------------------------------------------------------------

def test_v8_shaped_artifact_plan_compiles(capsule_registry, operator_registry, shipped_contracts):
    """The shape that went green live (v8): audit capsule + admitted task type
    + workspace-prefixed scope + presence obligations only."""
    graph = _graph_with({
        "id": "S1",
        "goal": "Transform the source pack into sources.json.",
        "capability_capsule_id": "cap.requirement-compiler-audit",
        "dispatch_task_type": "audit_inventory",
        "write_scope": ["workspace/rsi-deep-research-report/sources.json"],
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "field": "sources.json"},
            {"kind": "postcondition", "requirement": "output_present", "field": "handoff_md"},
        ],
        "depends_on": [],
    })
    assert _validate(graph, capsule_registry, operator_registry, shipped_contracts) == []


def test_real_code_node_keeps_patch_obligations(capsule_registry, operator_registry, shipped_contracts):
    """The fe2a7d69 safety net's other half: real code nodes KEEP patch proofs."""
    graph = _graph_with({
        "id": "C1",
        "goal": "Implement the CLI tool.",
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "dispatch_task_type": "implementation",
        "write_scope": ["workdir/tool.py", "workdir/README.md"],
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "field": "patch_diff"},
            {"kind": "self_check", "requirement": "check.patch_within_scope"},
        ],
        "depends_on": [],
    })
    assert _validate(graph, capsule_registry, operator_registry, shipped_contracts) == []


# ---------------------------------------------------------------------------
# F3 (round-2): the planner path had NO acyclicity or depends_on-existence check
# (only the schema path for fixed contracts did). A cyclic or dangling-dep graph
# compiled clean and would hang the scheduler. validate_plan now rejects both.
# ---------------------------------------------------------------------------

def _valid_audit_node(node_id: str, depends_on: list) -> dict:
    return {
        "id": node_id,
        "goal": f"Audit step {node_id}.",
        "capability_capsule_id": "cap.requirement-compiler-audit",
        "dispatch_task_type": "audit_inventory",
        "write_scope": [f"workspace/x/{node_id}.json"],
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "field": f"{node_id}.json"},
        ],
        "depends_on": list(depends_on),
    }


def test_cyclic_graph_rejected(capsule_registry, operator_registry, shipped_contracts):
    """Reviewer probe: a two-node cycle A->B->A compiled clean; it must reject."""
    graph = {
        "sprint_id": "sprint-cyclic",
        "nodes": [_valid_audit_node("A", ["B"]), _valid_audit_node("B", ["A"])],
        "node_results": {}, "gate_results": {},
    }
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    cyclic = [e for e in errors if e["code"] == wc.ERROR_GRAPH_CYCLIC]
    assert cyclic, f"expected GRAPH_CYCLIC, got {errors}"


def test_self_loop_graph_rejected(capsule_registry, operator_registry, shipped_contracts):
    graph = {
        "sprint_id": "sprint-selfloop",
        "nodes": [_valid_audit_node("A", ["A"])],
        "node_results": {}, "gate_results": {},
    }
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    assert any(e["code"] == wc.ERROR_GRAPH_CYCLIC for e in errors), errors


def test_dangling_depends_on_rejected(capsule_registry, operator_registry, shipped_contracts):
    """Reviewer probe: a node depending on a non-existent stage compiled clean."""
    graph = {
        "sprint_id": "sprint-dangling",
        "nodes": [_valid_audit_node("A", ["does-not-exist"])],
        "node_results": {}, "gate_results": {},
    }
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    dangling = [e for e in errors if e["code"] == wc.ERROR_DEP_NOT_FOUND]
    assert dangling and dangling[0]["stage_id"] == "A", errors
    assert dangling[0]["declared"] == "does-not-exist"


def test_valid_dag_has_no_graph_structure_errors(
    capsule_registry, operator_registry, shipped_contracts
):
    """A well-formed multi-node DAG must NOT trip the new checks (no over-rejection)."""
    graph = {
        "sprint_id": "sprint-valid",
        "nodes": [
            _valid_audit_node("A", []),
            _valid_audit_node("B", ["A"]),
            _valid_audit_node("C", ["A", "B"]),
        ],
        "node_results": {}, "gate_results": {},
    }
    errors = _validate(graph, capsule_registry, operator_registry, shipped_contracts)
    assert not [e for e in errors if e["code"] in (wc.ERROR_GRAPH_CYCLIC, wc.ERROR_DEP_NOT_FOUND)], errors


def test_route_unresolvable_for_plan_node(capsule_registry, shipped_contracts):
    graph = _graph_with({
        "id": "N1",
        "goal": "Any node under an empty operator registry.",
        "capability_capsule_id": "cap.requirement-compiler-audit",
        "dispatch_task_type": "audit_inventory",
        "write_scope": ["workspace/x/report.md"],
        "depends_on": [],
        # G1-compliant gate so the ONLY error is the empty registry's.
        "evaluator_gate": {"kind": "llm_eval", "on_fail": "repair_once_then_fail"},
    })
    errors = _validate(graph, capsule_registry, {}, shipped_contracts)
    assert [e["code"] for e in errors] == [wc.ERROR_ROUTE_UNRESOLVABLE]
    assert "Remediation" in errors[0]["message"]


# ---------------------------------------------------------------------------
# Errors artifact + standalone CLI
# ---------------------------------------------------------------------------

def test_write_errors_artifact(tmp_path):
    errors = [wc.compile_error(wc.ERROR_TASK_TYPE_NOT_ADMITTED, "S1", "msg", admitted=["evidence"])]
    target = pv.write_errors_artifact(tmp_path, "sprint-x", errors)
    assert target == tmp_path / "sprint-x.plan-compile-errors.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["error_count"] == 1
    assert payload["terminal_state_on_exhaustion"] == "PLAN_COMPILE_FAILED"
    assert payload["errors"][0]["code"] == wc.ERROR_TASK_TYPE_NOT_ADMITTED


def test_cli_rejects_v7_fixture_exit_3():
    import os
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    env["PYTHONPATH"] = str(HARNESS_DIR / "lib")
    result = subprocess.run(
        [sys.executable, str(HARNESS_DIR / "lib" / "plan_validator.py"), str(V7_FIXTURE)],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert result.returncode == 3, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert any(e["code"] == wc.ERROR_OBLIGATION_UNSATISFIABLE for e in payload["errors"])
