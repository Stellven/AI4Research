import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const auditDir = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
const sourcePath = `${auditDir}/control-material/ai4research_recursive_feature_split_qa_execution.xlsx`;
const resultsPath = `${auditDir}/feature-results.csv`;
const outputPath = `${auditDir}/ai4research_recursive_feature_split_qa_execution_colored.xlsx`;
const evidenceDir = fileURLToPath(new URL("./", import.meta.url));
const previewDir = `${evidenceDir}/previews-after`;

const targetSheets = [
  "Entrypoint Map",
  "Existing Test Map",
  "Missing Test Plan",
  "Pass Fail Criteria",
];

const allSheetNames = [
  "Recursive Split",
  "Summary",
  "Split Rules",
  "Feature IDs",
  "Function Inventory",
  ...targetSheets,
  "Severity Rubric",
];

const targetHeaderColors = {
  "Entrypoint Map": "#7030A0",
  "Existing Test Map": "#5B9BD5",
  "Missing Test Plan": "#C55A11",
  "Pass Fail Criteria": "#A61C00",
};

const approvedStatuses = new Set([
  "PASS",
  "FAIL",
  "BLOCKED_EXPECTED",
  "INCONCLUSIVE_EXPECTED",
  "SKIPPED_NA",
  "SKIPPED_ENV",
  "FLAKY",
  "NOT_RUN",
]);

const statusColors = {
  PASS: "#C6EFCE",
  FAIL: "#FFC7CE",
  BLOCKED_EXPECTED: "#DDEBF7",
  SKIPPED_ENV: "#DDEBF7",
  INCONCLUSIVE_EXPECTED: "#FCE4D6",
  FLAKY: "#FCE4D6",
  SKIPPED_NA: "#F2F2F2",
};

const directAliases = new Map([
  ["passed", "PASS"],
  ["success", "PASS"],
  ["ok", "PASS"],
  ["failed", "FAIL"],
  ["error", "FAIL"],
  ["skipped_env", "SKIPPED_ENV"],
  ["missing_dependency", "SKIPPED_ENV"],
  ["missing_credentials", "SKIPPED_ENV"],
  ["inconclusive", "INCONCLUSIVE_EXPECTED"],
  ["insufficient_evidence", "INCONCLUSIVE_EXPECTED"],
  ["flaky", "FLAKY"],
  ["unstable", "FLAKY"],
  ["skipped_na", "SKIPPED_NA"],
  ["not_applicable", "SKIPPED_NA"],
  ["not_run", "NOT_RUN"],
  ["pending", "NOT_RUN"],
  ["empty", "NOT_RUN"],
]);

function normalizeStatus(rawValue, rationale = "") {
  const raw = rawValue == null ? "" : String(rawValue).trim();
  if (!raw) return { value: "NOT_RUN", recognized: true, changed: true };
  const upper = raw.toUpperCase();
  if (approvedStatuses.has(upper)) {
    return { value: upper, recognized: true, changed: upper !== raw };
  }
  const lower = raw.toLowerCase();
  if (directAliases.has(lower)) {
    return { value: directAliases.get(lower), recognized: true, changed: true };
  }
  if (["blocked", "approval_required", "gated"].includes(lower)) {
    const context = String(rationale ?? "").toLowerCase();
    const expected = /expected|correct|approval|gate|gated|blocked as designed/.test(context);
    if (expected) {
      return { value: "BLOCKED_EXPECTED", recognized: true, changed: true };
    }
  }
  return { value: raw, recognized: false, changed: false };
}

function columnName(indexZeroBased) {
  let n = indexZeroBased + 1;
  let name = "";
  while (n > 0) {
    const remainder = (n - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function contiguousRuns(rows) {
  if (rows.length === 0) return [];
  const sorted = [...rows].sort((a, b) => a - b);
  const runs = [];
  let start = sorted[0];
  let end = sorted[0];
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i] === end + 1) {
      end = sorted[i];
    } else {
      runs.push([start, end]);
      start = sorted[i];
      end = sorted[i];
    }
  }
  runs.push([start, end]);
  return runs;
}

