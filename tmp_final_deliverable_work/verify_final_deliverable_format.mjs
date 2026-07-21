import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263/ai4research final l1 l2 feature deliverable.xlsx";

const valueText = (value) => (value == null ? "" : String(value));
const hasContent = (value) => valueText(value).trim() !== "";
const normalizeHeader = (value) => valueText(value).toLowerCase().replace(/[\s_]+/g, " ").trim();
const numberPrefix = (value) => {
  const match = valueText(value).match(/^\s*(\d+)\s*[.)]\s+/);
  return match ? Number(match[1]) : null;
};

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = [];
for (const sheet of workbook.worksheets.items) {
  const values = sheet.getUsedRange(false).values;
  const headers = values[0].map(normalizeHeader);
  const l1Col = headers.findIndex((h) => h.includes("level 1") && h.includes("feature") && !h.includes("description") && !h.includes("annotation"));
  const l2Col = headers.findIndex((h) => h.includes("level 2") && h.includes("feature") && !h.includes("description"));
  const blankRows = [];
  const l2Errors = [];
  let expected = 0;
  let currentL1 = null;
  for (let r = 1; r < values.length; r += 1) {
    const row = values[r];
    if (!row.some(hasContent)) blankRows.push(r + 1);
    if (l1Col >= 0 && hasContent(row[l1Col])) {
      const nextL1 = valueText(row[l1Col]).trim();
      if (nextL1 !== currentL1) {
        currentL1 = nextL1;
        expected = 0;
      }
    }
    if (l2Col >= 0 && hasContent(row[l2Col])) {
      expected += 1;
      const actual = numberPrefix(row[l2Col]);
      if (actual !== expected) {
        l2Errors.push({ row: r + 1, expected, actual, value: valueText(row[l2Col]).slice(0, 100) });
      }
    }
  }
  summary.push({ sheet: sheet.name, rows: values.length, cols: values[0].length, blankRows, l1Col: l1Col + 1, l2Col: l2Col + 1, l2Errors });
}

console.log(JSON.stringify(summary, null, 2));
console.log((await workbook.inspect({
  kind: "computedStyle",
  sheetId: "Workflow Features",
  range: "A1:F6",
  maxChars: 8000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "computedStyle",
  sheetId: "Foundation Features",
  range: "A1:I6",
  maxChars: 8000,
})).ndjson);
console.log((await workbook.inspect({
  kind: "computedStyle",
  sheetId: "Vertical Features",
  range: "A1:D6",
  maxChars: 8000,
})).ndjson);
