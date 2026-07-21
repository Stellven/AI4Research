"""Schema validation tests for Code-as-Harness Runtime vNext.

Validates Code-as-Harness Runtime JSON schemas pass Draft7Validator.check_schema()
and that required/optional fields match S02 interface-contracts spec.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class TestSchemaValidity:
    """All schemas must pass Draft7Validator.check_schema()."""

    def test_plan_ir_valid_schema(self):
        schema = _load("plan_ir.schema.json")
        jsonschema.Draft7Validator.check_schema(schema)

    def test_action_contract_valid_schema(self):
        schema = _load("action_contract.schema.json")
        jsonschema.Draft7Validator.check_schema(schema)

    def test_event_valid_schema(self):
        schema = _load("event.schema.json")
        jsonschema.Draft7Validator.check_schema(schema)

    def test_broker_event_valid_schema(self):
        schema = _load("broker_event.schema.json")
        jsonschema.Draft7Validator.check_schema(schema)

    def test_broker_coverage_valid_schema(self):
        schema = _load("broker_coverage.schema.json")
        jsonschema.Draft7Validator.check_schema(schema)


class TestActionContractFields:
    """action_contract.schema.json must have >= 11 required + >= 2 optional."""

    def test_required_fields_count(self):
        schema = _load("action_contract.schema.json")
        required = schema["required"]
        expected_required = {
            "schema_version", "action_id", "node_id", "kind", "intent",
            "read_set", "write_set", "required_capabilities", "preconditions",
            "success_predicates", "verification", "risk_class",
        }
        assert expected_required.issubset(set(required)), (
            f"Missing required fields: {expected_required - set(required)}"
        )
        assert len(required) >= 11

    def test_optional_fields_exist(self):
        schema = _load("action_contract.schema.json")
        props = set(schema["properties"].keys())
        optional = {"approval_required", "rollback", "timeout_sec", "legacy"}
        assert optional.issubset(props), (
            f"Missing optional fields: {optional - props}"
        )
        assert len(optional) >= 2

    def test_kind_enum_values(self):
        schema = _load("action_contract.schema.json")
        kind_enum = schema["properties"]["kind"]["enum"]
        assert set(kind_enum) == {
            "shell", "python", "file_write", "tool_call",
            "research_extract", "human_approval",
        }

    def test_risk_class_enum(self):
        schema = _load("action_contract.schema.json")
        risk_enum = schema["properties"]["risk_class"]["enum"]
        assert set(risk_enum) == {"low", "medium", "high"}

    def test_verification_subfields(self):
        schema = _load("action_contract.schema.json")
        ver = schema["properties"]["verification"]
        assert set(ver["required"]) == {"static", "runtime", "evidence"}

    def test_valid_fixture_passes(self):
        schema = _load("action_contract.schema.json")
        fixture = {
            "schema_version": "solar.action_contract.v1",
            "action_id": "A1",
            "node_id": "N3",
            "kind": "shell",
            "intent": "run deterministic verifier",
            "read_set": ["lib/foo.py"],
            "write_set": ["reports/output.json"],
            "required_capabilities": ["testing"],
            "preconditions": ["input exists"],
            "success_predicates": ["exit_code == 0"],
            "verification": {"static": True, "runtime": ["py_compile"], "evidence": ["output.json"]},
            "risk_class": "medium",
        }
        jsonschema.validate(instance=fixture, schema=schema)


class TestEventFields:
    """event.schema.json is the legacy coordinator event schema and must remain compatible."""

    def test_required_fields_count(self):
        schema = _load("event.schema.json")
        required = schema["required"]
        expected = {"ts", "actor", "event", "severity"}
        assert expected.issubset(set(required)), (
            f"Missing required: {expected - set(required)}"
        )
        assert schema["$id"] == "solar-harness-event-v1"

    def test_legacy_fixture_passes(self):
        schema = _load("event.schema.json")
        fixture = {
            "ts": "2026-05-20T10:00:00Z",
            "actor": "solar-harness",
            "event": "wake",
            "severity": "info",
            "sprint_id": "sprint-test",
            "payload": {"ok": True},
        }
        jsonschema.validate(instance=fixture, schema=schema)


class TestBrokerEventFields:
    """broker_event.schema.json must have >= 6 required + >= 6 optional."""

    def test_required_fields_count(self):
        schema = _load("broker_event.schema.json")
        required = schema["required"]
        expected = {"schema_version", "event_id", "ts", "sprint_id", "node_id", "type", "actor"}
        assert expected.issubset(set(required)), (
            f"Missing required: {expected - set(required)}"
        )
        assert len(required) >= 6

    def test_optional_fields_count(self):
        schema = _load("broker_event.schema.json")
        required = set(schema["required"])
        all_props = set(schema["properties"].keys())
        optional = all_props - required
        assert len(optional) >= 6, f"Only {len(optional)} optional fields: {optional}"

    def test_type_enum_values(self):
        schema = _load("broker_event.schema.json")
        type_enum = schema["properties"]["type"]["enum"]
        assert "action.executed" in type_enum
        assert "action.failed" in type_enum
        assert "policy.verdict" in type_enum

    def test_valid_fixture_passes(self):
        schema = _load("broker_event.schema.json")
        fixture = {
            "schema_version": "solar.broker_event.v1",
            "event_id": "evt_abcd1234",
            "ts": "2026-05-20T10:00:00Z",
            "sprint_id": "sprint-test",
            "node_id": "N1",
            "type": "action.executed",
            "actor": "builder:0.2",
        }
        jsonschema.validate(instance=fixture, schema=schema)


class TestBrokerCoverageFields:
    """broker_coverage.schema.json must match the current telemetry contract."""

    def test_required_fields_count(self):
        schema = _load("broker_coverage.schema.json")
        required = schema["required"]
        expected = {
            "total_actions",
            "contracted_actions",
            "coverage_pct",
            "unscoped_write_count",
            "policy_denied_count",
            "lease_denied_count",
            "human_approval_pending",
        }
        assert set(required) == expected
        assert len(required) == 7

    def test_coverage_pct_bounds(self):
        schema = _load("broker_coverage.schema.json")
        coverage = schema["properties"]["coverage_pct"]
        assert coverage["minimum"] == 0
        assert coverage["maximum"] == 100

    def test_valid_pass_fixture(self):
        schema = _load("broker_coverage.schema.json")
        fixture = {
            "total_actions": 10,
            "contracted_actions": 10,
            "coverage_pct": 100,
            "unscoped_write_count": 0,
            "policy_denied_count": 0,
            "lease_denied_count": 0,
            "human_approval_pending": 0,
        }
        jsonschema.validate(instance=fixture, schema=schema)


class TestPlanIRFields:
    def test_required_fields(self):
        schema = _load("plan_ir.schema.json")
        required = set(schema["required"])
        assert "schema_version" in required
        assert "sprint_id" in required
        assert "nodes" in required
        assert "actions" in required

    def test_valid_fixture_passes(self):
        schema = _load("plan_ir.schema.json")
        fixture = {
            "schema_version": "solar.plan_ir.v1",
            "sprint_id": "sprint-test",
            "epic_id": "epic-test",
            "nodes": [{
                "node_id": "N1",
                "goal": "implement schemas",
                "depends_on": [],
                "read_scope": [],
                "write_scope": [],
                "required_capabilities": [],
                "actions": ["A1"],
            }],
            "actions": [],
        }
        jsonschema.validate(instance=fixture, schema=schema)
