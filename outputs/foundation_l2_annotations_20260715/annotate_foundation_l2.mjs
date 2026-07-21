import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = "/Users/jamesyuan/Downloads/ai4research_short feature list.xlsx";
const outputDir = "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/outputs/foundation_l2_annotations_20260715";
const finalPath = path.join(outputDir, "ai4research_short feature list.xlsx");

await fs.mkdir(outputDir, { recursive: true });
const input = await FileBlob.load(sourcePath);
const workbook = await SpreadsheetFile.importXlsx(input);

if (process.argv.includes("--inspect-only")) {
  const workflowSheet = workbook.worksheets.getItem("Workflow Features");
  const foundationSheet = workbook.worksheets.getItem("Foundation Features");
  const workflowValues = workflowSheet.getRange("A1:E141").values;
  const workflowL2 = workflowValues
    .map((row, index) => ({ row: index + 1, value: row[3] }))
    .filter((item) => typeof item.value === "string" && item.value.trim().length > 0);
  const foundationValues = foundationSheet.getRange("A1:F119").values;
  const foundationL2 = foundationValues
    .slice(1)
    .map((row, index) => ({ row: index + 2, id: row[0], level1: row[2], value: row[4] }));
  console.log(JSON.stringify({ workflowL2, foundationL2 }, null, 2));

  const previews = [
    ["Workflow Features", "A1:E70", "workflow_reference_before.png"],
    ["Foundation Features", "A1:F119", "foundation_before.png"],
  ];
  for (const [sheetName, range, filename] of previews) {
    const preview = await workbook.render({ sheetName, range, scale: 0.7, format: "png" });
    await fs.writeFile(path.join(outputDir, filename), new Uint8Array(await preview.arrayBuffer()));
  }
  process.exit(0);
}

