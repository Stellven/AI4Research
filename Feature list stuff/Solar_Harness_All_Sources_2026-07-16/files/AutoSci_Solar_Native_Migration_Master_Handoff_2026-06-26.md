# AutoSci → Solar-Native Migration: Master Coding-Agent Handoff

**Generated:** 2026-06-26  
**Primary writable repository:** `Coconut-ch1ken/OpenSolar`  
**Assessed snapshot:** `2026-06-25-1717-snapshot`  
**Native behavioral oracle:** `skyllwt/AutoSci@main`  
**Solar architecture reference:** `Stellven/AI4Research@main`  
**Document purpose:** one self-contained handoff containing the complete current-state assessment, the original implementation plan, and the detailed continuation instructions for a coding AI agent.

---

## Master directive to the coding agent

Read this entire document before changing code. Parts I and II establish **what the system currently is**, **what native AutoSci behavior requires**, and **what the target Solar-native architecture must be**. Part III is the operational instruction set you must follow while implementing the continuation.

Your central objective is not route coverage, fixture success, or compatibility-shell completeness. It is to make AutoSci-derived scientific capabilities execute through Solar's real control plane as recoverable, evidence-gated TaskGraph work while preserving AutoSci's durable research-state semantics.

The architectural invariant is:

```text
TaskGraph node
  → logical operator
  → capability capsule
  → physical operator
  → registered execution host
  → bounded implementation action
  → typed Evidence ABI artifact
  → deterministic/runtime gate
  → durable scheduler and lifecycle state
```

The following do **not** prove parity by themselves:

- a configured route;
- a projected `$skill` wrapper;
- schema-valid fixture output;
- direct invocation of `autosci_bridge.py` outside the scheduler;
- pre-created wiki pages or supplied result JSON classified after the fact;
- a declarative TaskGraph that was never dispatched;
- an empty runtime result map accepted by a structural gate;
- a report that says a stage completed without node, gate, log, and artifact evidence.

Use native AutoSci as the behavioral specification, but keep Solar as the workflow owner. Do not introduce a monolithic `AutoSciRunner`, do not invoke AutoSci's full `/research` workflow as a hidden subprocess, and do not weaken gates to obtain green tests.

### Required reading order

1. **Part I — Detailed Current-State Gap Analysis**
2. **Part II — Original 18-Phase Solar-Native Implementation Plan**
3. **Part III — Executable Coding-Agent Continuation Prompt**

### First implementation milestone

Before attempting broad feature work, prove one safe scientific capability traverses the real chain:

```text
TaskGraph submission
→ graph scheduler
→ logical-to-physical resolution
→ registered host/worker dispatch
→ bounded backend action
→ Evidence ABI artifact
→ runtime gate
→ persisted node/gate state
→ parent closure remains blocked or advances correctly
```

Then use that working vertical slice to complete the full lifecycle rather than extending the compatibility shim horizontally.

---

## Contents

