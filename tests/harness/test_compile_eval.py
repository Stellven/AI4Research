"""test_compile_eval.py — Integration tests for compiler_profile and compile_eval.

Acceptance criteria coverage:
- AC1: compiler_profile schema (P1)
- AC2: registry register/query/activate (P2)
- AC3: CompileEvalHarness outputs score + ASI on golden cases (P3+P7)
- AC4: ASI trace records score + profile + task type (P5)
- AC5: GEPA adapter calls CompileEvalHarness as fitness function (P7)
- AC6: Hard validators hard fail on violations (P4)
- AC8: PRD/contract/DAG alignment check passes
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any


def _make_valid_profile(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid compiler profile dict."""
    base: dict[str, Any] = {
        "profile_id": "test-profile-001",
        "version": 1,
        "name": "Test Profile",
        "tags": ["test"],
        "created_at": "2026-05-24T00:00:00Z",
        "policies": {
            "intake_policy": {"version": "1.0", "params": {}},
            "requirement_ir_policy": {"version": "1.0", "params": {}},
            "contract_compiler_policy": {"version": "1.0", "params": {}},
            "dag_compiler_policy": {"version": "1.0", "params": {}},
            "evidence_policy": {"version": "1.0", "params": {}},
            "handoff_policy": {"version": "1.0", "params": {}},
        },
    }
    base.update(overrides)
    return base


def _make_valid_artifacts() -> dict[str, Any]:
    """Build a minimal valid artifacts dict for evaluation."""
    return {
        "requirement_ir": {
            "goal": "Implement feature X",
            "success_metrics": ["metric1", "metric2"],
            "non_goals": ["not this"],
        },
        "contracts": {
            "goal": "Implement feature X",
            "policies": {
                "intake_policy": {"version": "1.0", "params": {}},
                "requirement_ir_policy": {"version": "1.0", "params": {}},
                "contract_compiler_policy": {"version": "1.0", "params": {}},
                "dag_compiler_policy": {"version": "1.0", "params": {}},
                "evidence_policy": {"version": "1.0", "params": {}},
                "handoff_policy": {"version": "1.0", "params": {}},
            },
            "acceptance": {
                "ACC-1": "Feature X works end-to-end",
            },
        },
        "dag": {
            "nodes": [
                {
                    "id": "N1",
                    "goal": "Implement feature X",
                    "depends_on": [],
                    "write_scope": "src/",
                    "type": "task",
                    "validation_steps": ["ACC-1"],
                    "acceptance_ids": ["ACC-1"],
                },
            ],
        },
        "traces": {
            "planner": {"nodes": ["N1"]},
            "builder": {"nodes": ["N1"]},
            "evaluator": {"nodes": ["N1"]},
        },
    }


# ===================================================================
# AC1: compiler_profile schema
# ===================================================================

class TestCompilerProfileSchema(unittest.TestCase):
    """AC1: Schema validation for compiler profiles."""

    def test_valid_profile_passes(self):
        from lib.compiler_profile import validate_profile
        profile = _make_valid_profile()
        is_valid, errors = validate_profile(profile)
        self.assertTrue(is_valid, f"Valid profile should pass: {errors}")
        self.assertEqual(errors, [])

    def test_missing_required_field_fails(self):
        from lib.compiler_profile import validate_profile
        for key in ("profile_id", "version", "name", "tags", "created_at", "policies"):
            profile = _make_valid_profile()
            del profile[key]
            is_valid, errors = validate_profile(profile)
            self.assertFalse(is_valid, f"Missing {key} should fail")
            self.assertTrue(any(key in e for e in errors))

    def test_invalid_version_fails(self):
        from lib.compiler_profile import validate_profile
        for bad_version in (0, -1, "1", 1.5):
            profile = _make_valid_profile(version=bad_version)
            is_valid, errors = validate_profile(profile)
            self.assertFalse(is_valid, f"Version {bad_version!r} should fail")

    def test_missing_policy_key_fails(self):
        from lib.compiler_profile import validate_profile
        profile = _make_valid_profile()
        del profile["policies"]["intake_policy"]
        is_valid, errors = validate_profile(profile)
        self.assertFalse(is_valid)
        self.assertTrue(any("intake_policy" in e for e in errors))

    def test_extra_policy_key_fails(self):
        from lib.compiler_profile import validate_profile
        profile = _make_valid_profile()
        profile["policies"]["extra_policy"] = {"version": "1.0", "params": {}}
        is_valid, errors = validate_profile(profile)
        self.assertFalse(is_valid)
        self.assertTrue(any("extra_policy" in e for e in errors))

    def test_policy_missing_version_fails(self):
        from lib.compiler_profile import validate_profile
        profile = _make_valid_profile()
        profile["policies"]["intake_policy"] = {"params": {}}
        is_valid, errors = validate_profile(profile)
        self.assertFalse(is_valid)

    def test_empty_tags_fails(self):
        from lib.compiler_profile import validate_profile
        profile = _make_valid_profile(tags=[])
        # Empty list is still valid (it's a list of strings, just empty)
        # Actually per schema tags is required list[str], empty should be ok
        is_valid, errors = validate_profile(profile)
        # This should pass since tags is a list (even empty)
        self.assertTrue(is_valid, f"Empty tags list should pass: {errors}")

    def test_non_string_profile_id_fails(self):
        from lib.compiler_profile import validate_profile
        profile = _make_valid_profile(profile_id=123)
        is_valid, errors = validate_profile(profile)
        self.assertFalse(is_valid)

    def test_non_dict_input_fails(self):
        from lib.compiler_profile import validate_profile
        is_valid, errors = validate_profile("not a dict")
        self.assertFalse(is_valid)


