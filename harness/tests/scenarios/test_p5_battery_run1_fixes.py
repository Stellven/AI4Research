"""Battery run-1 B12 fix — declared outputs are enforced by the proof gate.

Evidence: run-archive/p5-battery-live-20260711T222837Z/12-B12 (sprint
sprint-20260712-004139-...-38978c6c). S1 passed via the reconcile seam with
its manifest recording all_outputs_present=false: workspace/pyproject.toml
and workspace/README.md were DECLARED in the write scope but never written.
The node's only proof obligations were capsule-injected (guard/resource) —
nothing named the work outputs, so _evaluate_proof_obligations had nothing
to check and the sprint terminalized passed/completed. UNTRUTHFUL: the
graph claimed outputs its own manifest disproved.

Fix under test: the proof gate blocks on missing DECLARED outputs
regardless of which obligations the node names (the AC-R6.3 pattern),
keyed off the manifest presence map so legacy uncontracted graphs stay
pinned. An existing directory satisfies a declared scope (the manifest now
binds the complete tree digest rather than treating it as a boolean). The
zero-obligation contracted variant is closed too (the gate no longer
early-returns required=False while a manifest exists).
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


B12_SCOPE = [
    "workspace/sumdir",
    "workspace/tests/test_sumdir.py",
    "workspace/pyproject.toml",
    "workspace/README.md",
]


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


def _stage_reviewing_node(sprints: Path, sid: str, graph: dict, node_id: str) -> Path:
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (sprints / f"{sid}.{node_id}-handoff.md").write_text(
        "# handoff\n\nbuilder work summary\n", encoding="utf-8"
    )
    (sprints / f"{sid}.{node_id}-eval.json").write_text(
        json.dumps({"node_id": node_id, "verdict": "PASS", "summary": "content pass"}),
        encoding="utf-8",
    )
    (sprints / f"{sid}.{node_id}-eval.md").write_text(
        "# eval\n\nindependent report\n", encoding="utf-8"
    )
    return graph_path


def _write_workspace_files(sprints: Path, sid: str, rel_paths: list[str]) -> None:
    for rel in rel_paths:
        target = sprints / sid / "workdir" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("content\n", encoding="utf-8")


def _bind_eval_to_current_artifacts(
    sprints: Path,
    sid: str,
    graph: dict,
    node_id: str,
) -> None:
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


class TestDeclaredOutputsGate:
    def test_b12_replay_missing_declared_outputs_never_pass(self, sandbox):
        """The B12 shape: obligations name only files that exist; two other
        DECLARED outputs are missing. Pre-fix this reconciled to passed."""
        sprints, _harness = sandbox
        sid = "sprint-b12-missing"
        node = _node("S1", B12_SCOPE, [_output_present("workspace/sumdir")])
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S1")
        _write_workspace_files(sprints, sid, ["workspace/sumdir", "workspace/tests/test_sumdir.py"])

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S1"]["status"] != "passed", repaired
        assert gs.node_status(graph, "S1") != "passed"
        notes = _ledger_notes(sprints, sid)
        assert any(
            k == "gate_check" and n == "eval_artifact_snapshot_missing"
            for _nid, k, n in notes
        ), notes

    def test_b12_missing_outputs_named_in_gate_result(self, sandbox):
        """The gate names the concrete missing rows so the repair dispatch
        (and the ledger reader) can see WHAT was unproven."""
        sprints, _harness = sandbox
        sid = "sprint-b12-named"
        node = _node("S1", B12_SCOPE, [_output_present("workspace/sumdir")])
        graph = _graph(sid, node)
        _stage_reviewing_node(sprints, sid, graph, "S1")
        _write_workspace_files(sprints, sid, ["workspace/sumdir", "workspace/tests/test_sumdir.py"])

        gate = gnd._run_node_proof_seam(
            sid, node, graph,
            sprints / f"{sid}.S1-eval.json",
            sprints / f"{sid}.S1-handoff.md",
        )

        assert gate["required"] is True
        assert gate["ok"] is False
        missing = [item for item in gate["missing"] if item.get("reason") == "MISSING_DECLARED_OUTPUT"]
        assert len(missing) == 1, gate["missing"]
        assert "workspace/pyproject.toml" in str(missing[0].get("field"))
        assert "workspace/README.md" in str(missing[0].get("field"))

    def test_all_declared_outputs_present_passes(self, sandbox):
        """Green pin: the same node shape with every declared output written
        reconciles to passed with a complete manifest."""
        sprints, _harness = sandbox
        sid = "sprint-b12-green"
        node = _node("S1", B12_SCOPE, [_output_present("workspace/sumdir")])
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S1")
        _write_workspace_files(sprints, sid, B12_SCOPE)
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S1")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S1"]["status"] == "passed", repaired
        manifest = json.loads((sprints / f"{sid}.S1-manifest.json").read_text(encoding="utf-8"))
        assert manifest["all_outputs_present"] is True

    def test_zero_obligation_contracted_node_still_gated(self, sandbox):
        """The required=False variant of the same hole: a contracted node with
        NO proof obligations at all must still not pass with a declared
        output missing."""
        sprints, _harness = sandbox
        sid = "sprint-b12-zero-obl"
        node = _node("S1", ["workspace/out.md"], [])
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S1")
        (sprints / sid / "workdir").mkdir(parents=True)  # declared output absent

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S1"]["status"] != "passed", repaired

    def test_declared_directory_scope_counts_as_present(self, sandbox):
        """A write_scope entry that resolves to an existing DIRECTORY must
        satisfy the gate and carry a complete directory-tree commitment."""
        sprints, _harness = sandbox
        sid = "sprint-b12-dirscope"
        node = _node("S1", ["workspace/report.md", "workspace/src"], [_output_present("workspace/report.md")])
        graph = _graph(sid, node)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S1")
        _write_workspace_files(sprints, sid, ["workspace/report.md", "workspace/src/module.py"])
        _bind_eval_to_current_artifacts(sprints, sid, graph, "S1")

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S1"]["status"] == "passed", repaired

    def test_legacy_uncontracted_zero_obligations_unchanged(self, sandbox):
        """Legacy pin: uncontracted + no obligations keeps the old
        reconcile-to-passed behavior — no manifest, no new gating."""
        sprints, _harness = sandbox
        sid = "sprint-b12-legacy"
        node = _node("S1", ["workspace/out.md"], [])
        graph = _graph(sid, node)
        graph.pop("workflow_contract_id", None)
        graph.pop("workflow_contract_version", None)
        graph.pop("plan_certificate", None)
        graph_path = _stage_reviewing_node(sprints, sid, graph, "S1")
        (sprints / sid / "workdir").mkdir(parents=True)  # artifact deliberately absent

        repaired = gnd._reconcile_existing_dispatches(graph, graph_path)

        entries = {item["node"]: item for item in repaired}
        assert entries["S1"]["status"] == "passed", repaired
        assert not (sprints / f"{sid}.S1-manifest.json").exists()
