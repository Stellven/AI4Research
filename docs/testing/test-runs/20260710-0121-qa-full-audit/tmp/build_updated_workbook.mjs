import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [rootArg] = process.argv.slice(2);
if (!rootArg) throw new Error("usage: build_updated_workbook.mjs RUN_ROOT");
const root = path.resolve(rootArg);
const input = path.join(root, "control-material/ai4research_recursive_feature_split_qa_execution.xlsx");
const output = path.join(root, "ai4research_recursive_feature_split_qa_execution_UPDATED.xlsx");
const previewDir = path.join(root, "workbook-updated-previews");
await fs.mkdir(previewDir, { recursive: true });

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') { cell += '"'; i += 1; }
      else if (ch === '"') inQuotes = false;
      else cell += ch;
    } else if (ch === '"') inQuotes = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else if (ch !== "\r") cell += ch;
  }
  if (cell.length || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

function escapeCsv(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(rows) {
  return rows.map((row) => row.map(escapeCsv).join(",")).join("\n") + "\n";
}

function colName(index) {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function styleTable(sheet, rows, freezeColumns = 2) {
  if (!rows.length) return;
  const rowCount = rows.length;
  const colCount = Math.max(...rows.map((row) => row.length));
  const last = colName(colCount - 1);
  const used = sheet.getRange(`A1:${last}${rowCount}`);
  used.format.wrapText = true;
  used.format.verticalAlignment = "top";
  used.format.font = { name: "Aptos", size: 9 };
  const header = sheet.getRange(`A1:${last}1`);
  header.format = {
    fill: "#17365D",
    font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "middle",
    rowHeight: 34,
    wrapText: true,
  };
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(freezeColumns);
  sheet.showGridLines = false;
  for (let c = 0; c < colCount; c += 1) {
    const sample = rows.slice(0, 200).map((row) => String(row[c] ?? "").length);
    const width = Math.max(12, Math.min(c < 4 ? 42 : 58, Math.ceil(Math.max(12, ...sample) * 0.72)));
    sheet.getRange(`${colName(c)}:${colName(c)}`).format.columnWidth = width;
  }
  if (rowCount > 1) sheet.getRange(`A2:${last}${Math.min(rowCount, 300)}`).format.rowHeight = 42;
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const originalSheetNames = workbook.worksheets.items.map((sheet) => sheet.name);
const featureRows = parseCsv(await fs.readFile(path.join(root, "feature-results.csv"), "utf8"));
const eligibleRows = parseCsv(await fs.readFile(path.join(root, "evidence/eligible-full-phase-v3/feature-execution-results.csv"), "utf8"));
const commandRows = (await fs.readFile(path.join(root, "command-log.tsv"), "utf8"))
  .split(/\r?\n/).filter(Boolean).map((line) => line.split("\t"));
const featureSummary = JSON.parse(await fs.readFile(path.join(root, "evidence/feature-results-summary.json"), "utf8"));
const environment = JSON.parse(await fs.readFile(path.join(root, "environment.json"), "utf8"));

await workbook.fromCSV(toCsv(featureRows), { sheetName: "Audit Results" });
const resultsSheet = workbook.worksheets.getItem("Audit Results");
styleTable(resultsSheet, featureRows, 2);
const statusColumn = resultsSheet.getRange(`N2:N${featureRows.length}`);
statusColumn.format.font = { bold: true };

await workbook.fromCSV(toCsv(commandRows), { sheetName: "Audit Commands" });
const commandsSheet = workbook.worksheets.getItem("Audit Commands");
styleTable(commandsSheet, commandRows, 2);

await workbook.fromCSV(toCsv(eligibleRows), { sheetName: "Eligible Phase" });
const eligibleSheet = workbook.worksheets.getItem("Eligible Phase");
styleTable(eligibleSheet, eligibleRows, 2);

const defectRows = [
  ["Defect ID", "Severity", "Title", "Primary evidence"],
  ["D-001", "P1", "auto-chain.sh syntax error", "phase4_static_repo_checks"],
  ["D-002", "P1", "Missing epic_child_status_lines blocks graph collection", "phase4_pytest_matrix_installed_home"],
  ["D-003", "P1", "Approved AutoSci commands fail in spaced paths", "phase4_scientific_experiment_inconclusive_repro"],
  ["D-004", "P1", "Root TVS imports unresolved", "phase4_bun_test"],
  ["D-005", "P2", "Research-survey CLI/implementation drift", "phase4_pytest_matrix_installed_home"],
  ["D-006", "P2", "Survey local-command paths not quoted", "phase4_pytest_matrix_installed_home"],
  ["D-007", "P2", "AutoSci setup/parity references missing .env.example", "phase4_autosci_plugin_pytest_final"],
  ["D-008", "P2", "AutoSci ingest/provider proof incomplete", "phase4_autosci_plugin_pytest_final"],
  ["D-009", "P2", "Browser-research compatibility APIs absent", "phase4_pytest_matrix_installed_home"],
  ["D-010", "P2", "Physical-operator compatibility schema drift", "phase4_pytest_matrix_installed_home"],
  ["D-011", "P2", "Terminal-benchmark prerequisite semantics disagree", "phase4_pytest_matrix_installed_home"],
  ["D-012", "P2", "Installed harness omits sprint scaffold", "phase4_pytest_matrix_installed_home"],
  ["D-013", "P2", "Livework fail-open/path expansion broken", "phase4_pytest_matrix_installed_home"],
  ["D-014", "P3", "Research status omits quality-gates section", "phase4_pytest_matrix_installed_home"],
  ["D-015", "P3", "File-provider URI not percent encoded", "phase4_autosci_plugin_pytest_final"],
  ["D-016", "P3", "Broad pytest import/package collisions", "phase4_pytest_matrix_installed_home"],
  ["D-017", "P3", "Tracked JSON files empty/malformed", "phase4_static_repo_checks"],
  ["D-018", "P3", "Missing-approval status taxonomy inconsistent", "phase4_autosci_plugin_pytest_final"],
  ["D-019", "P3", "Data-plane tests do not self-skip", "phase4_pytest_matrix_installed_home"],
  ["D-020", "P2", "Research intake omits capability capsule ID", "eligible-0069"],
  ["D-021", "P2", "Graph hygiene/reuse APIs drifted", "eligible-0027; eligible-0032"],
  ["D-022", "P2", "Actor/logical-operator registries disagree", "eligible-0062; eligible-0083"],
  ["D-023", "P2", "ThunderOMLX legacy alias not resolved", "eligible-0081"],
];
await workbook.fromCSV(toCsv(defectRows), { sheetName: "Audit Defects" });
const defectsSheet = workbook.worksheets.getItem("Audit Defects");
styleTable(defectsSheet, defectRows, 1);

const summarySheet = workbook.worksheets.add("Audit Summary");
summarySheet.getRange("A1:N1").merge();
summarySheet.getRange("A1").values = [["AI4Research QA Full Audit — NOT READY"]];
summarySheet.getRange("A1:N1").format = {
  fill: "#8B1E1E",
  font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "middle",
  rowHeight: 34,
};
summarySheet.getRange("A3:B11").values = [
  ["Audit field", "Value"],
  ["Source", "https://github.com/Stellven/AI4Research"],
  ["Branch", "openJiuwen-Solar"],
  ["Locked SHA", environment.locked_test_sha],
  ["Atomic features", featureSummary.feature_count],
  ["Verdict", "NOT READY"],
  ["P1 defects", 4],
  ["Live phase executed", "No"],
  ["Completed", environment.audit_completed_local],
];
summarySheet.getRange("D3:E11").values = [
  ["Status", "Count"],
  ["PASS", ""], ["FAIL", ""], ["BLOCKED_EXPECTED", ""], ["INCONCLUSIVE_EXPECTED", ""],
  ["SKIPPED_NA", ""], ["SKIPPED_ENV", ""], ["FLAKY", ""], ["NOT_RUN", ""],
];
for (let row = 4; row <= 11; row += 1) {
  summarySheet.getRange(`E${row}`).formulas = [[`=COUNTIF('Audit Results'!$N$2:$N$${featureRows.length},D${row})`]];
}
summarySheet.getRange("G3:N7").values = [
  ["Part", "PASS", "FAIL", "BLOCKED_EXPECTED", "INCONCLUSIVE_EXPECTED", "SKIPPED_ENV", "NOT_RUN", "Total"],
  ["workflow", "", "", "", "", "", "", ""],
  ["foundations", "", "", "", "", "", "", ""],
  ["misc.", "", "", "", "", "", "", ""],
  ["All", "", "", "", "", "", "", ""],
];
for (let row = 4; row <= 6; row += 1) {
  for (let col = 8; col <= 13; col += 1) {
    const letter = colName(col - 1);
    const statusHeader = `${letter}$3`;
    summarySheet.getRange(`${letter}${row}`).formulas = [[`=COUNTIFS('Audit Results'!$B$2:$B$${featureRows.length},$G${row},'Audit Results'!$N$2:$N$${featureRows.length},${statusHeader})`]];
  }
  summarySheet.getRange(`N${row}`).formulas = [[`=SUM(H${row}:M${row})`]];
}
for (let col = 8; col <= 13; col += 1) {
  const letter = colName(col - 1);
  summarySheet.getRange(`${letter}7`).formulas = [[`=SUM(${letter}4:${letter}6)`]];
}
summarySheet.getRange("N7").formulas = [["=SUM(N4:N6)"]];
summarySheet.getRange("A13:N19").values = [
  ["Audit notes", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["Fixture and local deterministic evidence is not live AutoSci parity.", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["All 448 strict-phase eligible features were attempted across 107 unique targets.", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["Strict phase: 93 target PASS, 14 target FAIL; 523 testcase PASS, 15 FAIL, 3 ERROR, 1 SKIP.", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["Only high-confidence direct mappings can automatically PASS/FAIL; indirect/partial evidence is INCONCLUSIVE_EXPECTED.", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["355 heuristic candidate mappings were reclassified to missing after semantic/executable validation.", "", "", "", "", "", "", "", "", "", "", "", "", ""],
  ["See final-report.md, defects.md, gated-and-live-test-plan.md, and the CSV deliverables beside this workbook.", "", "", "", "", "", "", "", "", "", "", "", "", ""],
];
for (let row = 13; row <= 19; row += 1) summarySheet.getRange(`A${row}:N${row}`).merge();
summarySheet.getRange("A3:N19").format.font = { name: "Aptos", size: 10 };
summarySheet.getRange("A3:N19").format.wrapText = true;
summarySheet.getRange("A3:N19").format.verticalAlignment = "top";
for (const range of ["A3:B3", "D3:E3", "G3:N3", "A13:N13"]) {
  summarySheet.getRange(range).format = {
    fill: "#17365D",
    font: { name: "Aptos", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "middle",
    wrapText: true,
  };
}
summarySheet.getRange("B11").format.numberFormat = "yyyy-mm-dd hh:mm:ss";
summarySheet.getRange("A14:N19").format.rowHeight = 24;
summarySheet.getRange("A:A").format.columnWidth = 28;
summarySheet.getRange("B:B").format.columnWidth = 48;
summarySheet.getRange("D:D").format.columnWidth = 26;
summarySheet.getRange("E:E").format.columnWidth = 14;
summarySheet.getRange("G:G").format.columnWidth = 18;
summarySheet.getRange("H:N").format.columnWidth = 20;
summarySheet.freezePanes.freezeRows(1);
summarySheet.showGridLines = false;

const previews = [
  ["Audit Summary", "A1:N19", "audit-summary.png"],
  ["Audit Results", "A1:W32", "audit-results-head.png"],
  ["Audit Results", `A${Math.max(2, featureRows.length - 30)}:W${featureRows.length}`, "audit-results-tail.png"],
  ["Audit Defects", "A1:D24", "audit-defects.png"],
  ["Audit Commands", `A1:K${Math.min(40, commandRows.length)}`, "audit-commands.png"],
  ["Eligible Phase", "A1:S32", "eligible-phase-head.png"],
  ["Eligible Phase", `A${Math.max(2, eligibleRows.length - 30)}:S${eligibleRows.length}`, "eligible-phase-tail.png"],
];
for (const [sheetName, range, filename] of previews) {
  const image = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, filename), new Uint8Array(await image.arrayBuffer()));
}
const formulaInspection = await workbook.inspect({
  kind: "formula",
  sheetId: "Audit Summary",
  range: "A1:N19",
  maxChars: 12000,
  options: { maxResults: 200 },
});
await fs.writeFile(path.join(previewDir, "audit-summary-formulas.ndjson"), formulaInspection.ndjson, "utf8");
const errorInspection = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fs.writeFile(path.join(previewDir, "formula-error-scan.ndjson"), errorInspection.ndjson, "utf8");

const blob = await SpreadsheetFile.exportXlsx(workbook);
await blob.save(output);
console.log(JSON.stringify({
  output,
  originalSheetCount: originalSheetNames.length,
  originalSheetNames,
  finalSheetCount: workbook.worksheets.items.length,
  addedSheets: ["Audit Summary", "Audit Results", "Audit Commands", "Audit Defects", "Eligible Phase"],
  featureResultRows: featureRows.length - 1,
  commandRows: commandRows.length - 1,
  defectRows: defectRows.length - 1,
  eligibleFeatureRows: eligibleRows.length - 1,
}, null, 2));
