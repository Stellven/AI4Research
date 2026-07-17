# AutoSci → Solar-Native Migration Gap Analysis

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

