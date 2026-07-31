"""P5 G1b: governed birth wiring for generic planner graphs.

These tests drive the real validator, registries, graph files, dispatcher
guard, runtime status writer, and workflow guard from tmp_path sandboxes. No
runtime process is spawned.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HARNESS / "lib"))

import graph_node_dispatcher as gnd  # noqa: E402
import plan_validator as pv  # noqa: E402
import workflow_guard as wg  # noqa: E402

WORKFLOWS_DIR = _HARNESS / "config" / "workflows"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture_config(tmp_path: Path, *, with_contract: bool = True) -> tuple[Path, Path]:
    config = tmp_path / "config"
    capsules = config / "capability-capsules"
    workflows = config / "workflows"
    capsules.mkdir(parents=True)
    workflows.mkdir(parents=True)
    shutil.copy2(
        _HARNESS / "config" / "capability-capsules" / "cap.requirement-compiler-implementation.yaml",
        capsules / "cap.requirement-compiler-implementation.yaml",
    )
    if with_contract:
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


def _errors_payload(sprints: Path, sid: str) -> dict:
    return json.loads((sprints / f"{sid}.plan-compile-errors.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # G4 default-on: unset now means ON — model the OFF baseline explicitly.
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "0")
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")


def test_env_off_compile_helper_leaves_graph_and_status_byte_identical(tmp_path):
    sid = "sprint-g1b-env-off"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    status_path = sprints / f"{sid}.status.json"
    before_graph = graph_path.read_bytes()
    before_status = status_path.read_bytes()

    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert verdict["ok"] is True
    assert verdict["stamped"] is False
    assert verdict["skipped_reason"] == "env_off"
    assert graph_path.read_bytes() == before_graph
    assert status_path.read_bytes() == before_status


def test_env_on_valid_generic_graph_is_stamped_idempotently_and_dispatch_guard_passes(tmp_path, monkeypatch):
    sid = "sprint-g1b-valid"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert verdict["ok"] is True
    assert verdict["stamped"] is True
    compiled = json.loads(graph_path.read_text(encoding="utf-8"))
    assert compiled["workflow_contract_id"] == "pm.generic.v1"
    assert compiled["workflow_contract_version"] == "1.0"
    assert compiled["plan_certificate"]["verdict"] == "PASS"
    first_bytes = graph_path.read_bytes()

    second = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert second["ok"] is True
    assert second["stamped"] is False
    assert second["skipped_reason"] == "already_certified"
    assert graph_path.read_bytes() == first_bytes

    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setattr(gnd, "WORKFLOWS_DIR", workflows, raising=False)
    assert gnd._workflow_contract_guard(compiled) is None


def test_invalid_generic_graph_bounces_once_per_changed_graph_then_terminal_with_ledger(tmp_path, monkeypatch):
    sid = "sprint-g1b-invalid"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    invalid = _graph(sid, node=_valid_node(evaluator_gate={"kind": "none", "on_fail": "fail"}))
    graph_path = _write_sprint(sprints, sid, invalid)
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")

    first = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert first["ok"] is False
    assert first["bounce_count"] == 1
    assert first["exhausted"] is False
    assert "plan_certificate" not in json.loads(graph_path.read_text(encoding="utf-8"))
    errors = _errors_payload(sprints, sid)
    assert errors["bounce_count"] == 1
    assert any(error["code"] == "PLAN_GATE_KIND_ILLEGAL" for error in errors["errors"])
    assert json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))["status"] == "drafting"

    unchanged = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert unchanged["ok"] is False
    assert unchanged["bounce_count"] == 1
    assert unchanged["exhausted"] is False
    assert _errors_payload(sprints, sid)["bounce_count"] == 1

    changed_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    changed_graph["nodes"][0]["evaluator_gate"] = {"kind": "vibes", "on_fail": "fail"}
    _write_json(graph_path, changed_graph)

    exhausted = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert exhausted["ok"] is False
    assert exhausted["bounce_count"] == 2
    assert exhausted["exhausted"] is True
    assert exhausted["terminal"] is True
    terminal_status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert terminal_status["status"] == "failed"
    assert terminal_status["phase"] == "plan_compile_failed"
    assert terminal_status["history"][-1]["reason"] == "PLAN_COMPILE_FAILED"
    assert "plan_certificate" not in json.loads(graph_path.read_text(encoding="utf-8"))

    ledger_rows = [
        json.loads(line)
        for line in (sprints / f"{sid}.gate-ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        row["kind"] == "status_transition"
        and row["node_id"] == "__sprint__"
        and row["from_status"] == "drafting"
        and row["to_status"] == "plan_compile_failed"
        and row["writer"] == "plan_validator"
        for row in ledger_rows
    )


def test_fixed_contract_graph_is_not_touched_when_env_on(tmp_path, monkeypatch):
    sid = "sprint-g1b-fixed"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    graph_path = _write_sprint(
        sprints,
        sid,
        _graph(sid, workflow_contract_id="code.cli_smoke", workflow_contract_version="1.0"),
    )
    before = graph_path.read_bytes()
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert verdict["ok"] is True
    assert verdict["skipped_reason"] == "non_generic_contract"
    assert graph_path.read_bytes() == before


def test_dispatch_guard_preserves_nameerror_detail(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path / "sprints")

    def explode(*_args, **_kwargs):
        raise NameError("name 'contract_id' is not defined")

    monkeypatch.setattr(pv, "check_planner_graph_dispatchable", explode)
    refusal = gnd._plan_validator_dispatch_guard({"sprint_id": "sprint-nameerror"})

    assert refusal is not None
    assert refusal["reason"] == "plan_validator_dispatch_refused"
    assert refusal["errors"] == [
        "PLAN_VALIDATOR_UNCHECKABLE:NameError:name 'contract_id' is not defined"
    ]


def test_missing_generic_contract_fails_closed_only_when_env_on(tmp_path, monkeypatch):
    sid = "sprint-g1b-missing-contract"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path, with_contract=False)
    graph_path = _write_sprint(sprints, sid, _graph(sid))
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    verdict = pv.compile_planner_graph(sprints, sid, config_dir=config, workflows_dir=workflows)

    assert verdict["ok"] is False
    assert verdict["stamped"] is False
    assert any(error["code"] == "PLAN_GENERIC_CONTRACT_MISSING" for error in verdict["errors"])
    assert "workflow_contract_id" not in json.loads(graph_path.read_text(encoding="utf-8"))
    assert any(error["code"] == "PLAN_GENERIC_CONTRACT_MISSING" for error in _errors_payload(sprints, sid)["errors"])


def test_workflow_guard_refuses_builder_ready_for_uncertified_generic_graph(tmp_path, monkeypatch):
    sid = "sprint-g1b-guard"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    _write_sprint(sprints, sid, _graph(sid))
    (sprints / f"{sid}.prd.md").write_text("# PRD\n", encoding="utf-8")
    (sprints / f"{sid}.design.md").write_text("# Design\n", encoding="utf-8")
    (sprints / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")
    monkeypatch.setattr(wg, "SPRINTS_DIR", sprints)
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    route = wg.route(sid)

    assert route["route_role"] not in {"builder", "builder_main"}
    assert any("plan_certificate" in violation for violation in route["violations"])


def test_compile_generic_cli_exit_codes_cover_certified_bounce_and_terminal(tmp_path, monkeypatch):
    sid = "sprint-g1b-cli"
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    _write_sprint(sprints, sid, _graph(sid, node=_valid_node(evaluator_gate={"kind": "none", "on_fail": "fail"})))
    env = dict(os.environ)
    env["SOLAR_PLAN_VALIDATOR"] = "1"
    env["PYTHONPATH"] = str(_HARNESS / "lib")

    first = subprocess.run(
        [
            sys.executable,
            str(_HARNESS / "lib" / "plan_validator.py"),
            "compile-generic",
            sid,
            "--sprints-dir",
            str(sprints),
            "--config-dir",
            str(config),
            "--workflows-dir",
            str(workflows),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    assert first.returncode == 3, (first.stdout, first.stderr)
    payload = json.loads(first.stdout)
    assert payload["bounce_count"] == 1

    graph_path = sprints / f"{sid}.task_graph.json"
    changed_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    changed_graph["nodes"][0]["evaluator_gate"] = {"kind": "vibes", "on_fail": "fail"}
    _write_json(graph_path, changed_graph)

    second = subprocess.run(
        [
            sys.executable,
            str(_HARNESS / "lib" / "plan_validator.py"),
            "compile-generic",
            sid,
            "--sprints-dir",
            str(sprints),
            "--config-dir",
            str(config),
            "--workflows-dir",
            str(workflows),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    assert second.returncode == 4, (second.stdout, second.stderr)
    terminal = json.loads(second.stdout)
    assert terminal["terminal"] is True
