"""Cross-artifact checks for the Phase 0 contract and Phase 1 skeleton."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.intent import RUN_MODES, SEED_KINDS, WORKFLOW_KINDS


TASK_SCHEMA_PATH = ROOT / "schemas/draft/research_task_contract.v1.schema.json"
SELECTION_PATH = ROOT / "config/research-workflow-selection.v1.json"
ROUTE_PATH = ROOT / "plugins/autosci/config/research_orchestration_route.v2.draft.json"


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_intent_enums_match_frozen_task_contract() -> None:
    schema = _load(TASK_SCHEMA_PATH)
    assert set(schema["$defs"]["seed_kind"]["enum"]) == set(SEED_KINDS)
    assert set(schema["$defs"]["workflow_kind"]["enum"]) == set(WORKFLOW_KINDS)
    assert set(schema["$defs"]["run_mode"]["enum"]) == set(RUN_MODES)


def test_selection_and_capability_routes_cover_each_workflow_kind_once() -> None:
    selection = _load(SELECTION_PATH)
    selected_kinds = [route["workflow_kind"] for route in selection["routes"]]
    assert len(selected_kinds) == len(set(selected_kinds))
    assert set(selected_kinds) == set(WORKFLOW_KINDS)

    route_config = _load(ROUTE_PATH)
    routed_kinds = [
        kind
        for route in route_config["routes"]
        for kind in route["workflow_kinds"]
    ]
    assert len(routed_kinds) == len(set(routed_kinds))
    assert set(routed_kinds) == set(WORKFLOW_KINDS)


def test_selection_references_real_workflows_and_entry_nodes() -> None:
    selection = _load(SELECTION_PATH)
    for route in selection["routes"]:
        workflow_path = ROOT / route["workflow_path"]
        workflow = _load(workflow_path)
        assert workflow["workflow_id"] == route["workflow_id"]
        node_ids = {node.get("node_id") or node.get("id") for node in workflow["nodes"]}
        assert route["start_node"] in node_ids


def test_phase1_route_files_remain_nonactive() -> None:
    selection = _load(SELECTION_PATH)
    route_config = _load(ROUTE_PATH)
    assert selection["status"] == "draft"
    assert selection["active"] is False
    assert route_config["active"] is False
    assert all(route["active"] is False for route in route_config["routes"])


def test_workflow_evolution_uses_its_existing_capability() -> None:
    route_config = _load(ROUTE_PATH)
    by_kind = {
        kind: route["target_capability"]
        for route in route_config["routes"]
        for kind in route["workflow_kinds"]
    }
    assert by_kind["workflow_evolution"] == "cap.research-workflow-evolve"
    for kind in set(WORKFLOW_KINDS) - {"workflow_evolution"}:
        assert by_kind[kind] == "cap.research-lifecycle-run"
