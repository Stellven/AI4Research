"""G4-lite run-2 fix-round — stray workdir + stale-verdict generation fence.

Evidence: run-archive/p5-g4-lite-live-rung-20260710T133158Z (sprint
sprint-20260710-133320-...-b742b775). The default-on spine proved live to
certified dispatch; the rung failed on two seams:

1. STRAY WORKDIR (primary FAIL): the builder agent — cwd correctly set to
   sprints/<sid>/workdir, envelope and codex --cd both canonical — typed an
   ABSOLUTE path it constructed by analogy with the sprint's dot-suffixed
   artifact files: `mkdir -p .../sprints/<sid>.workdir/workspace/tests`
   (codex-cli-output.log:1938). Real work landed under sprints/<sid>.workdir,
   the canonical workdir stayed empty, patch emission reported
   patch_diff_not_emitted_no_write_scope_targets, and the proof gate failed
   a functionally-passing node (evaluator: "4 passed"). F-CLASS-16's agent-
   side tail: the workdir was only ever communicated via cwd, never stated.

2. STALE-VERDICT GENERATION FENCE: repair_start (attempt 1) at 13:40:05
   archived the gen-0 eval sidecars and dispatched the repair builder; at
   13:40:12 the ORIGINAL FAIL verdict arrived through node_verdict, which
   stamps eval_generation from the NODE's current repair_attempts — the
   stale verdict masqueraded as generation 1, burned the just-granted
   budget, and terminalized N1 while its repair builder was still running.
   The AC-R4.4 staleness fence (_eval_payload_stale_for_current_repair)
   existed but only the reconcile path consulted it.

Fixes under test:
- contract_gate_executor.recover_stray_workdir: certified-generic sprints
  relocate sprints/<sid>.workdir content into the canonical workdir (never
  overwriting), consumed by BOTH verification paths (deterministic gate
  executor cwd selection + the node proof seam); kill switch
  SOLAR_WORKDIR_STRAY_RECOVERY=0; legacy sprints untouched.
- The builder dispatch text for certified-generic sprints STATES the
  absolute workdir and the dot-form anti-pattern.
- node_verdict runs the AC-R4.4 fence: a stale-generation eval payload is
  archived non-consumable and never flips node status.
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

import contract_gate_executor as cge  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


def _certified_graph(sid: str, node: dict) -> dict:
    return {
        "sprint_id": sid,
        "workflow_contract_id": "pm.generic.v1",
        "workflow_contract_version": "1",
        "plan_certificate": {"algo": "sha256", "hash": "test-not-revalidated-here"},
        "plan_compile_required": True,
        "nodes": [node],
        "node_results": {node["id"]: {"status": str(node.get("status") or "reviewing")}},
        "gate_results": {},
    }


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


def _stage_stray(sprints: Path, sid: str, relpath: str, content: str = "print('x')\n") -> Path:
    stray = sprints / f"{sid}.workdir" / relpath
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text(content, encoding="utf-8")
    (sprints / sid / "workdir").mkdir(parents=True, exist_ok=True)
    return stray


class TestStrayWorkdirRecovery:
    def test_recover_moves_stray_into_canonical(self, sandbox, tmp_path):
        sprints, _ = sandbox
        sid = "sprint-g4r2-stray"
        graph = _certified_graph(sid, {"id": "N1", "status": "reviewing", "depends_on": []})
        (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        _stage_stray(sprints, sid, "workspace/linecount", "#!/usr/bin/env python3\n")
        _stage_stray(sprints, sid, "workspace/tests/test_linecount_cli.py", "def test_ok(): pass\n")

        result = cge.recover_stray_workdir(sprints, sid)

        assert sorted(result.get("recovered") or []) == [
            "workspace/linecount",
            "workspace/tests/test_linecount_cli.py",
        ], result
        assert (sprints / sid / "workdir" / "workspace" / "linecount").exists()
        assert (sprints / sid / "workdir" / "workspace" / "tests" / "test_linecount_cli.py").exists()

    def test_recover_never_overwrites_canonical(self, sandbox):
        sprints, _ = sandbox
        sid = "sprint-g4r2-noclobber"
        graph = _certified_graph(sid, {"id": "N1", "status": "reviewing", "depends_on": []})
        (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        _stage_stray(sprints, sid, "workspace/out.py", "STRAY\n")
        canonical = sprints / sid / "workdir" / "workspace" / "out.py"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("CANONICAL\n", encoding="utf-8")

        result = cge.recover_stray_workdir(sprints, sid)

        assert canonical.read_text(encoding="utf-8") == "CANONICAL\n"
        assert "workspace/out.py" in (result.get("skipped_existing") or []), result

    def test_recover_skips_legacy_sprints(self, sandbox):
        sprints, _ = sandbox
        sid = "sprint-g4r2-legacy"
        graph = _certified_graph(sid, {"id": "N1", "status": "reviewing", "depends_on": []})
        graph.pop("workflow_contract_id")
        graph.pop("plan_certificate")
        (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        stray = _stage_stray(sprints, sid, "workspace/out.py")

        result = cge.recover_stray_workdir(sprints, sid)

        assert not (result.get("recovered") or []), result
        assert stray.exists()

    def test_recover_kill_switch(self, sandbox, monkeypatch):
        sprints, _ = sandbox
        sid = "sprint-g4r2-kill"
        graph = _certified_graph(sid, {"id": "N1", "status": "reviewing", "depends_on": []})
        (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        stray = _stage_stray(sprints, sid, "workspace/out.py")
        monkeypatch.setenv("SOLAR_WORKDIR_STRAY_RECOVERY", "0")

        result = cge.recover_stray_workdir(sprints, sid)

        assert not (result.get("recovered") or []), result
        assert stray.exists()

    def test_proof_seam_recovers_the_run2_shape(self, sandbox):
        """The run-2 replay: declared output exists only under the stray
        workdir — the proof seam must recover it and the manifest must then
        see it under the canonical anchor."""
        sprints, _ = sandbox
        sid = "sprint-g4r2-proofseam"
        node = {
            "id": "N1",
            "status": "reviewing",
            "depends_on": [],
            "write_scope": ["workspace/linecount"],
            "proof_obligations": [{
                "field": "workspace/linecount",
                "kind": "postcondition",
                "proof_kind": "artifact_presence",
                "requirement": "output_present",
            }],
        }
        graph = _certified_graph(sid, node)
        (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        _stage_stray(sprints, sid, "workspace/linecount", "#!/usr/bin/env python3\n")

        proof_gate = gnd._run_node_proof_seam(sid, node, graph, "", None)

        assert proof_gate.get("ok") is True, proof_gate
        assert (sprints / sid / "workdir" / "workspace" / "linecount").exists()
        manifest = json.loads((sprints / f"{sid}.N1-manifest.json").read_text(encoding="utf-8"))
        assert manifest["all_outputs_present"] is True, manifest
        ledger = (sprints / f"{sid}.gate-ledger.jsonl").read_text(encoding="utf-8")
        assert "artifact_recovery" in ledger and "recovered_stray_workdir" in ledger, ledger


class TestGenericWorkdirTeaching:
    def test_builder_dispatch_states_the_workdir_and_the_antipattern(self, sandbox):
        sprints, _ = sandbox
        sid = "sprint-g4r2-teach"
        graph = _certified_graph(sid, {"id": "N1", "status": "pending", "depends_on": [],
                                       "write_scope": ["workspace/linecount"]})
        block = gnd._generic_workdir_block(sid, graph)
        assert f"{sid}/workdir" in block
        assert f"{sid}.workdir" in block  # the named anti-pattern
        assert "NEVER" in block or "never" in block

    def test_no_block_for_legacy_graphs(self, sandbox):
        sprints, _ = sandbox
        sid = "sprint-g4r2-teach-legacy"
        graph = _certified_graph(sid, {"id": "N1", "status": "pending", "depends_on": []})
        graph.pop("workflow_contract_id")
        graph.pop("plan_certificate")
        graph.pop("plan_compile_required")
        assert gnd._generic_workdir_block(sid, graph) == ""


class TestNodeVerdictGenerationFence:
    def _stage(self, sprints: Path, sid: str, *, repair_attempts: int, payload: dict) -> str:
        node = {
            "id": "N1",
            "status": "reviewing",
            "depends_on": [],
            "repair_attempts": repair_attempts,
            "repair_max_attempts": 1,
            "eval_assignments": [{"dispatch_id": "graph-eval-gen1-dispatch", "pane": "", "pm_task_id": ""}],
        }
        graph = _certified_graph(sid, node)
        graph_path = sprints / f"{sid}.task_graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        (sprints / f"{sid}.N1-handoff.md").write_text("# handoff\n\nwork\n", encoding="utf-8")
        (sprints / f"{sid}.N1-eval.json").write_text(json.dumps(payload), encoding="utf-8")
        (sprints / f"{sid}.N1-eval.md").write_text("# eval\n\nreport\n", encoding="utf-8")
        return str(graph_path)

    def test_stale_generation_fail_never_flips_the_node(self, sandbox):
        """Run-2 replay: node is at repair attempt 1; the arriving FAIL
        payload carries generation-0 metadata (old dispatch id, generation 0).
        It must be archived, never applied — no terminal flip, no budget burn."""
        sprints, _ = sandbox
        sid = "sprint-g4r2-fence"
        payload = {
            "node_id": "N1", "verdict": "FAIL",
            "summary": "functional passes but patch.diff missing",
            "eval_generation": 0, "repair_attempt": 0,
            "eval_dispatch_id": "graph-eval-gen0-dispatch",
        }
        graph_path = self._stage(sprints, sid, repair_attempts=1, payload=payload)

        result = gnd.node_verdict(graph_path, "N1", "fail",
                                  reason="functional passes but patch.diff missing",
                                  dispatch_downstream=False)

        assert result.get("ok") is False, result
        assert result.get("reason") == "stale_eval_generation", result
        graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
        assert gs.node_status(graph, "N1") != "failed", graph.get("node_results")

    def test_current_generation_fail_still_applies(self, sandbox):
        sprints, _ = sandbox
        sid = "sprint-g4r2-fence-cur"
        payload = {
            "node_id": "N1", "verdict": "FAIL", "summary": "real gen-1 fail",
            "eval_generation": 1, "repair_attempt": 1,
            "eval_dispatch_id": "graph-eval-gen1-dispatch",
        }
        graph_path = self._stage(sprints, sid, repair_attempts=1, payload=payload)

        result = gnd.node_verdict(graph_path, "N1", "fail", reason="real gen-1 fail",
                                  dispatch_downstream=False)

        assert result.get("reason") != "stale_eval_generation", result

    def test_unrepaired_node_payload_without_metadata_applies(self, sandbox):
        """Legacy pin: first-pass evals (attempt 0) are never fenced."""
        sprints, _ = sandbox
        sid = "sprint-g4r2-fence-first"
        payload = {"node_id": "N1", "verdict": "FAIL", "summary": "first-pass fail"}
        graph_path = self._stage(sprints, sid, repair_attempts=0, payload=payload)

        result = gnd.node_verdict(graph_path, "N1", "fail", reason="first-pass fail",
                                  dispatch_downstream=False)

        assert result.get("reason") != "stale_eval_generation", result


class TestTerminalSprintFreezesLateMarks:
    """Defect C tail (G4-lite run 2 drift): the sprint reached truthful
    terminal failed/failed at 13:40:18Z, the surviving repair builder ran its
    closing `graph-scheduler mark --node N1 --status reviewing` at 13:42:48Z,
    and the projection refresh propagated the reopen to the terminal sprint
    (history: graph_parent_failed -> graph_parent_projection_refreshed,
    status failed -> reviewing). mark_node_result already refuses progress
    regression on PASSED nodes (dfab5b1f); a TERMINAL SPRINT must refuse
    late progress marks for any node."""

    def _stage(self, sprints: Path, sid: str, status: str, phase: str) -> dict:
        node = {"id": "N1", "status": "failed", "depends_on": []}
        graph = _certified_graph(sid, node)
        graph["node_results"]["N1"] = {"status": "failed"}
        (sprints / f"{sid}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (sprints / f"{sid}.status.json").write_text(
            json.dumps({"id": sid, "sprint_id": sid, "status": status, "phase": phase}),
            encoding="utf-8",
        )
        return graph

    @pytest.mark.parametrize("status,phase", [("failed", "failed"), ("passed", "completed")])
    def test_late_progress_mark_refused_on_terminal_sprint(self, sandbox, status, phase):
        sprints, _ = sandbox
        sid = f"sprint-g4r2-mark-{status}"
        graph = self._stage(sprints, sid, status, phase)

        result = gs.mark_node_result(graph, "N1", "reviewing", note="late repair builder mark")

        assert result.get("refused_terminal_sprint_write"), result
        assert gs.node_status(graph, "N1") == "failed"

    def test_progress_mark_allowed_on_live_sprint(self, sandbox):
        sprints, _ = sandbox
        sid = "sprint-g4r2-mark-live"
        graph = self._stage(sprints, sid, "building", "build")

        result = gs.mark_node_result(graph, "N1", "reviewing", note="normal flow")

        assert not result.get("refused_terminal_sprint_write"), result
        assert gs.node_status(graph, "N1") == "reviewing"
