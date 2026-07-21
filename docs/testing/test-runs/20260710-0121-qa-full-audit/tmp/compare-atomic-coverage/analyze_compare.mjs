import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const newPath = "/Users/jamesyuan/Downloads/AI4RnD Feature List - atomic coverage resolved.xlsx";
const oldPath = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx";

const load = async (path) => SpreadsheetFile.importXlsx(await FileBlob.load(path));
const [newBook, oldBook] = await Promise.all([load(newPath), load(oldPath)]);

function rowsFromSheet(book, sheetName, headerRow = 0) {
  const values = book.worksheets.getItem(sheetName).getUsedRange().values;
  const headers = values[headerRow].map((value) => String(value ?? "").trim());
  return values.slice(headerRow + 1).map((row, index) => {
    const result = { __row: headerRow + index + 2 };
    headers.forEach((header, column) => {
      if (header) result[header] = row[column] ?? null;
    });
    return result;
  }).filter((row) => Object.entries(row).some(([key, value]) => key !== "__row" && value !== null && String(value).trim() !== ""));
}

const clean = (value) => String(value ?? "").trim();
const countBy = (rows, key) => Object.fromEntries([...rows.reduce((map, row) => {
  const value = clean(row[key]) || "(blank)";
  map.set(value, (map.get(value) ?? 0) + 1);
  return map;
}, new Map()).entries()].sort((a, b) => a[0].localeCompare(b[0])));

const oldTests = rowsFromSheet(oldBook, "Missing Test Plan").map((row) => ({
  row: row.__row,
  featureId: clean(row.feature_id),
  featureName: clean(row["atomic feature"]),
  testName: clean(row["suggested test name"]),
  result: clean(row.test_result_status),
}));

const newRegistry = rowsFromSheet(newBook, "Atomic Test Registry").map((row) => ({
  row: row.__row,
  registryId: clean(row["Atomic Test Registry ID"]),
  registryStatus: clean(row["Registry Status"]),
  origin: clean(row["Test Origin"]),
  featureId: clean(row["Atomic Feature ID"]),
  featureName: clean(row["Atomic Feature Name"]),
  officialSheet: clean(row["Official Feature Sheet"]),
  officialL1: clean(row["Official Level 1 Feature"]),
  officialL2: clean(row["Official Level 2 Feature"]),
  testName: clean(row["Atomic Test Name"]),
  testType: clean(row["Test Type"]),
  result: clean(row["Historical Result / Planned Status"]),
  oldFeatureId: clean(row["Old Feature ID"]),
  oldPart: clean(row["Old Part"]),
  oldWorkbookRow: clean(row["Old Workbook Row"]),
  notes: clean(row["Notes / Exclusion Reason"]),
}));

const newBindings = rowsFromSheet(newBook, "Atomic Test Binding").map((row) => ({
  row: row.__row,
  bindingId: clean(row["Atomic Test Binding ID"]),
  featureId: clean(row["Atomic Feature ID"]),
  featureName: clean(row["Atomic Feature Name"]),
  mappingSource: clean(row["Mapping Source"]),
  testName: clean(row["Atomic Test Name"]),
  result: clean(row["Test Result / Planned Status"]),
  oldFeatureId: clean(row["Old Feature ID"]),
  oldWorkbookRow: clean(row["Old Workbook Row"]),
}));

const unmapped = rowsFromSheet(newBook, "Unmapped Historical Tests").map((row) => ({
  row: row.__row,
  oldFeatureId: clean(row["Old Feature ID"]),
  oldPart: clean(row["Old Part"]),
  featureName: clean(row["Old Atomic Feature"]),
  testName: clean(row["Suggested Test Name"]),
  result: clean(row["Historical Test Result"]),
  reason: clean(row["Why Not In Current Feature Hierarchy"]),
}));

const featureRegistry = rowsFromSheet(newBook, "Atomic Feature Registry").map((row) => ({
  row: row.__row,
  featureId: clean(row["Atomic Feature ID"]),
  featureName: clean(row["Atomic Feature Name"]),
  source: clean(row["Atomic Feature Source"]),
  oldFeatureIds: clean(row["Old Feature IDs"]).split(/[;,]/).map((value) => value.trim()).filter(Boolean),
  boundCount: Number(row["Bound Atomic Test Count"] ?? 0),
  boundNames: clean(row["Bound Atomic Test Names"]),
  statusMix: clean(row["Result Mix / Planned Status"]),
}));

const registryByOldId = new Map();
for (const test of newRegistry) {
  const key = test.oldFeatureId || (test.origin !== "NEW_REQUIRED_TEST" ? test.featureId : "");
  if (!key) continue;
  if (!registryByOldId.has(key)) registryByOldId.set(key, []);
  registryByOldId.get(key).push(test);
}

