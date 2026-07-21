import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/jamesyuan/Downloads/ai4research final l1 l2 feature deliverable.xlsx";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/019f60e6-f228-7b60-85aa-5578ac437263";
const outputPath = `${outputDir}/ai4research final l1 l2 feature deliverable.xlsx`;

const replacements = [
  {
    start: 2,
    end: 14,
    items: [
      ["Request Capture", "Receives the user’s question, instruction, desired outcome, and requested deliverable as an intake candidate without prematurely treating it as a formal requirement."],
      ["Qualified Channel Signal Intake", "Accepts a V-05-qualified Slack or internal-tool clue with its permitted context, sensitivity, relevance, and provenance; raw channel traffic remains outside Workflow."],
      ["User-Supplied Material Import", "Imports documents, uploads, pasted content, datasets, and explicit file, repository, or URL references supplied by the user; related-source discovery belongs to Search & Ideation."],
      ["Intake Context Binding", "Binds the candidate to the authorized user, session, workspace, project, originating signal, and explicitly selected prior artifacts needed for interpretation."],
      ["Real-Time Intake Deduplication & Cleaning", "Canonicalizes incoming candidates, filters malformed or noisy content, and merges replays, exact duplicates, and near-duplicates while preserving meaningful revisions and independent corroboration."],
      ["Intake Provenance Registration", "Records origin, identity, version, timestamp, access path, acquisition mode, and transformations for every accepted intake input."],
      ["Intake Qualification", "Checks accessibility, authorization, readability, and minimum completeness, then emits a qualified intake package or an explicit rejection or quarantine reason."],
    ],
  },
  {
    start: 15,
    end: 60,
    items: [
      ["Intent Interpretation", "Determines the user’s actual problem, desired change, audience, decision, and deliverable without selecting an opportunity or solution."],
      ["Context Scoping", "Resolves applicable context, affected entities, time horizon, inclusions, exclusions, and the boundary of the decision to support."],
      ["Ambiguity Resolution", "Finds missing information, conflicting instructions, undefined terms, and consequential assumptions and resolves them through focused questions or explicit defaults."],
      ["Constraint Resolution", "Identifies and reconciles authorization, scope, time, cost, data, safety, policy, tool, environment, and output-format constraints with the user’s intended outcome."],
      ["Requirement Prioritization", "Separates mandatory outcomes, preferences, tradeable qualities, dependencies, exclusions, and deferred requests."],
      ["Acceptance Definition", "Defines observable success criteria, proof obligations, decision thresholds, failure conditions, and stopping rules."],
      ["Requirement Contract Confirmation", "Assembles a versioned contract with executable task semantics, presents consequential interpretations, and records user confirmation or authorized assumptions."],
    ],
  },
  {
    start: 61,
    end: 93,
    items: [
      ["Search Strategy Formation", "Turns the requirement contract into technical themes, source families, queries, time horizons, counter-signals, diversity goals, and coverage targets."],
      ["Multi-Source Signal Discovery", "Uses parallel research agents to search open-source projects, papers, patents, standards, experts, think tanks, industry reports, big-tech dynamics, technical communities, the open web, and authorized internal history."],
      ["Source Qualification", "Screens discovered material for intent relevance, authority, recency, independence, incentives, duplication, access limits, and potential bias."],
      ["Technical Signal Extraction", "Extracts claims, data, methods, mechanisms, results, benchmarks, limitations, failures, dependencies, adoption signals, and unresolved questions."],
      ["Signal Organization", "Normalizes signals, binds provenance, clusters related findings, and maps convergence, divergence, dependencies, and opposing viewpoints."],
      ["Trend & Gap Analysis", "Detects momentum, decay, contradictions, bottlenecks, missing capabilities, abandoned directions, and technical white spaces."],
      ["Idea Generation", "Expands a diverse candidate set from signal clusters, gaps, adjacencies, cross-domain transfers, and contrarian combinations while retaining initial supporting and opposing evidence."],
      ["Search Coverage Review", "Tests source-family, technical, geographic, temporal, viewpoint, and counter-evidence coverage before the candidate space is allowed to narrow."],
    ],
  },
  {
    start: 94,
    end: 101,
    items: [
      ["Candidate Consolidation", "Combines parallel search outputs, resolves semantic duplicates, and preserves variants whose assumptions, evidence, or opportunity boundaries materially differ."],
      ["Idea Identification", "Converts meaningful signal combinations and gaps into discrete candidate ideas with a recognizable technical or user value proposition."],
      ["Idea Card Formation", "Forms the governing Idea Card with the candidate’s opportunity, relevance, linked evidence, assumptions, novelty, uncertainty, risks, and open questions; evidence formation is part of this card."],
      ["Opportunity Definition", "States the unmet need, technical bottleneck, missing capability, unserved user, or unexploited combination that makes the idea actionable."],
      ["Technical Opportunity Screening", "Screens novelty, evidence maturity, reachable data, known mechanisms, technical feasibility, and the existence of a credible verification path."],
      ["Strategic Opportunity Screening", "Screens user or company value, timing, defensibility, strategic fit, adoption, safety, legal exposure, dependencies, and resource implications."],
      ["Opportunity Portfolio Prioritization", "Ranks and selects a bounded, diverse opportunity portfolio using transparent criteria and records why other directions were deferred or rejected."],
    ],
  },
];

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Workflow Features");

for (const group of replacements) {
  const rowCount = group.end - group.start + 1;
  const values = Array.from({ length: rowCount }, (_, index) => {
    const item = group.items[index];
    if (!item) return [null, null];
    const [name, description] = item;
    return [`${index + 1}. ${name}\n\n${description}`, null];
  });
  sheet.getRange(`D${group.start}:E${group.end}`).values = values;
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(formulaErrors.ndjson);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Workflow Features",
  range: "A1:F110",
  tableMaxRows: 110,
  tableMaxCols: 6,
  tableMaxCellChars: 160,
  maxChars: 22000,
});
console.log(check.ndjson);

for (const [sheetName, range] of [
  ["Workflow Features", "A1:F110"],
  ["Foundation Features", "A1:I40"],
  ["Misc Features", "A1:D50"],
]) {
  const rendered = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${sheetName.replaceAll(" ", "_")}.png`, new Uint8Array(await rendered.arrayBuffer()));
}

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }, null, 2));
