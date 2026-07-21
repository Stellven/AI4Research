import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const auditDir = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
const workbookPath = `${auditDir}/ai4research_recursive_feature_split_qa_execution_row_colored.xlsx`;
const outputDir = fileURLToPath(new URL("./previews-row-colored-final/", import.meta.url));
const renderRanges = {
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

await fs.mkdir(outputDir, { recursive: true });
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

for (const [sheetName, range] of Object.entries(renderRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    `${outputDir}/${sheetName.replaceAll(" ", "_")}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const drawings = await workbook.inspect({ kind: "drawing", maxChars: 10000 });
await fs.writeFile(new URL("./final-drawings.ndjson", import.meta.url), drawings.ndjson, "utf8");
console.log(drawings.ndjson);
