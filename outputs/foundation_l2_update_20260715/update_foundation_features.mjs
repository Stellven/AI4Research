import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = "/Users/jamesyuan/Downloads/ai4research_short feature list.xlsx";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/foundation_l2_update_20260715";
const finalPath = path.join(outputDir, "ai4research_short feature list.xlsx");

await fs.mkdir(outputDir, { recursive: true });
const input = await FileBlob.load(sourcePath);
const workbook = await SpreadsheetFile.importXlsx(input);

if (process.argv.includes("--inspect-only")) {
  const sheet = workbook.worksheets.getItem("Foundation Features");
  const used = sheet.getUsedRange();
  const anchors = used.values
    .map((row, index) => ({
      row: index + 1,
      id: row[0],
      level1: row[2],
      level2: row[4],
      level3: row[5],
    }))
    .filter((row) => row.row === 1 || row.level1);
  console.log(JSON.stringify({
    sheetNames: workbook.worksheets.items.map((item) => item.name),
    table: sheet.tables.items.map((item) => ({ name: item.name, style: item.style, showHeaders: item.showHeaders, showFilterButton: item.showFilterButton })),
    usedRangeAddress: used.address,
    anchors: anchors.map((row) => ({
      row: row.row,
      id: row.id,
      level1: typeof row.level1 === "string" ? row.level1.split("\n")[0] : row.level1,
      level2: typeof row.level2 === "string" ? row.level2.split("\n")[0] : row.level2,
    })),
  }, null, 2));

  try {
    const preview = await workbook.render({
      sheetName: "Foundation Features",
      range: "A1:F40",
      scale: 1,
      format: "png",
    });
    await fs.writeFile(path.join(outputDir, "foundation_features_before.png"), new Uint8Array(await preview.arrayBuffer()));
  } catch (error) {
    console.error(`RENDER_ERROR: ${error?.message ?? String(error)}`);
  }
  process.exit(0);
}

const groups = [
  {
    match: "Capability capsule",
    features: [
      "Capability Contract Management",
      "Capsule Packaging",
      "Capability Verification & Certification",
      "Capsule Registry Management",
      "Capability Discovery, Scoring & Selection",
      "Capsule Invocation",
      "Capsule Composition",
      "Capsule Evolution",
    ],
  },
  {
    match: "Operators",
    features: [
      "Operator Registration",
      "Operator Profile Management",
      "Operator Capability Profiling",
      "Operator Qualification",
      "Operator Eligibility Matching",
      "Operator Selection",
      "Operator Performance Learning",
      "Operator Independence Control",
      "Logical Operator Contract Management",
      "Logical-to-Physical Binding Eligibility",
      "Operator Architecture Boundary Enforcement",
    ],
  },
  {
    match: "Evaluator",
    features: [
      "Evaluation Contract Management",
      "Evaluation Method Selection",
      "Evaluator Assignment",
      "Reasoning & External Plausibility Verification",
      "Evaluation Calibration",
      "Evidence Admissibility & Sufficiency Gating",
      "Human Review Gate Management",
      "Evaluation Verdict Generation",
      "Evaluation Quality Learning",
      "Lifecycle, Parity & Runtime Claim Evaluation",
      "Operator Contract & Boundary Validation",
    ],
  },
  {
    match: "Foundational models",
    features: [
      "Model Capability Registry",
      "Model Routing & Selection",
      "Model Context Preparation",
      "Model Invocation",
      "Model Tool-Use Mediation",
      "Model Response Normalization",
      "Model Continuity Management",
      "Model Availability & Fallback Management",
      "Model Policy Enforcement",
      "Model Usage Auditing",
      "Model/Provider Runtime Configuration",
      "Model Performance Monitoring",
    ],
  },
  {
    match: "RSI",
    features: [
      "Improvement Experience Capture",
      "Improvement Pattern Discovery",
      "Improvement Opportunity Formation",
      "Improvement Candidate Generation",
      "Improvement Experimentation",
      "Improvement Evaluation",
      "Improvement Deployment Control",
      "Improvement Policy Calibration",
    ],
  },
  {
    match: "Data foundations",
    features: [
      "Unified Data Access",
      "Source Connector Management",
      "Source Acquisition & Structural Normalization",
      "Data Quality Validation & Remediation",
      "Data Semantics & Schema Management",
      "Data Lineage & Provenance Management",
      "Hybrid Retrieval",
      "Research Knowledge Graph Management",
      "Opportunity Graph Management",
      "Opportunity Metadata Enrichment",
      "Evidence Ledger Management",
      "Research Asset Repository",
      "Failure Knowledge Repository",
      "Technical Memory Management",
      "Data Governance",
      "Evidence & Artifact Contract Storage",
    ],
  },
  {
    match: "Harness Core",
    features: [
      "Run Initialization",
      "Work Readiness & Task Graph Scheduling",
      "Execution Assignment, Queueing & Dispatch",
      "Execution Environment Provisioning",
      "Execution Admission, Approval, Lease & Concurrency Control",
      "Execution Recordkeeping",
      "Experiment Loop Automation",
      "Run Recovery Control",
      "Artifact Routing",
      "Run Closure Assurance",
      "Runtime Bridge & Route Execution",
      "Runtime State and Status Management",
      "Actor Host & Physical Host Management",
      "Runtime Operator Binding Activation",
    ],
  },
  {
    match: "Intention compilers",
    features: [
      "Compiler Profile Selection",
      "Intent Classification & Command Parsing",
      "Goal Extraction & Parameter Binding",
      "Context Projection",
      "Ambiguity Detection",
      "Clarification Generation",
      "Constraint Compilation",
      "Task Contract Compilation",
      "Contract Traceability",
      "Execution Envelope Construction",
      "Approval Contract Compilation",
    ],
  },
  {
    match: "Planner",
    features: [
      "Task Decomposition",
      "Planning Strategy Selection",
      "Research and Experiment Planning",
      "Report and Delivery Handoff Planning",
      "Dependency Graph Formation",
      "Execution Requirement Compilation",
      "Resource Planning",
      "Assurance Planning",
      "Plan Validation",
      "Physical Plan Selection",
      "Plan Evolution",
      "Runtime Execution Planning",
      "Physical Operator Binding Planning",
    ],
  },
  {
    match: "Builder",
    features: [
      "Build Contract Interpretation",
      "Build Preparation",
      "Code Construction",
      "Model Construction",
      "Experimental Asset Construction",
      "Benchmark Asset Construction",
      "Verification Asset Construction",
      "Decision Artifact Construction",
      "Prototype Assembly",
      "Product Integration",
      "Defect Repair",
      "Build Evidence Generation",
      "Report/Paper/Deliverable Construction",
      "Runtime Deliverable Construction",
    ],
  },
];

