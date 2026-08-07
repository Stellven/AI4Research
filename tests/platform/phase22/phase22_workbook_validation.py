"""Helpers to validate the Phase 22 workbook output without external dependencies."""
from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from collections import Counter

from typing import Any


WORKBOOK_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ZIP_REL_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"

CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")
WEAK_PASS_EVIDENCE_RE = re.compile(
    r"\b(?:inferred|mock(?:-only)?|schema(?:-only)?|fixture(?:-only)?|"
    r"static(?:-text)?(?:-only)?|no journey)\b",
    re.IGNORECASE,
)
ERROR_FORMULA_RE = re.compile(r"#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N/A", re.IGNORECASE)


def _normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _col_to_index(col: str) -> int:
    index = 0
    for char in col:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _value_for_cell(cell: ET.Element, shared_strings: list[str]) -> str | None:
    t = cell.attrib.get("t")
    if t == "s":
        raw = cell.findtext(f"{{{WORKBOOK_NAMESPACE}}}v")
        if raw is None:
            return None
        return shared_strings[int(raw)]
    if t == "inlineStr":
        inline = cell.find(f"{{{WORKBOOK_NAMESPACE}}}is/{{{WORKBOOK_NAMESPACE}}}t")
        return None if inline is None else (inline.text or "")
    raw = cell.findtext(f"{{{WORKBOOK_NAMESPACE}}}v")
    return (raw if raw is not None else "")


def _read_shared_strings(root: ET.Element) -> list[str]:
    values = []
    for si in root.findall(f".//{{{WORKBOOK_NAMESPACE}}}si"):
        text = "".join(node.text or "" for node in si.findall(".//") if node.tag.endswith("t"))
        values.append(text)
    return values


def _worksheet_rows(worksheet: ET.Element, shared_strings: list[str]) -> dict[int, dict[int, ET.Element]]:
    rows = {}
    for row in worksheet.findall(f".//{{{WORKBOOK_NAMESPACE}}}sheetData/{{{WORKBOOK_NAMESPACE}}}row"):
        row_index = int(row.attrib["r"])
        row_values = {}
        for cell in row.findall(f"{{{WORKBOOK_NAMESPACE}}}c"):
            match = CELL_REF_RE.match(cell.attrib["r"])
            if not match:
                continue
            column = match.group(1)
            col_index = _col_to_index(column)
            row_values[col_index] = cell
        rows[row_index] = row_values
    return rows


def _scan_formula_errors(
    worksheet: ET.Element,
    shared_strings: list[str],
    sheet_name: str,
) -> list[str]:
    formula_errors: list[str] = []
    for row in worksheet.findall(f".//{{{WORKBOOK_NAMESPACE}}}sheetData/{{{WORKBOOK_NAMESPACE}}}row"):
        row_index = int(row.attrib["r"])
        for cell in row.findall(f"{{{WORKBOOK_NAMESPACE}}}c"):
            match = CELL_REF_RE.match(cell.attrib["r"])
            if not match:
                continue
            col = match.group(1)
            col_index = _col_to_index(col)
            column_ref = f"{col}{row_index}"
            formula = cell.findtext(f"{{{WORKBOOK_NAMESPACE}}}f")
            if formula and ERROR_FORMULA_RE.search(formula):
                formula_errors.append(f"{sheet_name}!{column_ref}:{formula}")
            value = _value_for_cell(cell, shared_strings)
            if isinstance(value, str) and ERROR_FORMULA_RE.search(value):
                formula_errors.append(f"{sheet_name}!{column_ref}:{value}")
    return formula_errors


def _row_to_values(rows: dict[int, dict[int, ET.Element]], row_index: int, shared_strings: list[str]) -> dict[int, str | None]:
    values: dict[int, str | None] = {}
    for col, cell in rows.get(row_index, {}).items():
        values[col] = _value_for_cell(cell, shared_strings)
    return values


