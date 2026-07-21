import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research_short feature list.xlsx";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263";
const outputPath = `${outputDir}/ai4research_short feature list.xlsx`;
const previewDir = "/private/tmp/ai4research_misc_l2_work/final_previews";

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Misc Features");
const originalRows = sheet.getRange("A2:E30").values;

const records = new Map();
const level1Texts = [];
for (const row of originalRows) {
  const [id, part, level1, , level3] = row;
  if (id) {
    if (records.has(id)) throw new Error(`Duplicate visible_feature_id: ${id}`);
    records.set(id, { id, part, level3 });
  }
  if (level1) level1Texts.push(level1);
}

function findLevel1(prefix) {
  const value = level1Texts.find((text) => String(text).startsWith(prefix));
  if (!value) throw new Error(`Missing L1 text for ${prefix}`);
  return value;
}

const blocks = [
  {
    level1: findLevel1("Visibility / Statistics"),
    candidates: [
      {
        name: "Workflow & Platform Status Visibility",
        description: "Show workflow progress, blockers, gates, budgets, and the health of hosts, providers, queues, data sources, and other platform components without changing authoritative runtime state.",
        ids: ["MS-B006"],
      },
      {
        name: "Execution Trace Search & Inspection",
        description: "Search and inspect time-ordered requests, transitions, tool calls, approvals, failures, artifacts, decisions, and outcomes using filters for project, run, actor, and time range.",
        ids: ["MS-B002"],
      },
      {
        name: "Opportunity & Innovation Portfolio Analytics",
        description: "Analyze source coverage, signal momentum, opportunity maturity, risk, value, ranking, strategic fit, and portfolio diversity at both opportunity and portfolio levels.",
        ids: ["MS-B003"],
      },
      {
        name: "Experiment & Evaluation Analytics",
        description: "Aggregate experiment queues, variants, iteration history, failures, budget burn, baseline comparisons, uncertainty, regressions, reproducibility, and evaluation verdicts.",
        ids: ["MS-B004"],
      },
      {
        name: "Resource Usage, Cost & Capacity Analytics",
        description: "Report model, compute, token, tool, storage, data, quota, human-review, budget, cost, and capacity consumption by project, experiment, capability, and time.",
        ids: ["MS-B005"],
      },
      {
        name: "Evidence & Decision Reporting",
        description: "Produce and export source-backed reports containing evidence, provenance, metrics, evaluations, decisions, investment judgments, and capability references.",
        ids: ["MS-B001"],
      },
    ],
  },
  {
    level1: findLevel1("Installer & CLI & Webapp"),
    candidates: [
      {
        name: "Guided Installation & Product Initialization",
        description: "Guide users through product installation, provision selected dependencies and services, and initialize storage, default configuration, providers, integrations, and product state.",
        ids: ["MS-B011", "MS-B017"],
      },
      {
        name: "Installation Readiness Validation",
        description: "Validate operating-system, hardware, dependency, permission, network, storage, provider, access-surface, and minimal end-to-end readiness before and after installation.",
        ids: ["MS-B010"],
      },
      {
        name: "Installation Diagnostics & Repair",
        description: "Diagnose and repair missing dependencies, broken configuration, failed services, permission errors, stale state, and installation drift.",
        ids: ["MS-B016"],
      },
      {
        name: "Product Update, Migration & Rollback",
        description: "Update application components and schemas, perform required migrations, verify the upgraded installation, and restore the prior working version when necessary.",
        ids: ["MS-B013"],
      },
      {
        name: "Safe Uninstallation & Data Disposition",
        description: "Remove installed components and services while preserving, exporting, or securely deleting product data according to explicit user choices.",
        ids: ["MS-B008"],
      },
      {
        name: "CLI Product Access",
        description: "Provide coherent command-line access to research tasks, runs, configuration, diagnostics, updates, exports, and product lifecycle operations without splitting the feature by individual command.",
        ids: ["MS-B009", "MS-B015", "MS-B012", "MS-B007"],
      },
      {
        name: "Web Application Access",
        description: "Start and securely expose the web application in an approved local or shared environment and verify browser access and service health.",
        ids: ["MS-B018"],
      },
      {
        name: "Supported Environment Packaging",
        description: "Produce and maintain installable product packages for the operating systems and execution environments the product explicitly supports.",
        ids: ["MS-B014"],
      },
    ],
  },
  {
    level1: findLevel1("UI"),
    candidates: [
      {
        name: "Conversational Research Interaction",
        description: "Let users express research goals, provide materials, answer clarifications, guide active work, challenge conclusions, and receive decision-oriented explanations through conversation.",
        ids: ["MS-B019"],
      },
      {
        name: "Work Navigation & Organization",
        description: "Let users browse, search, organize, resume, and compare workspaces, topics, projects, opportunity portfolios, experiments, sessions, and runs.",
        ids: ["MS-B020"],
      },
      {
        name: "Research Signal Exploration",
        description: "Let users inspect source families, papers, reports, experts, company dynamics, open-web signals, clusters, gaps, coverage, freshness, and credibility.",
        ids: [],
      },
      {
        name: "Opportunity Review & Portfolio Workspace",
        description: "Let users inspect, compare, annotate, enrich, merge, split, rank, defer, or reject opportunities and analyze the portfolio through an interactive matrix.",
        ids: [],
      },
      {
        name: "Experiment Workspace",
        description: "Let users inspect and edit hypotheses, verification paths, POCs, experiments, scripts, queues, budgets, gates, failures, and stop conditions.",
        ids: [],
      },
      {
        name: "Evidence Review & Collaborative Evaluation",
        description: "Let reviewers compare evidence, POCs, variants, baselines, metrics, uncertainty, failures, and reproducibility, request evidence or reruns, record dissent, and approve, defer, or terminate directions.",
        ids: [],
      },
      {
        name: "Investment Decision Workspace",
        description: "Let decision makers compare investment targets, recommendations, expected value, resource commitments, milestones, risks, options, and technical roadmaps and record their decisions.",
        ids: [],
      },
      {
        name: "Capability Library & Reuse Interface",
        description: "Let users discover, compare, inspect evidence for, invoke, compose, reuse, and provide feedback on available capabilities and capsules.",
        ids: [],
      },
      {
        name: "Live Execution Inspection",
        description: "Let users inspect active plans, dependencies, operators, hosts, models, tools, gates, resource use, failures, recovery actions, and expected next steps without managing authoritative runtime state.",
        ids: ["MS-B021"],
      },
      {
        name: "Research Interaction Preferences",
        description: "Let users configure permitted sources, quality, cost, speed, autonomy, approvals, privacy, notifications, presentation, and accessibility preferences for research work.",
        ids: [],
      },
    ],
  },
  {
    level1: findLevel1("Account management"),
    candidates: [
      {
        name: "Account Registration",
        description: "Create an individual product account with verified identity, accepted terms, and initial personal settings.",
        ids: [],
      },
      {
        name: "Authentication & Session Security",
        description: "Support secure sign-in, sign-out, session establishment, reauthentication, recovery, session revocation, and suspicious-access visibility.",
        ids: ["MS-B022", "MS-B024"],
      },
      {
        name: "User Profile Management",
        description: "Manage identity, expertise, role, research preferences, notification choices, accessibility choices, and default product behavior.",
        ids: ["MS-B023"],
      },
      {
        name: "Privacy & Personal Data Controls",
        description: "Let users inspect, export, retain, or delete personal settings and supplied data and manage consent for message-derived information.",
        ids: [],
      },
    ],
  },
  {
    level1: findLevel1("Message channels"),
    candidates: [
      {
        name: "Channel Connection Management",
        description: "Establish, test, disable, and maintain authorized Slack and supported messaging, collaboration, incident, project, and knowledge-tool connections.",
        ids: ["MS-B026"],
      },
      {
        name: "Channel Sensing Governance",
        description: "Define which workspaces, channels, conversations, participants, content classes, time windows, and events may be sensed, retained, and used for research intake.",
        ids: [],
      },
      {
        name: "Continuous Channel Signal Capture",
        description: "Continuously observe authorized channel activity and capture permitted messages, replies, edits, reactions, mentions, attachments, links, participants, threads, and workspace context.",
        ids: [],
      },
      {
        name: "Channel Signal Discovery & Qualification",
        description: "Normalize captured channel content, detect potentially valuable weak signals, filter noise and restricted information, and correlate related clues into reviewable qualified signals.",
        ids: [],
      },
      {
        name: "Qualified Signal Routing",
        description: "Package qualified signals with context, provenance, sensitivity, relevance, and suggested intake scope and route them into W1 without compiling requirements or selecting opportunities.",
        ids: ["MS-B028", "MS-B027", "MS-B025"],
      },
    ],
  },
  {
    level1: findLevel1("Configurations / LLM providers"),
    candidates: [
      {
        name: "Configuration Management",
        description: "Let authorized users inspect and edit supported settings, resolve the effective value across configuration layers, and validate changes before activation.",
        ids: [],
      },
      {
        name: "Configuration Profile Lifecycle",
        description: "Import, export, compare, version, migrate, apply, and roll back portable configuration profiles without exposing protected secrets.",
        ids: [],
      },
      {
        name: "Research Source Configuration",
        description: "Configure repositories, indexes, websites, feeds, message targets, sensing scope, crawl limits, freshness, licensing, consent, and connector policy.",
        ids: [],
      },
      {
        name: "Experiment Infrastructure Configuration",
        description: "Configure code environments, clusters, sandboxes, data stores, simulations, job systems, benchmark runners, demo environments, quotas, and isolation policy.",
        ids: [],
      },
      {
        name: "Decision & Review Policy Configuration",
        description: "Configure strategy, technical priorities, investment horizon, risk appetite, review roles, evidence thresholds, gates, resource assumptions, and decision vocabulary.",
        ids: [],
      },
      {
        name: "Operator & Capsule Configuration",
        description: "Configure operator roles and policies, capsule catalogs and availability, host eligibility, verification thresholds, and capability lifecycle rules.",
        ids: [],
      },
      {
        name: "LLM Provider Connection & Diagnostics",
        description: "Register, edit, test, disable, and remove provider connections and diagnose credentials, endpoints, model access, quotas, billing, network, region, capacity, policy, and adapter failures.",
        ids: ["MS-B029"],
      },
      {
        name: "Credential Reference Management",
        description: "Manage protected credential references, authentication methods, rotation state, and access scope for models, sources, repositories, data, compute, channels, and services.",
        ids: [],
      },
      {
        name: "Model Governance Configuration",
        description: "Configure model identifiers, modalities, context limits, pricing, regions, role eligibility, enablement, data classes, budgets, and provider or model restrictions.",
        ids: [],
      },
    ],
  },
];

