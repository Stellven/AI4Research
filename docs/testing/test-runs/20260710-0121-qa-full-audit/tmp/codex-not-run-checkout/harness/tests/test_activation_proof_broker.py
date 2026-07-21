#!/usr/bin/env python3
"""test_activation_proof_broker.py — N3: activation_proof broker_coverage section.

Acceptance criteria:
  - activation-proof JSON contains broker_coverage section
  - All 7 broker_coverage subfields present
  - JSON schema validation passes
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
HARNESS_SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
sys.path.insert(0, str(HARNESS_LIB))


REQUIRED_SUBFIELDS = (
    "total_actions",
    "contracted_actions",
    "coverage_pct",
    "unscoped_write_count",
    "policy_denied_count",
    "lease_denied_count",
    "human_approval_pending",
)


# ---------------------------------------------------------------------------
# Acceptance 1: broker_coverage section present in output JSON
# ---------------------------------------------------------------------------

class TestBrokerCoveragePresent:
    def setup_method(self):
        import activation_proof as mod
        self.mod = mod

    def test_build_activation_proof_has_broker_coverage_key(self):
        proof = self.mod.build_activation_proof()
        assert "broker_coverage" in proof, "broker_coverage key missing from activation proof"

    def test_build_activation_proof_ok_true(self):
        proof = self.mod.build_activation_proof()
        assert proof.get("ok") is True

    def test_build_activation_proof_has_schema_version(self):
        proof = self.mod.build_activation_proof()
        assert "schema_version" in proof

    def test_broker_coverage_is_dict(self):
        proof = self.mod.build_activation_proof()
        assert isinstance(proof["broker_coverage"], dict)

    def test_build_activation_proof_with_sprint_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        (tmp_path / "sprints").mkdir(exist_ok=True)
        (tmp_path / "schemas").mkdir(exist_ok=True)
        proof = self.mod.build_activation_proof("test-sprint-001")
        assert "broker_coverage" in proof
        assert proof.get("sprint_id") == "test-sprint-001"


# ---------------------------------------------------------------------------
# Acceptance 2: All 7 broker_coverage subfields present
# ---------------------------------------------------------------------------

class TestBrokerCoverageSubfields:
    def setup_method(self):
        import activation_proof as mod
        self.mod = mod

    def test_all_required_subfields_present_defaults(self):
        coverage = self.mod.build_broker_coverage()
        missing = [f for f in REQUIRED_SUBFIELDS if f not in coverage]
        assert not missing, f"Missing broker_coverage subfields: {missing}"

    def test_all_required_subfields_in_activation_proof_output(self):
        proof = self.mod.build_activation_proof()
        coverage = proof["broker_coverage"]
        missing = [f for f in REQUIRED_SUBFIELDS if f not in coverage]
        assert not missing, f"Missing broker_coverage subfields in proof: {missing}"

    def test_total_actions_is_int(self):
        coverage = self.mod.build_broker_coverage()
        assert isinstance(coverage["total_actions"], int)
        assert coverage["total_actions"] >= 0

    def test_contracted_actions_is_int(self):
        coverage = self.mod.build_broker_coverage()
        assert isinstance(coverage["contracted_actions"], int)
        assert coverage["contracted_actions"] >= 0

    def test_coverage_pct_is_float_in_range(self):
        coverage = self.mod.build_broker_coverage()
        pct = coverage["coverage_pct"]
        assert isinstance(pct, (int, float))
        assert 0.0 <= float(pct) <= 100.0

    def test_unscoped_write_count_is_int(self):
        coverage = self.mod.build_broker_coverage()
        assert isinstance(coverage["unscoped_write_count"], int)
        assert coverage["unscoped_write_count"] >= 0

    def test_policy_denied_count_is_int(self):
        coverage = self.mod.build_broker_coverage()
        assert isinstance(coverage["policy_denied_count"], int)
        assert coverage["policy_denied_count"] >= 0

    def test_lease_denied_count_is_int(self):
        coverage = self.mod.build_broker_coverage()
        assert isinstance(coverage["lease_denied_count"], int)
        assert coverage["lease_denied_count"] >= 0

    def test_human_approval_pending_is_int(self):
        coverage = self.mod.build_broker_coverage()
        assert isinstance(coverage["human_approval_pending"], int)
        assert coverage["human_approval_pending"] >= 0

    def test_defaults_when_no_sprint_id(self):
        coverage = self.mod.build_broker_coverage()
        for field in ("total_actions", "contracted_actions", "unscoped_write_count",
                      "policy_denied_count", "lease_denied_count", "human_approval_pending"):
            assert coverage[field] == 0, f"Expected 0 default for {field}"
        assert coverage["coverage_pct"] == 0.0


# ---------------------------------------------------------------------------
# Acceptance 3: JSON schema validation passes
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def setup_method(self):
        import activation_proof as mod
        self.mod = mod

    def test_validate_defaults_passes(self):
        coverage = self.mod.build_broker_coverage()
        result = self.mod.validate_against_schema(coverage)
        assert result["ok"] is True, f"Schema validation failed: {result}"

    def test_validate_activation_proof_coverage_passes(self):
        proof = self.mod.build_activation_proof()
        result = self.mod.validate_against_schema(proof["broker_coverage"])
        assert result["ok"] is True, f"Schema validation failed: {result}"

    def test_validate_missing_field_fails(self):
        coverage = dict(self.mod.BROKER_COVERAGE_DEFAULTS)
        del coverage["human_approval_pending"]
        result = self.mod.validate_against_schema(coverage)
        assert result["ok"] is False
        assert "missing_fields" in result.get("reason", "")
        assert "human_approval_pending" in result.get("missing", [])

    def test_validate_all_required_fields_present_passes(self):
        coverage = {f: 0 for f in REQUIRED_SUBFIELDS}
        coverage["coverage_pct"] = 0.0
        result = self.mod.validate_against_schema(coverage)
        assert result["ok"] is True

    def test_schema_file_exists_and_loadable(self):
        schema_path = HARNESS_SCHEMAS / "broker_coverage.schema.json"
        assert schema_path.exists(), f"Schema file missing: {schema_path}"
        schema = json.loads(schema_path.read_text())
        assert schema.get("type") == "object"
        assert "required" in schema
        for field in REQUIRED_SUBFIELDS:
            assert field in schema["required"], f"{field} not in schema required"

    def test_proof_broker_coverage_schema_exists_field(self, tmp_path, monkeypatch):
        schemas_dir = tmp_path / "schemas"
        schemas_dir.mkdir()
        schema_path = schemas_dir / "broker_coverage.schema.json"
        schema_data = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": list(REQUIRED_SUBFIELDS),
            "properties": {f: {"type": "integer"} for f in REQUIRED_SUBFIELDS},
        }
        schema_data["properties"]["coverage_pct"] = {"type": "number"}
        schema_path.write_text(json.dumps(schema_data))
        (tmp_path / "sprints").mkdir()
        (tmp_path / "lib").mkdir()
        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        proof = self.mod.build_activation_proof(include_schema_path=True)
        assert "broker_coverage_schema" in proof
        assert "broker_coverage_schema_exists" in proof


# ---------------------------------------------------------------------------
# Tests: source fallback chain
# ---------------------------------------------------------------------------

class TestBrokerCoverageSourceFallback:
    def setup_method(self):
        import activation_proof as mod
        self.mod = mod

    def test_defaults_source_when_no_observability(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        (tmp_path / "sprints").mkdir()
        coverage = self.mod.build_broker_coverage()
        assert coverage.get("_source") == "defaults"

    def test_events_jsonl_source_with_sprint_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        sprints = tmp_path / "sprints"
        sprints.mkdir()
        events_path = sprints / "sprint-test.events.jsonl"
        events = [
            {"type": "command_issued", "data": {"contracted": True}},
            {"type": "command_issued", "data": {}},
            {"type": "policy_denied", "data": {}},
        ]
        events_path.write_text("\n".join(json.dumps(e) for e in events))
        coverage = self.mod.build_broker_coverage("sprint-test")
        assert coverage["total_actions"] == 2
        assert coverage["contracted_actions"] == 1
        assert coverage["unscoped_write_count"] == 1
        assert coverage["policy_denied_count"] == 1
        assert abs(coverage["coverage_pct"] - 50.0) < 0.01
        assert "sprint-test" in coverage.get("_source", "")

    def test_all_fields_present_even_with_empty_events(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        (tmp_path / "sprints").mkdir()
        events_path = tmp_path / "sprints" / "sprint-empty.events.jsonl"
        events_path.write_text("")
        coverage = self.mod.build_broker_coverage("sprint-empty")
        for field in REQUIRED_SUBFIELDS:
            assert field in coverage, f"Missing field after empty events: {field}"

    def test_coverage_pct_zero_when_no_actions(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        (tmp_path / "sprints").mkdir()
        coverage = self.mod.build_broker_coverage("sprint-no-events")
        assert coverage["coverage_pct"] == 0.0

    def test_observability_metrics_used_when_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        obs_dir = tmp_path / "lib" / "observability"
        obs_dir.mkdir(parents=True)
        (obs_dir / "__init__.py").write_text("")
        metrics_code = """
