import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263";
const outputPath = `${outputDir}/ai4research final l1 l2 feature deliverable.xlsx`;

const text = (value) => (value == null ? "" : String(value));
const hasContent = (value) => text(value).trim() !== "";
const normalizeHeader = (value) => text(value).toLowerCase().replace(/[\s_]+/g, " ").trim();
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

const stripLeadingNumber = (value) => text(value).replace(/^\s*\d+\s*[.)]\s*/, "").trimStart();

const splitNameDescription = (value, { numbered = false } = {}) => {
  const raw = text(value).trim();
  if (!raw) return { name: null, description: null };
  const lines = raw.split(/\r?\n/);
  const firstIndex = lines.findIndex((line) => line.trim() !== "");
  if (firstIndex < 0) return { name: null, description: null };
  const firstLine = lines[firstIndex].trim();
  const rest = lines.slice(firstIndex + 1).join("\n").trim();
  return {
    name: numbered ? stripLeadingNumber(firstLine) : firstLine,
    description: rest || null,
  };
};

const combineDescription = (existing, moved) => {
  const a = text(existing).trim();
  const b = text(moved).trim();
  if (!a) return b || null;
  if (!b) return a || null;
  if (a === b || a.includes(b)) return a;
  if (b.includes(a)) return b;
  return `${a}\n\n${b}`;
};

const findColumns = (headers) => {
  const normalized = headers.map(normalizeHeader);
  const l1Col = normalized.findIndex((h) => h.includes("level 1") && h.includes("feature") && !h.includes("description") && !h.includes("annotation"));
  let l1DescCol = normalized.findIndex((h) => h.includes("level 1") && (h.includes("description") || h.includes("annotation")));
  if (l1DescCol < 0 && l1Col >= 0 && !hasContent(headers[l1Col + 1])) l1DescCol = l1Col + 1;
  const l2Col = normalized.findIndex((h) => h.includes("level 2") && h.includes("feature") && !h.includes("description"));
  let l2DescCol = normalized.findIndex((h) => h.includes("level 2") && h.includes("description"));
  if (l2DescCol < 0 && l2Col >= 0 && !hasContent(headers[l2Col + 1])) l2DescCol = l2Col + 1;
  return { l1Col, l1DescCol, l2Col, l2DescCol };
};

const sourceInput = await FileBlob.load(inputPath);
const sourceWorkbook = await SpreadsheetFile.importXlsx(sourceInput);
const outputWorkbook = Workbook.create();

const summary = [];

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

  const normalizedRows = sourceValues.map((row) => Array.from({ length: lastContentCol }, (_, i) => row[i] ?? null));
  const compactRows = normalizedRows.filter((row, index) => index === 0 || row.some(hasContent));
  const { l1Col, l1DescCol, l2Col, l2DescCol } = findColumns(compactRows[0]);

  if (l1DescCol >= 0) compactRows[0][l1DescCol] = "level 1 feature description";
  if (l2DescCol >= 0) compactRows[0][l2DescCol] = "level 2 feature description";

  for (let r = 1; r < compactRows.length; r += 1) {
    if (l1Col >= 0 && l1DescCol >= 0 && hasContent(compactRows[r][l1Col])) {
      const split = splitNameDescription(compactRows[r][l1Col]);
      compactRows[r][l1Col] = split.name;
      compactRows[r][l1DescCol] = combineDescription(compactRows[r][l1DescCol], split.description);
    }

    if (l2Col >= 0 && l2DescCol >= 0 && hasContent(compactRows[r][l2Col])) {
      const split = splitNameDescription(compactRows[r][l2Col], { numbered: true });
      compactRows[r][l2Col] = split.name;
      compactRows[r][l2DescCol] = combineDescription(compactRows[r][l2DescCol], split.description);
    }
  }

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

  if (colCount >= 2) sheet.getRange(`B1:${lastCol}${rowCount}`).format.columnWidthPx = 440;
  sheet.getRange(`A1:A${rowCount}`).format.columnWidthPx = 130;
  header.format.rowHeightPx = 48;
  if (rowCount >= 2) sheet.getRange(`A2:${lastCol}${rowCount}`).format.rowHeightPx = 300;

  sheet.getRange(`A1:A${rowCount}`).format.font = { bold: true };
  sheet.getRange("A1").format.font = { bold: true, color: "#FFFFFF" };

  const l1StartRows = [];
  if (l1Col >= 0) {
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
    for (let i = 0; i < l1StartRows.length - 1; i += 1) {
      const start = l1StartRows[i];
      const end = l1StartRows[i + 1] - 1;
      if (end > start) sheet.getRange(`${colLetter(l1Col + 1)}${start}:${colLetter(l1Col + 1)}${end}`).merge();
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
    l1DescriptionColumn: l1DescCol + 1,
    l2Column: l2Col + 1,
    l2DescriptionColumn: l2DescCol + 1,
    l1MergeCount: Math.max(0, l1StartRows.length - 1),
  });
}

const formulaErrors = await outputWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(formulaErrors.ndjson);
console.log(JSON.stringify({ summary }, null, 2));

await fs.mkdir(outputDir, { recursive: true });
for (const sheet of outputWorkbook.worksheets.items) {
  const values = sheet.getUsedRange(false).values;
  const range = `A1:${colLetter(values[0].length)}${values.length}`;
  const rendered = await outputWorkbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${sheet.name.replaceAll(" ", "_")}_requested_updates.png`, new Uint8Array(await rendered.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(outputWorkbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }, null, 2));
