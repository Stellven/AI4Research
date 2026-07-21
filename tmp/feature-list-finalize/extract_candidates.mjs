import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputs = [
  "/Users/jamesyuan/Downloads/ai4research_short feature list.xlsx",
  "/Users/jamesyuan/Downloads/ai4research_restructured_feature_workbook_workflow_l2_pipeline_v2_no_chinese_annotations.xlsx",
];

const outDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/tmp/feature-list-finalize/extracted";
await fs.mkdir(outDir, { recursive: true });

for (const inputPath of inputs) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
  const base = path.basename(inputPath, ".xlsx").replaceAll(/[^a-zA-Z0-9]+/g, "_");
  const sheetSummary = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 10000 });
  const records = sheetSummary.ndjson.split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const payload = {};
  for (const rec of records) {
    if (!rec.name) continue;
    const sheet = workbook.worksheets.getItem(rec.name);
    const used = sheet.getUsedRange();
    payload[rec.name] = {
      address: used.address,
      values: used.values,
      formulas: used.formulas,
    };
  }
  await fs.writeFile(path.join(outDir, `${base}.json`), JSON.stringify(payload, null, 2), "utf8");
  console.log(base, Object.keys(payload));
}
