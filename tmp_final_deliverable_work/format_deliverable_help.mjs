import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);
console.log(workbook.help("*", {
  search: "delete.*row|row.*delete|range.delete|worksheet.*delete",
  include: "index,examples,notes",
  maxChars: 6000,
}).ndjson);
