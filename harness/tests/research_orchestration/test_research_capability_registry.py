from __future__ import annotations

from pathlib import Path
import json
import yaml


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config/capability-capsules.registry.yaml"
SELECTION_PATH = ROOT / "config/research-workflow-selection.v1.json"
ROUTE_PATH = ROOT / "plugins/autosci/config/research_orchestration_route.v2.draft.json"
LIFECYCLE_PATH = ROOT / "capability-capsules/cap.research-lifecycle-run.yaml"
EVOLVE_PATH = ROOT / "capability-capsules/cap.research-workflow-evolve.yaml"


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
    "literature_synthesis": ("research_synthesis_v1", "source_discovery"),
    "scientific_lifecycle": ("scientific_research_lifecycle_full_v1", "literature_discover"),
    "workflow_evolution": ("scientific_research_lifecycle_full_v1", "workflow_evolve"),
}

RUN_MODE = ["execute", "resume", "import_evidence"]


def test_new_artifacts_are_valid_yaml_json():
    yaml.safe_load(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    json.loads(ROUTE_PATH.read_text(encoding="utf-8"))


def test_registry_ids_are_unique():
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    capabilities = [entry["capability_capsule_id"] for entry in payload["capability"]]
    assert len(capabilities) == len(set(capabilities))


def test_lifecycle_run_and_workflow_evolve_are_distinct():
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = {str(entry["capability_capsule_id"]): entry for entry in payload["capability"]}

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
    assert (
        "postmortem" in evolve_manifest["metadata"]["description"].lower()
    )


def test_research_workflow_selection_has_exact_five_kinds():
    payload = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
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


def test_research_orchestration_route_is_nonactive_skeleton():
    payload = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    assert payload["active"] is False
    routes = payload["routes"]
    assert len(routes) == 1

    route = routes[0]
    assert route["active"] is False
    assert route["native_skill"] == "research"
    assert route["target_capability"] == "cap.research-lifecycle-run"
    assert route["target_logical_operator"] == "ScientificResearchLifecycleOrchestrator"
    assert route["planned_backend_action"] == "dispatch_research_lifecycle"
    assert route["coverage"] == "skeleton/partial"
    assert route["run_mode"] == RUN_MODE


def test_no_full_stable_overstatement_and_no_real_data_research_schema():
    lifecycle_manifest = yaml.safe_load(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    selection_payload = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    route_payload = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    registry_payload = REGISTRY_PATH.read_text(encoding="utf-8")

    assert lifecycle_manifest["capsule_kind"] == "capability"
    assert route_payload.get("active") is False
    assert route_payload["routes"][0]["coverage"] != "full"
    assert route_payload["routes"][0]["coverage"] != "stable"
    assert route_payload["routes"][0]["coverage"] == "skeleton/partial"

    for raw in (LIFECYCLE_PATH.read_text(encoding="utf-8"), EVOLVE_PATH.read_text(encoding="utf-8")):
        assert "real_data_research" not in raw

    for raw in (
        json.dumps(selection_payload, ensure_ascii=False),
        json.dumps(route_payload, ensure_ascii=False),
    ):
        assert "workflow_evolution.v1" not in raw

    assert "workflow_evolution.v1" not in registry_payload
    assert "real_data_research" not in registry_payload