const unmappedById = new Map(unmapped.map((row) => [row.oldFeatureId, row]));
const featureRegistryOldIds = new Set(featureRegistry.flatMap((row) => row.oldFeatureIds));

const missingOldTests = [];
const duplicateOldMatches = [];
const renamedTests = [];
const statusChanges = [];
const exactMatches = [];
for (const old of oldTests) {
  const matches = registryByOldId.get(old.featureId) ?? [];
  if (matches.length === 0) {
    missingOldTests.push(old);
    continue;
  }
  if (matches.length > 1) duplicateOldMatches.push({ old, matches });
  const exact = matches.find((test) => test.testName === old.testName) ?? matches[0];
  if (exact.testName !== old.testName) renamedTests.push({ old, current: exact });
  if (exact.result !== old.result) statusChanges.push({ old, current: exact });
  if (exact.testName === old.testName && exact.result === old.result) exactMatches.push(old.featureId);
}

const oldIds = new Set(oldTests.map((row) => row.featureId));
const newRequired = newRegistry.filter((row) => row.origin === "NEW_REQUIRED_TEST");
const registryHistorical = newRegistry.filter((row) => row.origin !== "NEW_REQUIRED_TEST");
const newRequiredFeatureIds = new Set(newRequired.map((row) => row.featureId));
const boundHistorical = newBindings.filter((row) => row.mappingSource === "HISTORICAL_OLD_TEST");
const boundNew = newBindings.filter((row) => row.mappingSource === "NEW_REQUIRED_TEST");
const oldIdsNotInBoundFeatureRegistry = [...oldIds].filter((id) => !featureRegistryOldIds.has(id)).sort();
const oldIdsNotInUnmapped = oldIdsNotInBoundFeatureRegistry.filter((id) => !unmappedById.has(id));

const summary = {
  files: { oldPath, newPath },
  old: {
    atomicTestRows: oldTests.length,
    uniqueFeatureIds: oldIds.size,
    uniqueTestNames: new Set(oldTests.map((row) => row.testName)).size,
    resultCounts: countBy(oldTests, "result"),
  },
  new: {
    atomicFeatureRegistryRows: featureRegistry.length,
    atomicTestBindingRows: newBindings.length,
    atomicTestRegistryRows: newRegistry.length,
    unmappedHistoricalRows: unmapped.length,
    originCounts: countBy(newRegistry, "origin"),
    registryStatusCounts: countBy(newRegistry, "registryStatus"),
    resultCounts: countBy(newRegistry, "result"),
    mappingSourceCounts: countBy(newBindings, "mappingSource"),
    featureSourceCounts: countBy(featureRegistry, "source"),
    newRequiredTestCount: newRequired.length,
    newRequiredFeatureCount: newRequiredFeatureIds.size,
    newRequiredResultCounts: countBy(newRequired, "result"),
    newRequiredByOfficialSheet: countBy(newRequired, "officialSheet"),
    newRequiredByTestType: countBy(newRequired, "testType"),
    newRequiredOfficialL2Count: new Set(newRequired.map((row) => `${row.officialSheet}::${row.officialL2}`)).size,
    newRequiredOfficialL2: [...new Set(newRequired.map((row) => `${row.officialSheet} :: ${row.officialL2}`))].sort(),
    unmappedByOldPart: countBy(unmapped, "oldPart"),
    unmappedByReason: countBy(unmapped, "reason"),
  },
  historicalComparison: {
    historicalRegistryRows: registryHistorical.length,
    exactNameAndResultMatches: exactMatches.length,
    missingOldTestsCount: missingOldTests.length,
    renamedTestsCount: renamedTests.length,
    statusChangesCount: statusChanges.length,
    duplicateOldMatchesCount: duplicateOldMatches.length,
    boundHistoricalCount: boundHistorical.length,
    unmappedHistoricalCount: unmapped.length,
    oldFeatureIdsNotBoundToOfficialHierarchyCount: oldIdsNotInBoundFeatureRegistry.length,
    oldFeatureIdsNeitherBoundNorInUnmappedCount: oldIdsNotInUnmapped.length,
  },
  anomalies: {
    missingOldTests,
    renamedTests,
    statusChanges,
    duplicateOldMatches,
    oldIdsNeitherBoundNorInUnmapped: oldIdsNotInUnmapped,
  },
  samples: {
    unmappedHistorical: unmapped.slice(0, 20),
    newRequired: newRequired.slice(0, 20),
    boundNew: boundNew.slice(0, 20),
  },
};

await fs.writeFile("comparison-summary.json", JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
