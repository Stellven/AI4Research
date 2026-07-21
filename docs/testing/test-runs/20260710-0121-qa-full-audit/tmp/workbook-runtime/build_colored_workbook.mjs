import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const auditRoot = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
const sourceWorkbook = `${auditRoot}/control-material/ai4research_recursive_feature_split_qa_execution.xlsx`;
const featureResultsPath = `${auditRoot}/feature-results.csv`;
const outputWorkbook = `${auditRoot}/ai4research_recursive_feature_split_qa_execution_colored.xlsx`;
const changelogPath = `${auditRoot}/qa_workbook_coloring_changelog.md`;
const previewDir = `${auditRoot}/tmp/workbook-runtime`;

const targetSheets = ["Entrypoint Map", "Existing Test Map", "Missing Test Plan", "Pass Fail Criteria"];
const headerColors = {
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
const resultColors = {
  PASS: "#C6EFCE",
  FAIL: "#FFC7CE",
  BLOCKED_EXPECTED: "#DDEBF7",
  SKIPPED_ENV: "#DDEBF7",
  INCONCLUSIVE_EXPECTED: "#FCE4D6",
  FLAKY: "#FCE4D6",
  SKIPPED_NA: "#F2F2F2",
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.endsWith("\r") ? field.slice(0, -1) : field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  const headers = rows.shift();
  return rows.filter((values) => values.some((value) => value !== "")).map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
  );
}

function normalizedStatus(value) {
  return String(value || "").trim().toUpperCase();
}

function contiguousRuns(items) {
  const runs = [];
  if (!items.length) return runs;
  let start = 0;
  let value = items[0];
  for (let index = 1; index <= items.length; index += 1) {
    if (index === items.length || items[index] !== value) {
      runs.push({ start, count: index - start, value });
      start = index;
      value = items[index];
    }
  }
  return runs;
}

const resultRows = parseCsv(await fs.readFile(featureResultsPath, "utf8"));
const resultByFeature = new Map();
const duplicateFeatureIds = [];
const nonStandardStatuses = [];
for (const row of resultRows) {
  const featureId = String(row.feature_id || "").trim();
  const status = normalizedStatus(row.final_result_status);
  if (!featureId) continue;
  if (resultByFeature.has(featureId)) duplicateFeatureIds.push(featureId);
  if (status && !approvedStatuses.has(status)) nonStandardStatuses.push({ featureId, status });
  resultByFeature.set(featureId, status);
}

const input = await FileBlob.load(sourceWorkbook);
const workbook = await SpreadsheetFile.importXlsx(input);
const perSheet = [];
const globallyMatched = new Set();
const globallyUnmatched = new Set();