def _find_header_column(rows: dict[int, dict[int, ET.Element]], shared_strings: list[str], header: str) -> tuple[int, int]:
    for row_index, cols in rows.items():
        for column_index, cell in cols.items():
            if _value_for_cell(cell, shared_strings) == header:
                return row_index, column_index
    raise AssertionError(f"Missing required column header: {header}")


def _find_first_header_column(
    rows: dict[int, dict[int, ET.Element]],
    shared_strings: list[str],
    headers: list[str],
) -> tuple[int, int]:
    errors = []
    for header in headers:
        try:
            return _find_header_column(rows, shared_strings, header)
        except AssertionError as exc:
            errors.append(str(exc))
    raise AssertionError("; ".join(errors))


def _read_workbook_xml_paths(xlsx_path: Path) -> dict[str, ET.Element]:
    with ZipFile(xlsx_path) as archive:
        payloads = {name: ET.fromstring(archive.read(name)) for name in archive.namelist() if name.endswith((".xml", ".rels"))}
    return payloads


def parse_workbook(xlsx_path: Path) -> dict[str, Any]:
    """Parse workbook metadata and validate a minimal OPC structure."""
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Missing workbook output: {xlsx_path}")

    workbook_payloads = _read_workbook_xml_paths(xlsx_path)
    required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
    for name in required:
        if name not in workbook_payloads:
            raise AssertionError(f"Workbook package is missing required part: {name}")

    workbook_root = workbook_payloads["xl/workbook.xml"]
    rels_root = workbook_payloads["xl/_rels/workbook.xml.rels"]
    shared_strings_root = workbook_payloads.get("xl/sharedStrings.xml")
    shared_strings = _read_shared_strings(shared_strings_root) if shared_strings_root is not None else []

    sheet_nodes = workbook_root.findall(f".//{{{WORKBOOK_NAMESPACE}}}sheets/{{{WORKBOOK_NAMESPACE}}}sheet")
    if not sheet_nodes:
        raise AssertionError("Workbook contains no worksheets.")

    rel_to_target = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f".//{{{ZIP_REL_NAMESPACE}}}Relationship")
        if rel.attrib.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
    }

    sheet_parts = {}
    formula_errors: list[str] = []
    rows_by_sheet: dict[str, dict[int, dict[int, ET.Element]]] = {}
    sheet_id_map = {}

    for sheet in sheet_nodes:
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{REL_NAMESPACE}}}id"]
        target = rel_to_target.get(rel_id)
        if not target:
            raise AssertionError(f"Missing worksheet relation for {name}: {rel_id}")
        target_path = str(target).lstrip("/")
        normalized = _normalize_path(Path(target_path) if target_path.startswith("xl/") else Path("xl") / target_path)
        if normalized not in workbook_payloads:
            raise AssertionError(f"Worksheet part missing for sheet '{name}': {normalized}")
        sheet_xml = workbook_payloads[normalized]
        sheet_rows = _worksheet_rows(sheet_xml, shared_strings)
        rows_by_sheet[name] = sheet_rows
        sheet_id_map[name] = normalized
        formula_errors.extend(_scan_formula_errors(sheet_xml, shared_strings, name))

    return {
        "sheet_names": [sheet.attrib["name"] for sheet in sheet_nodes],
        "sheet_rows": rows_by_sheet,
        "shared_strings": shared_strings,
        "sheet_parts": sheet_id_map,
        "formula_errors": formula_errors,
    }