const csvText = await fs.readFile(resultsPath, "utf8");
const csvWorkbook = await Workbook.fromCSV(csvText, { sheetName: "Feature Results" });
const csvSheet = csvWorkbook.worksheets.getItem("Feature Results");
const resultValues = csvSheet.getUsedRange().values;
const resultHeaders = resultValues[0].map((value) => String(value ?? "").trim());
const resultHeaderIndex = new Map(resultHeaders.map((header, index) => [header, index]));
for (const required of ["feature_id", "final_result_status", "result_rationale"]) {
  if (!resultHeaderIndex.has(required)) throw new Error(`Missing required result column: ${required}`);
}

const resultMap = new Map();
const resultDuplicates = [];
const ambiguousMappings = [];
const unknownStatusValues = new Map();
const normalizationCounts = new Map();
for (const row of resultValues.slice(1)) {
  const featureId = String(row[resultHeaderIndex.get("feature_id")] ?? "").trim();
  if (!featureId) continue;
  const rawStatus = row[resultHeaderIndex.get("final_result_status")];
  const rationale = row[resultHeaderIndex.get("result_rationale")];
  const normalized = normalizeStatus(rawStatus, rationale);
  if (!normalized.recognized) {
    const raw = String(rawStatus ?? "").trim();
    unknownStatusValues.set(raw, (unknownStatusValues.get(raw) ?? 0) + 1);
  }
  if (normalized.changed) {
    const key = `${String(rawStatus ?? "").trim() || "<blank>"} -> ${normalized.value}`;
    normalizationCounts.set(key, (normalizationCounts.get(key) ?? 0) + 1);
  }
  const mapped = {
    featureId,
    status: normalized.value,
    recognized: normalized.recognized,
    rawStatus: String(rawStatus ?? "").trim(),
    rationale: String(rationale ?? "").trim(),
  };
  if (resultMap.has(featureId)) {
    const existing = resultMap.get(featureId);
    resultDuplicates.push(featureId);
    if (existing.status !== mapped.status) {
      ambiguousMappings.push({
        feature_id: featureId,
        reason: "conflicting result statuses",
        values: [existing.status, mapped.status],
      });
      continue;
    }
  }
  resultMap.set(featureId, mapped);
}

const sourceBlob = await FileBlob.load(sourcePath);
const workbook = await SpreadsheetFile.importXlsx(sourceBlob);
const originalSheetInfo = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 10000 });
const originalSnapshots = {};
for (const sheetName of allSheetNames) {
  const used = workbook.worksheets.getItem(sheetName).getUsedRange();
  originalSnapshots[sheetName] = {
    rows: used.values.length,
    cols: used.values[0]?.length ?? 0,
    values: used.values,
    formulas: used.formulas,
  };
}

const report = {
  source_workbook: sourcePath,
  test_result_directory: auditDir,
  output_workbook: outputPath,
  result_feature_ids: resultMap.size,
  duplicate_result_feature_ids: [...new Set(resultDuplicates)],
  ambiguous_mappings: ambiguousMappings,
  unknown_status_values: Object.fromEntries(unknownStatusValues),
  normalizations: Object.fromEntries(normalizationCounts),
  sheets: {},
};

