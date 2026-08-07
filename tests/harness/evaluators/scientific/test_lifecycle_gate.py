from copy import deepcopy
from pathlib import Path

from evaluators.scientific import lifecycle_contract_gate, lifecycle_gate
from evaluators.scientific.common import load_json

HARNESS_DIR = (Path(__file__).resolve().parents[4] / 'harness')
FIXTURES = (Path(__file__).resolve().parents[4] / 'tests' / 'harness' / 'evaluators' / 'scientific') / "fixtures"


def _workflow(name: str) -> dict:
    return load_json(HARNESS_DIR / "workflows" / name)


def _compact_summary_from_workflow(workflow: dict, status: str = "passed") -> dict:
    root = "artifacts/scientific/phase15-smoke"
    nodes = []
    for node in workflow["nodes"]:
        artifact = node["write_scope"][0].replace(
            workflow["artifact_contract"]["root"],
            root,
            1,
        )
        nodes.append(
            {
                "id": node["id"],
                "logical_operator": node["logical_operator"],
                "gate": node["gate"],
                "status": "passed",
                "artifact": artifact,
                "expected_schema": node["evidence_policy"]["expected_schema"],
                "evidence_entry_id": f"evidence:{node['id']}",
            }
        )
    return {
        "schema": "scientific_lifecycle.v1",
        "workflow_id": workflow["workflow_id"],
        "artifact_root": root,
        "summary_artifact": f"{root}/lifecycle_summary.json",
        "evidence_log": f"{root}/evidence.jsonl",
        "lifecycle_status": status,
        "nodes": nodes,
    }


def test_full_lifecycle_workflow_contract_passes():
    result = lifecycle_contract_gate.evaluate(
        _workflow("scientific_research_lifecycle_full_v1.json")
    )

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_resume_workflow_contract_passes():
    result = lifecycle_contract_gate.evaluate(
        _workflow("scientific_research_resume_v1.json")
    )

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_lifecycle_gate_rejects_black_box_runner():
    payload = deepcopy(_workflow("scientific_research_lifecycle_full_v1.json"))
    payload["nodes"][0]["logical_operator"] = "AutoSciRunner"

    result = lifecycle_contract_gate.evaluate(payload)

    assert result.ok is False
    assert result.status == "failed"
    assert "AutoSciRunner" in " ".join(result.reasons)


def test_compact_lifecycle_summary_without_runtime_maps_is_rejected():
    payload = _compact_summary_from_workflow(
        _workflow("scientific_research_lifecycle_full_v1.json"),
        status="inconclusive",
    )

    result = lifecycle_gate.evaluate(payload)

    assert result.ok is False
    assert result.status == "failed"
    assert "node_results" in " ".join(result.reasons)


def test_lifecycle_summary_fixture_without_runtime_maps_is_rejected():
    result = lifecycle_gate.evaluate(load_json(FIXTURES / "pass/lifecycle.json"))

    assert result.ok is False
    assert result.status == "failed"
    assert "node_results" in " ".join(result.reasons)


def test_lifecycle_summary_fixture_fails_on_black_box():
    result = lifecycle_gate.evaluate(load_json(FIXTURES / "fail/lifecycle.json"))

    assert result.ok is False
    assert result.status == "failed"
    assert "AutoSciRunner" in " ".join(result.reasons)