def summarize_feature_sheets(
    rows_by_sheet: dict[str, dict[int, dict[int, ET.Element]]],
    shared_strings: list[str],
    feature_sheet_names: list[str],
) -> dict[str, Any]:
    header_row_ids = {}
    atomic_rows = 0
    atomic_feature_ids: list[str] = []
    l2_values = Counter()

    for sheet_name in feature_sheet_names:
        if sheet_name not in rows_by_sheet:
            raise AssertionError(f"Missing required feature sheet: {sheet_name}")
        rows = rows_by_sheet[sheet_name]
        atom_row, atom_col = _find_header_column(rows, shared_strings, "Atomic Feature ID")
        l2_row, l2_col = _find_header_column(rows, shared_strings, "Level 2 Feature")
        header_row_ids[sheet_name] = (atom_row, atom_col, l2_row, l2_col)

        for row_num, cols in rows.items():
            if row_num <= max(atom_row, l2_row):
                continue
            atomic_id = _value_for_cell(cols.get(atom_col), shared_strings)
            if atomic_id and str(atomic_id).startswith("P22-AF-"):
                atomic_rows += 1
                atomic_feature_ids.append(str(atomic_id))
                l2_feature = _value_for_cell(cols.get(l2_col), shared_strings)
                if l2_feature:
                    l2_values[str(l2_feature)] += 1

    return {
        "total_atomic_rows": atomic_rows,
        "atomic_feature_ids": atomic_feature_ids,
        "l2_feature_counts": dict(l2_values),
        "unique_l2_count": len(l2_values),
    }


def read_matrix_counts(matrix_path: Path) -> dict[str, Any]:
    import json
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = payload["atomic_features"]
    return {
        "payload": payload,
        "counts": {
            "rows": len(rows),
            "l2_features": payload["counts"]["l2_features"],
            "reviewed_atomic": payload["counts"]["reviewed_atomic_features"],
            "net_rows_removed": payload["counts"]["net_rows_removed"],
            "test_generation": payload["counts"]["test_generation_status"],
            "coverage": Counter(row["coverage_relationship"] for row in rows),
            "current_result": Counter(row["current_result"] for row in rows),
            "implementation": Counter(row["implementation_status"] for row in rows),
            "l2_rollup": Counter(item["atomic_rollup_status"] for item in payload["l2_summary"]),
        },
    }


def validate_l2_report_evidence(
    parsed_workbook: dict[str, Any],
    feature_sheet_names: list[str],
) -> dict[str, Any]:
    """Reject weak-only evidence used to claim an L2 PASS conclusion."""
    rows_by_sheet = parsed_workbook["sheet_rows"]
    shared_strings = parsed_workbook["shared_strings"]
    status_counts: Counter[str] = Counter()
    weak_passes: list[str] = []
    l2_count = 0

    for sheet_name in feature_sheet_names:
        rows = rows_by_sheet[sheet_name]
        header_row, l2_col = _find_first_header_column(
            rows,
            shared_strings,
            ["level_2_feature", "Level 2 Feature"],
        )
        _, status_col = _find_header_column(rows, shared_strings, "Current Report Conclusion")
        _, basis_col = _find_header_column(rows, shared_strings, "Evidence Basis")
        _, limitation_col = _find_header_column(rows, shared_strings, "Evidence / Known Limitations")
        for row_num, cols in rows.items():
            if row_num <= header_row:
                continue
            l2 = str(_value_for_cell(cols.get(l2_col), shared_strings) or "").strip()
            if not l2:
                continue
            l2_count += 1
            status = str(_value_for_cell(cols.get(status_col), shared_strings) or "").strip()
            basis = str(_value_for_cell(cols.get(basis_col), shared_strings) or "")
            limitation = str(_value_for_cell(cols.get(limitation_col), shared_strings) or "")
            status_counts[status] += 1
            if status.startswith("PASS") and WEAK_PASS_EVIDENCE_RE.search(f"{basis} {limitation}"):
                weak_passes.append(f"{sheet_name}!{row_num}:{l2}:{basis}")

    if l2_count != 142:
        raise AssertionError(f"Expected 142 canonical L2 rows, found {l2_count}")
    if weak_passes:
        raise AssertionError("Weak-only evidence cannot support PASS: " + "; ".join(weak_passes))
    return {"l2_count": l2_count, "status_counts": dict(status_counts)}
