#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = REPO_ROOT / "status-server" / "routes" / "orchestration_routes.py"
UI_DIR = REPO_ROOT / "ui" / "orchestration"
SID = "sprint-20260530-p0-修复单-actorhost-taxonomy-与-actor-first-runtime-落地补齐-s04-orchestration-ui"
PASSED_UPSTREAM = [
    "N1_activation_graph_route",
    "N2_actorhost_status_bridge",
    "N3_status_api_surface",
    "N4_orchestration_ui_rendering",
]
NODE_UNDER_TEST = "N5_evidence_gate_handoff"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "harness"
    sprints = root / "sprints"
    state = root / "state"
    config = root / "config"

    _write_json(sprints / f"{SID}.status.json", {
        "sprint_id": SID,
        "epic_id": "epic-actorhost",
        "title": "S04 orchestration UI",
        "status": "active",
        "phase": "planning_complete",
    })
    _write_json(sprints / f"{SID}.task_graph.json", {
        "sprint_id": SID,
        "required_gates": ["G_S04_ORCHESTRATION_READY"],
        "nodes": [
            {
                "id": "N3_status_api_surface",
                "status": "passed",
                "depends_on": [],
                "goal": "status API",
                "required_capabilities": ["harness.status"],
                "estimated_cost": 1,
            },
            {
                "id": "N4_orchestration_ui_rendering",
                "status": "passed",
                "depends_on": ["N3_status_api_surface"],
                "goal": "orchestration UI",
                "required_capabilities": ["harness.status"],
                "estimated_cost": 1,
            },
            {
                "id": NODE_UNDER_TEST,
                "status": "pending",
                "depends_on": ["N3_status_api_surface", "N4_orchestration_ui_rendering"],
                "goal": "evidence gate",
                "required_capabilities": ["dag.validate", "harness.contracts", "harness.status", "test.tdd"],
                "estimated_cost": 1,
            },
        ],
    })
    _write_json(state / "pane-state.json", {
        "panes": [{"id": "pane-builder", "role": "builder", "state": "active", "model": "spark"}]
    })
    _write_json(state / "autopilot-state.json", {
        "routing_decisions": [
            {
                "sprint_id": SID,
                "node_id": "N4_orchestration_ui_rendering",
                "decision": "dispatched",
                "target_pane": "pane-builder",
                "provided_capabilities": ["harness.status"],
                "blocked_reason": "",
            }
        ]
    })
    _write_json(config / "actor-hosts.json", {
        "hosts": {"spark-host": {"host_id": "spark-host", "host_type": "claude_code_session"}}
    })
    _write_json(config / "agent-actors.json", {
        "actors": {
            "builder-spark": {
                "actor_id": "builder-spark",
                "host_id": "spark-host",
                "capability_profile": {"harness.status": 5, "test.tdd": 4},
            }
        }
    })
    _write_json(config / "physical-operators.json", {
        "operators": {"builder-spark": {"pane": "pane-builder"}}
    })
    for node_id in PASSED_UPSTREAM:
        _write_text(sprints / f"{SID}.{node_id}-handoff.md", f"# {node_id} handoff\n")
        _write_json(sprints / f"{SID}.{node_id}-eval.json", {
            "node_id": node_id,
            "status": "passed",
            "verdict": "pass",
        })
    _write_text(sprints / f"{SID}.handoff.md", """
# S04 Handoff

## Verification Commands
- graph_scheduler validate: passed
- pytest route/API/UI evidence: passed

## Unresolved Risks
- Browser-level check skipped and not counted as 100 percent passed.

## Upstream
- S03 must be re-verified before closing parent Epic.

## Downstream
- S05 must re-verify S03+S04 before release closeout.
""")
    return root


def _artifact_root(tmp_path: Path) -> Path:
    live = os.environ.get("SOLAR_S04_ACCEPTANCE_SPRINT_DIR")
    if live:
        root = Path(live).expanduser()
        if root.name == "sprints":
            return root.parent
        return root
    return _fixture_root(tmp_path)


