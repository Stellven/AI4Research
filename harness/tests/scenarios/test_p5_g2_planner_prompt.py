"""P5 G2 follow-up: the planner dispatch prompt must teach the compile policy.

The G2 live battery (p5-g2-battery-20260708T205146Z) measured compile_rate
0.0 — 0 compiled / 5 rejected, CAPSULE_UNBOUND x20, PLAN_REPAIR_BUDGET_MISSING
x3. The planner objective told the planner to write task_graph.json but never
said what a compilable node must contain, so the live planner emitted bare
nodes (no capsule binding, no evaluator gate, no repair budget).

Fix under test: plan_validator.planner_compile_policy_block() — a single-
source, env-gated, registry-driven prompt block, with previous compile errors
included on re-dispatch so a bounced planner repairs instead of re-guessing.
Injection points (G2b hardening): the compiled-sprint objective builders
(lib/intent_consumer.py, tools/pm_dispatch.py), the pm_dispatch submit choke
point every role-pool planner dispatch flows through, and the autopilot
monitor's legacy pane-wake instruction builder.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HARNESS / "lib"))

import plan_validator as pv  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _anchor_env(monkeypatch):
    # G4 default-on: unset now means ON — model the OFF baseline explicitly.
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "0")
    # Anchor registry/contract lookups to the repo harness, not ~/.solar.
    monkeypatch.setenv("HARNESS_DIR", str(_HARNESS))


def test_policy_block_is_empty_when_env_off():
    assert pv.planner_compile_policy_block() == ""


def test_policy_block_teaches_the_compile_rules_when_env_on(monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    block = pv.planner_compile_policy_block()

    # The two live failure classes from the G2 battery, by name:
    assert "capability_capsule_id" in block
    assert "CAPSULE_UNBOUND" in block
    assert "max_repair_attempts" in block
    assert "PLAN_REPAIR_BUDGET_MISSING" in block
    # Registry-driven capsule list (not hardcoded): a shipped capsule id with
    # its admitted task types must be present.
    assert "cap.requirement-compiler-implementation" in block
    assert "implementation" in block
    # Gate policy: llm_eval default, allowlisted deterministic commands only.
    assert "llm_eval" in block
    assert "python3 -m pytest" in block
    # Artifact-root containment and the graph size bound.
    assert "workspace/" in block
    assert str(pv.DEFAULT_MAX_NODES) in block


def test_policy_block_appends_previous_compile_errors_on_bounce(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    sid = "sprint-g2-bounce"
    sprints = tmp_path / "sprints"
    pv.write_errors_artifact(
        sprints,
        sid,
        [
            {
                "code": "CAPSULE_UNBOUND",
                "node_id": "S1",
                "message": "node S1 has no capability_capsule_id",
            }
        ],
        bounce_count=1,
        graph_hash="abc123",
        exhausted=False,
        terminal=False,
    )

    block = pv.planner_compile_policy_block(sprints, sid)

    assert "CAPSULE_UNBOUND" in block
    assert "S1" in block
    assert "node S1 has no capability_capsule_id" in block
    assert "bounce" in block.lower()


def test_policy_block_without_bounce_artifact_has_no_error_section(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    block = pv.planner_compile_policy_block(tmp_path / "sprints", "sprint-g2-clean")
    assert "previous compile errors" not in block.lower()


def test_intent_consumer_objective_includes_policy_only_when_env_on(tmp_path, monkeypatch):
    import intent_consumer as ic

    monkeypatch.setattr(ic, "SPRINTS_DIR", tmp_path / "sprints")

    off = ic.planner_objective_for_compiled_sprint("sprint-g2-ic")
    assert "capability_capsule_id" not in off

    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    on = ic.planner_objective_for_compiled_sprint("sprint-g2-ic")
    assert "capability_capsule_id" in on
    assert "CAPSULE_UNBOUND" in on
    # The legacy objective text is preserved, the block is appended.
    assert on.startswith(off)


def test_pm_dispatch_objective_includes_policy_only_when_env_on(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "pm_dispatch_under_test", _HARNESS / "tools" / "pm_dispatch.py"
    )
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    monkeypatch.setattr(pm, "SPRINTS_DIR", tmp_path / "sprints")

    off = pm._planner_objective_for_compiled_sprint("sprint-g2-pm")
    assert "capability_capsule_id" not in off

    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    on = pm._planner_objective_for_compiled_sprint("sprint-g2-pm")
    assert "capability_capsule_id" in on
    assert "CAPSULE_UNBOUND" in on
    assert on.startswith(off)


# --- G2b finding: the block must reach EVERY planner dispatch, not just the
# --- two compiled-sprint objective builders. The live intake run dispatched
# --- the planner via the autopilot monitor's role-pool handoff, whose
# --- objective (objective_for_role_handoff) carried no policy block
# --- (p5-g2b-battery-20260709T023116Z: policy_block_present=false, scores
# --- identical to the untaught G2 baseline). Fix: inject at the pm_dispatch
# --- submit choke point every role-pool caller goes through, plus the legacy
# --- pane-wake instruction builder.


def _load_pm_dispatch():
    spec = importlib.util.spec_from_file_location(
        "pm_dispatch_under_test", _HARNESS / "tools" / "pm_dispatch.py"
    )
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    return pm


def _load_autopilot_monitor():
    spec = importlib.util.spec_from_file_location(
        "solar_autopilot_monitor_under_test",
        _HARNESS / "tools" / "solar-autopilot-monitor.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["solar_autopilot_monitor_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pm_dispatch_choke_point_appends_policy_for_planner_objectives(tmp_path, monkeypatch):
    pm = _load_pm_dispatch()
    monkeypatch.setattr(pm, "SPRINTS_DIR", tmp_path / "sprints")
    objective = "请接手 sprint-g2-choke：produce design/plan and refine the task graph."

    # env off: unchanged.
    assert pm._with_planner_compile_policy(objective, "sprint-g2-choke") == objective

    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    enriched = pm._with_planner_compile_policy(objective, "sprint-g2-choke")
    assert enriched.startswith(objective)
    assert "## Plan compile policy" in enriched
    assert "CAPSULE_UNBOUND" in enriched

    # idempotent: an objective that already carries the block (e.g. built by
    # intent_consumer) is not double-appended.
    again = pm._with_planner_compile_policy(enriched, "sprint-g2-choke")
    assert again == enriched
    assert again.count("## Plan compile policy") == 1


def test_pm_dispatch_cmd_submit_wires_the_choke_point_for_planner_role(tmp_path, monkeypatch):
    """Drive the REAL cmd_submit dry-run in a sandbox harness and observe the
    objective that reaches build_pm_dispatch_text (wrapper delegates to the
    real renderer; dry-run stops before any operator/tmux side effect)."""
    import argparse

    harness = tmp_path / "harness"
    (harness / "personas").mkdir(parents=True)
    (harness / "personas" / "planner.md").write_text("# planner persona\n", encoding="utf-8")
    _write_json(
        harness / "config" / "physical-operators.json",
        {
            "version": 1,
            "operators": {
                "test-planner": {
                    "enabled": True,
                    "available": True,
                    "deprecated": False,
                    "health_status": "ok",
                    "role": "planner",
                    "roles": ["planner"],
                    "provider": "openai",
                    "backend": "command",
                    "model": "test",
                }
            },
        },
    )
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(harness))
    monkeypatch.setenv("HARNESS_DIR", str(harness))
    monkeypatch.setenv("SOLAR_HARNESS_SPRINTS_DIR", str(harness / "sprints"))
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    pm = _load_pm_dispatch()

    seen: dict = {}
    real_render = pm.build_pm_dispatch_text

    def observing_render(**kwargs):
        seen.update(kwargs)
        return real_render(**kwargs)

    monkeypatch.setattr(pm, "build_pm_dispatch_text", observing_render)
    args = argparse.Namespace(
        role="planner",
        objective="请接手 sprint-g2-submit：produce design/plan.",
        operator="",
        sprint="sprint-g2-submit",
        node="N0",
        task_type="planning",
        dry_run=True,
        context="",
        work_dir="",
    )

    rc = pm.cmd_submit(args)

    assert rc == 0
    assert "## Plan compile policy" in seen.get("objective", ""), seen.get("objective", "")[:400]


def test_pm_dispatch_cmd_submit_leaves_builder_objectives_alone(tmp_path, monkeypatch):
    """Role scoping: the choke point enriches PLANNER submissions only."""
    import argparse

    harness = tmp_path / "harness"
    (harness / "personas").mkdir(parents=True)
    (harness / "personas" / "builder.md").write_text("# builder persona\n", encoding="utf-8")
    _write_json(
        harness / "config" / "physical-operators.json",
        {
            "version": 1,
            "operators": {
                "test-builder": {
                    "enabled": True,
                    "available": True,
                    "deprecated": False,
                    "health_status": "ok",
                    "role": "builder",
                    "roles": ["builder"],
                    "provider": "openai",
                    "backend": "command",
                    "model": "test",
                }
            },
        },
    )
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(harness))
    monkeypatch.setenv("HARNESS_DIR", str(harness))
    monkeypatch.setenv("SOLAR_HARNESS_SPRINTS_DIR", str(harness / "sprints"))
    monkeypatch.setenv("SOLAR_PM_DISPATCH_ALLOW_DIRECT", "1")
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    pm = _load_pm_dispatch()

    seen: dict = {}
    real_render = pm.build_pm_dispatch_text

    def observing_render(**kwargs):
        seen.update(kwargs)
        return real_render(**kwargs)

    monkeypatch.setattr(pm, "build_pm_dispatch_text", observing_render)
    args = argparse.Namespace(
        role="builder",
        objective="builder objective text",
        operator="",
        sprint="sprint-g2-builder",
        node="B1",
        task_type="implementation",
        dry_run=True,
        context="",
        work_dir="",
    )

    rc = pm.cmd_submit(args)

    assert rc == 0
    assert "## Plan compile policy" not in seen.get("objective", "")


def test_autopilot_pane_wake_planner_instruction_includes_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path / "harness"))
    monitor = _load_autopilot_monitor()
    status = {"sprint_id": "sprint-g2-wake", "handoff_to": "planner"}
    files = {
        "contract": True,
        "prd": True,
        "design": False,
        "plan": False,
        "task_graph": False,
        "handoff": False,
        "eval": False,
    }

    off = monitor.instruction_for(status, files)
    assert "## Plan compile policy" not in off
    assert off  # planner branch selected

    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    on = monitor.instruction_for(status, files)
    assert "## Plan compile policy" in on
    assert "CAPSULE_UNBOUND" in on
    assert on.startswith(off)


def test_autopilot_role_handoff_objective_gains_policy_via_submit_helper(tmp_path, monkeypatch):
    """objective_for_role_handoff itself stays lean — its dispatches flow
    through pm_dispatch submit, where the choke point enriches them. This test
    pins that composition: monitor objective -> submit helper -> block."""
    monkeypatch.setenv("HARNESS_DIR", str(tmp_path / "harness"))
    monitor = _load_autopilot_monitor()
    pm = _load_pm_dispatch()
    monkeypatch.setattr(pm, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")

    objective = monitor.objective_for_role_handoff("sprint-g2-pool", "planner")
    enriched = pm._with_planner_compile_policy(objective, "sprint-g2-pool")

    assert enriched.startswith(objective)
    assert "## Plan compile policy" in enriched
