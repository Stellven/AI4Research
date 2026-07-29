import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import process from "node:process";

const ROOT = path.resolve(path.dirname(path.dirname(path.dirname(path.dirname(path.resolve(process.argv[1]))))));
const ARTIFACT_TOOL = pathToFileURL(
  path.resolve(
    ROOT,
    ".codex-tmp",
    "phase22-provider-audit",
    "node_modules",
    "@oai",
    "artifact-tool",
    "dist",
    "artifact_tool.mjs",
  ),
).href;
const artifact = await import(ARTIFACT_TOOL);
const { FileBlob, SpreadsheetFile } = artifact;

const SHEETS = ["Workflow Features", "Foundation Features", "Vertical Features"];
const SUMMARY_ROW_MAP = {
  sourceL2: 2,
  historical: 3,
  reviewed: 4,
  generated: 6,
  reusedExisting: 7,
  representative: 8,
  manualOracle: 9,
  externalBlocked: 10,
  blockedBoundary: 11,
  pass: 12,
  fail: 13,
  passAll: 14,
  failAny: 15,
  blockedImpl: 16,
  gapBlocked: 17,
};

function cellToValue(value) {
  return value === undefined ? null : value;
}

function countif(values, columnIndex, predicate) {
  let count = 0;
  for (const row of values) {
    if (predicate(row[columnIndex])) {
      count += 1;
    }
  }
  return count;
}

function toHeaderIndex(headerValues) {
  const headers = headerValues.map((value) => String(value || ""));
  const index = {};
  headers.forEach((header, column) => {
    index[header] = column;
  });
  return index;
}

function getColumnLetter(index) {
  let n = index + 1;
  let letters = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    letters = String.fromCharCode(65 + rem) + letters;
    n = Math.floor((n - 1) / 26);
  }
  return letters;
}

function scanFormulaErrors(values, formulas, sheetName, errors) {
  const regex = /#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/i;
  for (let r = 0; r < values.length; r += 1) {
    const row = formulas[r] || [];
    for (let c = 0; c < row.length; c += 1) {
      const formula = row[c];
      if (typeof formula === "string" && regex.test(formula)) {
        errors.push(`${sheetName}!${getColumnLetter(c)}${r + 1}:${formula}`);
      }
    }
    const valuesRow = values[r] || [];
    for (let c = 0; c < valuesRow.length; c += 1) {
      const value = valuesRow[c];
      if (typeof value === "string" && regex.test(value)) {
        errors.push(`${sheetName}!${getColumnLetter(c)}${r + 1}:${value}`);
      }
    }
  }
}

const args = Object.fromEntries(
  process.argv.slice(2).map((item) => {
    const [key, value] = item.split("=", 2);
    return [key.replace(/^--/, ""), value];
  }),
);
const matrixPath = args["matrix"] || path.join(ROOT, "tests/platform/phase22/atomic_feature_matrix.json");
const sourcePath = args["source"] || path.join(ROOT, "docs/integrations/autosci/.codex-tmp-phase22-copy.xlsx");
const outputPath = args["output"] || path.join(ROOT, ".codex-tmp/phase22-i1/phase-22-test-report.generated.xlsx");

const matrix = JSON.parse(await fs.readFile(matrixPath, "utf8"));
const matrixByAtomicId = new Map(matrix.atomic_features.map((row) => [row.atomic_feature_id, row]));
const matrixByL2 = new Map(matrix.l2_summary.map((row) => [`${row.sheet}|${row.level_2_feature}`, row]));
const sourceWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));

const statusByL2 = new Map();
for (const row of matrix.l2_summary) {
  statusByL2.set(`${row.sheet}|${row.level_2_feature}`, row.atomic_rollup_status);
}

const coverageCounts = {
  testGeneration: {},
  currentResult: {},
  coverageRelationship: {},
  rollup: {},
};
for (const row of matrix.atomic_features) {
  coverageCounts.testGeneration[row.test_generation_status] = (coverageCounts.testGeneration[row.test_generation_status] || 0) + 1;
  coverageCounts.currentResult[row.current_result] = (coverageCounts.currentResult[row.current_result] || 0) + 1;
  coverageCounts.coverageRelationship[row.coverage_relationship] = (coverageCounts.coverageRelationship[row.coverage_relationship] || 0) + 1;
}
for (const row of matrix.l2_summary) {
  coverageCounts.rollup[row.atomic_rollup_status] = (coverageCounts.rollup[row.atomic_rollup_status] || 0) + 1;
}

