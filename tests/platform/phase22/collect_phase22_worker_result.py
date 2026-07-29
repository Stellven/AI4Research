"""Produce a deterministic worker result payload for the Phase 22 repair task."""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from typing import Any
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase22_workbook_validation import parse_workbook, read_matrix_counts, summarize_feature_sheets, _value_for_cell


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DEFAULT_MATRIX_SCRIPT = HERE / "build_atomic_feature_matrix.py"
DEFAULT_WORKBOOK_SCRIPT = HERE / "build_phase22_workbook.mjs"
DEFAULT_MATRIX_PATH = HERE / "atomic_feature_matrix.json"
DEFAULT_WORKBOOK_PATH = ROOT / ".codex-tmp/phase22-i1/phase-22-test-report.generated.xlsx"
DEFAULT_RESULT_PATH = ROOT / ".codex-tmp/phase22-worker-results/I1/result.json"


def _run_matrix(
    generator: list[str],
    matrix_path: Path,
    work_dir: Path,
    runs: int = 2,
) -> dict[str, Any]:
    hashes = []
    blockers: list[str] = []
    for index in range(runs):
        completed = subprocess.run(
            generator,
            cwd=work_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            blockers.append(f"matrix_run_{index + 1}_failed:{completed.returncode}")
            continue
        hashes.append(hashlib.sha256(matrix_path.read_bytes()).hexdigest())

    return {
        "hashes": hashes,
        "hash_match": len(hashes) == runs and len(set(hashes)) == 1,
        "blockers": blockers,
    }


def _value(sheet_rows: dict[int, dict[int, Any]], shared_strings: list[str], row: int, col: int) -> int:
    cell = sheet_rows.get(row, {}).get(col)
    if cell is None:
        raise AssertionError(f"Missing Coverage Summary cell at R{row}C{col}.")
    raw = _value_for_cell(cell, shared_strings)
    return int(raw or 0)


def _assert_summary(
    matrix: dict[str, Any],
    parsed: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    summary_sheet = parsed["sheet_rows"].get("Coverage Summary")
    if summary_sheet is None:
        return ["Coverage Summary sheet is missing."]

    shared_strings = parsed["shared_strings"]
    checks = [
        (3, 1, matrix["counts"]["l2_features"]),
        (4, 1, 2047),
        (5, 1, matrix["counts"]["reviewed_atomic"]),
        (6, 1, matrix["counts"]["net_rows_removed"]),
        (7, 1, matrix["counts"]["test_generation"].get("GENERATED_EXECUTABLE", 0)),
        (8, 1, matrix["counts"]["test_generation"].get("REUSED_EXISTING_EXECUTABLE", 0)),
        (9, 1, matrix["counts"]["test_generation"].get("REUSED_L2_REPRESENTATIVE_EXECUTABLE", 0)),
        (
            10,
            1,
            matrix["counts"]["test_generation"].get("MANUAL_ORACLE_REQUIRED", 0)
            + matrix["counts"]["test_generation"].get("TAGGED_NOT_GENERATED_MANUAL_ORACLE", 0),
        ),
        (11, 1, matrix["counts"]["test_generation"].get("PLATFORM_OR_HARDWARE_REQUIRED", 0)),
        (12, 1, matrix["counts"]["test_generation"].get("BLOCKED_NOT_IMPLEMENTED", 0)),
        (13, 1, matrix["counts"]["current_result"].get("PASS", 0)),
        (14, 1, matrix["counts"]["current_result"].get("FAIL", 0)),
        (15, 1, matrix["counts"]["l2_rollup"].get("FUNCTION_IMPLEMENTED_ALL_ATOMIC_TESTS_PASSED", 0)),
        (16, 1, matrix["counts"]["l2_rollup"].get("FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED", 0)),
        (17, 1, matrix["counts"]["l2_rollup"].get("FUNCTION_NOT_IMPLEMENTED_TEST_BLOCKED", 0)),
        (18, 1, matrix["counts"]["l2_rollup"].get("IMPLEMENTED_TEST_GAP_BLOCKED", 0)),
        (29, 1, 0),
    ]
    for row, col, expected in checks:
        actual = _value(summary_sheet, shared_strings, row, col)
        if actual != expected:
            blockers.append(f"coverage_summary_R{row}C{col}_{actual}_!={expected}")
    return blockers


def _build_workbook(
    node: str | None,
    workbook_script: Path,
    matrix_path: Path,
    workbook_path: Path,
    blockers: list[str],
) -> bool:
    if workbook_path.exists():
        return True
    if node is None:
        blockers.append("node_runtime_not_available")
        return False
    command = [
        node,
        str(workbook_script),
        f"--matrix={matrix_path}",
        f"--source={ROOT / 'docs/integrations/autosci/.codex-tmp-phase22-copy.xlsx'}",
        f"--output={workbook_path}",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        blockers.append(f"workbook_build_failed:{completed.returncode}")
        if completed.stderr:
            blockers.append(completed.stderr[:800])
        return False
    return True


def _baseline_reconciled(counts: dict[str, Any]) -> bool:
    if counts["rows"] != 1502:
        return False
    if counts["l2_features"] != 142:
        return False
    if counts["test_generation"].get("REUSED_L2_REPRESENTATIVE_EXECUTABLE") != 120:
        return False
    if counts["test_generation"].get("TAGGED_NOT_GENERATED_MANUAL_ORACLE") != 909:
        return False
    if counts["coverage"].get("DIRECT") != 160:
        return False
    if counts["coverage"].get("UNRESOLVED") != 1049:
        return False
    if counts["implementation"].get("IMPLEMENTED_CURRENT_SUBSET_UNVERIFIED") != 1194:
        return False
    if counts["implementation"].get("IMPLEMENTED_EXECUTABLE_EVIDENCE") != 158:
        return False
    if counts["implementation"].get("NOT_IMPLEMENTED") != 150:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix-script", type=Path, default=DEFAULT_MATRIX_SCRIPT)
    parser.add_argument("--workbook-script", type=Path, default=DEFAULT_WORKBOOK_SCRIPT)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK_PATH)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT_PATH)
    args = parser.parse_args()
    matrix_path = args.matrix
    workbook_path = args.workbook
    matrix_script = args.matrix_script
    workbook_script = args.workbook_script
    result_path = args.result

    blocked: list[str] = []
    tests_run: list[str] = []
    test_results: list[str] = []

    matrix_payload = [str(matrix_script)]
    result = _run_matrix(
        [str(sys.executable), *matrix_payload],
        matrix_path,
        ROOT,
    )
    tests_run.append("build_atomic_feature_matrix.py")
    blocked.extend(result["blockers"])
    test_results.append(
        "matrix_deterministic_sha256="
        + ("true" if result["hash_match"] else "false")
    )

    matrix = read_matrix_counts(matrix_path)
    baseline_reconciled = _baseline_reconciled(matrix["counts"])

    workbook_ready = _build_workbook(
        shutil.which("node"),
        workbook_script,
        matrix_path,
        workbook_path,
        blocked,
    )
    tests_run.append("build_phase22_workbook.mjs")
    workbook_reimport_passed = False
    formula_errors = None
    summary_reconciled = False

    if workbook_ready:
        parsed = parse_workbook(workbook_path)
        feature_summary = summarize_feature_sheets(parsed["sheet_rows"], parsed["shared_strings"], [
            "Workflow Features",
            "Foundation Features",
            "Vertical Features",
        ])
        matrix_ids = [row["atomic_feature_id"] for row in matrix["payload"]["atomic_features"]]
        if len(feature_summary["atomic_feature_ids"]) != len(matrix_ids):
            blocked.append("workbook_atomic_count_mismatch")
        elif set(feature_summary["atomic_feature_ids"]) != set(matrix_ids):
            blocked.append("workbook_atomic_ids_mismatch")
        if feature_summary["unique_l2_count"] != matrix["counts"]["l2_features"]:
            blocked.append("workbook_l2_count_mismatch")

        worksheet_blockers = _assert_summary(matrix, parsed)
        blocked.extend(worksheet_blockers)
        summary_reconciled = not any(worksheet_blockers)
        formula_errors = len(parsed["formula_errors"])
        workbook_reimport_passed = formula_errors == 0 and not any(worksheet_blockers)
        test_results.append("workbook_reimport_passed=" + str(workbook_reimport_passed).lower())
    else:
        blocked.append("workbook_generation_skipped")
        workbook_reimport_passed = False
        formula_errors = None
        summary_reconciled = False
        test_results.append("workbook_reimport_passed=false")

    output = {
        "baseline_reconciled": baseline_reconciled,
        "matrix_rows": matrix["counts"]["rows"],
        "l2_rows": matrix["counts"]["l2_features"],
        "deterministic_hash_match": bool(result["hash_match"]),
        "workbook_reimport_passed": workbook_reimport_passed,
        "summary_reconciled": summary_reconciled,
        "formula_errors": formula_errors if formula_errors is not None else 0,
        "tests_run": tests_run,
        "test_results": test_results,
        "changed_files": [
            line[3:].strip()
            for line in subprocess.check_output(["git", "status", "--short", str(HERE)]).decode("utf-8").splitlines()
            if line.strip()
        ],
        "remaining_blockers": blocked,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