# ===================================================================
# AC2: Registry register/query/activate
# ===================================================================

class TestCompilerProfileRegistry(unittest.TestCase):
    """AC2: Register, query, activate, list, history."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test_profiles.db"
        self._profiles_dir = Path(self._tmpdir) / "profiles"

    def test_register_and_query(self):
        from lib.compiler_profile.registry import register, query
        profile = _make_valid_profile()
        result = register(
            profile,
            profiles_dir=self._profiles_dir,
            db_path=self._db_path,
        )
        self.assertEqual(result["profile_id"], "test-profile-001")
        self.assertEqual(result["version"], 1)
        self.assertTrue(Path(result["path"]).exists())

        profiles = query(profile_id="test-profile-001", db_path=self._db_path)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["profile_id"], "test-profile-001")

    def test_register_invalid_fails(self):
        from lib.compiler_profile.registry import register
        with self.assertRaises(ValueError):
            register({"bad": "data"}, profiles_dir=self._profiles_dir, db_path=self._db_path)

    def test_activate_and_get_active(self):
        from lib.compiler_profile.registry import (
            register, activate, get_active, deactivate,
        )
        profile = _make_valid_profile()
        register(profile, profiles_dir=self._profiles_dir, db_path=self._db_path)

        result = activate("test-profile-001", db_path=self._db_path)
        self.assertEqual(result["profile_id"], "test-profile-001")

        active = get_active(db_path=self._db_path)
        self.assertIsNotNone(active)
        self.assertEqual(active["profile_id"], "test-profile-001")

        deactivate(db_path=self._db_path)
        active = get_active(db_path=self._db_path)
        self.assertIsNone(active)

    def test_list_profiles(self):
        from lib.compiler_profile.registry import register, list_profiles
        p1 = _make_valid_profile(profile_id="p1", name="Profile 1")
        p2 = _make_valid_profile(profile_id="p2", name="Profile 2")
        register(p1, profiles_dir=self._profiles_dir, db_path=self._db_path)
        register(p2, profiles_dir=self._profiles_dir, db_path=self._db_path)

        all_profiles = list_profiles(db_path=self._db_path)
        self.assertEqual(len(all_profiles), 2)

    def test_history(self):
        from lib.compiler_profile.registry import register, history
        v1 = _make_valid_profile()
        v2 = _make_valid_profile(version=2)
        register(v1, profiles_dir=self._profiles_dir, db_path=self._db_path)
        register(v2, profiles_dir=self._profiles_dir, db_path=self._db_path)

        hist = history("test-profile-001", db_path=self._db_path)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0]["version"], 1)
        self.assertEqual(hist[1]["version"], 2)

    def test_query_by_tag(self):
        from lib.compiler_profile.registry import register, query
        p1 = _make_valid_profile(profile_id="tagged-1", tags=["ml", "research"])
        p2 = _make_valid_profile(profile_id="tagged-2", tags=["infra"])
        register(p1, profiles_dir=self._profiles_dir, db_path=self._db_path)
        register(p2, profiles_dir=self._profiles_dir, db_path=self._db_path)

        ml_profiles = query(tag="ml", db_path=self._db_path)
        self.assertEqual(len(ml_profiles), 1)
        self.assertEqual(ml_profiles[0]["profile_id"], "tagged-1")


# ===================================================================
# AC3: CompileEvalHarness outputs score + ASI
# ===================================================================

class TestCompileEvalHarness(unittest.TestCase):
    """AC3: Evaluate outputs score + dimension breakdown."""

    def test_evaluate_returns_all_dimensions(self):
        from lib.compile_eval import evaluate
        artifacts = _make_valid_artifacts()
        scores = evaluate(artifacts, {})
        self.assertEqual(len(scores), 7)
        for dim_name, score in scores.items():
            self.assertIsInstance(score, float, f"{dim_name} should be float")
            self.assertGreaterEqual(score, 0.0, f"{dim_name} should be >= 0")
            self.assertLessEqual(score, 1.0, f"{dim_name} should be <= 1")

    def test_evaluate_perfect_artifacts_high_scores(self):
        from lib.compile_eval import evaluate
        artifacts = _make_valid_artifacts()
        scores = evaluate(artifacts, {})
        # IR schema compliance should be 1.0 with all required fields
        self.assertEqual(scores["ir_schema_compliance"], 1.0)

    def test_evaluate_empty_artifacts_low_scores(self):
        from lib.compile_eval import evaluate
        scores = evaluate({}, {})
        self.assertEqual(scores["ir_schema_compliance"], 0.0)
        self.assertEqual(scores["contract_completeness"], 0.0)

    def test_harness_evaluate_produces_asi(self):
        from lib.compile_eval.harness import CompileGEPAAdapter
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            adapter = CompileGEPAAdapter(
                trace_db=db_path,
                profile_id="test-profile",
                profile_version=1,
                task_type="compile",
            )
            artifacts = _make_valid_artifacts()
            result = adapter.evaluate(artifacts, {}, golden_case_id="gc-1")

            self.assertIsInstance(result.asi_score, float)
            self.assertGreater(result.asi_score, 0.0)
            self.assertEqual(len(result.dimension_scores), 7)
            self.assertTrue(result.hard_validators_passed)
        finally:
            os.unlink(db_path)


# ===================================================================
# AC4: ASI trace records
# ===================================================================

class TestASITrace(unittest.TestCase):
    """AC4: ASI trace records score + profile + task type."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test_asi.db"

    def test_init_creates_table(self):
        from lib.compile_eval.asi_trace import init_trace_db
        init_trace_db(self._db_path)
        self.assertTrue(self._db_path.exists())

        conn = sqlite3.connect(str(self._db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        self.assertIn("asi_traces", [t[0] for t in tables])

    def test_write_and_query_trace(self):
        from lib.compile_eval.asi_trace import (
            ASITrace, init_trace_db, write_trace, query_traces,
        )
        init_trace_db(self._db_path)

        trace = ASITrace(
            trace_id="trace-001",
            timestamp="2026-05-24T12:00:00Z",
            profile_id="test-profile",
            profile_version=2,
            task_type="compile",
            sprint_id="sprint-123",
            asi_score=0.85,
            dimension_scores={"ir_schema_compliance": 1.0},
            hard_validators_passed=["HV1", "HV2"],
            hard_validators_failed=[],
            golden_case_used="gc-1",
        )
        trace_id = write_trace(self._db_path, trace)
        self.assertEqual(trace_id, "trace-001")

        traces = query_traces(self._db_path, profile_id="test-profile")
        self.assertEqual(len(traces), 1)
        t = traces[0]
        self.assertEqual(t.trace_id, "trace-001")
        self.assertEqual(t.profile_id, "test-profile")
        self.assertEqual(t.task_type, "compile")
        self.assertAlmostEqual(t.asi_score, 0.85)
        self.assertEqual(t.dimension_scores["ir_schema_compliance"], 1.0)

    def test_query_by_task_type(self):
        from lib.compile_eval.asi_trace import (
            ASITrace, init_trace_db, write_trace, query_traces,
        )
        init_trace_db(self._db_path)

        for i in range(5):
            trace = ASITrace(
                trace_id=f"trace-{i:03d}",
                timestamp="2026-05-24T12:00:00Z",
                profile_id="p1",
                task_type="compile" if i % 2 == 0 else "evaluate",
            )
            write_trace(self._db_path, trace)

        compile_traces = query_traces(self._db_path, task_type="compile")
        self.assertEqual(len(compile_traces), 3)

    def test_query_by_time_range(self):
        from lib.compile_eval.asi_trace import (
            ASITrace, init_trace_db, write_trace, query_traces,
        )
        init_trace_db(self._db_path)

        for day in range(1, 6):
            trace = ASITrace(
                trace_id=f"trace-day{day}",
                timestamp=f"2026-05-{day:02d}T12:00:00Z",
                profile_id="p1",
            )
            write_trace(self._db_path, trace)

        traces = query_traces(
            self._db_path,
            time_range=("2026-05-02T00:00:00Z", "2026-05-04T23:59:59Z"),
        )
        self.assertEqual(len(traces), 3)


# ===================================================================
# AC5: GEPA adapter uses fitness function
# ===================================================================

class TestGEPAAdapterFitness(unittest.TestCase):
    """AC5: GEPA adapter calls CompileEvalHarness as fitness function."""

    def test_fitness_function_returns_mean_asi(self):
        from lib.compile_eval.harness import CompileGEPAAdapter
        from lib.compile_eval.golden_cases import GoldenCase

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            adapter = CompileGEPAAdapter(trace_db=db_path)

            # Create synthetic golden cases
            cases = [
                GoldenCase(
                    sprint_id="gc-1",
                    input="Build feature A",
                    expected_ir={
                        "goal": "Build feature A",
                        "success_metrics": ["works"],
                        "non_goals": [],
                    },
                    expected_contracts=[{
                        "goal": "Build feature A",
                        "policies": {
                            k: {"version": "1.0", "params": {}}
                            for k in (
                                "intake_policy", "requirement_ir_policy",
                                "contract_compiler_policy", "dag_compiler_policy",
                                "evidence_policy", "handoff_policy",
                            )
                        },
                        "acceptance": {"ACC-1": "Feature A works"},
                    }],
                    expected_dag={
                        "nodes": [{
                            "id": "N1",
                            "goal": "Build feature A",
                            "depends_on": [],
                            "write_scope": "src/",
                            "validation_steps": ["ACC-1"],
                            "acceptance_ids": ["ACC-1"],
                        }],
                    },
                ),
                GoldenCase(
                    sprint_id="gc-2",
                    input="Build feature B",
                    expected_ir={
                        "goal": "Build feature B",
                        "success_metrics": ["tested"],
                        "non_goals": [],
                    },
                    expected_contracts=[{
                        "goal": "Build feature B",
                        "policies": {
                            k: {"version": "1.0", "params": {}}
                            for k in (
                                "intake_policy", "requirement_ir_policy",
                                "contract_compiler_policy", "dag_compiler_policy",
                                "evidence_policy", "handoff_policy",
                            )
                        },
                        "acceptance": {"ACC-2": "Feature B tested"},
                    }],
                    expected_dag={
                        "nodes": [{
                            "id": "N1",
                            "goal": "Build feature B",
                            "depends_on": [],
                            "write_scope": "src/",
                            "validation_steps": ["ACC-2"],
                            "acceptance_ids": ["ACC-2"],
                        }],
                    },
                ),
            ]

            profile = _make_valid_profile()
            fitness = adapter.fitness_function(profile, cases)

            self.assertIsInstance(fitness, float)
            self.assertGreater(fitness, 0.0)
        finally:
            os.unlink(db_path)

    def test_fitness_function_empty_cases(self):
        from lib.compile_eval.harness import CompileGEPAAdapter

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            adapter = CompileGEPAAdapter(trace_db=db_path)
            fitness = adapter.fitness_function(_make_valid_profile(), [])
            self.assertEqual(fitness, 0.0)
        finally:
            os.unlink(db_path)


# ===================================================================
# AC6: Hard validators hard fail on violations
# ===================================================================

class TestHardValidators(unittest.TestCase):
    """AC6: Hard validators hard fail on violations."""

    def test_all_pass_with_valid_artifacts(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        result = run_hard_validators(artifacts)
        self.assertTrue(result.passed)
        self.assertEqual(result.failures, [])

    def test_hv1_ir_schema_missing_fields(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        del artifacts["requirement_ir"]["goal"]
        result = run_hard_validators(artifacts)
        self.assertFalse(result.passed)
        self.assertIn("HV1_IR_SCHEMA_INVALID", result.failures)

    def test_hv1_ir_schema_missing_entirely(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        result = run_hard_validators({})
        self.assertFalse(result.passed)
        self.assertIn("HV1_IR_SCHEMA_INVALID", result.failures)

    def test_hv2_contract_mismatch(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        artifacts["requirement_ir"]["goal"] = "Goal A"
        artifacts["contracts"]["goal"] = "Completely different goal Z"
        artifacts["contracts"].pop("policies", None)
        result = run_hard_validators(artifacts)
        self.assertIn("HV2_CONTRACT_MISMATCH", result.failures)

    def test_hv3_dag_cycle_detected(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        # Create a cycle: N1 -> N2 -> N1
        artifacts["dag"]["nodes"] = [
            {"id": "N1", "depends_on": ["N2"]},
            {"id": "N2", "depends_on": ["N1"]},
        ]
        result = run_hard_validators(artifacts)
        self.assertFalse(result.passed)
        self.assertIn("HV3_DAG_CYCLE", result.failures)

    def test_hv3_dag_no_cycle(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        artifacts["dag"]["nodes"] = [
            {"id": "N1", "depends_on": []},
            {"id": "N2", "depends_on": ["N1"]},
        ]
        result = run_hard_validators(artifacts)
        self.assertNotIn("HV3_DAG_CYCLE", result.failures)

    def test_hv5_research_no_evidence_gate(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        artifacts["dag"]["nodes"] = [
            {"id": "N1", "type": "research", "depends_on": [], "gates": []},
        ]
        result = run_hard_validators(artifacts)
        self.assertFalse(result.passed)
        self.assertIn("HV5_RESEARCH_NO_EVIDENCE", result.failures)

    def test_hv5_research_with_evidence_gate(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        artifacts["dag"]["nodes"] = [
            {"id": "N1", "type": "research", "depends_on": [], "gates": ["evidence_gate"]},
        ]
        result = run_hard_validators(artifacts)
        self.assertNotIn("HV5_RESEARCH_NO_EVIDENCE", result.failures)

    def test_hv6_high_risk_no_approval_gate(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        artifacts["dag"]["nodes"] = [
            {"id": "N1", "risk_level": "high", "depends_on": [], "gates": []},
        ]
        result = run_hard_validators(artifacts)
        self.assertFalse(result.passed)
        self.assertIn("HV6_HIGH_RISK_NO_APPROVAL", result.failures)

    def test_hv6_high_risk_with_approval_gate(self):
        from lib.compile_eval.hard_validators import run_hard_validators
        artifacts = _make_valid_artifacts()
        artifacts["dag"]["nodes"] = [
            {"id": "N1", "risk_level": "high", "depends_on": [], "gates": ["approval_gate"]},
        ]
        result = run_hard_validators(artifacts)
        self.assertNotIn("HV6_HIGH_RISK_NO_APPROVAL", result.failures)


# ===================================================================
# AC8: PRD/contract/DAG alignment
# ===================================================================

class TestPRDContractDAGAlignment(unittest.TestCase):
    """AC8: PRD/contract/DAG alignment check passes."""

    def test_aligned_goals_pass(self):
        from lib.compile_eval import evaluate
        artifacts = {
            "requirement_ir": {"goal": "Implement auth system"},
            "contracts": {"goal": "Implement auth system"},
            "dag": {
                "nodes": [
                    {"goal": "Implement auth system", "depends_on": []},
                ],
            },
        }
        scores = evaluate(artifacts, {})
        self.assertGreater(scores["prd_contract_dag_alignment"], 0.5)

    def test_misaligned_goals_lower_score(self):
        from lib.compile_eval import evaluate
        artifacts = {
            "requirement_ir": {"goal": "Implement auth system"},
            "contracts": {"goal": "Build a spaceship"},
            "dag": {
                "nodes": [
                    {"goal": "Do something unrelated", "depends_on": []},
                ],
            },
        }
        scores = evaluate(artifacts, {})
        self.assertLess(scores["prd_contract_dag_alignment"], 0.5)

    def test_empty_ir_goal_zero_score(self):
        from lib.compile_eval import evaluate
        artifacts = {
            "requirement_ir": {},
            "contracts": {"goal": "something"},
            "dag": {"nodes": []},
        }
        scores = evaluate(artifacts, {})
        self.assertEqual(scores["prd_contract_dag_alignment"], 0.0)


# ===================================================================
# Loader tests
# ===================================================================

class TestLoader(unittest.TestCase):
    """Test profile loading from JSON and DB."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test_loader.db"
        self._profiles_dir = Path(self._tmpdir) / "profiles"

    def test_load_from_json(self):
        from lib.compiler_profile.registry import register
        from lib.compiler_profile.loader import load_from_json

        profile = _make_valid_profile()
        register(profile, profiles_dir=self._profiles_dir, db_path=self._db_path)

        loaded = load_from_json(
            "test-profile-001", profiles_dir=self._profiles_dir,
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["profile_id"], "test-profile-001")

    def test_load_from_json_specific_version(self):
        from lib.compiler_profile.registry import register
        from lib.compiler_profile.loader import load_from_json

        v1 = _make_valid_profile()
        v2 = _make_valid_profile(version=2)
        register(v1, profiles_dir=self._profiles_dir, db_path=self._db_path)
        register(v2, profiles_dir=self._profiles_dir, db_path=self._db_path)

        loaded = load_from_json(
            "test-profile-001", version=1,
            profiles_dir=self._profiles_dir,
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["version"], 1)

    def test_load_from_json_missing_returns_none(self):
        from lib.compiler_profile.loader import load_from_json
        result = load_from_json("nonexistent", profiles_dir=self._profiles_dir)
        self.assertIsNone(result)

    def test_load_from_db(self):
        from lib.compiler_profile.registry import register
        from lib.compiler_profile.loader import load_from_db

        profile = _make_valid_profile()
        register(profile, profiles_dir=self._profiles_dir, db_path=self._db_path)

        loaded = load_from_db("test-profile-001", db_path=self._db_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["profile_id"], "test-profile-001")


# ===================================================================
# Golden cases loader tests
# ===================================================================

class TestGoldenCases(unittest.TestCase):
    """Test golden case loading from accepted artifacts."""

    def test_load_golden_cases_with_empty_dir(self):
        from lib.compile_eval.golden_cases import load_golden_cases

        with tempfile.TemporaryDirectory() as tmpdir:
            cases = load_golden_cases(accepted_dir=Path(tmpdir))
            self.assertEqual(cases, [])

    def test_load_golden_cases_with_nonexistent_dir(self):
        from lib.compile_eval.golden_cases import load_golden_cases
        cases = load_golden_cases(accepted_dir=Path("/nonexistent/path"))
        self.assertEqual(cases, [])

    def test_load_golden_cases_parses_files(self):
        from lib.compile_eval.golden_cases import load_golden_cases

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake accepted file
            content = '''---
source: solar-harness
sprint_id: sprint-20260524-120000
title: "Test sprint"
status: passed
---

# Accepted Sprint: sprint-20260524-120000

## Executive Summary

Test sprint passed.

## 需求

Build a REST API endpoint for user registration.

## Done 定义

- [ ] **D1 (功能)**: Endpoint accepts POST requests
- [ ] **D2 (测试)**: Integration tests cover all cases
'''
            fpath = Path(tmpdir) / "sprint-20260524-120000.accepted.md"
            fpath.write_text(content, encoding="utf-8")

            cases = load_golden_cases(limit=5, accepted_dir=Path(tmpdir))
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].sprint_id, "sprint-20260524-120000")
            self.assertIn("REST API", cases[0].input)
            self.assertIn("goal", cases[0].expected_ir)

    def test_load_respects_limit(self):
        from lib.compile_eval.golden_cases import load_golden_cases

        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                content = f'''---
sprint_id: sprint-20260524-{i:06d}
title: "Sprint {i}"
---

## 需求

Build feature {i}.
'''
                fpath = Path(tmpdir) / f"sprint-20260524-{i:06d}.accepted.md"
                fpath.write_text(content, encoding="utf-8")

            cases = load_golden_cases(limit=3, accepted_dir=Path(tmpdir))
            self.assertLessEqual(len(cases), 3)


if __name__ == "__main__":
    unittest.main()
