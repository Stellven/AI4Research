"""Lane 3 serialized-file items (plan §0 serialized-files rule).

1. workflow_contract_id guard (design §1.2, C1+C2): a graph claiming a contract
   identity must match the registered contract's structure — net-new dispatcher
   code, fail-closed under SOLAR_GATE_LEDGER.
2. Per-node on_human_review policy consult (design §2 change 2, review 7.2):
   needs_human_review blocking is per-stage on the contracted path;
   warn_and_continue deps neither skip-cascade nor block readiness.
3. Bare-sonnet alias (AC-R8.3): under SOLAR_PRODUCT_MODE=1 bare "sonnet"
   resolves Anthropic, never GLM; flag-off keeps the legacy table bit-identical.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import workflow_contract as wc  # noqa: E402


WORKFLOWS_DIR = _HARNESS / "config" / "workflows"


def _contracted_graph():
    contract = wc.find_contract("code.cli_smoke", WORKFLOWS_DIR)
    assert contract is not None
    graph = wc.instantiate(contract, {"sprint_id": "lane3-guard-sprint",
                                      "workspace_root": "/tmp/lane3-guard-ws"})
    return graph


# ---------------------------------------------------------------------------
# 1. workflow_contract_id guard
# ---------------------------------------------------------------------------

class TestWorkflowContractGuard:
    @pytest.fixture(autouse=True)
    def _flag(self, monkeypatch):
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
        monkeypatch.setattr(gnd, "WORKFLOWS_DIR", WORKFLOWS_DIR, raising=False)

    def test_legit_instantiation_passes(self):
        graph = _contracted_graph()
        assert gnd._workflow_contract_guard(graph) is None

    def test_uncontracted_graph_is_ignored(self):
        graph = {"sprint_id": "x", "nodes": [{"id": "N1"}]}
        assert gnd._workflow_contract_guard(graph) is None

    def test_unregistered_contract_trips(self):
        graph = _contracted_graph()
        graph["workflow_contract_id"] = "no.such.contract"
        result = gnd._workflow_contract_guard(graph)
        assert result is not None
        assert result["reason"] == "workflow_contract_guard_failed"
        assert any("WORKFLOW_CONTRACT_UNREGISTERED" in e for e in result["errors"])

    def test_version_mismatch_trips(self):
        graph = _contracted_graph()
        graph["workflow_contract_version"] = "999.0"
        result = gnd._workflow_contract_guard(graph)
        assert result is not None
        assert any("WORKFLOW_CONTRACT_VERSION_MISMATCH" in e for e in result["errors"])

    def test_tampered_task_type_trips(self):
        graph = _contracted_graph()
        graph["nodes"][1]["task_type"] = "totally-different"
        result = gnd._workflow_contract_guard(graph)
        assert result is not None
        assert any("WORKFLOW_CONTRACT_STRUCTURE_MISMATCH" in e for e in result["errors"])

    def test_tampered_on_human_review_trips(self):
        """Round-4 G4 (reviewer tamper probe): flipping block_dependents ->
        warn_and_continue lets dependents dispatch on un-human-reviewed work.
        The field is contract-determined (instantiate copies it verbatim from
        the stage's evaluator_gate) — the guard must compare it."""
        graph = _contracted_graph()
        tampered = 0
        for node in graph["nodes"]:
            if node.get("on_human_review") == "block_dependents":
                node["on_human_review"] = "warn_and_continue"
                tampered += 1
        assert tampered, "code.cli_smoke must ship block_dependents stages for this probe"
        result = gnd._workflow_contract_guard(graph)
        assert result is not None
        assert any("on_human_review" in e for e in result["errors"])

    def test_removed_on_human_review_trips(self):
        # instantiate() always copies a shipped policy onto the node, so a
        # missing field on a policy-shipping contract means the graph was
        # edited — the raw compare fails closed on the delete too.
        graph = _contracted_graph()
        tampered = 0
        for node in graph["nodes"]:
            if node.get("on_human_review") == "block_dependents":
                del node["on_human_review"]
                tampered += 1
        assert tampered
        result = gnd._workflow_contract_guard(graph)
        assert result is not None
        assert any("on_human_review" in e for e in result["errors"])

    def test_extra_node_trips(self):
        graph = _contracted_graph()
        graph["nodes"].append({"id": "SNEAKY", "depends_on": [], "task_type": "code"})
        result = gnd._workflow_contract_guard(graph)
        assert result is not None
        assert any("WORKFLOW_CONTRACT_STRUCTURE_MISMATCH" in e for e in result["errors"])

    def test_planner_contract_requires_plan_certificate(self):
        # pm.generic.v1 stages come from the LLM planner. Pre-P5 the guard
        # checked registration + version only — a graph merely CLAIMING the
        # generic contract dispatched ungoverned. G1: the guard demands the
        # plan_validator's hash-stamped PASS (full matrix in
        # scenarios/test_p5_g1_plan_certificate.py).
        graph = {
            "sprint_id": "x",
            "workflow_contract_id": "pm.generic.v1",
            "workflow_contract_version": "1.0",
            "nodes": [{"id": "anything", "depends_on": [], "task_type": "planning"}],
        }
        verdict = gnd._workflow_contract_guard(graph)
        assert verdict is not None and not verdict.get("ok")
        assert any("PLAN_CERTIFICATE_MISSING" in e for e in verdict.get("errors") or [])

    def test_flag_off_never_trips(self, monkeypatch):
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
        graph = _contracted_graph()
        graph["workflow_contract_id"] = "no.such.contract"
        assert gnd._workflow_contract_guard(graph) is None

    def test_dispatch_ready_fails_closed_on_tampered_graph(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
        graph = _contracted_graph()
        graph["nodes"][1]["task_type"] = "totally-different"
        graph_path = tmp_path / "lane3-guard-sprint.task_graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        result = gnd.dispatch_ready(str(graph_path), dry_run=True)
        assert result["ok"] is False
        assert result["reason"] == "workflow_contract_guard_failed"


# ---------------------------------------------------------------------------
# 2. per-node on_human_review
# ---------------------------------------------------------------------------

def _review_graph(policy, contracted=True):
    graph = {
        "sprint_id": "lane3-review-sprint",
        "nodes": [
            {"id": "S1", "status": "needs_human_review", "depends_on": []},
            {"id": "S2", "status": "pending", "depends_on": ["S1"]},
        ],
        "node_results": {},
        "gate_results": {},
    }
    if contracted:
        graph["workflow_contract_id"] = "research.deepdive.rsi_demo"
    if policy is not None:
        graph["nodes"][0]["on_human_review"] = policy
    return graph


class TestOnHumanReviewPolicy:
    @pytest.fixture(autouse=True)
    def _flag(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)

    def test_warn_and_continue_dep_does_not_skip_dependents(self):
        graph = _review_graph("warn_and_continue")
        changed = gs.terminalize_dependency_blocked_nodes(graph)
        assert changed == []
        assert gs.node_status(graph, "S2") == "pending"

    def test_warn_and_continue_dep_does_not_block_readiness(self):
        graph = _review_graph("warn_and_continue")
        ready = gs.ready_nodes(graph)
        assert [n["id"] for n in ready] == ["S2"]

    def test_absent_policy_keeps_legacy_block(self):
        graph = _review_graph(None)
        changed = gs.terminalize_dependency_blocked_nodes(graph)
        assert [c["node"] for c in changed] == ["S2"]
        assert gs.node_status(graph, "S2") == "skipped"

    def test_block_dependents_policy_blocks(self):
        graph = _review_graph("block_dependents")
        changed = gs.terminalize_dependency_blocked_nodes(graph)
        assert [c["node"] for c in changed] == ["S2"]

    def test_flag_off_is_legacy_even_with_policy(self, monkeypatch):
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
        graph = _review_graph("warn_and_continue")
        changed = gs.terminalize_dependency_blocked_nodes(graph)
        assert [c["node"] for c in changed] == ["S2"]
        graph2 = _review_graph("warn_and_continue")
        assert gs.ready_nodes(graph2) == []

    def test_uncontracted_graph_is_legacy_even_with_policy(self):
        graph = _review_graph("warn_and_continue", contracted=False)
        changed = gs.terminalize_dependency_blocked_nodes(graph)
        assert [c["node"] for c in changed] == ["S2"]


# ---------------------------------------------------------------------------
# 3. bare-sonnet alias (AC-R8.3)
# ---------------------------------------------------------------------------

class TestBareSonnetAlias:
    @pytest.fixture(autouse=True)
    def _no_registry(self, monkeypatch):
        # Force the fallback path so the test pins the table itself, not the
        # machine-local model registry.
        monkeypatch.setattr(gnd, "_model_registry", lambda: {})
        monkeypatch.setattr(gnd, "_normalize_model", None, raising=False)

    def test_product_mode_maps_bare_sonnet_to_anthropic(self, monkeypatch):
        monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
        assert gnd._normalize_model_alias("sonnet") == "claude-sonnet"

    def test_legacy_keeps_the_glm_trap_bit_identical(self, monkeypatch):
        monkeypatch.delenv("SOLAR_PRODUCT_MODE", raising=False)
        assert gnd._normalize_model_alias("sonnet") == "zhipu-glm-4.7"

    def test_product_mode_leaves_other_aliases_alone(self, monkeypatch):
        monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
        assert gnd._normalize_model_alias("glm") == "zhipu-glm-5.1"
        assert gnd._normalize_model_alias("anthropic-sonnet") == "claude-sonnet"
