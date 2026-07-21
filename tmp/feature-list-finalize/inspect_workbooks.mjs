import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputs = [
  "/Users/jamesyuan/Downloads/ai4research_short feature list.xlsx",
  "/Users/jamesyuan/Downloads/ai4research_restructured_feature_workbook_workflow_l2_pipeline_v2_no_chinese_annotations.xlsx",
];

const outDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/tmp/feature-list-finalize/previews";
await fs.mkdir(outDir, { recursive: true });

for (const inputPath of inputs) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
  const name = path.basename(inputPath, ".xlsx").replaceAll(/[^a-zA-Z0-9]+/g, "_");
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table,region",
    maxChars: 18000,
    tableMaxRows: 30,
    tableMaxCols: 12,
    tableMaxCellChars: 500,
  });
  await fs.writeFile(path.join(outDir, `${name}_inspect.ndjson`), summary.ndjson, "utf8");
  console.log(`WORKBOOK ${inputPath}`);
  console.log(summary.ndjson);

  const sheets = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 5000 });
  const sheetRecords = sheets.ndjson
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));

  for (const rec of sheetRecords) {
    const sheetName = rec.name;
    if (!sheetName) continue;
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1.3, format: "png" });
    const safeSheet = sheetName.replaceAll(/[^a-zA-Z0-9]+/g, "_");
    await fs.writeFile(path.join(outDir, `${name}__${safeSheet}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}
