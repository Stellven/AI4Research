"""P5 G2b fix-round review: regression tests for the five confirmed findings.

Independent review of 28d6f2b4..5cee48a4 (p2-runbook/REVIEW-FIXROUND-G2B.md)
found five coverage gaps, each reproduced with a runnable probe
(p2-runbook/g2b-review-probes/). These tests are those probes converted to
deterministic regressions (red first):

1. Two dispatch-capable entrypoints bypass the validator dispatch guard:
   multi_task_runner.schedule_once() (all three copies) launches ready nodes
   and graph_node_dispatcher.dispatch_queue_item() (the drain_queue worker)
   writes instruction files for uncertified generic graphs with
   SOLAR_PLAN_VALIDATOR=1.
2. The certificate hash omitted read_scope / required_skills /
   required_capabilities, all rendered into worker dispatch text, so a
   post-PASS edit changed worker behavior without invalidating the PASS.
3. The gate option denylist blocks import/config OPTIONS but pytest also
   imports conftest.py from any positional path argument, so a
   planner-controlled directory suffix ran import-time code in the gate
   process; a pathless pytest command collects the whole harness cwd.
4. _record_status_bounce() wrote the full stale status object back, so a
   status transition landing between its read and write was silently lost.
5. Two legacy planner dispatch surfaces (solar-harness.sh wake dispatch.md,
   coordinator.sh drafting-flow planner dispatch) never carried the
   compile-policy block, so a planner woken through them was untaught.

Same sandbox conventions as test_p5_g1b_review_fixes.py: real validator,
registries, graph files and dispatcher, all under tmp_path; no tmux/pane is
touched (queue-item and schedule_once run in-process with the pane/lease seams
stubbed, exactly like the review probes).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
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
                    # capability vocabulary the fixture nodes may draw from
                    # (G3 run-7 fix: declared capabilities must be
                    # registry-satisfiable at compile time)
                    "capabilities": ["baseline-capability", "code_impl"],
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


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # G4 default-on: unset now means ON — model the OFF baseline explicitly.
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "0")
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")


# --- Finding 1a: dispatch_queue_item (drain_queue) must honor the guard ------


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


def test_dispatch_queue_item_refuses_uncertified_generic_graph(tmp_path, monkeypatch):
    sid = "sprint-g2bfix1-queue"
    sprints = tmp_path / "sprints"
    graph = _graph(sid, workflow_contract_id="pm.generic.v1", workflow_contract_version="test")
    graph_path = _write_sprint(sprints, sid, graph)
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    gnd = _queue_dispatcher(monkeypatch, sprints)

    result = gnd.dispatch_queue_item(_queue_item(sid, graph_path, graph["nodes"][0]), dry_run=True)

    assert result.get("ok") is False, result
    assert result.get("reason") == "plan_validator_dispatch_refused"
    assert not result.get("instruction_file")
    assert not (sprints / f"{sid}.B1-dispatch.md").exists()


def test_dispatch_queue_item_admits_certified_generic_graph(tmp_path, monkeypatch):
    sid = "sprint-g2bfix1-queue-ok"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True
    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    gnd = _queue_dispatcher(monkeypatch, sprints)

    result = gnd.dispatch_queue_item(_queue_item(sid, graph_path, stamped["nodes"][0]), dry_run=True)

    assert result.get("ok") is True, result
    assert result.get("reason") != "plan_validator_dispatch_refused"
    assert result.get("instruction_file")


def test_dispatch_queue_item_untouched_when_validator_off(tmp_path, monkeypatch):
    sid = "sprint-g2bfix1-queue-off"
    sprints = tmp_path / "sprints"
    graph = _graph(sid, workflow_contract_id="pm.generic.v1", workflow_contract_version="test")
    graph_path = _write_sprint(sprints, sid, graph)
    gnd = _queue_dispatcher(monkeypatch, sprints)

    result = gnd.dispatch_queue_item(_queue_item(sid, graph_path, graph["nodes"][0]), dry_run=True)

    assert result.get("ok") is True, result
    assert result.get("instruction_file")


# --- Finding 1b: multi_task_runner.schedule_once must honor the guard --------

_RUNNER_COPIES = {
    "root": _HARNESS / "multi_task_runner.py",
    "tools": _HARNESS / "tools" / "multi_task_runner.py",
    "lib": _HARNESS / "lib" / "multi_task_runner.py",
}


def _load_runner(name: str, path: Path, monkeypatch, tmp_path: Path):
    import argparse

    monkeypatch.setenv("HARNESS_DIR", str(_HARNESS))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(tmp_path / "sprints"))
    module_name = f"g2b_review_runner_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    mtr = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, mtr)
    spec.loader.exec_module(mtr)

    profile = {
        "name": "test",
        "role": "builder",
        "persona": "builder",
        "backend": "test",
        "model": "noop",
        "command": "true",
        "approval_mode": "auto_edit",
    }
    monkeypatch.setattr(mtr, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(mtr, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(
        mtr, "load_profiles",
        lambda: {"defaults": {"profile": "test"}, "profiles": {"test": profile}},
    )
    monkeypatch.setattr(mtr, "select_profile", lambda node, p, m, b: profile)
    monkeypatch.setattr(
        mtr, "capability_for_profile",
        lambda selected: {
            "provider": "test",
            "status": "ok",
            "profile": selected.get("name"),
            "model": selected.get("model"),
            "backend": selected.get("backend"),
        },
    )
    monkeypatch.setattr(mtr, "launch_guard", lambda *a, **k: {"ok": True, "reason": "test"})
    monkeypatch.setattr(mtr, "active_tasks", lambda: [])
    monkeypatch.setattr(mtr, "capability_summary", lambda: {"test": "ok"})
    monkeypatch.setattr(mtr, "cached_status_summaries_for_graphs", lambda paths: [])
    monkeypatch.setattr(mtr, "list_harness_panes", lambda: [])
    monkeypatch.setattr(mtr, "recent_dispatch_rows", lambda: [])
    monkeypatch.setattr(mtr, "status_summary_for_graph", lambda path: {"graph": str(path)})
    monkeypatch.setattr(mtr, "scope_conflicts_with_active", lambda node: False)

    def schedule(graph_path: Path) -> dict:
        args = argparse.Namespace(
            graph=[str(graph_path)],
            max_workers=1,
            memory_reserve_gb=0,
            cooldown_sec=0,
            quota_backoff_sec=0,
            dry_run=True,
            profile="",
            model="",
            backend="",
        )
        return mtr.schedule_once(args)

    return schedule


@pytest.mark.parametrize("copy_name", sorted(_RUNNER_COPIES))
def test_schedule_once_refuses_uncertified_generic_graph(tmp_path, monkeypatch, copy_name):
    sid = f"sprint-g2bfix1-mtr-{copy_name}"
    sprints = tmp_path / "sprints"
    graph = _graph(sid, workflow_contract_id="pm.generic.v1", workflow_contract_version="test")
    graph_path = _write_sprint(sprints, sid, graph)
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    schedule = _load_runner(copy_name, _RUNNER_COPIES[copy_name], monkeypatch, tmp_path)

    result = schedule(graph_path)

    assert result.get("launched") == [], result.get("launched")
    reasons = {str(s.get("reason")) for s in result.get("skipped") or []}
    assert "plan_validator_dispatch_refused" in reasons, result.get("skipped")


@pytest.mark.parametrize("copy_name", sorted(_RUNNER_COPIES))
def test_schedule_once_launches_certified_generic_graph(tmp_path, monkeypatch, copy_name):
    sid = f"sprint-g2bfix1-mtr-ok-{copy_name}"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True
    schedule = _load_runner(copy_name, _RUNNER_COPIES[copy_name], monkeypatch, tmp_path)

    result = schedule(graph_path)

    assert len(result.get("launched") or []) == 1, result


@pytest.mark.parametrize("copy_name", sorted(_RUNNER_COPIES))
def test_schedule_once_untouched_when_validator_off(tmp_path, monkeypatch, copy_name):
    sid = f"sprint-g2bfix1-mtr-off-{copy_name}"
    sprints = tmp_path / "sprints"
    graph = _graph(sid, workflow_contract_id="pm.generic.v1", workflow_contract_version="test")
    graph_path = _write_sprint(sprints, sid, graph)
    schedule = _load_runner(copy_name, _RUNNER_COPIES[copy_name], monkeypatch, tmp_path)

    result = schedule(graph_path)

    assert len(result.get("launched") or []) == 1, result


# --- Finding 2: certificate must cover ALL worker-visible fields -------------


def _worker_fields_node() -> dict:
    return _valid_node(
        required_skills=["baseline-skill"],
        required_capabilities=["baseline-capability"],
        read_scope=["workspace/baseline.md"],
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("required_skills", ["changed-skill"]),
        ("required_capabilities", ["changed-capability"]),
        ("read_scope", ["workspace/changed.md"]),
    ],
)
def test_certificate_invalidated_by_worker_control_field_change(tmp_path, monkeypatch, field, value):
    sid = "sprint-g2bfix2-fields"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid, node=_worker_fields_node()))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True

    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    stamped["nodes"][0][field] = value

    errors = pv.check_plan_certificate(stamped)
    assert [e["code"] for e in errors] == ["PLAN_CERTIFICATE_HASH_MISMATCH"], field


def test_certificate_invalidated_by_worker_control_field_injection(tmp_path, monkeypatch):
    """Adding a field the planner never declared is also a post-PASS edit."""
    sid = "sprint-g2bfix2-inject"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True

    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    stamped["nodes"][0]["required_capabilities"] = ["injected-capability"]

    errors = pv.check_plan_certificate(stamped)
    assert [e["code"] for e in errors] == ["PLAN_CERTIFICATE_HASH_MISMATCH"]


# --- Finding 3: pytest gate paths must stay inside trusted test roots --------


def _gate_node(command: str) -> dict:
    return _valid_node(
        evaluator_gate={"kind": "deterministic_command", "command": command, "on_fail": "fail"},
        max_repair_attempts=0,
    )


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest /tmp/anywhere -q",
        "python3 -m pytest ../outside -q",
        "python3 -m pytest ~/anywhere -q",
        "python3 -m pytest random/dir -q",
        "python3 -m pytest tests/../workspace/evil -q",
        "python3 -m pytest -q",  # pathless: collects the whole harness cwd
        "python3 -m pytest random/dir/test_x.py::test_ok -q",
        "python3 -m pytest sprints/<sid>/workdir/tests -q",
        # a value-taking option must not swallow the path check by making the
        # command look positional-free
        "python3 -m pytest -k pattern",
    ],
)
def test_gate_rejects_pytest_paths_outside_trusted_roots(command):
    graph = _graph("sprint-g2bfix3", node=_gate_node(command))
    codes = [e["code"] for e in pv.validate_plan(graph, None, None)]
    assert "PLAN_GATE_PATH_DENIED" in codes, command


@pytest.mark.parametrize(
    "command",
    [
        # G3 run-9 class fix: gate paths live under the ARTIFACT ROOTS only
        # (the bare repo-tests root was a second legal spelling the planner
        # sampled nondeterministically — see test_p5_g3_live_fixes.py)
        "python3 -m pytest workspace/tests/scenarios -q",
        "python3 -m pytest workspace/tests/test_x.py::test_y -q",
        "python3 -m pytest --co -q workspace/tests",
        "python3 -m pytest -k pattern workspace/tests",
        "python3 -m pytest -m marker workspace/tests -q",
        # the generic-path design: the gate runs builder-written tests under
        # the contract's artifact roots (battery E1 / certificate fixtures)
        "python3 -m pytest workspace/tests -q",
        "python3 -m pytest sprints/<sid>/workdir/tests -q",
        "python3 scripts/validate_rsi_demo_report.py --strict",
        "python3 scripts/validate_rsi_demo_report.py workspace/report.md",
    ],
)
def test_gate_accepts_trusted_paths_and_selection_args(command):
    sid = "sprint-g2bfix3-ok"
    command = command.replace("<sid>", sid)
    graph = _graph(sid, node=_gate_node(command))
    codes = [e["code"] for e in pv.validate_plan(graph, None, None)]
    assert "PLAN_GATE_PATH_DENIED" not in codes, command
    assert "PLAN_GATE_OPTION_DENIED" not in codes, command
    assert "PLAN_GATE_COMMAND_NOT_ALLOWLISTED" not in codes, command


def test_policy_block_teaches_the_path_rule(monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    block = pv.planner_compile_policy_block()
    assert "PLAN_GATE_PATH_DENIED" in block


def test_execute_gate_does_not_import_conftest_from_gate_paths(tmp_path, monkeypatch):
    """The review probe, executor side: a conftest.py inside the (legal)
    artifact-root gate path must not run import-time code in the gate
    process — the executor pins --noconftest for validator-governed gates
    (fix-round 2 finding 6 scoped the hardening to SOLAR_PLAN_VALIDATOR;
    the flag-off legacy path is covered by test_p5_r2_review_fixes.py)."""
    import contract_gate_executor

    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    harness = tmp_path / "harness"
    sprints = tmp_path / "sprints"
    marker = tmp_path / "conftest_imported.txt"
    (harness / "lib").mkdir(parents=True)
    # hardening is scoped to certified-generic sprints (G4 default-on audit)
    _write_json(
        sprints / "sprint-g2bfix3-exec.task_graph.json",
        {
            "sprint_id": "sprint-g2bfix3-exec",
            "workflow_contract_id": "pm.generic.v1",
            "workflow_contract_version": "1.0",
            "nodes": [{"id": "N1", "status": "pending"}],
        },
    )
    evil = harness / "workspace" / "evil"
    evil.mkdir(parents=True)
    (evil / "conftest.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('loaded', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (evil / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = contract_gate_executor.execute_gate(
        sprints,
        "sprint-g2bfix3-exec",
        {"id": "N1"},
        {"kind": "deterministic_command", "command": "python3 -m pytest workspace/evil -q"},
        harness_dir=harness,
    )

    assert result.get("exit_code") == 0, result
    assert not marker.exists(), "conftest.py was imported by the gate process"


# --- Finding 4: bounce mirror must not clobber concurrent status writes ------


def _bounce_status(sprints: Path, sid: str) -> Path:
    status_path = sprints / f"{sid}.status.json"
    _write_json(
        status_path,
        {
            "sprint_id": sid,
            "status": "active",
            "phase": "prd_ready",
            "handoff_to": "planner",
            "target_role": "planner",
        },
    )
    return status_path


def test_record_status_bounce_does_not_full_object_write_stale_state(tmp_path, monkeypatch):
    """The review probe: a status transition that lands between the bounce
    mirror's read and its write must not be reverted by a stale full-object
    write through _atomic_write_json."""
    sid = "sprint-g2bfix4-clobber"
    sprints = tmp_path / "sprints"
    status_path = _bounce_status(sprints, sid)

    original_atomic = pv._atomic_write_json
    interleaved = {"count": 0}

    def interleaving_atomic(path, payload):
        if Path(path) == status_path and interleaved["count"] == 0:
            interleaved["count"] += 1
            original_atomic(
                status_path,
                {
                    "sprint_id": sid,
                    "status": "failed",
                    "phase": "plan_compile_failed",
                    "handoff_to": "",
                    "target_role": "none",
                    "concurrent_marker": "transition_won_then_clobbered",
                },
            )
        original_atomic(path, payload)

    monkeypatch.setattr(pv, "_atomic_write_json", interleaving_atomic)
    pv._record_status_bounce(sprints, sid, 1, "hash-a")

    final = json.loads(status_path.read_text(encoding="utf-8"))
    assert pv.STATUS_BOUNCE_KEY in final
    assert not (interleaved["count"] == 1 and "concurrent_marker" not in final)


def test_record_status_bounce_waits_for_the_status_write_lock(tmp_path):
    """A writer holding the status write lock (the transition side) must not
    have its update overwritten: the bounce mirror blocks, then merges onto
    the transitioned state."""
    import runtime_status

    sid = "sprint-g2bfix4-lock"
    sprints = tmp_path / "sprints"
    status_path = _bounce_status(sprints, sid)

    entered = threading.Event()

    def bounce():
        entered.set()
        pv._record_status_bounce(sprints, sid, 1, "hash-a")

    with runtime_status.status_write_lock(status_path):
        worker = threading.Thread(target=bounce)
        worker.start()
        assert entered.wait(5)
        time.sleep(0.3)  # give the bounce writer time to (wrongly) run unlocked
        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert pv.STATUS_BOUNCE_KEY not in data, "bounce mirror wrote while the lock was held"
        data["status"] = "failed"
        data["phase"] = "plan_compile_failed"
        data["concurrent_marker"] = "transition_first"
        status_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    worker.join(10)
    assert not worker.is_alive()

    final = json.loads(status_path.read_text(encoding="utf-8"))
    assert final["status"] == "failed"
    assert final["concurrent_marker"] == "transition_first"
    assert final[pv.STATUS_BOUNCE_KEY]["bounce_count"] == 1


def test_transition_status_participates_in_the_status_write_lock(tmp_path):
    """The canonical transition writer takes the same lock, so bounce-vs-
    transition interleavings serialize instead of last-write-wins."""
    import runtime_status

    sid = "sprint-g2bfix4-transition"
    sprints = tmp_path / "sprints"
    status_path = _bounce_status(sprints, sid)

    entered = threading.Event()
    done = threading.Event()

    def transition():
        entered.set()
        runtime_status.transition_status(
            status_path, "failed", "plan_compile_failed", "test",
            extra={"status_fields": {"phase": "plan_compile_failed"}},
        )
        done.set()

    with runtime_status.status_write_lock(status_path):
        worker = threading.Thread(target=transition)
        worker.start()
        assert entered.wait(5)
        time.sleep(0.3)
        assert not done.is_set(), "transition_status wrote while the lock was held"
    worker.join(10)
    assert done.is_set()
    final = json.loads(status_path.read_text(encoding="utf-8"))
    assert final["status"] == "failed"


# --- Finding 5: legacy planner surfaces must carry the compile policy --------


def test_plan_validator_cli_prints_planner_policy_block(tmp_path):
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    env = dict(os.environ, SOLAR_PLAN_VALIDATOR="1")
    proc = subprocess.run(
        [
            sys.executable,
            str(_HARNESS / "lib" / "plan_validator.py"),
            "planner-policy-block",
            "sprint-g2bfix5",
            "--sprints-dir",
            str(sprints),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "## Plan compile policy" in proc.stdout


def test_plan_validator_cli_policy_block_empty_when_flag_off(tmp_path):
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    env = dict(os.environ)
    # G4 default-on: unset now means ON — model the OFF state explicitly.
    env["SOLAR_PLAN_VALIDATOR"] = "0"
    proc = subprocess.run(
        [
            sys.executable,
            str(_HARNESS / "lib" / "plan_validator.py"),
            "planner-policy-block",
            "sprint-g2bfix5-off",
            "--sprints-dir",
            str(sprints),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""


def _region(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def test_wake_dispatch_file_carries_planner_policy_block():
    """solar-harness.sh wake writes ${sid}.dispatch.md and can fall back to a
    fixed-pane send; the planner-role dispatch file must append the policy
    block (review probe: g2b_probe_planner_prompt_surfaces.py)."""
    text = (_HARNESS / "solar-harness.sh").read_text(encoding="utf-8")
    region = _region(text, 'cat > "$SPRINTS_DIR/${sid}.dispatch.md"', "dispatch_via_operator_pool()")
    assert "planner-policy-block" in region


def test_coordinator_planner_dispatch_carries_policy_block():
    text = (_HARNESS / "coordinator.sh").read_text(encoding="utf-8")
    region = _region(text, "PRD ready → 自动派 planner", 'dispatch_to_planner "$sid" "planner_design_plan"')
    assert "planner-policy-block" in region
