import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const auditRoot = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
const inputPath = `${auditRoot}/control-material/ai4research_recursive_feature_split_qa_execution.xlsx`;
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheetInspect = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 12000 });
console.log(sheetInspect.ndjson);

const targetSheets = ["Entrypoint Map", "Existing Test Map", "Missing Test Plan", "Pass Fail Criteria"];
for (const sheetName of targetSheets) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange();
  console.log(JSON.stringify({ sheet: sheetName, usedAddress: used.address, rowCount: used.rowCount, columnCount: used.columnCount }));
  const rows = Math.min(6, used.rowCount);
  const cols = Math.min(18, used.columnCount);
  const region = await workbook.inspect({
    kind: "region",
    sheetId: sheetName,
    range: sheet.getRangeByIndexes(0, 0, rows, cols).address,
    maxChars: 8000,
  });
  console.log(region.ndjson);
  const styles = await workbook.inspect({
    kind: "computedStyle",
    sheetId: sheetName,
    range: sheet.getRangeByIndexes(0, 0, Math.min(3, rows), cols).address,
    maxChars: 5000,
  });
  console.log(styles.ndjson);
  const previewRange = sheet.getRangeByIndexes(0, 0, Math.min(30, used.rowCount), used.columnCount).address;
  const preview = await workbook.render({ sheetName, range: previewRange, scale: 1, format: "png" });
  await fs.writeFile(`${auditRoot}/tmp/workbook-runtime/${sheetName.replaceAll(" ", "-")}-before-crop.png`, new Uint8Array(await preview.arrayBuffer()));
}
