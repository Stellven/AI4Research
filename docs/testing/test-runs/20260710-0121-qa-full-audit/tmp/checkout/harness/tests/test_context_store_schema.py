#!/usr/bin/env python3
"""
Tests for context-store schema and fixture.

Sprint: sprint-20260523-lease-based-model-fleet-runtime / N2
Validates:
  - Schema defines context_packet with packet_type enum (project/task/memory)
  - Schema defines task_envelope with criticality levels
  - Critical task envelopes MUST have context_packet_ref or context_packet — reject if absent
  - Non-critical envelopes may omit context_packet_ref
  - Task packets must have sprint_id and node_id (via if/then)
  - Fixture validates against schema end-to-end
  - Fixture's critical envelopes all carry context_packet_ref or context_packet
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
CS_SCHEMA_FILE = CONFIG_DIR / "context-store.schema.json"
CS_FILE = CONFIG_DIR / "context-store.json"


def _load_cs_schema() -> dict:
    return json.loads(CS_SCHEMA_FILE.read_text(encoding="utf-8"))


def _load_cs() -> dict:
    return json.loads(CS_FILE.read_text(encoding="utf-8"))


class TestContextStoreSchemaDefinitions:
    """Schema must define context_packet and task_envelope sub-schemas."""

    def test_schema_defines_context_packet(self):
        schema = _load_cs_schema()
        assert "context_packet" in schema.get("$defs", {}), (
            "context-store schema missing $defs/context_packet"
        )

    def test_schema_defines_task_envelope(self):
        schema = _load_cs_schema()
        assert "task_envelope" in schema.get("$defs", {}), (
            "context-store schema missing $defs/task_envelope"
        )

    def test_schema_defines_packet_type(self):
        schema = _load_cs_schema()
        assert "packet_type" in schema.get("$defs", {}), (
            "context-store schema missing $defs/packet_type"
        )

    def test_packet_type_enum_has_project_task_memory(self):
        schema = _load_cs_schema()
        enum_vals = schema["$defs"]["packet_type"].get("enum", [])
        assert "project" in enum_vals
        assert "task" in enum_vals
        assert "memory" in enum_vals

    def test_packet_type_enum_has_exactly_three_values(self):
        schema = _load_cs_schema()
        enum_vals = schema["$defs"]["packet_type"].get("enum", [])
        assert len(enum_vals) == 3, (
            f"packet_type enum should have exactly 3 values, got {len(enum_vals)}: {enum_vals}"
        )

    def test_context_packet_requires_packet_id(self):
        schema = _load_cs_schema()
        required = schema["$defs"]["context_packet"].get("required", [])
        assert "packet_id" in required

    def test_context_packet_requires_packet_type(self):
        schema = _load_cs_schema()
        required = schema["$defs"]["context_packet"].get("required", [])
        assert "packet_type" in required

    def test_context_packet_requires_created_at(self):
        schema = _load_cs_schema()
        required = schema["$defs"]["context_packet"].get("required", [])
        assert "created_at" in required

    def test_task_envelope_requires_envelope_id(self):
        schema = _load_cs_schema()
        required = schema["$defs"]["task_envelope"].get("required", [])
        assert "envelope_id" in required

    def test_task_envelope_requires_task_id(self):
        schema = _load_cs_schema()
        required = schema["$defs"]["task_envelope"].get("required", [])
        assert "task_id" in required

    def test_task_envelope_requires_criticality(self):
        schema = _load_cs_schema()
        required = schema["$defs"]["task_envelope"].get("required", [])
        assert "criticality" in required

    def test_task_envelope_requires_assigned_actor_id(self):
        schema = _load_cs_schema()
        required = schema["$defs"]["task_envelope"].get("required", [])
        assert "assigned_actor_id" in required

    def test_criticality_enum_has_four_levels(self):
        schema = _load_cs_schema()
        props = schema["$defs"]["task_envelope"].get("properties", {})
        assert "criticality" in props
        enum_vals = props["criticality"].get("enum", [])
        assert "low" in enum_vals
        assert "normal" in enum_vals
        assert "high" in enum_vals
        assert "critical" in enum_vals


class TestCriticalTaskEnvelopeEnforcement:
    """Critical task envelopes must have context_packet_ref or embedded context_packet."""

    def _make_envelope(self, criticality: str, **kwargs) -> dict:
        base = {
            "envelope_id": "test-env",
            "task_id": "T1",
            "criticality": criticality,
            "assigned_actor_id": "mini-claude-sonnet-builder",
        }
        base.update(kwargs)
        return base

    def _validate_envelope(self, envelope: dict):
        schema = _load_cs_schema()
        envelope_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
        }
        envelope_schema.update(schema["$defs"]["task_envelope"])
        jsonschema.validate(instance=envelope, schema=envelope_schema)

    def test_critical_envelope_with_context_packet_ref_passes(self):
        envelope = self._make_envelope(
            "critical",
            context_packet_ref={"packet_id": "pkt-123", "path": "context/pkt-123.json"},
        )
        self._validate_envelope(envelope)

    def test_critical_envelope_with_embedded_context_packet_passes(self):
        envelope = self._make_envelope(
            "critical",
            context_packet={
                "packet_id": "pkt-inline",
                "packet_type": "task",
                "created_at": "2026-05-23T00:00:00Z",
                "sprint_id": "sprint-xyz",
                "node_id": "N1",
            },
        )
        self._validate_envelope(envelope)

    def test_critical_envelope_without_context_fails(self):
        envelope = self._make_envelope("critical")
        with pytest.raises(jsonschema.ValidationError):
            self._validate_envelope(envelope)

    def test_critical_envelope_with_null_context_packet_ref_fails(self):
        envelope = self._make_envelope(
            "critical",
            context_packet_ref=None,
        )
        with pytest.raises(jsonschema.ValidationError):
            self._validate_envelope(envelope)

    def test_low_envelope_without_context_passes(self):
        envelope = self._make_envelope("low")
        self._validate_envelope(envelope)

    def test_normal_envelope_without_context_passes(self):
        envelope = self._make_envelope("normal")
        self._validate_envelope(envelope)

    def test_high_envelope_without_context_passes(self):
        envelope = self._make_envelope("high")
        self._validate_envelope(envelope)


class TestTaskPacketConstraints:
    """Task packets must carry sprint_id and node_id."""

    def _make_packet(self, packet_type: str, **kwargs) -> dict:
        base = {
            "packet_id": "pkt-test",
            "packet_type": packet_type,
            "created_at": "2026-05-23T00:00:00Z",
        }
        base.update(kwargs)
        return base

    def _validate_packet(self, packet: dict):
        schema = _load_cs_schema()
        packet_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
        }
        packet_schema.update(schema["$defs"]["context_packet"])
        jsonschema.validate(instance=packet, schema=packet_schema)

    def test_task_packet_with_sprint_and_node_passes(self):
        packet = self._make_packet(
            "task",
            sprint_id="sprint-xyz",
            node_id="N1",
            expires_at="2026-05-24T00:00:00Z",
        )
        self._validate_packet(packet)

    def test_task_packet_without_sprint_id_fails(self):
        packet = self._make_packet(
            "task",
            node_id="N1",
            expires_at="2026-05-24T00:00:00Z",
        )
        with pytest.raises(jsonschema.ValidationError):
            self._validate_packet(packet)

    def test_task_packet_without_node_id_fails(self):
        packet = self._make_packet(
            "task",
            sprint_id="sprint-xyz",
            expires_at="2026-05-24T00:00:00Z",
        )
        with pytest.raises(jsonschema.ValidationError):
            self._validate_packet(packet)

    def test_project_packet_without_sprint_and_node_passes(self):
        packet = self._make_packet("project")
        self._validate_packet(packet)

    def test_memory_packet_without_sprint_and_node_passes(self):
        packet = self._make_packet("memory")
        self._validate_packet(packet)

    def test_packet_type_rejects_unknown_type(self):
        packet = self._make_packet("ephemeral")
        with pytest.raises(jsonschema.ValidationError):
            self._validate_packet(packet)


class TestContextStoreFixture:
    """Fixture must pass schema validation and obey the critical envelope rule."""

    def test_fixture_validates_against_schema(self):
        cs = _load_cs()
        schema = _load_cs_schema()
        jsonschema.validate(instance=cs, schema=schema)

    def test_fixture_has_packets_section(self):
        cs = _load_cs()
        assert "packets" in cs, "context-store.json missing packets section"

    def test_fixture_has_at_least_one_packet(self):
        cs = _load_cs()
        assert len(cs.get("packets", {})) >= 1, "context-store.json must have at least one packet"

    def test_fixture_has_all_three_packet_types(self):
        cs = _load_cs()
        types_present = {p["packet_type"] for p in cs.get("packets", {}).values()}
        assert "project" in types_present, "fixture missing a project-type packet"
        assert "task" in types_present, "fixture missing a task-type packet"
        assert "memory" in types_present, "fixture missing a memory-type packet"

    def test_all_critical_envelopes_have_context_packet_ref_or_embedded(self):
        cs = _load_cs()
        for env_id, env in cs.get("task_envelopes", {}).items():
            if env.get("criticality") == "critical":
                has_ref = (
                    env.get("context_packet_ref") is not None
                    and env.get("context_packet_ref") != {}
                )
                has_embedded = "context_packet" in env and env["context_packet"] is not None
                assert has_ref or has_embedded, (
                    f"{env_id}: critical envelope missing context_packet_ref or context_packet"
                )

    def test_all_packet_ids_match_their_keys(self):
        cs = _load_cs()
        for pkt_key, pkt in cs.get("packets", {}).items():
            assert pkt.get("packet_id") == pkt_key, (
                f"packet key={pkt_key!r} but packet_id={pkt.get('packet_id')!r}"
            )

    def test_all_envelope_ids_match_their_keys(self):
        cs = _load_cs()
        for env_key, env in cs.get("task_envelopes", {}).items():
            assert env.get("envelope_id") == env_key, (
                f"envelope key={env_key!r} but envelope_id={env.get('envelope_id')!r}"
            )

    def test_task_packets_have_sprint_and_node(self):
        cs = _load_cs()
        for pkt_key, pkt in cs.get("packets", {}).items():
            if pkt.get("packet_type") == "task":
                assert pkt.get("sprint_id"), (
                    f"{pkt_key}: task packet missing sprint_id"
                )
                assert pkt.get("node_id"), (
                    f"{pkt_key}: task packet missing node_id"
                )

    def test_fixture_version_is_integer(self):
        cs = _load_cs()
        assert isinstance(cs.get("version"), int)
        assert cs["version"] >= 1


class TestContextStoreSchemaValidation:
    """End-to-end schema validation: good and bad instances."""

    def test_schema_accepts_minimal_project_packet(self):
        schema = _load_cs_schema()
        valid = {
            "version": 1,
            "packets": {
                "pkt-minimal": {
                    "packet_id": "pkt-minimal",
                    "packet_type": "project",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            }
        }
        jsonschema.validate(instance=valid, schema=schema)

    def test_schema_rejects_missing_packets(self):
        schema = _load_cs_schema()
        bad = {"version": 1}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)

    def test_schema_rejects_missing_version(self):
        schema = _load_cs_schema()
        bad = {"packets": {}}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)

    def test_schema_accepts_empty_packets_and_envelopes(self):
        schema = _load_cs_schema()
        valid = {
            "version": 1,
            "packets": {},
            "task_envelopes": {},
        }
        jsonschema.validate(instance=valid, schema=schema)


if __name__ == "__main__":
    suites = [
        TestContextStoreSchemaDefinitions(),
        TestCriticalTaskEnvelopeEnforcement(),
        TestTaskPacketConstraints(),
        TestContextStoreFixture(),
        TestContextStoreSchemaValidation(),
    ]
    passed = 0
    failed = 0
    for suite in suites:
        for name in dir(suite):
            if not name.startswith("test_"):
                continue
            try:
                getattr(suite, name)()
                print(f"  PASS  {suite.__class__.__name__}::{name}")
                passed += 1
            except Exception as exc:
                print(f"  FAIL  {suite.__class__.__name__}::{name}: {exc}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)