for (const sheetName of targetSheets) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange();
  const values = used.values;
  const headers = values[0].map((value) => String(value ?? "").trim());
  const featureIdCol = headers.indexOf("feature_id");
  if (featureIdCol < 0) throw new Error(`${sheetName}: feature_id column not found`);

  let preStatusCol = headers.indexOf("pre_test_status");
  let testStatusCol = headers.indexOf("test_result_status");
  let nextColumn = headers.length;
  const addedColumns = [];
  if (preStatusCol < 0) {
    preStatusCol = nextColumn;
    nextColumn += 1;
    addedColumns.push("pre_test_status");
  }
  if (testStatusCol < 0) {
    testStatusCol = nextColumn;
    nextColumn += 1;
    addedColumns.push("test_result_status");
  }

  const lastOriginalHeader = sheet.getCell(0, headers.length - 1);
  for (const [columnIndex, header] of [
    [preStatusCol, "pre_test_status"],
    [testStatusCol, "test_result_status"],
  ]) {
    const headerCell = sheet.getCell(0, columnIndex);
    if (columnIndex >= headers.length) headerCell.copyFrom(lastOriginalHeader, "all");
    headerCell.values = [[header]];
    sheet.getRangeByIndexes(0, columnIndex, values.length, 1).format.columnWidth = 22;
  }
  sheet.getRangeByIndexes(0, preStatusCol, 1, 2).format = {
    fill: targetHeaderColors[sheetName],
    font: { bold: true, fontSize: 11, typeface: "Carlito", color: "#FFFFFF" },
    wrapText: true,
    horizontalAlignment: "center",
  };

  const preValues = [];
  const testValues = [];
  const matchedIds = new Set();
  const unmatchedIds = new Set();
  const duplicateSheetIds = new Set();
  const seenSheetIds = new Set();
  const unknownSheetStatuses = [];
  const preRowsToColor = [];
  const testRowsByStatus = new Map(Object.keys(statusColors).map((status) => [status, []]));
  let notRunRows = 0;

  for (let dataIndex = 1; dataIndex < values.length; dataIndex += 1) {
    const excelRow = dataIndex + 1;
    const featureId = String(values[dataIndex][featureIdCol] ?? "").trim();
    if (featureId && seenSheetIds.has(featureId)) duplicateSheetIds.add(featureId);
    if (featureId) seenSheetIds.add(featureId);

    const existingPreRaw = preStatusCol < headers.length ? values[dataIndex][preStatusCol] : "";
    const existingPre = String(existingPreRaw ?? "").trim();
    let preValue = existingPre;
    let preRecognized = true;
    if (existingPre) {
      const normalizedPre = normalizeStatus(existingPre, "");
      preValue = normalizedPre.value;
      preRecognized = normalizedPre.recognized;
      if (!preRecognized) unknownSheetStatuses.push({ row: excelRow, column: "pre_test_status", value: existingPre });
      if (preRecognized) preRowsToColor.push(excelRow);
    }
    preValues.push([preValue]);

    let testValue = "NOT_RUN";
    let testRecognized = true;
    if (featureId && resultMap.has(featureId)) {
      const result = resultMap.get(featureId);
      testValue = result.status;
      testRecognized = result.recognized;
      matchedIds.add(featureId);
    } else {
      if (featureId) unmatchedIds.add(featureId);
      testValue = "NOT_RUN";
    }
    testValues.push([testValue]);
    if (!testRecognized) {
      unknownSheetStatuses.push({ row: excelRow, column: "test_result_status", value: testValue });
    } else if (statusColors[testValue]) {
      testRowsByStatus.get(testValue).push(excelRow);
    } else if (testValue === "NOT_RUN" || testValue === "") {
      notRunRows += 1;
    }
  }

  const rowCount = values.length - 1;
  const preColumnLetter = columnName(preStatusCol);
  const testColumnLetter = columnName(testStatusCol);
  const preRange = sheet.getRange(`${preColumnLetter}2:${preColumnLetter}${values.length}`);
  const testRange = sheet.getRange(`${testColumnLetter}2:${testColumnLetter}${values.length}`);
  preRange.values = preValues;
  testRange.values = testValues;
  preRange.format = { font: { color: "#000000" }, wrapText: true };
  testRange.format = { font: { color: "#000000" }, wrapText: true };

  for (const [startRow, endRow] of contiguousRuns(preRowsToColor)) {
    sheet.getRange(`${preColumnLetter}${startRow}:${preColumnLetter}${endRow}`).format = {
      fill: "#EDEDED",
      font: { color: "#000000" },
    };
  }
  for (const [status, rows] of testRowsByStatus.entries()) {
    for (const [startRow, endRow] of contiguousRuns(rows)) {
      sheet.getRange(`${testColumnLetter}${startRow}:${testColumnLetter}${endRow}`).format = {
        fill: statusColors[status],
        font: { color: "#000000" },
      };
    }
  }

  report.sheets[sheetName] = {
    data_rows: rowCount,
    added_columns: addedColumns,
    pre_test_status_column: preColumnLetter,
    test_result_status_column: testColumnLetter,
    matched_feature_ids: matchedIds.size,
    unmatched_feature_ids: unmatchedIds.size,
    unmatched_feature_id_values: [...unmatchedIds],
    duplicate_sheet_feature_ids: [...duplicateSheetIds],
    pre_test_status_cells_colored: preRowsToColor.length,
    test_result_status_cells_colored: [...testRowsByStatus.values()].reduce((sum, rows) => sum + rows.length, 0),
    total_status_cells_colored: preRowsToColor.length + [...testRowsByStatus.values()].reduce((sum, rows) => sum + rows.length, 0),
    not_run_or_blank_test_result_rows: notRunRows,
    unknown_sheet_statuses: unknownSheetStatuses,
    status_counts: Object.fromEntries(
      [...testRowsByStatus.entries()].map(([status, rows]) => [status, rows.length]).concat([["NOT_RUN", notRunRows]]),
    ),
  };
}