const usedIds = [];
const outputRows = [];
const level1Segments = [];
const level2Segments = [];
let rowNumber = 2;

for (const block of blocks) {
  const blockStart = rowNumber;
  block.candidates.forEach((candidate, index) => {
    const annotation = `${index + 1}. ${candidate.name}\n\n${candidate.description}`;
    const assigned = candidate.ids.length
      ? candidate.ids.map((id) => {
          const record = records.get(id);
          if (!record) throw new Error(`Unknown mapped visible_feature_id: ${id}`);
          usedIds.push(id);
          return record;
        })
      : [{ id: null, part: "misc", level3: null }];

    const segmentStart = rowNumber;
    for (const record of assigned) {
      outputRows.push([
        record.id,
        record.part || "misc",
        block.level1,
        annotation,
        record.level3,
      ]);
      rowNumber += 1;
    }
    level2Segments.push({ start: segmentStart, end: rowNumber - 1 });
  });
  level1Segments.push({ start: blockStart, end: rowNumber - 1 });
}

const finalRow = rowNumber - 1;
if (blocks.reduce((sum, block) => sum + block.candidates.length, 0) !== 42) {
  throw new Error("Expected exactly 42 Misc L2 candidates");
}
if (new Set(usedIds).size !== records.size || usedIds.length !== records.size) {
  const missing = [...records.keys()].filter((id) => !usedIds.includes(id));
  throw new Error(`L3 preservation mapping is incomplete; missing=${missing.join(",")}`);
}

