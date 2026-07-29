from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[4]
RUN_ID = "overnight-phase22-20260729T044000Z"
LEDGER_PATH = ROOT / "outputs" / "phase22-real-journeys" / RUN_ID / "l2-evidence-ledger.json"
FULL_REPORT = ROOT / "docs" / "integrations" / "autosci" / "phase-22-test-report.xlsx"
BRIEF_REPORT = Path("C:/Users/j50058254/Downloads/AI4RnD Feature List.xlsx")
STAGED_BRIEF = ROOT / ".codex-tmp" / "phase22-worker-results" / "overnight-phase22" / "staged-reports" / "AI4RnD Feature List.xlsx"
BRIEF_LOCK = Path("C:/Users/j50058254/Downloads/~$AI4RnD Feature List.xlsx")
OUT_PATH = ROOT / ".codex-tmp" / "phase22-worker-results" / "overnight-phase22" / "final-validator.json"

ALLOWED = {"PASS", "PASS_WITH_KNOWN_LIMITATIONS", "FAIL", "ENVIRONMENT_BLOCKED", "NOT_AVAILABLE"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _formula_errors(path: Path) -> list[str]:
    error_re = re.compile(r"#REF!|#DIV/0!|#VALUE!|#NAME\?|#N/A", re.IGNORECASE)
    errors: list[str] = []
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith(".xml"):
                text = archive.read(name).decode("utf-8", errors="replace")
                if error_re.search(text):
                    errors.append(name)
    return errors


def _read_xlsx_sheet_values(path: Path) -> dict[str, list[list[str]]]:
    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    }

    def col_to_index(cell_ref: str) -> int:
        match = re.match(r"([A-Z]+)", cell_ref)
        if not match:
            return 0
        out = 0
        for char in match.group(1):
            out = out * 26 + ord(char) - 64
        return out - 1

    def normalize_target(target: str) -> str:
        target = target.replace("\\", "/")
        if target.startswith("/"):
            return target.lstrip("/")
        return f"xl/{target}".replace("xl/../", "")

    with ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.findall(".//main:si", ns):
                shared.append("".join(node.text or "" for node in si.findall(".//main:t", ns)))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_to_target = {
            rel.attrib["Id"]: normalize_target(rel.attrib["Target"])
            for rel in rels.findall(".//pkg:Relationship", ns)
        }
        output: dict[str, list[list[str]]] = {}
        for sheet in workbook.findall(".//main:sheet", ns):
            sheet_name = sheet.attrib["name"]
            rel_id = sheet.attrib[f"{{{ns['rel']}}}id"]
            target = rel_to_target[rel_id]
            xml = ET.fromstring(archive.read(target))
            rows: list[list[str]] = []
            for row in xml.findall(".//main:sheetData/main:row", ns):
                row_index = int(row.attrib["r"]) - 1
                while len(rows) <= row_index:
                    rows.append([])
                values = rows[row_index]
                for cell in row.findall("main:c", ns):
                    column = col_to_index(cell.attrib.get("r", "A1"))
                    while len(values) <= column:
                        values.append("")
                    value = ""
                    if cell.attrib.get("t") == "s":
                        raw = cell.findtext("main:v", default="", namespaces=ns)
                        value = shared[int(raw)] if raw else ""
                    elif cell.attrib.get("t") == "inlineStr":
                        value = cell.findtext("main:is/main:t", default="", namespaces=ns)
                    else:
                        value = cell.findtext("main:v", default="", namespaces=ns)
                    values[column] = value or ""
            output[sheet_name] = rows
        return output


def _brief_counts(path: Path) -> Counter:
    workbook = _read_xlsx_sheet_values(path)
    counts: Counter[str] = Counter()
    for sheet_name in ("Workflow Features", "Foundation Features", "Vertical Features"):
        rows = workbook[sheet_name]
        header_row = next((i for i, row in enumerate(rows) if "Current Report Conclusion" in row), -1)
        if header_row < 0:
            continue
        conclusion_col = rows[header_row].index("Current Report Conclusion")
        for row in rows[header_row + 1:]:
            value = row[conclusion_col] if conclusion_col < len(row) else ""
            if value:
                counts[str(value)] += 1
    return counts