def broker_coverage_pct(): return 75.0
def policy_denied_rate(): return 3
def approval_pending_count(): return 1
"""
        (obs_dir / "metrics.py").write_text(metrics_code)

        # Reload to pick up new HARNESS_DIR
        import importlib
        import activation_proof as mod
        importlib.reload(mod)
        monkeypatch.setattr(mod, "HARNESS_DIR", tmp_path)

        coverage = mod.build_broker_coverage()
        assert coverage["_source"] == "observability.metrics"
        assert float(coverage["coverage_pct"]) == 75.0
        assert int(coverage["policy_denied_count"]) == 3
        assert int(coverage["human_approval_pending"]) == 1


# ---------------------------------------------------------------------------
# Tests: CLI main function
# ---------------------------------------------------------------------------

class TestActivationProofCLI:
    def setup_method(self):
        import activation_proof as mod
        self.mod = mod

    def test_main_exits_zero(self, capsys):
        with patch("sys.argv", ["activation_proof.py"]):
            rc = self.mod.main()
        assert rc == 0

    def test_main_outputs_valid_json(self, capsys):
        with patch("sys.argv", ["activation_proof.py"]):
            self.mod.main()
        captured = capsys.readouterr()
        proof = json.loads(captured.out)
        assert proof["ok"] is True
        assert "broker_coverage" in proof

    def test_main_with_validate_flag(self, capsys):
        with patch("sys.argv", ["activation_proof.py", "--validate"]):
            self.mod.main()
        captured = capsys.readouterr()
        proof = json.loads(captured.out)
        assert "schema_validation" in proof
        assert proof["schema_validation"]["ok"] is True