const groups = [
  {
    level1: "Capability capsule",
    features: [
      ["Capability Contract Management", "Define and version a capsule's capability scope, inputs, outputs, effects, compatibility, completion conditions, and routing constraints."],
      ["Capsule Packaging", "Bundle the capsule specification, dependencies, resources, metadata, and entry point into a loadable and distributable capability unit."],
      ["Capability Verification & Certification", "Verify capsule schema conformance, integrity, safety, and quality requirements, then grant, update, or revoke its certification status."],
      ["Capsule Registry Management", "Register, publish, index, version, update, and deprecate capsules while preserving ownership and lifecycle metadata."],
      ["Capability Discovery, Scoring & Selection", "Find compatible capsules, compare them by capability, effects, quality, cost, and policy, and select the best candidate for the task."],
      ["Capsule Invocation", "Bind inputs, context, permissions, and an execution binding to a selected capsule, invoke it, and return contract-compliant outputs and evidence."],
      ["Capsule Composition", "Combine multiple capsules by connecting their contracts, data dependencies, effects, and failure behavior into one composite capability."],
      ["Capsule Evolution", "Create, test, promote, migrate, or roll back new capsule versions from approved improvement proposals."],
    ],
  },
  {
    level1: "Operators",
    features: [
      ["Operator Registration", "Register a logical or physical operator with its identity, type, contract reference, owner, and initial status."],
      ["Operator Profile Management", "Maintain the operator's role, policy, cost, risk, quota, candidate hosts, and operational metadata."],
      ["Operator Capability Profiling", "Build an evidence-backed profile of the operator's capabilities, limitations, suitable task types, and confidence levels."],
      ["Operator Qualification", "Check an operator's contract compliance, safety, permissions, reliability, and minimum quality before it is enabled or promoted."],
      ["Operator Eligibility Matching", "Filter operators for a specific task using capability, policy, risk, quota, health, and host constraints."],
      ["Operator Selection", "Rank eligible operators by quality, cost, latency, load, independence, and fallback policy, then choose the executor."],
      ["Operator Performance Learning", "Learn task-specific success, quality, latency, cost, and failure priors from completed operator runs for future selection."],
      ["Operator Independence Control", "Enforce separation of duties, isolation, and conflict rules between builders, evaluators, and independent reviewers."],
      ["Logical Operator Contract Management", "Define and version stable logical work units, including their inputs, outputs, capability needs, effects, and completion conditions."],
      ["Logical-to-Physical Binding Eligibility", "Define which logical operator and physical actor or host combinations are valid under capability, permission, and architecture rules."],
      ["Operator Architecture Boundary Enforcement", "Prevent operators, capsules, hosts, and backends from crossing architecture layers or bypassing the shared control plane."],
    ],
  },
  {
    level1: "Evaluator",
    features: [
      ["Evaluation Contract Management", "Compile and version acceptance criteria, metrics, evidence requirements, thresholds, and verdict formats into an evaluation contract."],
      ["Evaluation Method Selection", "Choose suitable static checks, tests, benchmarks, model reviews, or human reviews for the evaluation target and risk."],
      ["Evaluator Assignment", "Assign qualified evaluators while enforcing independence, conflict-of-interest, and separation-of-duty requirements."],
      ["Reasoning & External Plausibility Verification", "Check reasoning consistency, claim-to-evidence support, and whether the result conflicts with credible external knowledge or baselines."],
      ["Evaluation Calibration", "Calibrate evaluator scores, thresholds, bias, and confidence using reference cases, historical errors, and reviewer agreement."],
      ["Evidence Admissibility & Sufficiency Gating", "Check whether evidence has an acceptable type and source and sufficiently covers the evaluation contract before a verdict is allowed."],
      ["Human Review Gate Management", "Prepare review materials, collect attributable human decisions and reasons, and manage the lifecycle of human-required gates."],
      ["Evaluation Verdict Generation", "Aggregate evaluation results into a pass, fail, blocked, or inconclusive verdict with reasons, confidence, and required follow-up."],
      ["Evaluation Quality Learning", "Track evaluator errors, drift, consistency, and feedback to improve later evaluator assignment and calibration."],
      ["Lifecycle, Parity & Runtime Claim Evaluation", "Use typed evidence to verify lifecycle completion, semantic or feature parity, and claims that real execution or side effects occurred."],
      ["Operator Contract & Boundary Validation", "Run contract, input/output, effect, smoke, and architecture-boundary checks before an operator is trusted by the system."],
    ],
  },
  {
    level1: "Foundational models",
    features: [
      ["Model Capability Registry", "Record declared and verified model capabilities such as modality, context size, tool use, structured output, cost class, and suitable tasks."],
      ["Model Routing & Selection", "Match and select a model route using task needs, capability, quality, cost, policy, quota, and current health."],
      ["Model Context Preparation", "Assemble, retrieve, compress, format, and budget the prompt and context required for a model call."],
      ["Model Invocation", "Execute model requests through a common interface and handle streaming, timeouts, retries, and call-level errors."],
      ["Model Tool-Use Mediation", "Control which tools a model can see, validate tool arguments, authorize calls, return results, and manage tool-use loops."],
      ["Model Response Normalization", "Convert provider-specific text, structured output, tool calls, usage data, and errors into one standard response format."],
      ["Model Continuity Management", "Preserve task context, continuation state, and tool state across calls, sessions, model switches, and recovery."],
      ["Model Availability & Fallback Management", "Monitor model and provider availability and perform fallback or failover during outages, throttling, quota exhaustion, or authentication failure."],
      ["Model Policy Enforcement", "Apply privacy, security, data-residency, budget, and allowed-use policies before and during model calls."],
      ["Model Usage Auditing", "Record model calls, routes, users, tokens, cost, quota consumption, and policy decisions for audit and accounting."],
      ["Model/Provider Runtime Configuration", "Resolve and provide effective endpoint, deployment, timeout, quota, default, and provider-specific settings to the runtime."],
      ["Model Performance Monitoring", "Monitor model latency, throughput, error rate, task success, output quality, and performance regression trends."],
    ],
  },
  {
    level1: "RSI",
    features: [
      ["Improvement Experience Capture", "Collect cross-run failures, gate rejections, human interventions, poor bindings, runtime errors, and reusable success evidence."],
      ["Improvement Pattern Discovery", "Find recurring failures, regressions, bottlenecks, and generalizable success patterns across accumulated experience."],
      ["Improvement Opportunity Formation", "Turn a validated pattern into a scoped improvement opportunity with goals, expected benefit, risks, and supporting evidence."],
      ["Improvement Candidate Generation", "Generate comparable changes to workflows, prompts, capsules, routing, schemas, gates, adapters, or memory policy."],
      ["Improvement Experimentation", "Test system-change candidates through replay, A/B comparison, canary runs, or sandbox experiments."],
      ["Improvement Evaluation", "Compare candidate effects on quality, cost, latency, reliability, and safety, then produce adoption or rejection evidence."],
      ["Improvement Deployment Control", "Apply approved improvements through staged promotion, monitoring, version control, and rollback."],
      ["Improvement Policy Calibration", "Adjust RSI triggers, risk levels, experiment budgets, approval requirements, and automation boundaries from long-term results."],
    ],
  },
  {
    level1: "Data foundations",
    features: [
      ["Unified Data Access", "Provide one addressing, reading, and query interface across structured data, documents, graphs, vectors, and artifacts."],
      ["Source Connector Management", "Register, configure, monitor, update, and retire connectors for files, websites, research services, repositories, and other sources."],
      ["Source Acquisition & Structural Normalization", "Acquire source content through connectors and convert it into canonical data or document structures while preserving provenance."],
      ["Data Quality Validation & Remediation", "Detect and handle missing, corrupted, duplicated, malformed, inconsistent, or unsuccessfully normalized data."],
      ["Data Semantics & Schema Management", "Manage field and entity semantics, ontologies, schemas, versions, compatibility, and structural validation."],
      ["Data Lineage & Provenance Management", "Record and verify source, transformation, version, and responsibility links from original data to derived assets."],
      ["Hybrid Retrieval", "Combine lexical, vector, graph, metadata, and filtered retrieval into ranked results with source references and scores."],
      ["Research Knowledge Graph Management", "Manage research entities and relationships across papers, concepts, methods, claims, experiments, people, and citations."],
      ["Opportunity Graph Management", "Manage relationships among problems, requirements, gaps, opportunities, ideas, evidence, and decisions."],
      ["Opportunity Metadata Enrichment", "Add source, topic, impact, feasibility, risk, evidence coverage, and lifecycle metadata to opportunities."],
      ["Evidence Ledger Management", "Record evidence identity, producer, provenance, supported claims or criteria, status, and audit history for each run."],
      ["Research Asset Repository", "Store, version, identify, and retrieve research code, data, models, documents, figures, and experiment outputs."],
      ["Failure Knowledge Repository", "Preserve failed attempts, counterexamples, invalid hypotheses, root causes, fixes, and recurrence conditions for later reuse."],
      ["Technical Memory Management", "Write, compress, retrieve, expire, and govern durable technical facts, decisions, constraints, and reusable context across runs."],
      ["Data Governance", "Enforce data access, privacy, retention, licensing, sensitivity, deletion, sharing, and audit policies."],
      ["Evidence & Artifact Contract Storage", "Store and version evidence and artifact schemas, constraints, compatibility rules, and contract metadata."],
    ],
  },
  {
    level1: "Harness Core",
    features: [
      ["Run Initialization", "Create the run or sprint identity, workspace, initial state, log and evidence paths, and load effective runtime configuration."],
      ["Work Readiness & Task Graph Scheduling", "Determine node readiness from dependencies, gates, write scopes, resources, and state, then schedule runnable work."],
      ["Execution Assignment, Queueing & Dispatch", "Assign ready work to selected executors, manage queue order, and submit dispatch requests."],
      ["Execution Environment Provisioning", "Prepare worktrees, sandboxes, processes, remote environments, runtime dependencies, and execution isolation."],
      ["Execution Admission, Approval, Lease & Concurrency Control", "Check approval, policy, and resource conditions, acquire leases atomically, and enforce concurrency, exclusion, quota, and backpressure."],
      ["Execution Recordkeeping", "Append dispatch, start, heartbeat, result, error, retry, approval, and handoff events to the execution audit history."],
      ["Experiment Loop Automation", "Coordinate experiment preparation, execution, collection, evaluation, repetition, and stopping conditions."],
      ["Run Recovery Control", "Recover, retry, compensate, or safely terminate runs after interruption, worker failure, stale leases, or partial results."],
      ["Artifact Routing", "Route artifact and evidence references to downstream nodes, ledgers, repositories, or delivery channels according to contract."],
      ["Run Closure Assurance", "Allow a run to close only after its nodes, gates, artifacts, evidence, and parent-child states satisfy closure rules."],
      ["Runtime Bridge & Route Execution", "Execute a chosen route through actor-host, provider, CLI, API, browser, or remote adapters and normalize results and errors."],
      ["Runtime State and Status Management", "Maintain valid state machines, transitions, and current status projections for runs, tasks, operators, actors, and hosts."],
      ["Actor Host & Physical Host Management", "Manage host types, instances, health, carrier metadata, lifecycle, and compatibility mappings for environments that carry actors."],
      ["Runtime Operator Binding Activation", "Resolve a planned logical-to-physical binding into an available actor-host instance ready for lease and dispatch."],
    ],
  },
  {
    level1: "Intention compilers",
    features: [
      ["Compiler Profile Selection", "Select an intention compiler profile from the input type, domain, task risk, and required output."],
      ["Intent Classification & Command Parsing", "Parse natural-language or command structure and identify the intent category, action, flags, and candidate task type."],
      ["Goal Extraction & Parameter Binding", "Extract goals, objects, success conditions, and parameters, then bind them to normalized contract fields."],
      ["Context Projection", "Select and project the minimum relevant project, memory, attachment, and historical context needed for the intention."],
      ["Ambiguity Detection", "Identify missing, conflicting, or ambiguous goals, terms, scope, constraints, priorities, and success conditions."],
      ["Clarification Generation", "Generate the smallest answerable questions needed to resolve blocking ambiguity and complete the contract."],
      ["Constraint Compilation", "Convert budget, time, permission, scope, quality, data, approval, and prohibition requirements into enforceable constraints."],
      ["Task Contract Compilation", "Compile goals, context, constraints, and acceptance criteria into a stable and traceable task contract."],
      ["Contract Traceability", "Link raw input, requirements, goals, constraints, task contracts, plan nodes, and acceptance evidence."],
      ["Execution Envelope Construction", "Assemble the task contract, context, chosen binding, criticality, timeout, retry, approval, and evidence references into a dispatch envelope."],
      ["Approval Contract Compilation", "Define who can approve which side effect or state transition, under what conditions, using what evidence, and for how long."],
    ],
  },
  {
    level1: "Planner",
    features: [
      ["Task Decomposition", "Split a task contract into bounded work units with explicit inputs, outputs, completion conditions, and responsibilities."],
      ["Planning Strategy Selection", "Choose a sequential, parallel, iterative, exploratory, or other planning strategy from task type, risk, uncertainty, and cost."],
      ["Research and Experiment Planning", "Create the domain-level logical plan for research, retrieval, hypotheses, experiments, benchmarks, and verification."],
      ["Report and Delivery Handoff Planning", "Plan the creation, review, compilation, packaging, and consumer handoff of reports and delivery artifacts."],
      ["Dependency Graph Formation", "Create and validate data, control, gate, artifact, and parent-child dependencies among planned work units."],
      ["Execution Requirement Compilation", "Define capability, environment, tool, data, security, evidence, and side-effect requirements for every plan node."],
      ["Resource Planning", "Estimate and allocate time, compute, model budget, concurrency, storage, equipment, and human attention."],
      ["Assurance Planning", "Plan evaluators, tests, benchmarks, human gates, evidence, and rollback needed to prove task completion."],
      ["Plan Validation", "Check plan coverage, dependency validity, executability, risk, and compliance with the task contract and constraints."],
      ["Physical Plan Selection", "Compare executable topologies and resource strategies, then choose an overall physical plan with cost, risk, and fallback rationale."],
      ["Plan Evolution", "Version and revise unfinished plans when requirements, evidence, constraints, or execution feedback change."],
      ["Runtime Execution Planning", "Translate a domain plan into runtime batches, environments, resources, concurrency, recovery, dispatch, and fallback intentions."],
      ["Physical Operator Binding Planning", "Select a concrete or ordered set of physical actor-host bindings for plan nodes and define their fallback ladder."],
    ],
  },
  {
    level1: "Builder",
    features: [
      ["Build Contract Interpretation", "Translate the task or build contract into implementation goals, interfaces, write scope, acceptance conditions, and prohibited changes."],
      ["Build Preparation", "Prepare source material, dependencies, templates, data, workspace, toolchain, and pre-build readiness checks."],
      ["Code Construction", "Create or modify deterministic source code, scripts, tests, and configuration to implement the required technical function."],
      ["Model Construction", "Build, train, fine-tune, or assemble reproducible algorithmic, statistical, or machine-learning models."],
      ["Experimental Asset Construction", "Build experiment code, data processing, instrumentation, environment descriptions, and run scripts."],
      ["Benchmark Asset Construction", "Build benchmark datasets, harnesses, workloads, baselines, metric implementations, and comparison scripts."],
      ["Verification Asset Construction", "Build unit, integration, and end-to-end tests, validators, fixtures, checklists, and verification scripts."],
      ["Decision Artifact Construction", "Create opportunity cards, decision records, trade-off matrices, and recommendation packets for decision-making."],
      ["Prototype Assembly", "Combine code, models, data, and interfaces into a bounded, runnable, and demonstrable proof of concept."],
      ["Product Integration", "Integrate verified components into target product interfaces, data flows, and production-oriented operational boundaries."],
      ["Defect Repair", "Use failure evidence to identify and repair code, configuration, contract, or integration defects and prevent regression."],
      ["Build Evidence Generation", "Generate diffs, manifests, hashes, compile and test results, provenance, and acceptance evidence for the build."],
      ["Report/Paper/Deliverable Construction", "Create and assemble human-facing reports, papers, slides, posters, rebuttals, and narrative delivery packages."],
      ["Runtime Deliverable Construction", "Build executable or deployable services, packages, containers, workflow bundles, and deployment configuration."],
    ],
  },
];

