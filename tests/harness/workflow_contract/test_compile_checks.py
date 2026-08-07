"""Deterministic tests 3/6/9 + route resolvability (generalized from
rsi-demo-stage-contract.json deterministic_tests_required_before_live):

- every_dispatch_task_type_admitted_by_capsule — against the REAL shipped
  capsule registry, no stubs (R2a);
- no_implementation_capsule_and_no_patch_diff_obligation on research stages,
  both the declarative half and the compile-enforcement half (R2b + forbidden);
- proof_obligations_resolve_to_output_present — obligation targets are declared
  outputs, gate-produced inputs, or runtime sidecars;
- artifact-root containment for declared outputs (R2c);
- route resolvability incl. AC-R2.4 remediation and the openai-only research
  route (route_proof_openai_only, compile-time half) (R2d).
"""
from __future__ import annotations

import copy
from pathlib import Path

import workflow_contract as wc

HARNESS_DIR = (Path(__file__).resolve().parents[3] / 'harness')


# ---------------------------------------------------------------------------
# The load-bearing positive: all three shipped contracts compile clean against
# the real capsule + operator registries (this is what makes the contract files
# shippable at all).
# ---------------------------------------------------------------------------

def test_shipped_contracts_compile_clean_against_real_registries(
    shipped_contracts, capsule_registry, operator_registry
):
    for workflow_id, contract in shipped_contracts.items():
        errors = wc.compile_checks(contract, capsule_registry, operator_registry)
        assert errors == [], f"{workflow_id} must compile clean, got: {errors}"


def test_every_stage_task_type_admitted_by_every_allowed_capsule(
    shipped_contracts, capsule_registry
):
    for workflow_id, contract in shipped_contracts.items():
        for stage in contract.get("stages", []):
            for capsule_id in stage["allowed_capsules"]:
                admitted = set(capsule_registry[capsule_id]["task_type_in"])
                assert stage["task_type"] in admitted, (
                    f"{workflow_id}/{stage['id']}: {stage['task_type']} not in {sorted(admitted)} "
                    f"of {capsule_id}"
                )


# ---------------------------------------------------------------------------
# R2(a): admission failures reject at compile
# ---------------------------------------------------------------------------

def test_task_type_not_admitted_rejects(shipped_contracts, capsule_registry, operator_registry):
    contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    # the example-schema shape this repo corrected: audit_inventory on the scout capsule
    contract["stages"][1]["task_type"] = "audit_inventory"
    errors = wc.compile_checks(contract, capsule_registry, operator_registry)
    hits = [e for e in errors if e["code"] == wc.ERROR_TASK_TYPE_NOT_ADMITTED]
    assert hits and hits[0]["stage_id"] == "D2"
    assert "knowledge-extraction" in hits[0]["admitted"]
    assert "D2" in hits[0]["message"] and "audit_inventory" in hits[0]["message"]


def test_unregistered_capsule_rejects(shipped_contracts, capsule_registry, operator_registry):
    contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    contract["stages"][0]["allowed_capsules"] = ["cap.does-not-exist"]
    errors = wc.compile_checks(contract, capsule_registry, operator_registry)
    assert any(e["code"] == wc.ERROR_CAPSULE_NOT_REGISTERED and e["stage_id"] == "D1" for e in errors)


# ---------------------------------------------------------------------------
# Research lock: no implementation capsule, no patch proofs (declarative half
# + enforcement half)
# ---------------------------------------------------------------------------

def test_research_contract_carries_no_impl_capsule_and_no_patch_proof(shipped_contracts):
    contract = shipped_contracts["research.deepdive.rsi_demo"]
    for stage in contract["stages"]:
        assert "cap.requirement-compiler-implementation" not in stage["allowed_capsules"], stage["id"]
        for obligation in stage["proof_obligations"]:
            assert wc.classify_obligation(obligation) != wc.PROOF_KIND_PATCH_PROOF, (
                stage["id"], obligation,
            )


def test_forbidden_capsule_on_research_stage_rejects(
    shipped_contracts, capsule_registry, operator_registry
):
    contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    contract["stages"][4]["allowed_capsules"].append("cap.requirement-compiler-implementation")
    errors = wc.compile_checks(contract, capsule_registry, operator_registry)
    codes = {e["code"] for e in errors if e["stage_id"] == "D5"}
    assert wc.ERROR_FORBIDDEN_CAPSULE in codes
    # the impl capsule also does not admit 'reporting', so admission fires too
    assert wc.ERROR_TASK_TYPE_NOT_ADMITTED in codes


def test_patch_diff_obligation_on_research_stage_rejects(
    shipped_contracts, capsule_registry, operator_registry
):
    contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    contract["stages"][4]["proof_obligations"].append(
        {"kind": "postcondition", "requirement": "output_present", "field": "patch_diff"}
    )
    errors = wc.compile_checks(contract, capsule_registry, operator_registry)
    codes = {e["code"] for e in errors if e["stage_id"] == "D5"}
    assert wc.ERROR_OBLIGATION_UNSATISFIABLE in codes  # artifact stage, patch proof illegal
    assert wc.ERROR_FORBIDDEN_OBLIGATION in codes  # and the contract forbids it outright


