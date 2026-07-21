from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


REQUIRED = [
    "final-report.md",
    "environment.json",
    "repo-state.txt",
    "command-log.tsv",
    "feature-results.csv",
    "function-inventory.csv",
    "feature-entrypoint-map.csv",
    "feature-existing-test-map.csv",
    "missing-test-plan.csv",
    "pass-fail-criteria.csv",
    "gated-and-live-test-plan.md",
    "inventory-diff.md",
    "defects.md",
    "ai4research_recursive_feature_split_qa_execution_UPDATED.xlsx",
]


def csv_count(path: Path, delimiter: str = ",") -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.reader(handle, delimiter=delimiter)) - 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    checks: dict[str, bool] = {}
    for name in REQUIRED:
        path = root / name
        checks[f"required_nonempty:{name}"] = path.is_file() and path.stat().st_size > 0

    expected_rows = {
        "feature-results.csv": 2117,
        "function-inventory.csv": 31463,
        "feature-entrypoint-map.csv": 2117,
        "feature-existing-test-map.csv": 2117,
        "missing-test-plan.csv": 2117,
        "pass-fail-criteria.csv": 2117,
    }
    row_counts = {name: csv_count(root / name) for name in expected_rows}
    for name, expected in expected_rows.items():
        checks[f"row_count:{name}"] = row_counts[name] == expected

    allowed = {"PASS", "FAIL", "BLOCKED_EXPECTED", "INCONCLUSIVE_EXPECTED", "SKIPPED_NA", "SKIPPED_ENV", "FLAKY", "NOT_RUN"}
    feature_rows = list(csv.DictReader((root / "feature-results.csv").open()))
    checks["feature_status_taxonomy"] = {row["final_result_status"] for row in feature_rows} <= allowed
    checks["feature_ids_unique"] = len({row["feature_id"] for row in feature_rows}) == len(feature_rows)

    phase = root / "evidence/eligible-full-phase-v3"
    eligible_rows = list(csv.DictReader((phase / "eligible-features.csv").open()))
    excluded_rows = list(csv.DictReader((phase / "excluded-features.csv").open()))
    execution_rows = list(csv.DictReader((phase / "feature-execution-results.csv").open()))
    target_rows = list(csv.DictReader((phase / "target-results.tsv").open(), delimiter="\t"))
    eligible_ids = {row["feature_id"] for row in eligible_rows}
    execution_ids = {row["feature_id"] for row in execution_rows}
    checks["strict_phase_scope_partitions_all_features"] = len(eligible_rows) == 448 and len(excluded_rows) == 1669
    checks["strict_phase_every_eligible_feature_reconciled"] = eligible_ids == execution_ids
    checks["strict_phase_no_not_run_feature"] = all(row["execution_result"] in {"PASS", "FAIL"} for row in execution_rows)
    checks["strict_phase_all_targets_attempted"] = len(target_rows) == 107 and all(row["execution_status"] in {"PASS", "FAIL", "SKIPPED_ENV", "FLAKY"} for row in target_rows)
    checks["strict_phase_execution_report_present"] = (phase / "execution-report.md").is_file()

    environment = json.loads((root / "environment.json").read_text())
    checks["locked_sha"] = environment.get("isolated_checkout_final_sha") == "fb3f589b08e4167ac3cb0043fb3d59801a0f110b"
    checks["no_live_phase"] = environment.get("live_phase_executed") is False

    report = (root / "final-report.md").read_text(encoding="utf-8")
    checks["report_12_sections"] = all(f"## {index}." in report for index in range(1, 13))
    checks["report_not_ready"] = "**Final verdict: NOT READY" in report and "**NOT READY.**" in report
    checks["report_no_full_parity_claim"] = "Full runtime parity remains unproven" in report

    command_rows = list(csv.DictReader((root / "command-log.tsv").open(), delimiter="\t"))
    checks["command_log_nonempty"] = len(command_rows) >= 40
    checks["command_evidence_paths_exist"] = all(
        (root / row["stdout_path"]).is_file() and (root / row["stderr_path"]).is_file()
        for row in command_rows
    )

    xlsx = root / "ai4research_recursive_feature_split_qa_execution_UPDATED.xlsx"
    with zipfile.ZipFile(xlsx) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheet_names = [node.attrib["name"] for node in workbook_xml.findall("x:sheets/x:sheet", namespace)]
    required_original = {"Recursive Split", "Summary", "Split Rules", "Feature IDs", "Function Inventory", "Entrypoint Map", "Existing Test Map", "Missing Test Plan", "Pass Fail Criteria", "Severity Rubric"}
    required_added = {"Audit Summary", "Audit Results", "Audit Commands", "Audit Defects", "Eligible Phase"}
    checks["workbook_preserves_original_sheets"] = required_original <= set(sheet_names)
    checks["workbook_adds_audit_sheets"] = required_added <= set(sheet_names)
    checks["workbook_sheet_count_15"] = len(sheet_names) == 15
    checks["workbook_formula_error_scan_clean"] = "matched 0" in (root / "workbook-updated-previews/formula-error-scan.ndjson").read_text()

    manifest = {
        "schema": "qa.deliverable_validation.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "row_counts": row_counts,
        "command_count_validated": len(command_rows),
        "workbook_sheet_names": sheet_names,
        "deliverables": [
            {"path": name, "bytes": (root / name).stat().st_size, "sha256": sha256(root / name)}
            for name in REQUIRED if (root / name).is_file()
        ],
    }
    output = root / "evidence/deliverable-validation.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "checks": len(checks), "command_count": len(command_rows), "sheet_count": len(sheet_names)}, indent=2))
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
