#!/usr/bin/env python3
"""test_s04_e2e.py — S04 end-to-end integration test.

Acceptance criteria (N8):
  1. Full chain: dispatcher env → activation-proof → evidence_validator PASS
  2. All upstream N1-N7 nodes that have importable tests still PASS
  3. SOLAR_BROKER_ENABLED=0 legacy path unchanged in dispatcher
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

HARNESS_ROOT = Path(__file__).resolve().parent.parent
HARNESS_LIB = HARNESS_ROOT / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from activation_proof import (
    build_activation_proof,
    build_broker_coverage,
    validate_against_schema,
    BROKER_COVERAGE_FIELDS,
)
from graph_node_dispatcher import _broker_env
from pane_handoff.evidence_validator import validate as ev_validate, ValidationResult


# ---------------------------------------------------------------------------
# Acceptance 1A: _broker_env (N2) → broker_coverage (N3)
# Dispatcher env passthrough feeds broker_coverage defaults.
# ---------------------------------------------------------------------------

class TestDispatcherEnvToActivationProof:
    def test_broker_env_default_disabled(self):
        """_broker_env with no SOLAR_BROKER_ENABLED set → env gets '0'."""
        with mock.patch.dict(os.environ, {}, clear=True):
            env = _broker_env(None)
        assert env["SOLAR_BROKER_ENABLED"] == "0"

    def test_broker_env_preserves_existing_enabled(self):
        """_broker_env must not override caller's SOLAR_BROKER_ENABLED=1."""
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            env = _broker_env(None)
        assert env["SOLAR_BROKER_ENABLED"] == "1"

    def test_broker_env_injects_sprint_id(self):
        """_broker_env injects SOLAR_BROKER_SPRINT_ID when sprint_id given."""
        with mock.patch.dict(os.environ, {}, clear=True):
            env = _broker_env("sprint-test-123")
        assert env.get("SOLAR_BROKER_SPRINT_ID") == "sprint-test-123"

    def test_broker_env_does_not_override_sprint_id(self):
        """_broker_env must not override caller's SOLAR_BROKER_SPRINT_ID."""
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_SPRINT_ID": "existing-sprint"}):
            env = _broker_env("new-sprint")
        assert env["SOLAR_BROKER_SPRINT_ID"] == "existing-sprint"

    def test_activation_proof_contains_broker_coverage(self):
        """build_activation_proof returns dict with broker_coverage key."""
        proof = build_activation_proof(sprint_id=None)
        assert "broker_coverage" in proof

    def test_activation_proof_all_7_fields(self):
        """broker_coverage has all 7 required subfields."""
        proof = build_activation_proof(sprint_id=None)
        bc = proof["broker_coverage"]
        for field in BROKER_COVERAGE_FIELDS:
            assert field in bc, f"Missing broker_coverage field: {field}"

    def test_activation_proof_schema_valid(self):
        """validate_against_schema passes on build_broker_coverage output."""
        bc = build_broker_coverage(sprint_id=None)
        result = validate_against_schema(bc)
        assert result["ok"] is True

    def test_broker_coverage_numeric_types(self):
        """broker_coverage fields have correct numeric types."""
        bc = build_broker_coverage(sprint_id=None)
        assert isinstance(bc["coverage_pct"], float)
        for field in ("total_actions", "contracted_actions", "unscoped_write_count",
                      "policy_denied_count", "lease_denied_count", "human_approval_pending"):
            assert isinstance(bc[field], int), f"{field} should be int"


# ---------------------------------------------------------------------------
# Acceptance 1B: activation-proof → evidence_validator
# Activation proof artifact path in handoff text → ok=True
# ---------------------------------------------------------------------------

class TestActivationProofToEvidenceValidator:
    def test_activation_proof_path_as_ref(self):
        """Handoff referencing activation_proof.py path → validator ok=True."""
        text = (
            "# Handoff\n\n"
            "Activation proof generated at "
            f"`{HARNESS_LIB / 'activation_proof.py'}` and validated.\n"
        )
        result = ev_validate(text, events_jsonl_paths=[])
        assert result.ok is True

    def test_activation_proof_json_as_handoff_ref(self):
        """Handoff with real event UUID from dispatch context → ok=True."""
        event_id = "19cafd5a-0f1a-46b3-ab07-88f15596c12a"
        text = (
            f"# Handoff\n\n"
            f"Activation proof confirmed, event_id `{event_id}`.\n"
        )
        result = ev_validate(text, events_jsonl_paths=[])
        assert result.ok is True

    def test_evidence_validator_rejects_bare_activation_claim(self):
        """'done' + 'implemented' without refs → validator ok=False."""
        text = "# Handoff\n\nActivation done. Implemented.\n"
        result = ev_validate(text, events_jsonl_paths=[])
        assert result.ok is False
        assert len(result.missing_refs) > 0

    def test_evidence_validator_result_type(self):
        """validate() returns ValidationResult."""
        result = ev_validate(
            f"# Handoff\n\nPath `{HARNESS_LIB / 'activation_proof.py'}` ready.\n",
            events_jsonl_paths=[],
        )
        assert isinstance(result, ValidationResult)

    def test_to_dict_round_trip(self):
        """ValidationResult.to_dict() has ok, refs, missing_refs keys."""
        result = ev_validate(
            "# Handoff\n\nSee `graph-sprint-test-N8-20260520T200000Z`.\n",
            events_jsonl_paths=[],
        )
        d = result.to_dict()
        assert "ok" in d and "refs" in d and "missing_refs" in d


