import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263/ai4research final l1 l2 feature deliverable.xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);

for (const sheet of workbook.worksheets.items) {
  const values = sheet.getUsedRange(false).values;
  console.log(JSON.stringify({
    sheet: sheet.name,
    rows: values.length,
    cols: values[0].length,
    header: values[0],
    firstRows: values.slice(0, Math.min(6, values.length)),
  }, null, 2));
}
