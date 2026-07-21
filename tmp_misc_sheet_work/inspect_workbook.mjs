import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = process.argv[2] || "/Users/jamesyuan/Downloads/ai4research_short feature list.xlsx";
const outputDir = "/private/tmp/ai4research_misc_l2_work";
await fs.mkdir(outputDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));

const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 12000,
});
console.log("SHEETS");
console.log(sheets.ndjson);

for (const sheetName of ["Workflow Features", "Foundation Features", "Misc Features"]) {
  try {
    const inspected = await workbook.inspect({
      kind: "table",
      sheetId: sheetName,
      range: sheetName === "Misc Features" ? "A1:E60" : "A1:E24",
      include: "values,formulas",
      tableMaxRows: sheetName === "Misc Features" ? 60 : 24,
      tableMaxCols: 5,
      tableMaxCellChars: 2000,
      maxChars: 80000,
    });
    await fs.writeFile(
      `${outputDir}/${sheetName.replaceAll(" ", "_")}.ndjson`,
      inspected.ndjson,
      "utf8",
    );

    const styles = await workbook.inspect({
      kind: "computedStyle",
      sheetId: sheetName,
      range: sheetName === "Misc Features" ? "A1:E30" : "A1:E12",
      maxChars: 30000,
    });
    await fs.writeFile(
      `${outputDir}/${sheetName.replaceAll(" ", "_")}_styles.ndjson`,
      styles.ndjson,
      "utf8",
    );

    const preview = await workbook.render({
      sheetName,
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    await fs.writeFile(
      `${outputDir}/${sheetName.replaceAll(" ", "_")}.png`,
      new Uint8Array(await preview.arrayBuffer()),
    );
  } catch (error) {
    console.log(`ERROR ${sheetName}`);
    console.log(String(error));
  }
}