await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of targetSheets) {
  const sheetReport = report.sheets[sheetName];
  const lastColumn = sheetReport.test_result_status_column;
  const preview = await workbook.render({
    sheetName,
    range: `A1:${lastColumn}25`,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    `${previewDir}/${sheetName.replaceAll(" ", "_")}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const exportedBlob = await FileBlob.load(outputPath);
const exportedWorkbook = await SpreadsheetFile.importXlsx(exportedBlob);
const exportedSheetInfo = await exportedWorkbook.inspect({ kind: "sheet", include: "id,name", maxChars: 10000 });
const formulaErrors = await exportedWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});

report.verification = {
  original_sheet_info: originalSheetInfo.ndjson,
  exported_sheet_info: exportedSheetInfo.ndjson,
  formula_error_scan: formulaErrors.ndjson,
  original_content_preserved: {},
  target_header_checks: {},
};

for (const sheetName of allSheetNames) {
  const snapshot = originalSnapshots[sheetName];
  const exportedOriginalRange = exportedWorkbook.worksheets
    .getItem(sheetName)
    .getRangeByIndexes(0, 0, snapshot.rows, snapshot.cols);
  const valuesPreserved = JSON.stringify(exportedOriginalRange.values) === JSON.stringify(snapshot.values);
  const formulasPreserved = JSON.stringify(exportedOriginalRange.formulas) === JSON.stringify(snapshot.formulas);
  report.verification.original_content_preserved[sheetName] = {
    values_preserved: valuesPreserved,
    formulas_preserved: formulasPreserved,
  };
}
report.verification.all_original_content_preserved = Object.values(
  report.verification.original_content_preserved,
).every((entry) => entry.values_preserved && entry.formulas_preserved);

for (const sheetName of targetSheets) {
  const sheet = exportedWorkbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange().values;
  const headers = values[0].map((value) => String(value ?? "").trim());
  const preCol = headers.indexOf("pre_test_status");
  const testCol = headers.indexOf("test_result_status");
  const counts = new Map();
  for (const row of values.slice(1)) {
    const status = String(row[testCol] ?? "").trim();
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }
  report.verification.target_header_checks[sheetName] = {
    pre_test_status_present: preCol >= 0,
    test_result_status_present: testCol >= 0,
    data_rows: values.length - 1,
    status_counts: Object.fromEntries(counts),
  };
}

await fs.writeFile(`${evidenceDir}/coloring-summary.json`, JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
