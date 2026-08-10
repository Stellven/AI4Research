"""AC-R4.1 / R4.2 / R4.4 acceptance replays (requirements R4).

AC-R4.1  v5 replay — a mechanical FAIL (research_eval_json_missing) cannot flip
         a policy-passed node; verdict_kind is set by the gate runner.
AC-R4.2  LDES shape — a critic record verdict=block blocks the gate even when
         the critic NODE status is passed (locks 5fcff602/983ce35a).
AC-R4.4  stale-generation evidence is archived (non-consumable record), never
         applied (locks 714eb781); pm_task_id correlation preserved (2a8ab9db).

(AC-R4.3's property/audit suite lives in test_status_writer_surface.py and the
consumability unit tests in test_gate_ledger_module.py.)
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

import gate_ledger as gl  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


SID = "lane3-r4-sprint"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    return tmp_path


def _contracted_graph(nodes):
    return {
        "sprint_id": SID,
        "workflow_contract_id": "research.deepdive.rsi_demo",
        "nodes": nodes,
        "node_results": {},
        "gate_results": {},
    }


def _write_graph(tmp_path, graph):
    path = tmp_path / f"{SID}.task_graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    return str(path)


def _bind_content_fail_eval(tmp_path: Path, graph: dict, node_id: str) -> tuple[str, str]:
    graph_path = Path(_write_graph(tmp_path, graph))
    handoff = tmp_path / f"{SID}.{node_id}-handoff.md"
    handoff.write_text("# handoff\n\ncontent ready for review\n", encoding="utf-8")
    node = next(item for item in graph["nodes"] if item["id"] == node_id)
    gnd._emit_node_proof_sidecars(SID, node)
    snapshot = gnd._capture_eval_artifact_snapshot(SID, node, graph)
    assert snapshot.get("ok") is True, snapshot
    eval_path = tmp_path / f"{SID}.{node_id}-eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "node_id": node_id,
                "verdict": "FAIL",
                "verdict_kind": "content",
                "summary": "report contradicts sources",
                "artifact_snapshot_schema": snapshot["schema"],
                "artifact_snapshot_path": snapshot["path"],
                "artifact_snapshot_digest": snapshot["snapshot_digest"],
            }
        ),
        encoding="utf-8",
    )
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    return str(graph_path), str(eval_path)


# ---------------------------------------------------------------------------
# AC-R4.1 — v5 mechanical-FAIL replay
# ---------------------------------------------------------------------------

class TestMechanicalFailCannotFlipPassed:
    def test_v5_replay_runner_vocabulary(self, sandbox, tmp_path):
        graph = _contracted_graph([
            {"id": "S1", "status": "passed", "depends_on": []},
        ])
        graph["node_results"]["S1"] = {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}
        graph_path = _write_graph(tmp_path, graph)

        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="research_eval_json_missing", dry_run=True)
        assert result["ok"] is False
        assert result["reason"] == "mechanical_fail_cannot_flip_passed_node"
        assert result["verdict_kind"] == "mechanical"

        # The node did not flip.
        reloaded = json.loads(Path(graph_path).read_text(encoding="utf-8"))
        assert reloaded["nodes"][0]["status"] == "passed"

        # The verdict is archived, non-consumable; a gate_check hold explains why.
        verdicts = gl.read_records(sandbox, SID, node_id="S1", kind="eval_verdict")
        assert verdicts and verdicts[-1]["verdict"] == "FAIL"
        assert verdicts[-1]["verdict_kind"] == "mechanical"
        assert verdicts[-1]["archived"] is True
        assert gl.is_gate_consumable(verdicts[-1]) is False
        holds = gl.read_records(sandbox, SID, node_id="S1", kind="gate_check")
        assert holds and holds[-1]["note"] == "mechanical_fail_cannot_flip_passed_node"

    def test_v5_shape_handoff_no_eval_is_held(self, sandbox, tmp_path):
        """Round-4 G1 (reviewer probe case B): the REAL v5 shape — recorded
        passed, handoff PRESENT, eval.json missing — is downgraded to effective
        'reviewing' by the fail-closed passed-without-eval rule, which bypassed
        the hold. The hold must gate on the RECORDED pass, not the effective
        status."""
        graph = _contracted_graph([
            {"id": "S1", "status": "passed", "depends_on": []},
        ])
        graph["node_results"]["S1"] = {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}
        graph_path = _write_graph(tmp_path, graph)
        (tmp_path / f"{SID}.S1-handoff.md").write_text("# handoff\n", encoding="utf-8")

        loaded = gs.load_graph(graph_path)
        assert gs.node_status(loaded, "S1") == "reviewing"  # the bypass precondition
        assert gs.node_recorded_status(loaded, "S1") == "passed"

        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="research_eval_json_missing", dry_run=True)
        assert result["ok"] is False
        assert result["reason"] == "mechanical_fail_cannot_flip_passed_node"

        reloaded = json.loads(Path(graph_path).read_text(encoding="utf-8"))
        assert reloaded["nodes"][0]["status"] == "passed"
        verdicts = gl.read_records(sandbox, SID, node_id="S1", kind="eval_verdict")
        assert verdicts and verdicts[-1]["archived"] is True
        assert gl.is_gate_consumable(verdicts[-1]) is False

    def test_v5_shape_with_exhausted_repair_budget_never_terminal_fails(self, sandbox, tmp_path):
        """Round-4 G1 (probe case B'): with the repair budget exhausted
        (repair_attempts=1, default max 1) the bypassed FAIL fell through to
        mark_node_result(..., 'failed') — a TERMINAL failure for an
        infrastructure reason. The hold must fire first."""
        graph = _contracted_graph([
            {"id": "S1", "status": "passed", "depends_on": [], "repair_attempts": 1},
        ])
        graph["node_results"]["S1"] = {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}
        graph_path = _write_graph(tmp_path, graph)
        (tmp_path / f"{SID}.S1-handoff.md").write_text("# handoff\n", encoding="utf-8")

        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="research_eval_json_missing", dry_run=True)
        assert result["reason"] == "mechanical_fail_cannot_flip_passed_node"
        reloaded = json.loads(Path(graph_path).read_text(encoding="utf-8"))
        assert reloaded["nodes"][0]["status"] == "passed"

    def test_content_fail_on_v5_shape_keeps_legacy_effect(self, sandbox, tmp_path):
        """The hold is for mechanical/infrastructure kinds only — a CONTENT
        FAIL on the same recorded-passed shape must keep flipping."""
        graph = _contracted_graph([
            {"id": "S1", "status": "passed", "depends_on": []},
        ])
        graph["node_results"]["S1"] = {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}
        graph_path, eval_path = _bind_content_fail_eval(tmp_path, graph, "S1")
        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="report contradicts sources", eval_json=eval_path,
                                  dry_run=True)
        assert result.get("reason") != "mechanical_fail_cannot_flip_passed_node"
        assert result.get("status") in {"failed", "failed_review"}

    def test_explicit_infrastructure_kind_also_held(self, sandbox, tmp_path):
        graph = _contracted_graph([{"id": "S1", "status": "passed", "depends_on": []}])
        graph["node_results"]["S1"] = {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}
        graph_path = _write_graph(tmp_path, graph)
        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="operator pool restarted",
                                  verdict_kind="infrastructure", dry_run=True)
        assert result["reason"] == "mechanical_fail_cannot_flip_passed_node"

    def test_content_fail_still_flips(self, sandbox, tmp_path):
        """A real (content) evaluator FAIL keeps its legacy effect — only the
        mechanical/infrastructure kinds are held."""
        graph = _contracted_graph([{"id": "S1", "status": "passed", "depends_on": []}])
        graph["node_results"]["S1"] = {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}
        graph_path, eval_path = _bind_content_fail_eval(tmp_path, graph, "S1")
        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="report contradicts sources", eval_json=eval_path,
                                  dry_run=True)
        assert result.get("reason") != "mechanical_fail_cannot_flip_passed_node"
        assert result.get("status") in {"failed", "failed_review"}

    def test_flag_off_keeps_legacy_flip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path)
        monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
        graph = _contracted_graph([{"id": "S1", "status": "passed", "depends_on": []}])
        graph["node_results"]["S1"] = {"status": "passed", "updated_at": "2026-07-07T00:00:00Z"}
        graph_path = _write_graph(tmp_path, graph)
        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="research_eval_json_missing", dry_run=True)
        assert result.get("reason") != "mechanical_fail_cannot_flip_passed_node"


# ---------------------------------------------------------------------------
# AC-R4.2 — LDES critic-block shape
# ---------------------------------------------------------------------------

class TestCriticBlockBlocksGate:
    def test_consumable_block_record_blocks_gate_despite_passed_node(self, sandbox):
        graph = _contracted_graph([
            {"id": "C1", "status": "passed", "depends_on": [], "gate": "G1"},
        ])
        gl.append_record(sandbox, SID, node_id="C1", kind="eval_verdict",
                         author={"type": "evaluator", "operator_id": "critic-1"},
                         verdict="block", verdict_kind="content")
        ok, blocking_node, detail = gs._gate_verdicts_ok(graph, ["C1"])
        assert ok is False
        assert blocking_node == "C1"
        assert detail.startswith("ledger_verdict_block:")

    def test_gate_result_blocked_through_verified_pass_commit(self, sandbox):
        graph = _contracted_graph([
            {"id": "C1", "status": "reviewing", "depends_on": [], "gate": "G1"},
        ])
        gl.append_record(sandbox, SID, node_id="C1", kind="eval_verdict",
                         author={"type": "evaluator", "operator_id": "critic-1"},
                         verdict="block", verdict_kind="content")
        gs.commit_verified_node_pass(
            graph,
            "C1",
            closeout_receipt={
                "schema": "solar.node_closeout.v1",
                "sid": SID,
                "node_id": "C1",
                "verdict": "passed",
                "eval": {
                    "consumable": True,
                    "record_id": "fixture-pass",
                    "path": "C1-eval.json",
                    "generation": 0,
                    "artifact_snapshot": {
                        "required": True,
                        "ok": True,
                        "schema": "solar.eval_artifact_snapshot.v1",
                        "path": "C1-eval-snapshot.json",
                        "snapshot_digest": "a" * 64,
                        "generation": 0,
                    },
                },
                "manifest": {
                    "ok": True,
                    "schema": "solar.artifact_manifest.v1",
                    "path": "C1-manifest.json",
                    "generation": 0,
                    "content_digest": "b" * 64,
                    "eval_snapshot_match": True,
                },
                "proof": {"ok": True},
                "research_quality": {"ok": True},
                "publication": {"ok": True, "required": False},
            },
        )
        gate = graph["gate_results"]["G1"]
        assert gate["status"] == "blocked"
        assert "ledger_verdict_block" in str(gate.get("reason") or "")

    def test_mechanical_fail_record_does_not_block_gate(self, sandbox):
        """Round-4 G2: gates consume verdict CONTENT (R4). A consumable
        mechanical FAIL — evidence machinery broke, not a content judgment —
        must not block the gate."""
        graph = _contracted_graph([
            {"id": "C1", "status": "passed", "depends_on": [], "gate": "G1"},
        ])
        gl.append_record(sandbox, SID, node_id="C1", kind="eval_verdict",
                         author={"type": "evaluator", "operator_id": "critic-1"},
                         verdict="FAIL", verdict_kind="mechanical")
        ok, _, detail = gs._gate_verdicts_ok(graph, ["C1"])
        assert ok is True, f"mechanical FAIL blocked the gate: {detail}"

    def test_infrastructure_fail_record_does_not_block_gate(self, sandbox):
        graph = _contracted_graph([
            {"id": "C1", "status": "passed", "depends_on": [], "gate": "G1"},
        ])
        gl.append_record(sandbox, SID, node_id="C1", kind="eval_verdict",
                         author={"type": "evaluator", "operator_id": "critic-1"},
                         verdict="FAIL", verdict_kind="infrastructure")
        ok, _, _ = gs._gate_verdicts_ok(graph, ["C1"])
        assert ok is True

    def test_human_verdict_fail_blocks_gate_regardless_of_kind(self, sandbox):
        # A human FAIL is always an authored content judgment for gate purposes.
        graph = _contracted_graph([
            {"id": "C1", "status": "passed", "depends_on": [], "gate": "G1"},
        ])
        gl.append_record(sandbox, SID, node_id="C1", kind="human_verdict",
                         author={"type": "human"},
                         verdict="FAIL", verdict_kind="mechanical")
        ok, blocking_node, detail = gs._gate_verdicts_ok(graph, ["C1"])
        assert ok is False
        assert blocking_node == "C1"

    def test_kindless_fail_record_blocks_gate_as_content(self, sandbox):
        # D6's default: anything outside the runner's mechanical vocabulary is
        # content — a kind-less FAIL keeps the stricter content effect.
        graph = _contracted_graph([
            {"id": "C1", "status": "passed", "depends_on": [], "gate": "G1"},
        ])
        gl.append_record(sandbox, SID, node_id="C1", kind="eval_verdict",
                         author={"type": "evaluator", "operator_id": "critic-1"},
                         verdict="FAIL")
        ok, _, _ = gs._gate_verdicts_ok(graph, ["C1"])
        assert ok is False

    def test_non_consumable_block_does_not_block(self, sandbox):
        graph = _contracted_graph([
            {"id": "C1", "status": "passed", "depends_on": [], "gate": "G1"},
        ])
        gl.append_record(sandbox, SID, node_id="C1", kind="eval_verdict",
                         author={"type": "doctor"},
                         verdict="block", verdict_kind="content",
                         gate_consumable=False)
        ok, _, _ = gs._gate_verdicts_ok(graph, ["C1"])
        assert ok is True

    def test_uncontracted_graph_skips_ledger_consult(self, sandbox):
        graph = {"sprint_id": SID, "nodes": [{"id": "C1", "status": "passed", "gate": "G1"}],
                 "node_results": {}, "gate_results": {}}
        gl.append_record(sandbox, SID, node_id="C1", kind="eval_verdict",
                         author={"type": "evaluator", "operator_id": "critic-1"},
                         verdict="block", verdict_kind="content")
        ok, _, _ = gs._gate_verdicts_ok(graph, ["C1"])
        assert ok is True


# ---------------------------------------------------------------------------
# AC-R4.4 — stale-generation archive + PM-task correlation
# ---------------------------------------------------------------------------

class TestStaleGenerationAndCorrelation:
    def test_stale_generation_eval_archived_with_record_never_applied(self, sandbox, tmp_path):
        eval_json = tmp_path / f"{SID}.S1-eval.json"
        eval_json.write_text(json.dumps({
            "verdict": "PASS",
            "eval_generation": 0,
            "summary": "stale pre-repair pass",
        }), encoding="utf-8")
        graph = _contracted_graph([
            {
                "id": "S1", "status": "reviewing", "depends_on": [],
                "eval_json": str(eval_json),
                "repair_attempts": 1,
                "repair_context": {"attempt": 1, "created_at": "2026-07-07T00:00:00Z"},
            },
        ])
        graph_path = _write_graph(tmp_path, graph)
        loaded = gs.load_graph(graph_path)
        gnd._reconcile_existing_dispatches(loaded, graph_path)

        # Never applied: the stale PASS did not close the node.
        assert gs.node_status(loaded, "S1") != "passed"
        # Archived + recorded as non-consumable.
        verdicts = gl.read_records(sandbox, SID, node_id="S1", kind="eval_verdict")
        assert verdicts, "stale-generation archive must leave a ledger record"
        row = verdicts[-1]
        assert row["archived"] is True
        assert row["stale_reason"], "the archive record must name why the evidence was stale"
        assert gl.is_gate_consumable(row, current_generation=1) is False

    def test_pm_task_id_correlation_preserved_on_verdict_records(self, sandbox, tmp_path):
        graph = _contracted_graph([
            {
                "id": "S1", "status": "reviewing", "depends_on": [],
                "eval_assignments": [
                    {"role": "evaluator", "pane": "operator-pool:mini-codex-eval-1",
                     "dispatch_id": "d-77", "pm_task_id": "pm-42"},
                ],
            },
        ])
        graph_path = _write_graph(tmp_path, graph)
        result = gnd.node_verdict(graph_path, "S1", "fail",
                                  reason="weak evidence", dry_run=True)
        assert result.get("reason") != "mechanical_fail_cannot_flip_passed_node"
        verdicts = gl.read_records(sandbox, SID, node_id="S1", kind="eval_verdict")
        assert verdicts and verdicts[-1]["pm_task_id"] == "pm-42"
        assert verdicts[-1]["verdict"] == "FAIL"
        assert verdicts[-1]["verdict_kind"] == "content"