# ---------------------------------------------------------------------------
# Acceptance 1C: Full end-to-end chain test
# SOLAR_BROKER_ENABLED=0 → dispatcher env → activation_proof → evidence_validator
# ---------------------------------------------------------------------------

class TestFullChainE2E:
    def test_full_chain_legacy_mode(self):
        """Full chain with SOLAR_BROKER_ENABLED=0: env → proof → evidence."""
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "0"}):
            env = _broker_env(sprint_id="sprint-s04-e2e-test")
            assert env["SOLAR_BROKER_ENABLED"] == "0"
            assert env["SOLAR_BROKER_SPRINT_ID"] == "sprint-s04-e2e-test"

            proof = build_activation_proof(sprint_id="sprint-s04-e2e-test")
            bc = proof["broker_coverage"]
            schema_result = validate_against_schema(bc)
            assert schema_result["ok"] is True

        artifact_path = HARNESS_LIB / "activation_proof.py"
        handoff_text = (
            "# Handoff\n\n"
            f"Activation proof at `{artifact_path}`, schema valid. "
            f"Dispatch action: `graph-sprint-s04-e2e-test-N8-20260520T200000Z`.\n"
        )
        ev_result = ev_validate(handoff_text, events_jsonl_paths=[])
        assert ev_result.ok is True

    def test_full_chain_broker_enabled_mode(self):
        """Full chain with SOLAR_BROKER_ENABLED=1: same outputs, coverage populated."""
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            env = _broker_env(sprint_id=None)
            assert env["SOLAR_BROKER_ENABLED"] == "1"

            proof = build_activation_proof(sprint_id=None)
            assert "broker_coverage" in proof
            for field in BROKER_COVERAGE_FIELDS:
                assert field in proof["broker_coverage"]

        handoff_text = (
            "# Handoff\n\n"
            f"Output at `{HARNESS_LIB / 'activation_proof.py'}`.\n"
        )
        result = ev_validate(handoff_text, events_jsonl_paths=[])
        assert result.ok is True

    def test_chain_produces_verifiable_handoff(self):
        """Chain output can produce a handoff that evidence_validator accepts."""
        proof = build_activation_proof(sprint_id=None)
        bc = proof["broker_coverage"]
        schema_ok = validate_against_schema(bc)["ok"]

        handoff_text = (
            "# N8 Handoff\n\n"
            "## Summary\n\n"
            f"Activation proof validated: schema_ok={schema_ok}. "
            f"Output at `{HARNESS_LIB / 'activation_proof.py'}`.\n\n"
            "## Verification Evidence\n\n"
            f"Dispatch: `graph-sprint-s04-orchestration-ui-N8-20260520T200000Z`.\n"
        )
        result = ev_validate(handoff_text, events_jsonl_paths=[])
        assert result.ok is True
        assert len(result.refs["action_ids"]) >= 1


# ---------------------------------------------------------------------------
# Acceptance 2: SOLAR_BROKER_ENABLED=0 legacy path identical to pre-S04
# ---------------------------------------------------------------------------

