"""P5 G1: plan_validator hardening + plan_certificate + dispatcher guard.

The generic-path gap (P5 runbook, design draft §0-§2): plan_validator existed
with R2a-d + F3 but had NO call site and NO way for the dispatcher to know it
ran — a planner-emitted graph reached dispatch ungoverned (the v5-v10 failure
substrate). G1 adds, deterministically:

- R2(e) gate legality: planner nodes may gate with llm_eval (default when the
  gate is absent) or an allowlisted deterministic_command; `none` and
  arbitrary commands are not plannable.
- R2(f) repair budgets stamped: max_repair_attempts in [0,2] or derivable
  from evaluator_gate.on_fail (the instantiate convention).
- R2(g) size bound: over-decomposition (epic explosion) rejects at compile.
- plan_certificate: hash-stamped PASS verdict over the governed node subset;
  any post-validation tamper flips the hash (the P2 smoke-4 capsule-authority
  lesson generalized to whole-graph birth).
- _workflow_contract_guard: a graph claiming a planner_generated contract
  (pm.generic.v1) fails closed at dispatch without a valid certificate.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(_HARNESS / "lib"))

import plan_validator as pv  # noqa: E402
import evaluation_budget  # noqa: E402
import workflow_contract as wc  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"


def _node(node_id: str = "N1", **overrides) -> dict:
    node = {
        "id": node_id,
        "goal": f"{node_id} goal",
        "depends_on": [],
        "task_type": "implementation",
        "dispatch_task_type": "implementation",
        "capability_capsule_id": "",
        "write_scope": ["workspace/out.md"],
        "proof_obligations": [],
        "evaluator_gate": {"kind": "llm_eval", "on_fail": "repair_once_then_fail"},
        "status": "pending",
    }
    node.update(overrides)
    return node


def _graph(*nodes: dict, **top) -> dict:
    graph = {
        "sprint_id": "sprint-p5-g1-fixture",
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "nodes": list(nodes) or [_node()],
    }
    graph.update(top)
    return graph


def _errors(graph: dict) -> list[str]:
    # Registries None: R2a/R2d families skip; the G1 checks under test and
    # R2c/F3 still run. The product call site passes both registries.
    return [e.get("code") for e in pv.validate_plan(graph, None, None)]


# ---------------------------------------------------------------------------
# R2(e) gate legality
# ---------------------------------------------------------------------------

class TestGateLegality:
    def test_llm_eval_gate_is_legal(self):
        assert _errors(_graph(_node())) == []

    def test_absent_gate_defaults_to_llm_eval_and_is_legal_with_budget(self):
        node = _node()
        node.pop("evaluator_gate")
        node["max_repair_attempts"] = 1
        assert _errors(_graph(node)) == []

    def test_none_gate_is_not_plannable(self):
        node = _node(evaluator_gate={"kind": "none", "on_fail": "fail"})
        assert "PLAN_GATE_KIND_ILLEGAL" in _errors(_graph(node))

    def test_compiler_applied_budget_may_waive_redundant_node_evaluation(self):
        graph = evaluation_budget.apply_evaluation_budget(
            _graph(
                _node("N1"),
                _node("N2", depends_on=["N1"], logical_operator="Verifier"),
            ),
            {"request_type": "short_implementation"},
        )
        assert _errors(graph) == []
        verifier = next(node for node in graph["nodes"] if node["id"] == "N2")
        assert verifier["evaluator_gate"]["kind"] == "none"

    def test_unknown_gate_kind_rejects(self):
        node = _node(evaluator_gate={"kind": "vibes", "on_fail": "fail"})
        assert "PLAN_GATE_KIND_ILLEGAL" in _errors(_graph(node))

    def test_allowlisted_pytest_command_is_legal(self):
        node = _node(evaluator_gate={
            "kind": "deterministic_command",
            "command": "python3 -m pytest sprints/sprint-p5-g1-fixture/workdir/tests -q",
            "on_fail": "fail",
        })
        assert _errors(_graph(node)) == []

    def test_allowlisted_demo_validator_command_is_legal(self):
        node = _node(evaluator_gate={
            "kind": "deterministic_command",
            "command": "python3 scripts/validate_rsi_demo_report.py --workspace <resolved_root> --sources-only",
            "on_fail": "repair_once_then_fail",
        })
        assert _errors(_graph(node)) == []

    def test_arbitrary_command_is_not_allowlisted(self):
        node = _node(evaluator_gate={
            "kind": "deterministic_command",
            "command": "bash -c 'exit 0'",
            "on_fail": "fail",
        })
        assert "PLAN_GATE_COMMAND_NOT_ALLOWLISTED" in _errors(_graph(node))

    def test_prefix_smuggling_is_not_allowlisted(self):
        # Vacuous-gate hazard (P3 run-2 D2): the allowlist is a token prefix,
        # not a substring — "python3 -m pytest2" and lookalikes must reject.
        node = _node(evaluator_gate={
            "kind": "deterministic_command",
            "command": "python3 -m pytest2 --collect-only",
            "on_fail": "fail",
        })
        assert "PLAN_GATE_COMMAND_NOT_ALLOWLISTED" in _errors(_graph(node))


# ---------------------------------------------------------------------------
# R2(f) repair budget
# ---------------------------------------------------------------------------

class TestRepairBudget:
    def test_on_fail_derivable_budget_is_legal(self):
        assert _errors(_graph(_node())) == []

    def test_explicit_budget_is_legal(self):
        node = _node(evaluator_gate={"kind": "llm_eval"})
        node["max_repair_attempts"] = 0
        assert _errors(_graph(node)) == []

    def test_missing_budget_rejects(self):
        node = _node(evaluator_gate={"kind": "llm_eval"})  # no on_fail, no explicit
        assert "PLAN_REPAIR_BUDGET_MISSING" in _errors(_graph(node))

    def test_oversized_budget_rejects(self):
        node = _node()
        node["max_repair_attempts"] = 9
        assert "PLAN_REPAIR_BUDGET_MISSING" in _errors(_graph(node))


# ---------------------------------------------------------------------------
# R2(g) size bound
# ---------------------------------------------------------------------------

class TestSizeBound:
    def test_empty_graph_rejects(self):
        graph = _graph()
        graph["nodes"] = []
        assert "PLAN_GRAPH_EMPTY" in _errors(graph)

    def test_epic_explosion_rejects(self):
        nodes = [_node(f"N{i}") for i in range(1, pv.DEFAULT_MAX_NODES + 2)]
        assert "PLAN_GRAPH_TOO_LARGE" in _errors(_graph(*nodes))

    def test_bound_is_inclusive(self):
        nodes = [_node(f"N{i}") for i in range(1, pv.DEFAULT_MAX_NODES + 1)]
        assert _errors(_graph(*nodes)) == []


# ---------------------------------------------------------------------------
# plan_certificate stamp + check
# ---------------------------------------------------------------------------

class TestPlanCertificate:
    def test_stamp_on_pass_and_check_roundtrip(self):
        graph = _graph(_node())
        errors = pv.validate_plan(graph, None, None)
        assert errors == []
        pv.stamp_plan_certificate(graph)
        cert = graph.get("plan_certificate") or {}
        assert cert.get("verdict") == "PASS"
        assert cert.get("graph_hash")
        assert pv.check_plan_certificate(graph) == []

    def test_stamp_refuses_a_failing_graph(self):
        node = _node(evaluator_gate={"kind": "none", "on_fail": "fail"})
        graph = _graph(node)
        with pytest.raises(ValueError):
            pv.stamp_plan_certificate(graph)

    def test_missing_certificate_reports(self):
        graph = _graph(_node())
        codes = [e.get("code") for e in pv.check_plan_certificate(graph)]
        assert "PLAN_CERTIFICATE_MISSING" in codes

    def test_tampered_node_flips_the_hash(self):
        graph = _graph(_node())
        pv.stamp_plan_certificate(graph)
        tampered = copy.deepcopy(graph)
        tampered["nodes"][0]["capability_capsule_id"] = "smuggled-capsule"
        codes = [e.get("code") for e in pv.check_plan_certificate(tampered)]
        assert "PLAN_CERTIFICATE_HASH_MISMATCH" in codes

    def test_runtime_only_fields_do_not_flip_the_hash(self):
        # Dispatch mutates status/pane/dispatch_id constantly; the certificate
        # covers the GOVERNED subset only, or every tick would invalidate it.
        graph = _graph(_node())
        pv.stamp_plan_certificate(graph)
        running = copy.deepcopy(graph)
        running["nodes"][0]["status"] = "dispatched"
        running["nodes"][0]["dispatch_id"] = "d-123"
        running["nodes"][0]["pane"] = "operator-pool:builder.0"
        assert pv.check_plan_certificate(running) == []


# ---------------------------------------------------------------------------
# Dispatcher guard branch (planner_generated contracts require a certificate)
# ---------------------------------------------------------------------------

class TestDispatcherGuardBranch:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        import graph_node_dispatcher as gnd
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
        monkeypatch.setattr(gnd, "WORKFLOWS_DIR", WORKFLOWS_DIR, raising=False)
        self.gnd = gnd

    def test_planner_graph_without_certificate_fails_closed(self):
        graph = _graph(_node())
        verdict = self.gnd._workflow_contract_guard(graph)
        assert verdict is not None and not verdict.get("ok")
        assert any("PLAN_CERTIFICATE" in e for e in verdict.get("errors") or [])

    def test_planner_graph_with_valid_certificate_passes(self):
        graph = _graph(_node())
        assert pv.validate_plan(graph, None, None) == []
        pv.stamp_plan_certificate(graph)
        assert self.gnd._workflow_contract_guard(graph) is None

    def test_planner_graph_with_tampered_certificate_fails_closed(self):
        graph = _graph(_node())
        pv.stamp_plan_certificate(graph)
        graph["nodes"][0]["evaluator_gate"] = {"kind": "none"}
        verdict = self.gnd._workflow_contract_guard(graph)
        assert verdict is not None and not verdict.get("ok")
        assert any("PLAN_CERTIFICATE_HASH_MISMATCH" in e for e in verdict.get("errors") or [])

    def test_uncontracted_legacy_graph_is_untouched(self):
        graph = _graph(_node())
        graph.pop("workflow_contract_id")
        graph.pop("workflow_contract_version")
        assert self.gnd._workflow_contract_guard(graph) is None

    def test_fixed_contract_graphs_do_not_require_certificates(self):
        # code.cli_smoke structure checks are the fixed-path guard; the
        # certificate branch must not leak onto it.
        contract = wc.find_contract("code.cli_smoke", WORKFLOWS_DIR)
        graph = wc.instantiate(
            contract, {"tool": "uniqwords", "sprint_id": "sprint-p5-guard-fixed"}
        )
        assert self.gnd._workflow_contract_guard(graph) is None
