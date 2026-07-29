"""Integrity checks for the reviewed Phase 22 atomic execution matrix.

These tests validate traceability data only. They are deliberately excluded
from feature-coverage counts and never substitute for product behavior tests.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MATRIX = json.loads((HERE / "atomic_feature_matrix.json").read_text(encoding="utf-8"))
INVENTORY = json.loads((HERE / "atomic_test_inventory.json").read_text(encoding="utf-8"))
RESULTS = json.loads((HERE / "atomic_test_run_results.json").read_text(encoding="utf-8"))


def _recompute_counts(payload: dict) -> dict:
    rows = payload["atomic_features"]
    return {
        "test_generation_status": Counter(row["test_generation_status"] for row in rows),
        "coverage_relationship": Counter(row["coverage_relationship"] for row in rows),
        "current_result": Counter(row["current_result"] for row in rows),
        "implementation_status": Counter(row["implementation_status"] for row in rows),
        "l2_atomic_rollup_status": Counter(row["atomic_rollup_status"] for row in payload["l2_summary"]),
    }


def test_atomic_matrix_has_exact_counts_and_unique_rows() -> None:
    rows = MATRIX["atomic_features"]
    l2_summary = MATRIX["l2_summary"]

    assert MATRIX["counts"]["l2_features"] == 142
    assert len(l2_summary) == 142
    assert len(rows) == MATRIX["counts"]["reviewed_atomic_features"] == 1502
    assert len({row["atomic_feature_id"] for row in rows}) == len(rows)
    assert len({(row["sheet"], row["level_2_feature"]) for row in rows}) == 142
    assert MATRIX["counts"]["net_rows_removed"] == (
        MATRIX["counts"]["historical_atomic_rows"] - MATRIX["counts"]["reviewed_atomic_features"]
    )


def test_atomic_status_counts_are_reconciled_from_rows() -> None:
    actual = _recompute_counts(MATRIX)
    assert sum(actual["test_generation_status"].values()) == 1502
    assert sum(actual["coverage_relationship"].values()) == 1502
    assert sum(actual["current_result"].values()) == 1502
    assert sum(actual["implementation_status"].values()) == 1502
    assert sum(actual["l2_atomic_rollup_status"].values()) == 142

    assert dict(sorted(MATRIX["counts"]["test_generation_status"].items())) == dict(
        sorted(actual["test_generation_status"].items())
    )
    assert dict(sorted(MATRIX["counts"]["implementation_status"].items())) == dict(
        sorted(actual["implementation_status"].items())
    )
    assert dict(sorted(MATRIX["counts"]["l2_atomic_rollup_status"].items())) == dict(
        sorted(actual["l2_atomic_rollup_status"].items())
    )


def test_atomic_rows_have_explicit_generation_and_coverage_states() -> None:
    allowed_generation = {
        "TAGGED_NOT_GENERATED_MANUAL_ORACLE",
        "MANUAL_ORACLE_REQUIRED",
        "CONFIG_RESOLVED_NEEDS_EXACT_BINDING",
        "CONFIG_RESOLVED_RELATED_SUITE_FAILED",
        "ATOMIC_BINDING_GAP",
        "PLATFORM_OR_HARDWARE_REQUIRED",
        "BLOCKED_NOT_IMPLEMENTED",
        "REUSED_L2_REPRESENTATIVE_EXECUTABLE",
        "REUSED_EXISTING_EXECUTABLE",
        "GENERATED_EXECUTABLE",
    }
    allowed_coverage = {
        "UNRESOLVED",
        "RELATED_SUITE_EVIDENCE_ONLY",
        "DIRECT",
        "SHARED_DIRECT",
        "PLATFORM_GATED",
        "RELATED_SUITE_FAILED_NOT_ATOMIC",
        "CURRENT_IMPLEMENTATION_BOUNDARY",
        "UNRESOLVED_ATOMIC_BINDING",
        "MANUAL_ORACLE_REQUIRED",
    }
    for row in MATRIX["atomic_features"]:
        assert row["test_generation_status"] in allowed_generation
        assert row["coverage_relationship"] in allowed_coverage


def test_bound_or_result_rows_have_expected_inventory_fields() -> None:
    rows = MATRIX["atomic_features"]
    recorded = {item["selector"]: item["result"] for item in RESULTS["results"]}

    for row in rows:
        generation = row["test_generation_status"]
        coverage = row["coverage_relationship"]
        result = row["current_result"]

        if generation in {"REUSED_EXISTING_EXECUTABLE", "REUSED_L2_REPRESENTATIVE_EXECUTABLE", "GENERATED_EXECUTABLE"}:
            assert row["test_binding_id"] and row["test_binding_id"].startswith("P22-ATB-")
            assert row["test_selector"] and row["test_file"]
            assert row["runner"] and row["runner_command"], row["atomic_feature_id"]
            if coverage in {"DIRECT", "SHARED_DIRECT"}:
                assert row["test_selector"], row["atomic_feature_id"]

        if result in {"PASS", "FAIL"}:
            if row["test_selector"] in recorded:
                assert recorded[row["test_selector"]] == result, row["atomic_feature_id"]
            assert row["test_file"] is not None
            assert row["runner"] is not None
            assert row["runner_command"], row["atomic_feature_id"]

        if generation == "MANUAL_ORACLE_REQUIRED":
            assert row["current_result"] == "MANUAL_ORACLE_REQUIRED"
            assert row["coverage_relationship"] == "MANUAL_ORACLE_REQUIRED"
            assert row["test_selector"] is None

            if coverage == "PLATFORM_GATED":
                assert row["test_generation_status"] == "PLATFORM_OR_HARDWARE_REQUIRED"
                assert row["current_result"] == "BLOCKED_PLATFORM"
                assert row["current_result"] != "UNRESOLVED"
                assert row["blocker_or_notes"], row["atomic_feature_id"]
                notes = row["blocker_or_notes"].lower()
                assert any(
                    token in notes
                    for token in ("windows", "macos", "linux", "ubuntu", "wsl", "ios", "android", "cuda", "gpu", "hardware", "platform", "session", "provider", "resource")
                )

        if coverage in {
            "UNRESOLVED",
            "UNRESOLVED_ATOMIC_BINDING",
            "RELATED_SUITE_EVIDENCE_ONLY",
            "RELATED_SUITE_FAILED_NOT_ATOMIC",
            "PLATFORM_GATED",
            "CURRENT_IMPLEMENTATION_BOUNDARY",
            "MANUAL_ORACLE_REQUIRED",
            "CONFIG_RESOLVED_NEEDS_EXACT_BINDING",
        }:
            if row["current_result"] in {"PASS", "FAIL"}:
                raise AssertionError(f"Pass/fail states must not be unresolved: {row['atomic_feature_id']}")

        if generation == "BLOCKED_NOT_IMPLEMENTED":
            assert row["current_result"] in {"BLOCKED_IMPLEMENTATION", "BLOCKED_NOT_IMPLEMENTED"}
            if row["current_result"] == "BLOCKED_NOT_IMPLEMENTED":
                assert row["coverage_relationship"] == "CURRENT_IMPLEMENTATION_BOUNDARY"

        if row["current_result"] == "PASS":
            assert row["test_generation_status"] in {"REUSED_EXISTING_EXECUTABLE", "REUSED_L2_REPRESENTATIVE_EXECUTABLE", "GENERATED_EXECUTABLE"}
            assert row["coverage_relationship"] in {"DIRECT", "SHARED_DIRECT"}
            assert row["test_selector"] is not None

        if row["current_result"] in {"NOT_RUN", "RELATED_SUITE_FAILED", "NOT_RUN_ATOMIC", "MANUAL_ORACLE_REQUIRED", "BLOCKED_PLATFORM", "BLOCKED_IMPLEMENTATION", "BLOCKED_NOT_IMPLEMENTED"}:
            if row["coverage_relationship"] in {"DIRECT", "SHARED_DIRECT"}:
                assert row["test_selector"] is not None, row["atomic_feature_id"]


def test_l2_rollup_is_strict_and_reconciled_from_rows() -> None:
    rows_by_l2: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in MATRIX["atomic_features"]:
        rows_by_l2[(row["sheet"], row["level_2_feature"])] = rows_by_l2[(row["sheet"], row["level_2_feature"])] + [row]

    summaries = {
        (row["sheet"], row["level_2_feature"]): row
        for row in MATRIX["l2_summary"]
    }

    for key, rows in rows_by_l2.items():
        summary = summaries[key]
        assert len(rows) == summary["reviewed_atomic_features"]

        if any(r["current_result"] == "FAIL" for r in rows):
            expected = "FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED"
        elif any(r["implementation_status"] == "NOT_IMPLEMENTED" for r in rows):
            expected = "FUNCTION_NOT_IMPLEMENTED_TEST_BLOCKED"
        elif any(r["current_result"] == "NOT_RUN" for r in rows):
            expected = "IMPLEMENTED_TEST_GAP_BLOCKED"
        else:
            expected = "FUNCTION_IMPLEMENTED_ALL_ATOMIC_TESTS_PASSED"

        assert summary["atomic_rollup_status"] == expected

        if expected != "FUNCTION_IMPLEMENTED_ALL_ATOMIC_TESTS_PASSED":
            assert summary["executable_bound"] == sum(bool(r["test_selector"]) for r in rows)


def test_l2_summary_counts_match_atomic_rows() -> None:
    rows = MATRIX["atomic_features"]
    summary_counts = Counter((row["sheet"], row["level_2_feature"]) for row in rows)

    observed = Counter((row["sheet"], row["level_2_feature"]) for row in MATRIX["l2_summary"])
    for key in summary_counts:
        assert observed[key] == 1

    assert sum(item["reviewed_atomic_features"] for item in MATRIX["l2_summary"]) == len(rows)
    assert sum(item["historical_atomic_rows"] for item in MATRIX["l2_summary"]) == MATRIX["counts"]["historical_atomic_rows"]

    from collections import defaultdict

    rolled = Counter(item["atomic_rollup_status"] for item in MATRIX["l2_summary"])
    assert dict(sorted(rolled.items())) == dict(sorted(Counter(r["atomic_rollup_status"] for r in MATRIX["l2_summary"]).items()))
