import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);

for (const sheet of workbook.worksheets.items) {
  const values = sheet.getUsedRange(false).values;
  console.log(JSON.stringify({
    sheet: sheet.name,
    rows: values.length,
    cols: values[0].length,
    headers: values[0],
    sample: values.slice(0, Math.min(values.length, 12)),
  }, null, 2));
}