for (let row = 31; row <= finalRow; row += 1) {
  sheet.getRange("A30:N30").copyTo(sheet.getRange(`A${row}:N${row}`), "all");
}

sheet.getRange("C2:D80").unmerge();
sheet.getRange("A2:E80").clear({ applyTo: "contents" });
sheet.getRange(`A2:E${finalRow}`).values = outputRows;
sheet.getRange(`A2:E${finalRow}`).format.wrapText = true;
sheet.getRange(`A2:E${finalRow}`).format.horizontalAlignment = "left";
sheet.getRange(`A2:N${finalRow}`).format.rowHeight = 185;

for (const segment of level1Segments) {
  if (segment.end > segment.start) {
    sheet.getRange(`C${segment.start}:C${segment.end}`).merge();
  }
}
for (const segment of level2Segments) {
  if (segment.end > segment.start) {
    sheet.getRange(`D${segment.start}:D${segment.end}`).merge();
  }
}

const finalValues = sheet.getRange(`A2:E${finalRow}`).values;
const finalRecordMap = new Map(
  finalValues
    .filter((row) => row[0])
    .map((row) => [row[0], row[4]]),
);
if (finalRecordMap.size !== records.size) {
  throw new Error(`Expected ${records.size} preserved L3 rows, found ${finalRecordMap.size}`);
}
for (const [id, record] of records.entries()) {
  if (finalRecordMap.get(id) !== record.level3) {
    throw new Error(`level_3_feature_bundle changed for ${id}`);
  }
}

for (const [sheetName, range] of [
  ["Workflow Features", "A1:E24"],
  ["Foundation Features", "A1:E24"],
  ["Misc Features", `A1:E${finalRow}`],
]) {
  const preview = await workbook.render({
    sheetName,
    range,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    `${previewDir}/${sheetName.replaceAll(" ", "_")}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const inspection = await workbook.inspect({
  kind: "table",
  sheetId: "Misc Features",
  range: `A1:E${finalRow}`,
  include: "values,formulas",
  tableMaxRows: finalRow,
  tableMaxCols: 5,
  tableMaxCellChars: 2000,
  maxChars: 120000,
});
await fs.writeFile(`${previewDir}/Misc_Features_final.ndjson`, inspection.ndjson, "utf8");

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fs.writeFile(`${previewDir}/formula_errors.ndjson`, errors.ndjson, "utf8");

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(JSON.stringify({ outputPath, finalRow, candidateCount: 42, preservedL3Count: records.size }));