def main() -> int:
    failures: list[str] = []
    payload = _load_json(LEDGER_PATH)
    ledger = payload["ledger"]
    summary = payload["summary"]
    counts = Counter(item["result"] for item in ledger)

    if summary["brief_l2_count"] != 142 or len(ledger) != summary["brief_l2_count"]:
        failures.append("Ledger row count does not match 142 brief L2 rows.")
    keys = [item["ledger_key"] for item in ledger]
    if len(keys) != len(set(keys)):
        failures.append("Ledger contains duplicate L2 keys.")
    if set(counts) - ALLOWED:
        failures.append(f"Ledger contains disallowed statuses: {sorted(set(counts) - ALLOWED)}")
    for zero_field in ("not_tested", "unresolved", "planned_no_direct", "no_journey_evidence", "unmatched_observed_l2"):
        if summary.get(zero_field) != 0:
            failures.append(f"{zero_field} is not zero: {summary.get(zero_field)}")

    for item in ledger:
        required = ("actual_product_command", "assertion_name", "evidence_path", "repo_head", "run_id")
        missing = [field for field in required if not str(item.get(field) or "").strip()]
        if missing:
            failures.append(f"{item['ledger_key']} missing evidence fields: {missing}")
        if item["result"] == "ENVIRONMENT_BLOCKED" and not str(item.get("environment_requirement") or "").strip():
            failures.append(f"{item['ledger_key']} environment block lacks named requirement.")
        if item["result"] == "NOT_AVAILABLE" and "evidence" not in str(item.get("evidence_basis") or "").lower():
            failures.append(f"{item['ledger_key']} NOT_AVAILABLE lacks implementation/probe evidence basis.")

    full_errors = _formula_errors(FULL_REPORT)
    staged_brief_errors = _formula_errors(STAGED_BRIEF)
    if full_errors:
        failures.append(f"Full report formula errors: {full_errors[:5]}")
    if staged_brief_errors:
        failures.append(f"Staged brief formula errors: {staged_brief_errors[:5]}")

    ledger_counts = Counter({status: counts.get(status, 0) for status in ALLOWED})
    staged_counts = _brief_counts(STAGED_BRIEF)
    current_counts = _brief_counts(BRIEF_REPORT)
    for status in ALLOWED:
        if staged_counts.get(status, 0) != ledger_counts.get(status, 0):
            failures.append(f"Staged brief count mismatch for {status}: {staged_counts.get(status, 0)} != {ledger_counts.get(status, 0)}")
        if current_counts.get(status, 0) != ledger_counts.get(status, 0):
            failures.append(f"Current brief count mismatch for {status}: {current_counts.get(status, 0)} != {ledger_counts.get(status, 0)}")

    if BRIEF_LOCK.exists():
        failures.append(f"Excel lock file still present: {BRIEF_LOCK}")

    diff = subprocess.run(["git", "diff", "--check"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if diff.returncode != 0:
        failures.append(f"git diff --check failed: {(diff.stdout + diff.stderr)[-1000:]}")

    result = {
        "schema_version": "phase22.overnight_validator.v1",
        "ledger_path": str(LEDGER_PATH),
        "full_report": str(FULL_REPORT),
        "brief_report": str(BRIEF_REPORT),
        "staged_brief_report": str(STAGED_BRIEF),
        "ledger_counts": dict(sorted(ledger_counts.items())),
        "staged_brief_counts": dict(sorted(staged_counts.items())),
        "current_brief_counts": dict(sorted(current_counts.items())),
        "full_formula_errors": len(full_errors),
        "staged_brief_formula_errors": len(staged_brief_errors),
        "brief_lock_present": BRIEF_LOCK.exists(),
        "git_diff_check_exit_code": diff.returncode,
        "passed": not failures,
        "failures": failures,
    }
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
