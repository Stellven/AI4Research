import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research_short feature list.xlsx";
const canonicalPath = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/tmp/feature-list-finalize/canonical_workflow_l2.json";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/feature-list-finalize";
const previewDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/tmp/feature-list-finalize/final-previews";
const outputPath = `${outputDir}/ai4research_short feature list.xlsx`;

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const canonical = JSON.parse(await fs.readFile(canonicalPath, "utf8"));
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Workflow Features");

const level2MergedRanges = [
  "D4:D6", "D7:D8", "D17:D36", "D39:D44", "D47:D48", "D50:D51",
  "D52:D58", "D63:D68", "D69:D72", "D73:D79", "D81:D82", "D83:D84",
  "D88:D89", "D91:D93", "D96:D100", "D108:D109", "D110:D111",
  "D112:D113", "D114:D116", "D117:D120", "D124:D125", "D129:D131",
  "D136:D137", "D138:D139", "D140:D141"
];

for (const address of level2MergedRanges) {
  sheet.unmergeCells(address);
}

sheet.getRange("D2:D141").clear({ applyTo: "contents" });

for (const [name, spec] of Object.entries(canonical)) {
  const level1Text = spec.entry && spec.exit
    ? `${name}\nEntry: ${spec.entry}\nExit: ${spec.exit}`
    : name;
  sheet.getRange(`C${spec.row_start}`).values = [[level1Text]];
  spec.level_2.forEach((feature, index) => {
    const row = spec.row_start + index;
    if (row > spec.row_end) {
      throw new Error(`${name} has more L2 features than available rows`);
    }
    sheet.getRange(`D${row}`).values = [[feature]];
  });
}

sheet.getRange("C2:D141").format.wrapText = true;
sheet.getRange("C2:D141").format.verticalAlignment = "top";
sheet.freezePanes.freezeRows(1);

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

const verificationWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const tableCheck = await verificationWorkbook.inspect({
  kind: "table",
  sheetId: "Workflow Features",
  range: "A1:E141",
  include: "values,formulas",
  tableMaxRows: 141,
  tableMaxCols: 5,
  tableMaxCellChars: 500,
  maxChars: 80000,
});
await fs.writeFile(`${previewDir}/workflow_values.ndjson`, tableCheck.ndjson, "utf8");

const errorCheck = await verificationWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fs.writeFile(`${previewDir}/formula_errors.ndjson`, errorCheck.ndjson, "utf8");

const previews = [
  ["Workflow Features", "A1:E21", "workflow_w1_w2.png"],
  ["Workflow Features", "A49:E68", "workflow_w2_w3.png"],
  ["Workflow Features", "A94:E116", "workflow_w4_w7.png"],
  ["Workflow Features", "A127:E141", "workflow_w8_w9.png"],
  ["Workflow Features", "A15:E60", "workflow_w2_full.png"],
  ["Workflow Features", "A61:E93", "workflow_w3_full.png"],
  ["Workflow Features", "A112:E126", "workflow_w7_full.png"],
  ["Foundation Features", null, "foundation.png"],
  ["Misc Features", null, "misc.png"],
];

for (const [sheetName, range, filename] of previews) {
  const options = { sheetName, autoCrop: "all", scale: 1.5, format: "png" };
  if (range) options.range = range;
  const preview = await verificationWorkbook.render(options);
  await fs.writeFile(`${previewDir}/${filename}`, new Uint8Array(await preview.arrayBuffer()));
}

console.log(outputPath);
console.log(errorCheck.ndjson);