def test_patch_diff_is_legal_on_code_stages(shipped_contracts, capsule_registry, operator_registry):
    """The v7 distinction in the other direction: real code stages KEEP patch proofs."""
    for workflow_id in ("code.cli_smoke", "code.cli_smoke_anthropic"):
        contract = shipped_contracts[workflow_id]
        errors = wc.compile_checks(contract, capsule_registry, operator_registry)
        assert not [e for e in errors if e["code"] == wc.ERROR_OBLIGATION_UNSATISFIABLE]


# ---------------------------------------------------------------------------
# Obligation targets resolve (deterministic test 9, generalized)
# ---------------------------------------------------------------------------

def test_obligation_targets_are_declared_outputs_gate_inputs_or_sidecars(shipped_contracts):
    for workflow_id, contract in shipped_contracts.items():
        for stage in contract.get("stages", []):
            targets = {out["path"] for out in stage["outputs"]}
            targets |= set((stage.get("evaluator_gate") or {}).get("inputs_produced_by_this_gate", []))
            for obligation in stage["proof_obligations"]:
                if wc.classify_obligation(obligation) != wc.PROOF_KIND_ARTIFACT_PRESENCE:
                    continue
                field = obligation.get("field")
                if not field:
                    continue
                assert field in targets or field in wc.SIDECAR_PROOF_FIELDS, (
                    f"{workflow_id}/{stage['id']}: obligation target {field!r} undeclared"
                )


def test_undeclared_obligation_target_rejects(shipped_contracts, capsule_registry, operator_registry):
    contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    contract["stages"][0]["proof_obligations"].append(
        {"kind": "postcondition", "requirement": "output_present", "field": "ghost-artifact.json"}
    )
    errors = wc.compile_checks(contract, capsule_registry, operator_registry)
    assert any(
        e["code"] == wc.ERROR_OBLIGATION_TARGET_UNDECLARED and e["stage_id"] == "D1"
        for e in errors
    )


def test_gate_produced_input_is_a_valid_obligation_target(
    shipped_contracts, capsule_registry, operator_registry
):
    contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
    contract["stages"][2]["proof_obligations"].append(
        {"kind": "postcondition", "requirement": "output_present", "field": "research_eval.json"}
    )
    errors = wc.compile_checks(contract, capsule_registry, operator_registry)
    assert not [e for e in errors if e["code"] == wc.ERROR_OBLIGATION_TARGET_UNDECLARED]


# ---------------------------------------------------------------------------
# R2(c): declared outputs stay inside the declared roots
# ---------------------------------------------------------------------------

def test_output_escaping_root_rejects(shipped_contracts, capsule_registry, operator_registry):
    for bad_path in ("../escape.md", "/etc/passwd", "a/../../b.md"):
        contract = copy.deepcopy(shipped_contracts["research.deepdive.rsi_demo"])
        contract["stages"][0]["outputs"].append({"path": bad_path, "type": "markdown"})
        errors = wc.compile_checks(contract, capsule_registry, operator_registry)
        assert any(
            e["code"] == wc.ERROR_ARTIFACT_ROOT_UNRESOLVED and e["stage_id"] == "D1"
            for e in errors
        ), bad_path


# ---------------------------------------------------------------------------
# R2(d): route resolvability (registry resolvability, never live capacity)
# ---------------------------------------------------------------------------

def _degraded_registry():
    return {
        "op-disabled": {"enabled": False, "available": True, "deprecated": False, "health_status": "ok", "role": "builder", "provider": "openai"},
        "op-deprecated": {"enabled": True, "available": True, "deprecated": True, "health_status": "ok", "role": "builder", "provider": "openai"},
        "op-unhealthy": {"enabled": True, "available": True, "deprecated": False, "health_status": "missing", "role": "builder", "provider": "openai"},
        "op-wrong-provider": {"enabled": True, "available": True, "deprecated": False, "health_status": "ok", "role": "builder", "provider": "glm"},
        "op-wrong-role": {"enabled": True, "available": True, "deprecated": False, "health_status": "ok", "role": "planner", "provider": "openai"},
    }


def test_route_unresolvable_fails_compile_with_remediation(shipped_contracts, capsule_registry):
    """AC-R2.4: only disabled/deprecated/unhealthy operators => compile error with remediation."""
    contract = shipped_contracts["research.deepdive.rsi_demo"]
    errors = wc.compile_checks(contract, capsule_registry, _degraded_registry())
    route_errors = [e for e in errors if e["code"] == wc.ERROR_ROUTE_UNRESOLVABLE]
    assert route_errors
    assert all("Remediation" in e["message"] for e in route_errors)
    assert any(e["stage_id"] == "D1" for e in route_errors)


