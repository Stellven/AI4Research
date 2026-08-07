from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError


CHECKOUT = Path(__file__).resolve().parents[3] / "tmp" / "codex-not-run-checkout"
SCHEMA_DIR = CHECKOUT / "harness" / "schemas" / "evidence"
PASS_FIXTURES = CHECKOUT / "harness" / "tests" / "evaluators" / "scientific" / "fixtures" / "pass"
SAMPLE_FIXTURES = SCHEMA_DIR / "fixtures"

SCHEMAS = [
    "research_paper",
    "research_claims",
    "research_method",
    "code_evidence_map",
    "idea_candidate",
    "idea_evaluation",
    "experiment_plan",
    "experiment_result",
    "experiment_status",
    "claim_verdict",
    "artifact_review",
    "scientific_report",
    "workflow_evolution",
]


def load_contract(name: str) -> tuple[dict, dict, Draft202012Validator]:
    schema = json.loads((SCHEMA_DIR / f"{name}.v1.schema.json").read_text(encoding="utf-8"))
    fixture_path = PASS_FIXTURES / f"{name}.json"
    sample_path = SAMPLE_FIXTURES / f"sample_{name}.v1.json"
    if fixture_path.is_file():
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    elif sample_path.is_file():
        fixture = json.loads(sample_path.read_text(encoding="utf-8"))
    elif name == "artifact_review":
        fixture = {
            "schema": "artifact_review.v1",
            "task_id": "task-review",
            "sprint_id": "sprint-review",
            "node_id": "node-review",
            "status": "completed",
            "inputs": {"target": "fixtures/review-target.md"},
            "outputs": {
                "review": {
                    "artifact_id": "artifact:review-target",
                    "target": "fixtures/review-target.md",
                    "review_mode": "local_surrogate",
                    "review_available": False,
                    "difficulty": "hard",
                    "focus": "method",
                    "score": 0.7,
                    "recommendation": "pass_with_review_required",
                    "evidence_ids": ["artifact:review-target"],
                },
                "findings": [],
                "artifact": {"artifact_id": "artifact:review-target", "path": "fixtures/review-target.md"},
            },
            "artifacts": [{"type": "review_target", "path": "fixtures/review-target.md"}],
            "provenance": {
                "operator_id": "audit",
                "implementation_package": "audit.fixture",
                "timestamp": "2026-07-10T00:00:00Z",
            },
            "limitations": ["Review LLM evidence is not connected for this local surrogate."],
        }
    else:
        raise FileNotFoundError(f"No valid fixture found for {name}")
    return schema, fixture, Draft202012Validator(schema)


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_minimal_required_payload_is_valid(name: str) -> None:
    schema, fixture, validator = load_contract(name)
    required = set(schema["required"])
    minimal = {key: copy.deepcopy(value) for key, value in fixture.items() if key in required}
    assert set(minimal) == required
    validator.validate(minimal)


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_rich_payload_roundtrip_preserves_nested_fields(name: str) -> None:
    _, fixture, validator = load_contract(name)
    encoded = json.dumps(fixture, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded == fixture
    assert isinstance(decoded["outputs"], dict)
    assert isinstance(decoded["artifacts"], list)
    assert isinstance(decoded["provenance"], dict)
    assert isinstance(decoded["limitations"], list)
    validator.validate(decoded)


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_allowed_statuses_and_limitations_contract(name: str) -> None:
    schema, fixture, validator = load_contract(name)
    allowed = schema["$defs"]["status"]["enum"]
    assert allowed == ["completed", "failed", "inconclusive"]
    for status in allowed:
        candidate = copy.deepcopy(fixture)
        candidate["status"] = status
        if status != "completed":
            candidate["limitations"] = [f"audit fixture for {status}"]
        validator.validate(candidate)
    rejected = copy.deepcopy(fixture)
    rejected["status"] = "success_without_evidence"
    with pytest.raises(ValidationError):
        validator.validate(rejected)


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_rejects_missing_required_and_wrong_types(name: str) -> None:
    schema, fixture, validator = load_contract(name)
    for required_key in schema["required"]:
        missing = copy.deepcopy(fixture)
        missing.pop(required_key)
        with pytest.raises(ValidationError):
            validator.validate(missing)
    wrong_type = copy.deepcopy(fixture)
    wrong_type["artifacts"] = "not-a-list"
    with pytest.raises(ValidationError):
        validator.validate(wrong_type)