const foundationSheet = workbook.worksheets.getItem("Foundation Features");
const usedRange = foundationSheet.getUsedRange();
const usedValues = usedRange.values;
const headers = usedValues[0];
const idColumn = headers.indexOf("visible_feature_id");
const level1Column = headers.indexOf("level_1_feature");
const level2Column = headers.indexOf("level_2_feature");
if (idColumn < 0 || level1Column < 0 || level2Column < 0) {
  throw new Error(`Required Foundation headers not found: ${JSON.stringify(headers)}`);
}

const existingRows = usedValues.slice(1).filter((row) => typeof row[idColumn] === "string" && row[idColumn].startsWith("FD-B"));
const annotations = groups.flatMap((group) =>
  group.features.map(([title, description], index) => `${index + 1}. ${title}\n\n${description}`),
);

if (existingRows.length !== 118) throw new Error(`Expected 118 Foundation rows, received ${existingRows.length}`);
if (annotations.length !== 118) throw new Error(`Expected 118 annotations, received ${annotations.length}`);

const expectedTitles = groups.flatMap((group) => group.features.map(([title]) => title));
const existingTitles = existingRows.map((row) => {
  const value = row[level2Column];
  if (typeof value !== "string") return value;
  return value.split("\n")[0].replace(/^\d+\.\s*/, "");
});
const mismatches = expectedTitles
  .map((title, index) => ({ index, expected: title, actual: existingTitles[index] }))
  .filter((item) => item.expected !== item.actual);