def test_llm_eval_gate_requires_resolvable_evaluator(shipped_contracts, capsule_registry):
    registry = _degraded_registry()
    registry["op-good-builder"] = {
        "enabled": True, "available": True, "deprecated": False, "health_status": "ok",
        "role": "builder", "provider": "openai",
    }
    contract = shipped_contracts["research.deepdive.rsi_demo"]
    errors = wc.compile_checks(contract, capsule_registry, registry)
    evaluator_errors = [
        e for e in errors
        if e["code"] == wc.ERROR_ROUTE_UNRESOLVABLE and e.get("declared") == "evaluator"
    ]
    assert evaluator_errors and evaluator_errors[0]["stage_id"] == "D5"


def test_research_routes_resolve_openai_only(shipped_contracts, operator_registry):
    """route_proof_openai_only, compile-time half: under the RSI provider policy
    every stage resolves to >=1 operator and every resolved operator is openai."""
    contract = shipped_contracts["research.deepdive.rsi_demo"]
    policy = contract["provider_policy"]
    for stage in contract["stages"]:
        allowed = stage["allowed_operators"]
        resolved = wc.resolve_role_operators(
            allowed["role"], allowed.get("providers"), operator_registry, policy
        )
        assert resolved, stage["id"]
        for operator_id in resolved:
            assert operator_registry[operator_id]["provider"] == "openai", (stage["id"], operator_id)


def test_anthropic_cli_routes_resolve_anthropic_only(shipped_contracts, operator_registry):
    contract = shipped_contracts["code.cli_smoke_anthropic"]
    policy = contract["provider_policy"]
    assert policy["allowed_providers"] == ["anthropic"]
    for stage in contract["stages"]:
        allowed = stage["allowed_operators"]
        assert allowed.get("providers") == ["anthropic"]
        resolved = wc.resolve_role_operators(
            allowed["role"], allowed.get("providers"), operator_registry, policy
        )
        assert resolved, stage["id"]
        for operator_id in resolved:
            assert operator_registry[operator_id]["provider"] == "anthropic", (stage["id"], operator_id)


def test_generic_contract_required_roles_resolve(shipped_contracts, capsule_registry, operator_registry):
    contract = shipped_contracts["pm.generic.v1"]
    assert contract["required_roles"] == ["planner", "builder", "evaluator"]
    errors = wc.compile_checks(contract, capsule_registry, operator_registry)
    assert errors == []


# ---------------------------------------------------------------------------
# F1 (round-2): an EMPTY stage∩policy provider intersection must resolve to
# ZERO operators (=> ROUTE_UNRESOLVABLE), never fall through the falsy-empty-set
# short-circuit and "resolve all". The reviewer's ▶EXECUTED probe: the RSI
# contract (every stage pins providers=["openai"]) compiled under an
# anthropic-only run policy compiled CLEAN — a cross-provider plan that would
# have exploded at the first live dispatch.
# ---------------------------------------------------------------------------

def test_empty_stage_policy_intersection_fails_compile(shipped_contracts, capsule_registry, operator_registry):
    """RSI's openai stages under an anthropic-only run policy must NOT compile."""
    contract = shipped_contracts["research.deepdive.rsi_demo"]
    anthropic_only = {"allowed_providers": ["anthropic"]}
    errors = wc.compile_checks(contract, capsule_registry, operator_registry, provider_policy=anthropic_only)
    route_errors = [e for e in errors if e["code"] == wc.ERROR_ROUTE_UNRESOLVABLE]
    assert route_errors, "empty openai∩anthropic intersection must reject, not resolve-all"
    assert any(e["stage_id"] == "D1" for e in route_errors)
    assert all("Remediation" in e["message"] for e in route_errors)


def test_resolve_role_operators_empty_intersection_resolves_nothing(operator_registry):
    """Unit: stage providers=[openai] ∩ policy=[anthropic] = ∅ => [] (not all)."""
    resolved = wc.resolve_role_operators(
        "builder", ["openai"], operator_registry, {"allowed_providers": ["anthropic"]}
    )
    assert resolved == [], resolved


def test_resolve_role_operators_unconstrained_still_resolves(operator_registry):
    """The genuinely-unconstrained case (no stage providers, no policy) must
    still resolve every healthy builder — the empty-set fix must not over-reject."""
    resolved = wc.resolve_role_operators("builder", None, operator_registry, None)
    assert resolved, "no provider constraint at all must resolve healthy operators"


def test_resolve_role_operators_excludes_statically_unavailable_operator():
    registry = {
        "op-unavailable": {
            "enabled": True,
            "available": False,
            "deprecated": False,
            "health_status": "ok",
            "role": "builder",
            "provider": "openai",
        }
    }

    assert wc.resolve_role_operators("builder", None, registry, None) == []


def test_resolve_role_operators_nonempty_intersection_filters(operator_registry):
    """A NON-empty intersection still filters to the intersected providers."""
    resolved = wc.resolve_role_operators(
        "builder", ["openai", "anthropic"], operator_registry, {"allowed_providers": ["openai"]}
    )
    assert resolved
    for operator_id in resolved:
        assert operator_registry[operator_id]["provider"] == "openai", operator_id
