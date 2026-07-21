"""Tests for autopilot.py broker coverage gate (S04 N1).

Acceptance:
  1. pytest 4 cases PASS
  2. SOLAR_BROKER_ENABLED=0 path identical to pre-S04 behavior
  3. broker_coverage uncontracted_action_count > 0 blocks ready_for_planner
"""

import ast
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

AUTOPILOT = Path(__file__).parent.parent / "lib" / "autopilot.py"


# ---------------------------------------------------------------------------
# Case 1: SOLAR_BROKER_ENABLED=0 short-circuits to legacy (LR-01)
# ---------------------------------------------------------------------------


class TestLegacyMode:
    def test_ready_for_planner_legacy(self):
        from harness.lib.autopilot import ready_for_planner
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "0"}):
            result = ready_for_planner()
        assert result["ready"] is True
        assert result["reason"] == "legacy_mode"
        assert result["broker_enabled"] is False

    def test_ready_for_builder_legacy(self):
        from harness.lib.autopilot import ready_for_builder
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "0"}):
            result = ready_for_builder()
        assert result["ready"] is True
        assert result["reason"] == "legacy_mode"
        assert result["broker_enabled"] is False


# ---------------------------------------------------------------------------
# Case 2: broker enabled + clean coverage → ready
# ---------------------------------------------------------------------------


class TestBrokerCoveragePass:
    def test_planner_clean_coverage(self):
        from harness.lib.autopilot import ready_for_planner
        coverage = {
            "uncontracted_action_count": 0,
            "unscoped_write_count": 0,
            "total_actions": 10,
            "contracted_actions": 10,
            "coverage_ratio": 1.0,
            "legacy_path_actions": 0,
            "by_kind": {},
            "health": "PASS",
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            result = ready_for_planner(coverage)
        assert result["ready"] is True
        assert result["broker_enabled"] is True

    def test_builder_clean_coverage(self):
        from harness.lib.autopilot import ready_for_builder
        coverage = {
            "uncontracted_action_count": 0,
            "unscoped_write_count": 0,
            "total_actions": 10,
            "contracted_actions": 10,
            "coverage_ratio": 1.0,
            "legacy_path_actions": 0,
            "by_kind": {},
            "health": "PASS",
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            result = ready_for_builder(coverage)
        assert result["ready"] is True
        assert result["broker_enabled"] is True

    def test_no_coverage_data_is_ready(self):
        from harness.lib.autopilot import ready_for_planner, ready_for_builder
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            assert ready_for_planner(None)["ready"] is True
            assert ready_for_builder(None)["ready"] is True


# ---------------------------------------------------------------------------
# Case 3: uncontracted_action_count > 0 blocks ready_for_planner
# ---------------------------------------------------------------------------


class TestUncontractedBlocks:
    def test_planner_uncontracted_blocks(self):
        from harness.lib.autopilot import ready_for_planner
        coverage = {
            "uncontracted_action_count": 3,
            "unscoped_write_count": 0,
            "total_actions": 10,
            "contracted_actions": 7,
            "coverage_ratio": 0.7,
            "legacy_path_actions": 0,
            "by_kind": {},
            "health": "FAIL",
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            result = ready_for_planner(coverage)
        assert result["ready"] is False
        assert "uncontracted_action_count=3" in result["reason"]
        assert result["uncontracted_action_count"] == 3

    def test_builder_uncontracted_blocks(self):
        from harness.lib.autopilot import ready_for_builder
        coverage = {
            "uncontracted_action_count": 2,
            "unscoped_write_count": 0,
            "total_actions": 5,
            "contracted_actions": 3,
            "coverage_ratio": 0.6,
            "legacy_path_actions": 0,
            "by_kind": {},
            "health": "FAIL",
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            result = ready_for_builder(coverage)
        assert result["ready"] is False
        assert "uncontracted_action_count=2" in result["reason"]

    def test_unscoped_write_count_blocks_planner(self):
        from harness.lib.autopilot import ready_for_planner
        coverage = {
            "uncontracted_action_count": 0,
            "unscoped_write_count": 1,
            "total_actions": 10,
            "contracted_actions": 10,
            "coverage_ratio": 1.0,
            "legacy_path_actions": 0,
            "by_kind": {},
            "health": "FAIL",
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            result = ready_for_planner(coverage)
        assert result["ready"] is False
        assert "unscoped_write_count=1" in result["reason"]

    def test_low_coverage_ratio_blocks_builder(self):
        from harness.lib.autopilot import ready_for_builder
        coverage = {
            "uncontracted_action_count": 0,
            "unscoped_write_count": 0,
            "total_actions": 10,
            "contracted_actions": 8,
            "coverage_ratio": 0.8,
            "legacy_path_actions": 0,
            "by_kind": {},
            "health": "DEGRADED",
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "1"}):
            result = ready_for_builder(coverage)
        assert result["ready"] is False
        assert "coverage_ratio=0.8" in result["reason"]


# ---------------------------------------------------------------------------
# Case 4: legacy path identical to pre-S04 behavior (diff test)
# ---------------------------------------------------------------------------


class TestLegacyDiff:
    def test_legacy_returns_same_with_or_without_coverage(self):
        """When broker disabled, coverage data must not change the result."""
        from harness.lib.autopilot import ready_for_planner, ready_for_builder
        bad_coverage = {
            "uncontracted_action_count": 999,
            "unscoped_write_count": 999,
            "total_actions": 0,
            "contracted_actions": 0,
            "coverage_ratio": 0.0,
            "legacy_path_actions": 0,
            "by_kind": {},
            "health": "FAIL",
        }
        with mock.patch.dict(os.environ, {"SOLAR_BROKER_ENABLED": "0"}):
            r1 = ready_for_planner()
            r2 = ready_for_planner(bad_coverage)
            r3 = ready_for_builder()
            r4 = ready_for_builder(bad_coverage)
        assert r1 == r2 == {"ready": True, "reason": "legacy_mode", "broker_enabled": False}
        assert r3 == r4 == {"ready": True, "reason": "legacy_mode", "broker_enabled": False}


# ---------------------------------------------------------------------------
# py_compile
# ---------------------------------------------------------------------------


class TestCompile:
    def test_py_compile_autopilot(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(AUTOPILOT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
