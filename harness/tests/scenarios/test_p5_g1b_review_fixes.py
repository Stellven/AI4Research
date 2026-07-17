"""P5 G1b review fix-round: regression tests for the five confirmed findings.

Independent review of 55e11a7a..28d6f2b4 (p2-runbook/REVIEW-G1-G1B.md) found
five gaps in the governed-birth wiring, each reproduced with a runnable probe.
These tests are those probes converted to deterministic regressions (red
first):

1. dispatch_ready()/dispatch_node_evals() launch uncertified generic graphs —
   the only dispatch guard was gated on SOLAR_GATE_LEDGER, not
   SOLAR_PLAN_VALIDATOR, and skipped graphs with no workflow_contract_id.
2. The certificate hash excluded worker-visible execution text (goal /
   description / acceptance) and the top-level sprint_id, so post-PASS edits
   and cross-sprint certificate reuse went undetected.
3. The gate-command allowlist matched a token prefix and accepted any suffix,
   including pytest options that make the gate process import a caller-named
   module (-p / --import-mode / ...).
4. The planner bounce budget lived only in <sid>.plan-compile-errors.json;
   deleting that artifact reset the counter so a graph never terminalized.
5. workflow_guard.route() did not treat top-level status "failed" as
   terminal: failed + phase=plan_compile_failed with planner artifacts routed
   as builder_main/planning_complete, which chain-watcher/autopilot consume.

Same sandbox conventions as test_p5_g1b_birth_wiring.py: real validator,
registries, graph files, dispatcher and guard, all under tmp_path; no runtime
process is spawned (dispatcher runs are --dry-run subprocesses).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HARNESS / "lib"))

import plan_validator as pv  # noqa: E402
import workflow_guard as wg  # noqa: E402

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


def _sandbox_harness(tmp_path: Path) -> Path:
    """A minimal HARNESS_DIR whose config/workflows carries the generic contract,
    so subprocess dispatcher/validator lookups resolve inside the sandbox."""
    harness = tmp_path / "harness"
    workflows = harness / "config" / "workflows"
    workflows.mkdir(parents=True)
    shutil.copy2(
        WORKFLOWS_DIR / "pm.generic.v1.workflow.json",
        workflows / "pm.generic.v1.workflow.json",
    )
    return harness


def _status(sid: str, *, status: str = "drafting", phase: str = "prd_ready") -> dict:
    return {
        "id": sid,
        "sprint_id": sid,
        "status": status,
        "phase": phase,
        "handoff_to": "planner",
        "target_role": "planner",
        "round": 0,
        "history": [],
    }


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


def _write_sprint(sprints: Path, sid: str, graph: dict, status: dict | None = None) -> Path:
    _write_json(sprints / f"{sid}.status.json", status or _status(sid))
    _write_json(sprints / f"{sid}.task_graph.json", graph)
    return sprints / f"{sid}.task_graph.json"


def _dispatcher_env(harness: Path, sprints: Path, *, validator: bool) -> dict:
    env = dict(os.environ)
    # G4 default-on: these dispatch tests pin the VALIDATOR guard channel;
    # the ledger guard is explicitly killed so refusal reasons stay stable.
    env["SOLAR_GATE_LEDGER"] = "0"
    env.update(
        {
            "HARNESS_DIR": str(harness),
            "SPRINTS_DIR": str(sprints),
            "SOLAR_GRAPH_DISPATCH_FAKE_WORKERS": "1",
            "PYTHONPATH": str(_HARNESS / "lib"),
        }
    )
    env["SOLAR_PLAN_VALIDATOR"] = "1" if validator else "0"
    return env


def _run_dispatcher(subcommand: str, graph_path: Path, env: dict) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(_HARNESS / "lib" / "graph_node_dispatcher.py"),
            subcommand,
            "--graph",
            str(graph_path),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.stdout.strip(), (proc.returncode, proc.stderr)
    return json.loads(proc.stdout)


def _enqueued(payload: dict) -> list:
    return list((payload.get("enqueue") or {}).get("enqueued") or [])


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # G4 default-on: unset now means ON — model the OFF baseline explicitly.
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "0")
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")


# --- Finding 1: uncertified generic graphs must not reach the launch path ----


def test_dispatch_ready_refuses_uncertified_generic_graph_when_validator_on(tmp_path):
    sid = "sprint-fix1-uncertified"
    harness = _sandbox_harness(tmp_path)
    sprints = tmp_path / "sprints"
    graph_path = _write_sprint(sprints, sid, _graph(sid))

    payload = _run_dispatcher(
        "dispatch-ready", graph_path, _dispatcher_env(harness, sprints, validator=True)
    )

    assert payload.get("ok") is False
    assert payload.get("reason") == "plan_validator_dispatch_refused"
    assert _enqueued(payload) == []


def test_dispatch_ready_still_dispatches_uncertified_graph_when_validator_off(tmp_path):
    sid = "sprint-fix1-env-off"
    harness = _sandbox_harness(tmp_path)
    sprints = tmp_path / "sprints"
    graph_path = _write_sprint(sprints, sid, _graph(sid))

    payload = _run_dispatcher(
        "dispatch-ready", graph_path, _dispatcher_env(harness, sprints, validator=False)
    )

    assert payload.get("ok") is True
    assert len(_enqueued(payload)) == 1


def test_dispatch_ready_admits_certified_generic_graph_when_validator_on(tmp_path, monkeypatch):
    sid = "sprint-fix1-certified"
    harness = _sandbox_harness(tmp_path)
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True

    payload = _run_dispatcher(
        "dispatch-ready", graph_path, _dispatcher_env(harness, sprints, validator=True)
    )

    assert payload.get("ok") is True, payload
    assert payload.get("reason") != "plan_validator_dispatch_refused"
    assert len(_enqueued(payload)) == 1


def test_dispatch_evals_refuses_uncertified_generic_graph_when_validator_on(tmp_path):
    sid = "sprint-fix1-evals"
    harness = _sandbox_harness(tmp_path)
    sprints = tmp_path / "sprints"
    graph_path = _write_sprint(
        sprints, sid, _graph(sid, node=_valid_node(status="reviewing"))
    )

    payload = _run_dispatcher(
        "dispatch-evals", graph_path, _dispatcher_env(harness, sprints, validator=True)
    )

    assert payload.get("ok") is False
    assert payload.get("reason") == "plan_validator_dispatch_refused"
    assert payload.get("dispatched") in ([], None)


# --- Finding 2: the certificate must cover worker-visible execution text -----


@pytest.mark.parametrize(
    "field,value",
    [
        ("goal", "CHANGED GOAL: perform a different worker-visible task"),
        ("description", "injected post-PASS description"),
        ("acceptance", ["injected post-PASS acceptance"]),
    ],
)
def test_certificate_invalidated_by_worker_visible_field_change(tmp_path, monkeypatch, field, value):
    sid = "sprint-fix2-fields"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True

    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    stamped["nodes"][0][field] = value

    errors = pv.check_plan_certificate(stamped)
    assert [e["code"] for e in errors] == ["PLAN_CERTIFICATE_HASH_MISMATCH"], field
    dispatchable = pv.check_planner_graph_dispatchable(stamped)
    assert dispatchable.get("ok") is False
    assert dispatchable.get("reason") == "plan_validator_dispatch_refused"


def test_certificate_bound_to_sprint_id(tmp_path, monkeypatch):
    sid = "sprint-fix2-original"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True

    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    stamped["sprint_id"] = "sprint-fix2-hijacked"

    errors = pv.check_plan_certificate(stamped)
    assert [e["code"] for e in errors] == ["PLAN_CERTIFICATE_HASH_MISMATCH"]


def test_certificate_survives_runtime_field_mutation(tmp_path, monkeypatch):
    """Dispatch must not invalidate its own certificate: status/pane/dispatch
    bookkeeping stays outside the governed hash."""
    sid = "sprint-fix2-runtime"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True

    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    node = stamped["nodes"][0]
    node["status"] = "running"
    node["pane"] = "solar:0.7"
    node["dispatch_id"] = "graph-x-q1"
    node["repair_attempts"] = 1
    node["updated_at"] = "2026-07-08T00:00:00Z"
    stamped["node_results"] = {"B1": {"status": "running"}}

    assert pv.check_plan_certificate(stamped) == []


def test_dispatch_ready_refuses_certified_graph_after_goal_change(tmp_path, monkeypatch):
    """Findings 1+2 composed: the post-PASS goal edit must be refused at the
    launch path, not just detectable by a library call nobody makes."""
    sid = "sprint-fix2-dispatch"
    harness = _sandbox_harness(tmp_path)
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert verdict["stamped"] is True

    stamped = json.loads(graph_path.read_text(encoding="utf-8"))
    stamped["nodes"][0]["goal"] = "CHANGED GOAL: perform a different worker-visible task"
    _write_json(graph_path, stamped)

    payload = _run_dispatcher(
        "dispatch-ready", graph_path, _dispatcher_env(harness, sprints, validator=True)
    )

    assert payload.get("ok") is False
    assert payload.get("reason") == "plan_validator_dispatch_refused"
    assert _enqueued(payload) == []


# --- Finding 3: allowlisted gate commands must not admit import-control opts -


def _gate_node(command: str) -> dict:
    return _valid_node(
        evaluator_gate={"kind": "deterministic_command", "command": command, "on_fail": "fail"},
        max_repair_attempts=0,
    )


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest --co -p sample_plugin",
        "python3 -m pytest -psample_plugin",
        "python3 -m pytest tests/x -c custom.ini",
        "python3 -m pytest tests/x -o addopts=-psample_plugin",
        "python3 -m pytest tests/x --override-ini=addopts=-psample_plugin",
        "python3 -m pytest tests/x --confcutdir=/somewhere",
        "python3 -m pytest tests/x --rootdir /somewhere",
        "python3 -m pytest tests/x --import-mode=importlib",
        "python3 -m pytest --pyargs sample_plugin",
    ],
)
def test_gate_allowlist_rejects_import_control_options(command):
    graph = _graph("sprint-fix3", node=_gate_node(command))
    codes = [e["code"] for e in pv.validate_plan(graph, None, None)]
    assert "PLAN_GATE_OPTION_DENIED" in codes, command


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest tests/scenarios -q",
        "python3 -m pytest --co -q tests/gate_ledger",
        "python3 scripts/validate_rsi_demo_report.py --strict",
    ],
)
def test_gate_allowlist_still_accepts_plain_selection_args(command):
    graph = _graph("sprint-fix3-ok", node=_gate_node(command))
    codes = [e["code"] for e in pv.validate_plan(graph, None, None)]
    assert "PLAN_GATE_OPTION_DENIED" not in codes, command
    assert "PLAN_GATE_COMMAND_NOT_ALLOWLISTED" not in codes, command


# --- Finding 4: the bounce budget must survive errors-artifact deletion ------


def _invalid_graph(sid: str, gate_kind: str) -> dict:
    return _graph(sid, node=_valid_node(evaluator_gate={"kind": gate_kind, "on_fail": "fail"}))


def test_bounce_budget_survives_errors_artifact_delete(tmp_path, monkeypatch):
    sid = "sprint-fix4-reset"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    _write_sprint(sprints, sid, _invalid_graph(sid, "none"))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    first = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert first["bounce_count"] == 1
    assert first["terminal"] is False

    (sprints / f"{sid}.plan-compile-errors.json").unlink()
    _write_json(sprints / f"{sid}.task_graph.json", _invalid_graph(sid, "vibes"))

    second = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert second["bounce_count"] == 2
    assert second["exhausted"] is True
    assert second["terminal"] is True
    terminal_status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert terminal_status["status"] == "failed"
    assert terminal_status["phase"] == "plan_compile_failed"


def test_bounce_budget_unchanged_graph_stays_idempotent_after_artifact_delete(tmp_path, monkeypatch):
    """Deleting the artifact and recompiling the SAME bad graph must not burn
    extra budget either — the counter is monotonic, not double-charged."""
    sid = "sprint-fix4-idempotent"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    _write_sprint(sprints, sid, _invalid_graph(sid, "none"))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    first = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)
    assert first["bounce_count"] == 1

    (sprints / f"{sid}.plan-compile-errors.json").unlink()

    second = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert second["bounce_count"] == 1
    assert second["exhausted"] is False
    assert second["terminal"] is False


# --- Finding 5: top-level "failed" is terminal for routing -------------------


def _planner_artifacts(sprints: Path, sid: str) -> None:
    (sprints / f"{sid}.prd.md").write_text("# PRD\n", encoding="utf-8")
    (sprints / f"{sid}.design.md").write_text("# Design\n", encoding="utf-8")
    (sprints / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")


def test_workflow_guard_routes_failed_plan_compile_sprint_as_terminal(tmp_path, monkeypatch):
    sid = "sprint-fix5-terminal"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    _write_sprint(
        sprints,
        sid,
        _graph(sid),
        status={
            "id": sid,
            "sprint_id": sid,
            "status": "failed",
            "phase": "plan_compile_failed",
            "handoff_to": "",
            "target_role": "",
            "history": [{"event": "plan_compile_failed", "reason": "PLAN_COMPILE_FAILED"}],
        },
    )
    _planner_artifacts(sprints, sid)
    monkeypatch.setattr(wg, "SPRINTS_DIR", sprints)

    route = wg.route(sid)

    assert route["route_role"] == "none"
    assert route["route_role"] not in {"builder", "builder_main"}
    # autopilot normalizes role=none + stage=done to status "passed"; a failed
    # sprint must never present that pair.
    assert route["stage"] != "done"


def test_workflow_guard_pre_planner_uncertified_graph_routes_planner_cleanly(tmp_path, monkeypatch):
    """G2b live finding (E5, p5-g2b-battery-20260709T030014Z): a plain intake
    sprint at drafting/prd_ready carries the requirement-compiler's parent
    graph, which is generic and (correctly) uncertified — the planner hasn't
    run yet. route() emitted invalid_task_graph:plan_certificate_required,
    autopilot's ok-and-no-violations gate then refused to advance handoff
    pm->planner, and the sprint starved. Pre-planner (no design/plan), the
    missing certificate is the EXPECTED state, not a violation; the planner
    route is exactly the repair path. Builder-readiness keeps demanding the
    certificate (see test_workflow_guard_refuses_builder_ready_for_...)."""
    sid = "sprint-fix6-pre-planner."  # trailing dot: E5's sid shape
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    _write_json(
        sprints / f"{sid}.status.json",
        {
            "id": sid,
            "status": "drafting",
            "phase": "prd_ready",
            "handoff_to": "pm",
            "target_role": "pm",
            "history": [],
        },
    )
    (sprints / f"{sid}.prd.md").write_text("# PRD\n", encoding="utf-8")
    _write_json(sprints / f"{sid}.task_graph.json", _graph(sid))
    monkeypatch.setattr(wg, "SPRINTS_DIR", sprints)
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    route = wg.route(sid)

    assert route["route_role"] == "planner"
    assert route["ok"] is True
    assert not any("plan_certificate" in v for v in route["violations"])


def test_workflow_guard_failed_review_still_routes_builder_for_repair(tmp_path, monkeypatch):
    """Only top-level "failed" is terminal; failed_review keeps its repair route."""
    sid = "sprint-fix5-repair"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    _write_sprint(
        sprints,
        sid,
        # a LEGACY repair sprint (grandfathered): governed-but-uncertified
        # sprints route planner first by design under default-on
        _graph(sid, plan_compile_required=False),
        status={
            "id": sid,
            "sprint_id": sid,
            "status": "failed_review",
            "phase": "eval_failed",
            "handoff_to": "builder",
            "target_role": "builder",
            "history": [],
        },
    )
    _planner_artifacts(sprints, sid)
    monkeypatch.setattr(wg, "SPRINTS_DIR", sprints)

    route = wg.route(sid)

    assert route["route_role"] in {"builder", "builder_main"}
