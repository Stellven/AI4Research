"""G3 divided-mark-authority fix — the reconcile path runs the proof seam.

Evidence (two live runs, mirror images of the same class):

- Run 12 (run-archive/p5-g3-live-rung-20260710T025050Z, the G3 PASS): S2, a
  deterministic-gate node, has NO eval_verdict ledger entry and NO manifest —
  it was marked passed by gate_check(deterministic_gate_executed) followed by
  `reconciled_from_eval_sidecar`. node_verdict — which owns BOTH the manifest
  write and the proof gate — never ran, so S2's proof obligations were never
  checked. Green run, but a whole node class passed ungoverned.
- Run 5 (p5-g3-live-rung-20260709T210652Z ledger): the mirror image — S1's
  gate_check verdict=block note=proof_obligations_failed was OVERWRITTEN by a
  later reconcile mark to passed.

Fix under test: _reconcile_existing_dispatches routes a PASS-sidecar
reconcile on the CONTRACTED path through the same proof seam node_verdict
uses (_run_node_proof_seam: emit support sidecars -> write workdir-anchored
manifest -> evaluate proof obligations). Proof failure never marks passed:
it records the gate_check block and enters the bounded repair path (terminal
failed once the budget is exhausted — truthful, never a silent loop).
Legacy UNCONTRACTED graphs keep byte-identical reconcile behavior (pinned).
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

import graph_scheduler as gs  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


def _output_present(field: str) -> dict:
    return {
        "field": field,
        "kind": "postcondition",
        "proof_kind": "artifact_presence",
        "requirement": "output_present",
    }


def _node(node_id: str, write_scope: list[str], obligations: list[dict], **extra) -> dict:
    node = {
        "id": node_id,
        "status": "reviewing",
        "depends_on": [],
        "write_scope": list(write_scope),
        "proof_obligations": list(obligations),
    }
    node.update(extra)
    return node


def _graph(sid: str, node: dict, **top) -> dict:
    graph = {
        "sprint_id": sid,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1",
        "plan_certificate": {"algo": "sha256", "hash": "test-not-revalidated-here"},
        "nodes": [node],
        "node_results": {node["id"]: {"status": "reviewing"}},
        "gate_results": {},
    }
    graph.update(top)
    return graph


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    return sprints, harness


def _stage_reviewing_node(sprints: Path, sid: str, graph: dict, node_id: str, verdict: str = "PASS") -> Path:
    """A run-12-S2-shaped state: handoff + independent PASS eval sidecar on
    disk, node in reviewing — exactly what the reconcile loop acts on."""
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{sid}.{node_id}-handoff.md").write_text(
        "# handoff\n\nbuilder work summary\n", encoding="utf-8"
    )
    (sprints / f"{sid}.{node_id}-eval.json").write_text(
        json.dumps({"node_id": node_id, "verdict": verdict, "summary": "gate output"}),
        encoding="utf-8",
    )
    # Non-empty eval.md = independent evaluator report (the deterministic gate
    # executor writes one too) -> the self-graded guard does not intercept.
    (sprints / f"{sid}.{node_id}-eval.md").write_text(
        "# eval\n\nindependent report\n", encoding="utf-8"
    )
    return graph_path


def _bind_eval_to_current_artifacts(
    sprints: Path,
    sid: str,
    graph: dict,
    node_id: str,
) -> None:
    """Model the real evaluator dispatch after the fixture artifacts exist."""
    node = next(item for item in graph["nodes"] if item["id"] == node_id)
    gnd._emit_node_proof_sidecars(sid, node)
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    assert snapshot.get("ok") is True, snapshot
    eval_path = sprints / f"{sid}.{node_id}-eval.json"
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "artifact_snapshot_schema": snapshot["schema"],
            "artifact_snapshot_path": snapshot["path"],
            "artifact_snapshot_digest": snapshot["snapshot_digest"],
        }
    )
    eval_path.write_text(json.dumps(payload), encoding="utf-8")
    (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")


def _ledger_notes(sprints: Path, sid: str) -> list[tuple[str, str, str]]:
    path = sprints / f"{sid}.gate-ledger.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        rows.append((str(d.get("node_id") or ""), str(d.get("kind") or ""), str(d.get("note") or "")))
    return rows


class TestReconcileRunsProofSeam:
    def test_run12_replay_reconcile_pass_writes_manifest(self, sandbox):
        """Run-12 S2 replay: artifacts exist under the workdir — the reconcile
        pass must produce the SAME governance trail node_verdict produces (a
        workdir-anchored manifest) and still mark the node passed."""
        sprints, _harness = sandbox
        sid = "sprint-g3rec-pass"
        node = _node("S2", ["workspace/test-report.md"], [_output_present("workspace/test-report.md")])
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S2")
        target = sprints / sid / "workdir" / "workspace" / "test-report.md"
        target.parent.mkdir(parents=True)
        target.write_text("4 passed\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S2")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S2"]["status"] == "passed", repaired
        manifest_path = sprints / f"{sid}.S2-manifest.json"
        assert manifest_path.exists(), "reconcile pass must write the node manifest (run-12 gap)"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["all_outputs_present"] is True
        assert str(sprints / sid / "workdir") in str(manifest["roots"].get("canonical") or "")

    def test_reconcile_pass_with_missing_artifact_never_marks_passed(self, sandbox):
        """The run-5 mirror: proof obligations unsatisfied -> the reconcile
        path must NOT mark passed. With repair budget available it enters
        failed_review (bounded repair), and the gate_check block is in the
        ledger."""
        sprints, _harness = sandbox
        sid = "sprint-g3rec-block"
        node = _node("S2", ["workspace/ready.txt"], [_output_present("workspace/test-report.md")])
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S2")
        ready = sprints / sid / "workdir" / "workspace" / "ready.txt"
        ready.parent.mkdir(parents=True)
        ready.write_text("ready\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S2")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S2"]["status"] != "passed", repaired
        assert gs.node_status(graph, "S2") != "passed", graph.get("node_results")
        notes = _ledger_notes(sprints, sid)
        assert any(k == "gate_check" and n == "proof_obligations_failed" for _nid, k, n in notes), notes

    def test_reconcile_proof_failure_exhausted_budget_terminalizes_failed(self, sandbox):
        """Repair budget already burned -> the proof failure terminalizes the
        node failed (truthful terminal), never a silent re-block loop and
        never passed."""
        sprints, _harness = sandbox
        sid = "sprint-g3rec-exhaust"
        node = _node(
            "S2",
            ["workspace/ready.txt"],
            [_output_present("workspace/test-report.md")],
            repair_attempts=1,
            repair_max_attempts=1,
        )
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S2")
        ready = sprints / sid / "workdir" / "workspace" / "ready.txt"
        ready.parent.mkdir(parents=True)
        ready.write_text("ready\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S2")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S2"]["status"] == "failed", repaired
        assert gs.node_status(graph, "S2") == "failed"
        notes = _ledger_notes(sprints, sid)
        assert any(k == "gate_check" and n == "proof_obligations_failed" for _nid, k, n in notes), notes

    def test_uncontracted_reconcile_behavior_unchanged(self, sandbox):
        """Legacy pin: an UNCONTRACTED graph keeps the old reconcile-to-passed
        behavior byte-identical — no manifest, no proof enforcement."""
        sprints, _harness = sandbox
        sid = "sprint-g3rec-legacy"
        node = _node("S2", ["workspace/out.md"], [_output_present("workspace/out.md")])
        graph = _graph(sid, node)
        graph.pop("workflow_contract_id", None)
        graph.pop("workflow_contract_version", None)
        graph.pop("plan_certificate", None)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S2")
        (sprints / sid / "workdir").mkdir(parents=True)  # artifact deliberately absent

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S2"]["status"] == "passed", repaired
        assert not (sprints / f"{sid}.S2-manifest.json").exists()

    def test_reconcile_fail_sidecar_path_unchanged(self, sandbox):
        """A FAIL sidecar keeps the existing repair semantics (regression pin
        around the inserted seam)."""
        sprints, _harness = sandbox
        sid = "sprint-g3rec-fail"
        node = _node("S2", ["workspace/out.md"], [_output_present("workspace/out.md")])
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S2", verdict="FAIL")
        output = sprints / sid / "workdir" / "workspace" / "out.md"
        output.parent.mkdir(parents=True)
        output.write_text("candidate output\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S2")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S2"]["status"] == "failed_review", repaired
        assert entries["S2"]["reason"] == "eval_sidecar_failed_repair_requested"


class TestTestEvidenceObligationHonorsField:
    """Second bug the run-12 replay exposed (masked by the reconcile bypass):
    an obligation like {requirement: test_evidence_present, field:
    workspace/test-report.md} — the real S2 capsule shape — was routed by the
    coarse '"test" in requirement' heuristic to presence["test_log"] (a node
    artifacts key), IGNORING the declared field even when the manifest row
    for it says exists=true. node_verdict would have wrongly blocked run-12's
    S2 had it ever run. The declared field must win; the test_log heuristic
    is the fallback for field-less obligations."""

    def test_test_evidence_obligation_satisfied_by_declared_field(self, sandbox):
        sprints, _harness = sandbox
        sid = "sprint-g3rec-testfield"
        node = _node(
            "S2",
            ["workspace/test-report.md"],
            [{
                "kind": "postcondition",
                "requirement": "test_evidence_present",
                "field": "workspace/test-report.md",
            }],
        )
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S2")
        target = sprints / sid / "workdir" / "workspace" / "test-report.md"
        target.parent.mkdir(parents=True)
        target.write_text("4 passed\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S2")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S2"]["status"] == "passed", repaired

    def test_test_evidence_obligation_still_fails_when_field_absent(self, sandbox):
        sprints, _harness = sandbox
        sid = "sprint-g3rec-testfield-miss"
        node = _node(
            "S2",
            ["workspace/ready.txt"],
            [{
                "kind": "postcondition",
                "requirement": "test_evidence_present",
                "field": "workspace/test-report.md",
            }],
        )
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S2")
        ready = sprints / sid / "workdir" / "workspace" / "ready.txt"
        ready.parent.mkdir(parents=True)
        ready.write_text("ready\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S2")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S2"]["status"] != "passed", repaired
