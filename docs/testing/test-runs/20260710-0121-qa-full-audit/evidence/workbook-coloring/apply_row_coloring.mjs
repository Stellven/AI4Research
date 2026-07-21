import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const auditDir = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
const inputPath = `${auditDir}/ai4research_recursive_feature_split_qa_execution_colored.xlsx`;
const outputPath = `${auditDir}/ai4research_recursive_feature_split_qa_execution_row_colored.xlsx`;
const evidenceDir = fileURLToPath(new URL("./", import.meta.url));
const previewDir = `${evidenceDir}/previews-row-colored`;

const targetSheets = [
  "Entrypoint Map",
  "Existing Test Map",
  "Missing Test Plan",
  "Pass Fail Criteria",
];

const allSheetRanges = {
  "Recursive Split": "A1:I25",
  Summary: "A1:H82",
  "Split Rules": "A1:B8",
  "Feature IDs": "A1:N25",
  "Function Inventory": "A1:N25",
  "Entrypoint Map": "A1:N25",
  "Existing Test Map": "A1:O25",
  "Missing Test Plan": "A1:N25",
  "Pass Fail Criteria": "A1:M25",
  "Severity Rubric": "A1:E6",
};

const statusColors = {
  PASS: "#C6EFCE",
  FAIL: "#FFC7CE",
  BLOCKED_EXPECTED: "#DDEBF7",
  SKIPPED_ENV: "#DDEBF7",
  INCONCLUSIVE_EXPECTED: "#FCE4D6",
  FLAKY: "#FCE4D6",
  SKIPPED_NA: "#F2F2F2",
};

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
  for (let index = 1; index < sorted.length; index += 1) {
    if (sorted[index] === end + 1) {
      end = sorted[index];
    } else {
      runs.push([start, end]);
      start = sorted[index];
      end = sorted[index];
    }
  }
  runs.push([start, end]);
  return runs;
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const snapshots = {};
for (const sheetName of Object.keys(allSheetRanges)) {
  const used = workbook.worksheets.getItem(sheetName).getUsedRange();
  snapshots[sheetName] = {
    rows: used.values.length,
    cols: used.values[0]?.length ?? 0,
    values: used.values,
    formulas: used.formulas,
  };
}

const report = {
  input_workbook: inputPath,
  output_workbook: outputPath,
  sheets: {},
};

for (const sheetName of targetSheets) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange();
  const values = used.values;
  const headers = values[0].map((value) => String(value ?? "").trim());
  const statusColumn = headers.indexOf("test_result_status");
  if (statusColumn < 0) throw new Error(`${sheetName}: test_result_status column not found`);
  const lastColumnLetter = columnName(headers.length - 1);
  const rowsByStatus = new Map(Object.keys(statusColors).map((status) => [status, []]));
  let untouchedNotRunRows = 0;
  let unknownStatusRows = 0;

  for (let dataIndex = 1; dataIndex < values.length; dataIndex += 1) {
    const status = String(values[dataIndex][statusColumn] ?? "").trim();
    const excelRow = dataIndex + 1;
    if (rowsByStatus.has(status)) {
      rowsByStatus.get(status).push(excelRow);
    } else if (status === "NOT_RUN" || status === "") {
      untouchedNotRunRows += 1;
    } else {
      unknownStatusRows += 1;
    }
  }

  for (const [status, rows] of rowsByStatus.entries()) {
    for (const [startRow, endRow] of contiguousRuns(rows)) {
      sheet.getRange(`A${startRow}:${lastColumnLetter}${endRow}`).format.fill = statusColors[status];
    }
  }

  report.sheets[sheetName] = {
    used_range: `A1:${lastColumnLetter}${values.length}`,
    rows_colored: [...rowsByStatus.values()].reduce((sum, rows) => sum + rows.length, 0),
    rows_left_uncolored_not_run_or_blank: untouchedNotRunRows,
    rows_with_unknown_status_left_unchanged: unknownStatusRows,
    status_counts: Object.fromEntries([...rowsByStatus.entries()].map(([status, rows]) => [status, rows.length])),
  };
}

await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, range] of Object.entries(allSheetRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    `${previewDir}/${sheetName.replaceAll(" ", "_")}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const exportedInput = await FileBlob.load(outputPath);
const exportedWorkbook = await SpreadsheetFile.importXlsx(exportedInput);
const formulaErrors = await exportedWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "row-colored workbook formula error scan",
});

report.verification = {
  formula_error_scan: formulaErrors.ndjson,
  original_content_preserved: {},
};
for (const [sheetName, snapshot] of Object.entries(snapshots)) {
  const originalArea = exportedWorkbook.worksheets
    .getItem(sheetName)
    .getRangeByIndexes(0, 0, snapshot.rows, snapshot.cols);
  report.verification.original_content_preserved[sheetName] = {
    values_preserved: JSON.stringify(originalArea.values) === JSON.stringify(snapshot.values),
    formulas_preserved: JSON.stringify(originalArea.formulas) === JSON.stringify(snapshot.formulas),
  };
}
report.verification.all_original_content_preserved = Object.values(
  report.verification.original_content_preserved,
).every((entry) => entry.values_preserved && entry.formulas_preserved);

const drawings = await exportedWorkbook.inspect({ kind: "drawing", maxChars: 10000 });
report.verification.drawings = drawings.ndjson;

await fs.writeFile(`${evidenceDir}/row-coloring-summary.json`, JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
