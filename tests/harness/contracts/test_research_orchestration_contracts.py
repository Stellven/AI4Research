from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


ROOT = (Path(__file__).resolve().parents[3] / 'harness')
SCHEMAS = ROOT / "schemas"


SCHEMA_PATHS = {
    "task": SCHEMAS / "draft" / "research_task_contract.v1.schema.json",
    "request": SCHEMAS / "draft" / "research_node_request.v1.schema.json",
    "result": SCHEMAS / "evidence" / "research_node_result.v1.schema.json",
    "state": SCHEMAS / "evidence" / "research_run_state.v1.schema.json",
}


HASH = "a" * 64


def load_schema(name: str) -> dict:
    return json.loads(SCHEMA_PATHS[name].read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict]:
    loaded = {name: load_schema(name) for name in SCHEMA_PATHS}
    for schema in loaded.values():
        jsonschema.Draft202012Validator.check_schema(schema)
    return loaded


def assert_valid(schema: dict, instance: dict) -> None:
    jsonschema.Draft202012Validator(schema).validate(instance)


def assert_invalid(schema: dict, instance: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(instance)


def valid_task_contract() -> dict:
    return {
        "schema": "research_task_contract.v1",
        "task_id": "task-phase0",
        "run_id": "run-phase0",
        "user_intent": "Synthesize current evidence about a research question.",
        "seed_inputs": [
            {
                "seed_id": "seed-topic",
                "seed_kind": "topic",
                "value": "bounded research orchestration",
            }
        ],
        "deliverable": {
            "kind": "research_brief",
            "description": "Evidence-linked synthesis with visible limitations.",
            "artifact_expectations": ["markdown report", "evidence index"],
        },
        "workflow_kind": "research_synthesis",
        "run_mode": "execute",
        "constraints": {
            "no_live_provider_without_approval": True,
            "no_secret_logging": True,
            "time_budget_minutes": 30,
        },
        "provider_requirements": [
            {
                "requirement_id": "provider-offline-ok",
                "description": "No live provider is required for contract validation.",
                "required": False,
            }
        ],
        "platform_requirements": [
            {
                "requirement_id": "platform-local",
                "description": "Local schema validation only.",
                "required": True,
            }
        ],
        "success_criteria": [
            "Schema parses.",
            "Valid instance is accepted.",
            "Invalid contract boundaries are rejected.",
        ],
        "supplied_evidence": [],
    }


def valid_node_request() -> dict:
    return {
        "schema": "research_node_request.v1",
        "task_id": "task-phase0",
        "run_id": "run-phase0",
        "workflow_id": "workflow-phase0",
        "node_id": "node-discover",
        "logical_operator": {
            "operator_id": "ScientificLiteratureDiscoverer",
            "operator_kind": "logical",
            "capabilities": ["cap.research-literature-discover"],
        },
        "physical_operator": {
            "operator_id": "autosci.discover_literature",
            "operator_kind": "physical",
            "capabilities": ["bounded_worker"],
        },
        "typed_inputs": {
            "input_schema": "literature_discovery_request.v1",
            "payload": {"query": "bounded orchestration"},
        },
        "input_artifact_refs": [
            {"artifact_id": "task-contract", "path": "dispatch/task.json", "sha256": HASH}
        ],
        "authorization": {
            "scope_id": "scope-node-discover",
            "approved_capabilities": ["cap.research-literature-discover"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": ["dispatch/task.json"],
        "write_scope": ["artifacts/research/run-phase0/node-discover/result.json"],
        "timeout_retry_policy": {
            "timeout_seconds": 60,
            "max_attempts": 1,
            "retry_on": [],
        },
    }


def valid_node_result() -> dict:
    return {
        "schema": "research_node_result.v1",
        "task_id": "task-phase0",
        "run_id": "run-phase0",
        "workflow_id": "workflow-phase0",
        "node_id": "node-discover",
        "status": "completed",
        "status_is_terminal": True,
        "output_artifacts": [
            {
                "artifact_id": "discovery-result",
                "path": "artifacts/research/run-phase0/node-discover/result.json",
                "schema": "literature_discovery.v1",
                "sha256": HASH,
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev-discovery",
                "kind": "literature_discovery",
                "summary": "Offline fixture produced a bounded candidate list.",
                "artifact_id": "discovery-result",
            }
        ],
        "hashes": [{"hash_id": "discovery-result", "algorithm": "sha256", "value": HASH}],
        "model_provider_usage": [
            {"provider": "none", "model": "none", "usage_kind": "none"}
        ],
        "errors": [],
        "limitations": ["No live provider was used."],
        "secret_redaction_assertion": {
            "no_secrets_observed": True,
            "redaction_review": "passed",
        },
    }


def valid_run_state() -> dict:
    return {
        "schema": "research_run_state.v1",
        "task_id": "task-phase0",
        "run_id": "run-phase0",
        "workflow_id": "workflow-phase0",
        "graph_identity": {
            "graph_id": "graph-phase0",
            "graph_version": 1,
            "workflow_kind": "research_synthesis",
        },
        "run_provenance": {
            "repo_head": "a" * 40,
            "worktree_status": "clean",
            "captured_at": "2030-01-01T00:00:00Z",
            "workflow_identity": {
                "workflow_id": "workflow-phase0",
                "workflow_version": 1,
                "workflow_kind": "research_synthesis",
            },
        },
        "node_states": {
            "node-discover": {
                "node_id": "node-discover",
                "required_for_completion": True,
                "previous_status": "running",
                "status": "completed",
                "depends_on": [],
                "result_ref": "artifacts/research/run-phase0/node-discover/result.json",
                "updated_at": "2030-01-01T00:00:00Z",
            }
        },
        "ready_nodes": [],
        "current_blockers": [],
        "resume_import_provenance": {
            "run_mode": "execute",
            "imported_evidence_refs": [],
            "source_run_ids": [],
        },
        "final_status": "completed",
        "status_updated_at": "2030-01-01T00:00:01Z",
        "final_status_evidence_refs": ["ev-discovery"],
    }


@pytest.mark.parametrize("name", ["task", "request", "result", "state"])
def test_contract_schemas_parse(schemas: dict[str, dict], name: str) -> None:
    jsonschema.Draft202012Validator.check_schema(schemas[name])


def test_valid_contract_instances_pass(schemas: dict[str, dict]) -> None:
    assert_valid(schemas["task"], valid_task_contract())
    assert_valid(schemas["request"], valid_node_request())
    assert_valid(schemas["result"], valid_node_result())
    assert_valid(schemas["state"], valid_run_state())


def test_invalid_enum_is_rejected(schemas: dict[str, dict]) -> None:
    task = valid_task_contract()
    task["workflow_kind"] = "real_data_research"
    assert_invalid(schemas["task"], task)


def test_missing_run_id_is_rejected(schemas: dict[str, dict]) -> None:
    for name, factory in [
        ("task", valid_task_contract),
        ("request", valid_node_request),
        ("result", valid_node_result),
        ("state", valid_run_state),
    ]:
        instance = factory()
        instance.pop("run_id")
        assert_invalid(schemas[name], instance)


def test_execute_mode_rejects_forged_imported_evidence(schemas: dict[str, dict]) -> None:
    task = valid_task_contract()
    task["seed_inputs"][0]["seed_kind"] = "external_evidence"
    task["supplied_evidence"] = [
        {
            "artifact_id": "old-result",
            "path": "artifacts/old/result.json",
            "sha256": HASH,
            "provenance": {
                "source": "older-run",
                "captured_at": "2030-01-01T00:00:00Z",
            },
        }
    ]
    assert_invalid(schemas["task"], task)

    state = valid_run_state()
    state["resume_import_provenance"] = {
        "run_mode": "execute",
        "imported_evidence_refs": ["ev-old"],
        "source_run_ids": ["run-old"],
    }
    assert_invalid(schemas["state"], state)


def test_resume_mode_accepts_imported_evidence(schemas: dict[str, dict]) -> None:
    task = valid_task_contract()
    task["run_mode"] = "resume"
    task["supplied_evidence"] = [
        {
            "artifact_id": "old-result",
            "path": "artifacts/old/result.json",
            "sha256": HASH,
            "provenance": {
                "source": "older-run",
                "captured_at": "2030-01-01T00:00:00Z",
            },
        }
    ]
    assert_valid(schemas["task"], task)


def test_external_evidence_seed_requires_artifact_provenance(schemas: dict[str, dict]) -> None:
    task = valid_task_contract()
    task["run_mode"] = "import_evidence"
    task["seed_inputs"][0]["seed_kind"] = "external_evidence"
    task["supplied_evidence"] = []
    assert_invalid(schemas["task"], task)

    task["seed_inputs"][0]["artifact_ref"] = {
        "artifact_id": "external-evidence",
        "path": "imports/evidence.json",
        "sha256": HASH,
        "provenance": {
            "source": "reviewed-external-run",
            "captured_at": "2030-01-01T00:00:00Z",
        },
    }
    assert_valid(schemas["task"], task)


def test_resume_mode_rejects_empty_import_declaration(schemas: dict[str, dict]) -> None:
    task = valid_task_contract()
    task["run_mode"] = "resume"
    task["supplied_evidence"] = []
    assert_invalid(schemas["task"], task)


def test_task_safety_invariants_cannot_be_disabled(schemas: dict[str, dict]) -> None:
    for field in ("no_live_provider_without_approval", "no_secret_logging"):
        task = valid_task_contract()
        task["constraints"][field] = False
        assert_invalid(schemas["task"], task)


def test_operator_kinds_cannot_be_swapped(schemas: dict[str, dict]) -> None:
    request = valid_node_request()
    request["logical_operator"]["operator_kind"] = "physical"
    assert_invalid(schemas["request"], request)

    request = valid_node_request()
    request["physical_operator"]["operator_kind"] = "logical"
    assert_invalid(schemas["request"], request)


def test_live_provider_requires_network_and_explicit_approval(schemas: dict[str, dict]) -> None:
    request = valid_node_request()
    request["authorization"]["allow_live_provider"] = True
    request["authorization"]["allow_network"] = True
    assert_invalid(schemas["request"], request)

    request["authorization"]["approval_ref"] = "user-approval-phase0"
    assert_valid(schemas["request"], request)

    request["authorization"]["allow_network"] = False
    assert_invalid(schemas["request"], request)


def test_result_outcome_requires_matching_evidence_or_error(schemas: dict[str, dict]) -> None:
    completed = valid_node_result()
    completed["evidence"] = []
    assert_invalid(schemas["result"], completed)

    completed = valid_node_result()
    completed["errors"] = [
        {"error_id": "unexpected", "error_type": "test", "message": "not allowed"}
    ]
    assert_invalid(schemas["result"], completed)

    failed = valid_node_result()
    failed["status"] = "failed"
    failed["errors"] = []
    assert_invalid(schemas["result"], failed)


def test_illegal_node_transition_is_rejected(schemas: dict[str, dict]) -> None:
    state = copy.deepcopy(valid_run_state())
    state["node_states"]["node-discover"]["previous_status"] = "completed"
    state["node_states"]["node-discover"]["status"] = "running"
    assert_invalid(schemas["state"], state)


def test_completed_run_requires_completed_nodes_evidence_and_no_blockers(
    schemas: dict[str, dict],
) -> None:
    state = valid_run_state()
    state["node_states"]["node-discover"]["status"] = "running"
    assert_invalid(schemas["state"], state)

    state = valid_run_state()
    state["current_blockers"] = [
        {"blocker_id": "blocker-1", "node_id": "node-discover", "reason": "blocked"}
    ]
    assert_invalid(schemas["state"], state)

    state = valid_run_state()
    state["final_status_evidence_refs"] = []
    assert_invalid(schemas["state"], state)

    state = valid_run_state()
    state["node_states"]["node-discover"]["result_ref"] = None
    assert_invalid(schemas["state"], state)


def test_completed_run_allows_cancelled_optional_nodes(schemas: dict[str, dict]) -> None:
    state = valid_run_state()
    state["node_states"]["optional-review"] = {
        "node_id": "optional-review",
        "required_for_completion": False,
        "previous_status": "ready",
        "status": "cancelled",
        "depends_on": ["node-discover"],
        "result_ref": None,
        "updated_at": "2030-01-01T00:00:00Z",
    }
    assert_valid(schemas["state"], state)


def test_terminal_result_must_mark_terminal(schemas: dict[str, dict]) -> None:
    result = valid_node_result()
    result["status"] = "failed"
    result["status_is_terminal"] = False
    assert_invalid(schemas["result"], result)
