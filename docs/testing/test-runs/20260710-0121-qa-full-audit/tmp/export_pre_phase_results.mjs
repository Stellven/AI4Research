import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [rootArg] = process.argv.slice(2);
if (!rootArg) throw new Error("usage: export_pre_phase_results.mjs RUN_ROOT");
const root = path.resolve(rootArg);
const workbookPath = path.join(root, "ai4research_recursive_feature_split_qa_execution_UPDATED.xlsx");
const outputPath = path.join(root, "tmp/pre-eligible-phase-feature-results.csv");

function escapeCsv(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheet = workbook.worksheets.getItem("Audit Results");
const used = sheet.getUsedRange();
if (!used) throw new Error("Audit Results sheet is empty");
const values = used.values;
const csv = values.map((row) => row.map(escapeCsv).join(",")).join("\n") + "\n";
await fs.writeFile(outputPath, csv, "utf8");
console.log(JSON.stringify({ outputPath, rows: values.length - 1, columns: values[0]?.length ?? 0 }));
