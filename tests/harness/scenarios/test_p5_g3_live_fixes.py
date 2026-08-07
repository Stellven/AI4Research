"""P5 G3 live rung fix-round: regressions for the two live-run defects.

The G3 live rung (run-archive/p5-g3-live-rung-20260709T161420Z) failed before
builder execution:

1. The dispatch path's capability enrichment mutated the CERTIFIED graph:
   assign_ready -> auto_enrich_graph -> enrich_graph injected
   `required_capabilities: []` into every node whose planner omitted the
   field. required_capabilities is certificate-governed, so the write changed
   the governed hash and the dispatch guard refused the graph it had just
   admitted (PLAN_CERTIFICATE_HASH_MISMATCH; deletion sweep over the archived
   graph reproduces the stamped hash exactly when the injected fields are
   removed). Inference may run before stamping, never after.
2. The refusal then looped silently: the coordinator re-ticked, the guard
   re-refused, and the sprint sat drafting/spec for ~40 minutes until the
   run budget expired with no terminal state. A PASS-stamped graph whose
   governed content changed is unrecoverable at dispatch time (re-stamping
   would launder the edit), so the sprint must fail closed with a truthful
   terminal state — while an UNCERTIFIED refusal stays non-terminal (that is
   the normal pre-planner / bounce state; terminalizing it would recreate the
   E5 starvation class).

Same sandbox conventions as test_p5_g2b_review_fixes.py.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(_HARNESS / "lib"))

import plan_validator as pv  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture_config(tmp_path: Path) -> tuple[Path, Path]:
    config = tmp_path / "config"
    capsules = config / "capability-capsules"
    workflows = config / "workflows"
    capsules.mkdir(parents=True)
    workflows.mkdir(parents=True)
    shutil.copy2(
        _HARNESS / "config" / "capability-capsules" / "cap.requirement-compiler-implementation.yaml",
        capsules / "cap.requirement-compiler-implementation.yaml",
    )
    shutil.copy2(
        WORKFLOWS_DIR / "pm.generic.v1.workflow.json",
        workflows / "pm.generic.v1.workflow.json",
    )
    _write_json(
        config / "physical-operators.json",
        {
            "version": 1,
            "operators": {
                "test-builder": {
                    "enabled": True,
                    "deprecated": False,
                    "health_status": "ok",
                    "role": "builder",
                    "roles": ["builder"],
                    "provider": "anthropic",
                }
            },
        },
    )
    return config, workflows


def _valid_node(**overrides) -> dict:
    node = {
        "id": "B1",
        "goal": "Implement the requested change.",
        "depends_on": [],
        "logical_operator": "ImplementationWorker",
        "task_type": "implementation",
        "dispatch_task_type": "implementation",
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "allowed_operators": {"role": "builder", "providers": ["anthropic"]},
        "write_scope": ["workspace/harness/lib/example.py"],
        "proof_obligations": [{"proof_kind": "patch_proof", "field": "patch_diff"}],
        "evaluator_gate": {"kind": "llm_eval", "on_fail": "repair_once_then_fail"},
        "status": "pending",
    }
    node.update(overrides)
    return node


def _graph(sid: str, *, node: dict | None = None, **top) -> dict:
    # Intake-born sprints carry the birth marker from the requirement
    # compiler (G4 blocker 2); these fixtures model that population.
    graph = {"sprint_id": sid, "plan_compile_required": True, "nodes": [node or _valid_node()]}
    graph.update(top)
    return graph


def _write_sprint(sprints: Path, sid: str, graph: dict) -> Path:
    _write_json(
        sprints / f"{sid}.status.json",
        {
            "id": sid,
            "sprint_id": sid,
            "status": "active",
            "phase": "planning_complete",
            "handoff_to": "builder_main",
            "target_role": "builder_main",
            "round": 0,
            "history": [],
        },
    )
    _write_json(sprints / f"{sid}.task_graph.json", graph)
    return sprints / f"{sid}.task_graph.json"


def _certified_sprint(tmp_path: Path, sid: str, monkeypatch) -> tuple[Path, dict]:
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True
    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    assert pv.check_plan_certificate(stamped) == []
    return graph_path, stamped


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SOLAR_PLAN_VALIDATOR", raising=False)
    monkeypatch.delenv("SOLAR_GATE_LEDGER", raising=False)


# --- Finding 1: capability enrichment must not mutate a certified graph ------

_CAPINF_COPIES = {
    "lib": _HARNESS / "lib" / "capability_inference.py",
    "tools": _HARNESS / "tools" / "capability_inference.py",
}


def _load_capinf(name: str, monkeypatch):
    module_name = f"g3fix_capinf_{name}"
    spec = importlib.util.spec_from_file_location(module_name, _CAPINF_COPIES[name])
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("copy_name", sorted(_CAPINF_COPIES))
def test_enrich_graph_leaves_certified_graph_governed_content_untouched(tmp_path, monkeypatch, copy_name):
    """The G3 defect: the planner omitted required_capabilities, enrichment
    injected an empty list into every node, and the governed hash no longer
    matched the PASS certificate."""
    capinf = _load_capinf(copy_name, monkeypatch)
    _, stamped = _certified_sprint(tmp_path, f"sprint-g3fix1-{copy_name}", monkeypatch)
    assert "required_capabilities" not in stamped["nodes"][0]

    enriched = capinf.enrich_graph(copy.deepcopy(stamped))

    assert "required_capabilities" not in enriched["nodes"][0], (
        "enrichment injected a governed field into a certified graph"
    )
    assert pv.check_plan_certificate(enriched) == [], (
        "enrichment invalidated the plan certificate"
    )


@pytest.mark.parametrize("copy_name", sorted(_CAPINF_COPIES))
def test_enrich_graph_still_enriches_uncertified_graphs(monkeypatch, copy_name):
    """Legacy behavior preserved: an uncertified graph still gets the field
    injected (empty or inferred) exactly as before."""
    capinf = _load_capinf(copy_name, monkeypatch)
    graph = _graph("sprint-g3fix1-legacy")
    assert "required_capabilities" not in graph["nodes"][0]

    enriched = capinf.enrich_graph(graph)

    assert "required_capabilities" in enriched["nodes"][0]


def test_auto_enrich_graph_skips_certified_graph(tmp_path, monkeypatch):
    """The live call site: assign_ready -> auto_enrich_graph (graph_scheduler)."""
    import graph_scheduler

    _, stamped = _certified_sprint(tmp_path, "sprint-g3fix1-auto", monkeypatch)

    enriched = graph_scheduler.auto_enrich_graph(copy.deepcopy(stamped))

    assert pv.check_plan_certificate(enriched) == []
    assert "required_capabilities" not in enriched["nodes"][0]


# --- Finding 2: mismatch refusal must terminalize truthfully -----------------


def _queue_dispatcher(monkeypatch, sprints: Path):
    import graph_node_dispatcher as gnd

    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "_prepare_human_search_handoff", lambda *a, **k: None)
    monkeypatch.setattr(gnd, "_ensure_lease", lambda *a, **k: {"acquired": True, "reason": "test"})
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda *a, **k: False)
    monkeypatch.setattr(gnd, "_actorhost_bridge", lambda *a, **k: {})
    monkeypatch.setattr(gnd, "dispatch_policy_block", lambda n, g: "## Architecture Guard\n\n- test")
    monkeypatch.setattr(gnd, "_write_scope_preflight_block", lambda sid, n: "")
    monkeypatch.setattr(gnd, "_canonical_output_paths_block", lambda n: "")
    return gnd


def _queue_item(sid: str, graph_path: Path, node: dict) -> dict:
    return {
        "sprint_id": sid,
        "intent": "graph_node|node_id=B1",
        "priority": 80,
        "payload": {
            "sprint_id": sid,
            "node": copy.deepcopy(node),
            "graph": str(graph_path),
            "assignment": {"pane": "test-pane"},
            "pane": "test-pane",
            "dispatch_id": "test-dispatch",
        },
    }


def _status(sprints: Path, sid: str) -> dict:
    return json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))


def _tamper(graph_path: Path, stamped: dict) -> dict:
    """The G3 shape: a governed field changes after PASS (here via direct
    edit; live it was the enrichment injection)."""
    tampered = copy.deepcopy(stamped)
    tampered["nodes"][0]["required_capabilities"] = []
    graph_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert [e["code"] for e in pv.check_plan_certificate(tampered)] == ["PLAN_CERTIFICATE_HASH_MISMATCH"]
    return tampered


def test_dispatch_queue_item_mismatch_terminalizes_sprint(tmp_path, monkeypatch):
    sid = "sprint-g3fix2-queue"
    sprints = tmp_path / "sprints"
    graph_path, stamped = _certified_sprint(tmp_path, sid, monkeypatch)
    tampered = _tamper(graph_path, stamped)
    gnd = _queue_dispatcher(monkeypatch, sprints)

    result = gnd.dispatch_queue_item(_queue_item(sid, graph_path, tampered["nodes"][0]), dry_run=True)

    assert result.get("ok") is False, result
    assert result.get("reason") == "plan_validator_dispatch_refused"
    status = _status(sprints, sid)
    assert status.get("status") == "failed", status
    assert status.get("phase") == "plan_certificate_invalid", status


def test_dispatch_queue_item_uncertified_refusal_does_not_terminalize(tmp_path, monkeypatch):
    """The E5 guard: an uncertified generic graph refusal is a normal
    pre-planner/bounce state and must never terminalize the sprint."""
    sid = "sprint-g3fix2-uncert"
    sprints = tmp_path / "sprints"
    graph = _graph(sid, workflow_contract_id="pm.generic.v1", workflow_contract_version="test")
    graph_path = _write_sprint(sprints, sid, graph)
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    gnd = _queue_dispatcher(monkeypatch, sprints)

    result = gnd.dispatch_queue_item(_queue_item(sid, graph_path, graph["nodes"][0]), dry_run=True)

    assert result.get("ok") is False, result
    status = _status(sprints, sid)
    assert status.get("status") == "active", status
    assert status.get("phase") == "planning_complete", status


_RUNNER_COPIES = {
    "root": _HARNESS / "multi_task_runner.py",
    "tools": _HARNESS / "tools" / "multi_task_runner.py",
    "lib": _HARNESS / "lib" / "multi_task_runner.py",
}


def _load_runner_module(name: str, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HARNESS_DIR", str(_HARNESS))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(tmp_path / "sprints"))
    module_name = f"g3fix_runner_{name}"
    spec = importlib.util.spec_from_file_location(module_name, _RUNNER_COPIES[name])
    assert spec is not None and spec.loader is not None
    mtr = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, mtr)
    spec.loader.exec_module(mtr)
    monkeypatch.setattr(mtr, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(mtr, "SPRINTS_DIR", tmp_path / "sprints")
    return mtr


@pytest.mark.parametrize("copy_name", sorted(_RUNNER_COPIES))
def test_launch_node_mismatch_terminalizes_sprint(tmp_path, monkeypatch, copy_name):
    sid = f"sprint-g3fix2-mtr-{copy_name}"
    sprints = tmp_path / "sprints"
    graph_path, stamped = _certified_sprint(tmp_path, sid, monkeypatch)
    tampered = _tamper(graph_path, stamped)
    mtr = _load_runner_module(copy_name, monkeypatch, tmp_path)

    result = mtr.launch_node(
        graph_path, tampered, tampered["nodes"][0],
        argparse.Namespace(profile="", model="", backend=""), dry_run=True,
    )

    assert result.get("status") == "plan_validator_dispatch_refused", result
    status = _status(sprints, sid)
    assert status.get("status") == "failed", status
    assert status.get("phase") == "plan_certificate_invalid", status


# --- Run-9 finding: ONE path vocabulary — the class fix, not the instance ----
#
# Run 5 failed on workspace/-vs-HARNESS_DIR; run 9 failed on
# tests/-vs-workspace/tests — the SAME class (F-CLASS-16): the planner may
# legally spell paths several ways, the builder anchors one way, and
# planner nondeterminism samples a new unaligned combination each run.
# The class dies by removing the freedom: generic pytest gate paths must
# resolve into the DECLARED ARTIFACT ROOTS only (canonical workspace/,
# whose aliases all normalize onto the gate cwd). The bare repo-tests root
# is no longer a legal generic gate target — under the workdir-cwd
# execution convention it never pointed at the repo anyway.


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest tests/test_wordfreq.py -q",  # run 9 verbatim
        "python3 -m pytest tests/scenarios -q",
        "python3 -m pytest tests/gate_ledger/test_x.py::test_y -q",
    ],
)
def test_bare_tests_root_is_not_a_generic_gate_target(command):
    node = _valid_node(evaluator_gate={
        "kind": "deterministic_command", "command": command, "on_fail": "fail",
    }, max_repair_attempts=0)
    graph = _graph("sprint-g3fix9", node=node)

    codes = [e["code"] for e in pv.validate_plan(graph, None, None)]

    assert "PLAN_GATE_PATH_DENIED" in codes, (command, codes)


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest workspace/tests/test_wordfreq.py -q",
        "python3 -m pytest workspace/tests -q",
        "python3 -m pytest sprints/<sid>/workdir/tests -q",
    ],
)
def test_artifact_root_gate_targets_stay_legal(command):
    sid = "sprint-g3fix9-ok"
    command = command.replace("<sid>", sid)
    node = _valid_node(evaluator_gate={
        "kind": "deterministic_command", "command": command, "on_fail": "fail",
    }, max_repair_attempts=0)
    graph = _graph(sid, node=node)

    codes = [e["code"] for e in pv.validate_plan(graph, None, None)]

    assert "PLAN_GATE_PATH_DENIED" not in codes, (command, codes)


def test_policy_block_teaches_the_canonical_test_location(monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    block = pv.planner_compile_policy_block()
    assert "workspace/tests" in block


# --- Run-7 finding: certified must imply dispatchable (capabilities) ---------
#
# G3 run 7 (p5-g3-live-rung-20260709T225219Z): the planner invented
# required_capabilities ("repo.worktree", "shell.pytest") — plausible
# strings that no operator advertises (the registry vocabulary is
# browser/UI tags) — and NOTHING validated them at compile time, so a
# CERTIFIED graph wedged forever at dispatch (worker_blocked /
# no_matching_worker, coordinator looping with empty batches, non-terminal).
# Compile-accepting what dispatch cannot serve breaks the certificate's
# meaning. Route resolvability now covers capabilities, and the policy
# block teaches the live vocabulary (the G2 lesson: never an untaught
# error code).


def test_unsatisfiable_required_capabilities_fail_compile():
    """A node demanding a capability no enabled operator advertises must
    bounce at birth, not wedge at dispatch."""
    node = _valid_node(required_capabilities=["repo.worktree", "shell.pytest"])
    graph = _graph("sprint-g3fix7", node=node)
    registry = {
        "test-builder": {
            "enabled": True, "deprecated": False, "health_status": "ok",
            "role": "builder", "roles": ["builder"], "provider": "anthropic",
            "capabilities": ["code_impl"],
        }
    }

    codes = [e["code"] for e in pv.validate_plan(graph, None, registry)]

    assert pv.ERROR_PLAN_CAPABILITY_UNSATISFIABLE in codes, codes


def test_satisfiable_and_absent_capabilities_still_compile():
    """Both live-proven planner shapes stay legal: capabilities omitted
    (run 5) and capabilities drawn from the registry vocabulary."""
    registry = {
        "test-builder": {
            "enabled": True, "deprecated": False, "health_status": "ok",
            "role": "builder", "roles": ["builder"], "provider": "anthropic",
            "capabilities": ["code_impl"],
        }
    }
    absent = _graph("sprint-g3fix7-absent")
    satisfiable = _graph(
        "sprint-g3fix7-ok", node=_valid_node(required_capabilities=["code_impl"])
    )

    for graph in (absent, satisfiable):
        codes = [e["code"] for e in pv.validate_plan(graph, None, registry)]
        assert pv.ERROR_PLAN_CAPABILITY_UNSATISFIABLE not in codes, codes


def test_policy_block_teaches_the_capability_vocabulary(tmp_path, monkeypatch):
    """The planner must be told the legal vocabulary (or to omit the field)
    — never an untaught error code."""
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    config, workflows = _fixture_config(tmp_path)

    block = pv.planner_compile_policy_block(config_dir=config, workflows_dir=workflows)

    assert pv.ERROR_PLAN_CAPABILITY_UNSATISFIABLE in block
    assert "required_capabilities" in block


# --- Run-5 findings: gate cwd must be the builder's anchor -------------------
#
# G3 run 5 (p5-g3-live-rung-20260709T210652Z): the graph stamped and
# dispatched live; S1 built real files and S2's builder wrote the test file —
# all under sprints/<sid>/workdir/workspace/... (the operator work_dir). The
# deterministic gate then ran `python3 -m pytest workspace/tests/...` from
# HARNESS_DIR and exited 4 (file not found): the contract treats workspace/
# and sprints/<sid>/workdir/ as ALIASES at validation time, but nothing
# unified them at execution time (F-CLASS-16 live on the generic path). The
# same run also showed pytest exit 4 recorded as a CONTENT fail, consuming
# the repair budget on a mechanical miss (F-CLASS-10).


def _run5_gate_fixture(tmp_path, *, with_test_file: bool) -> tuple:
    import contract_gate_executor

    harness = tmp_path / "harness"
    sprints = tmp_path / "sprints"
    (harness / "lib").mkdir(parents=True)
    sid = "sprint-g3fix5-cwd"
    _write_json(
        sprints / f"{sid}.task_graph.json",
        {
            "sprint_id": sid,
            "workflow_contract_id": "pm.generic.v1",
            "workflow_contract_version": "1.0",
            "nodes": [{"id": "S2", "status": "reviewing"}],
        },
    )
    workspace_tests = sprints / sid / "workdir" / "workspace" / "tests"
    workspace_tests.mkdir(parents=True)
    if with_test_file:
        (workspace_tests / "test_wordfreq.py").write_text(
            "def test_ok():\n    assert True\n", encoding="utf-8"
        )
    return contract_gate_executor, harness, sprints, sid


def test_generic_gate_resolves_paths_from_the_sprint_workdir(tmp_path, monkeypatch):
    """The run-5 shape verbatim: builder artifacts live under
    sprints/<sid>/workdir/workspace/, the gate command uses the canonical
    workspace/ alias — the gate must find the files the builder wrote."""
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    cge, harness, sprints, sid = _run5_gate_fixture(tmp_path, with_test_file=True)

    result = cge.execute_gate(
        sprints, sid, {"id": "S2"},
        {"kind": "deterministic_command",
         "command": "python3 -m pytest workspace/tests/test_wordfreq.py -q"},
        harness_dir=harness,
    )

    assert result.get("exit_code") == 0, result
    assert result.get("verdict") == "PASS", result


def test_generic_gate_missing_path_is_an_infrastructure_fail(tmp_path, monkeypatch):
    """When the gate input genuinely does not exist, pytest exit 4 is a
    mechanical miss, not a content judgment (F-CLASS-10) — it must not
    consume the repair budget as a content FAIL."""
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    cge, harness, sprints, sid = _run5_gate_fixture(tmp_path, with_test_file=False)

    result = cge.execute_gate(
        sprints, sid, {"id": "S2"},
        {"kind": "deterministic_command",
         "command": "python3 -m pytest workspace/tests/test_wordfreq.py -q"},
        harness_dir=harness,
    )

    assert result.get("verdict") == "FAIL", result
    assert result.get("verdict_kind") == "infrastructure", result


def test_fixed_contract_gate_keeps_harness_cwd(tmp_path, monkeypatch):
    """Fixed contracts address artifacts as sprints/<sid>/workdir/... from
    HARNESS_DIR (the P2/P3 proven convention) — their cwd must not move."""
    import contract_gate_executor

    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    (harness / "lib").mkdir(parents=True)
    sid = "sprint-g3fix5-fixed"
    _write_json(
        sprints / f"{sid}.task_graph.json",
        {
            "sprint_id": sid,
            "workflow_contract_id": "code.cli_smoke",
            "workflow_contract_version": "1.0",
            "nodes": [{"id": "S2", "status": "reviewing"}],
        },
    )
    tests_dir = sprints / sid / "workdir" / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = contract_gate_executor.execute_gate(
        sprints, sid, {"id": "S2"},
        {"kind": "deterministic_command",
         "command": f"python3 -m pytest sprints/{sid}/workdir/tests -q"},
        harness_dir=harness,
    )

    assert result.get("exit_code") == 0, result


# --- Run-4 findings: plain-sprint acceptance seam + PRD gate demotion --------
#
# G3 run 4 (p5-g3-live-rung-20260709T201817Z): the planner completed a valid
# 3-node graph, but (a) NO seam compiled/stamped it on the plain-sprint live
# path — the coordinator's only compile call sites are the drafting flow and
# a backfill gated on guard_role=builder, which is circular because the
# route only says builder AFTER the certificate exists; (b) the legacy PRD
# schema gate then demoted planning_complete back to drafting/spec/pm
# (gate_blocked invalid_prd, the F-040 class) and the sprint wedged for
# 600s. Coordinator doctrine already says "PM quality belongs before planner
# completion" — these pins hold the active-state flow to it.


def _coordinator_active_case() -> str:
    text = (_HARNESS / "coordinator.sh").read_text(encoding="utf-8")
    start = text.index('guard_violations="$(workflow_guard_violations "$sid")"')
    end = text.index("planning_complete)", start)
    return text[start:end]


def test_coordinator_active_flow_compiles_before_legacy_gates():
    """Fix A: with planner artifacts present and the route not yet builder,
    the active-state flow must attempt compile-generic (the acceptance seam)
    BEFORE any legacy PRD gating can demote the sprint."""
    region = _coordinator_active_case()
    assert "compile_generic_plan_graph" in region, (
        "active-state flow never compiles the planner graph (acceptance seam missing)"
    )
    assert region.index("compile_generic_plan_graph") < region.index("gate_prd_schema")


def test_coordinator_prd_gate_does_not_demote_after_planner_completion():
    """Fix B: the PRD schema demotion must be skipped once planner artifacts
    (design+plan+task_graph) exist."""
    region = _coordinator_active_case()
    demotion = region.index("gate_prd_schema")
    guard = region.rfind("planner_artifacts_present", 0, demotion)
    assert guard != -1, (
        "PRD schema demotion is not gated on planner artifacts being absent"
    )


def test_record_helper_only_fires_on_hash_mismatch(tmp_path, monkeypatch):
    """Unit seam: PLAN_CERTIFICATE_MISSING must not transition anything."""
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    sid = "sprint-g3fix2-unit"
    sprints = tmp_path / "sprints"
    _write_sprint(sprints, sid, _graph(sid))

    out = pv.record_certificate_mismatch_refusal(
        sprints, {"sprint_id": sid},
        [{"code": "PLAN_CERTIFICATE_MISSING", "message": "never validated"}],
    )
    assert out.get("attempted") is not True
    assert _status(sprints, sid)["status"] == "active"

    out = pv.record_certificate_mismatch_refusal(
        sprints, {"sprint_id": sid},
        [{"code": "PLAN_CERTIFICATE_HASH_MISMATCH", "message": "governed field changed"}],
    )
    assert out.get("attempted") is True, out
    final = _status(sprints, sid)
    assert final["status"] == "failed"
    assert final["phase"] == "plan_certificate_invalid"


# --- Run-10 finding: the governed spine ships in the generated env -----------


def test_sandbox_env_governed_spine_flags_stay_in_lockstep():
    """Run 10 (p5-g3-live-rung-20260710T003432Z) history: an unexported
    validator flag left children ungoverned while the shell looked governed.
    The original pin required BOTH flags exported at every env-generation
    site. G4 default-on SUPERSEDES that: the parser resolves ON with no env
    at all, so the scripts now export NEITHER flag (the e2e rung must prove
    the fresh-machine default; see test_p5_g4_env_probe.py). The residual
    lockstep invariant: the two flags never diverge — either both exported
    (pre-G4 world) or both absent (G4 world), never one without the other,
    which is exactly the half-governed run-10 shape."""
    for script in ("scripts/live-codex-e2e-isolated.sh", "scripts/live-claude-e2e-isolated.sh"):
        text = (_HARNESS.parent / script).read_text(encoding="utf-8")
        ledger = text.count("export SOLAR_GATE_LEDGER=")
        validator = text.count("export SOLAR_PLAN_VALIDATOR=")
        assert validator == ledger, (
            f"{script}: governed-spine flags diverged "
            f"(ledger exports: {ledger}, validator exports: {validator})"
        )
