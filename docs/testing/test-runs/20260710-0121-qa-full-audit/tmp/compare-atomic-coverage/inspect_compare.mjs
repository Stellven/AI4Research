import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const paths = [
  "/Users/jamesyuan/Downloads/AI4RnD Feature List - atomic coverage resolved.xlsx",
  "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx",
];

for (const path of paths) {
  const input = await FileBlob.load(path);
  const workbook = await SpreadsheetFile.importXlsx(input);
  const sheets = [];
  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange();
    const rowCount = used?.rowCount ?? 0;
    const columnCount = used?.columnCount ?? 0;
    const sampleRows = rowCount && columnCount
      ? sheet.getRangeByIndexes(0, 0, Math.min(4, rowCount), Math.min(30, columnCount)).values
      : [];
    sheets.push({
      name: sheet.name,
      used: used?.address ?? null,
      rowCount,
      columnCount,
      headers: sampleRows[0] ?? [],
      sampleRows: sampleRows.slice(1),
    });
  }
  console.log(JSON.stringify({ path, sheetCount: sheets.length, sheets }));
}
