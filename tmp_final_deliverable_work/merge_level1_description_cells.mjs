import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

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

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = [];

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange(false);
  const values = used.values;
  if (!values || values.length === 0) continue;

  const headers = values[0].map(normalizeHeader);
  const descCol = headers.findIndex((header) => header.includes("level 1") && header.includes("description"));
  if (descCol < 0) {
    summary.push({ sheet: sheet.name, skipped: true, reason: "no level 1 description column" });
    continue;
  }

  const descRows = [];
  for (let r = 1; r < values.length; r += 1) {
    if (hasContent(values[r][descCol])) descRows.push(r + 1);
  }

  const descColLetter = colLetter(descCol + 1);
  const mergedRanges = [];
  for (let i = 0; i < descRows.length - 1; i += 1) {
    const start = descRows[i];
    const end = descRows[i + 1] - 1;
    if (end <= start) continue;
    const address = `${descColLetter}${start}:${descColLetter}${end}`;
    sheet.getRange(address).merge();
    sheet.getRange(address).format = {
      horizontalAlignment: "center",
      verticalAlignment: "middle",
      wrapText: true,
    };
    mergedRanges.push(address);
  }

  summary.push({
    sheet: sheet.name,
    level1DescriptionColumn: descCol + 1,
    nonEmptyDescriptionRows: descRows,
    mergedRanges,
    lastDescriptionRowLeftUnmerged: descRows.at(-1) ?? null,
  });
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(formulaErrors.ndjson);
console.log(JSON.stringify({ summary }, null, 2));

await fs.mkdir(outputDir, { recursive: true });
for (const sheet of workbook.worksheets.items) {
  const values = sheet.getUsedRange(false).values;
  const colCount = values[0].length;
  const rowCount = values.length;
  const range = `A1:${colLetter(colCount)}${rowCount}`;
  const rendered = await workbook.render({ sheetName: sheet.name, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${sheet.name.replaceAll(" ", "_")}_l1_description_merged.png`, new Uint8Array(await rendered.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }, null, 2));
