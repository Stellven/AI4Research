"""rc.9 regression: never evaluate or publish a still-running worker's files.

The final live rc.9 candidate exposed a real lifecycle race.  S2 wrote its
handoff and marked itself reviewing before the asynchronous Codex process had
finished.  The deterministic evaluator passed and Solar published the node at
18:59:50Z, but the same worker remained alive until 19:00:03Z and rewrote a
declared output at 18:59:52Z.  The user workspace therefore retained an
earlier snapshot instead of the worker's final bytes.

The invariant is class-level: a ``pm_dispatch`` builder's exact durable
``result.json`` must report successful completion before evaluation, proof, or
publication consumes its staging tree.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import workspace_binding  # noqa: E402


SID = "sprint-operator-result-before-publish"
NODE_ID = "S1"
OPERATOR_ID = "codex-builder"
TASK_ID = f"pm-{SID}-{NODE_ID}-builder"


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    workspace = tmp_path / "project"
    harness.mkdir()
    sprints.mkdir()
    workspace.mkdir()

    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gs, "HARNESS_DIR", harness)
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "_discover_evaluators", lambda _dry_run=False: [])
    monkeypatch.setattr(gnd, "_plan_validator_dispatch_guard", lambda _graph: None)

    workspace_binding.bind_active_workspace(harness, workspace)
    (sprints / f"{SID}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(workspace)}}),
        encoding="utf-8",
    )
    return harness, sprints, workspace


def _stage_reviewing_node(sprints: Path, *, deterministic_gate: bool = False) -> tuple[dict, Path, Path]:
    output = sprints / SID / "workdir" / "workspace" / "result.txt"
    output.parent.mkdir(parents=True)
    output.write_text("draft bytes\n", encoding="utf-8")
    node = {
        "id": NODE_ID,
        "status": "reviewing",
        "depends_on": [],
        "task_type": "implementation",
        "write_scope": ["workspace/result.txt"],
        "proof_obligations": [
            {
                "kind": "postcondition",
                "requirement": "output_present",
                "field": "workspace/result.txt",
                "proof_kind": "artifact_presence",
            }
        ],
        "dispatched_via": "pm_dispatch",
        "operator_id": OPERATOR_ID,
        "pm_task_id": TASK_ID,
        "assigned_to": f"operator:{OPERATOR_ID}",
        "dispatch_id": "graph-dispatch-live-worker",
    }
    if deterministic_gate:
        node["evaluator_gate"] = {
            "kind": "deterministic_command",
            "command": "python3 -c 'from pathlib import Path; assert Path(\"workspace/result.txt\").is_file()'",
        }
    graph = {
        "sprint_id": SID,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1.0",
        "plan_certificate": {"verdict": "PASS"},
        "nodes": [node],
        "node_results": {NODE_ID: {"status": "reviewing"}},
        "gate_results": {},
        "required_gates": [],
    }
    graph_path = sprints / f"{SID}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{SID}.{NODE_ID}-handoff.md").write_text(
        "# handoff\n\nworker says its node is ready for review\n",
        encoding="utf-8",
    )
    (sprints / f"{SID}.{NODE_ID}-eval.md").write_text(
        "# independent evaluation\n\nPASS\n",
        encoding="utf-8",
    )
    (sprints / f"{SID}.{NODE_ID}-eval.json").write_text(
        json.dumps({"node_id": NODE_ID, "verdict": "PASS", "summary": "temporary bytes pass"}),
        encoding="utf-8",
    )
    return graph, graph_path, output


def _write_operator_result(
    harness: Path,
    *,
    status: str = "completed",
    exit_code: int = 0,
) -> Path:
    result = harness / "run" / "operator-results" / OPERATOR_ID / TASK_ID / "result.json"
    result.parent.mkdir(parents=True)
    result.write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "operator_id": OPERATOR_ID,
                "sprint_id": SID,
                "node_id": NODE_ID,
                "status": status,
                "exit_code": exit_code,
                "started_at": "2026-07-14T18:59:04Z",
                "finished_at": "2026-07-14T19:00:03Z",
            }
        ),
        encoding="utf-8",
    )
    return result


def _bind_existing_eval_snapshot(graph: dict, graph_path: Path, sprints: Path) -> dict:
    node = graph["nodes"][0]
    gnd._emit_node_proof_sidecars(SID, node)
    snapshot = gnd._capture_eval_artifact_snapshot(SID, node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_path = sprints / f"{SID}.{NODE_ID}-eval.json"
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "artifact_snapshot_schema": snapshot["schema"],
            "artifact_snapshot_path": snapshot["path"],
            "artifact_snapshot_digest": snapshot["snapshot_digest"],
        }
    )
    eval_path.write_text(json.dumps(payload), encoding="utf-8")
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    return snapshot


def test_reconcile_waits_for_exact_operator_result_then_publishes_final_bytes(sandbox) -> None:
    harness, sprints, workspace = sandbox
    graph, graph_path, staged_output = _stage_reviewing_node(sprints)

    waiting = gnd._reconcile_existing_dispatches(graph, graph_path)

    assert gs.node_status(graph, NODE_ID) == "reviewing"
    assert any(row.get("reason") == "builder_operator_result_pending" for row in waiting)
    assert not (sprints / f"{SID}.{NODE_ID}-manifest.json").exists()
    assert not (sprints / f"{SID}.{NODE_ID}-publish.json").exists()
    assert not (workspace / "result.txt").exists()

    # This is the exact live-race boundary: the still-running worker changes a
    # declared output after the first scheduler observation.
    staged_output.write_text("final worker bytes\n", encoding="utf-8")
    _write_operator_result(harness)
    _bind_existing_eval_snapshot(graph, graph_path, sprints)

    completed = gnd._reconcile_existing_dispatches(graph, graph_path)

    assert any(row.get("node") == NODE_ID and row.get("status") == "passed" for row in completed)
    assert gs.node_status(graph, NODE_ID) == "passed"
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "final worker bytes\n"
    publish = json.loads((sprints / f"{SID}.{NODE_ID}-publish.json").read_text(encoding="utf-8"))
    assert publish["ok"] is True
    final_hash = hashlib.sha256(b"final worker bytes\n").hexdigest()
    assert publish["published"][0]["sha256"] == final_hash
    assert hashlib.sha256(staged_output.read_bytes()).hexdigest() == final_hash
    assert hashlib.sha256((workspace / "result.txt").read_bytes()).hexdigest() == final_hash


def test_deterministic_evaluation_does_not_run_while_builder_result_is_pending(sandbox) -> None:
    harness, sprints, _workspace = sandbox
    _graph, graph_path, _output = _stage_reviewing_node(sprints, deterministic_gate=True)
    eval_json = sprints / f"{SID}.{NODE_ID}-eval.json"
    eval_md = sprints / f"{SID}.{NODE_ID}-eval.md"
    eval_json.unlink()
    eval_md.unlink()

    result = gnd.dispatch_node_evals(str(graph_path))

    assert result["dispatched"] == []
    assert any(
        row.get("reason") == "builder_operator_result_pending" for row in result["skipped"]
    ), result
    assert not eval_json.exists()
    assert not eval_md.exists()

    _write_operator_result(harness)
    unlocked = gnd.dispatch_node_evals(str(graph_path))

    assert len(unlocked["dispatched"]) == 1
    assert unlocked["dispatched"][0]["dispatch_mode"] == "deterministic_gate"
    assert unlocked["dispatched"][0]["verdict"] == "PASS"
    assert eval_json.is_file()
    assert eval_md.is_file()


def test_direct_pass_verdict_cannot_publish_before_builder_result(sandbox) -> None:
    _harness, sprints, workspace = sandbox
    _graph, graph_path, _output = _stage_reviewing_node(sprints)

    result = gnd.node_verdict(
        str(graph_path),
        NODE_ID,
        "pass",
        eval_json=str(sprints / f"{SID}.{NODE_ID}-eval.json"),
    )

    assert result["ok"] is False
    assert result["reason"] == "builder_operator_result_pending"
    assert not (workspace / "result.txt").exists()


def test_failed_builder_result_is_requeued_instead_of_passing_or_wedging(sandbox) -> None:
    harness, sprints, workspace = sandbox
    graph, graph_path, _output = _stage_reviewing_node(sprints)
    _write_operator_result(harness, status="failed", exit_code=1)

    reconciled = gnd._reconcile_existing_dispatches(graph, graph_path)

    assert gs.node_status(graph, NODE_ID) == "pending"
    assert any(row.get("reason") == "operator_result_failed" for row in reconciled)
    assert not (sprints / f"{SID}.{NODE_ID}-publish.json").exists()
    assert not (workspace / "result.txt").exists()
