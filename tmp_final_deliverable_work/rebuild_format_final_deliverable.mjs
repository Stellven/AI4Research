import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263";
const outputPath = `${outputDir}/ai4research final l1 l2 feature deliverable.xlsx`;

const text = (value) => (value == null ? "" : String(value));
const hasContent = (value) => text(value).trim() !== "";
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
const normalizeHeader = (value) => text(value).toLowerCase().replace(/[\s_]+/g, " ").trim();
const stripLeadingNumber = (value) => text(value).replace(/^\s*\d+\s*[.)]\s*/, "").trimStart();

const sourceInput = await FileBlob.load(inputPath);
const sourceWorkbook = await SpreadsheetFile.importXlsx(sourceInput);
const outputWorkbook = Workbook.create();

const summary = [];
let globalMaxChars = 0;

for (const sourceSheet of sourceWorkbook.worksheets.items) {
  const sourceValues = sourceSheet.getUsedRange(false).values;
  if (!sourceValues || sourceValues.length === 0) continue;

  let lastContentCol = 0;
  for (const row of sourceValues) {
    for (let c = 0; c < row.length; c += 1) {
      if (hasContent(row[c])) lastContentCol = Math.max(lastContentCol, c + 1);
    }
  }
  if (lastContentCol === 0) continue;

  const normalizedRows = sourceValues.map((row) => (
    Array.from({ length: lastContentCol }, (_, i) => row[i] ?? null)
  ));
  const compactRows = normalizedRows.filter((row, idx) => idx === 0 || row.some(hasContent));

  const headers = compactRows[0].map(normalizeHeader);
  const l1Col = headers.findIndex((h) => h.includes("level 1") && h.includes("feature") && !h.includes("description") && !h.includes("annotation"));
  const l2Col = headers.findIndex((h) => h.includes("level 2") && h.includes("feature") && !h.includes("description"));

  let l2Number = 0;
  let currentL1 = null;
  for (let r = 1; r < compactRows.length; r += 1) {
    if (l1Col >= 0 && hasContent(compactRows[r][l1Col])) {
      const nextL1 = text(compactRows[r][l1Col]).trim();
      if (nextL1 !== currentL1) {
        currentL1 = nextL1;
        l2Number = 0;
      }
    }
    if (l2Col >= 0 && hasContent(compactRows[r][l2Col])) {
      l2Number += 1;
      compactRows[r][l2Col] = `${l2Number}. ${stripLeadingNumber(compactRows[r][l2Col])}`;
    }
  }

  for (const row of compactRows) {
    for (const cell of row) {
      globalMaxChars = Math.max(globalMaxChars, text(cell).length);
    }
  }

  const sheet = outputWorkbook.worksheets.add(sourceSheet.name);
  const rowCount = compactRows.length;
  const colCount = lastContentCol;
  const lastCol = colLetter(colCount);
  sheet.getRange(`A1:${lastCol}${rowCount}`).values = compactRows;

  const all = sheet.getRange(`A1:${lastCol}${rowCount}`);
  all.format = {
    font: { bold: false },
    horizontalAlignment: "center",
    verticalAlignment: "middle",
    wrapText: true,
  };
  all.format.borders = { preset: "all", style: "thin", color: "#D9D9D9" };

  const header = sheet.getRange(`A1:${lastCol}1`);
  header.format = {
    font: { bold: false, color: "#FFFFFF" },
    fill: "#1F4E79",
    horizontalAlignment: "center",
    verticalAlignment: "middle",
    wrapText: true,
  };
  header.format.borders = { preset: "all", style: "thin", color: "#FFFFFF" };

  if (colCount >= 2) {
    sheet.getRange(`B1:${lastCol}${rowCount}`).format.columnWidthPx = 440;
  }
  sheet.getRange(`A1:A${rowCount}`).format.columnWidthPx = 130;
  header.format.rowHeightPx = 48;
  if (rowCount >= 2) {
    sheet.getRange(`A2:${lastCol}${rowCount}`).format.rowHeightPx = 300;
  }

  if (l1Col >= 0) {
    const l1StartRows = [];
    let lastL1 = null;
    for (let r = 1; r < compactRows.length; r += 1) {
      if (!hasContent(compactRows[r][l1Col])) continue;
      const nextL1 = text(compactRows[r][l1Col]).trim();
      if (nextL1 !== lastL1) {
        l1StartRows.push(r + 1);
        lastL1 = nextL1;
      }
    }
    for (const rowNumber of l1StartRows) {
      if (rowNumber <= 2) continue;
      sheet.getRange(`A${rowNumber}:${lastCol}${rowNumber}`).format.borders = {
        top: { style: "medium", color: "#000000" },
      };
    }
  }

  summary.push({
    sheet: sourceSheet.name,
    beforeRows: normalizedRows.length,
    afterRows: rowCount,
    blankRowsRemoved: normalizedRows.length - rowCount,
    beforeNonEmptyCells: normalizedRows.flat().filter(hasContent).length,
    afterNonEmptyCells: compactRows.flat().filter(hasContent).length,
    columnsPreservedThrough: lastCol,
    l1Column: l1Col + 1,
    l2Column: l2Col + 1,
  });
}

const formulaErrors = await outputWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(formulaErrors.ndjson);
console.log(JSON.stringify({ summary, globalMaxChars }, null, 2));

await fs.mkdir(outputDir, { recursive: true });
for (const sheet of outputWorkbook.worksheets.items) {
  const values = sheet.getUsedRange(false).values;
  const range = `A1:${colLetter(values[0].length)}${values.length}`;
  const rendered = await outputWorkbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${sheet.name.replaceAll(" ", "_")}_rebuilt_formatted.png`, new Uint8Array(await rendered.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(outputWorkbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }, null, 2));
