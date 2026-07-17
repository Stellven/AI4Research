"""P4 live-run finding: false "Review the plan" decision card.

Fixture source: the P4 dashboard-initiated run (run-archive/
p4-sprint-20260708-185911-wf-code-cli-smoke-passed-20260708T191732Z).
The truthful-states reconciler recorded the "YOUR DECISION — Review the plan"
card in every UI snapshot (39 sightings) while the gate ledger contained ZERO
human/plan verdicts and the contracted graph self-advanced S1->S3 to terminal.

Cause: _human_action_required advertises plan_review from a heuristic
(plan artifacts exist + sprint active) with no look at the graph, so a
contracted run — parent status stays "active" until terminal — shows a
decision the runtime never waits on, for the whole run. Same shape as failure
class 14 (dashboard surface from heuristics instead of contract truth).

Contract: plan_review may only be advertised while the plan is actually
awaiting a decision — never on a contracted graph (its gates come from the
contract), and never once any node has left "pending" (the runtime has
already consumed the plan).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]

SID = "sprint-20260708-185911-wf-code-cli-smoke"


def _load_routes(harness_dir: Path):
    """Load orchestration_routes the way the live status-server does, pinned
    to a sandbox harness root."""
    routes_path = _HARNESS / "status-server" / "routes" / "orchestration_routes.py"
    spec = importlib.util.spec_from_file_location(
        "p4_false_plan_review_routes", str(routes_path)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    lib_path = str(_HARNESS / "lib")
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)
    spec.loader.exec_module(mod)
    mod.HARNESS_DIR = harness_dir
    mod.SPRINTS_DIR = harness_dir / "sprints"
    mod.SESSIONS_DIR = harness_dir / "sessions"
    mod.STATE_DIR = harness_dir / "state"
    return mod


def _write_sprint_fixture(
    harness_dir: Path,
    *,
    contracted: bool,
    node_statuses: dict[str, str],
) -> None:
    sprints = harness_dir / "sprints"
    for sub in ("sprints", "sessions", "state", "config", "events"):
        (harness_dir / sub).mkdir(parents=True, exist_ok=True)
    (sprints / f"{SID}.status.json").write_text(
        json.dumps(
            {
                "sprint_id": SID,
                "epic_id": "epic-p4",
                "title": "[code.cli_smoke] uniqwords",
                "status": "active",
                "phase": "planning_complete",
            }
        ),
        encoding="utf-8",
    )
    graph = {
        "sprint_id": SID,
        "nodes": [
            {
                "id": node_id,
                "goal": f"{node_id} goal",
                "status": status,
                "depends_on": [] if node_id == "S1" else [f"S{int(node_id[1]) - 1}"],
            }
            for node_id, status in node_statuses.items()
        ],
    }
    if contracted:
        graph["workflow_contract_id"] = "code.cli_smoke"
        graph["workflow_contract_version"] = "1"
    (sprints / f"{SID}.task_graph.json").write_text(
        json.dumps(graph), encoding="utf-8"
    )
    # plan_ready requires design + plan + task_graph artifacts on disk.
    (sprints / f"{SID}.design.md").write_text("# design\n", encoding="utf-8")
    (sprints / f"{SID}.plan.md").write_text("# plan\n", encoding="utf-8")


def _human_action(mod, sid: str) -> dict:
    payload, _degraded = mod.build_projection_payload(sid)
    action = payload.get("human_action_required") or {}
    assert isinstance(action, dict)
    return action


def test_contracted_inflight_run_never_advertises_plan_review(tmp_path):
    """The P4 live shape: contracted graph, build already dispatched."""
    _write_sprint_fixture(
        tmp_path,
        contracted=True,
        node_statuses={"S1": "dispatched", "S2": "pending", "S3": "pending"},
    )
    mod = _load_routes(tmp_path)
    action = _human_action(mod, SID)
    assert action.get("type") != "plan_review", action


def test_contracted_pre_dispatch_run_never_advertises_plan_review(tmp_path):
    """Even before any dispatch, a contracted graph's gates come from the
    contract — there is no human plan gate for the dashboard to invent."""
    _write_sprint_fixture(
        tmp_path,
        contracted=True,
        node_statuses={"S1": "pending", "S2": "pending", "S3": "pending"},
    )
    mod = _load_routes(tmp_path)
    action = _human_action(mod, SID)
    assert action.get("type") != "plan_review", action


def test_generic_run_with_build_started_does_not_advertise_plan_review(tmp_path):
    """Generic path: once any node left pending, the runtime has consumed the
    plan; asking for approval afterwards is a false decision surface."""
    _write_sprint_fixture(
        tmp_path,
        contracted=False,
        node_statuses={"S1": "dispatched", "S2": "pending", "S3": "pending"},
    )
    mod = _load_routes(tmp_path)
    action = _human_action(mod, SID)
    assert action.get("type") != "plan_review", action


def test_generic_unstarted_plan_still_asks_for_review(tmp_path):
    """Behavior guard: the legitimate case — generic run, plan artifacts
    ready, nothing dispatched — keeps its human plan gate."""
    _write_sprint_fixture(
        tmp_path,
        contracted=False,
        node_statuses={"S1": "pending", "S2": "pending", "S3": "pending"},
    )
    mod = _load_routes(tmp_path)
    action = _human_action(mod, SID)
    assert action.get("type") == "plan_review", action
