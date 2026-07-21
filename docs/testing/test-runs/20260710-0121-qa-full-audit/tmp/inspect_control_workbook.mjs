import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const failCompactly = (error) => {
  const payload = {
    name: error?.name ?? "Error",
    message: error?.message ?? String(error),
    cause: error?.cause ? String(error.cause) : null,
  };
  console.error(JSON.stringify(payload, null, 2));
  process.exit(1);
};
process.on("uncaughtException", failCompactly);
process.on("unhandledRejection", failCompactly);

const [inputPath, outputDir] = process.argv.slice(2);
if (!inputPath || !outputDir) {
  throw new Error("usage: inspect_control_workbook.mjs INPUT_XLSX OUTPUT_DIR");
}

await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const overview = await workbook.inspect({
  kind: "workbook,sheet,table,definedName,drawing",
  maxChars: 20000,
  tableMaxRows: 8,
  tableMaxCols: 24,
  tableMaxCellChars: 160,
});
await fs.writeFile(path.join(outputDir, "workbook-overview.ndjson"), overview.ndjson, "utf8");

const sheets = [];
const columnName = (index) => {
  let value = index + 1;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
};
for (let i = 0; i < workbook.worksheets.items.length; i += 1) {
  const sheet = workbook.worksheets.getItemAt(i);
  const used = sheet.getUsedRange();
  const values = used ? used.values : [];
  const formulas = used ? used.formulas : [];
  const rowCount = values.length;
  const columnCount = values.reduce((max, row) => Math.max(max, row.length), 0);
  const sheetInfo = await workbook.inspect({
    kind: "region,formula,computedStyle",
    sheetId: sheet.name,
    maxChars: 50000,
    tableMaxRows: 500,
    tableMaxCols: 80,
    tableMaxCellChars: 500,
    options: { maxResults: 2000 },
  });
  const safeName = `${String(i + 1).padStart(2, "0")}-${sheet.name.replace(/[^A-Za-z0-9._-]+/g, "_")}`;
  await fs.writeFile(path.join(outputDir, `${safeName}.inspect.ndjson`), sheetInfo.ndjson, "utf8");
  await fs.writeFile(
    path.join(outputDir, `${safeName}.data.json`),
    JSON.stringify({ values, formulas }, null, 2),
    "utf8",
  );
  const previewFiles = [];
  const rowsPerPreview = 60;
  if (rowCount > 0 && columnCount > 0) {
    for (let startRow = 1; startRow <= rowCount; startRow += rowsPerPreview) {
      const endRow = Math.min(rowCount, startRow + rowsPerPreview - 1);
      const range = `A${startRow}:${columnName(columnCount - 1)}${endRow}`;
      const preview = await workbook.render({
        sheetName: sheet.name,
        range,
        scale: 1,
        format: "png",
      });
      const previewFile = `${safeName}-rows-${String(startRow).padStart(4, "0")}-${String(endRow).padStart(4, "0")}.png`;
      await fs.writeFile(
        path.join(outputDir, previewFile),
        new Uint8Array(await preview.arrayBuffer()),
      );
      previewFiles.push(previewFile);
    }
  }
  sheets.push({
    index: i + 1,
    name: sheet.name,
    usedRangeAvailable: Boolean(used),
    rowCount,
    columnCount,
    safeName,
    previewFiles,
  });
}
await fs.writeFile(path.join(outputDir, "sheet-manifest.json"), JSON.stringify(sheets, null, 2), "utf8");
console.log(JSON.stringify({ sheetCount: sheets.length, sheets }, null, 2));