if (mismatches.length > 0) throw new Error(`Foundation L2 order mismatch: ${JSON.stringify(mismatches.slice(0, 10))}`);

foundationSheet
  .getRangeByIndexes(1, level2Column, annotations.length, 1)
  .values = annotations.map((value) => [value]);
foundationSheet
  .getRangeByIndexes(1, level2Column, annotations.length, 1)
  .format.wrapText = true;
foundationSheet
  .getRangeByIndexes(1, 0, annotations.length, usedValues[0].length)
  .format.autofitRows();

const checkRange = `Foundation Features!${String.fromCharCode(65 + level2Column)}1:${String.fromCharCode(65 + level2Column)}119`;
const check = await workbook.inspect({
  kind: "table",
  range: checkRange,
  include: "values,formulas",
  tableMaxRows: 125,
  tableMaxCols: 1,
  tableMaxCellChars: 260,
  maxChars: 45000,
});
await fs.writeFile(path.join(outputDir, "foundation_l2_annotation_check.ndjson"), check.ndjson, "utf8");

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 5000,
});

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(finalPath);

const verifyInput = await FileBlob.load(finalPath);
const verifyWorkbook = await SpreadsheetFile.importXlsx(verifyInput);
const verifyFoundation = verifyWorkbook.worksheets.getItem("Foundation Features");
const verifyValues = verifyFoundation.getUsedRange().values;
const verifyHeaders = verifyValues[0];
const verifyIdColumn = verifyHeaders.indexOf("visible_feature_id");
const verifyLevel2Column = verifyHeaders.indexOf("level_2_feature");
if (verifyIdColumn < 0 || verifyLevel2Column < 0) {
  throw new Error(`Required headers missing after export: ${JSON.stringify(verifyHeaders)}`);
}
const verifyRows = verifyValues
  .slice(1)
  .filter((row) => typeof row[verifyIdColumn] === "string" && row[verifyIdColumn].startsWith("FD-B"));
