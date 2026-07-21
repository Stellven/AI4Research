import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx";
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Workflow Features");

const values = sheet.getRange("A1:F160").values;
const starts = [];
for (let i = 1; i < values.length; i += 1) {
  if (values[i][1]) {
    starts.push({ row: i + 1, text: String(values[i][1]).replace(/\n/g, " ").slice(0, 140) });
  }
}
console.log(JSON.stringify(starts, null, 2));

for (let i = 0; i < starts.length; i += 1) {
  const start = starts[i].row;
  const end = i + 1 < starts.length ? starts[i + 1].row - 1 : 142;
  const l2 = [];
  for (let r = start; r <= end; r += 1) {
    const val = values[r - 1][3];
    if (val) l2.push({ row: r, l2: String(val).replace(/\n/g, " ").slice(0, 120), desc: values[r - 1][4] ?? null });
  }
  console.log(JSON.stringify({ start, end, l1: starts[i].text, l2 }, null, 2));
}
