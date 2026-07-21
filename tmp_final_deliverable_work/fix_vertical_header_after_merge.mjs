import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputPath = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263/ai4research final l1 l2 feature deliverable.xlsx";

const input = await FileBlob.load(outputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Vertical Features");
sheet.getRange("A1").values = [["level_1_feature"]];
sheet.getRange("A1").format = {
  font: { bold: true, color: "#FFFFFF" },
  fill: "#1F4E79",
  horizontalAlignment: "center",
  verticalAlignment: "middle",
  wrapText: true,
};
sheet.getRange("A1").format.borders = { preset: "all", style: "thin", color: "#FFFFFF" };

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }, null, 2));