function gapSeverityFormulaKey(count) {
  if (count >= 15) return "CRITICAL";
  if (count >= 10) return "HIGH";
  if (count >= 5) return "MEDIUM";
  return "LOW";
}

function rollupResolution(l2Rows, status) {
  if (status === "FUNCTION_IMPLEMENTED_ALL_ATOMIC_TESTS_PASSED") return "COMPLETE_PASS";
  if (status === "FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED") return "COMPLETE_FAIL";
  if (status === "FUNCTION_NOT_IMPLEMENTED_TEST_BLOCKED") return "IMPLEMENTATION_BLOCKED";
  if (status === "IMPLEMENTED_TEST_GAP_BLOCKED") {
    const implemented = l2Rows.filter((row) => row.implementation_status !== "NOT_IMPLEMENTED");
    const bound = implemented.filter((row) => row.test_selector).length;
    const missing = implemented.length - bound;
    return `TEST_GAPS_TAGGED_${gapSeverityFormulaKey(Math.max(0, missing))}`;
  }
  return "INCONCLUSIVE";
}

const errors = [];
let atomicRows = 0;

for (const sheetName of SHEETS) {
  const sheet = sourceWorkbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange().values.map((row) => row.map(cellToValue));
  const formulas = sheet.getUsedRange().formulas.map((row) => row.map((value) => value || null));
  const headerIndex = toHeaderIndex(values[1]);
  const atomicIdCol = headerIndex["Atomic Feature ID"];
  const implCol = headerIndex["Atomic Implementation Status"];
  const statusCol = headerIndex["Atomic Test Generation Status"];
  const relCol = headerIndex["Atomic Coverage Relationship"];
  const bindingCol = headerIndex["Test Binding ID"];
  const nameCol = headerIndex["Test Name"];
  const fileCol = headerIndex["Test File"];
  const selectorCol = headerIndex["Test Selector"];
  const runnerCol = headerIndex["Runner"];
  const commandCol = headerIndex["Runner Command"];
  const currentCol = headerIndex["Atomic Current Result"];
  const confidenceCol = headerIndex["Mapping Confidence"];
  const basisCol = headerIndex["Mapping Basis"];
  const attemptCol = headerIndex["Generation Attempt"];
  const notesCol = headerIndex["Blocker / Notes"];
  const resolutionCol = headerIndex["Atomic Coverage Resolution"];
  const rollupStatusCol = headerIndex["L2 Atomic Rollup Status"];
  const rollupReasonCol = headerIndex["L2 Atomic Rollup Reason"];
  const l2Col = headerIndex["Level 2 Feature"];

  let currentL2 = null;
  let currentGroup = [];
  let groupStart = 0;
  for (let rowIndex = 2; rowIndex < values.length; rowIndex += 1) {
    const row = values[rowIndex];
    const atomicId = String(row[atomicIdCol] || "").trim();
    if (!atomicId) {
      continue;
    }
    atomicRows += 1;
    const sourceRow = matrixByAtomicId.get(atomicId);
    if (!sourceRow) {
      throw new Error(`Missing matrix row for atomic id ${atomicId}`);
    }
    row[implCol] = sourceRow.implementation_status;
    row[statusCol] = sourceRow.test_generation_status;
    row[relCol] = sourceRow.coverage_relationship;
    row[bindingCol] = sourceRow.test_binding_id;
    row[nameCol] = sourceRow.test_name;
    row[fileCol] = sourceRow.test_file;
    row[selectorCol] = sourceRow.test_selector;
    row[runnerCol] = sourceRow.runner;
    row[commandCol] = sourceRow.runner_command;
    row[currentCol] = sourceRow.current_result;
    row[confidenceCol] = sourceRow.mapping_confidence;
    row[basisCol] = sourceRow.mapping_basis;
    row[attemptCol] = sourceRow.generation_attempt;
    row[notesCol] = sourceRow.blocker_or_notes;

    const level2 = String(row[l2Col] || "");
    if (currentL2 !== level2) {
      if (currentL2 && currentGroup.length && (currentL2 !== level2)) {
        const summary = matrixByL2.get(`${sheetName}|${currentL2}`);
        const key = `${sheetName}|${currentL2}`;
        const l2Status = matrixByL2.get(key)?.atomic_rollup_status;
        const resolution = rollupResolution(
          currentGroup,
          l2Status || "IMPLEMENTED_TEST_GAP_BLOCKED",
        );
        values[groupStart][resolutionCol] = resolution;
        values[groupStart][rollupStatusCol] = l2Status || "IMPLEMENTED_TEST_GAP_BLOCKED";
        values[groupStart][rollupReasonCol] = matrixByL2.get(key)?.atomic_rollup_reason || "";
        currentGroup = [];
      }
      currentL2 = level2;
      currentGroup = [];
      groupStart = rowIndex;
    }
    if (currentL2 === level2) {
      currentGroup.push({
        implementation_status: sourceRow.implementation_status,
        test_selector: sourceRow.test_selector,
      });
    }
  }
  if (currentL2 && currentGroup.length) {
    const summary = matrixByL2.get(`${sheetName}|${currentL2}`);
    const l2Status = summary?.atomic_rollup_status || "IMPLEMENTED_TEST_GAP_BLOCKED";
    const resolution = rollupResolution(currentGroup, l2Status);
    values[groupStart][resolutionCol] = resolution;
    values[groupStart][rollupStatusCol] = l2Status;
    values[groupStart][rollupReasonCol] = summary?.atomic_rollup_reason || "";
  }
  sheet.getUsedRange().values = values;
  scanFormulaErrors(values, formulas, sheetName, errors);
}

