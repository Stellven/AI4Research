import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263";
const outputPath = `${outputDir}/ai4research final l1 l2 feature deliverable.xlsx`;

const nodeText = (value) => (value == null ? "" : String(value));
const hasContent = (value) => nodeText(value).trim() !== "";
const colLetter = (colNumber) => {
  let n = colNumber;
  let out = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    out = String.fromCharCode(65 + r) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
};
const normalizeHeader = (value) => nodeText(value).toLowerCase().replace(/[\s_]+/g, " ").trim();
const stripLeadingNumber = (value) => nodeText(value).replace(/^\s*\d+\s*[.)]\s*/, "").trimStart();

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = [];
let globalMaxChars = 0;

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange(false);
  const rawValues = used.values;
  if (!rawValues || rawValues.length === 0) continue;

  const colCount = Math.max(...rawValues.map((row) => row.length));
  const rows = rawValues.map((row) => Array.from({ length: colCount }, (_, i) => row[i] ?? null));
  const header = rows[0];
  const headers = header.map(normalizeHeader);

  const l1Col = headers.findIndex((h) => (
    (h === "level 1 feature" || h === "level 1 feature annotation" || h === "level 1 feature description" || h === "level 1 feature")
    || (h.includes("level 1") && h.includes("feature") && !h.includes("description") && !h.includes("annotation"))
  ));
  const l2Col = headers.findIndex((h) => h.includes("level 2") && h.includes("feature") && !h.includes("description"));

  const beforeRows = rows.length;
  const beforeNonEmptyCells = rows.flat().filter(hasContent).length;
  const compactRows = rows.filter((row, idx) => idx === 0 || row.some(hasContent));

  let l2Number = 0;
  let sawL1 = false;
  for (let r = 1; r < compactRows.length; r += 1) {
    if (l1Col >= 0 && hasContent(compactRows[r][l1Col])) {
      l2Number = 0;
      sawL1 = true;
    }
    if (l2Col >= 0 && hasContent(compactRows[r][l2Col])) {
      if (!sawL1) sawL1 = true;
      l2Number += 1;
      compactRows[r][l2Col] = `${l2Number}. ${stripLeadingNumber(compactRows[r][l2Col])}`;
    }
  }

  for (const row of compactRows) {
    for (const cell of row) {
      globalMaxChars = Math.max(globalMaxChars, nodeText(cell).length);
    }
  }

  const lastCol = colLetter(colCount);
  const oldRowCount = rows.length;
  const newRowCount = compactRows.length;
  const oldRange = sheet.getRange(`A1:${lastCol}${oldRowCount}`);
  oldRange.unmerge();
  oldRange.clear({ applyTo: "all" });
  sheet.getRange(`A1:${lastCol}${newRowCount}`).values = compactRows;

  const all = sheet.getRange(`A1:${lastCol}${newRowCount}`);
  all.format = {
    font: { bold: false },
    horizontalAlignment: "center",
    verticalAlignment: "middle",
    wrapText: true,
  };
  all.format.borders = { preset: "all", style: "thin", color: "#D9D9D9" };

  sheet.getRange(`A1:${lastCol}1`).format = {
    font: { bold: false, color: "#FFFFFF" },
    fill: "#1F4E79",
    horizontalAlignment: "center",
    verticalAlignment: "middle",
    wrapText: true,
  };
  sheet.getRange(`A1:${lastCol}1`).format.borders = { preset: "all", style: "thin", color: "#FFFFFF" };

  if (colCount >= 2) {
    sheet.getRange(`B1:${lastCol}${newRowCount}`).format.columnWidthPx = 440;
  }
  if (newRowCount >= 2) {
    sheet.getRange(`A2:${lastCol}${newRowCount}`).format.rowHeightPx = 300;
  }
  sheet.getRange(`A1:A${newRowCount}`).format.columnWidthPx = 130;
  sheet.getRange(`A1:${lastCol}1`).format.rowHeightPx = 48;

  if (l1Col >= 0) {
    const l1StartRows = [];
    for (let r = 1; r < compactRows.length; r += 1) {
      if (hasContent(compactRows[r][l1Col])) l1StartRows.push(r + 1);
    }
    for (const rowNumber of l1StartRows) {
      if (rowNumber <= 2) continue;
      sheet.getRange(`A${rowNumber}:${lastCol}${rowNumber}`).format.borders = {
        top: { style: "medium", color: "#000000" },
      };
    }
  }

  const afterNonEmptyCells = compactRows.flat().filter(hasContent).length;
  summary.push({
    sheet: sheet.name,
    beforeRows,
    afterRows: newRowCount,
    blankRowsRemoved: beforeRows - newRowCount,
    beforeNonEmptyCells,
    afterNonEmptyCells,
    l1Column: l1Col + 1,
    l2Column: l2Col + 1,
  });
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(formulaErrors.ndjson);
console.log(JSON.stringify({ summary, globalMaxChars }, null, 2));

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange(false);
  const values = used.values;
  const colCount = Math.max(...values.map((row) => row.length));
  const rowCount = values.length;
  const range = `A1:${colLetter(colCount)}${rowCount}`;
  const rendered = await workbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${sheet.name.replaceAll(" ", "_")}_formatted.png`, new Uint8Array(await rendered.arrayBuffer()));
}

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }, null, 2));