const verifyAnnotations = verifyRows.map((row) => row[verifyLevel2Column]);
if (verifyAnnotations.length !== 118 || verifyAnnotations.some((value) => typeof value !== "string" || !value.includes("\n\n"))) {
  throw new Error("Foundation L2 annotations were not preserved after export.");
}

const previewSpecs = [
  ["Workflow Features", "A1:E141", "workflow_after.png"],
  ["Foundation Features", `A1:${String.fromCharCode(65 + verifyLevel2Column)}119`, "foundation_after.png"],
  ["Misc Features", "A1:F30", "misc_after.png"],
];
for (const [sheetName, range, filename] of previewSpecs) {
  const preview = await verifyWorkbook.render({ sheetName, range, scale: 0.65, format: "png" });
  await fs.writeFile(path.join(outputDir, filename), new Uint8Array(await preview.arrayBuffer()));
}

console.log(JSON.stringify({
  foundationRows: existingRows.length,
  annotatedRows: annotations.length,
  level2ColumnIndex: level2Column,
  level2Header: headers[level2Column],
  formulaErrors: errors.ndjson,
  firstAnnotation: annotations[0],
  lastAnnotation: annotations.at(-1),
  verifiedAnnotationCount: verifyAnnotations.length,
  verifiedLevel2ColumnIndex: verifyLevel2Column,
  exported: finalPath,
}, null, 2));