const summary = sourceWorkbook.worksheets.getItem("Coverage Summary");
const summaryValues = summary.getUsedRange().values.map((row) => row.map(cellToValue));
summaryValues[2][1] = matrix.l2_summary.length;
summaryValues[3][1] = 2047;
summaryValues[4][1] = matrix.counts.reviewed_atomic_features;
summaryValues[5][1] = matrix.counts.net_rows_removed;
summaryValues[6][1] = coverageCounts.testGeneration.GENERATED_EXECUTABLE || 0;
summaryValues[7][1] = coverageCounts.testGeneration.REUSED_EXISTING_EXECUTABLE || 0;
summaryValues[8][1] = coverageCounts.testGeneration.REUSED_L2_REPRESENTATIVE_EXECUTABLE || 0;
summaryValues[9][1] = (coverageCounts.testGeneration.MANUAL_ORACLE_REQUIRED || 0) + (coverageCounts.testGeneration.TAGGED_NOT_GENERATED_MANUAL_ORACLE || 0);
summaryValues[10][1] = (coverageCounts.testGeneration.PLATFORM_OR_HARDWARE_REQUIRED || 0);
summaryValues[11][1] = coverageCounts.testGeneration.BLOCKED_NOT_IMPLEMENTED || 0;
summaryValues[12][1] = coverageCounts.currentResult.PASS || 0;
summaryValues[13][1] = coverageCounts.currentResult.FAIL || 0;
summaryValues[14][1] = coverageCounts.rollup.FUNCTION_IMPLEMENTED_ALL_ATOMIC_TESTS_PASSED || 0;
summaryValues[15][1] = coverageCounts.rollup.FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED || 0;
summaryValues[16][1] = coverageCounts.rollup.FUNCTION_NOT_IMPLEMENTED_TEST_BLOCKED || 0;
summaryValues[17][1] = coverageCounts.rollup.IMPLEMENTED_TEST_GAP_BLOCKED || 0;
summaryValues[29][1] = 0;
summary.getUsedRange().values = summaryValues;

const summaryFormulas = summary.getUsedRange().formulas.map((row) => row.map((value) => value || null));
scanFormulaErrors(summaryValues, summaryFormulas, "Coverage Summary", errors);

const outputDir = path.dirname(outputPath);
await fs.mkdir(outputDir, { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(sourceWorkbook);
await exported.save(outputPath);

const verifier = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const verifierValues = verifier.worksheets.getItem("Coverage Summary").getUsedRange().values;
const formulaErrorCount = errors.length;
const rowCount = atomicRows;
const l2Count = matrix.l2_summary.length;

await fs.writeFile(
  path.join(outputDir, "workbook-validation.json"),
  JSON.stringify(
    {
      output_path: outputPath,
      atomic_rows: rowCount,
      l2_rows: l2Count,
      matrix_rows: matrix.atomic_features.length,
      summary_verifier_preview: {
        row3_14: {
          l2: verifierValues[2]?.[1],
          reviewed: verifierValues[4]?.[1],
          pass: verifierValues[12]?.[1],
          fail: verifierValues[13]?.[1],
        },
      },
      formula_errors: formulaErrorCount,
    },
    null,
    2,
  ),
);
console.log(JSON.stringify({ outputPath, formula_errors: formulaErrorCount, atomic_rows: rowCount, l2_rows: l2Count }, null, 2));