def _sprints_dir(root: Path) -> Path:
    return root / "sprints"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_routes(root: Path):
    spec = importlib.util.spec_from_file_location("s04_acceptance_routes", ROUTE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["s04_acceptance_routes"] = mod
    spec.loader.exec_module(mod)
    mod.HARNESS_DIR = root
    mod.SPRINTS_DIR = root / "sprints"
    mod.STATE_DIR = root / "state"
    mod.EVENTS_JSONL = root / "events.jsonl"
    return mod


def test_graph_dependencies_and_gate_state_are_consistent(tmp_path: Path) -> None:
    root = _artifact_root(tmp_path)
    graph = _load_json(_sprints_dir(root) / f"{SID}.task_graph.json")
    nodes = {node["id"]: node for node in graph["nodes"]}

    for node_id in ["N3_status_api_surface", "N4_orchestration_ui_rendering"]:
        assert nodes[node_id]["status"] == "passed"

    n5 = nodes[NODE_UNDER_TEST]
    assert set(n5["depends_on"]) == {"N3_status_api_surface", "N4_orchestration_ui_rendering"}
    assert n5["status"] in {"pending", "passed"}
    assert "G_S04_ORCHESTRATION_READY" in graph.get("required_gates", [])


def test_passed_upstream_nodes_have_handoff_and_eval_sidecars(tmp_path: Path) -> None:
    root = _artifact_root(tmp_path)
    sprints = _sprints_dir(root)

    for node_id in PASSED_UPSTREAM:
        handoff = sprints / f"{SID}.{node_id}-handoff.md"
        eval_json = sprints / f"{SID}.{node_id}-eval.json"
        assert handoff.exists(), node_id
        assert eval_json.exists(), node_id
        verdict = _load_json(eval_json)
        assert verdict.get("status") == "passed" or verdict.get("verdict") in {"pass", "passed"}


def test_dashboard_payload_supplies_route_actorhost_and_degraded_evidence(tmp_path: Path) -> None:
    root = _artifact_root(tmp_path)
    mod = _load_routes(root)

    payload, degraded = mod.build_dashboard_payload(SID)

    assert isinstance(degraded, list)
    assert "dag" in payload
    assert "capabilities" in payload
    assert "pane_supply" in payload["capabilities"]
    node = next(item for item in payload["dag"]["nodes"] if item["id"] in {"N4_orchestration_ui_rendering", NODE_UNDER_TEST})
    for key in ["route_decision", "blocked_reason", "actor_id", "host_id", "host_type", "lease_state", "pane_carrier"]:
        assert key in node
    pane = payload["capabilities"]["pane_supply"][0]
    for key in ["actor_id", "host_id", "host_type", "lease_state", "pane_carrier"]:
        assert key in pane


def test_ui_surface_renders_acceptance_gate_fields() -> None:
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    js = (UI_DIR / "main.js").read_text(encoding="utf-8")
    css = (UI_DIR / "styles.css").read_text(encoding="utf-8")

    for token in ["route-list", "actorhost-list", "degraded-list", "pane-supply"]:
        assert token in html
    for token in ["route_decision", "blocked_reason", "actor_id", "host_id", "host_type", "lease_state"]:
        assert token in js
    assert "@media (max-width: 960px)" in css
    assert "display: none" not in css


def test_sprint_handoff_records_commands_risks_and_downstream_s05(tmp_path: Path) -> None:
    root = _artifact_root(tmp_path)
    handoff = (_sprints_dir(root) / f"{SID}.handoff.md").read_text(encoding="utf-8").lower()

    for token in ["verification commands", "unresolved risk", "s03", "s05"]:
        assert token in handoff
    assert "skipped" in handoff
    assert "100 percent passed" in handoff or "100%" in handoff
