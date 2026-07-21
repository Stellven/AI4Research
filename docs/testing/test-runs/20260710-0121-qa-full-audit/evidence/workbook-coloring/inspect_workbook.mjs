import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const auditDir = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
const sourcePath = `${auditDir}/control-material/ai4research_recursive_feature_split_qa_execution.xlsx`;
const outputDir = fileURLToPath(new URL("./previews-before/", import.meta.url));

await fs.mkdir(outputDir, { recursive: true });
const input = await FileBlob.load(sourcePath);
const workbook = await SpreadsheetFile.importXlsx(input);

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 20000,
  tableMaxRows: 8,
  tableMaxCols: 40,
  tableMaxCellChars: 120,
});
await fs.writeFile(new URL("./workbook-overview.ndjson", import.meta.url), overview.ndjson, "utf8");

const sheetInfo = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 10000,
});
await fs.writeFile(new URL("./sheet-info.ndjson", import.meta.url), sheetInfo.ndjson, "utf8");

const renderRanges = {
  "Recursive Split": "A1:I25",
  Summary: "A1:H82",
  "Split Rules": "A1:B8",
  "Feature IDs": "A1:N25",
  "Function Inventory": "A1:N25",
  "Entrypoint Map": "A1:L25",
  "Existing Test Map": "A1:M25",
  "Missing Test Plan": "A1:L25",
  "Pass Fail Criteria": "A1:K25",
  "Severity Rubric": "A1:E6",
};

for (const [sheetName, range] of Object.entries(renderRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    `${outputDir}/${sheetName.replaceAll(" ", "_")}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

for (const sheetName of ["Entrypoint Map", "Existing Test Map", "Missing Test Plan", "Pass Fail Criteria"]) {
  const table = await workbook.inspect({
    kind: "table",
    sheetId: sheetName,
    range: "A1:AZ12",
    include: "values,formulas",
    tableMaxRows: 12,
    tableMaxCols: 52,
    maxChars: 20000,
  });
  await fs.writeFile(new URL(`./${sheetName.replaceAll(" ", "_")}-table.ndjson`, import.meta.url), table.ndjson, "utf8");

  const styles = await workbook.inspect({
    kind: "computedStyle",
    sheetId: sheetName,
    range: "A1:AZ6",
    maxChars: 12000,
  });
  await fs.writeFile(new URL(`./${sheetName.replaceAll(" ", "_")}-styles.ndjson`, import.meta.url), styles.ndjson, "utf8");
}

console.log(sheetInfo.ndjson);
