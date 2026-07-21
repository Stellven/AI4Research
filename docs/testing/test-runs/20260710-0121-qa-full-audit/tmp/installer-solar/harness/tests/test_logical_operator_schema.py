#!/usr/bin/env python3
"""
Tests for logical-operators schema and fixture.

Sprint: sprint-20260523-lease-based-model-fleet-runtime / N2
Validates:
  - Schema defines all 16 P0 logical operator types in the enum
  - Fixture contains entries for all 16 types
  - Binding table maps every logical operator type to at least one candidate actor_id
  - All candidate actor_ids in bindings exist in agent-actors.json
  - DAG node schema accepts logical_operator
  - DAG node schema rejects physical_actor_id/physical_operator_id/physical_model_id
    unless compatibility=true
  - Fixture validates against schema end-to-end
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
LO_SCHEMA_FILE = CONFIG_DIR / "logical-operators.schema.json"
LO_FILE = CONFIG_DIR / "logical-operators.json"
ACTORS_FILE = CONFIG_DIR / "agent-actors.json"

OPERATOR_TYPES = [
    "DeepArchitect",
    "RootCauseDebugger",
    "ImplementationWorker",
    "PatchWorker",
    "TestDesigner",
    "TestRunner",
    "BenchmarkRunner",
    "ParallelExplorer",
    "ResearchScout",
    "ResearchSynthesizer",
    "Critic",
    "Verifier",
    "VerifierLite",
    "SecurityGate",
    "QuotaBroker",
    "ContextCompressor",
    "ArtifactCurator",
    "DeepResearchBrowser",
    "DeepResearchGemini",
    "DeepResearchChatGPT",
    "WebwrightPlaywright",
    "BrowserUseMcp",
    "YoutubeTranscriptExtractor",
    "TechnologyDiagramPainter",
]


def _load_lo_schema() -> dict:
    return json.loads(LO_SCHEMA_FILE.read_text(encoding="utf-8"))


def _load_lo() -> dict:
    return json.loads(LO_FILE.read_text(encoding="utf-8"))


def _load_actors() -> dict:
    return json.loads(ACTORS_FILE.read_text(encoding="utf-8"))


class TestLogicalOperatorSchemaEnum:
    """Schema enum must include all declared logical operator types."""

    def test_schema_defines_logical_operator_type_enum(self):
        schema = _load_lo_schema()
        defs = schema.get("$defs", {})
        assert "logical_operator_type" in defs, (
            "logical-operators schema missing $defs/logical_operator_type"
        )

    def test_enum_contains_all_16_types(self):
        schema = _load_lo_schema()
        enum_vals = schema["$defs"]["logical_operator_type"].get("enum", [])
        missing = set(OPERATOR_TYPES) - set(enum_vals)
        assert not missing, f"logical_operator_type enum missing: {missing}"

    def test_enum_has_exactly_24_entries(self):
        schema = _load_lo_schema()
        enum_vals = schema["$defs"]["logical_operator_type"].get("enum", [])
        assert len(enum_vals) == 24, (
            f"Expected 24 logical operator types, got {len(enum_vals)}: {enum_vals}"
        )

    @pytest.mark.parametrize("op_type", OPERATOR_TYPES)
    def test_each_type_in_enum(self, op_type):
        schema = _load_lo_schema()
        enum_vals = schema["$defs"]["logical_operator_type"].get("enum", [])
        assert op_type in enum_vals, (
            f"{op_type!r} missing from logical_operator_type enum"
        )


class TestLogicalOperatorSchemaDefinitions:
    """Schema must define required sub-schemas for operator defs and bindings."""

    def test_schema_defines_logical_operator_def(self):
        schema = _load_lo_schema()
        assert "logical_operator_def" in schema.get("$defs", {}), (
            "logical-operators schema missing $defs/logical_operator_def"
        )

    def test_schema_defines_binding_entry(self):
        schema = _load_lo_schema()
        assert "binding_entry" in schema.get("$defs", {}), (
            "logical-operators schema missing $defs/binding_entry"
        )

    def test_schema_defines_dag_node(self):
        schema = _load_lo_schema()
        assert "dag_node" in schema.get("$defs", {}), (
            "logical-operators schema missing $defs/dag_node"
        )

    def test_logical_operator_def_requires_operator_type(self):
        schema = _load_lo_schema()
        required = schema["$defs"]["logical_operator_def"].get("required", [])
        assert "operator_type" in required

    def test_logical_operator_def_requires_description(self):
        schema = _load_lo_schema()
        required = schema["$defs"]["logical_operator_def"].get("required", [])
        assert "description" in required

    def test_binding_entry_requires_operator_type_and_candidates(self):
        schema = _load_lo_schema()
        required = schema["$defs"]["binding_entry"].get("required", [])
        assert "operator_type" in required
        assert "candidates" in required


class TestDAGNodePhysicalIdRejection:
    """DAG node schema must reject physical ids unless compatibility=true."""

    def _dag_node_schema(self) -> dict:
        parent = _load_lo_schema()
        # Embed $defs so $ref resolution works when the dag_node is used standalone
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema"}
        schema["$defs"] = parent["$defs"]
        schema.update(parent["$defs"]["dag_node"])
        return schema

    def test_dag_node_accepts_logical_operator(self):
        valid = {
            "node_id": "N1",
            "logical_operator": "DeepArchitect",
        }
        jsonschema.validate(instance=valid, schema=self._dag_node_schema())

    def test_dag_node_rejects_physical_actor_id_without_compatibility(self):
        bad = {
            "node_id": "N1",
            "physical_actor_id": "mini-claude-sonnet-builder",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=self._dag_node_schema())

    def test_dag_node_rejects_physical_operator_id_without_compatibility(self):
        bad = {
            "node_id": "N1",
            "physical_operator_id": "mini-claude-sonnet-builder",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=self._dag_node_schema())

    def test_dag_node_rejects_physical_model_id_without_compatibility(self):
        bad = {
            "node_id": "N1",
            "physical_model_id": "claude-sonnet-4-6",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=self._dag_node_schema())

    def test_dag_node_accepts_physical_actor_id_with_compatibility_true(self):
        valid = {
            "node_id": "N1",
            "compatibility": True,
            "physical_actor_id": "mini-claude-sonnet-builder",
        }
        jsonschema.validate(instance=valid, schema=self._dag_node_schema())

    def test_dag_node_accepts_physical_operator_id_with_compatibility_true(self):
        valid = {
            "node_id": "N1",
            "compatibility": True,
            "physical_operator_id": "mini-claude-sonnet-builder",
        }
        jsonschema.validate(instance=valid, schema=self._dag_node_schema())


class TestLogicalOperatorFixture:
    """Fixture must define entries for all declared types."""

    def test_fixture_has_logical_operators_section(self):
        lo = _load_lo()
        assert "logical_operators" in lo, "logical-operators.json missing logical_operators"

    def test_fixture_has_bindings_section(self):
        lo = _load_lo()
        assert "bindings" in lo, "logical-operators.json missing bindings"

    def test_fixture_defines_all_operator_types(self):
        lo = _load_lo()
        defined = set(lo["logical_operators"].keys())
        missing = set(OPERATOR_TYPES) - defined
        assert not missing, (
            f"logical-operators.json missing operator definitions: {missing}"
        )

    @pytest.mark.parametrize("op_type", OPERATOR_TYPES)
    def test_each_operator_type_has_definition(self, op_type):
        lo = _load_lo()
        assert op_type in lo["logical_operators"], (
            f"logical-operators.json missing definition for {op_type!r}"
        )

    def test_each_operator_has_operator_type_field(self):
        lo = _load_lo()
        for op_type, op_def in lo["logical_operators"].items():
            assert "operator_type" in op_def, (
                f"{op_type}: missing operator_type field"
            )
            assert op_def["operator_type"] == op_type, (
                f"{op_type}: operator_type value mismatch"
            )

    def test_each_operator_has_description(self):
        lo = _load_lo()
        for op_type, op_def in lo["logical_operators"].items():
            assert "description" in op_def, f"{op_type}: missing description"
            assert op_def["description"], f"{op_type}: description is empty"

    def test_each_operator_has_primary_role(self):
        lo = _load_lo()
        valid_roles = {"planner", "builder", "evaluator", "knowledge-extractor", "router", "auditor"}
        for op_type, op_def in lo["logical_operators"].items():
            assert "primary_role" in op_def, f"{op_type}: missing primary_role"
            assert op_def["primary_role"] in valid_roles, (
                f"{op_type}: primary_role={op_def['primary_role']!r} not in {valid_roles}"
            )


class TestBindingFixture:
    """Binding table must cover all declared types; all candidate actor_ids must exist."""

    def test_binding_table_covers_all_types(self):
        lo = _load_lo()
        defined = set(lo["bindings"].keys())
        missing = set(OPERATOR_TYPES) - defined
        assert not missing, (
            f"logical-operators.json bindings missing entries for: {missing}"
        )

    @pytest.mark.parametrize("op_type", OPERATOR_TYPES)
    def test_each_type_has_binding(self, op_type):
        lo = _load_lo()
        assert op_type in lo["bindings"], (
            f"logical-operators.json bindings missing entry for {op_type!r}"
        )

    def test_each_binding_has_at_least_one_candidate(self):
        lo = _load_lo()
        for op_type, binding in lo["bindings"].items():
            candidates = binding.get("candidates", [])
            assert len(candidates) >= 1, (
                f"{op_type}: binding must have at least one candidate"
            )

    def test_all_binding_candidates_exist_in_actor_registry(self):
        lo = _load_lo()
        actors = _load_actors()
        known_actor_ids = set(actors["actors"].keys())
        for op_type, binding in lo["bindings"].items():
            for i, candidate in enumerate(binding.get("candidates", [])):
                actor_id = candidate.get("actor_id")
                assert actor_id in known_actor_ids, (
                    f"{op_type}.candidates[{i}]: actor_id={actor_id!r} "
                    "not found in agent-actors.json"
                )

    def test_each_binding_has_operator_type_field(self):
        lo = _load_lo()
        for op_type, binding in lo["bindings"].items():
            assert "operator_type" in binding, (
                f"{op_type}: binding missing operator_type field"
            )
            assert binding["operator_type"] == op_type, (
                f"{op_type}: binding.operator_type mismatch"
            )

    def test_each_candidate_has_actor_id(self):
        lo = _load_lo()
        for op_type, binding in lo["bindings"].items():
            for i, candidate in enumerate(binding.get("candidates", [])):
                assert "actor_id" in candidate, (
                    f"{op_type}.candidates[{i}]: missing actor_id"
                )


class TestLogicalOperatorFixtureSchemaValidation:
    """Fixture must validate against the logical-operators schema."""

    def test_fixture_validates_against_schema(self):
        lo = _load_lo()
        schema = _load_lo_schema()
        jsonschema.validate(instance=lo, schema=schema)

    def test_fixture_version_is_integer(self):
        lo = _load_lo()
        assert isinstance(lo.get("version"), int), "version must be an integer"
        assert lo["version"] >= 1

    def test_schema_rejects_fixture_missing_bindings(self):
        schema = _load_lo_schema()
        bad = {
            "version": 1,
            "logical_operators": {},
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)

    def test_schema_rejects_fixture_missing_logical_operators(self):
        schema = _load_lo_schema()
        bad = {
            "version": 1,
            "bindings": {},
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad, schema=schema)


if __name__ == "__main__":
    suites = [
        TestLogicalOperatorSchemaEnum(),
        TestLogicalOperatorSchemaDefinitions(),
        TestDAGNodePhysicalIdRejection(),
        TestLogicalOperatorFixture(),
        TestBindingFixture(),
        TestLogicalOperatorFixtureSchemaValidation(),
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