const sheet = workbook.worksheets.getItem("Foundation Features");
const originalValues = sheet.getRange("A1:F91").values;
const level1ByMatch = new Map();
for (const group of groups) {
  const found = originalValues.find((row) => typeof row[2] === "string" && row[2].startsWith(group.match));
  if (!found) throw new Error(`Could not locate Foundation L1: ${group.match}`);
  level1ByMatch.set(group.match, found[2]);
}

const headers = [[
  "visible_feature_id",
  "part",
  "level_1_feature",
  "system_scope",
  "level_2_feature",
  "level_3_feature_bundle",
]];

const rows = [];
let featureNumber = 1;
for (const group of groups) {
  group.features.forEach((feature, index) => {
    rows.push([
      `FD-B${String(featureNumber).padStart(3, "0")}`,
      "foundations",
      index === 0 ? level1ByMatch.get(group.match) : null,
      null,
      feature,
      null,
    ]);
    featureNumber += 1;
  });
}

if (rows.length !== 118) throw new Error(`Expected 118 Foundation L2 rows, received ${rows.length}`);

sheet.getRange("A1:F200").unmerge();
sheet.getRange("A1:F200").clear({ applyTo: "contents" });
sheet.getRange("A1:F1").values = headers;
sheet.getRange(`A2:F${rows.length + 1}`).values = rows;

sheet.getRange("A1:F1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#D9E2F3" },
};
sheet.getRange(`A2:F${rows.length + 1}`).format = {
  verticalAlignment: "top",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#D9E2F3" },
};
sheet.getRange(`A2:B${rows.length + 1}`).format.horizontalAlignment = "left";
sheet.getRange(`C2:F${rows.length + 1}`).format.horizontalAlignment = "left";
sheet.getRange("A:A").format.columnWidth = 15;
sheet.getRange("B:B").format.columnWidth = 13;
sheet.getRange("C:C").format.columnWidth = 42;
sheet.getRange("D:D").format.columnWidth = 20;
sheet.getRange("E:E").format.columnWidth = 44;
sheet.getRange("F:F").format.columnWidth = 20;
sheet.getRange(`A1:F${rows.length + 1}`).format.autofitRows();
sheet.freezePanes.freezeRows(1);

const anchors = [];
let cursor = 2;
for (const group of groups) {
  anchors.push({ row: cursor, level1: group.match, count: group.features.length });
  cursor += group.features.length;
}

const check = await workbook.inspect({
  kind: "table",
  range: `Foundation Features!A1:F${rows.length + 1}`,
  include: "values,formulas",
  tableMaxRows: 125,
  tableMaxCols: 6,
  tableMaxCellChars: 140,
  maxChars: 40000,
});
await fs.writeFile(path.join(outputDir, "foundation_features_check.ndjson"), check.ndjson, "utf8");

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 5000,
});
console.log(JSON.stringify({ totalFoundationL2: rows.length, finalRow: rows.length + 1, anchors, formulaErrors: errors.ndjson }, null, 2));

const previewSpecs = [
  ["Workflow Features", "A1:E141", "workflow_features_after.png"],
  ["Foundation Features", `A1:F${rows.length + 1}`, "foundation_features_after.png"],
  ["Misc Features", "A1:F30", "misc_features_after.png"],
];
for (const [sheetName, range, filename] of previewSpecs) {
  const preview = await workbook.render({ sheetName, range, scale: 0.65, format: "png" });
  await fs.writeFile(path.join(outputDir, filename), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(finalPath);
console.log(`EXPORTED: ${finalPath}`);