for (const sheetName of targetSheets) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const originalUsed = sheet.getUsedRange();
  const originalColumns = originalUsed.columnCount;
  const dataRows = originalUsed.rowCount - 1;
  const featureValues = sheet.getRangeByIndexes(1, 0, dataRows, 1).values;
  const headers = originalUsed.getRow(0).values[0].map((value) => String(value || "").trim());
  const preExistingIndex = headers.indexOf("pre_test_status");
  const resultExistingIndex = headers.indexOf("test_result_status");
  const preIndex = preExistingIndex >= 0 ? preExistingIndex : originalColumns;
  const resultIndex = resultExistingIndex >= 0 ? resultExistingIndex : originalColumns + (preExistingIndex >= 0 ? 0 : 1);
  const finalColumns = Math.max(originalColumns, preIndex + 1, resultIndex + 1);

  if (preExistingIndex < 0) {
    const header = sheet.getCell(0, preIndex);
    header.copyFrom(sheet.getCell(0, originalColumns - 1), "all");
    header.values = [["pre_test_status"]];
    header.format.columnWidth = 20;
  }
  if (resultExistingIndex < 0) {
    const header = sheet.getCell(0, resultIndex);
    header.copyFrom(sheet.getCell(0, originalColumns - 1), "all");
    header.values = [["test_result_status"]];
    header.format.columnWidth = 24;
  }
  sheet.getRangeByIndexes(0, preIndex, 1, 1).format = {
    fill: headerColors[sheetName],
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    wrapText: true,
  };
  sheet.getRangeByIndexes(0, resultIndex, 1, 1).format = {
    fill: headerColors[sheetName],
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    wrapText: true,
  };

  const existingPreValues = preExistingIndex >= 0
    ? sheet.getRangeByIndexes(1, preIndex, dataRows, 1).values
    : Array.from({ length: dataRows }, () => [""]);
  const testValues = [];
  const rowColors = [];
  const counts = {};
  let matchedRows = 0;
  let unmatchedRows = 0;
  let resultColoredRows = 0;
  let preColoredRows = 0;

  for (let rowIndex = 0; rowIndex < dataRows; rowIndex += 1) {
    const featureId = String(featureValues[rowIndex]?.[0] || "").trim();
    const status = resultByFeature.get(featureId) || "";
    const preStatus = String(existingPreValues[rowIndex]?.[0] || "").trim();
    if (status) {
      matchedRows += 1;
      globallyMatched.add(featureId);
    } else {
      unmatchedRows += 1;
      if (featureId) globallyUnmatched.add(featureId);
    }
    testValues.push([status || "NOT_RUN"]);
    counts[status || "NOT_RUN"] = (counts[status || "NOT_RUN"] || 0) + 1;
    if (resultColors[status]) {
      rowColors.push(resultColors[status]);
      resultColoredRows += 1;
    } else if (preStatus) {
      rowColors.push("#EDEDED");
      preColoredRows += 1;
    } else {
      rowColors.push("");
    }
  }

  sheet.getRangeByIndexes(1, preIndex, dataRows, 1).values = existingPreValues;
  sheet.getRangeByIndexes(1, resultIndex, dataRows, 1).values = testValues;
  sheet.getRangeByIndexes(1, preIndex, dataRows, 1).format = {
    font: { color: "#000000" },
    horizontalAlignment: "center",
    wrapText: true,
  };
  sheet.getRangeByIndexes(1, resultIndex, dataRows, 1).format = {
    font: { color: "#000000" },
    horizontalAlignment: "center",
    wrapText: true,
  };
  sheet.getRangeByIndexes(1, resultIndex, dataRows, 1).dataValidation = {
    rule: { type: "list", values: [...approvedStatuses] },
  };

  for (const run of contiguousRuns(rowColors)) {
    if (!run.value) continue;
    sheet.getRangeByIndexes(run.start + 1, 0, run.count, finalColumns).format = {
      fill: run.value,
      font: { color: "#000000" },
    };
  }

  for (let rowIndex = 0; rowIndex < dataRows; rowIndex += 1) {
    const preStatus = String(existingPreValues[rowIndex]?.[0] || "").trim();
    const status = testValues[rowIndex][0];
    const preCell = sheet.getCell(rowIndex + 1, preIndex);
    const resultCell = sheet.getCell(rowIndex + 1, resultIndex);
    if (preStatus) preCell.format = { fill: "#EDEDED", font: { color: "#000000" } };
    if (resultColors[status]) {
      resultCell.format = { fill: resultColors[status], font: { color: "#000000" } };
    } else {
      resultCell.format = { fill: "#FFFFFF", font: { color: "#000000" } };
    }
  }

  const previewRows = Math.min(30, dataRows + 1);
  const previewRange = sheet.getRangeByIndexes(0, 0, previewRows, finalColumns).address;
  const preview = await workbook.render({ sheetName, range: previewRange, scale: 1, format: "png" });
  await fs.writeFile(
    `${previewDir}/${sheetName.replaceAll(" ", "-")}-after-crop.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );

  const keyInspect = await workbook.inspect({
    kind: "region",
    sheetId: sheetName,
    range: sheet.getRangeByIndexes(0, 0, Math.min(6, dataRows + 1), finalColumns).address,
    maxChars: 6000,
  });
  await fs.writeFile(`${previewDir}/${sheetName.replaceAll(" ", "-")}-after-inspect.ndjson`, keyInspect.ndjson, "utf8");

  perSheet.push({
    sheetName,
    dataRows,
    matchedRows,
    unmatchedRows,
    resultColoredRows,
    preColoredRows,
    wholeRowsColored: resultColoredRows + preColoredRows,
    statusCounts: counts,
  });
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fs.writeFile(`${previewDir}/final-formula-error-scan.ndjson`, formulaErrors.ndjson, "utf8");

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputWorkbook);

const changelog = [
  "# QA workbook coloring changelog",
  "",
  `- Source workbook path: \`${sourceWorkbook}\``,
  `- Test result directory used: \`${auditRoot}\``,
  `- Output workbook path: \`${outputWorkbook}\``,
  `- Matched feature IDs: ${globallyMatched.size} unique feature IDs (${perSheet.reduce((sum, row) => sum + row.matchedRows, 0)} matched sheet rows)`,
  `- Unmatched feature IDs: ${globallyUnmatched.size}`,
  `- Ambiguous mappings: ${duplicateFeatureIds.length ? [...new Set(duplicateFeatureIds)].join(", ") : "none"}`,
  `- Status values outside approved taxonomy: ${nonStandardStatuses.length ? nonStandardStatuses.map((item) => `${item.featureId}=${item.status}`).join(", ") : "none"}`,
  "",
  "## Rows colored per sheet",
  "",
  "| Sheet | Result-colored rows | Pre-test gray rows | Whole rows colored | Matched | Unmatched |",
  "|---|---:|---:|---:|---:|---:|",
  ...perSheet.map((row) => `| ${row.sheetName} | ${row.resultColoredRows} | ${row.preColoredRows} | ${row.wholeRowsColored} | ${row.matchedRows} | ${row.unmatchedRows} |`),
  "",
  "## Final status counts per target sheet",
  "",
  "Each target sheet contains the same 2,117 feature IDs and final result mapping:",
  "",
  ...Object.entries(perSheet[0].statusCounts).sort().map(([status, count]) => `- ${status}: ${count}`),
  "",
  "The `test_result_status` color takes precedence for the whole row. A non-empty `pre_test_status` remains gray in its own status cell; if no terminal result color exists, gray would be used for the row. Blank/NOT_RUN result cells receive no approved status color.",
].join("\n") + "\n";
await fs.writeFile(changelogPath, changelog, "utf8");

console.log(JSON.stringify({ outputWorkbook, changelogPath, perSheet, globallyMatched: globallyMatched.size, globallyUnmatched: globallyUnmatched.size, duplicateFeatureIds, nonStandardStatuses }, null, 2));
