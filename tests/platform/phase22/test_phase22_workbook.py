"""Integrity checks for the Phase 22 generated workbook artifact."""
from __future__ import annotations

from collections import Counter
import sys
from pathlib import Path
import subprocess
import shutil
import pytest

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase22_workbook_validation import (
    parse_workbook,
    _value_for_cell,
    read_matrix_counts,
    summarize_feature_sheets,
)


HERE = Path(__file__).resolve().parent
ROOT = HERE.resolve().parents[3]
MATRIX_PATH = HERE / "atomic_feature_matrix.json"
WORKBOOK_PATH = ROOT / ".codex-tmp/phase22-i1/phase-22-test-report.generated.xlsx"

REQUIRED_SHEETS = [
    "Workflow Features",
    "Foundation Features",
    "Vertical Features",
    "Coverage Summary",
]
FEATURE_SHEETS = ["Workflow Features", "Foundation Features", "Vertical Features"]


def _build_workbook_if_possible() -> None:
    if WORKBOOK_PATH.exists():
        return

    node = shutil.which("node")
    if not node:
        pytest.skip(
            "Workbook output is absent and Node.js is unavailable in this environment. "
            "Re-run with node installed to build and validate the generated workbook."
        )

    command = [
        node,
        str(ROOT / "tests/platform/phase22/build_phase22_workbook.mjs"),
        f"--matrix={MATRIX_PATH}",
        f"--source={ROOT / 'docs/integrations/autosci/.codex-tmp-phase22-copy.xlsx'}",
        f"--output={WORKBOOK_PATH}",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"Workbook builder failed ({completed.returncode}): {completed.stderr or completed.stdout}")


def test_phase22_workbook_output_exists() -> None:
    _build_workbook_if_possible()
    assert WORKBOOK_PATH.is_file()
    assert WORKBOOK_PATH.suffix.lower() == ".xlsx"


def test_phase22_workbook_has_expected_sheets_and_reimport_shape() -> None:
    _build_workbook_if_possible()
    workbook = parse_workbook(WORKBOOK_PATH)
    assert workbook["sheet_names"] == REQUIRED_SHEETS

    summary = summarize_feature_sheets(
        workbook["sheet_rows"],
        workbook["shared_strings"],
        FEATURE_SHEETS,
    )

    assert summary["total_atomic_rows"] == 1502
    assert summary["unique_l2_count"] == 142
    assert summary["total_atomic_rows"] == len(summary["atomic_feature_ids"])

    matrix_counts = read_matrix_counts(MATRIX_PATH)
    assert summary["total_atomic_rows"] == matrix_counts["counts"]["rows"]
    assert len(summary["atomic_feature_ids"]) == len(set(summary["atomic_feature_ids"]))
    assert summary["unique_l2_count"] == matrix_counts["payload"]["counts"]["l2_features"]
    assert summary["l2_feature_counts"] == Counter(
        {
            row["level_2_feature"]: row["reviewed_atomic_features"]
            for row in matrix_counts["payload"]["l2_summary"]
        }
    )


def test_phase22_workbook_summary_matches_matrix_counts() -> None:
    _build_workbook_if_possible()
    workbook = parse_workbook(WORKBOOK_PATH)
    summary_sheet_name = "Coverage Summary"
    if summary_sheet_name not in workbook["sheet_rows"]:
        raise AssertionError("Coverage Summary sheet is missing from generated workbook.")

    shared_strings = workbook["shared_strings"]
    sheet_rows = workbook["sheet_rows"][summary_sheet_name]
    matrix = read_matrix_counts(MATRIX_PATH)

    def value(row: int, col: int) -> int:
        text = sheet_rows.get(row, {}).get(col)
        if text is None:
            raise AssertionError(f"Missing cell R{row}C{col} in Coverage Summary.")
        return int(_value_for_cell(text, shared_strings) or 0)

    assert value(3, 1) == matrix["counts"]["l2_features"]
    assert value(4, 1) == 2047
    assert value(5, 1) == matrix["counts"]["reviewed_atomic"]
    assert value(6, 1) == matrix["counts"]["net_rows_removed"]
    assert value(7, 1) == matrix["counts"]["test_generation"].get("GENERATED_EXECUTABLE", 0)
    assert value(8, 1) == matrix["counts"]["test_generation"].get("REUSED_EXISTING_EXECUTABLE", 0)
    assert value(9, 1) == (
        matrix["counts"]["test_generation"].get("REUSED_L2_REPRESENTATIVE_EXECUTABLE", 0)
    )
    manual_total = (
        matrix["counts"]["test_generation"].get("MANUAL_ORACLE_REQUIRED", 0)
        + matrix["counts"]["test_generation"].get("TAGGED_NOT_GENERATED_MANUAL_ORACLE", 0)
    )
    assert value(10, 1) == manual_total
    assert value(11, 1) == matrix["counts"]["test_generation"].get("PLATFORM_OR_HARDWARE_REQUIRED", 0)
    assert value(12, 1) == matrix["counts"]["test_generation"].get("BLOCKED_NOT_IMPLEMENTED", 0)
    assert value(13, 1) == matrix["counts"]["current_result"].get("PASS", 0)
    assert value(14, 1) == matrix["counts"]["current_result"].get("FAIL", 0)
    assert value(15, 1) == matrix["counts"]["l2_rollup"].get("FUNCTION_IMPLEMENTED_ALL_ATOMIC_TESTS_PASSED", 0)
    assert value(16, 1) == matrix["counts"]["l2_rollup"].get("FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED", 0)
    assert value(17, 1) == matrix["counts"]["l2_rollup"].get("FUNCTION_NOT_IMPLEMENTED_TEST_BLOCKED", 0)
    assert value(18, 1) == matrix["counts"]["l2_rollup"].get("IMPLEMENTED_TEST_GAP_BLOCKED", 0)
    assert value(29, 1) == 0


def test_phase22_workbook_formula_errors_and_opc_sanity() -> None:
    _build_workbook_if_possible()
    workbook = parse_workbook(WORKBOOK_PATH)
    assert not workbook["formula_errors"]
    assert len(workbook["sheet_names"]) == 4
    assert sorted(workbook["sheet_names"]) == sorted(REQUIRED_SHEETS)
    for sheet_name in REQUIRED_SHEETS:
        assert sheet_name in workbook["sheet_parts"]
