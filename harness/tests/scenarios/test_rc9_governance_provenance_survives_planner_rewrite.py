"""RC9 live finding: planner graph replacement must not erase governance.

The installed Codex UI run at 891a3bf9 proved the requirement compiler born
graph initially carried ``plan_compile_required: true``.  The planner replaced
the whole JSON document, dropped that field, observed ``legacy_uncontracted``,
and a builder launched without a pm.generic.v1 certificate.  During the same
window the dashboard advertised a plan-review decision the autopilot never
waits on.

The birth classification is runtime provenance, not planner-authored graph
content.  These tests require the compiler to persist it outside the graph and
every launch/projection seam to honor it after a full graph replacement.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
# Insert tools first, then lib at index zero: modules with duplicate wrapper
# names (notably graph_node_dispatcher.py) must resolve to the real lib seam.
for _entry in (str(_HARNESS / "tools"), str(_HARNESS / "lib")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import plan_validator as pv  # noqa: E402
import pm_dispatch as pmd  # noqa: E402
import workflow_guard as wg  # noqa: E402


# ``pm_dispatch`` imports the legacy tools wrapper under the unqualified module
# name before this test reaches the dispatcher import.  Load the real launch
# seam under a unique name so the regression exercises product code rather than
# whichever duplicate name happened to win ``sys.modules`` ordering.
_GND_SPEC = importlib.util.spec_from_file_location(
    "rc9_governance_graph_node_dispatcher",
    str(_HARNESS / "lib" / "graph_node_dispatcher.py"),
)
assert _GND_SPEC is not None and _GND_SPEC.loader is not None
gnd = importlib.util.module_from_spec(_GND_SPEC)
_GND_SPEC.loader.exec_module(gnd)


SID = "sprint-rc9-planner-replaced-graph"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_unmarked_graph() -> dict:
    return {
        "sprint_id": SID,
        "nodes": [
            {
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
        ],
    }


def _status() -> dict:
    return {
        "id": SID,
        "sprint_id": SID,
        "status": "active",
        "phase": "planning_complete",
        "handoff_to": "builder_main",
        "target_role": "builder_main",
        "plan_compile_required": True,
        "history": [{"event": "compiled_requirement_package_created"}],
    }


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
        _HARNESS / "config" / "workflows" / "pm.generic.v1.workflow.json",
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


def _load_routes(harness_dir: Path):
    path = _HARNESS / "status-server" / "routes" / "orchestration_routes.py"
    spec = importlib.util.spec_from_file_location("rc9_governance_routes", str(path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.HARNESS_DIR = harness_dir
    mod.SPRINTS_DIR = harness_dir / "sprints"
    mod.SESSIONS_DIR = harness_dir / "sessions"
    mod.STATE_DIR = harness_dir / "state"
    return mod


@pytest.fixture(autouse=True)
def _validator_on(monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")


def test_compiled_status_persists_governance_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(pmd, "SPRINTS_DIR", tmp_path)
    monkeypatch.delenv("SOLAR_PM_OPERATOR_DISPATCH", raising=False)
    monkeypatch.delenv("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH", raising=False)

    path = pmd.ensure_compiled_sprint_status(SID, "title", "summary")

    assert json.loads(path.read_text(encoding="utf-8"))["plan_compile_required"] is True


def test_compile_restores_deleted_graph_marker_and_stamps(tmp_path):
    sprints = tmp_path / "sprints"
    config, workflows = _fixture_config(tmp_path)
    _write_json(sprints / f"{SID}.status.json", _status())
    graph_path = sprints / f"{SID}.task_graph.json"
    _write_json(graph_path, _valid_unmarked_graph())

    verdict = pv.compile_planner_graph(sprints, SID, config_dir=config, workflows_dir=workflows)

    compiled = json.loads(graph_path.read_text(encoding="utf-8"))
    assert verdict["ok"] is True and verdict["stamped"] is True, verdict
    assert compiled["plan_compile_required"] is True
    assert compiled["workflow_contract_id"] == "pm.generic.v1"
    assert compiled["plan_certificate"]["verdict"] == "PASS"


def test_dispatch_guard_refuses_unstamped_replacement_from_governed_sprint(tmp_path):
    sprints = tmp_path / "sprints"
    _write_json(sprints / f"{SID}.status.json", _status())
    graph = _valid_unmarked_graph()

    verdict = pv.check_planner_graph_dispatchable(graph, sprints_dir=sprints, sid=SID)

    assert verdict["ok"] is False, verdict
    assert any("CERTIFICATE" in str(item.get("code")) for item in verdict.get("errors") or [])


def test_workflow_guard_routes_replaced_graph_back_through_compile(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    _write_json(sprints / f"{SID}.status.json", _status())
    graph_path = sprints / f"{SID}.task_graph.json"
    _write_json(graph_path, _valid_unmarked_graph())
    monkeypatch.setattr(wg, "SPRINTS_DIR", sprints)

    ready, reason = wg._plan_certificate_ready(graph_path)

    assert ready is False
    assert reason.startswith("plan_certificate_required:"), reason


def test_graph_dispatcher_launch_guard_honors_status_provenance(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    _write_json(sprints / f"{SID}.status.json", _status())
    graph = _valid_unmarked_graph()
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)

    refusal = gnd._plan_validator_dispatch_guard(graph)

    assert refusal is not None, "runtime launch seam accepted an uncertified compiler-born graph"
    assert refusal["reason"] == "plan_validator_dispatch_refused"


def test_dashboard_uses_status_provenance_and_never_invents_plan_review(tmp_path):
    harness_dir = tmp_path
    sprints = harness_dir / "sprints"
    for name in ("sessions", "state", "config", "events"):
        (harness_dir / name).mkdir(parents=True, exist_ok=True)
    _write_json(sprints / f"{SID}.status.json", _status())
    _write_json(sprints / f"{SID}.task_graph.json", _valid_unmarked_graph())
    (sprints / f"{SID}.design.md").write_text("# design\n", encoding="utf-8")
    (sprints / f"{SID}.plan.md").write_text("# plan\n", encoding="utf-8")

    payload, _degraded = _load_routes(harness_dir).build_projection_payload(SID, mode="fast")

    assert payload["plan_governance"]["state"] == "compiling", payload["plan_governance"]
    assert payload["human_action_required"]["type"] != "plan_review", payload["human_action_required"]
