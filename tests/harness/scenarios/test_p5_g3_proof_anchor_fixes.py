"""G3 run-11 proof-anchor fix-round — F-CLASS-16 tail in the PROOF layer.

Run 11 (run-archive/p5-g3-live-rung-20260710T011720Z-crashrecovery, sprint
sprint-20260710-011912-intent-build-a-small-command-line-u-6df32ed7):
certified-generic builders execute with work_dir = sprints/<sid>/workdir and
wrote REAL artifacts (workdir/workspace/wordfreq.py, tests/, test_report.md;
pytest cache proves the tests ran). The gate ledger shows the same shape for
S1, S2 and S3: evaluator PASS content -> gate_check policy block
proof_obligations_failed -> evaluator re-records FAIL quoting the manifest.

Root cause (archived S1/S2/S3 manifests: roots {}, rows exists=false, while
the secret-leak guard scanned the SAME files under the workdir): the node
artifact manifest was written with base_dir=HARNESS_DIR and roots={} — the
planner-authored generic graph carries no artifact_roots map — so every
declared workspace/... output resolved to a nonexistent HARNESS_DIR path,
the manifest override flipped the presence map to false, and the proof gate
failed work that existed.

Fix under test: graph_node_dispatcher anchors the manifest for
CERTIFIED-GENERIC sprints at the sprint workdir with the contract's
canonical root (workspace/), normalizing the contract's alias spellings
(sprints/<sid>/workdir/..., workdir/...) onto it — the same principle as
the run-5 gate-cwd fix in contract_gate_executor (commit 519755a6 /
5c0ed562). Fixed contracts keep the HARNESS_DIR anchor and graph-carried
roots byte-identical (P2/P3 proven) — pinned below. Genuinely missing
outputs still fail the gate — pinned below.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import graph_scheduler as gs  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


def _output_present(field: str) -> dict:
    # The run-11 planner's obligation shape, verbatim class.
    return {
        "field": field,
        "kind": "postcondition",
        "proof_kind": "artifact_presence",
        "requirement": "output_present",
    }


def _graph(sid: str, node: dict, **top) -> dict:
    graph = {
        "sprint_id": sid,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1",
        "plan_certificate": {"algo": "sha256", "hash": "test-not-revalidated-here"},
        "nodes": [node],
        "node_results": {},
        "gate_results": {},
    }
    graph.update(top)
    return graph


def _node(node_id: str, write_scope: list[str], obligations: list[dict]) -> dict:
    return {
        "id": node_id,
        "status": "reviewing",
        "depends_on": [],
        "write_scope": list(write_scope),
        "proof_obligations": list(obligations),
    }


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Hermetic dispatcher: tmp sprints dir + tmp EMPTY harness dir.

    The empty harness dir is load-bearing for the red assertion: run 11's
    HARNESS_DIR had no workspace/ either, which is exactly why the manifest
    rows came back exists=false."""
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gs, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    return sprints, harness


def _stage_sprint(sprints: Path, sid: str, graph: dict, node_id: str) -> str:
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    # Real-evaluator sidecar set: eval.json PLUS a non-empty eval.md so the
    # self-graded guard does not intercept before the proof gate.
    (sprints / f"{sid}.{node_id}-handoff.md").write_text(
        "# handoff\n\nbuilder work summary\n", encoding="utf-8"
    )
    (sprints / f"{sid}.{node_id}-eval.json").write_text(
        json.dumps({"node_id": node_id, "verdict": "PASS", "summary": "content pass"}),
        encoding="utf-8",
    )
    (sprints / f"{sid}.{node_id}-eval.md").write_text(
        "# eval\n\nindependent evaluator report\n", encoding="utf-8"
    )
    return str(graph_path)


def _bind_eval_to_current_artifacts(
    sprints: Path,
    sid: str,
    graph_path: str,
    node_id: str,
) -> None:
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
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
    Path(graph_path).write_text(json.dumps(graph), encoding="utf-8")


def _manifest(sprints: Path, sid: str, node_id: str) -> dict:
    path = sprints / f"{sid}.{node_id}-manifest.json"
    assert path.exists(), "manifest sidecar must be written on the contracted path"
    return json.loads(path.read_text(encoding="utf-8"))


