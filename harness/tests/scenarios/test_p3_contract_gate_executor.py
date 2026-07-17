#!/usr/bin/env python3
"""P3 pre-live blocker — the contracted evaluator-gate EXECUTOR (rehearsal
finding 1, 2026-07-08).

The workflow-contract schema admits three evaluator_gate kinds (none |
deterministic_command | llm_eval) and the structure guard enforces them, but
NOTHING in the runtime executed the first two: `evaluator_gate` was consumed
only by the guard. Both P2 contracts are all-llm_eval, so this stayed latent;
research.deepdive.rsi_demo needs `none` (D1/D4) and `deterministic_command`
(D2/D3/D6) and would wedge every non-llm stage in `reviewing`.

The executor is deliberately a DETERMINISTIC EVALUATOR: it produces the same
sidecar pair a live evaluator produces ({sid}.{node}-eval.json + -eval.md,
correct generation, honest generation_mode), so the PROVEN consume machinery
(sidecar reconcile -> mark -> ledger verdict -> repair on FAIL) runs
unchanged. Verdict mapping: exit 0 -> PASS (verdict_kind content); nonzero
exit -> FAIL content (a real content judgment); command-unrunnable/timeout ->
FAIL infrastructure (which AC-R4.1 already holds back from flipping
policy-passed nodes). Gate kind `none` writes a policy pass sidecar
(generation_mode evaluator_gate_none) recording that the contract declares no
evaluator for the stage. on_fail is enforced via instantiate() stamping
max_repair_attempts (fail -> 0, repair_once_then_fail -> 1) — consumed by the
EXISTING repair budget logic.

Everything is contracted-path-gated: uncontracted graphs and llm_eval stages
keep byte-identical legacy behavior.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import graph_node_dispatcher as gnd  # noqa: E402
import workflow_contract as wc  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"
SID = "p3-gate-exec"


def _node(gate: dict, node_id: str = "D2", status: str = "reviewing") -> dict:
    return {
        "id": node_id,
        "status": status,
        "task_type": "evidence",
        "evaluator_gate": gate,
        "depends_on": [],
    }


def _graph(nodes: list[dict], contracted: bool = True) -> dict:
    graph: dict = {"sprint_id": SID, "nodes": nodes}
    if contracted:
        graph["workflow_contract_id"] = "research.deepdive.rsi_demo"
        graph["workflow_contract_version"] = "1.1"
    return graph


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path))
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "_discover_evaluators", lambda dry_run=False: [])
    return tmp_path


def _dispatch(graph, tmp_path):
    # a node only needs eval once its builder handoff exists (live shape)
    for node in graph.get("nodes", []):
        handoff = tmp_path / "sprints" / f"{SID}.{node['id']}-handoff.md"
        if not handoff.exists():
            handoff.write_text(f"# {node['id']} handoff\nbuilder done\n", encoding="utf-8")
    graph_path = tmp_path / "sprints" / f"{SID}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    return gnd.dispatch_node_evals(str(graph_path))


def _eval_sidecars(tmp_path, node_id):
    sprints = tmp_path / "sprints"
    ej = sprints / f"{SID}.{node_id}-eval.json"
    em = sprints / f"{SID}.{node_id}-eval.md"
    payload = json.loads(ej.read_text(encoding="utf-8")) if ej.exists() else {}
    return payload, (em.read_text(encoding="utf-8") if em.exists() else "")


def test_deterministic_gate_pass_writes_consumable_eval_sidecars(sandbox):
    gate = {"kind": "deterministic_command",
            "command": "python3 -c \"import sys; sys.exit(0)\""}
    result = _dispatch(_graph([_node(gate)]), sandbox)
    assert any(d.get("dispatch_mode") == "deterministic_gate" for d in result.get("dispatched", [])), result
    payload, md = _eval_sidecars(sandbox, "D2")
    assert payload.get("verdict") == "PASS"
    assert payload.get("verdict_kind") == "content"
    assert payload.get("generation_mode") == "deterministic_command"
    assert payload.get("eval_generation") == 0
    assert payload.get("exit_code") == 0
    assert payload.get("artifact_snapshot_schema") == "solar.eval_artifact_snapshot.v1"
    assert len(str(payload.get("artifact_snapshot_digest") or "")) == 64
    assert Path(str(payload.get("artifact_snapshot_path") or "")).is_file()
    assert md.strip(), "eval.md must be non-empty (self-graded guard)"


def test_deterministic_gate_fail_is_content_fail(sandbox):
    gate = {"kind": "deterministic_command",
            "command": "python3 -c \"import sys; print('bad artifacts'); sys.exit(3)\"",
            "on_fail": "repair_once_then_fail"}
    _dispatch(_graph([_node(gate)]), sandbox)
    payload, md = _eval_sidecars(sandbox, "D2")
    assert payload.get("verdict") == "FAIL"
    assert payload.get("verdict_kind") == "content"
    assert payload.get("exit_code") == 3
    assert "bad artifacts" in md


def test_unrunnable_gate_is_infrastructure_fail(sandbox):
    gate = {"kind": "deterministic_command",
            "command": "python3 scripts/does-not-exist-anywhere.py"}
    _dispatch(_graph([_node(gate)]), sandbox)
    payload, _ = _eval_sidecars(sandbox, "D2")
    assert payload.get("verdict") == "FAIL"
    assert payload.get("verdict_kind") == "infrastructure"


def test_gate_none_writes_policy_pass_sidecar(sandbox):
    result = _dispatch(_graph([_node({"kind": "none"}, node_id="D1")]), sandbox)
    assert any(d.get("dispatch_mode") == "deterministic_gate" for d in result.get("dispatched", [])), result
    payload, md = _eval_sidecars(sandbox, "D1")
    assert payload.get("verdict") == "PASS"
    assert payload.get("generation_mode") == "evaluator_gate_none"
    assert md.strip()


def test_gate_waits_for_builder_completion(sandbox):
    """P3 live run 1: on the pool path the handoff appears while the builder
    is still in flight, and the executor fired at status=dispatched — D1
    passed prematurely (then the builder-complete mark downgraded it back to
    reviewing, where its now-stale sidecar was never re-consumed) and D3
    evaluated half-written artifacts (research_eval_json_missing -> FAIL ->
    repair archived the handoff -> both in-flight builders failed contract
    closeout exit 67). Deterministic gates evaluate COMPLETED stage outputs:
    the executor must wait for the builder-complete `reviewing` mark. D2 —
    whose gate happened to run after reviewing — passed cleanly in the same
    run, the controlled experiment for this rule."""
    gate = {"kind": "deterministic_command",
            "command": "python3 -c \"import sys; sys.exit(0)\""}
    node = _node(gate, status="dispatched")
    result = _dispatch(_graph([node]), sandbox)
    assert not any(d.get("dispatch_mode") == "deterministic_gate" for d in result.get("dispatched", []))
    assert any(
        s.get("reason") == "deterministic_gate_waiting_for_builder"
        for s in result.get("skipped", [])
    ), result
    payload, _ = _eval_sidecars(sandbox, "D2")
    assert not payload, "no sidecar may be written while the builder is in flight"


def test_llm_eval_stage_keeps_legacy_path(sandbox):
    """llm_eval must NOT be executed deterministically — with no evaluators
    discovered the node is skipped for capacity, exactly the legacy shape."""
    result = _dispatch(_graph([_node({"kind": "llm_eval"}, node_id="D5")]), sandbox)
    assert not any(d.get("dispatch_mode") == "deterministic_gate" for d in result.get("dispatched", []))
    payload, _ = _eval_sidecars(sandbox, "D5")
    assert not payload, "no executor sidecar for llm_eval stages"


def test_uncontracted_graph_keeps_legacy_path(sandbox):
    gate = {"kind": "deterministic_command", "command": "true"}
    result = _dispatch(_graph([_node(gate)], contracted=False), sandbox)
    assert not any(d.get("dispatch_mode") == "deterministic_gate" for d in result.get("dispatched", []))
    payload, _ = _eval_sidecars(sandbox, "D2")
    assert not payload


def test_pass_sidecar_reconciles_node_to_passed(sandbox):
    """The money path: executor sidecars -> existing reconcile -> passed."""
    gate = {"kind": "deterministic_command",
            "command": "python3 -c \"import sys; sys.exit(0)\""}
    node = _node(gate)
    graph = _graph([node])
    _dispatch(graph, sandbox)
    graph_path = sandbox / "sprints" / f"{SID}.task_graph.json"
    # Evaluation dispatch writes generation-bearing snapshot authority into the
    # durable graph. Reload it instead of restoring the pre-dispatch fixture.
    graph = gnd.load_graph(graph_path)
    reconciled = gnd._reconcile_existing_dispatches(graph, str(graph_path))
    assert next(n for n in graph["nodes"] if n["id"] == "D2")["status"] == "passed", reconciled


def test_instantiate_stamps_repair_budget_from_on_fail():
    contract = wc.find_contract("research.deepdive.rsi_demo", WORKFLOWS_DIR)
    graph = wc.instantiate(contract, {"sprint_id": "p3-budget-probe"})
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["D6"].get("max_repair_attempts") == 0  # on_fail: fail
    assert nodes["D2"].get("max_repair_attempts") == 1  # repair_once_then_fail
    assert nodes["D3"].get("max_repair_attempts") == 1
    for nid in ("D1", "D4", "D5"):
        assert "max_repair_attempts" not in nodes[nid]


def test_repaired_node_gate_verdict_is_consumed_not_archived(sandbox):
    """P3 live run 2: after repair_start, every fresh executor FAIL was
    archived as late_pre_repair_eval_output (the classifier keys on
    node.eval_dispatched_at being NEWER than the repair marker, which only the
    llm dispatch path stamped) -> the gate re-fired every ~11s forever. The
    executor now stamps eval_dispatched_at; a post-repair FAIL at an exhausted
    budget must therefore be CONSUMED and terminalize the node as failed."""
    gate = {"kind": "deterministic_command",
            "command": "python3 -c \"import sys; sys.exit(4)\"",
            "on_fail": "repair_once_then_fail"}
    node = _node(gate)
    node["repair_attempts"] = 1
    node["max_repair_attempts"] = 1
    node["repair_context"] = {"attempt": 1, "created_at": "2026-07-08T00:00:00Z"}
    graph = _graph([node])
    result = _dispatch(graph, sandbox)
    assert any(d.get("dispatch_mode") == "deterministic_gate" for d in result.get("dispatched", [])), result
    payload, _ = _eval_sidecars(sandbox, "D2")
    assert payload.get("verdict") == "FAIL"
    assert payload.get("eval_generation") == 1
    # dispatch_node_evals loads+saves its own graph copy — reread from disk
    graph_path = sandbox / "sprints" / f"{SID}.task_graph.json"
    saved = json.loads(graph_path.read_text(encoding="utf-8"))
    saved_node = next(n for n in saved["nodes"] if n["id"] == "D2")
    assert saved_node.get("eval_dispatched_at"), "executor must stamp eval_dispatched_at (staleness classifier input)"
    gnd._reconcile_existing_dispatches(saved, str(graph_path))
    ej = sandbox / "sprints" / f"{SID}.D2-eval.json"
    assert ej.exists(), "post-repair executor verdict must NOT be archived as late_pre_repair"
    assert saved_node["status"] in {"failed", "failed_review"}, saved["nodes"]


def test_late_progress_mark_cannot_regress_a_passed_node(sandbox):
    """P3 live run 3: EVERY stage gate passed live, but the generated worker
    runner marks its node `reviewing` AFTER the worker process exits
    (rc==0 && fresh handoff), and the worker's own closing instruction does
    the same mid-run. With llm evals (minutes) the window between those
    progress marks and node close was harmless; the deterministic gate closes
    nodes in SECONDS, so the runner's post-exit mark landed 4s after D2
    passed and regressed it to reviewing (ledger reopen:true) — the graph
    never reached all-terminal. Progress marks (reviewing/dispatched/...)
    must never regress a pass; repair reopens use their own dedicated path
    (failed_review -> assigned), and terminal flips (passed -> failed via a
    human/eval verdict) stay allowed."""
    import graph_scheduler as gs
    gate = {"kind": "deterministic_command",
            "command": "python3 -c \"import sys; sys.exit(0)\""}
    node = _node(gate)
    graph = _graph([node])
    _dispatch(graph, sandbox)
    graph_path = sandbox / "sprints" / f"{SID}.task_graph.json"
    saved = json.loads(graph_path.read_text(encoding="utf-8"))
    gnd._reconcile_existing_dispatches(saved, str(graph_path))
    d2 = next(n for n in saved["nodes"] if n["id"] == "D2")
    assert d2["status"] == "passed"
    # the runner's late completion mark (graph-scheduler mark --status reviewing)
    result = gs.mark_node_result(saved, "D2", "reviewing", note="builder complete")
    assert gs.node_status(saved, "D2") == "passed", (
        "late progress mark regressed a passed node (P3 run-3 reopen wedge)"
    )
    assert result.get("refused_progress_regression"), result
    # terminal flip stays allowed (human/eval verdict semantics)
    gs.mark_node_result(saved, "D2", "failed", note="human overturn")
    assert gs.node_status(saved, "D2") == "failed"
