"""Static validation for the research synthesis draft workflow skeleton."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

SCHEMA_PATH = (
    (Path(__file__).resolve().parents[3] / 'harness')
    / "schemas/draft/research_workflow_skeleton.v1.schema.json"
)
WORKFLOW_PATH = (
    (Path(__file__).resolve().parents[3] / 'harness')
    / "workflows/drafts/research_synthesis_v1.json"
)

EXPECTED_WORKFLOW_ID = "research_synthesis_v1"
EXPECTED_DEPENDENCIES = {
    "seed_fetch": [],
    "source_discovery": ["seed_fetch"],
    "source_validation": ["source_discovery"],
    "evidence_synthesis": ["seed_fetch", "source_validation"],
    "report_draft": ["evidence_synthesis"],
    "independent_review": ["report_draft", "source_validation"],
    "report_revision": ["source_validation", "evidence_synthesis", "report_draft", "independent_review"],
    "final_acceptance": ["source_validation", "evidence_synthesis", "report_draft", "independent_review", "report_revision"],
}
NETWORK_ALLOWED_NODES = {"seed_fetch", "source_discovery"}
PROVIDER_ALLOWED_NODES = {"evidence_synthesis", "report_draft", "independent_review", "report_revision"}


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _collect_strings(obj: object, *, include_keys: bool = False) -> list[str]:
    strings: list[str] = []
    if isinstance(obj, str):
        strings.append(obj)
        return strings
    if isinstance(obj, list):
        for item in obj:
            strings.extend(_collect_strings(item, include_keys=include_keys))
        return strings
    if isinstance(obj, dict):
        for key, value in obj.items():
            if include_keys:
                strings.append(str(key))
            strings.extend(_collect_strings(value, include_keys=include_keys))
        return strings
    return strings


def _node_by_id(nodes: list[dict], node_id: str) -> dict:
    for node in nodes:
        if node.get("node_id") == node_id:
            return node
    raise AssertionError(f"missing required node: {node_id}")


def _topological_order(nodes: list[dict]) -> list[str]:
    deps = {node["node_id"]: list(node.get("depends_on", [])) for node in nodes}
    indegree: dict[str, int] = {node["node_id"]: 0 for node in nodes}
    for dep_list in deps.values():
        for dep in dep_list:
            indegree[dep] = indegree.get(dep, 0) + 0
    for node in nodes:
        indegree[node["node_id"]] = len(deps[node["node_id"]])

    queue = [node_id for node_id, count in indegree.items() if count == 0]
    ordered: list[str] = []
    while queue:
        node_id = queue.pop(0)
        ordered.append(node_id)
        for child, dep_list in deps.items():
            if node_id in dep_list:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
    if len(ordered) != len(nodes):
        raise AssertionError("cycle detected in research synthesis node graph")
    return ordered


def test_schema_parsable() -> None:
    schema = _load_json(SCHEMA_PATH)
    workflow = _load_json(WORKFLOW_PATH)
    assert schema["schema_version"] in {"v1.0.0-draft", "v1"}
    jsonschema.Draft202012Validator.check_schema(schema)
    assert workflow["schema_version"] == "v1.0.0-draft"
    assert workflow["workflow_id"] == EXPECTED_WORKFLOW_ID

    referenced_schema = (WORKFLOW_PATH.parent / workflow["$schema"]).resolve()
    assert referenced_schema == SCHEMA_PATH.resolve()
    assert referenced_schema.is_file()


def test_graph_passes_own_schema() -> None:
    schema = _load_json(SCHEMA_PATH)
    workflow = _load_json(WORKFLOW_PATH)

    jsonschema.Draft202012Validator(schema).validate(workflow)

    nodes = workflow["nodes"]
    assert isinstance(nodes, list) and nodes
    node_schema = schema["$defs"]["workflow_node"]
    required_node_fields = set(node_schema["required"])
    for node in nodes:
        assert isinstance(node, dict)
        assert required_node_fields.issubset(node.keys())
        assert node["node_id"] not in {"", None}
        assert node["node_id"] in EXPECTED_DEPENDENCIES

        assert node["permission_profile"]["network"]["enabled"] in {True, False}
        assert isinstance(node["permission_profile"]["provider_execution"], bool)
        assert node["binding_status"] in {"planned", "required"}
        assert node["retry_policy"]["mode"] in {"planned", "required", "once"}
        assert int(node["retry_policy"]["max_attempts"]) >= 1


def test_skeleton_nodes_unique_and_counted() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    nodes = workflow["nodes"]
    assert len(nodes) == 8
    node_ids = [node["node_id"] for node in nodes]
    assert len(node_ids) == len(set(node_ids))
    assert node_ids == list(EXPECTED_DEPENDENCIES.keys())


def test_graph_dag_no_cycle() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    nodes = workflow["nodes"]
    assert _topological_order(nodes)


def test_dependencies_exact_definition() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    nodes = workflow["nodes"]
    for node in nodes:
        expected = EXPECTED_DEPENDENCIES[node["node_id"]]
        actual = node.get("depends_on", [])
        assert actual == expected


def test_network_scope_only_in_allowed_nodes() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    nodes = workflow["nodes"]
    for node in nodes:
        node_id = node["node_id"]
        network_allowed = bool(node["permission_profile"]["network"]["enabled"])
        if node_id in NETWORK_ALLOWED_NODES:
            assert network_allowed is True
        else:
            assert network_allowed is False


def test_report_draft_without_network() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    node = _node_by_id(workflow["nodes"], "report_draft")
    assert node["permission_profile"]["network"]["enabled"] is False


def test_provider_execution_is_allowed_only_for_model_nodes() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    for node in workflow["nodes"]:
        allowed = node["node_id"] in PROVIDER_ALLOWED_NODES
        assert node["permission_profile"]["provider_execution"] is allowed


def test_final_acceptance_without_provider_execution() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    node = _node_by_id(workflow["nodes"], "final_acceptance")
    assert node["permission_profile"]["provider_execution"] is False


def test_no_fixture_paths() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    for item in _collect_strings(workflow, include_keys=True):
        lowered = item.lower()
        assert "fixtures/" not in lowered
        assert "/fixtures/" not in lowered


def test_no_task_specific_constants() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    fields = _collect_strings(workflow)
    for text in fields:
        lowered = text.lower()
        assert "腾讯" not in text
        assert "tencent" not in lowered
        assert not re.search(r"\b(19|20)\d{2}\b", text)
        assert not re.search(r"\btop\s*[4-6]\b", lowered)
        assert not re.search(r"\b[4-6]\s*-\s*[4-6]\b", lowered)


def test_graph_marked_as_draft_and_non_executable() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    assert workflow["status"] == "draft"
    assert workflow["execution_mode"] == "non-executable"


def test_output_and_input_contracts_present() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    nodes = workflow["nodes"]
    assert isinstance(workflow["contract"]["deliverables"], list) and workflow["contract"]["deliverables"]
    assert isinstance(workflow["contract"]["success_criteria"], list) and workflow["contract"]["success_criteria"]
    for node in nodes:
        gate = node["gate_contract"]
        assert gate["entry_condition"] and gate["exit_condition"]
        assert gate["deliverable"]
        assert gate["success_criteria"] and isinstance(gate["success_criteria"], list)


def test_artifact_inputs_have_upstream_or_task_context_producers() -> None:
    workflow = _load_json(WORKFLOW_PATH)
    nodes = {node["node_id"]: node for node in workflow["nodes"]}
    outputs_by_node = {
        node_id: set(node["output_artifacts"]) for node_id, node in nodes.items()
    }

    for node_id, node in nodes.items():
        upstream_outputs: set[str] = set()
        for dependency in node["depends_on"]:
            assert dependency in nodes
            upstream_outputs.update(outputs_by_node[dependency])
        for artifact in node["input_artifacts"]:
            assert artifact.startswith("task_context/") or artifact in upstream_outputs, (
                node_id,
                artifact,
            )