- [Part I — Detailed Current-State Gap Analysis](#part-i--detailed-current-state-gap-analysis)
- [Part II — Original 18-Phase Solar-Native Implementation Plan](#part-ii--original-18-phase-solar-native-implementation-plan)
- [Part III — Executable Coding-Agent Continuation Prompt](#part-iii--executable-coding-agent-continuation-prompt)
- [Source-integrity record](#source-integrity-record)

---

## Part I — Detailed Current-State Gap Analysis

**Assessment date:** 2026-06-25  
**Current-progress ref:** `Coconut-ch1ken/OpenSolar@2026-06-25-1717-snapshot`  
**Native reference:** `skyllwt/AutoSci@main`  
**Solar architecture reference:** `Stellven/AI4Research@main`  
**Implementation oracle:** `autosci_solar_native_implementation_plan(1).md`

---

## 1. Executive verdict

The migration has built a substantial **Solar-native architectural shell** around AutoSci, but it has **not yet reproduced native AutoSci end-to-end behavior**.

The strongest accomplishments are:

- a complete user-facing route inventory for the 28 native AutoSci skills;
- generic `Scientific*` logical operators and `cap.research-*` capability capsules;
- typed scientific Evidence ABI schemas and deterministic artifact gates;
- seven declarative scientific TaskGraph templates;
- a bounded AutoSci backend package under `harness/plugins/autosci/`;
- PDF/TeX/arXiv source preparation, route argument compatibility, wiki writeback, citation-map handoff, model-command bridges, approved command execution, and several publication-side tool ABIs;
- a large set of fixture, schema, route, and targeted runtime regression tests;
- unusually candid late-stage logs that explicitly avoid calling partial work full parity.

The central unfinished work is not “adding more routes.” It is making the existing routes execute through the **actual Solar control plane** and reproduce AutoSci’s durable state transitions and side effects.

The current, honest top-line status recorded by the latest Phase 19 audit command is:

| Status | Count |
|---|---:|
| Full | **0** |
| Partial | **17** |
| Approval/provider gated | **11** |
| Missing route | **0** |

This is a much more accurate statement than “Phase 18 complete.” Phase 18 proved a fixture-oriented action-and-gate surface; it did not prove native behavioral parity.

### The single most important finding

`$research` does **not** currently submit and execute `scientific_research_lifecycle_full_v1.json` through Solar’s graph scheduler. In non-smoke mode, the skill shim collapses the command to one bridge action, `run_research_lifecycle`. That action inspects supplied files and wiki contents, infers which stages appear complete, and writes pipeline projection files. It explicitly does not launch the scientific stage runners.

Therefore, the current `$research` path is best described as:

> **an evidence roll-up and resume-planning projection, not a scheduler-executed Solar-native research lifecycle.**

This is the primary blocker for Phase 15 and Phase 18 acceptance.

### Overall assessment

| Dimension | Assessment |
|---|---|
| Solar-native naming and decomposition | Strong |
| Route/command coverage | Strong |
| Evidence schemas and shape validation | Strong |
| Bounded single-stage implementations | Moderate and improving |
| Scheduler/physical-operator integration | Incomplete |
| Native OmegaWiki semantics | Incomplete |
| Native ideation protocol | Partial |
| Native experiment lifecycle | Partial |
| Native publication lifecycle | Partial |
| Durable suspend/resume orchestration | Not demonstrated |
| Full native AutoSci parity | Not achieved |

---

## 2. Audit scope and evidentiary limitations

This assessment reviewed the workflow-critical code and documentation surfaces across all three repositories, with the deepest inspection applied to native AutoSci and the OpenSolar snapshot. In particular, it reviewed:

- the complete `docs/integrations/autosci/` phase-log sequence that exists in the snapshot;
- the strict migrated-parity audit and the feature-parity matrix;
- the route and operator-binding configurations;
- the generated `$skill` wrappers;
- the bridge and shim execution paths;
- the full and resume TaskGraph templates;
- scientific logical and physical operator registries;
- the graph scheduler and lifecycle/skill/parity gates;
- the simplified OpenSolar wiki tool and native AutoSci OmegaWiki tool;
- native AutoSci skill protocols for setup, initialization, ingestion, discovery, question answering, health checking, editing, prefill/reset, daily arXiv, ideation, novelty, review, experiment design/run/status/evaluation, survey, paper planning/drafting/compilation, full research, rebuttal, poster, and visualization;
- native entity and lifecycle schemas for ideas and experiments.

A network-level local clone was unavailable in the analysis environment, so repository-recorded commands and test results were not independently rerun here. Statements such as “124 tests passed” mean **the repository’s progress log records that result**, not that this assessment reran it. Source-level conclusions—such as the `$research` direct bridge dispatch, missing lifecycle bindings, and lifecycle-gate default behavior—come from direct inspection of the branch contents.

---

## 3. Correct architectural interpretation of the three repositories

### 3.1 Solar: control-plane reference, not the feature source

Solar’s core operating model is:

```text
intent
  -> contract
  -> TaskGraph IR
  -> logical operator
  -> physical operator / host
  -> lease and dispatch
  -> artifact and evidence
  -> deterministic node gate
  -> parent gate
  -> accepted state and replayable memory
```

The important implication for this migration is that **the workflow owner must be Solar’s TaskGraph runtime**. AutoSci code may implement individual bounded scientific actions, but it must not secretly own the end-to-end lifecycle.

Solar already has the necessary primitives:

- `harness/lib/graph_scheduler.py` for DAG readiness and parent-gate handling;
- `harness/lib/operator_runtime.py` for validated envelopes, leases, inbox dispatch, worker start, and result recording;
- logical and physical operator registries;
- actor/host registry;
- capability capsules;
- event/session projections;
- plugin scope and rollback contracts.

The migration should use those primitives rather than building a second scheduler inside `autosci_bridge.py`.

### 3.2 Native AutoSci: a stateful research operating system

Native AutoSci is not just a collection of prompts or independent commands. Its behavior is organized around a durable **OmegaWiki** and a set of linked lifecycle protocols.

Its state model includes:

- typed entities: papers, concepts, topics, people, methods, ideas, experiments, summaries, and foundations;
- typed semantic edges and a separate citation graph;
- lifecycle-enforced idea states: `proposed -> in_progress -> tested -> validated | failed`;
- lifecycle-enforced experiment states: `planned -> running -> completed | abandoned`;
- source-owned, wiki-owned, derived, and user-owned file boundaries;
- checkpoints for resumable batch work;
- purpose-specific context compilation;
- maturity and health checks;
- an append-only research log;
- failed-idea memory to prevent repeated dead ends.

Native `/research` is a state machine, not a report macro. It includes:

1. bootstrap and state inspection;
2. idea generation and novelty filtering;
3. a human idea-acceptance gate;
4. experiment design and independent review;
5. deployment;
6. an asynchronous waiting period that may end the current session;
7. status checking and result collection;
8. evidence evaluation and possible iteration;
9. a human results gate;
10. paper plan, draft, refinement, and compilation;
11. durable updates to idea, experiment, paper, graph, and log state;
12. resume without repeating completed stages.

### 3.3 OpenSolar snapshot: correct boundary, incomplete execution

The snapshot made the right high-level boundary choice:

- AutoSci-specific mechanics live under `harness/plugins/autosci/`;
- generic semantics live in `Scientific*` operators, `cap.research-*` capsules, scientific workflows, schemas, and gates;
- user-facing AutoSci commands are represented by `$skill` wrappers;
- the original AutoSci repository is treated as a behavioral reference rather than invoked as a giant black box.

That boundary should be preserved.

The problem is that the implementation later accumulated too much behavior in a single bridge file and then routed the most important command—`$research`—back through that bridge as one action. This recreates workflow ownership at the backend layer even though the declarative TaskGraph exists.

---

## 4. Evidence maturity model used in this report

A major source of confusion in the current logs is that several different kinds of “working” evidence are mixed together. The following scale separates them:

| Level | Meaning | What it proves |
|---|---|---|
| **E0 — Declared** | Route/config/file exists | Naming and coverage intent only |
| **E1 — Contract-valid** | Schema, capsule, graph, or gate validates | Structural consistency only |
| **E2 — Fixture/smoke** | Deterministic fixture passes | Local adapter and artifact-shape behavior |
| **E3 — Real bounded stage** | One approved real command/provider/tool stage executes and emits audited evidence | A specific native side effect works |
| **E4 — Recoverable multi-stage lifecycle** | Multiple real stages run through Solar, suspend, resume, transition state, and pass parent gate | Native workflow semantics are substantially reproduced |
| **E5 — End-to-end parity** | A representative full research job reaches final accepted artifacts with real source/model/runtime/publication evidence | Full behavioral parity for that workflow |

The snapshot has extensive E0–E2 coverage and several E3 paths. It has not demonstrated E4 or E5 for `$research`.

A route should never be labeled “full” from E0–E2 evidence. A safety-gated route can still become semantically full once an approved E3/E4 test exists; safety gating and implementation completeness should therefore be tracked as separate axes.

---

## 5. What has actually been accomplished

### 5.1 Architecture and contracts

The following are real, reusable accomplishments and should not be discarded:

1. **Workflow inventory and decomposition**
   - AutoSci workflows were decomposed into generic scientific stages.
   - A no-black-box rule was documented.
   - Native command coverage was later expanded to 28 routes.

2. **Evidence ABI family**
   - Generic schemas exist for papers, discovery, memory, graph, claims, methods, code evidence, ideas, experiments, verdicts, reports, publication bundles, and workflow evolution.
   - Failure and inconclusive states are first-class.

3. **Capability capsules**
   - Eighteen `cap.research-*` capsule files were added and registered.
   - The naming correctly avoids making AutoSci the semantic owner.

4. **Logical operators**
   - Eighteen generic `Scientific*` logical operator definitions exist.
   - Bounded execution intent is represented for experiment-running operators.

5. **Physical backend workers**
   - AutoSci-backed workers exist for ingestion, claims, methods, code mapping, memory, graph, ideas, experiment design/run/monitor, verification, and report production.

6. **Manuals and dispatch templates**
   - Scientific personas and templates define expected artifacts, restrictions, and failure behavior.

7. **TaskGraph templates**
   - Ingestion, claim extraction, verification, experiment, publication, full lifecycle, and resume graph files exist.
   - The full graph explicitly forbids a hidden backend full-workflow runner.

8. **Deterministic gates**
   - Artifact gates exist for major scientific outputs.
   - Unsupported or malformed evidence can be rejected.

### 5.2 Capability implementation improvements

Later Phase 19 repairs went beyond the original fixture-only bridge:

- local PDF text extraction;
- arXiv ID recovery and source-fetch attempts;
- synthetic TeX fallback that is explicitly marked rather than silently passed as native source;
- original AutoSci argument compatibility for discovery and other commands;
- source manifests and no implicit fixture fallback for real discovery modes;
- source-grounded idea generation inputs;
- external novelty provider evidence;
- model-command and Review-LLM evidence import paths;
- approved wiki writeback for selected flows;
- citation-map propagation into paper planning/drafting;
- approved local experiment command execution with stdout/stderr and result artifacts;
- experiment-evaluation writeback;
- approved refine apply;
- approved TeX fix apply and allowlisted compile executor support;
- root tool ABIs for remote execution, SMTP, poster rendering, and other native command surfaces;
- truthful limitations when providers or side effects are unavailable.

These changes raise several routes from E1/E2 toward E3. They do not yet compose into E4.

---

## 6. Core differences between native AutoSci and current OpenSolar progress

### 6.1 Orchestration ownership

**Native AutoSci:** `/research` owns a staged state machine with human gates, asynchronous pauses, iteration, and resume.

**Target Solar-native design:** Solar’s graph scheduler owns those stages; each stage is a bounded logical operator with its own capsule, physical binding, evidence, and gate.

**Current snapshot:** `$research` calls `run_research_lifecycle` as one bridge action. The bridge reads evidence files and wiki counts, calculates a stage plan, and writes:

- `pipeline-progress.md`;
- `PIPELINE_REPORT.md`;
- `pipeline-state.json`.

It does not dispatch the declarative graph’s nodes through `graph_scheduler.py` and `operator_runtime.py`.

**Consequence:** the most important workflow is not yet Solar-native in execution, despite being Solar-native in configuration.

### 6.2 Durable state versus inferred completion

**Native AutoSci:** stage completion is grounded in lifecycle transitions, tool outputs, checkpoints, and linked entity state.

**Current snapshot:** lifecycle completion can be inferred from conditions such as:

- any paper page existing;
- any idea page existing;
- any experiment page existing;
- an output plan existing;
- externally supplied runtime/review/compile evidence files.

A current test deliberately pre-creates wiki pages and supplied evidence documents, then verifies that every stage becomes complete. That proves evidence ingestion, not stage execution.

**Consequence:** stale or unrelated workspace files can falsely satisfy a new job unless all evidence is job-scoped, node-scoped, hash-bound, and causally linked.

### 6.3 OmegaWiki versus a simplified local wiki helper

**Native AutoSci wiki tool provides:**

- schema-backed entity validation;
- typed edge validation and endpoint topology;
- citations as a distinct graph;
- lifecycle transition validation;
- batch edges and deduplication;
- rich entity find/query;
- multi-hop neighbors with filters;
- purpose-driven context compilation;
- open-question rebuilding;
- maturity metrics;
- checkpoints and checkpoint metadata;
- worktree-specific graph rebuild protections.

**Current OpenSolar wiki tool provides:**

- simple markdown lookup;
- simple neighbor lookup;
- page counts;
- arbitrary frontmatter key replacement;
- generic relation append;
- log append;
- index/context rebuild.

It does not import the native schema authority, enforce idea/experiment transitions, validate edge types/endpoints, maintain a citation store, or implement checkpoints.

**Consequence:** current wiki writeback reproduces file mutation, but not the native knowledge-system invariants that make AutoSci memory reliable.

### 6.4 Native ideation protocol versus generic idea artifacts

**Native AutoSci:** ideation is a multi-phase protocol involving independent generation, gap grounding, duplicate/failed-idea exclusion, novelty checking across multiple sources, independent review, wiki persistence, and pilot progression.

**Current snapshot:** sourced candidate generation and novelty evidence are present, and external/model evidence can be attached. However, the complete independent dual-generation/merge protocol, failed-idea anti-memory, human idea gate, pilot design/run/eval chain, and lifecycle transitions are not demonstrated together.

### 6.5 Native experiment lifecycle versus one approved command

**Native AutoSci:** experiment design leads to code preparation and inspection, local or remote deployment, long-running state, later status polling, collection, independent evaluation, lifecycle updates, and possible iteration.

**Current snapshot:** a real allowlisted command can now execute behind an approval contract, and its streams/results can be captured. This is valuable E3 evidence. Still missing as one recoverable chain are:

- deployment identity and durable process/session state;
- asynchronous waiting without marking failure;
- idempotent status polling;
- exactly-once result collection;
- remote launch/pull evidence;
- verdict and idea/experiment transitions;
- iterative re-design/re-run when evidence is insufficient;
- process restart and resume.

### 6.6 Native publication lifecycle versus report sidecars

**Native AutoSci:** paper planning is grounded in accepted ideas/experiments; drafting creates a full LaTeX project; figures, tables, and BibTeX are verified; review/refinement loops are supported; compile produces and checks a real PDF.

**Current snapshot:** evidence-linked report and LaTeX sidecars, citation maps, compile diagnostics, approved TeX executor/fix paths, rebuttal mappings, and poster tool ABIs exist. Still missing as a proven chain are:

- manuscript generation from a complete accepted research state;
- real figure/table production and inclusion;
- verified bibliography resolution;
- section-level/cross-model review loop;
- compilation to a valid final PDF;
- PDF/submission checklist validation;
- final publication bundle accepted by a parent gate.

### 6.7 Route coverage versus runtime parity

The 28 wrappers are useful UX compatibility. They are intentionally thin and route to the Harness. Their existence proves that every native command has a Solar entry point; it does not prove that the native command protocol has been implemented.

The current parity and skill-run gates correctly issue warnings for partial/gated routes, but still return a successful gate result when the artifact shape is valid. Those gates are configuration-integrity gates, not full-parity acceptance gates.

---

## 7. Critical integrity defects

### C-1 — `$research` bypasses the TaskGraph scheduler

**Severity:** Critical  
**Plan impact:** Violates the core Phase 15 and Phase 18 objective.

**Observed behavior:** non-smoke `$research` is reduced to `run_research_lifecycle`; the shim invokes bridge actions directly.

**Required correction:** route `$research` to a workflow compiler/submitter that instantiates and submits `scientific_research_lifecycle_full_v1.json` to the existing scheduler. The bridge must expose only bounded stage actions.

**Acceptance:** scheduler records show every executed node, logical binding, physical operator, lease, result, gate, and parent verdict. No bridge function owns the stage sequence.

### C-2 — Lifecycle gate can pass structural declarations without runtime completion

**Severity:** Critical

The lifecycle gate validates graph shape and, when no explicit failure/inconclusive result is present, defaults runtime status to passed. Its tests deliberately assert that the declarative full and resume workflow files pass.

**Risk:** a valid graph contract can be confused with a completed lifecycle.

**Required correction:** split the gate into:

1. `lifecycle_contract_gate` for static graph validation; and
2. `lifecycle_runtime_gate` for completed job acceptance.

The runtime gate must require a result and node-gate verdict for every required executed node, verify artifact existence and schema, verify job/sprint/node provenance, and never default to passed when result maps are empty.

### C-3 — Stale and contradictory parity truth artifacts

**Severity:** Critical for auditability

The committed `harness/artifacts/autosci/phase19/parity_inventory.json` reports seven full routes, while later audited inventory commands report zero full, seventeen partial, and eleven gated. The committed artifact is marked completed and is timestamped earlier.

**Required correction:** generated parity artifacts must be regenerated from the current route config or removed from version control. CI must fail when the committed inventory and route configuration disagree.

### C-4 — Scheduler binding chain is incomplete or stale

**Severity:** Critical for executable graphs

The current logical binding section does not provide normal candidates for every `Scientific*` operator used by the full lifecycle. Several bindings retain `backend_action_pending` despite enabled physical workers. The physical workers still carry placeholder/stale metadata such as `owner_host: solar@example-host` and `model: autosci-adapter-fixture`. The actor/host registry does not expose a clearly registered local AutoSci command host.

**Required correction:** add a registry consistency test and repair the entire chain:

```text
workflow node
  -> logical operator definition
  -> logical binding
  -> physical actor
  -> registered host
  -> executable command
  -> declared capsule
  -> declared plugin capability
```

### C-5 — Completion evidence is not sufficiently job-scoped or causal

**Severity:** Critical

Current lifecycle planning can infer completion from generic wiki page counts or externally supplied artifacts. Evidence must instead prove that a specific node in a specific job produced or accepted the artifact.

**Required correction:** every accepted artifact must carry and be checked against:

- `job_id`/`task_id`;
- `sprint_id`;
- `node_id`;
- operator and implementation package;
- input artifact hashes;
- output artifact hashes;
- approval reference where relevant;
- timestamp and attempt number;
- predecessor evidence IDs.

### C-6 — Native lifecycle invariants are not enforced by the wiki layer

**Severity:** Critical for scientific state correctness

Arbitrary metadata writes can bypass native transition rules. Typed edge and citation constraints are not equivalent to native AutoSci.

**Required correction:** port or adapt the native schema/loader/transition engine into the plugin-owned implementation package, while keeping the human-facing wiki under Solar artifact scope.

---

## 8. High-priority architectural and behavioral gaps

### H-1 — The bridge has become a monolith

`autosci_bridge.py` is roughly 8,000+ lines and contains parsing, provider handling, mutation, publication, runtime evidence, experiment execution, and lifecycle projection behavior.

This increases coupling and makes it easy for backend code to retake workflow ownership.

**Target:** retain one CLI dispatcher, but move bounded actions into modules such as:

```text
plugins/autosci/actions/knowledge.py
plugins/autosci/actions/ideation.py
plugins/autosci/actions/experiments.py
plugins/autosci/actions/publication.py
plugins/autosci/actions/admin.py
plugins/autosci/runtime/approval.py
plugins/autosci/runtime/evidence.py
plugins/autosci/runtime/wiki.py
```

No action module may call the next lifecycle action.

### H-2 — Plugin manifest is stale

The manifest lists only thirteen of the eighteen target scientific capabilities. It omits at least:

- `cap.research-literature-discover`;
- `cap.research-memory-update`;
- `cap.research-graph-update`;
- `cap.research-paper-analyze`;
- `cap.research-idea-evaluate`.

It also still describes fixture/explicit-envelope operation and has `depends_on: []` despite optional PDF, network, model, TeX, remote, SMTP, and rendering surfaces.

### H-3 — Physical operator policies do not match later capabilities

Several physical operators still deny network and identify as fixture adapters, while later bridge actions can use live discovery, model commands, remote execution, SMTP, and renderers. Direct shim calls can therefore bypass the intended physical-operator policy envelope.

**Target:** capability-specific physical operators with explicit policies and no direct ungoverned side-channel.

### H-4 — Full TaskGraph is too linear for native behavior

The declarative full workflow is a linear chain. Native behavior requires conditional branches and pauses:

- optional bootstrap/ingest;
- parallel or independent idea generation/review;
- human Gate 1;
- deployment followed by `WAITING_EXTERNAL`;
- monitoring loop;
- collection;
- verdict branch;
- bounded iteration;
- human Gate 2;
- optional paper path.

The graph model must represent these states explicitly rather than treating all work as immediate sequential nodes.

### H-5 — No dedicated Phase 15 progress log or execution proof

There is no `phase15-progress-log.md` in the snapshot. Declarative lifecycle files and a lifecycle gate exist, but no dedicated phase artifact proves an actual scheduler-driven full lifecycle or resume/recovery test.

### H-6 — Safety gating and implementation status are conflated

A route can be semantically complete but still require approval. Current status values mix these concerns.

Use three independent fields:

```text
semantic_parity: full | partial | missing
execution_policy: pure | bounded_local | approval_required | provider_required
proof_level: E0 | E1 | E2 | E3 | E4 | E5
```

### H-7 — Full-suite test evidence is fragmented

The logs record growing test counts—up to at least 124 plugin tests and 54 scientific evaluator tests at one checkpoint, followed by later targeted fixes. They do not show one final clean run after every final patch, nor a non-fixture scheduler acceptance suite.

---

## 9. Phase-by-phase comparison against the attached implementation plan

| Phase | Plan objective | Current state | Verdict | Remaining work |
|---:|---|---|---|---|
| 0 | Complete native workflow inventory and decomposition | Workflow map, capability map, artifact map, and later 28-skill route matrix exist | **Implemented, refresh needed** | Reconcile current native main, strict audit, current route config, and stale inventory; add native state-machine details as acceptance contracts |
| 1 | Canonical scientific Evidence ABI | Broad schema family and fixtures exist | **Structurally complete** | Add state-transition, approval, checkpoint, citation, provider, and lifecycle-runtime evidence contracts; enforce causal provenance |
| 2 | Clean capsule structure | 18 generic capsules registered | **Mostly complete** | Reconcile capsule effects/bindings with current live tool paths and plugin manifest; add command/provider risk modes |
| 3 | Solar-native logical operators | 18 scientific definitions exist | **Definitions complete; routing incomplete** | Complete bindings for every full-workflow operator; remove stale pending conditions; avoid mapping `$research` to `ScientificWorkflowEvolver` |
| 4 | AutoSci backend implementation package | Rich adapter exists with many actions | **Substantial partial** | Decompose monolith; update manifest; eliminate lifecycle ownership; align policy and side effects |
| 5 | Physical operators and logical bindings | Many workers exist | **Partial / not scheduler-clean** | Register real local host; repair metadata/policies; complete bindings; prove dispatch for every node |
| 6 | Manuals/personas/templates | Scientific manuals and generated skill wrappers exist | **Mostly complete** | Ensure procedural manuals reflect latest native protocols; wrappers must not be counted as implementation; add state-machine and human-gate instructions |
| 7 | Research TaskGraphs | Seven graph files exist and validate | **Declaratively complete** | Wire `$research` to graph submission; add branching, waits, iterations, and human gates; prove execution |
| 8 | Deterministic gates | Major artifact gates exist | **Shape gates complete; runtime gate incomplete** | Split contract/runtime gates; reject empty result maps; require artifact/provenance/hash checks; add full-parity acceptance gate |
| 9 | Discovery, ingestion, memory, graph | PDF/TeX prep, discovery evidence, wiki writeback, graph sidecars exist | **Substantial partial** | Port OmegaWiki invariants, citations, entity validation, context compilation, checkpoints, mature graph semantics, live provider run |
| 10 | Claim, method, code evidence | Generic extraction/mapping artifacts exist | **Partial** | Prove source-anchored extraction on real papers/repos; distinguish unknown; integrate model/static analysis as bounded operators; native AutoSci parity is indirect because native lacks one identical standalone claim command |
| 11 | Idea generation/evaluation | Sourced candidates and novelty/review evidence paths exist | **Partial** | Implement independent dual generation, merge/dedup, failed-idea banlist, full novelty stack, human gate, pilot lifecycle, durable transitions |
| 12 | Experiment design/run/monitor/collect | Design artifacts, fixture flow, approved local command execution, result streams exist | **Partial** | Implement durable deploy/wait/status/collect, remote path, exactly-once collection, restart/resume, code inspection, integrated state transitions |
| 13 | Claim verification/verdict | Four-path verdict model and selected writeback exist | **Partial** | Run after real collection; independent evaluator evidence; transition idea/experiment state; branch to iterate/fail/validate |
| 14 | Report/paper/poster/rebuttal/publication | Report/LaTeX sidecars, citation maps, compile/fix hooks, rebuttal/poster ABIs exist | **Partial** | Full manuscript, figures/tables, verified BibTeX, review/refine loop, real PDF, submission audit, rendered poster/rebuttal bundle |
| 15 | Full lifecycle and resume/recovery | Declarative graphs and bridge projection exist; no phase log; no scheduler execution proof | **Not complete** | Implement graph instantiation/submission, durable run state, waiting, resume, parent gate, and end-to-end execution |
| 16 | Workflow evolution | Failed-run analysis and bounded proposals; approved refine apply exists | **Partial** | Governed proposal acceptance/rejection, replay, promotion, rollback, and measured improvement loop; never silently mutate protected core |
| 17 | Naming/architecture cleanup | Generic names are mostly correct | **Mostly complete with debt** | Correct `$research` semantic mapping; shrink bridge; remove stale fixture metadata; ensure AutoSci names stay backend-only |
| 18 | End-to-end human acceptance | Fixture-mode acceptance and extensive targeted tests exist | **Not met** | Run real bounded lifecycle through scheduler, suspend/resume, final verdict and actual publication artifact; regenerate truthful parity inventory |
| 19 (extra) | 28-skill UX parity and repairs | Route coverage and many targeted repairs implemented | **Useful compatibility overlay, still partial** | Convert route coverage into execution proof and maintain a two-axis semantic/safety status model |

---

## 10. Command-by-command parity matrix

The status below uses the latest audited route classification, not the stale committed parity inventory.

| Native skill | Current status | What is genuinely present | Main remaining gap |
|---|---|---|---|
| `ask` | Partial | Wiki retrieval plus optional model-command evidence | Native-quality synthesis, confidence calibration, and cited answer tested with real wiki/model path |
| `check` | Partial | Structural checks, lint/tool hooks, optional model findings | Full native health/maturity/graph quality protocol and actionable tiering on real state |
| `daily-arxiv` | Gated | Prepare/finalize ABI, source-manifest fan-in, approved wiki writeback | Live scheduled feed, enrichment/ranking, SMTP, optional auto-ingest, audited together |
| `discover` | Partial | Native seed modes, provider evidence, no silent fixture fallback | Live provider run integrated into downstream ingest/graph with reproducible ranking evidence |
| `edit` | Gated | Bounded edit planning and selected approved mutation primitives | Native ownership rules, typed transitions/edges, before/after rollback, rebuild and audit as one transaction |
| `exp-design` | Partial | Experiment plan, metrics/success criteria, optional Review-LLM evidence | Native code/setup plan, implementation inspection, environment/resource decisions, durable experiment entity |
| `exp-eval` | Partial | Four-path verdict, model evidence import, selected writeback | Real collected results, independent live review, state transitions and iteration branch in one run |
| `exp-pilot-eval` | Partial | Pilot-oriented verdict mapping | Native lenient pilot criteria, durable pilot result, idea progression, integration with pilot run |
| `exp-pilot-run` | Gated | Bounded experiment execution surface can be reused | Pilot code generation/inspection, actual local/remote pilot, pilot-specific artifacts and transition |
| `exp-run` | Gated | Real approved local command execution, captured streams and result artifacts | Durable deploy/wait/status/collect/resume, remote path, exactly-once collection, full chain |
| `exp-status` | Partial | Status artifact generation and verified runtime evidence consumption | Persistent process/session registry, live polling, automatic state updates, pipeline-level status |
| `ideate` | Partial | Grounded candidate generation, novelty evidence inputs, wiki outputs | Two independent idea generators, synthesis, dedup/banlist, human gate, pilot loop, lifecycle transitions |
| `ingest` | Partial | PDF/TeX/arXiv preparation, extracted text, metadata, wiki writeback, sidecars | Full native entity extraction, semantic dedup, typed graph/citation/backlinks, checkpointed bulk mode |
| `init` | Partial | Discovery planning, verified source manifests, approved fan-in writeback | Native fan-out/fan-in execution, checkpoints/worktrees, live fetch and bulk ingest, final rebuild/visualize |
| `novelty` | Partial | S2/DeepXiv/provider evidence and Review-LLM attachment paths | Complete live multi-source protocol, calibrated decision and durable idea update in one audited run |
| `paper-compile` | Gated | Diagnostics, approved TeX fix, allowlisted executor, PDF evidence interface | Actual full manuscript compile/fix rerun and PDF/submission validation under one accepted job |
| `paper-draft` | Partial | Evidence-linked report, LaTeX sidecars, citation-map/compile handoff | Full paper directory, figures/tables, verified BibTeX, section review, stylistic cleanup, actual compile |
| `paper-plan` | Partial | Outline/citation/review/compile handoff evidence | Plan derived from accepted idea/experiment graph, concrete figure/table plan, downstream audit |
| `poster` | Gated | Tool/config/runtime ABIs for DAG/build/validate/render | Real PaperX DAG, HTML, figure extraction, overflow probe and PNG render in an approved run |
| `prefill` | Gated | Proposal/approval-oriented foundation write path | Native catalog, semantic dedup against foundations/concepts, typed pages/edges, rebuild and validation |
| `rebuttal` | Partial | Comment/evidence mapping and draft bundle support | Full reviewer-thread ingestion, atomic concerns, independent stress test, formal/rich deliverables, risk writeback |
| `refine` | Gated | Approved bounded artifact replacement with evidence | Iterative review-fix loop plus rerun of lint/tests/review/compile gates and rollback |
| `research` | Partial | Pipeline projection from supplied evidence and declarative graph files | Actual scheduler-run state machine, human gates, async wait, iteration, resume, final publication |
| `reset` | Gated | Dry-run plan and safety stance | Approved backup/delete/scaffold-rebuild/validation transaction; should remain explicitly gated |
| `review` | Partial | Local surrogate and provider/command/supplied Review-LLM evidence paths | Proven independent reviewer session, rubric/score calibration, multi-turn refinement and entity mapping |
| `setup` | Gated | Configuration status and guide surface | Interactive configuration, non-secret validation, provider/tool health checks; secret writes remain user-controlled |
| `survey` | Partial | Report planning/drafting route and evidence output | Native breadth/depth search protocol, verified citation corpus, requested format outputs and quality review |
| `visualize` | Gated | Tool ABI/config path for graph artifacts | Real Obsidian config, Canvas generation/filter/BFS, SPA server lifecycle, output validation and logging |

---

## 11. Specific configuration inconsistencies to repair

### 11.1 Logical bindings

Every logical operator appearing in the full graph must have an executable candidate. Current binding coverage is incomplete, and several bindings are stale.

At minimum, verify and repair bindings for:

- `ScientificLiteratureDiscoverer`;
- `ScientificPaperAnalyzer`;
- `ScientificGraphUpdater`;
- `ScientificMethodExtractor`;
- `ScientificCodeEvidenceMapper`;
- `ScientificWorkflowEvolver`;
- all already-present operators whose condition still says `backend_action_pending`.

### 11.2 Physical operators and hosts

Replace placeholder ownership and fixture descriptions with accurate runtime declarations. Each AutoSci worker needs:

- a valid `host_id` present in `actor-hosts.json`;
- a local-command-compatible host type supported by `operator_runtime.py`;
- an accurate command and action;
- capability-specific network, shell, filesystem, secret, and approval policies;
- accurate health checks;
- current model/provider metadata, or a clear declaration that it is deterministic/local;
- no implicit route that bypasses the operator runtime.

### 11.3 Plugin manifest

Update the manifest to cover all eighteen target capabilities and declare actual dependencies/tool surfaces. Add validation that every capsule binding to the plugin is present in the manifest and every manifest capability has an implementation route.

### 11.4 Route semantics

`research` should not be represented as ordinary use of `ScientificWorkflowEvolver`. Use a route kind such as:

```yaml
route_kind: taskgraph
workflow_template: scientific_research_lifecycle_full_v1
workflow_compiler: scientific_research_workflow_compiler
```

A compiler may instantiate a graph; it must not execute scientific stages itself.

---

## 12. Target scheduler-native lifecycle

The target execution path should be:

```text
$research arguments
  -> AutoSci-compatible argument parser
  -> ResearchWorkflowRequest.v1
  -> workflow compiler
  -> instantiated TaskGraph with job-specific scopes and conditional nodes
  -> graph_scheduler state database
  -> ready-node selection
  -> logical operator binding
  -> physical operator/host lease
  -> one bounded backend action
  -> typed node evidence + hashes
  -> deterministic node gate
  -> scheduler state transition
  -> human/external wait when required
  -> resume from persisted scheduler state
  -> parent lifecycle runtime gate
  -> publication and memory acceptance
  -> optional workflow-evolution proposal
```

### Required lifecycle states

At the job level:

```text
created
planned
running
waiting_for_human
waiting_for_external
resumable
completed
failed
inconclusive
cancelled
```

At the node-attempt level:

```text
pending
ready
leased
running
waiting_for_human
waiting_for_external
passed
failed
inconclusive
skipped_by_condition
superseded
```

### Required human gates

1. **Gate 1: idea acceptance**
   - occurs after ideation, novelty, and independent review;
   - records accepted/rejected idea IDs and approval evidence;
   - rejected ideas are retained as failed/rejected memory where appropriate.

2. **Gate 2: result/publication acceptance**
   - occurs after experiment evaluation;
   - may approve publication, request iteration, or terminate;
   - records the decision and bounds any additional experiment iterations.

### Required asynchronous behavior

Deployment must be able to return `waiting_for_external` without being treated as failure. A later `$exp-status` or `$research --resume <job>` invocation must continue from scheduler state and must not rerun completed nodes.

---

## 13. Recommended continuation roadmap

### PR 0 — Truth baseline and registry integrity

**Purpose:** prevent false progress before adding behavior.

Deliver:

- regenerate or remove stale parity artifacts;
- split semantic parity, execution policy, and proof level;
- CI consistency test for route config versus inventory;
- registry-chain validation for every workflow node;
- complete physical host and logical binding repair;
- plugin manifest reconciliation;
- lifecycle contract/runtime gate split;
- negative tests proving empty result maps cannot pass.

### PR 1 — Scheduler-native `$research`

Deliver:

- job request schema and workflow compiler;
- graph instantiation with job-specific artifact root;
- scheduler submission and node dispatch;
- explicit Gate 1 and Gate 2 nodes;
- conditional paper path and iteration bounds;
- durable scheduler state and event log;
- status/resume CLI;
- removal of lifecycle stage ownership from the bridge.

Acceptance: a small fixture-free bounded job must dispatch at least ingestion, ideation, design, and a deliberately paused experiment node through the operator runtime, then resume in a new process without re-running passed nodes.

### PR 2 — OmegaWiki parity substrate

Deliver:

- schema-backed entity loader;
- validated lifecycle transitions;
- typed edges and citations;
- deduplication;
- find/query/neighbors;
- context compilation;
- open-question rebuild;
- checkpoints;
- maturity/stats;
- migration of existing workspace pages;
- golden tests against representative native AutoSci behavior.

### PR 3 — Native ideation and human Gate 1

Deliver:

- independent generator A and generator B evidence;
- merge/dedup/ranking;
- failed-idea anti-memory;
- wiki-grounded and external novelty evidence;
- independent review;
- human acceptance record;
- idea lifecycle transition;
- optional pilot branch.

### PR 4 — Durable experiment lifecycle

Deliver:

- code/setup preparation and inspection evidence;
- approved local executor;
- remote executor adapter where configured;
- durable deployment record;
- wait/status/collect states;
- exactly-once collection;
- independent evaluation;
- experiment and idea lifecycle transitions;
- bounded iteration;
- restart/resume test.

### PR 5 — Publication lifecycle and Gate 2

Deliver:

- evidence-grounded paper plan;
- complete LaTeX project;
- figures/tables and artifact lineage;
- verified bibliography;
- independent review/refine loop;
- actual PDF compile and checks;
- publication bundle;
- optional rebuttal/poster paths;
- final parent gate.

### PR 6 — Remaining utility/admin skills

Close semantic parity for setup, init, daily-arxiv, edit, prefill, reset, survey, visualize, and related side-effect surfaces while preserving explicit approval/provider policies.

### PR 7 — End-to-end acceptance and cleanup

Deliver:

- one real bounded local full lifecycle;
- one suspend/resume lifecycle;
- one negative/failure lifecycle;
- one actual PDF publication bundle;
- final current parity inventory;
- repository cleanup of generated PID/run/local artifacts;
- updated phase logs with exact commands, exit codes, hashes, and limitations.

---

## 14. Acceptance tests that must exist before declaring parity

### 14.1 Registry-chain test

For every node in every scientific workflow:

```text
[ ] logical operator exists
[ ] capsule exists and is registered
[ ] logical binding exists
[ ] candidate physical operator exists
[ ] physical operator host exists and is online/eligible
[ ] command/action exists
[ ] plugin manifest declares the capability
[ ] evidence schema exists
[ ] deterministic gate exists
```

### 14.2 Runtime lifecycle gate negatives

The runtime lifecycle gate must reject:

- no `node_results`;
- missing node result;
- result from another `job_id`;
- artifact path that does not exist;
- artifact with wrong schema;
- artifact hash mismatch;
- gate result missing;
- inconclusive predecessor claimed as passed;
- reused wiki page from an unrelated job;
- supplied PDF not produced or accepted by the compile node;
- direct bridge-level full-workflow execution.

### 14.3 Suspend/resume test

1. Start a job.
2. Reach experiment deployment.
3. Persist `waiting_for_external`.
4. Terminate the process.
5. Start a new process.
6. Resume by job ID.
7. Prove passed nodes were not rerun.
8. Collect result once.
9. Complete verdict and publication.

### 14.4 Native state-transition test

Verify legal and illegal transitions for:

- idea `proposed -> in_progress -> tested -> validated|failed`;
- experiment `planned -> running -> completed|abandoned`.

Every transition must produce before/after hashes and evidence IDs. Direct arbitrary metadata mutation must not bypass transition policy.

### 14.5 Full publication test

Require:

- real `.tex` sources;
- real figures/tables or explicit justified absence;
- resolved bibliography;
- successful allowlisted compiler exit;
- generated PDF with nonzero pages and size;
- no unresolved references/citations in logs;
- publication bundle linking all evidence;
- parent gate pass.

### 14.6 Parity-inventory consistency test

Regenerate inventory in CI and compare it byte-for-byte or semantically with the committed artifact. Any difference must fail CI.

---

## 15. What should not be redone

Do not throw away the following:

- generic scientific naming;
- the plugin-as-backend boundary;
- Evidence ABI schemas;
- deterministic artifact gates;
- truthful inconclusive handling;
- explicit approval contracts;
- route argument compatibility;
- source preparation and provenance work;
- approved command execution evidence;
- citation-map and publication handoff work;
- the declarative workflow files as starting material.

The continuation task is primarily to **connect, harden, and complete** these components.

---

## 16. Final completion definition

The migration should be called complete only when all of the following are true:

```text
[ ] The 28 native AutoSci commands have a documented semantic parity status.
[ ] Safety/provider gating is tracked separately from semantic completeness.
[ ] $research submits a Solar TaskGraph; it does not call a bridge-owned lifecycle.
[ ] Every full-lifecycle node resolves through logical binding -> physical operator -> registered host.
[ ] Every executed node emits job-scoped, hash-bound Evidence ABI.
[ ] Runtime gates—not config gates—decide node and parent completion.
[ ] Empty/missing result maps cannot pass a lifecycle gate.
[ ] Human Gate 1 and Gate 2 are durable scheduler states.
[ ] Experiment deployment can wait and resume across processes.
[ ] Result collection is idempotent and exactly-once from the scheduler’s perspective.
[ ] Idea and experiment lifecycle transitions are validated.
[ ] OmegaWiki typed graph, citations, checkpoints, and context semantics are reproduced or intentionally superseded with equivalent contracts.
[ ] A real bounded local experiment is run and evaluated.
[ ] A real paper PDF is compiled and validated.
[ ] A full lifecycle is run from clean state without fixture fallback.
[ ] A second run resumes after an intentional interruption without repeating passed nodes.
[ ] The parity inventory is regenerated and contains no unsupported full claims.
[ ] Intermediate artifacts are human-inspectable without reading native AutoSci internals.
[ ] AutoSci-specific code remains a backend implementation package rather than the workflow owner.
```

---

## 17. Source ledger

The most load-bearing sources for this assessment are listed below in repository-path form so the report remains usable outside this chat.

### Attached plan

- `autosci_solar_native_implementation_plan(1).md`

### Solar architecture reference

- `Stellven/AI4Research@main:README.md`
- `Stellven/AI4Research@main:docs/solar-architecture-code-map.md`

### Native AutoSci

- `skyllwt/AutoSci@main:README.md`
- `skyllwt/AutoSci@main:CLAUDE.md`
- `skyllwt/AutoSci@main:runtime/CLAUDE.md`
- `skyllwt/AutoSci@main:runtime/schema/entities.yaml`
- `skyllwt/AutoSci@main:tools/research_wiki.py`
- `skyllwt/AutoSci@main:.claude/skills/*/SKILL.md`, especially `init`, `ingest`, `ideate`, `novelty`, `review`, `exp-design`, `exp-run`, `exp-status`, `exp-eval`, `paper-plan`, `paper-draft`, `paper-compile`, `research`, `rebuttal`, `poster`, and `visualize`

### OpenSolar snapshot

- `docs/integrations/autosci/autosci-workflow-map.md`
- `docs/integrations/autosci/autosci-solar-feature-parity-matrix.md`
- `docs/integrations/autosci/audit/migrated-autosci-parity-audit-2026-06-25.md`
- `docs/integrations/autosci/phase0-progress-log.md` through `phase14-progress-log.md`
- `docs/integrations/autosci/phase16-progress-log.md` through `phase19-progress-log.md`
- note: `docs/integrations/autosci/phase15-progress-log.md` is absent
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `harness/plugins/autosci/config/feature_operator_bindings.v1.json`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/manifest.yaml`
- `harness/plugins/autosci/README.md`
- `.agents/skills/research/SKILL.md`
- `harness/workflows/scientific_research_lifecycle_full_v1.json`
- `harness/workflows/scientific_research_resume_v1.json`
- `harness/lib/graph_scheduler.py`
- `harness/config/logical-operators.json`
- `harness/config/physical-operators.json`
- `harness/config/actor-hosts.json`
- `harness/evaluators/scientific/lifecycle_gate.py`
- `harness/evaluators/scientific/autosci_skill_run_gate.py`
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/tests/evaluators/scientific/test_lifecycle_gate.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `tools/research_wiki.py`
- `harness/artifacts/autosci/phase19/parity_inventory.json`


---


## Part II — Original 18-Phase Solar-Native Implementation Plan

**Audience:** coding agent working in `Stellven/OpenSolar` with optional access to a local checkout of `skyllwt/AutoSci`.

**Goal:** integrate *all* AutoSci capabilities into Solar as native scientific research capabilities while keeping a clean capsule structure. AutoSci-specific code should remain in an implementation/backend package that is governed by Solar-native capability capsules, operators, TaskGraphs, evidence schemas, and gates.

---

## 0. Non-negotiable architecture model

Use this model for every capability:

```text
TaskGraph node
  -> Logical operator
  -> Capability capsule
  -> Physical operator
  -> Implementation package
  -> Command
  -> Evidence ABI
  -> Gate / human-verifiable test
```

### Meaning of each layer

| Layer | Role | Where it should live |
|---|---|---|
| TaskGraph node | Schedules a specific unit of scientific work | `harness/workflows/` or existing TaskGraph template location |
| Logical operator | Describes semantic work, for example `ScientificClaimExtractor` | `harness/config/logical-operators.json` |
| Capability capsule | Declares capability contract, inputs, outputs, effects, bindings, verification | `harness/capability-capsules/*.yaml` and `harness/config/capability-capsules.registry.yaml` |
| Physical operator | Concrete execution surface, for example AutoSci-backed local worker, Claude/Codex worker, deterministic runner | `harness/config/physical-operators.json` |
| Implementation package | AutoSci-specific bridge code, parsers, shims, fixtures | `harness/plugins/autosci/` |
| Command | Concrete command run by a physical operator | Usually invokes `harness/plugins/autosci/bin/autosci_bridge.py` or a non-AutoSci backend |
| Evidence ABI | Typed output contract for every node | `harness/schemas/evidence/*.schema.json` |
| Gate | Deterministic or bounded evaluator that accepts/rejects/inconclusive | `harness/evaluators/scientific/` or existing evaluator location |

### Critical design rules

1. **Do not create a black-box `AutoSciRunner` that owns the workflow.**
2. **Do not move AutoSci-specific implementation details into Solar control-plane core.**
3. **Do move AutoSci workflow semantics into Solar-native operators, capsules, TaskGraphs, manuals, Evidence ABI schemas, and gates.**
4. **Capsules should mostly use generic research capability names**, such as `cap.research-claim-extract`, not `cap.autosci-claim-extract`.
5. **The AutoSci plugin/package is a backend implementation package**, not the owner of the scientific workflow.
6. **Every phase must leave a human-testable artifact or command.**
7. **If a node cannot be verified with evidence, it is not complete.**

---

## 1. Required repository orientation commands

The coding agent should run these before modifying files. Replace paths as needed.

```bash
# Set local repository paths. Adjust if the checkouts already exist elsewhere.
export SOLAR_REPO="/path/to/OpenSolar"
export AUTOSCI_REPO="/path/to/AutoSci"

# Optional: clone if missing.
# git clone https://github.com/Stellven/OpenSolar.git "$SOLAR_REPO"
# git clone https://github.com/skyllwt/AutoSci.git "$AUTOSCI_REPO"

cd "$SOLAR_REPO"
pwd
git status --short

# Read Solar's top-level architecture/context.
sed -n '1,240p' README.md
sed -n '1,260p' docs/solar-architecture-code-map.md

# Inspect Solar Harness extension/control surfaces.
cd "$SOLAR_REPO/harness"
sed -n '1,240p' schemas/plugin.schema.json
sed -n '1,300p' lib/plugin_loader.py
sed -n '1,360p' config/logical-operators.json
sed -n '1,360p' config/physical-operators.json
sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json

# Inspect existing harness layout before adding directories.
find . -maxdepth 3 -type d | sort | sed -n '1,240p'
find . -maxdepth 3 -type f | sort | sed -n '1,240p'

# Inspect AutoSci source/workflows.
cd "$AUTOSCI_REPO"
pwd
git status --short
sed -n '1,260p' README.md
find . -maxdepth 4 -type f | sort | grep -E '(README|\.md$|\.py$|\.ya?ml$|\.json$)' | sed -n '1,360p'
```

---

## 2. Target native capability coverage

After all phases, Solar should natively cover these AutoSci-derived capability groups:

| AutoSci-derived capability group | Solar-native capability | Main logical operator |
|---|---|---|
| Paper ingestion | `cap.research-paper-ingest` | `ScientificPaperIngestor` |
| Literature discovery | `cap.research-literature-discover` | `ScientificLiteratureDiscoverer` |
| Research memory/wiki update | `cap.research-memory-update` | `ScientificMemoryUpdater` |
| Citation/relationship graph update | `cap.research-graph-update` | `ScientificGraphUpdater` |
| Paper analysis | `cap.research-paper-analyze` | `ScientificPaperAnalyzer` |
| Claim/hypothesis extraction | `cap.research-claim-extract` | `ScientificClaimExtractor` |
| Method extraction | `cap.research-method-extract` | `ScientificMethodExtractor` |
| Code evidence mapping | `cap.research-code-evidence-map` | `ScientificCodeEvidenceMapper` |
| Idea generation | `cap.research-idea-generate` | `ScientificIdeaGenerator` |
| Novelty/feasibility evaluation | `cap.research-idea-evaluate` | `ScientificIdeaEvaluator` |
| Experiment design | `cap.research-experiment-design` | `ScientificExperimentDesigner` |
| Experiment run/deploy/collect | `cap.research-experiment-run` | `ScientificExperimentRunner` |
| Experiment monitoring/resume | `cap.research-experiment-monitor` | `ScientificExperimentMonitor` |
| Claim verification/verdict | `cap.research-claim-verify` | `ScientificClaimVerifier` |
| Report planning | `cap.research-report-plan` | `ScientificReportPlanner` |
| Report drafting | `cap.research-report-draft` | `ScientificReportDrafter` |
| Publication/poster/rebuttal production | `cap.research-publication-produce` | `ScientificPublicationProducer` |
| Workflow evolution / self-improvement | `cap.research-workflow-evolve` | `ScientificWorkflowEvolver` |

---

# Phase 0 — Workflow inventory and decomposition

## Goal

Understand AutoSci deeply enough to decompose it into native Solar stages. This phase is documentation-first and should not implement runtime behavior yet.

## Directory/context commands

```bash
cd "$AUTOSCI_REPO"
sed -n '1,260p' README.md
find . -maxdepth 4 -type f | sort | grep -E '(README|\.md$|\.py$|\.ya?ml$|\.json$)' | sed -n '1,500p'

cd "$SOLAR_REPO"
mkdir -p docs/integrations/autosci
```

## Deliverables

Create:

```text
docs/integrations/autosci/autosci-workflow-map.md
docs/integrations/autosci/autosci-to-solar-capability-map.yaml
docs/integrations/autosci/autosci-artifact-map.yaml
```

## Required content

Each AutoSci workflow step must be mapped as:

```yaml
autosci_step: <command/skill/module>
purpose: <what this step does>
inputs: []
outputs: []
internal_mechanism: <brief but concrete>
state_or_memory_touched: []
failure_modes: []
solar_logical_operator: <Scientific...>
solar_capsule: <cap.research-...>
solar_evidence_abi: <schema.v1>
human_test: <how to manually verify>
```

## Human test

A reviewer checks:

```text
[ ] Every known AutoSci workflow is represented.
[ ] Every workflow maps to a native Solar logical operator.
[ ] Every workflow maps to a native Solar capability capsule.
[ ] Every workflow maps to a typed output artifact.
[ ] There is no proposed giant AutoSciRunner workflow owner.
[ ] AutoSci-specific mechanics are separated from Solar-native semantics.
```

## Done when

The human reviewer can explain AutoSci's workflow as a Solar-native TaskGraph without saying “just call AutoSci.”

---

# Phase 1 — Canonical Scientific Evidence ABI schemas

## Goal

Create stable artifact contracts before implementing the runtime. Operators, capsules, TaskGraphs, and gates will depend on these schemas.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
mkdir -p schemas/evidence schemas/evidence/fixtures
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json
find schemas -maxdepth 3 -type f | sort | sed -n '1,240p'
```

## Deliverables

Create:

```text
harness/schemas/evidence/research_paper.v1.schema.json
harness/schemas/evidence/literature_discovery.v1.schema.json
harness/schemas/evidence/research_memory_update.v1.schema.json
harness/schemas/evidence/research_graph_update.v1.schema.json
harness/schemas/evidence/research_claims.v1.schema.json
harness/schemas/evidence/research_method.v1.schema.json
harness/schemas/evidence/code_evidence_map.v1.schema.json
harness/schemas/evidence/idea_candidate.v1.schema.json
harness/schemas/evidence/idea_evaluation.v1.schema.json
harness/schemas/evidence/experiment_plan.v1.schema.json
harness/schemas/evidence/experiment_status.v1.schema.json
harness/schemas/evidence/experiment_result.v1.schema.json
harness/schemas/evidence/claim_verdict.v1.schema.json
harness/schemas/evidence/scientific_report.v1.schema.json
harness/schemas/evidence/publication_bundle.v1.schema.json
harness/schemas/evidence/workflow_evolution.v1.schema.json
```

Create fixtures for at least:

```text
harness/schemas/evidence/fixtures/sample_research_paper.v1.json
harness/schemas/evidence/fixtures/sample_research_claims.v1.json
harness/schemas/evidence/fixtures/sample_experiment_plan.v1.json
harness/schemas/evidence/fixtures/sample_experiment_result.v1.json
harness/schemas/evidence/fixtures/sample_claim_verdict.v1.json
harness/schemas/evidence/fixtures/sample_scientific_report.v1.json
```

## Common schema requirements

Each schema should include:

```text
schema
task_id
sprint_id
node_id
status: completed | failed | inconclusive
inputs
outputs
artifacts[]
provenance.operator_id
provenance.implementation_package
provenance.timestamp
limitations[]
```

Each artifact entry should include:

```text
type
path
sha256 optional at first, required once artifact hashing exists
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool schemas/evidence/fixtures/sample_research_claims.v1.json >/tmp/sample_research_claims.pretty.json
python3 -m json.tool schemas/evidence/fixtures/sample_claim_verdict.v1.json >/tmp/sample_claim_verdict.pretty.json

# If jsonschema CLI is installed:
python3 -m jsonschema schemas/evidence/research_claims.v1.schema.json -i schemas/evidence/fixtures/sample_research_claims.v1.json
python3 -m jsonschema schemas/evidence/claim_verdict.v1.schema.json -i schemas/evidence/fixtures/sample_claim_verdict.v1.json
```

Manual checklist:

```text
[ ] Schemas are generic scientific schemas, not AutoSci-only schemas.
[ ] Each schema records task/sprint/node provenance.
[ ] Each schema can represent failure/inconclusive status.
[ ] Core fixtures validate or at least parse cleanly.
```

## Done when

At minimum, these four schemas and fixtures exist and validate/parse:

```text
research_paper.v1
research_claims.v1
experiment_plan.v1
claim_verdict.v1
```

---

# Phase 2 — Clean scientific capability capsule structure

## Goal

Create declarative capsules for each scientific capability. Capsules govern the implementation packages; they are not implementation packages themselves.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json
mkdir -p capability-capsules
ls -la capability-capsules || true
```

## Deliverables

Create capsule files:

```text
harness/capability-capsules/cap.research-paper-ingest.yaml
harness/capability-capsules/cap.research-literature-discover.yaml
harness/capability-capsules/cap.research-memory-update.yaml
harness/capability-capsules/cap.research-graph-update.yaml
harness/capability-capsules/cap.research-paper-analyze.yaml
harness/capability-capsules/cap.research-claim-extract.yaml
harness/capability-capsules/cap.research-method-extract.yaml
harness/capability-capsules/cap.research-code-evidence-map.yaml
harness/capability-capsules/cap.research-idea-generate.yaml
harness/capability-capsules/cap.research-idea-evaluate.yaml
harness/capability-capsules/cap.research-experiment-design.yaml
harness/capability-capsules/cap.research-experiment-run.yaml
harness/capability-capsules/cap.research-experiment-monitor.yaml
harness/capability-capsules/cap.research-claim-verify.yaml
harness/capability-capsules/cap.research-report-plan.yaml
harness/capability-capsules/cap.research-report-draft.yaml
harness/capability-capsules/cap.research-publication-produce.yaml
harness/capability-capsules/cap.research-workflow-evolve.yaml
```

Update:

```text
harness/config/capability-capsules.registry.yaml
```

## Required capsule sections

Every capsule should contain at least:

```text
capability_capsule_id
capsule_kind
metadata
applicability
contract
composition
effects
bindings
verification
operator_compatibility
provenance
```

## Binding rule

A capsule may reference AutoSci implementation resources, but should not be named as AutoSci unless the capability is truly AutoSci-specific.

Good:

```yaml
capability_capsule_id: cap.research-claim-extract
bindings:
  skills:
    optional:
      - autosci.claim_extract
  data_refs:
    - schemas/evidence/research_claims.v1.schema.json
effects:
  execute:
    - plugins/autosci/bin/autosci_bridge.py
```

Avoid:

```yaml
capability_capsule_id: cap.autosci-run-everything
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 - <<'PY'
from pathlib import Path
import yaml
reg = yaml.safe_load(Path('config/capability-capsules.registry.yaml').read_text())
ids = []
for group, items in reg.get('capsules', {}).items():
    for item in items:
        ids.append(item['capability_capsule_id'])
required = [
    'cap.research-paper-ingest',
    'cap.research-claim-extract',
    'cap.research-experiment-design',
    'cap.research-claim-verify',
    'cap.research-report-draft',
]
missing = [x for x in required if x not in ids]
print('\n'.join(ids))
assert not missing, f'Missing capsules: {missing}'
PY
```

Manual checklist:

```text
[ ] Capsules are declarative and contract-focused.
[ ] Inputs/outputs reference Evidence ABI schemas.
[ ] Effects declare read/write/execute/network boundaries.
[ ] Verification has concrete pass conditions.
[ ] AutoSci is a backend binding, not the capability meaning.
```

## Done when

All 18 capsule files exist, are registered, and a human agrees the naming is clean and Solar-native.

---

# Phase 3 — Solar-native logical operators

## Goal

Make AutoSci-derived scientific work visible as native Solar logical operators.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,420p' config/logical-operators.json
python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.before.json
```

## Deliverables

Add these logical operators to `harness/config/logical-operators.json`:

```text
ScientificPaperIngestor
ScientificLiteratureDiscoverer
ScientificMemoryUpdater
ScientificGraphUpdater
ScientificPaperAnalyzer
ScientificClaimExtractor
ScientificMethodExtractor
ScientificCodeEvidenceMapper
ScientificIdeaGenerator
ScientificIdeaEvaluator
ScientificExperimentDesigner
ScientificExperimentRunner
ScientificExperimentMonitor
ScientificClaimVerifier
ScientificReportPlanner
ScientificReportDrafter
ScientificPublicationProducer
ScientificWorkflowEvolver
```

## Operator style

Each operator must include:

```text
operator_type
description
primary_role
required_capabilities
cost_hint
concurrency
```

For experiment-running operators, use conservative concurrency:

```json
"concurrency": { "max_parallel": 1, "singleton": false }
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.after.json
python3 - <<'PY'
import json
ops = json.load(open('config/logical-operators.json'))['logical_operators']
required = [
  'ScientificPaperIngestor',
  'ScientificClaimExtractor',
  'ScientificExperimentDesigner',
  'ScientificExperimentRunner',
  'ScientificClaimVerifier',
  'ScientificReportDrafter',
]
missing = [x for x in required if x not in ops]
assert not missing, f'Missing logical operators: {missing}'
for name in required:
    print(name, '->', ops[name].get('primary_role'), ops[name].get('required_capabilities'))
PY
```

Manual checklist:

```text
[ ] There is no giant AutoSciRunner logical operator.
[ ] Operator names describe scientific work, not backend implementation.
[ ] Required capability tokens match the capsule family.
[ ] Existing operators such as ResearchSynthesizer, BenchmarkRunner, Verifier, and ArtifactCurator are reused where appropriate.
```

## Done when

A human can identify which logical operators Solar will schedule for paper ingestion, claim extraction, experiment design, experiment run, verdict, and report generation.

---

# Phase 4 — AutoSci backend implementation package

## Goal

Create `harness/plugins/autosci/` as an implementation/backend adapter package. It should not own the workflow.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' schemas/plugin.schema.json
sed -n '1,340p' lib/plugin_loader.py
mkdir -p plugins/autosci/{bin,adapters,schemas/raw,tests/fixtures,eval_packs}
cd plugins/autosci
pwd
```

## Deliverables

Create:

```text
harness/plugins/autosci/manifest.yaml
harness/plugins/autosci/README.md
harness/plugins/autosci/bin/autosci_bridge.py
harness/plugins/autosci/adapters/solar_envelope_to_autosci.py
harness/plugins/autosci/adapters/autosci_to_research_paper.py
harness/plugins/autosci/adapters/autosci_to_research_claims.py
harness/plugins/autosci/adapters/autosci_to_research_method.py
harness/plugins/autosci/adapters/autosci_to_code_evidence_map.py
harness/plugins/autosci/adapters/autosci_to_idea_candidate.py
harness/plugins/autosci/adapters/autosci_to_experiment_plan.py
harness/plugins/autosci/adapters/autosci_to_experiment_result.py
harness/plugins/autosci/adapters/autosci_to_claim_verdict.py
harness/plugins/autosci/adapters/autosci_to_scientific_report.py
harness/plugins/autosci/schemas/raw/autosci_raw_paper.schema.json
harness/plugins/autosci/schemas/raw/autosci_raw_claims.schema.json
harness/plugins/autosci/schemas/raw/autosci_raw_experiment.schema.json
harness/plugins/autosci/tests/fixtures/sample_paper.md
harness/plugins/autosci/tests/fixtures/sample_autosci_raw_claims.json
harness/plugins/autosci/tests/fixtures/sample_autosci_raw_experiment_result.json
harness/plugins/autosci/tests/test_bridge_smoke.py
harness/plugins/autosci/tests/test_conversion_to_solar_evidence.py
harness/plugins/autosci/eval_packs/autosci_adapter_smoke.yaml
```

## Bridge actions

`autosci_bridge.py` should expose at least:

```bash
python3 plugins/autosci/bin/autosci_bridge.py --help
python3 plugins/autosci/bin/autosci_bridge.py smoke
python3 plugins/autosci/bin/autosci_bridge.py validate --result <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action ingest_paper --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action extract_claims --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action design_experiment --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action verify_claim --envelope <path>
python3 plugins/autosci/bin/autosci_bridge.py run --action write_report --envelope <path>
```

At first, actions may operate on fixtures, but must produce Solar Evidence ABI output.

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 lib/plugin_loader.py validate --id autosci
python3 lib/plugin_loader.py check-scope --plugin autosci --path artifacts/autosci/demo/result.json
python3 lib/plugin_loader.py check-scope --plugin autosci --path ../../README.md || true
python3 plugins/autosci/bin/autosci_bridge.py --help
python3 plugins/autosci/bin/autosci_bridge.py smoke
```

Expected:

```text
[ ] Manifest validates.
[ ] Allowed artifact path passes scope check.
[ ] Illegal path fails scope check.
[ ] Bridge help lists actions.
[ ] Smoke writes result.json and evidence.jsonl under an allowed path.
```

## Done when

AutoSci can be used as a backend adapter package without owning the global research workflow.

---

# Phase 5 — Physical operators and logical bindings

## Goal

Make AutoSci-backed execution surfaces schedulable through Solar's operator runtime.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,420p' config/physical-operators.json
sed -n '1,420p' config/logical-operators.json
sed -n '1,360p' lib/operator_runtime.py
sed -n '1,360p' tools/operatord.py
```

## Deliverables

Add physical operators to `harness/config/physical-operators.json`:

```text
autosci-paper-ingest-worker
autosci-claim-extract-worker
autosci-memory-update-worker
autosci-idea-worker
autosci-experiment-design-worker
autosci-experiment-run-worker
autosci-claim-verify-worker
autosci-report-worker
```

Add logical operator bindings in `harness/config/logical-operators.json`, mapping native logical operators to these physical operators as candidate backends.

## Physical operator command pattern

Use commands like:

```bash
python3 plugins/autosci/bin/autosci_bridge.py run --action extract_claims --envelope "$SOLAR_OPERATOR_ENVELOPE_JSON"
```

## Human test

Create:

```text
harness/artifacts/autosci/smoke/envelope.claim_extract.json
```

Then run:

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool config/physical-operators.json >/tmp/physical-operators.valid.json
python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.valid.json

python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, 'lib')
import operator_runtime

env_path = Path('artifacts/autosci/smoke/envelope.claim_extract.json')
print(env_path)
env = json.loads(env_path.read_text())
print(operator_runtime.submit(env))
PY
```

Manual checklist:

```text
[ ] Operator exists in physical-operators.json.
[ ] operator_runtime.submit does not reject unknown operator.
[ ] Lease is acquired.
[ ] Inbox task is written.
[ ] Result directory contains envelope/result/log artifacts.
[ ] No hidden AutoSci full workflow is invoked.
```

## Done when

At least one native logical operator, `ScientificClaimExtractor`, dispatches to an AutoSci-backed physical operator and produces Solar Evidence ABI output.

---

# Phase 6 — Manuals, personas, and dispatch templates

## Goal

Give scientific operators procedural guidance while keeping hard contracts in capsules, schemas, and gates.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
find personas -maxdepth 2 -type f | sort | sed -n '1,240p' || true
find templates -maxdepth 3 -type f | sort | sed -n '1,240p' || true
mkdir -p personas templates/dispatch
```

## Deliverables

Create personas/manuals:

```text
harness/personas/scientific-paper-ingestor.md
harness/personas/scientific-literature-discoverer.md
harness/personas/scientific-memory-updater.md
harness/personas/scientific-claim-extractor.md
harness/personas/scientific-code-evidence-mapper.md
harness/personas/scientific-experiment-designer.md
harness/personas/scientific-experiment-runner.md
harness/personas/scientific-claim-verifier.md
harness/personas/scientific-report-writer.md
```

Create dispatch templates:

```text
harness/templates/dispatch/scientific-paper-ingest.dispatch.md
harness/templates/dispatch/scientific-claim-extract.dispatch.md
harness/templates/dispatch/scientific-code-evidence-map.dispatch.md
harness/templates/dispatch/scientific-experiment-design.dispatch.md
harness/templates/dispatch/scientific-experiment-run.dispatch.md
harness/templates/dispatch/scientific-claim-verify.dispatch.md
harness/templates/dispatch/scientific-report-write.dispatch.md
```

## Manual pattern

Every manual should include:

```text
Role
Inputs
Outputs
Allowed actions
Forbidden actions
Required evidence
Failure handling
When to ask for human approval
Completion checklist
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
grep -R "research_claims.v1\|experiment_plan.v1\|claim_verdict.v1" personas templates/dispatch | sed -n '1,240p'
grep -R "Do not\|must not\|forbidden\|Forbidden" personas templates/dispatch | sed -n '1,240p'
```

Manual checklist:

```text
[ ] Every native scientific operator has a persona/manual.
[ ] Manuals refer to Evidence ABI outputs.
[ ] Manuals forbid overclaiming and hidden verification.
[ ] Manuals describe failure/inconclusive behavior.
[ ] Manuals do not hardcode AutoSci-only assumptions.
```

## Done when

A coding agent or worker can read the manual and know what artifacts to produce, what not to do, and what counts as completion.

---

# Phase 7 — Research TaskGraph templates

## Goal

Encode AutoSci's workflow as native Solar TaskGraphs.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
mkdir -p workflows
find workflows -maxdepth 2 -type f | sort | sed -n '1,240p' || true
sed -n '1,240p' lib/architecture_guard.py
sed -n '1,320p' lib/graph_scheduler.py || true
```

## Deliverables

Create:

```text
harness/workflows/scientific_paper_ingestion_v1.json
harness/workflows/scientific_claim_extraction_v1.json
harness/workflows/scientific_claim_verification_v1.json
harness/workflows/scientific_experiment_lifecycle_v1.json
harness/workflows/scientific_publication_lifecycle_v1.json
harness/workflows/scientific_research_lifecycle_full_v1.json
harness/workflows/scientific_research_resume_v1.json
```

## Minimum workflow shapes

### `scientific_claim_extraction_v1`

```text
ScientificPaperIngestor
  -> ScientificClaimExtractor
  -> VerifierLite
```

### `scientific_claim_verification_v1`

```text
ScientificPaperIngestor
  -> ScientificClaimExtractor
  -> ScientificMethodExtractor
  -> ScientificCodeEvidenceMapper
  -> ScientificExperimentDesigner
  -> ScientificExperimentRunner
  -> ScientificClaimVerifier
  -> ScientificReportDrafter
```

### `scientific_research_lifecycle_full_v1`

```text
ScientificLiteratureDiscoverer
  -> ScientificPaperIngestor
  -> ScientificPaperAnalyzer
  -> ScientificMemoryUpdater
  -> ScientificGraphUpdater
  -> ScientificClaimExtractor
  -> ScientificMethodExtractor
  -> ScientificCodeEvidenceMapper
  -> ScientificIdeaGenerator
  -> ScientificIdeaEvaluator
  -> ScientificExperimentDesigner
  -> ScientificExperimentRunner
  -> ScientificExperimentMonitor
  -> ScientificClaimVerifier
  -> ScientificReportPlanner
  -> ScientificReportDrafter
  -> ScientificPublicationProducer
  -> ScientificMemoryUpdater
  -> ScientificWorkflowEvolver
```

## Node requirements

Every node should include:

```text
id
logical_operator
required_capabilities
read_scope
write_scope
gate
acceptance or pass_conditions
depends_on where applicable
architecture_policy with package/plugin boundary where applicable
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m json.tool workflows/scientific_claim_verification_v1.json >/tmp/scientific_claim_verification_v1.valid.json
python3 lib/architecture_guard.py validate --graph workflows/scientific_claim_verification_v1.json --strict
python3 lib/architecture_guard.py validate --graph workflows/scientific_research_lifecycle_full_v1.json --strict
```

Manual checklist:

```text
[ ] Every node has logical_operator.
[ ] Every node has required_capabilities.
[ ] Every node has read_scope/write_scope.
[ ] Every node has a gate.
[ ] Dependencies are explicit.
[ ] No node calls a full AutoSci black-box workflow.
[ ] Experiment-running nodes require bounded mode or human approval.
```

## Done when

A human can read the TaskGraph and see the scientific workflow without reading AutoSci internals.

---

# Phase 8 — Deterministic evaluator gates

## Goal

Completion should be decided by Solar gates, not AutoSci self-report.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
find lib/research evaluators -maxdepth 4 -type f | sort | sed -n '1,240p' || true
mkdir -p evaluators/scientific tests/evaluators/scientific/fixtures/pass tests/evaluators/scientific/fixtures/fail
```

## Deliverables

Create:

```text
harness/evaluators/scientific/__init__.py
harness/evaluators/scientific/paper_gate.py
harness/evaluators/scientific/claims_gate.py
harness/evaluators/scientific/method_gate.py
harness/evaluators/scientific/code_evidence_gate.py
harness/evaluators/scientific/idea_gate.py
harness/evaluators/scientific/experiment_plan_gate.py
harness/evaluators/scientific/experiment_result_gate.py
harness/evaluators/scientific/claim_verdict_gate.py
harness/evaluators/scientific/report_gate.py
harness/evaluators/scientific/memory_update_gate.py
harness/evaluators/scientific/lifecycle_gate.py
harness/evaluators/scientific/workflow_evolution_gate.py
```

Create tests:

```text
tests/evaluators/scientific/test_claims_gate.py
tests/evaluators/scientific/test_experiment_plan_gate.py
tests/evaluators/scientific/test_experiment_result_gate.py
tests/evaluators/scientific/test_claim_verdict_gate.py
tests/evaluators/scientific/test_report_gate.py
```

## Gate examples

`claims_gate.py` should check:

```text
research_claims.v1 schema validates
claims array exists
claim_id exists
claim_type exists
each testable claim has source anchor
non-testable claims are explicitly marked
no claim is marked verified at extraction stage
```

`claim_verdict_gate.py` should check:

```text
claim_verdict.v1 schema validates
verdict is supported / partially_supported / not_supported / inconclusive
verdict links to evidence
limitations are present when confidence is not high
artifact paths exist or are declared unavailable with reason
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 -m pytest tests/evaluators/scientific
```

Manual checklist:

```text
[ ] Each evaluator has at least one pass fixture.
[ ] Each evaluator has at least one fail fixture.
[ ] Evaluators can return failure reasons.
[ ] Evaluators do not call an LLM for pass/fail.
[ ] Evaluators reject unsupported or source-free claims.
```

## Done when

Each major scientific artifact can be accepted/rejected/inconclusive by a deterministic gate.

---

# Phase 9 — Knowledge foundation: discovery, ingestion, memory, graph

## Goal

Implement native Solar support for AutoSci's research memory foundation.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
ls -la plugins/autosci
find plugins/autosci -maxdepth 4 -type f | sort | sed -n '1,260p'
find artifacts knowledge run -maxdepth 3 -type d | sort | sed -n '1,200p' || true
```

## Operators/capsules used

```text
ScientificLiteratureDiscoverer
ScientificPaperIngestor
ScientificPaperAnalyzer
ScientificMemoryUpdater
ScientificGraphUpdater

cap.research-literature-discover
cap.research-paper-ingest
cap.research-paper-analyze
cap.research-memory-update
cap.research-graph-update
```

## Evidence produced

```text
literature_discovery.v1
research_paper.v1
research_memory_update.v1
research_graph_update.v1
```

## Deliverables

Implement backend bridge actions or non-AutoSci backend actions for:

```text
ingest_paper
analyze_paper
update_memory
update_graph
discover_literature optional in first pass
```

## Human test

Run a fixture-mode paper ingestion flow:

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action ingest_paper \
  --envelope plugins/autosci/tests/fixtures/envelope.ingest_paper.json

python3 evaluators/scientific/paper_gate.py artifacts/scientific/smoke/research_paper.json
python3 evaluators/scientific/memory_update_gate.py artifacts/scientific/smoke/research_memory_update.json
```

Manual checklist:

```text
[ ] Paper metadata is extracted.
[ ] Source URL or local file is preserved.
[ ] Memory update is an explicit Solar artifact.
[ ] Graph edges are explicit Solar artifacts.
[ ] No hidden AutoSci full workflow was invoked.
[ ] Gates reject malformed metadata.
```

## Done when

Solar can ingest a paper and update research memory/graph through native nodes and evidence artifacts.

---

# Phase 10 — Claim, method, and code evidence extraction

## Goal

Implement native Solar support for paper → claim → method → code evidence mapping.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-claim-extract.yaml
sed -n '1,260p' capability-capsules/cap.research-method-extract.yaml
sed -n '1,260p' capability-capsules/cap.research-code-evidence-map.yaml
find plugins/autosci/adapters -maxdepth 1 -type f | sort
```

## Operators/capsules used

```text
ScientificClaimExtractor
ScientificMethodExtractor
ScientificCodeEvidenceMapper

cap.research-claim-extract
cap.research-method-extract
cap.research-code-evidence-map
```

## Evidence produced

```text
research_claims.v1
research_method.v1
code_evidence_map.v1
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action extract_claims \
  --envelope plugins/autosci/tests/fixtures/envelope.extract_claims.json

python3 plugins/autosci/bin/autosci_bridge.py run \
  --action map_code_evidence \
  --envelope plugins/autosci/tests/fixtures/envelope.map_code_evidence.json

python3 evaluators/scientific/claims_gate.py artifacts/scientific/smoke/research_claims.json
python3 evaluators/scientific/code_evidence_gate.py artifacts/scientific/smoke/code_evidence_map.json
```

Manual checklist:

```text
[ ] Claims are source-grounded.
[ ] Claims are testable or explicitly marked non-testable.
[ ] Methods are separated from claims.
[ ] Code evidence includes file paths/symbols where available.
[ ] Unknown mappings are marked unknown rather than fabricated.
[ ] Gates catch missing source anchors and unsupported code mappings.
```

## Done when

Solar can represent paper → claim → method → code mapping natively.

---

# Phase 11 — Idea generation and evaluation

## Goal

Implement native Solar support for AutoSci-style ideation and novelty/feasibility filtering.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-idea-generate.yaml
sed -n '1,260p' capability-capsules/cap.research-idea-evaluate.yaml
find schemas/evidence -maxdepth 1 -type f | grep idea | sort
```

## Operators/capsules used

```text
ScientificIdeaGenerator
ScientificIdeaEvaluator

cap.research-idea-generate
cap.research-idea-evaluate
```

## Evidence produced

```text
idea_candidate.v1
idea_evaluation.v1
research_memory_update.v1
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action generate_ideas \
  --envelope plugins/autosci/tests/fixtures/envelope.generate_ideas.json

python3 plugins/autosci/bin/autosci_bridge.py run \
  --action evaluate_ideas \
  --envelope plugins/autosci/tests/fixtures/envelope.evaluate_ideas.json

python3 evaluators/scientific/idea_gate.py artifacts/scientific/smoke/idea_evaluation.json
```

Manual checklist:

```text
[ ] Ideas are grounded in paper/memory context.
[ ] Each idea has novelty rationale.
[ ] Each idea has feasibility estimate.
[ ] Duplicate/failed ideas are filtered or marked.
[ ] Idea status is not updated without evidence.
```

## Done when

Solar can generate, evaluate, and record research ideas as native artifacts.

---

# Phase 12 — Experiment design, run, monitor, collect

## Goal

Implement native Solar support for experiment lifecycle while preserving bounded execution and human approval requirements.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-experiment-design.yaml
sed -n '1,260p' capability-capsules/cap.research-experiment-run.yaml
sed -n '1,260p' capability-capsules/cap.research-experiment-monitor.yaml
sed -n '1,260p' personas/scientific-experiment-runner.md
```

## Operators/capsules used

```text
ScientificExperimentDesigner
ScientificExperimentRunner
ScientificExperimentMonitor

cap.research-experiment-design
cap.research-experiment-run
cap.research-experiment-monitor
```

## Evidence produced

```text
experiment_plan.v1
experiment_status.v1
experiment_result.v1
```

## Safety rule

Experiment execution must require at least one of:

```text
fixture mode
dry-run mode
bounded local sandbox
known safe benchmark
explicit human approval for external commands
```

## Human test

Start with fixture mode:

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action design_experiment \
  --envelope plugins/autosci/tests/fixtures/envelope.design_experiment.json

python3 plugins/autosci/bin/autosci_bridge.py run \
  --action run_experiment \
  --envelope plugins/autosci/tests/fixtures/envelope.run_experiment.fixture.json

python3 evaluators/scientific/experiment_plan_gate.py artifacts/scientific/smoke/experiment_plan.json
python3 evaluators/scientific/experiment_result_gate.py artifacts/scientific/smoke/experiment_result.json
```

Manual checklist:

```text
[ ] Experiment plan has metric.
[ ] Experiment plan has baseline or justified absence.
[ ] Experiment plan has success criterion.
[ ] Run command is recorded.
[ ] Logs and metrics are captured.
[ ] Failure is classified as failed/inconclusive, not silently passed.
[ ] Non-fixture external commands require human approval.
```

## Done when

Solar can design and run a bounded experiment as a native DAG segment.

---

# Phase 13 — Claim verification and verdict

## Goal

Implement native claim verdict production and deterministic verdict gating.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-claim-verify.yaml
sed -n '1,260p' schemas/evidence/claim_verdict.v1.schema.json
sed -n '1,260p' evaluators/scientific/claim_verdict_gate.py
```

## Operators/capsules used

```text
ScientificClaimVerifier
cap.research-claim-verify
```

## Evidence produced

```text
claim_verdict.v1
```

## Human test

Prepare four fixtures:

```text
supported_experiment_result.json
partially_supported_experiment_result.json
not_supported_experiment_result.json
inconclusive_experiment_result.json
```

Run:

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action verify_claim \
  --envelope plugins/autosci/tests/fixtures/envelope.verify_claim.supported.json

python3 evaluators/scientific/claim_verdict_gate.py artifacts/scientific/smoke/claim_verdict.json
```

Manual checklist:

```text
[ ] Verdict is one of supported / partially_supported / not_supported / inconclusive.
[ ] Verdict cites claim artifact.
[ ] Verdict cites experiment/static/code evidence.
[ ] Verdict includes limitations.
[ ] Gate catches verdicts with missing evidence references.
[ ] Inconclusive evidence is not upgraded to supported.
```

## Done when

Solar can produce a claim verdict without trusting AutoSci self-report as final acceptance.

---

# Phase 14 — Report, paper, poster, rebuttal, publication bundle

## Goal

Implement native Solar support for evidence-linked report and publication artifact generation.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-report-plan.yaml
sed -n '1,260p' capability-capsules/cap.research-report-draft.yaml
sed -n '1,260p' capability-capsules/cap.research-publication-produce.yaml
find templates/dispatch -maxdepth 1 -type f | grep scientific-report | sort || true
```

## Operators/capsules used

```text
ScientificReportPlanner
ScientificReportDrafter
ScientificPublicationProducer

cap.research-report-plan
cap.research-report-draft
cap.research-publication-produce
```

## Evidence produced

```text
scientific_report.v1
publication_bundle.v1
report.md
optional poster.html
optional rebuttal.md
```

## Human test

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action write_report \
  --envelope plugins/autosci/tests/fixtures/envelope.write_report.json

python3 evaluators/scientific/report_gate.py artifacts/scientific/smoke/scientific_report.json
```

Manual checklist:

```text
[ ] Report sections map to evidence artifacts.
[ ] Unsupported claims are not presented as successful.
[ ] Figures/tables link to artifacts.
[ ] Report has limitations section.
[ ] Publication bundle lists generated files.
[ ] Gate rejects report sections with no evidence references.
```

## Done when

Solar can produce an evidence-linked scientific report and publication bundle natively.

---

# Phase 15 — Full lifecycle workflow and resume/recovery

## Goal

Implement the native equivalent of AutoSci's full research lifecycle.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,360p' workflows/scientific_research_lifecycle_full_v1.json
sed -n '1,360p' workflows/scientific_research_resume_v1.json
sed -n '1,320p' lib/graph_scheduler.py || true
sed -n '1,320p' lib/projection_engine.py || true
sed -n '1,320p' lib/session_log.py || true
```

## Deliverables

Finalize:

```text
harness/workflows/scientific_research_lifecycle_full_v1.json
harness/workflows/scientific_research_resume_v1.json
harness/evaluators/scientific/lifecycle_gate.py
```

## Full workflow shape

```text
ScientificLiteratureDiscoverer
  -> ScientificPaperIngestor
  -> ScientificPaperAnalyzer
  -> ScientificMemoryUpdater
  -> ScientificGraphUpdater
  -> ScientificClaimExtractor
  -> ScientificMethodExtractor
  -> ScientificCodeEvidenceMapper
  -> ScientificIdeaGenerator
  -> ScientificIdeaEvaluator
  -> ScientificExperimentDesigner
  -> ScientificExperimentRunner
  -> ScientificExperimentMonitor
  -> ScientificClaimVerifier
  -> ScientificReportPlanner
  -> ScientificReportDrafter
  -> ScientificPublicationProducer
  -> ScientificMemoryUpdater
  -> ScientificWorkflowEvolver
```

## Human test

Use a tiny paper and fixture repo. If no `solar run-workflow` CLI exists, submit nodes manually through the scheduler/dispatcher path already available in the repo.

Expected final artifact tree:

```text
artifacts/scientific/<job_id>/
  01_paper/
  02_claims/
  03_methods/
  04_code_evidence/
  05_ideas/
  06_experiment_plan/
  07_experiment_result/
  08_verdict/
  09_report/
  10_memory_update/
  lifecycle_summary.json
  evidence.jsonl
```

Manual checklist:

```text
[ ] Failed node can be resumed without rerunning completed nodes.
[ ] Each node has result.json or typed evidence artifact.
[ ] Each node has evidence.jsonl or equivalent evidence entry.
[ ] Parent lifecycle gate summarizes pass/fail/inconclusive.
[ ] Human can inspect intermediate artifacts.
[ ] No hidden AutoSci end-to-end workflow owns the graph.
```

## Done when

Solar can run an end-to-end scientific research lifecycle as a native TaskGraph.

---

# Phase 16 — Workflow evolution / SciEvolve-like feedback

## Goal

Implement native Solar support for learning from scientific workflow outcomes.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
sed -n '1,260p' capability-capsules/cap.research-workflow-evolve.yaml
sed -n '1,260p' schemas/evidence/workflow_evolution.v1.schema.json
find evaluators/scientific -maxdepth 1 -type f | sort
```

## Operators/capsules used

```text
ScientificWorkflowEvolver
cap.research-workflow-evolve
```

## Evidence produced

```text
workflow_evolution.v1
recommended_changes.md
optional patch_candidates/
```

## Evolver must collect

```text
failed nodes
gate rejection reasons
ambiguous manuals/prompts
insufficient schemas
poor operator bindings
human intervention points
runtime errors
```

## Evolver may propose

```text
capsule edits
manual edits
routing edits
gate improvements
workflow template changes
```

It must not silently promote changes without review.

## Human test

Use one intentionally failed workflow run.

```bash
cd "$SOLAR_REPO/harness"
python3 plugins/autosci/bin/autosci_bridge.py run \
  --action evolve_workflow \
  --envelope plugins/autosci/tests/fixtures/envelope.evolve_workflow.failed_run.json

python3 evaluators/scientific/workflow_evolution_gate.py artifacts/scientific/smoke/workflow_evolution.json
```

Manual checklist:

```text
[ ] Evolution report cites concrete failed nodes.
[ ] It proposes bounded changes.
[ ] It separates manual changes from schema/gate changes.
[ ] It does not silently edit protected core runtime.
[ ] Human can accept/reject each proposed change.
```

## Done when

Solar can learn from AutoSci-style research runs without losing governance.

---

# Phase 17 — Naming and architecture cleanup

## Goal

Ensure the final architecture reads as a Solar-native scientific research runtime, not a wrapper around AutoSci.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
grep -R "AutoSci\|autosci" capability-capsules workflows schemas/evidence evaluators/scientific config/logical-operators.json config/physical-operators.json personas templates/dispatch | sed -n '1,400p' || true
```

## Cleanup rule

AutoSci names are allowed in:

```text
plugins/autosci/**
physical operator vendor/backend descriptions
capsule bindings/provenance
implementation_package metadata
```

AutoSci names should not dominate:

```text
capability IDs
logical operator names
Evidence ABI schema names
workflow template names
gate names
manual role names
```

## Human test

Checklist:

```text
[ ] Capabilities are named `cap.research-*`, not `cap.autosci-*`, except where explicitly backend-specific.
[ ] Logical operators are `Scientific*`, not `AutoSci*`.
[ ] Evidence schemas are generic scientific schemas.
[ ] Workflows are scientific lifecycle workflows, not AutoSci lifecycle wrappers.
[ ] Plugin package remains as backend implementation only.
```

## Done when

The architecture reads as:

```text
Solar scientific research runtime using AutoSci as one backend implementation package.
```

---

# Phase 18 — End-to-end human acceptance test

## Goal

Prove that Solar has all AutoSci capabilities native.

## Directory/context commands

```bash
cd "$SOLAR_REPO/harness"
find workflows -maxdepth 1 -type f | sort | grep scientific
find capability-capsules -maxdepth 1 -type f | sort | grep scientific
find schemas/evidence -maxdepth 1 -type f | sort
find evaluators/scientific -maxdepth 1 -type f | sort
find plugins/autosci -maxdepth 3 -type f | sort | sed -n '1,400p'
```

## Acceptance Test A — Paper ingestion and memory

```bash
cd "$SOLAR_REPO/harness"
# Use actual workflow CLI if available; otherwise submit the template nodes manually.
solar run-workflow scientific_paper_ingestion_v1 \
  --paper plugins/autosci/tests/fixtures/sample_paper.md \
  --mode fixture
```

Pass if:

```text
[ ] research_paper.v1 exists.
[ ] research_memory_update.v1 exists.
[ ] graph update exists if graph update node is enabled.
[ ] Gates accept valid artifacts.
```

## Acceptance Test B — Claim extraction and code mapping

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_claim_extraction_v1 \
  --paper plugins/autosci/tests/fixtures/sample_paper.md \
  --repo plugins/autosci/tests/fixtures/sample_repo \
  --mode fixture
```

Pass if:

```text
[ ] research_claims.v1 exists.
[ ] research_method.v1 exists.
[ ] code_evidence_map.v1 exists.
[ ] Claims are source-grounded.
[ ] Unknown mappings are marked unknown.
```

## Acceptance Test C — Experiment lifecycle

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_experiment_lifecycle_v1 \
  --claim artifacts/scientific/demo/research_claims.json \
  --repo plugins/autosci/tests/fixtures/sample_repo \
  --mode fixture
```

Pass if:

```text
[ ] experiment_plan.v1 exists.
[ ] experiment_status.v1 exists.
[ ] experiment_result.v1 exists.
[ ] Logs and metrics exist.
[ ] Failure is classified correctly.
```

## Acceptance Test D — Claim verdict

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_claim_verification_v1 \
  --claim artifacts/scientific/demo/research_claims.json \
  --experiment-result artifacts/scientific/demo/experiment_result.json \
  --mode fixture
```

Pass if:

```text
[ ] claim_verdict.v1 exists.
[ ] Verdict is supported / partially_supported / not_supported / inconclusive.
[ ] Verdict cites evidence.
[ ] Gate rejects unsupported verdicts.
```

## Acceptance Test E — Report and publication

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_publication_lifecycle_v1 \
  --verdict artifacts/scientific/demo/claim_verdict.json \
  --mode fixture
```

Pass if:

```text
[ ] scientific_report.v1 exists.
[ ] report.md exists.
[ ] publication_bundle.v1 exists.
[ ] Report is evidence-linked.
[ ] Limitations are explicit.
```

## Acceptance Test F — Full lifecycle

```bash
cd "$SOLAR_REPO/harness"
solar run-workflow scientific_research_lifecycle_full_v1 \
  --input plugins/autosci/tests/fixtures/full_lifecycle_task.json \
  --mode fixture
```

Pass if:

```text
[ ] Every major AutoSci capability appears as a Solar-native node.
[ ] Every node has a logical operator.
[ ] Every node has a capability capsule.
[ ] Every node emits Evidence ABI artifacts.
[ ] Gates decide pass/fail/inconclusive.
[ ] AutoSci package is used only as backend implementation where appropriate.
[ ] Human can inspect intermediate artifacts without reading AutoSci internals.
```

## Final completion definition

The implementation is complete only when:

```text
[ ] AutoSci workflow is decomposed into Solar-native stages.
[ ] All major AutoSci capabilities have native Solar logical operators.
[ ] All major capabilities have clean declarative capsules.
[ ] Capsules bind to implementation packages without becoming implementation packages.
[ ] AutoSci code lives under plugins/autosci as backend adapter code.
[ ] Evidence ABI schemas exist for every major artifact.
[ ] Evaluator gates exist for every major artifact.
[ ] Research TaskGraph templates exist for minimal, verification, experiment, publication, and full lifecycle flows.
[ ] Human can run fixture-mode smoke tests for each capability group.
[ ] Human can inspect intermediate artifacts without reading AutoSci internals.
[ ] No single AutoSciRunner black box owns the workflow.
```

---

# Appendix A — Directory lookup commands for agents

These are the main commands agents should use to locate relevant context:

```bash
cd "$SOLAR_REPO"
sed -n '1,240p' README.md
sed -n '1,260p' docs/solar-architecture-code-map.md

cd "$SOLAR_REPO/harness"
sed -n '1,240p' schemas/plugin.schema.json
sed -n '1,300p' lib/plugin_loader.py
sed -n '1,360p' lib/operator_runtime.py
sed -n '1,360p' tools/operatord.py
sed -n '1,360p' config/logical-operators.json
sed -n '1,360p' config/physical-operators.json
sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/draft/capability-capsule.v1.draft.json
find . -maxdepth 3 -type d | sort | sed -n '1,240p'
find . -maxdepth 3 -type f | sort | sed -n '1,240p'

cd "$SOLAR_REPO/harness/plugins/autosci"
pwd
find . -maxdepth 4 -type f | sort | sed -n '1,260p'

cd "$SOLAR_REPO/harness/capability-capsules"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$SOLAR_REPO/harness/workflows"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$SOLAR_REPO/harness/schemas/evidence"
pwd
find . -maxdepth 1 -type f | sort

cd "$SOLAR_REPO/harness/evaluators/scientific"
pwd
find . -maxdepth 1 -type f | sort

cd "$SOLAR_REPO/harness/personas"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$SOLAR_REPO/harness/templates/dispatch"
pwd
find . -maxdepth 1 -type f | sort | grep scientific

cd "$AUTOSCI_REPO"
sed -n '1,260p' README.md
find . -maxdepth 4 -type f | sort | grep -E '(README|\.md$|\.py$|\.ya?ml$|\.json$)' | sed -n '1,360p'
```

---

# Appendix B — Minimal PR slicing recommendation

Implement in PRs that match the phases, but allow these combined PRs if needed:

```text
PR 1: Phase 0 docs only
PR 2: Phase 1 schemas + fixtures
PR 3: Phase 2 capsules + registry
PR 4: Phase 3 logical operators
PR 5: Phase 4 AutoSci implementation package skeleton + smoke
PR 6: Phase 5 physical operators + one working dispatch
PR 7: Phase 6 manuals/templates
PR 8: Phase 7 workflows
PR 9: Phase 8 evaluator gates
PR 10: Phase 9-10 paper/claim/code foundation
PR 11: Phase 11-13 idea/experiment/verdict
PR 12: Phase 14-16 report/lifecycle/evolution
PR 13: Phase 17-18 cleanup + acceptance
```

Each PR must include either:

```text
1. a human-readable artifact, or
2. a passing smoke command, or
3. a deterministic gate/test.
```


---


## Part III — Executable Coding-Agent Continuation Prompt

You are the implementation agent responsible for continuing the AutoSci-to-Solar migration in OpenSolar. Your job is **not** to add another compatibility wrapper or make fixture tests greener. Your job is to convert the existing architectural shell into a genuinely executable, recoverable, evidence-gated Solar-native scientific research runtime.

This prompt is intentionally strict. Treat every statement of completion as an evidence claim that must be supported by commands, artifacts, scheduler state, node results, gate results, and logs.

---

## 0. Inputs and embedded references

This coding-agent prompt is Part III of a single master handoff document. The two required written references are embedded in the same file:

1. **Part I — Detailed Current-State Gap Analysis**
2. **Part II — Original 18-Phase Solar-Native Implementation Plan**

Read both parts in full before editing code. Do not rely only on this prompt or on prior conversation context.

Repository access required:

1. writable local checkout of `Coconut-ch1ken/OpenSolar`, including branch/ref `2026-06-25-1717-snapshot` or the user's current continuation branch;
2. read-only local checkout of `skyllwt/AutoSci` as the behavioral oracle;
3. optional read-only checkout of `Stellven/AI4Research` as a Solar architecture reference.

If a required repository is unavailable, record that limitation explicitly and continue only with work that can be proved from the available checkout. Never fabricate repository state or test evidence.

---

## 1. Role and mission

Act as a senior runtime, workflow-engine, and scientific-computing engineer. You are responsible for preserving Solar’s control-plane invariants while reproducing native AutoSci behavior.

Your mission is:

> Make AutoSci-derived scientific research capabilities execute as Solar-native TaskGraph nodes, with generic logical operators and capsules, bounded backend actions, durable state, deterministic gates, explicit human approvals, recoverable asynchronous experiments, and evidence-linked publication artifacts.

The final system must read architecturally as:

```text
Solar scientific research runtime
  using AutoSci-derived implementation modules as bounded backend actions
```

It must not read as:

```text
Solar wrapper around an AutoSci lifecycle runner
```

---

## 2. Repository roles and modification policy

### 2.1 OpenSolar — writable implementation repository

Primary repository:

```text
Coconut-ch1ken/OpenSolar
ref: 2026-06-25-1717-snapshot
```

All implementation changes belong here unless the user explicitly authorizes another repository.

### 2.2 Native AutoSci — read-only behavioral specification

Reference repository:

```text
skyllwt/AutoSci
```

Treat this repository as the behavioral oracle for:

- command semantics;
- wiki/entity schemas;
- lifecycle transitions;
- side effects;
- human gates;
- experiment deployment/status/collection behavior;
- publication behavior;
- failure and resume behavior.

Do **not** modify this repository. Do not solve the migration by invoking its full `/research` workflow as a subprocess. You may port, adapt, or vendor bounded implementation components into `harness/plugins/autosci/` if licensing and repository policy allow, but Solar must remain the workflow owner.

### 2.3 Solar reference repository — read-only architecture reference

Reference repository:

```text
Stellven/AI4Research
```

Use it to confirm the intended semantics of:

- TaskGraph IR;
- logical/physical operators;
- actor and host registries;
- leases and dispatch;
- Evidence ABI;
- deterministic node gates and parent gates;
- session logs and projections;
- capability capsules;
- plugin boundaries.

---

## 3. Resolve local paths and establish a clean branch

Use environment variables. Prefer the known local paths if they exist, otherwise discover them.

```bash
export SOLAR_REPO="${SOLAR_REPO:-/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar}"
export AUTOSCI_REPO="${AUTOSCI_REPO:-/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci}"
export SOLAR_REF="${SOLAR_REF:-2026-06-25-1717-snapshot}"

for p in "$SOLAR_REPO" "$AUTOSCI_REPO"; do
  test -d "$p/.git" || { echo "missing git checkout: $p" >&2; exit 2; }
done

cd "$SOLAR_REPO"
pwd
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline --decorate

cd "$AUTOSCI_REPO"
pwd
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline --decorate
```

Do not overwrite uncommitted user work. If OpenSolar is dirty, inventory the changes and work around them or create a safe worktree. Never discard, reset, stash, or overwrite user changes without explicit authorization.

Create a continuation branch or worktree from the snapshot, for example:

```bash
cd "$SOLAR_REPO"
git fetch --all --prune

git worktree add \
  "${SOLAR_REPO}-autosci-native-continuation" \
  -b autosci/native-lifecycle-continuation \
  "$SOLAR_REF"

export WORK_REPO="${SOLAR_REPO}-autosci-native-continuation"
cd "$WORK_REPO"
git status --short
```

If the branch already exists, use a different non-destructive name.

---

## 4. Non-negotiable architecture

For every scientific stage, preserve this execution chain:

```text
TaskGraph node
  -> logical operator
  -> capability capsule
  -> logical binding
  -> physical operator
  -> registered host / actor
  -> bounded implementation action
  -> command execution
  -> typed Evidence ABI artifact
  -> deterministic node gate
  -> scheduler state transition
  -> parent lifecycle gate
```

### 4.1 Mandatory rules

1. Do not introduce or retain a giant `AutoSciRunner` or equivalent lifecycle owner.
2. Do not let `autosci_bridge.py` own the research stage sequence.
3. Do not call native AutoSci’s full `/research` workflow from OpenSolar.
4. Keep capability IDs generic: `cap.research-*`.
5. Keep logical operator names generic: `Scientific*`.
6. AutoSci-specific names may appear in backend package names, physical worker vendor metadata, bindings, and provenance.
7. Every node must emit typed evidence with job/sprint/node provenance.
8. A schema-valid artifact is not proof that work ran.
9. A fixture/smoke result is not proof of native parity.
10. A route is not an implementation.
11. A safety-gated route may be semantically complete, but semantic parity and execution policy must be tracked separately.
12. Human approvals must be durable scheduler state, not prompt text or an untracked boolean.
13. External wait states must be resumable and must not be treated as failure.
14. No stage may infer completion from the mere existence of unrelated wiki files.
15. No parent lifecycle gate may default to pass when runtime result maps are empty.
16. All protected side effects require explicit approval and before/after evidence.
17. Do not silently rewrite protected Solar core runtime merely to make AutoSci tests pass.
18. Do not weaken tests or gates to accept an incomplete implementation.

---

## 5. Read these files before editing anything

### 5.1 Embedded architecture and gap references

Before editing anything, read these earlier sections of this same master document in full:

```text
Part I — Detailed Current-State Gap Analysis
Part II — Original 18-Phase Solar-Native Implementation Plan
```

Treat Part II as the architecture/completion oracle and Part I as the current-state and prioritization baseline. Where later repository evidence conflicts with an earlier statement, preserve the architecture rules but update the current-state claim using real commands and artifacts.

### 5.2 OpenSolar architecture and current migration

```bash
cd "$WORK_REPO"

sed -n '1,280p' README.md
sed -n '1,360p' docs/solar-architecture-code-map.md

for f in \
  docs/integrations/autosci/autosci-workflow-map.md \
  docs/integrations/autosci/autosci-solar-feature-parity-matrix.md \
  docs/integrations/autosci/audit/migrated-autosci-parity-audit-2026-06-25.md \
  docs/integrations/autosci/phase0-progress-log.md \
  docs/integrations/autosci/phase1-evidence-abi-report.md \
  docs/integrations/autosci/phase2-capsule-report.md \
  docs/integrations/autosci/phase3-progress-log.md \
  docs/integrations/autosci/phase4-progress-log.md \
  docs/integrations/autosci/phase5-progress-log.md \
  docs/integrations/autosci/phase6-progress-log.md \
  docs/integrations/autosci/phase7-progress-log.md \
  docs/integrations/autosci/phase8-progress-log.md \
  docs/integrations/autosci/phase9-progress-log.md \
  docs/integrations/autosci/phase10-progress-log.md \
  docs/integrations/autosci/phase11-progress-log.md \
  docs/integrations/autosci/phase12-progress-log.md \
  docs/integrations/autosci/phase13-progress-log.md \
  docs/integrations/autosci/phase14-progress-log.md \
  docs/integrations/autosci/phase16-progress-log.md \
  docs/integrations/autosci/phase17-progress-log.md \
  docs/integrations/autosci/phase18-progress-log.md \
  docs/integrations/autosci/phase19-progress-log.md; do
  echo "===== $f ====="
  sed -n '1,4000p' "$f"
done

# Confirm the missing dedicated phase-15 log.
test ! -e docs/integrations/autosci/phase15-progress-log.md && \
  echo "phase15 progress log absent"
```

Read the runtime paths:

```bash
cd "$WORK_REPO/harness"

sed -n '1,500p' lib/graph_scheduler.py
sed -n '1,500p' lib/operator_runtime.py
sed -n '1,420p' lib/session_log.py
sed -n '1,420p' lib/projection_engine.py
sed -n '1,360p' lib/plugin_loader.py
sed -n '1,360p' lib/capability_capsules.py
sed -n '1,320p' lib/architecture_guard.py
sed -n '1,320p' lib/workflow_guard.py

python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.json
python3 -m json.tool config/physical-operators.json >/tmp/physical-operators.json
python3 -m json.tool config/actor-hosts.json >/tmp/actor-hosts.json

sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/plugin.schema.json
sed -n '1,260p' plugins/autosci/manifest.yaml
sed -n '1,320p' plugins/autosci/README.md
```

Read every scientific workflow, capsule, gate, and relevant test:

```bash
find workflows -maxdepth 1 -type f -name 'scientific*.json' -print -exec sed -n '1,1200p' {} \;
find capability-capsules -maxdepth 1 -type f -name 'cap.research-*.yaml' -print -exec sed -n '1,500p' {} \;
find schemas/evidence -maxdepth 1 -type f -name '*.json' -print | sort
find evaluators/scientific -maxdepth 1 -type f -print | sort

sed -n '1,900p' evaluators/scientific/lifecycle_gate.py
sed -n '1,400p' evaluators/scientific/autosci_skill_run_gate.py
sed -n '1,500p' evaluators/scientific/autosci_feature_parity_gate.py
sed -n '1,360p' tests/evaluators/scientific/test_lifecycle_gate.py
```

Read the AutoSci adapter paths in full. Do not skim only the CLI surface:

```bash
cd "$WORK_REPO/harness"

sed -n '1,1200p' plugins/autosci/config/feature_parity_routes.v1.json
sed -n '1,1200p' plugins/autosci/config/feature_operator_bindings.v1.json
sed -n '1,1000p' plugins/autosci/bin/autosci_skill_shim.py
sed -n '1,10000p' plugins/autosci/bin/autosci_bridge.py
sed -n '1,1200p' plugins/autosci/bin/autosci_parity_bridge.py

find plugins/autosci/adapters -maxdepth 2 -type f -print -exec sed -n '1,700p' {} \;
find plugins/autosci/backends -maxdepth 2 -type f -print -exec sed -n '1,900p' {} \;
find plugins/autosci/tests -maxdepth 2 -type f -print | sort
sed -n '1,5000p' plugins/autosci/tests/test_autosci_skill_shim.py

sed -n '1,900p' ../tools/research_wiki.py
```

Read generated wrappers, but do not count them as implementations:

```bash
cd "$WORK_REPO"
find .agents/skills -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort
sed -n '1,240p' .agents/skills/research/SKILL.md
```

### 5.3 Native AutoSci behavioral specification

Read the complete native architecture and schema:

```bash
cd "$AUTOSCI_REPO"

sed -n '1,700p' README.md
sed -n '1,700p' CLAUDE.md
sed -n '1,700p' runtime/CLAUDE.md
find runtime/schema -maxdepth 2 -type f -print -exec sed -n '1,900p' {} \;
sed -n '1,1600p' tools/research_wiki.py
```

Read every native skill protocol:

```bash
cd "$AUTOSCI_REPO"
find .claude/skills -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort

for f in $(find .claude/skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort); do
  echo "===== $f ====="
  sed -n '1,1200p' "$f"
done
```

If the repository uses `i18n/en/skills/` as the current canonical path, compare it with `.claude/skills/` and record any divergence.

Read the native tools used by the critical workflows:

```bash
cd "$AUTOSCI_REPO"
find tools -maxdepth 2 -type f | sort | grep -E \
  '(research_wiki|init_discovery|prepare_paper_source|discover|daily_arxiv|send_email|remote|poster|wiki2dag|visualize|serve|lint|reset)' \
  | while read -r f; do echo "===== $f ====="; sed -n '1,1600p' "$f"; done
```

---

## 6. Establish the baseline before changing code

Run the current tests using the repository’s documented environment. Record exact commands, exit codes, duration, and failures.

```bash
cd "$WORK_REPO"

# Rebuild only if needed and only from the committed dependency manifest.
test -x .venv/bin/python || {
  MISE_PYTHON="${MISE_PYTHON:-$HOME/.local/share/mise/installs/python/3.14.2/bin/python3}"
  "$MISE_PYTHON" -m venv .venv
  UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/Library/Caches/uv}" \
    uv pip sync --python .venv/bin/python requirements/autosci-solar-native-dev.txt
}

export PYTHONPATH="$WORK_REPO/harness"

.venv/bin/python -m pytest harness/plugins/autosci/tests -q
.venv/bin/python -m pytest harness/tests/evaluators/scientific -q

.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py \
  inventory --out /tmp/autosci-parity-baseline.json
python3 -m json.tool /tmp/autosci-parity-baseline.json >/tmp/autosci-parity-baseline.pretty.json
```

Also run static consistency probes:

```bash
cd "$WORK_REPO/harness"

python3 -m json.tool config/logical-operators.json >/dev/null
python3 -m json.tool config/physical-operators.json >/dev/null
python3 -m json.tool config/actor-hosts.json >/dev/null
python3 -m json.tool plugins/autosci/config/feature_parity_routes.v1.json >/dev/null
python3 -m json.tool plugins/autosci/config/feature_operator_bindings.v1.json >/dev/null

python3 lib/architecture_guard.py validate \
  --graph workflows/scientific_research_lifecycle_full_v1.json --strict
python3 lib/architecture_guard.py validate \
  --graph workflows/scientific_research_resume_v1.json --strict
```

Create a baseline report before edits:

```text
docs/integrations/autosci/continuation-baseline-2026-06-25.md
```

It must include:

- exact OpenSolar and AutoSci SHAs;
- working tree state;
- test commands/results;
- current 28-route status counts;
- current registry-chain failures;
- current `$research` execution trace;
- current lifecycle-gate false-positive probe;
- current committed-versus-regenerated parity inventory diff;
- known external dependencies unavailable in the environment.

---

## 7. First priority: repair truth and auditability

Do this before implementing new behavior.

### 7.1 Replace the one-dimensional route status model

Current `coverage_status` conflates completeness and safety. Add explicit fields to the route and generated parity schemas:

```json
{
  "semantic_parity": "full | partial | missing",
  "execution_policy": "pure | bounded_local | approval_required | provider_required",
  "proof_level": "E0 | E1 | E2 | E3 | E4 | E5",
  "proof_refs": [],
  "remaining_requirements": []
}
```

Preserve backward compatibility temporarily if needed, but make the new fields authoritative.

Definitions:

```text
E0 declared route/config only
E1 schema/capsule/graph/gate validates
E2 fixture/smoke action passes
E3 one real bounded stage executes with audited evidence
E4 recoverable multi-stage lifecycle executes through Solar
E5 representative end-to-end workflow reaches final accepted artifacts
```

A safety-gated route may be `semantic_parity=full` only if the approved execution path has at least E3 evidence, and lifecycle commands require E4/E5.

### 7.2 Eliminate stale parity artifacts

The committed Phase 19 inventory is inconsistent with later route status. Implement one of:

- regenerate and commit the current inventory deterministically; or
- stop committing generated run inventories and generate them in CI/release artifacts.

Add a test that fails when:

```text
route config counts != generated inventory counts
route item fields != inventory item fields
native skill set != routed skill set
committed artifact provenance ref != current config ref
```

Never permit a completed inventory with stale full claims.

### 7.3 Split contract gates from runtime acceptance gates

Rename or separate current lifecycle validation:

```text
lifecycle_contract_gate.py
lifecycle_runtime_gate.py
```

The contract gate validates only graph structure.

The runtime gate must require:

- expected job ID;
- complete node-result map for every required executed node;
- node gate-result map;
- artifact paths that exist;
- schema validation;
- artifact hashes;
- provenance matching job/sprint/node;
- dependency evidence linkage;
- approval evidence for gated effects;
- no failed or inconclusive required node;
- correct final state;
- final parent-gate evidence.

It must return inconclusive or failed—not passed—when result maps are absent.

Add negative tests for every missing field and cross-job artifact reuse.

### 7.4 Add a full-parity acceptance gate

The existing parity gate may continue validating inventory shape, but add an acceptance gate that rejects any command claimed full without the minimum proof level.

For `$research`, require E5.

---

## 8. Second priority: repair the complete scheduler binding chain

Create a deterministic registry audit tool, for example:

```text
harness/tools/audit_scientific_runtime_bindings.py
```

It must traverse every scientific workflow and verify:

```text
node.logical_operator exists
node.required_capabilities resolve to registered capsules
logical operator has a binding
binding candidate actor/physical operator exists
candidate condition is currently meaningful, not stale placeholder text
physical operator command exists
physical operator host_id exists in actor-hosts.json
host type is supported by operator runtime
plugin manifest declares capability
bridge action exists
expected Evidence ABI exists
node gate exists
```

Exit nonzero on any failure and emit JSON plus human-readable output.

### 8.1 Register a real local AutoSci backend host

Use the host type that `operator_runtime.py` actually supports for local commands. Do not invent an unsupported type merely to satisfy JSON.

Replace placeholder ownership such as:

```text
owner_host: solar@example-host
```

with a valid host reference. Include health and lifecycle fields consistent with the existing registry model.

### 8.2 Complete logical bindings

Ensure every operator in the full and resume graphs has at least one executable candidate, including:

```text
ScientificLiteratureDiscoverer
ScientificPaperIngestor
ScientificPaperAnalyzer
ScientificMemoryUpdater
ScientificGraphUpdater
ScientificClaimExtractor
ScientificMethodExtractor
ScientificCodeEvidenceMapper
ScientificIdeaGenerator
ScientificIdeaEvaluator
ScientificExperimentDesigner
ScientificExperimentRunner
ScientificExperimentMonitor
ScientificClaimVerifier
ScientificReportPlanner
ScientificReportDrafter
ScientificPublicationProducer
ScientificWorkflowEvolver
```

Remove stale conditions such as `backend_action_pending` once the action is available. Do not replace them with `always` unless the operator is genuinely available and policy-compatible.

### 8.3 Correct physical operator metadata and policies

Do not label live-capable workers `autosci-adapter-fixture`.

Separate workers when policies differ. Examples:

```text
autosci-paper-local-worker            network denied/optional
scientific-discovery-provider-worker  network provider-limited
autosci-model-review-worker           explicit model-command/provider policy
autosci-experiment-local-worker       approval + allowlist + sandbox
autosci-experiment-remote-worker      approval + SSH/rsync host policy
autosci-tex-compile-worker            approval + tool allowlist
autosci-poster-render-worker          approval + browser/render policy
autosci-email-worker                  approval + secret/SMTP policy
```

The user-facing shim must not bypass these policy distinctions by directly calling unrestricted bridge code.

### 8.4 Reconcile the plugin manifest

Declare all eighteen target capabilities:

```text
cap.research-paper-ingest
cap.research-literature-discover
cap.research-memory-update
cap.research-graph-update
cap.research-paper-analyze
cap.research-claim-extract
cap.research-method-extract
cap.research-code-evidence-map
cap.research-idea-generate
cap.research-idea-evaluate
cap.research-experiment-design
cap.research-experiment-run
cap.research-experiment-monitor
cap.research-claim-verify
cap.research-report-plan
cap.research-report-draft
cap.research-publication-produce
cap.research-workflow-evolve
```

Declare actual optional dependencies, read/write scopes, external tools, and rollback/disable behavior.

---

## 9. Third priority: make `$research` submit and run a TaskGraph

This is the primary implementation objective.

### 9.1 Remove bridge-level lifecycle ownership

`run_research_lifecycle` may remain temporarily as a migration diagnostic/projection command, but it must not be the execution backend for `$research`.

Rename it to something truthful if retained, such as:

```text
project_research_lifecycle_state
```

It may summarize scheduler state. It may not decide that stages ran from generic wiki counts.

### 9.2 Introduce a typed workflow request

Create a schema such as:

```text
harness/schemas/workflows/scientific_research_request.v1.schema.json
```

Required fields should include:

```text
job_id
objective/topic/target
input papers or discovery seed
venue optional
start_from optional
skip_paper optional
max_iterations
execution_mode
provider policy
human gate policy
budget/time/resource constraints
artifact root
approval references if pre-authorized
```

### 9.3 Compile a job-specific TaskGraph

Implement a compiler that:

- loads the canonical workflow template;
- creates a unique job-scoped artifact root;
- resolves conditional nodes;
- adds explicit human-gate nodes;
- adds external-wait and collection nodes;
- assigns job/sprint/node IDs;
- binds inputs and predecessor artifacts;
- validates scopes and architecture;
- writes the instantiated graph under the job directory;
- submits it to the existing scheduler.

The compiler must not execute scientific work.

A suitable path might be:

```text
harness/lib/research/scientific_workflow_compiler.py
```

### 9.4 Use the existing scheduler and operator runtime

The execution path must use the repository’s real scheduler state and physical operator dispatch. Do not implement a parallel ad hoc loop unless you are extending the existing scheduler in a general way.

Every node dispatch must record:

```text
job_id
sprint_id
node_id
attempt_id
logical_operator
selected physical operator
host/actor
capsule IDs
input evidence IDs and hashes
read/write scopes
approval state
command/action
start/end timestamps
exit/result state
output evidence IDs and hashes
gate verdict
```

### 9.5 Model the native lifecycle, not a flat linear chain

The instantiated graph must represent at least:

```text
Stage 0: bootstrap / inspect / optional init / optional ingest
Stage 1: ideation + novelty + independent review
Human Gate 1: accept/reject idea
Stage 2: experiment design + design review + code/setup inspection
Stage 3a: deploy
Stage 3b: wait/status
Stage 3c: collect
Stage 4: evaluate
Decision: validate | fail | iterate
Human Gate 2: accept result / request iteration / stop
Stage 5a: paper plan
Stage 5b: draft
Stage 5c: review/refine loop
Stage 5d: compile and submission checks
Final memory/graph/log update
Optional workflow-evolution proposal
```

Do not hide this inside one operator.

### 9.6 Explicit human gates

Represent approvals as durable task states and evidence artifacts, for example:

```text
human_decision.v1
```

Required fields:

```text
job_id
node_id
decision_type
decision
accepted/rejected artifact IDs
scope
constraints
actor/user reference
timestamp
signature/hash or immutable reference
```

A CLI or file-backed approval command may be used, but the scheduler must observe it and transition state.

### 9.7 External wait and resume

Deployment may yield:

```text
waiting_for_external
```

The scheduler must persist:

- remote/local process identity;
- host/session;
- launch command hash;
- output locations;
- polling policy;
- next eligible poll;
- timeout/cancellation policy.

A later process must be able to resume by job ID. Do not infer resume state from global wiki counts.

### 9.8 `--start-from` semantics

Support native-compatible `--start-from` only when predecessor evidence is supplied and accepted for the same job or explicitly imported with provenance.

Do not mark skipped predecessor stages complete from page existence alone. Record them as:

```text
imported_accepted
```

with source evidence and hashes, or reject the request.

### 9.9 `--skip-paper` semantics

Skipping publication must create an explicit conditional skip verdict. It must not leave publication nodes missing without explanation.

---

## 10. Fourth priority: implement native OmegaWiki invariants

The current simplified wiki helper is not sufficient for native AutoSci semantics.

### 10.1 Preferred implementation approach

Choose one of these, document the decision, and preserve licensing:

1. port the relevant native `runtime/loader.py`, schemas, and `tools/research_wiki.py` logic into `harness/plugins/autosci/omegawiki/`; or
2. implement equivalent generic Solar knowledge-state modules under the plugin and prove behavior against native golden fixtures.

Do not put AutoSci-specific schema mechanics into unrelated Solar control-plane core.

### 10.2 Required entity support

Support and validate at least:

```text
papers
concepts
topics
people
methods
ideas
experiments
Summary
foundations
```

### 10.3 Required lifecycle transitions

Enforce:

```text
idea:
  proposed -> in_progress
  in_progress -> tested
  tested -> validated | failed

experiment:
  planned -> running
  running -> completed | abandoned
```

Reject illegal transitions. Require `failure_reason` when an idea fails. Record before/after hashes and transition evidence.

Do not permit generic `set-meta status=...` to bypass the transition command.

### 10.4 Required graph and citation support

Implement:

- validated edge types;
- endpoint topology checks;
- confidence/evidence fields where required;
- symmetric-edge canonicalization;
- deduplication;
- citation graph separate from semantic graph;
- batch writes with transactional evidence;
- reference existence warnings/errors;
- provenance.

### 10.5 Required query and derived-state support

Implement:

- entity find by typed fields;
- rich query modes used by native skills;
- multi-hop neighbors with direction/type filters;
- semantic duplicate candidate search;
- purpose-driven context compilation;
- index rebuild;
- open-question rebuild;
- maturity/statistics;
- checkpoints for batch and resume;
- append-only log.

### 10.6 Workspace and ownership

Keep the human-facing workspace under a Solar-governed root such as:

```text
harness/artifacts/autosci/workspace/wiki/
```

Preserve source ownership boundaries and explicit mutation policies. Solar execution evidence stays under run/job artifact directories and must not pollute the human wiki.

### 10.7 Golden behavior tests

Create a small native-compatible fixture wiki and run equivalent operations against native AutoSci and OpenSolar implementation. Compare normalized outputs for:

- init;
- add edge/citation;
- duplicate detection;
- legal/illegal transitions;
- context compilation;
- open questions;
- checkpoints;
- query/neighbors;
- dedup.

Document intentional differences.

---

## 11. Fifth priority: complete ideation and Gate 1

### 11.1 Independent generation

Native ideation uses independent perspectives. Implement two separately evidenced generation calls or workers:

```text
idea_generator_primary
idea_generator_independent
```

They must not share generated outputs before completion. Record model/provider, prompt hash, input context hash, and output artifact.

### 11.2 Merge, dedup, and anti-memory

A synthesis node must:

- merge candidates;
- detect duplicates;
- compare against existing ideas;
- compare against failed/rejected ideas;
- preserve rejected candidates and reasons;
- prevent silent regeneration of known failed ideas.

### 11.3 Novelty stack

Require explicit evidence for configured layers, for example:

- wiki comparison;
- live web/provider search;
- Semantic Scholar/DeepXiv or equivalent;
- independent reviewer opinion.

Unavailable providers must produce inconclusive layer evidence. Never replace them with fixture candidates in a real run.

### 11.4 Idea evaluation

Emit:

- novelty rationale;
- feasibility;
- expected contribution;
- resource estimate;
- risks;
- falsifiable hypothesis;
- evidence IDs;
- recommendation.

### 11.5 Gate 1

Present accepted candidates to the human gate. Persist the decision. Transition the selected idea to `in_progress`. Preserve rejected/failed candidates appropriately.

### 11.6 Pilot branch

When configured, instantiate:

```text
pilot design -> pilot run -> pilot evaluation
```

Pilot behavior must not be reduced to ordinary full experiment output with renamed fields.

---

## 12. Sixth priority: complete the experiment lifecycle

### 12.1 Design

The design node must produce:

- hypothesis and claim linkage;
- baseline and justified absence rules;
- variables/controls;
- datasets/model/hardware/framework;
- metrics and success criteria;
- run matrix;
- artifact plan;
- expected duration/resource budget;
- code/setup plan;
- failure and stop conditions;
- independent design review evidence.

Create or update a typed experiment entity with `planned` status through the wiki API.

### 12.2 Code/setup preparation and inspection

Separate code generation/modification from execution. Before run approval, require evidence for:

- files changed/generated;
- static inspection;
- command allowlist;
- dependency/environment lock;
- data access boundaries;
- expected output paths;
- cleanup/rollback.

### 12.3 Approved deployment

Support at least one fully audited bounded local executor before expanding remote execution.

The approval contract must bind:

- exact command or command digest;
- working directory;
- environment allowlist;
- input hashes;
- output paths;
- time/memory limits;
- network policy;
- approval reference.

Record stdout, stderr, exit code, process ID, and start time.

### 12.4 Asynchronous state

Long-running deployment must return a durable process/session record and set:

```text
experiment status: running
node state: waiting_for_external
job state: waiting_for_external
```

It must not fabricate a result or mark the node complete.

### 12.5 Status

`$exp-status` and `$research --resume` must inspect the durable deployment record. The status operator must distinguish:

```text
queued
running
completed-awaiting-collection
failed
lost
cancelled
unknown
```

### 12.6 Exactly-once collection

Collection must be idempotent. Use a collection identity and artifact hashes. Repeated collection should return the existing accepted evidence rather than duplicate or overwrite it silently.

### 12.7 Independent evaluation

Evaluation must consume collected artifacts, not backend self-report alone. Require:

- metrics;
- baseline comparison;
- logs;
- limitations;
- independent model/reviewer evidence where configured;
- four-path verdict: supported, partially supported, not supported, inconclusive.

### 12.8 State transitions and iteration

On accepted evaluation:

- transition experiment `running -> completed` or `abandoned`;
- transition idea `in_progress -> tested`;
- after final human/result decision, transition idea `tested -> validated | failed`;
- if inconclusive and iteration is approved, create a new bounded experiment attempt linked to the idea;
- enforce `max_iterations`.

### 12.9 Resume test

Terminate the orchestrator after deployment, restart it, poll, collect, evaluate, and finish. Prove completed earlier nodes were not rerun.

---

## 13. Seventh priority: complete publication and Gate 2

### 13.1 Result Gate 2

After experiment evaluation, require durable human selection:

```text
publish
iterate
stop_as_failed
stop_as_inconclusive
```

The decision must bind the accepted verdict and experiment evidence.

### 13.2 Paper plan

Build the plan from accepted idea/experiment/wiki graph state. Include:

- contribution claims;
- evidence map;
- section outline;
- related-work/citation plan;
- figure plan;
- table plan;
- limitations;
- venue constraints;
- independent review evidence.

### 13.3 Paper draft

Produce a real manuscript project, not only a generic report:

```text
paper/
  main.tex
  sections/
  figures/
  tables/
  references.bib
  build/
  evidence-index.json
```

Every empirical claim must reference accepted evidence. Unsupported claims must be absent or explicitly qualified.

### 13.4 Figures and tables

Generate figures/tables from experiment artifacts or document justified absence. Record source data and rendering commands.

### 13.5 Bibliography

Verify citation identifiers and BibTeX records. Reject unresolved or fabricated citations.

### 13.6 Review/refine loop

Use independent review evidence. Classify findings and apply bounded revisions. Rerun relevant gates after changes. Preserve before/after hashes and iteration history.

### 13.7 Compile

Use an allowlisted compiler in a bounded environment. Require:

- successful exit;
- actual PDF path;
- nonzero file size;
- positive page count;
- no unresolved references/citations;
- no fatal compile errors;
- submission checklist.

A supplied PDF is not accepted merely because it exists; it must be produced or explicitly imported and accepted with provenance.

### 13.8 Rebuttal and poster

After the core paper path is complete, close native behavior for:

- reviewer-comment atomization;
- evidence mapping;
- independent stress test;
- rich and formal rebuttal outputs;
- PaperX DAG;
- HTML poster;
- figure extraction;
- overflow validation;
- PNG rendering.

These may remain approval/provider gated but must have real approved execution tests before semantic parity is full.

---

## 14. Decompose the backend bridge safely

Do not perform an unreviewable big-bang rewrite. Extract one bounded domain at a time while retaining CLI compatibility.

Recommended structure:

```text
harness/plugins/autosci/
  bin/
    autosci_bridge.py          # CLI parser and dispatch only
    autosci_skill_shim.py      # UX parser/router only
  actions/
    knowledge.py
    analysis.py
    ideation.py
    experiments.py
    publication.py
    admin.py
  runtime/
    approvals.py
    evidence.py
    executors.py
    providers.py
    workspace.py
  omegawiki/
    loader.py
    schemas/
    graph.py
    lifecycle.py
    checkpoints.py
    context.py
  adapters/
  backends/
  tests/
```

Rules:

- action functions perform one bounded action;
- action functions do not invoke the next lifecycle action;
- scheduler state lives outside the plugin action implementation;
- provider/tool adapters return explicit evidence;
- all writes remain scope-checked;
- shared evidence and approval helpers are unit-tested;
- compatibility aliases are documented and temporary.

---

## 15. Update the declarative workflows

Revise `scientific_research_lifecycle_full_v1.json` and resume handling so they represent executable semantics.

Do not create a separate static resume workflow that merely omits nodes unless it is generated from state. Prefer one canonical workflow plus persisted per-node status and conditional scheduling.

At minimum add or represent:

```text
bootstrap_inspect
optional_init
optional_ingest
ideate_primary
ideate_independent
idea_merge
novelty_check
idea_review
human_gate_idea
experiment_design
experiment_design_review
experiment_prepare
experiment_deploy
external_wait
experiment_status
experiment_collect
experiment_evaluate
human_gate_result
iteration_decision
paper_plan
paper_draft
paper_review
paper_refine
paper_compile
publication_gate
memory_graph_finalize
workflow_evolution_proposal
```

Use branches/conditions, not an unconditional linear sequence.

Every node must have:

```text
id
logical_operator
required_capabilities
read_scope
write_scope
input artifact bindings
expected Evidence ABI
gate
acceptance conditions
depends_on / conditional dependencies
retry policy
resume policy
architecture policy
approval/external-wait policy where relevant
```

---

## 16. Tests you must add

### 16.1 Static consistency

- all 18 target capabilities in manifest/registry;
- all workflow operators have bindings;
- all physical candidates and hosts exist;
- all actions and gates exist;
- no stale pending conditions;
- no AutoSci semantic names in generic layers except allowed provenance/backend fields.

### 16.2 Lifecycle gate negatives

Test that runtime acceptance rejects:

- empty node results;
- missing gate results;
- wrong job ID;
- wrong node ID;
- missing artifact;
- invalid schema;
- hash mismatch;
- reused artifact from another job;
- unapproved side effect;
- inconclusive required node;
- bridge-owned full workflow.

### 16.3 Scheduler dispatch integration

Use the actual graph scheduler and operator runtime. Assert:

- node readiness;
- binding;
- host resolution;
- lease acquisition;
- envelope write;
- action execution;
- result recording;
- node gate;
- downstream readiness;
- parent gate.

Mock only external services, not the scheduler path itself.

### 16.4 Suspend/resume

Use a test executor that launches a bounded process and deliberately waits. Restart the orchestration process and resume from durable state.

### 16.5 OmegaWiki golden tests

Compare normalized behavior with native AutoSci for legal transitions, illegal transitions, graph writes, citations, dedup, checkpoints, context, and queries.

### 16.6 Real bounded local lifecycle

Create a tiny scientific task and repository where an experiment command can run quickly and safely. It must not be a precomputed result fixture. The command must generate metrics from actual execution.

### 16.7 Actual publication

Compile a minimal but real LaTeX manuscript using generated evidence and validate the PDF.

### 16.8 Failure and inconclusive cases

Prove:

- provider unavailable -> inconclusive, not synthetic success;
- experiment command failure -> failed with logs;
- result missing -> inconclusive;
- novelty evidence missing -> cannot pass idea gate;
- compile failure -> no publication success;
- rejected human gate -> downstream nodes do not run;
- illegal lifecycle transition -> rejected.

---

## 17. Required end-to-end acceptance scenarios

### Scenario A — Clean bounded local research lifecycle

Starting from an empty job-scoped workspace:

1. ingest one real local paper or structured source;
2. populate typed wiki entities/edges/citations;
3. generate and evaluate ideas with two independently evidenced generators;
4. obtain Gate 1 approval;
5. design a bounded experiment;
6. execute a real local command;
7. collect actual metrics;
8. evaluate and transition states;
9. obtain Gate 2 approval;
10. create plan and draft;
11. compile an actual PDF;
12. pass parent lifecycle gate;
13. update memory/graph/log;
14. emit a final job report.

### Scenario B — Suspend and resume

1. run through deployment;
2. enter `waiting_for_external`;
3. terminate orchestration process;
4. restart;
5. resume by job ID;
6. prove passed nodes were not rerun;
7. collect exactly once;
8. finish the lifecycle.

### Scenario C — Negative/inconclusive lifecycle

Run a case where the experiment evidence is insufficient. The lifecycle must produce an inconclusive verdict or bounded iteration request, not a supported claim or publication success.

### Scenario D — Gated utility operations

Run approved, audited examples of:

- edit;
- refine apply;
- reset dry-run and optionally approved reset in a disposable workspace;
- paper compile;
- poster render if renderer available;
- daily-arxiv provider/SMTP only if credentials and explicit approval are provided.

Do not block the core local lifecycle on unavailable external credentials. Record those routes as provider-gated with honest proof levels.

---

## 18. Expected command surface after implementation

Adapt to existing CLI conventions, but provide equivalent usable commands. Example target:

```bash
# Compile and start a new lifecycle.
./harness/solar-harness.sh '$research' \
  --topic "<topic>" \
  --paper "<path>" \
  --job-id "<job-id>" \
  --execution-mode bounded-local \
  --max-iterations 2

# Inspect durable state.
./harness/solar-harness.sh '$exp-status' --pipeline "<job-id>"

# Record a human idea decision.
python3 harness/tools/scientific_workflow.py approve \
  --job-id "<job-id>" \
  --gate idea \
  --accept "<idea-id>" \
  --approval-ref "<ref>"

# Resume after approval or external completion.
python3 harness/tools/scientific_workflow.py resume --job-id "<job-id>"

# Validate runtime acceptance.
python3 harness/evaluators/scientific/lifecycle_runtime_gate.py \
  "harness/artifacts/scientific/<job-id>/lifecycle_summary.json"

# Audit registry and parity truth.
python3 harness/tools/audit_scientific_runtime_bindings.py --strict
python3 harness/plugins/autosci/bin/autosci_parity_bridge.py \
  inventory --out /tmp/autosci-parity-current.json
```

Do not invent commands without implementing and testing them.

---

## 19. Documentation and phase logs

Create a dedicated continuation log and a real Phase 15 log:

```text
docs/integrations/autosci/phase15-progress-log.md
docs/integrations/autosci/native-lifecycle-continuation-log.md
```

Every implementation step must record:

- objective;
- files changed;
- architecture decision;
- commands run;
- exit codes;
- test counts;
- artifact paths;
- hashes where relevant;
- current semantic parity/execution policy/proof level;
- remaining blockers;
- whether results are fixture, mocked-provider, bounded real stage, recoverable lifecycle, or full end-to-end.

Never write “complete” without naming the acceptance scenario that passed.

Update:

- workflow map;
- parity matrix;
- plugin README;
- manifest;
- route config;
- operator binding config;
- generated inventory;
- generated skill wrappers only if route metadata changes.

---

## 20. Repository hygiene

Do not commit local runtime state unless it is an intentional test fixture.

Inspect and clean or ignore as appropriate:

```text
.DS_Store
*.pid
coordinator/watchdog state
local inbox/outbox state
generated run directories
local provider outputs
temporary PDFs/TeX builds
local caches
backups
```

Preserve small, deterministic fixtures under explicit test directories. Do not delete historical evidence the user may need without recording and obtaining approval.

---

## 21. Required incremental PR slicing

Do not combine all work into one opaque patch. Prefer:

```text
PR 1: truth model, parity regeneration, contract/runtime gate split
PR 2: registry/host/binding/manifest repair
PR 3: workflow request/compiler and scheduler-native $research skeleton
PR 4: durable lifecycle state, human gates, wait/resume
PR 5: OmegaWiki schema/lifecycle/graph/checkpoint parity
PR 6: independent ideation, novelty, Gate 1, pilot path
PR 7: experiment deploy/status/collect/eval/iteration
PR 8: publication plan/draft/review/compile and Gate 2
PR 9: remaining utility/admin command parity
PR 10: full acceptance scenarios, inventory, docs, cleanup
```

Each PR must leave a human-verifiable artifact, deterministic test, or real bounded runtime result.

---

## 22. Prohibited shortcuts

Do not do any of the following:

- mark routes full because all 28 have wrappers;
- mark routes full because a schema validates;
- use fixture data in a non-smoke run;
- silently fall back to fixture data when a provider fails;
- pre-create wiki files and call that a completed stage;
- accept supplied evidence without job/provenance/hash validation;
- infer stage completion from global page counts;
- make the lifecycle gate pass by setting `lifecycle_status: passed` alone;
- change tests to expect the current false-positive behavior;
- call native AutoSci `/research` as a black box;
- move AutoSci workflow semantics into Solar core without a reusable abstraction;
- add one giant `ScientificResearchRunner` physical operator;
- let `ScientificWorkflowEvolver` act as the research workflow executor;
- bypass physical operator/host policies through the shim;
- execute unapproved shell, remote, SMTP, browser, destructive, or secret-writing actions;
- claim a PDF was compiled because a file named `.pdf` was supplied;
- claim an experiment ran because a result JSON was supplied;
- silently apply workflow-evolution proposals;
- overwrite user changes or native AutoSci source;
- hide failures or unresolved dependencies in logs.

---

## 23. Completion criteria

Do not declare the migration complete until every item below is proven:

```text
[ ] Current route inventory and committed artifact agree.
[ ] Semantic parity, execution policy, and proof level are separate.
[ ] All 18 target capabilities are in capsules, registry, and plugin manifest.
[ ] Every full/resume workflow logical operator has an executable binding.
[ ] Every candidate physical operator has a valid registered host.
[ ] $research submits a TaskGraph to graph_scheduler.
[ ] autosci_bridge owns no end-to-end stage sequence.
[ ] Every node dispatch goes through operator_runtime and records a lease/result.
[ ] Lifecycle runtime gate rejects empty/missing result maps.
[ ] All accepted artifacts are job/node scoped and hash-bound.
[ ] Human Gate 1 and Gate 2 are durable.
[ ] External wait/resume survives process restart.
[ ] Native idea and experiment lifecycle transitions are enforced.
[ ] Typed graph and citation invariants are enforced.
[ ] Checkpoints and context compilation exist.
[ ] Independent ideation/review evidence exists.
[ ] Failed-idea anti-memory is preserved.
[ ] A real bounded local experiment executes and is collected/evaluated.
[ ] Collection is idempotent.
[ ] Iteration is bounded and stateful.
[ ] A real manuscript is drafted and an actual PDF is compiled/validated.
[ ] A clean full lifecycle reaches the parent gate without fixture fallback.
[ ] A suspend/resume lifecycle completes without rerunning passed nodes.
[ ] A negative lifecycle remains failed/inconclusive and does not overclaim.
[ ] Final parity inventory contains no unsupported full status.
[ ] Intermediate artifacts are human-inspectable.
[ ] AutoSci remains a bounded backend implementation, not workflow owner.
```

---

## 24. Required response format after each implementation slice

Return exactly these sections:

### A. Baseline and scope

- OpenSolar SHA/branch
- AutoSci SHA/branch
- slice objective
- files intentionally in scope
- files intentionally out of scope

### B. Findings before change

- concrete defects
- source paths and line/function references
- why each defect violates Solar or native AutoSci semantics

### C. Changes made

For each file:

```text
path
purpose
behavioral change
architecture impact
compatibility impact
```

### D. Commands and results

Provide exact commands, exit codes, and concise outputs. Distinguish:

```text
static validation
unit test
fixture/smoke
mocked provider
real bounded stage
scheduler integration
suspend/resume
end-to-end
```

### E. Artifacts and evidence

List:

- artifact path;
- schema;
- job/node IDs;
- hash;
- gate verdict;
- whether it is fixture or real.

### F. Parity status changes

Use:

```text
skill
previous semantic parity
new semantic parity
execution policy
proof level
proof refs
remaining requirements
```

### G. Known limitations and next slice

Be explicit. Never imply that future work is already complete.

---

## 25. Immediate first implementation slice

Begin with the following bounded slice; do not jump directly to publication or more wrappers.

### Slice objective

Create a trustworthy baseline and make the declarative scientific graph schedulable without executing the full external lifecycle yet.

### Required deliverables

1. `continuation-baseline-2026-06-25.md`
2. regenerated current parity inventory or removal policy
3. three-axis parity schema/config fields
4. contract/runtime lifecycle gate split
5. negative runtime-gate tests
6. scientific registry audit tool
7. valid local backend host registration
8. complete logical bindings for all nodes in the current full graph
9. corrected physical operator metadata/policies sufficient for bounded local actions
10. reconciled plugin manifest with all eighteen capabilities
11. one actual scheduler-dispatched bounded node, not a direct bridge call
12. a progress log with exact evidence

### First-slice acceptance

Run a small `ScientificPaperIngestor` or other safe local node through:

```text
instantiated TaskGraph
-> graph scheduler
-> logical binding
-> physical operator
-> registered local host
-> operator runtime
-> bounded bridge action
-> Evidence ABI
-> deterministic node gate
-> scheduler result
```

The acceptance artifact must include the selected operator/host and a recorded lease/result. A direct invocation of `autosci_bridge.py` does not satisfy this slice.

After this slice passes, proceed to the scheduler-native `$research` lifecycle skeleton and durable wait/resume state.

---

## Source-integrity record

This master file was assembled from the three complete source documents below. Their original hashes are recorded for provenance. The coding-agent prompt was adapted only to replace references to separate attachments with references to Parts I and II of this same document; the substantive implementation instructions were retained.

| Embedded source | SHA-256 |
|---|---|
| `autosci_solar_gap_analysis_2026-06-25.md` | `fd06a275074cd94b80b4d70a411db89598fe53d6c4d9502dff627348b11b6e28` |
| `autosci_solar_native_implementation_plan(1).md` | `3fd380d97a681e5854a6d5434fa33382ea0ab288f6cab697f2e71aaa3598915d` |
| `autosci_migration_coding_agent_prompt_2026-06-25.md` | `cb79cfb3a2dda60750ec8a0b5557c9c1a77539b1ee650b91398bd788a9dffa0e` |

**End of master handoff.**
