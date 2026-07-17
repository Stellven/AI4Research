"""rc.10 contracted-closeout authority regressions.

The published rc.9 ordinary-prompt run proved that a contracted node could be
marked passed through ``graph-scheduler mark`` without a consumable evaluator
verdict, artifact manifest, proof checks, or workspace publication.  A second
coordinator shortcut could infer PASS from mere write-scope existence.

These tests pin the class boundary:

* legacy/uncontracted graphs retain their direct-mark compatibility;
* contracted PASS is committed only by the dispatcher closeout transaction;
* repair/doctor backfills are never consumable PASS evidence;
* manifest creation and research quality are fail-closed;
* both live-verdict and sidecar-reconcile paths emit the same durable receipt;
* the coordinator's artifact-exists reconciliation is legacy-only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


HARNESS = Path(__file__).resolve().parents[2]
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402


def _node(*, write_scope: list[str] | None = None, **extra: object) -> dict:
    node = {
        "id": "S3",
        "status": "reviewing",
        "depends_on": [],
        "write_scope": list(write_scope or []),
        "proof_obligations": [],
    }
    node.update(extra)
    return node


def _graph(sid: str, node: dict, *, contracted: bool = True) -> dict:
    graph = {
        "sprint_id": sid,
        "nodes": [node],
        "node_results": {"S3": {"status": "reviewing"}},
        "gate_results": {},
    }
    if contracted:
        graph.update(
            {
                "workflow_contract_id": "pm.generic.v1",
                "workflow_contract_version": "1",
                "plan_certificate": {"algo": "sha256", "hash": "fixture"},
            }
        )
    return graph


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    sprints = tmp_path / "sprints"
    harness = tmp_path / "harness"
    sprints.mkdir()
    harness.mkdir()
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    return sprints, harness


def _write_graph_and_eval(
    sprints: Path,
    sid: str,
    graph: dict,
    *,
    eval_payload: dict | None = None,
    independent_handoff: bool = False,
) -> tuple[Path, Path]:
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    eval_path = sprints / f"{sid}.S3-eval.json"
    eval_path.write_text(
        json.dumps(eval_payload or {"node_id": "S3", "verdict": "PASS"}),
        encoding="utf-8",
    )
    if independent_handoff:
        (sprints / f"{sid}.S3-handoff.md").write_text(
            "# Handoff\n\nBuilder output is ready for independent review.\n",
            encoding="utf-8",
        )
        (sprints / f"{sid}.S3-eval.md").write_text(
            "# Independent evaluation\n\nPASS\n",
            encoding="utf-8",
        )
    return graph_path, eval_path


def _bind_eval_snapshot(
    sid: str,
    graph: dict,
    graph_path: Path,
    eval_path: Path,
) -> dict:
    node = graph["nodes"][0]
    gnd._emit_node_proof_sidecars(sid, node)
    snapshot = gnd._capture_eval_artifact_snapshot(sid, node, graph)
    assert snapshot["ok"] is True, snapshot
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


def test_direct_mark_cannot_pass_a_contracted_gate_node(sandbox: tuple[Path, Path]) -> None:
    _sprints, _harness = sandbox
    graph = _graph("sprint-rc10-direct", _node())

    with pytest.raises(ValueError, match="contracted_pass_requires_closeout_authority"):
        gs.mark_node_result(graph, "S3", "passed")

    assert gs.node_status(graph, "S3") == "reviewing"


def test_low_level_status_writer_cannot_pass_a_contracted_node(
    sandbox: tuple[Path, Path],
) -> None:
    _sprints, _harness = sandbox
    graph = _graph("sprint-rc10-set-status", _node())

    with pytest.raises(ValueError, match="contracted_pass_requires_closeout_authority"):
        gs.set_node_status(graph, "S3", "passed")

    assert gs.node_status(graph, "S3") == "reviewing"


def test_dispatcher_file_writer_cannot_pass_a_contracted_node(
    sandbox: tuple[Path, Path],
) -> None:
    sprints, _harness = sandbox
    sid = "sprint-rc10-file-writer"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid, _node())), encoding="utf-8")

    assert gnd._mark_graph_node(str(graph_path), "S3", "passed") is False
    assert gs.node_status(gs.load_graph(graph_path), "S3") == "reviewing"


def test_contracted_doctor_never_propagates_pass_when_ledger_flag_is_off(
    sandbox: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, _harness = sandbox
    sid = "sprint-rc10-doctor-flag-off"
    graph = _graph(sid, _node())
    graph["nodes"][0]["updated_at"] = "2026-07-15T00:00:00Z"
    graph["node_results"]["S3"] = {
        "status": "passed",
        "updated_at": "2026-07-15T00:00:01Z",
    }
    (sprints / f"{sid}.S3-eval.json").write_text(
        json.dumps({"node_id": "S3", "verdict": "PASS"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")

    report = gs.doctor_graph(graph, repair=True)

    assert graph["nodes"][0]["status"] == "reviewing"
    assert report.get("suppressed"), report


def test_uncontracted_direct_mark_remains_compatible(sandbox: tuple[Path, Path]) -> None:
    _sprints, _harness = sandbox
    graph = _graph("sprint-rc10-legacy", _node(), contracted=False)

    parent = gs.mark_node_result(graph, "S3", "passed")

    assert gs.node_status(graph, "S3") == "passed"
    assert parent["ready"] is True


def test_graph_scheduler_cli_cannot_bypass_contracted_closeout(
    sandbox: tuple[Path, Path],
) -> None:
    sprints, harness = sandbox
    sid = "sprint-rc10-cli"
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(sid, _node())), encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "HARNESS_DIR": str(harness),
            "HARNESS_SPRINTS_DIR": str(sprints),
            "SOLAR_GATE_LEDGER": "1",
        }
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(LIB / "graph_scheduler.py"),
            "mark",
            "--graph",
            str(graph_path),
            "--node",
            "S3",
            "--status",
            "passed",
            "--in-place",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "contracted_pass_requires_closeout_authority" in completed.stderr
    assert json.loads(graph_path.read_text(encoding="utf-8"))["nodes"][0]["status"] == "reviewing"


def test_repair_backfill_is_not_a_consumable_pass_verdict(
    sandbox: tuple[Path, Path],
) -> None:
    sprints, _harness = sandbox
    sid = "sprint-rc10-backfill"
    graph = _graph(sid, _node())
    graph_path, eval_path = _write_graph_and_eval(
        sprints,
        sid,
        graph,
        eval_payload={
            "node_id": "S3",
            "verdict": "PASS",
            "generated_by": "graph_scheduler.doctor",
            "generation_mode": "repair_backfill",
        },
    )

    result = gnd.node_verdict(
        str(graph_path),
        "S3",
        "pass",
        eval_json=str(eval_path),
        dispatch_downstream=False,
    )

    assert result["ok"] is False
    assert result["reason"] == "eval_verdict_not_consumable"
    assert gs.node_status(gs.load_graph(graph_path), "S3") != "passed"


def test_manifest_write_failure_blocks_contracted_pass(
    sandbox: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, _harness = sandbox
    sid = "sprint-rc10-manifest-fail"
    graph = _graph(sid, _node(write_scope=["workspace/result.txt"]))
    graph_path, eval_path = _write_graph_and_eval(sprints, sid, graph)
    output = sprints / sid / "workdir" / "workspace" / "result.txt"
    output.parent.mkdir(parents=True)
    output.write_text("verified output\n", encoding="utf-8")
    _bind_eval_snapshot(sid, graph, graph_path, eval_path)
    assert gnd._artifact_manifest is not None
    monkeypatch.setattr(gnd._artifact_manifest, "write_manifest", lambda *args, **kwargs: None)

    result = gnd.node_verdict(
        str(graph_path),
        "S3",
        "pass",
        eval_json=str(eval_path),
        dispatch_downstream=False,
    )

    assert result["ok"] is False
    assert result["reason"] == "artifact_manifest_write_failed"
    assert gs.node_status(gs.load_graph(graph_path), "S3") != "passed"


def test_reconcile_cannot_skip_the_research_quality_gate(
    sandbox: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints, _harness = sandbox
    sid = "sprint-rc10-research-gate"
    node = _node(
        write_scope=["workspace/final.md"],
        research_quality_gate_required=True,
    )
    graph = _graph(sid, node)
    graph_path, _eval_path = _write_graph_and_eval(
        sprints,
        sid,
        graph,
        independent_handoff=True,
    )
    final_md = sprints / sid / "workdir" / "workspace" / "final.md"
    final_md.parent.mkdir(parents=True)
    final_md.write_text("# Grounded report\n", encoding="utf-8")
    _bind_eval_snapshot(sid, graph, graph_path, _eval_path)
    monkeypatch.setattr(
        gnd,
        "_deepresearch_quality_gate_auto_run",
        lambda *_args, **_kwargs: {"present": False, "ok": False},
    )

    reconciled = gnd._reconcile_existing_dispatches(graph, graph_path)

    row = next(item for item in reconciled if item.get("node") == "S3")
    assert row["status"] != "passed"
    assert row["reason"] == "missing_deepresearch_quality_gate"
    assert gs.node_status(graph, "S3") != "passed"


@pytest.mark.parametrize("entry_path", ["node_verdict", "reconcile"])
def test_both_pass_entry_paths_emit_the_same_closeout_receipt(
    sandbox: tuple[Path, Path],
    entry_path: str,
) -> None:
    sprints, _harness = sandbox
    sid = f"sprint-rc10-receipt-{entry_path}"
    node = _node(write_scope=["workspace/result.txt"])
    graph = _graph(sid, node)
    graph_path, eval_path = _write_graph_and_eval(
        sprints,
        sid,
        graph,
        independent_handoff=entry_path == "reconcile",
    )
    output = sprints / sid / "workdir" / "workspace" / "result.txt"
    output.parent.mkdir(parents=True)
    output.write_text("verified output\n", encoding="utf-8")
    _bind_eval_snapshot(sid, graph, graph_path, eval_path)

    if entry_path == "node_verdict":
        result = gnd.node_verdict(
            str(graph_path),
            "S3",
            "pass",
            eval_json=str(eval_path),
            dispatch_downstream=False,
        )
        assert result["ok"] is True, result
        closed_graph = gs.load_graph(graph_path)
    else:
        result = gnd._reconcile_existing_dispatches(graph, graph_path)
        assert any(item.get("status") == "passed" for item in result), result
        closed_graph = graph

    closed_node = closed_graph["nodes"][0]
    receipt = closed_node.get("closeout_receipt")
    assert receipt["schema"] == "solar.node_closeout.v1"
    assert receipt["verdict"] == "passed"
    assert receipt["eval"]["consumable"] is True
    assert receipt["eval"]["artifact_snapshot"]["ok"] is True
    assert len(receipt["eval"]["artifact_snapshot"]["snapshot_digest"]) == 64
    assert receipt["manifest"]["ok"] is True
    assert receipt["manifest"]["eval_snapshot_match"] is True
    assert len(receipt["manifest"]["content_digest"]) == 64
    assert receipt["proof"]["ok"] is True
    assert receipt["publication"]["ok"] is True
    assert closed_graph["node_results"]["S3"]["closeout_receipt"] == receipt


def test_coordinator_write_scope_reconcile_is_legacy_only(
    sandbox: tuple[Path, Path],
) -> None:
    _sprints, harness = sandbox
    output = harness / "legacy-output.txt"
    output.write_text("legacy result\n", encoding="utf-8")
    reconcile = getattr(gs, "reconcile_legacy_write_scope_artifacts", None)
    assert callable(reconcile), "the coordinator shortcut must be a testable legacy-only helper"

    contracted = _graph(
        "sprint-rc10-coordinator-contract",
        _node(write_scope=["legacy-output.txt"]),
    )
    contracted_result = reconcile(contracted, harness)
    assert contracted_result["changed"] == []
    assert contracted_result["reason"] == "contracted_graph_requires_node_verdict"
    assert gs.node_status(contracted, "S3") == "reviewing"

    legacy = _graph(
        "sprint-rc10-coordinator-legacy",
        _node(write_scope=["legacy-output.txt"]),
        contracted=False,
    )
    legacy_result = reconcile(legacy, harness)
    assert legacy_result["changed"] == ["S3"]
    assert gs.node_status(legacy, "S3") == "passed"


def test_coordinator_contains_no_inline_node_pass_writer() -> None:
    source = (HARNESS / "coordinator.sh").read_text(encoding="utf-8")

    assert "reconcile_legacy_write_scope_artifacts" in source
    assert 'node["status"] = "passed"' not in source
