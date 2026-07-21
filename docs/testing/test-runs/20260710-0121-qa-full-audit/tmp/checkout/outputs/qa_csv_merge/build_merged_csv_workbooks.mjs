import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repo = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar";
const outputDir = path.join(repo, "docs/testing/xlsx");

const inputs = [
  {
    csv: "docs/testing/qa_feature_list.csv",
    out: "qa_feature_list_merged.xlsx",
    mergedSheet: "Feature List",
  },
  {
    csv: "docs/testing/qa_feature_inventory.csv",
    out: "qa_feature_inventory_merged.xlsx",
    mergedSheet: "Function Inventory",
  },
  {
    csv: "docs/testing/qa_master_pass_fail_table.csv",
    out: "qa_master_pass_fail_table_merged.xlsx",
    mergedSheet: "Pass Fail Table",
  },
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

function truncateSheetName(name) {
  return name.replace(/[\\/?*[\]:]/g, " ").slice(0, 31);
}

function mergeAdjacentRuns(sheet, rows) {
  if (rows.length < 3) return;
  const colCount = Math.max(...rows.map((r) => r.length));
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
      }
      start = end + 1;
    }
  }
}

function styleSheet(sheet, rows) {
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
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "middle";
  header.format.rowHeight = 30;

  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;

  for (let c = 0; c < colCount; c += 1) {
    const maxLen = Math.max(
      10,
      ...rows.slice(0, 200).map((r) => String(r[c] ?? "").length),
    );
    const width = Math.max(14, Math.min(c <= 2 ? 34 : 60, Math.ceil(maxLen * 0.9)));
    sheet.getRange(`${colName(c)}:${colName(c)}`).format.columnWidth = width;
  }
  sheet.getRange(`A2:${lastCol}${Math.min(rowCount, 200)}`).format.rowHeight = 45;
}

async function buildWorkbook(input) {
  const csvPath = path.join(repo, input.csv);
  const csvText = await fs.readFile(csvPath, "utf8");
  const rows = parseCsv(csvText);
  const workbook = await Workbook.fromCSV(csvText, {
    sheetName: truncateSheetName(input.mergedSheet),
  });
  const mergedSheet = workbook.worksheets.getItem(truncateSheetName(input.mergedSheet));
  mergeAdjacentRuns(mergedSheet, rows);
  styleSheet(mergedSheet, rows);

  await workbook.fromCSV(csvText, { sheetName: "Raw Data" });
  const rawSheet = workbook.worksheets.getItem("Raw Data");
  styleSheet(rawSheet, rows);

  const preview = await workbook.render({
    sheetName: truncateSheetName(input.mergedSheet),
    range: "A1:D30",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(outputDir, `${path.basename(input.out, ".xlsx")}.preview.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );

  await fs.mkdir(outputDir, { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const outPath = path.join(outputDir, input.out);
  await output.save(outPath);
  console.log(`saved ${outPath}`);
}

for (const input of inputs) {
  await buildWorkbook(input);
}
