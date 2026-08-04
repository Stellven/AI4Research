from __future__ import annotations

from pathlib import Path
import json
import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config/capability-capsules.registry.yaml"
SELECTION_PATH = ROOT / "config/research-workflow-selection.v1.json"
ROUTE_PATH = ROOT / "plugins/autosci/config/research_orchestration_route.v2.draft.json"
LIFECYCLE_PATH = ROOT / "capability-capsules/cap.research-lifecycle-run.yaml"
EVOLVE_PATH = ROOT / "capability-capsules/cap.research-workflow-evolve.yaml"
CAPSULE_SCHEMA_PATH = ROOT / "schemas/draft/capability-capsule.v1.draft.json"


WORKFLOW_KINDS = {
    "research_synthesis",
    "paper_ingestion",
    "literature_synthesis",
    "scientific_lifecycle",
    "workflow_evolution",
}

SELECTED_WORKFLOWS = {
    "research_synthesis": ("research_synthesis_v1", "seed_fetch"),
    "paper_ingestion": ("scientific_research_lifecycle_full_v1", "paper_ingest"),
    "literature_synthesis": ("research_synthesis_v1", "seed_fetch"),
    "scientific_lifecycle": ("scientific_research_lifecycle_full_v1", "literature_discover"),
    "workflow_evolution": ("scientific_research_lifecycle_full_v1", "workflow_evolve"),
}

RUN_MODE = ["execute", "resume", "import_evidence"]


def test_new_artifacts_are_valid_yaml_json():
    lifecycle = yaml.safe_load(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    capsule_schema = json.loads(CAPSULE_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(capsule_schema)
    jsonschema.Draft202012Validator(capsule_schema).validate(lifecycle)
    json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    json.loads(ROUTE_PATH.read_text(encoding="utf-8"))


def test_registry_ids_are_unique():
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    capabilities = [
        entry["capability_capsule_id"]
        for entry in payload["capsules"]["capability"]
    ]
    assert len(capabilities) == len(set(capabilities))


def test_lifecycle_run_and_workflow_evolve_are_distinct():
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = {
        str(entry["capability_capsule_id"]): entry
        for entry in payload["capsules"]["capability"]
    }

    assert "cap.research-lifecycle-run" in entries
    assert "cap.research-workflow-evolve" in entries

    lifecycle_entry = entries["cap.research-lifecycle-run"]
    evolve_entry = entries["cap.research-workflow-evolve"]

    assert lifecycle_entry["status"] in {"draft", "experimental"}
    assert lifecycle_entry["status"] != "stable"
    assert evolve_entry["status"] == "stable"

    assert lifecycle_entry["manifest_path"] != evolve_entry["manifest_path"]

    lifecycle_manifest = yaml.safe_load(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    evolve_manifest = yaml.safe_load(EVOLVE_PATH.read_text(encoding="utf-8"))
    assert (
        "postmortem" not in lifecycle_manifest["metadata"]["description"].lower()
    )
    evolve_required_inputs = {
        item["name"] for item in evolve_manifest["contract"]["inputs"]["required"]
    }
    assert "trigger_evidence" in evolve_required_inputs
    assert "cap.research-workflow-evolve" in lifecycle_manifest["composition"]["incompatible_with"]


def test_research_workflow_selection_has_exact_five_kinds():
    payload = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    assert payload["status"] == "draft"
    assert payload["active"] is False
    routes = payload["routes"]

    assert len(routes) == 5
    kinds = [item["workflow_kind"] for item in routes]
    assert len(kinds) == len(set(kinds)) == 5
    assert set(kinds) == WORKFLOW_KINDS

    for item in routes:
        assert item.get("workflow_id"), item
        assert item.get("start_node"), item
        assert item["workflow_kind"] in SELECTED_WORKFLOWS
        expected_workflow_id, expected_start_node = SELECTED_WORKFLOWS[item["workflow_kind"]]
        assert item["workflow_id"] == expected_workflow_id
        assert item["start_node"] == expected_start_node
        workflow_path = ROOT / item["workflow_path"]
        assert workflow_path.is_file(), workflow_path
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        assert workflow["workflow_id"] == item["workflow_id"]
        node_ids = {node.get("node_id") or node.get("id") for node in workflow["nodes"]}
        assert item["start_node"] in node_ids


def test_research_orchestration_route_is_nonactive_skeleton():
    payload = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    assert payload["active"] is False
    routes = payload["routes"]
    assert len(routes) == 2

    by_capability = {route["target_capability"]: route for route in routes}
    assert set(by_capability) == {
        "cap.research-lifecycle-run",
        "cap.research-workflow-evolve",
    }
    lifecycle = by_capability["cap.research-lifecycle-run"]
    evolution = by_capability["cap.research-workflow-evolve"]

    for route in routes:
        assert route["active"] is False
        assert route["native_skill"] == "research"
        assert route["coverage"] == "skeleton/partial"
        assert route["run_mode"] == RUN_MODE

    assert set(lifecycle["workflow_kinds"]) == WORKFLOW_KINDS - {"workflow_evolution"}
    assert lifecycle["target_logical_operator"] == "ScientificResearchLifecycleOrchestrator"
    assert lifecycle["planned_backend_action"] == "dispatch_research_lifecycle"
    assert evolution["workflow_kinds"] == ["workflow_evolution"]
    assert evolution["target_logical_operator"] == "ScientificWorkflowEvolver"
    assert evolution["planned_backend_action"] == "dispatch_workflow_evolution"


def test_no_full_stable_overstatement_and_no_real_data_research_schema():
    lifecycle_manifest = yaml.safe_load(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    selection_payload = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    route_payload = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    registry_payload = REGISTRY_PATH.read_text(encoding="utf-8")

    assert lifecycle_manifest["capsule_kind"] == "capability"
    assert route_payload.get("active") is False
    assert selection_payload["active"] is False
    for route in route_payload["routes"]:
        assert route["coverage"] not in {"full", "stable"}
        assert route["coverage"] == "skeleton/partial"

    for raw in (LIFECYCLE_PATH.read_text(encoding="utf-8"), EVOLVE_PATH.read_text(encoding="utf-8")):
        assert "real_data_research" not in raw

    for raw in (
        json.dumps(selection_payload, ensure_ascii=False),
        json.dumps(route_payload, ensure_ascii=False),
    ):
        assert "workflow_evolution.v1" not in raw

    assert "workflow_evolution.v1" not in registry_payload
    assert "real_data_research" not in registry_payload
