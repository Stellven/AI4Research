import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx";
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

console.log((await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 80,
  tableMaxCols: 6,
  tableMaxCellChars: 180,
})).ndjson);

const sheets = await workbook.inspect({ kind: "sheet", include: "id,name" });
console.log(sheets.ndjson);
