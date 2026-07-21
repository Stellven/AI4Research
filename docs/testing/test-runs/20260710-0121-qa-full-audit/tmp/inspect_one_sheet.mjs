import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, outputDir, rawIndex] = process.argv.slice(2);
const index = Number(rawIndex);
if (!inputPath || !outputDir || !Number.isInteger(index)) {
  throw new Error("usage: inspect_one_sheet.mjs INPUT_XLSX OUTPUT_DIR SHEET_INDEX");
}

const columnName = (indexValue) => {
  let value = indexValue + 1;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
};

await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItemAt(index);
const used = sheet.getUsedRange();
const values = used ? used.values : [];
const formulas = used ? used.formulas : [];
const rowCount = values.length;
const columnCount = values.reduce((max, row) => Math.max(max, row.length), 0);
const safeName = `${String(index + 1).padStart(2, "0")}-${sheet.name.replace(/[^A-Za-z0-9._-]+/g, "_")}`;
await fs.writeFile(
  path.join(outputDir, `${safeName}.data.json`),
  JSON.stringify({ values, formulas }, null, 2),
  "utf8",
);

const inspect = await workbook.inspect({
  kind: "region,formula,computedStyle",
  sheetId: sheet.name,
  range: rowCount && columnCount ? `A1:${columnName(columnCount - 1)}${Math.min(rowCount, 80)}` : undefined,
  maxChars: 40000,
  tableMaxRows: 80,
  tableMaxCols: 80,
  tableMaxCellChars: 500,
  options: { maxResults: 1000 },
});
await fs.writeFile(path.join(outputDir, `${safeName}.inspect.ndjson`), inspect.ndjson, "utf8");

const previewRanges = [];
if (rowCount > 0 && columnCount > 0) {
  previewRanges.push([1, Math.min(rowCount, 60)]);
  if (rowCount > 60) previewRanges.push([Math.max(1, rowCount - 19), rowCount]);
}
const previewFiles = [];
for (const [startRow, endRow] of previewRanges) {
  const range = `A${startRow}:${columnName(columnCount - 1)}${endRow}`;
  const preview = await workbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
  const previewFile = `${safeName}-sample-${String(startRow).padStart(4, "0")}-${String(endRow).padStart(4, "0")}.png`;
  await fs.writeFile(path.join(outputDir, previewFile), new Uint8Array(await preview.arrayBuffer()));
  previewFiles.push(previewFile);
}
console.log(JSON.stringify({ index, name: sheet.name, rowCount, columnCount, safeName, previewFiles }));