class TestRun11Replay:
    def test_certified_generic_pass_survives_proof_gate_for_workdir_outputs(self, sandbox):
        """The run-11 S1 replay: the artifact exists under the sprint workdir,
        the evaluator passed content — node-verdict pass must not be flipped
        by proof_obligations_failed."""
        sprints, _harness = sandbox
        sid = "sprint-g3run11-s1"
        node = _node("S1", ["workspace/wordfreq.py"], [_output_present("workspace/wordfreq.py")])
        graph_path = _stage_sprint(sprints, sid, _graph(sid, node), "S1")
        target = sprints / sid / "workdir" / "workspace" / "wordfreq.py"
        target.parent.mkdir(parents=True)
        target.write_text("print('wordfreq')\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph_path, "S1")

        result = gnd.node_verdict(graph_path, "S1", "pass", dispatch_downstream=False)

        assert result.get("reason") != "proof_obligations_failed", result
        assert result.get("ok") is True, result
        proof_gate = result.get("proof_gate") or {}
        assert proof_gate.get("required") is True
        assert proof_gate.get("ok") is True, proof_gate

        manifest = _manifest(sprints, sid, "S1")
        rows = {row["declared"]: row for row in manifest["rows"]}
        assert rows["workspace/wordfreq.py"]["exists"] is True, manifest
        assert manifest["all_outputs_present"] is True
        # The manifest must record the WORKDIR-anchored root, not HARNESS_DIR.
        assert str(sprints / sid / "workdir") in str(manifest["roots"].get("canonical") or ""), manifest

    def test_certified_generic_alias_spelled_scope_normalizes(self, sandbox):
        """The contract's alias spellings (sprints/<sid>/workdir/..., workdir/...)
        are validation-legal forms of the same root — the manifest must resolve
        them onto the workdir anchor exactly like the run-5 gate-cwd fix."""
        sprints, _harness = sandbox
        sid = "sprint-g3run11-alias"
        node = _node(
            "S2",
            [f"sprints/{sid}/workdir/workspace/tests/test_wordfreq.py", "workdir/workspace/report.md"],
            [
                _output_present("workspace/tests/test_wordfreq.py"),
                _output_present("workspace/report.md"),
            ],
        )
        graph_path = _stage_sprint(sprints, sid, _graph(sid, node), "S2")
        base = sprints / sid / "workdir" / "workspace"
        (base / "tests").mkdir(parents=True)
        (base / "tests" / "test_wordfreq.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        (base / "report.md").write_text("# report\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph_path, "S2")

        result = gnd.node_verdict(graph_path, "S2", "pass", dispatch_downstream=False)

        assert result.get("ok") is True, result
        manifest = _manifest(sprints, sid, "S2")
        assert manifest["all_outputs_present"] is True, manifest
        declared = sorted(row["declared"] for row in manifest["rows"])
        # Normalized onto the one path vocabulary (canonical workspace/ forms).
        assert declared == [
            "workspace/report.md",
            "workspace/tests/test_wordfreq.py",
        ], manifest

    def test_certified_generic_missing_output_still_blocks(self, sandbox):
        """The anchor fix must not weaken the gate: a genuinely absent declared
        output cannot acquire evaluator-snapshot authority."""
        sprints, _harness = sandbox
        sid = "sprint-g3run11-missing"
        node = _node("S3", ["workspace/test_report.md"], [_output_present("workspace/test_report.md")])
        graph_path = _stage_sprint(sprints, sid, _graph(sid, node), "S3")
        (sprints / sid / "workdir").mkdir(parents=True)  # workdir exists, artifact does not

        result = gnd.node_verdict(graph_path, "S3", "pass", dispatch_downstream=False)

        assert result.get("ok") is False
        assert result.get("reason") == "eval_artifact_snapshot_missing", result

    def test_fixed_contract_keeps_harness_dir_anchor(self, sandbox):
        """Fixed contracts (P2/P3 proven) keep base_dir=HARNESS_DIR and the
        graph-carried roots — the certified-generic anchor must not leak."""
        sprints, harness = sandbox
        sid = "sprint-g3run11-fixed"
        node = _node("S1", ["ws/out.txt"], [_output_present("ws/out.txt")])
        graph = _graph(sid, node, workflow_contract_id="code.cli_smoke", artifact_roots={"canonical": "ws/"})
        graph.pop("plan_certificate", None)
        graph_path = _stage_sprint(sprints, sid, graph, "S1")
        # Artifact lives under the HARNESS_DIR-anchored root; a sprint workdir
        # also exists to prove the generic anchor does not capture this graph.
        (sprints / sid / "workdir").mkdir(parents=True)
        (harness / "ws").mkdir()
        (harness / "ws" / "out.txt").write_text("ok\n", encoding="utf-8")
        _bind_eval_to_current_artifacts(sprints, sid, graph_path, "S1")

        result = gnd.node_verdict(graph_path, "S1", "pass", dispatch_downstream=False)

        assert result.get("ok") is True, result
        manifest = _manifest(sprints, sid, "S1")
        assert manifest["all_outputs_present"] is True, manifest
        assert str(manifest["roots"]["canonical"]) == str(harness / "ws"), manifest

    def test_manifest_anchor_falls_back_without_workdir(self, sandbox):
        """A certified-generic graph whose sprint workdir does not exist keeps
        the legacy HARNESS_DIR anchor (nothing to anchor to)."""
        sprints, harness = sandbox
        sid = "sprint-g3run11-noworkdir"
        node = _node("S1", ["workspace/x.py"], [_output_present("workspace/x.py")])
        base, roots, scope = gnd._manifest_anchor(sid, _graph(sid, node), node)
        assert base == harness
        assert scope is None
        assert roots == {}
