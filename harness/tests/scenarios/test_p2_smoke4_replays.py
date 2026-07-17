#!/usr/bin/env python3
"""P2 smoke-4 deterministic replays (fail bundle p2-sprint-20260707-201914,
fixture P2-CODEX-SMOKE-S2-CAPSULE-GUARD.fixture.json).

Live smoke 4 at 83041a6e surfaced three distinct root causes; each is replayed
red-first here against the REAL seams (no mocks):

1. CAPSULE AUTHORITY (the S2 wedge): graph_scheduler.enqueue_ready lets the
   APO plan compiler's dispatch-time re-classification OVERWRITE the
   contract-assigned capability_capsule_id (S2 'code' node classified
   TestRunner -> cap.requirement-compiler-verification). The mutated node then
   (a) fails capsule task_type admission at operator submit and (b) trips
   _workflow_contract_guard on every subsequent dispatch attempt -> the node
   bounces assigned->pending forever (48 guard failures in the live events).
   On a contracted graph the workflow contract is the capsule authority.

2. TOOLS-SHADOW ROUTE RECORDS: pm_dispatch.py and operatord.py execute as
   scripts from harness/tools, so sys.path[0] is the tools dir. Their
   'if lib not in sys.path: insert(0)' guards are satisfied by an inherited
   PYTHONPATH=harness/lib (exactly what the live sandbox e2e.env pins), so lib
   never gains PRECEDENCE and `import operator_runtime` resolves the stale
   tools/operator_runtime.py — the copy without the Lane 3 _ledger_route
   hooks. Result: zero route records for every stage while every other ledger
   kind lands (the smoke-4 signature). The in-process tests in
   gate_ledger/test_route_records.py are structurally blind to this: the
   regression only exists when the tools script is the process entrypoint.

3. PROOF-GATE OUTPUT KEYING: contract output obligations carry the bare
   output name (field 'uniqwords.py') while artifact_manifest.presence_map
   keys rows by the full declared relpath
   (output:sprints/<sid>/workdir/uniqwords.py). _evaluate_proof_obligations
   looks up presence[field] -> proof_obligations_failed on a node whose
   outputs all exist (live S1 only survived by racing the sidecar reconcile).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import artifact_manifest as am  # noqa: E402
import gate_ledger as gl  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import workflow_contract as wc  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"
TOOLS_DIR = _HARNESS / "tools"
REAL_PERSONAS_DIR = _HARNESS / "personas"

OP_ID = "fake-p2-builder"
CONTRACT_CAPSULE = "cap.requirement-compiler-implementation"


# ---------------------------------------------------------------------------
# 1. Capsule authority on the contracted path
# ---------------------------------------------------------------------------

class TestContractCapsuleAuthority:
    @pytest.fixture()
    def contracted_graph(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path / "sprints")
        monkeypatch.setattr(gnd, "WORKFLOWS_DIR", WORKFLOWS_DIR, raising=False)
        contract = wc.find_contract("code.cli_smoke", WORKFLOWS_DIR)
        assert contract is not None
        graph = wc.instantiate(contract, {
            "sprint_id": "p2-smoke4-capsule",
            "workspace_root": str(tmp_path / "ws"),
            "tool": "uniqwords",
        })
        # S1 passed -> S2 is the ready node, exactly the live wedge position.
        for node in graph["nodes"]:
            if node["id"] == "S1":
                node["status"] = "passed"
        graph_path = tmp_path / "p2-smoke4-capsule.task_graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        return graph, graph_path

    def _dispatch_once(self, graph, graph_path):
        workers = [{
            "pane": "operator-pool:builder",
            "models": ["sonnet"],
            "skills": ["python"],
            "capabilities": ["python"],
            "busy": False,
        }]
        return gs.enqueue_ready(graph, str(graph_path), workers, dry_run=True)

    def test_dispatch_keeps_contract_assigned_capsule(self, contracted_graph):
        graph, graph_path = contracted_graph
        result = self._dispatch_once(graph, graph_path)
        assert any(e.get("node") == "S2" for e in result.get("enqueued", [])), result
        s2 = next(n for n in graph["nodes"] if n["id"] == "S2")
        assert s2.get("capability_capsule_id") == CONTRACT_CAPSULE, (
            "dispatch-time plan compilation overwrote the contract-assigned "
            f"capsule: {s2.get('capability_capsule_id')!r} (smoke-4 S2 wedge)"
        )

    def test_graph_still_passes_contract_guard_after_dispatch(self, contracted_graph):
        graph, graph_path = contracted_graph
        self._dispatch_once(graph, graph_path)
        verdict = gnd._workflow_contract_guard(graph)
        assert verdict is None, verdict

    def test_uncontracted_graph_keeps_apo_capsule_selection(self, tmp_path, monkeypatch):
        """Flag-off/parity guard: off the contracted path the APO compiler's
        capsule choice must keep flowing into the node (legacy behavior)."""
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
        monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path / "sprints")
        contract = wc.find_contract("code.cli_smoke", WORKFLOWS_DIR)
        graph = wc.instantiate(contract, {
            "sprint_id": "p2-smoke4-uncontracted",
            "workspace_root": str(tmp_path / "ws"),
            "tool": "uniqwords",
        })
        graph.pop("workflow_contract_id", None)
        for node in graph["nodes"]:
            if node["id"] == "S1":
                node["status"] = "passed"
            # strip the contract capsule so the APO choice is observable
            node.pop("capability_capsule_id", None)
        graph_path = tmp_path / "p2-smoke4-uncontracted.task_graph.json"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        self._dispatch_once(graph, graph_path)
        s2 = next(n for n in graph["nodes"] if n["id"] == "S2")
        assert str(s2.get("capability_capsule_id") or "")  # APO fills it


# ---------------------------------------------------------------------------
# 2. Route records survive the tools-script entrypoint (PYTHONPATH shadow)
# ---------------------------------------------------------------------------

def _write_fake_harness(harness_dir: Path) -> None:
    (harness_dir / "sprints").mkdir(parents=True, exist_ok=True)
    (harness_dir / "run").mkdir(parents=True, exist_ok=True)
    config_dir = harness_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "version": 1,
        "operators": {
            OP_ID: {
                "display_name": "Fake P2 builder",
                "role": "builder",
                "persona": "builder",
                "backend": "command",
                "command": "echo p2-fake-build-ok",
                "provider": "anthropic",
                "vendor": "Anthropic",
                "model": "fake-local",
                "enabled": True,
                "available": True,
                "roles": ["builder"],
                "task_classes": ["implementation"],
            }
        },
    }
    (config_dir / "physical-operators.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8"
    )
    personas = harness_dir / "personas"
    personas.mkdir(parents=True, exist_ok=True)
    for name in ("builder", "evaluator", "planner"):
        real = REAL_PERSONAS_DIR / f"{name}.md"
        if real.exists():
            personas.joinpath(f"{name}.md").write_text(
                real.read_text(encoding="utf-8"), encoding="utf-8"
            )
        else:
            personas.joinpath(f"{name}.md").write_text(
                f"# {name.title()}\nYou are a {name}.\n", encoding="utf-8"
            )


def _tools_entrypoint_env(harness_dir: Path) -> dict:
    """The live sandbox process env shape: PYTHONPATH pins harness/lib (e2e.env),
    the entrypoint is the tools script. No lib-precedence help from the caller."""
    env = dict(os.environ)
    env.update({
        "HARNESS_DIR": str(harness_dir),
        "SOLAR_HARNESS_DIR": str(harness_dir),
        "PYTHONPATH": _HARNESS_LIB,
        "SOLAR_GATE_LEDGER": "1",
        "SOLAR_OPERATORD_AUTO_KICK": "0",
        "SOLAR_PM_DISPATCH_ALLOW_DIRECT": "1",
        "SOLAR_PM_DEFAULT_PROVIDERS": "anthropic",
        "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS": "anthropic",
    })
    env.pop("HARNESS_SPRINTS_DIR", None)
    return env


class TestRouteRecordsFromToolsEntrypoints:
    SID = "p2-smoke4-route"

    def test_pm_dispatch_script_submit_emits_submitted_route_record(self, tmp_path):
        harness_dir = tmp_path / "harness"
        _write_fake_harness(harness_dir)
        env = _tools_entrypoint_env(harness_dir)
        proc = subprocess.run(
            [
                sys.executable, str(TOOLS_DIR / "pm_dispatch.py"), "submit",
                "--role", "builder",
                "--sprint", self.SID,
                "--node", "S1",
                "--task-type", "implementation",
                "--objective", "p2 smoke-4 route replay",
                "--context", json.dumps({"source": "test_p2_smoke4_replays"}),
            ],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout
        rows = gl.read_records(harness_dir / "sprints", self.SID, kind="route_record")
        submitted = [r for r in rows if r.get("phase") == "submitted"]
        assert submitted, (
            "pm_dispatch (tools entrypoint + PYTHONPATH=lib) submitted a task "
            "but wrote no 'submitted' route record — the stale "
            "tools/operator_runtime.py shadowed the lib module (smoke-4 "
            "zero-route-records signature)"
        )
        route = submitted[-1].get("route") or {}
        assert route.get("provider") == "anthropic"
        assert route.get("operator_id") == OP_ID

    def test_operatord_script_once_emits_completed_route_record(self, tmp_path):
        harness_dir = tmp_path / "harness"
        _write_fake_harness(harness_dir)
        env = _tools_entrypoint_env(harness_dir)
        env["SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS"] = "10"
        env["SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS"] = "20"
        # Seed the envelope through the REAL lib submit seam (in-process, its
        # 'submitted' record is covered above); what is under test here is the
        # operatord PROCESS writing the 'completed' record.
        import operator_runtime as opr
        old = {
            "HARNESS_DIR": opr.HARNESS_DIR,
            "OPERATOR_LEASE_DIR": opr.OPERATOR_LEASE_DIR,
            "OPERATOR_STATUS_DIR": opr.OPERATOR_STATUS_DIR,
            "OPERATOR_INBOX_DIR": opr.OPERATOR_INBOX_DIR,
            "OPERATOR_RESULTS_DIR": opr.OPERATOR_RESULTS_DIR,
            "OPERATOR_PERSONAS_DIR": opr.OPERATOR_PERSONAS_DIR,
            "PHYSICAL_OPERATORS_PATH": opr.PHYSICAL_OPERATORS_PATH,
        }
        os_env_before = {k: os.environ.get(k) for k in env}
        try:
            for key, value in env.items():
                os.environ[key] = value
            opr.HARNESS_DIR = harness_dir
            opr.OPERATOR_LEASE_DIR = harness_dir / "run" / "operator-leases"
            opr.OPERATOR_STATUS_DIR = harness_dir / "run" / "operator-status"
            opr.OPERATOR_INBOX_DIR = harness_dir / "run" / "operator-inbox"
            opr.OPERATOR_RESULTS_DIR = harness_dir / "run" / "operator-results"
            opr.OPERATOR_PERSONAS_DIR = harness_dir / "personas"
            opr.PHYSICAL_OPERATORS_PATH = harness_dir / "config" / "physical-operators.json"
            opr.submit({
                "task_id": "p2-route-task-1",
                "sprint_id": self.SID,
                "node_id": "S2",
                "operator_id": OP_ID,
                "task_type": "implementation",
                "objective": "p2 smoke-4 completed-route replay",
            })
        finally:
            for key, value in old.items():
                setattr(opr, key, value)
            for key, value in os_env_before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        proc = subprocess.run(
            [
                sys.executable, str(TOOLS_DIR / "operatord.py"), "daemon",
                "--operator", OP_ID, "--once", "--poll-interval", "0.1",
            ],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout
        deadline = time.time() + 10
        completed = []
        while time.time() < deadline:
            rows = gl.read_records(harness_dir / "sprints", self.SID, kind="route_record")
            completed = [r for r in rows if r.get("phase") == "completed"]
            if completed:
                break
            time.sleep(0.2)
        assert completed, (
            "operatord (tools entrypoint + PYTHONPATH=lib) wrote result.json "
            "but no 'completed' route record — stale tools/operator_runtime.py "
            "shadow (smoke-4 zero-route-records signature)"
        )
        route = completed[-1].get("route") or {}
        assert route.get("exit_code") == 0
        assert route.get("operator_id") == OP_ID


# ---------------------------------------------------------------------------
# 3. Proof gate: contract output obligations vs manifest declared-path keys
# ---------------------------------------------------------------------------

class TestProofGateOutputFieldKeying:
    SID = "p2-smoke4-proof"

    def test_output_present_matches_manifest_declared_relpath(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
        harness_dir = tmp_path / "harness"
        sprints = harness_dir / "sprints"
        workdir = sprints / self.SID / "workdir"
        workdir.mkdir(parents=True)
        (workdir / "uniqwords.py").write_text("print('ok')\n", encoding="utf-8")
        (workdir / "README.md").write_text("# ok\n", encoding="utf-8")
        monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
        monkeypatch.setattr(gnd, "HARNESS_DIR", harness_dir)
        monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)

        rel = f"sprints/{self.SID}/workdir"
        node = {
            "id": "S1",
            "status": "reviewing",
            # instantiate() declares write_scope as canonical-root relpaths —
            # the exact shape the live graph carried (task_graph S1).
            "write_scope": [f"{rel}/uniqwords.py", f"{rel}/README.md"],
            "outputs": [
                {"path": f"{rel}/uniqwords.py", "type": "python"},
                {"path": f"{rel}/README.md", "type": "markdown"},
            ],
            # ...while the contract obligation names the bare output file
            # (code.cli_smoke S1 proof_obligations, '<tool>.py' substituted).
            "proof_obligations": [
                {
                    "kind": "postcondition",
                    "requirement": "output_present",
                    "field": "uniqwords.py",
                    "proof_kind": "artifact_presence",
                }
            ],
        }
        manifest = am.write_manifest(
            sprints, self.SID, node,
            generation=0,
            base_dir=harness_dir,
            roots={"canonical": f"{rel}/"},
            sidecars={},
        )
        assert manifest and manifest.get("all_outputs_present") is True

        gate = gnd._evaluate_proof_obligations(self.SID, node)
        assert gate.get("required") is True
        assert gate.get("ok") is True, (
            "proof gate failed a node whose declared outputs all exist in the "
            f"manifest: {gate.get('missing')} (smoke-4 S1 "
            "proof_obligations_failed gate_check)"
        )