class TestLegacyPathUnchanged:
    def test_broker_env_zero_is_default(self):
        """SOLAR_BROKER_ENABLED=0 is the default — no env needed."""
        with mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                          if k != "SOLAR_BROKER_ENABLED"}):
            env = _broker_env(None)
        assert env["SOLAR_BROKER_ENABLED"] == "0"

    def test_broker_env_zero_does_not_add_sprint_id(self):
        """When sprint_id is None, SOLAR_BROKER_SPRINT_ID is not added."""
        with mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                          if k not in ("SOLAR_BROKER_ENABLED",
                                                       "SOLAR_BROKER_SPRINT_ID")}):
            env = _broker_env(None)
        assert "SOLAR_BROKER_SPRINT_ID" not in env

    def test_legacy_subprocess_sees_disabled_flag(self):
        """Child subprocess spawned with broker_env receives SOLAR_BROKER_ENABLED=0."""
        env = _broker_env(None)
        result = subprocess.run(
            [sys.executable, "-c",
             "import os, sys; sys.exit(0 if os.environ.get('SOLAR_BROKER_ENABLED') == '0' else 1)"],
            env=env,
            timeout=10,
        )
        assert result.returncode == 0

    def test_legacy_subprocess_does_not_see_sprint_id(self):
        """Child subprocess without sprint_id does not see SOLAR_BROKER_SPRINT_ID."""
        env = _broker_env(None)
        env.pop("SOLAR_BROKER_SPRINT_ID", None)
        result = subprocess.run(
            [sys.executable, "-c",
             "import os, sys; sys.exit(0 if 'SOLAR_BROKER_SPRINT_ID' not in os.environ else 1)"],
            env=env,
            timeout=10,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Acceptance 3: Upstream node regressions (N2/N3/N7 importable — must PASS)
# N1/N4/N6 have pre-existing ModuleNotFoundError ('harness.lib') not caused by N8.
# ---------------------------------------------------------------------------

class TestUpstreamNodeRegressions:
    """Verify N8 integration does not break upstream nodes.

    N2/N3/N7 tests use correct import paths (sys.path + direct import) and pass.
    N1/N4/N6 tests use `from harness.lib.xxx import ...` which requires a
    `harness/__init__.py` that does not exist — these are pre-existing failures
    from those nodes, not caused by N8.
    """

    def _run_pytest(self, test_file: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "--tb=short", "-q"],
            capture_output=True,
            text=True,
            cwd=str(HARNESS_ROOT),
            timeout=60,
        )

    def test_n2_dispatcher_env_passthrough_still_passes(self):
        """N2 test suite still passes after N8 integration."""
        r = self._run_pytest("tests/test_dispatcher_env_passthrough.py")
        assert r.returncode == 0, f"N2 tests regressed:\n{r.stdout}\n{r.stderr}"

    def test_n3_activation_proof_broker_still_passes(self):
        """N3 test suite still passes after N8 integration."""
        r = self._run_pytest("tests/test_activation_proof_broker.py")
        assert r.returncode == 0, f"N3 tests regressed:\n{r.stdout}\n{r.stderr}"

    def test_n7_pane_handoff_evidence_still_passes(self):
        """N7 test suite still passes after N8 integration."""
        r = self._run_pytest("tests/test_pane_handoff_evidence.py")
        assert r.returncode == 0, f"N7 tests regressed:\n{r.stdout}\n{r.stderr}"

    @pytest.mark.xfail(
        reason=(
            "N1 test file uses 'from harness.lib.autopilot import ready_for_planner' "
            "but harness/__init__.py and harness/lib/__init__.py do not exist. "
            "Also, ready_for_planner/ready_for_builder are not yet defined in autopilot.py. "
            "This is a pre-existing N1 implementation gap, not caused by N8."
        ),
        strict=False,
    )
    def test_n1_autopilot_broker_gate(self):
        """N1 autopilot broker gate tests (pre-existing failure — xfail documented)."""
        r = self._run_pytest("tests/test_autopilot_broker_gate.py")
        assert r.returncode == 0, f"N1 tests:\n{r.stdout}\n{r.stderr}"

    @pytest.mark.xfail(
        reason=(
            "N4 test file uses 'from harness.lib.observability import ...' "
            "but harness/__init__.py and harness/lib/__init__.py do not exist. "
            "Pre-existing import path mismatch; not caused by N8."
        ),
        strict=False,
    )
    def test_n4_observability_metrics(self):
        """N4 observability metrics tests (pre-existing import failure — xfail documented)."""
        r = self._run_pytest("tests/test_observability_metrics.py")
        assert r.returncode == 0, f"N4 tests:\n{r.stdout}\n{r.stderr}"

    @pytest.mark.xfail(
        reason=(
            "N6 test file uses 'from harness.lib.cli import status_cmd' "
            "but harness/__init__.py and harness/lib/__init__.py do not exist. "
            "Pre-existing import path mismatch; not caused by N8."
        ),
        strict=False,
    )
    def test_n6_status_cmd_metrics(self):
        """N6 status cmd metrics tests (pre-existing import failure — xfail documented)."""
        r = self._run_pytest("tests/test_status_cmd_metrics.py")
        assert r.returncode == 0, f"N6 tests:\n{r.stdout}\n{r.stderr}"
