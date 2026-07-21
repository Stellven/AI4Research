import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repo = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar";
const outputDir = path.join(repo, "docs/testing/xlsx");
const outPath = path.join(outputDir, "qa_inventory_test_mapping_and_pass_fail_merged.xlsx");

const inventoryColumns = [
  ["l1", "Level 1 Feature"],
  ["l2", "Level 2 Feature"],
  ["specific_inputs_outputs", "Specific Inputs / Outputs Supported"],
  ["feature_id", "Function / Feature ID"],
  ["source_type", "Source Type"],
  ["source_paths", "Source Paths"],
  ["entrypoints", "Entrypoints"],
  ["existing_tests", "Existing Tests"],
  ["coverage_status", "Coverage Status"],
  ["pass_criteria", "Pass Criteria"],
  ["why_testable", "Why Testable"],
  ["notes", "Notes"],
];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (ch !== "\r") {
      cell += ch;
    }
  }
  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function escapeCsvCell(value) {
  const s = String(value ?? "");
  if (/[",\n\r]/.test(s)) {
    return `"${s.replaceAll('"', '""')}"`;
  }
  return s;
}

function rowsToCsv(rows) {
  return rows.map((row) => row.map(escapeCsvCell).join(",")).join("\n") + "\n";
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

function mergeAdjacentRuns(sheet, rows) {
  if (rows.length < 3) return 0;
  const colCount = Math.max(...rows.map((r) => r.length));
  let mergeCount = 0;
  for (let c = 0; c < colCount; c += 1) {
    let start = 1;
    while (start < rows.length) {
      const value = rows[start]?.[c] ?? "";
      let end = start;
      while (end + 1 < rows.length && (rows[end + 1]?.[c] ?? "") === value) {
        end += 1;
      }
      if (value !== "" && end > start) {
        const col = colName(c);
        sheet.getRange(`${col}${start + 1}:${col}${end + 1}`).merge();
        mergeCount += 1;
      }
      start = end + 1;
    }
  }
  return mergeCount;
}

function styleSheet(sheet, rows, options = {}) {
  if (!rows.length) return;
  const rowCount = rows.length;
  const colCount = Math.max(...rows.map((r) => r.length));
  const lastCol = colName(colCount - 1);
  const used = sheet.getRange(`A1:${lastCol}${rowCount}`);

  used.format.wrapText = true;
  used.format.font = { name: "Aptos", size: 10 };
  used.format.verticalAlignment = "top";
  used.format.borders = { preset: "outside", style: "thin", color: "#B7C9D6" };

  const header = sheet.getRange(`A1:${lastCol}1`);
  header.format.font = { bold: true, color: "#000000", name: "Aptos", size: 10 };
  header.format.fill = { color: "#DDEBF7" };
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "middle";
  header.format.rowHeight = 32;

  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(options.freezeColumns ?? 2);
  sheet.showGridLines = false;

  for (let c = 0; c < colCount; c += 1) {
    const headerText = rows[0]?.[c] ?? "";
    const maxLen = Math.max(
      10,
      String(headerText).length,
      ...rows.slice(1, 150).map((r) => String(r[c] ?? "").length),
    );
    const cap = c < 2 ? 30 : c < 4 ? 46 : 64;
    const min = c < 2 ? 18 : 14;
    const width = Math.max(min, Math.min(cap, Math.ceil(maxLen * 0.85)));
    sheet.getRange(`${colName(c)}:${colName(c)}`).format.columnWidth = width;
  }

  if (rowCount > 1) {
    sheet.getRange(`A2:${lastCol}${Math.min(rowCount, 250)}`).format.rowHeight = 48;
  }
}

function buildInventoryRows(csvText) {
  const rows = parseCsv(csvText);
  const header = rows[0] ?? [];
  const index = new Map(header.map((name, i) => [name, i]));
  const outputRows = [inventoryColumns.map(([, label]) => label)];

  for (const row of rows.slice(1)) {
    outputRows.push(
      inventoryColumns.map(([key]) => {
        const i = index.get(key);
        return i === undefined ? "" : row[i] ?? "";
      }),
    );
  }
  return outputRows;
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });

  const inventoryCsv = await fs.readFile(
    path.join(repo, "docs/testing/qa_feature_inventory.csv"),
    "utf8",
  );
  const passFailCsv = await fs.readFile(
    path.join(repo, "docs/testing/qa_master_pass_fail_table.csv"),
    "utf8",
  );

  const inventoryRows = buildInventoryRows(inventoryCsv);
  const passFailRows = parseCsv(passFailCsv);

  const workbook = await Workbook.fromCSV(rowsToCsv(inventoryRows), {
    sheetName: "Inventory Test Mapping",
  });
  const inventorySheet = workbook.worksheets.getItem("Inventory Test Mapping");
  const inventoryMerges = mergeAdjacentRuns(inventorySheet, inventoryRows);
  styleSheet(inventorySheet, inventoryRows, { freezeColumns: 3 });

  await workbook.fromCSV(rowsToCsv(passFailRows), { sheetName: "Pass Fail Table" });
  const passFailSheet = workbook.worksheets.getItem("Pass Fail Table");
  const passFailMerges = mergeAdjacentRuns(passFailSheet, passFailRows);
  styleSheet(passFailSheet, passFailRows, { freezeColumns: 3 });

  for (const [sheetName, range] of [
    ["Inventory Test Mapping", "A1:L30"],
    ["Pass Fail Table", "A1:M30"],
  ]) {
    const preview = await workbook.render({
      sheetName,
      range,
      scale: 1,
      format: "png",
    });
    const safeName = sheetName.toLowerCase().replaceAll(" ", "-");
    await fs.writeFile(
      path.join(outputDir, `qa_combined_${safeName}.preview.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outPath);
  console.log(
    JSON.stringify(
      {
        outPath,
        sheets: [
          {
            name: "Inventory Test Mapping",
            rows: inventoryRows.length,
            columns: inventoryRows[0].length,
            verticalMergeRuns: inventoryMerges,
          },
          {
            name: "Pass Fail Table",
            rows: passFailRows.length,
            columns: passFailRows[0].length,
            verticalMergeRuns: passFailMerges,
          },
        ],
      },
      null,
      2,
    ),
  );
}

await main();
