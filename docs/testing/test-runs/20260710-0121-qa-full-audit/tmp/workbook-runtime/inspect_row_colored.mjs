import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const auditRoot = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
const input = await FileBlob.load(`${auditRoot}/ai4research_recursive_feature_split_qa_execution_colored.xlsx`);
const workbook = await SpreadsheetFile.importXlsx(input);
const approved = new Set([
  "PASS",
  "FAIL",
  "BLOCKED_EXPECTED",
  "INCONCLUSIVE_EXPECTED",
  "SKIPPED_NA",
  "SKIPPED_ENV",
  "FLAKY",
  "NOT_RUN",
]);
const verification = [];
for (const sheetName of ["Entrypoint Map", "Existing Test Map", "Missing Test Plan", "Pass Fail Criteria"]) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange();
  const values = used.values;
  const headers = values[0].map((value) => String(value ?? ""));
  const featureIndex = headers.indexOf("feature_id");
  const preIndex = headers.indexOf("pre_test_status");
  const resultIndex = headers.indexOf("test_result_status");
  const statusCounts = {};
  const invalidStatuses = [];
  const featureIds = [];
  for (let row = 1; row < values.length; row += 1) {
    const featureId = String(values[row][featureIndex] ?? "").trim();
    const status = String(values[row][resultIndex] ?? "").trim();
    if (featureId) featureIds.push(featureId);
    if (status) {
      statusCounts[status] = (statusCounts[status] ?? 0) + 1;
      if (!approved.has(status)) invalidStatuses.push({ row: row + 1, status });
    }
  }
  const duplicateFeatureIds = featureIds.filter((id, index) => featureIds.indexOf(id) !== index);
  verification.push({
    sheetName,
    used: used.address,
    dataRows: values.length - 1,
    columnCount: used.columnCount,
    headers,
    featureIndex,
    preIndex,
    resultIndex,
    statusCounts,
    blankResultRows: values.length - 1 - Object.values(statusCounts).reduce((a, b) => a + b, 0),
    invalidStatuses,
    duplicateFeatureIds: [...new Set(duplicateFeatureIds)],
    firstFeatureId: featureIds[0],
    lastFeatureId: featureIds.at(-1),
  });
}
console.log(JSON.stringify({ sheetCount: workbook.worksheets.items.length, verification }, null, 2));
