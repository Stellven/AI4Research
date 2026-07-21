# AutoSci Workflow Map for Solar-Native Research Runtime

Status: Phase 0 inventory only. This document does not define runtime behavior.

## Scope

This map decomposes the locally inspected AutoSci `main` branch plus the
`upstream/paper` / `arxiv-v1` research snapshot into Solar-native research
workflow semantics. AutoSci remains a future backend implementation package.
Solar owns the task graph, logical operators, capability capsules, Evidence ABI,
gates, manuals, dispatch templates, and memory policy.

Source inspection used:

- AutoSci `README.md` on local branch `main`
- AutoSci skill specs under `.agents/skills/*/SKILL.md`
- AutoSci schema/policy files under `runtime/schema/` and `runtime/policy/`
- AutoSci tool entry points under `tools/`
- AutoSci `upstream/paper` and local tag `arxiv-v1` file trees, README, i18n
  skill specs, `scidag/`, `docs/scievolve.md`, and `runtime/schema/scievolve.yaml`
- OpenSolar README, architecture map, Harness plugin loader, operator runtime,
  logical/physical operator registries, and capsule registry/schema

Validation notes:

- The global `solar-harness` command and `$HOME/.solar/bin/solar-harness` were
  not installed in this shell. The repo-local command did work with an explicit
  `HARNESS_DIR=<OpenSolar>/harness`; it returned Solar unified context with a
  degraded Mirage source.
- AutoSci dependencies were installed inside the AutoSci repo at `.venv/` using
  an in-repo pip cache and temp dir. Static smoke checks passed for
  `research_wiki.py --help`, `discover.py --help`, `init_discovery.py --help`,
  and `daily_arxiv.py --help`.
- The local `upstream/paper` branch and `arxiv-v1` tag differ only by README
  status text in the inspected refs; functional files were treated as the same
  research snapshot.

## Architecture Boundary

```text
TaskGraph node
  -> Solar logical operator
  -> Solar capability capsule
  -> Solar physical operator binding
  -> AutoSci backend implementation package
  -> command/action wrapper
  -> Solar Evidence ABI artifact
  -> Solar evaluator gate or human-verifiable test
```

Do not implement a single `AutoSciRunner`. AutoSci skills such as `/research`
are useful as an inventory of stages, but Solar must represent those stages as
native nodes with typed evidence at every boundary.

## AutoSci System Summary

AutoSci `main` is organized as a skill-driven research assistant around an
OmegaWiki-style durable research memory. It uses:

- `wiki/` as the typed knowledge base for papers, concepts, topics, people,
  ideas, methods, experiments, outputs, foundations, and derived graph files.
- `raw/` as user-owned source input and generated discovery/preparation area.
- `tools/research_wiki.py` as the wiki engine for entity metadata, graph
  edges, citations, lifecycle transitions, logs, checkpoints, statistics, and
  maturity.
- `tools/init_discovery.py`, `tools/discover.py`, `tools/daily_arxiv.py`,
  `tools/fetch_s2.py`, `tools/fetch_deepxiv.py`, and related helpers for
  literature discovery and paper preparation.
- `experiments/`, `results/`, `logs/`, and `paper/` as runtime and publication
  artifact areas.
- On `paper` / `arxiv-v1`, `scidag/` adds reusable research-operator DAGs for
  ideation, experiment design, and paper planning, while SciEvolve adds
  proposal-first memory/workflow/orchestration evolution through `/dream`,
  `/forge`, and `/morph`.

AutoSci skills can be grouped into these workflow families:

1. Setup and wiki foundation
2. Paper discovery and ingestion
3. Memory and graph maintenance
4. Idea generation and novelty/review
5. Pilot and full experiment lifecycle
6. Verdict and evidence-based idea status updates
7. Report, paper, poster, and rebuttal production
8. Full lifecycle orchestration and resume/recovery
9. Workflow improvement and health checking
10. Wiki question answering, manual edits, and destructive reset utilities
11. SciDAG augmentation and SciEvolve self-evolution from `paper` / `arxiv-v1`

## Solar-Native Decomposition

The following stages should become Solar-native nodes. AutoSci-specific scripts
or parsers may implement some nodes, but the semantics stay in Solar.

| Stage | AutoSci source | Solar logical operator | Solar capsule | Evidence ABI |
|---|---|---|---|---|
| Source and wiki setup | `/setup`, `/init`, `research_wiki.py init` | `ScientificMemoryUpdater` | `cap.research-memory-update` | `research_memory_update.v1` |
| Foundation seeding | `/prefill`, foundations catalog | `ScientificMemoryUpdater` | `cap.research-memory-update` | `research_memory_update.v1` |
| Literature discovery | `/discover`, `/daily-arxiv`, `discover.py`, `daily_arxiv.py` | `ScientificLiteratureDiscoverer` | `cap.research-literature-discover` | `literature_discovery.v1` |
| Paper preparation and ingestion | `/ingest`, `/init`, `prepare_paper_source.py`, `init_discovery.py` | `ScientificPaperIngestor` | `cap.research-paper-ingest` | `research_paper.v1` |
| Paper analysis | `/ingest`, `runtime/schema/entities.yaml` paper fields | `ScientificPaperAnalyzer` | `cap.research-paper-analyze` | `research_paper.v1` |
| Method extraction | `/ingest`, method entity creation | `ScientificMethodExtractor` | `cap.research-method-extract` | `research_method.v1` |
| Memory update | `/ingest`, `/edit`, `/check --fix`, `research_wiki.py set-meta` | `ScientificMemoryUpdater` | `cap.research-memory-update` | `research_memory_update.v1` |
| Graph update | `/ingest`, `/ideate`, `/exp-design`, `/exp-eval`, `research_wiki.py add-edge` | `ScientificGraphUpdater` | `cap.research-graph-update` | `research_graph_update.v1` |
| Claim extraction | derived from paper methods, results, hypotheses, idea hypotheses | `ScientificClaimExtractor` | `cap.research-claim-extract` | `research_claims.v1` |
| Code evidence mapping | `/exp-run`, experiment code generation, `methods.code_repo`, paper code URLs | `ScientificCodeEvidenceMapper` | `cap.research-code-evidence-map` | `code_evidence_map.v1` |
| Idea generation | `/ideate` | `ScientificIdeaGenerator` | `cap.research-idea-generate` | `idea_candidate.v1` |
| Idea evaluation | `/novelty`, `/review`, `/ideate` validation | `ScientificIdeaEvaluator` | `cap.research-idea-evaluate` | `idea_evaluation.v1` |
| Experiment design | `/exp-design`, `/ideate` pilot spec | `ScientificExperimentDesigner` | `cap.research-experiment-design` | `experiment_plan.v1` |
| Experiment run and collect | `/exp-run`, `/exp-pilot-run` | `ScientificExperimentRunner` | `cap.research-experiment-run` | `experiment_result.v1` |
| Experiment monitor | `/exp-status`, `/exp-run --collect` | `ScientificExperimentMonitor` | `cap.research-experiment-monitor` | `experiment_status.v1` |
| Claim verdict | `/exp-eval`, `/exp-pilot-eval` | `ScientificClaimVerifier` | `cap.research-claim-verify` | `claim_verdict.v1` |
| Report planning | `/survey`, `/paper-plan` | `ScientificReportPlanner` | `cap.research-report-plan` | `scientific_report.v1` |
| Report drafting | `/paper-draft`, `/paper-compile` | `ScientificReportDrafter` | `cap.research-report-draft` | `scientific_report.v1` |
| Publication bundle | `/poster`, `/rebuttal`, compiled paper artifacts | `ScientificPublicationProducer` | `cap.research-publication-produce` | `publication_bundle.v1` |
| Lifecycle orchestration | `/research` | TaskGraph template, not a backend runner | research workflow templates | lifecycle evidence ledger |
| Workflow improvement | `/check`, `/refine`, `/research` iteration, failed idea memory | `ScientificWorkflowEvolver` | `cap.research-workflow-evolve` | `workflow_evolution.v1` |
| Wiki question answering | `/ask` | `ScientificKnowledgeQuerier` | `cap.research-knowledge-query` support-only | `scientific_report.v1` or `research_memory_update.v1` only when crystallized |
| Manual source/content edit | `/edit` | `ScientificMemoryUpdater` | `cap.research-memory-update` | `research_memory_update.v1` |
| Destructive project reset | `/reset`, `reset_wiki.py` | maintenance gate, excluded from research capability coverage | no research capsule | reset plan/report, not acceptance evidence |
| SciDAG augmented stages | `/ideate-dag`, `/exp-design-dag`, `/paper-plan-dag`, `scidag/` | existing idea/design/report logical operators | existing research capsules | existing stage ABIs |
| SciEvolve loops | `/dream`, `/forge`, `/morph`, `runtime/schema/scievolve.yaml` | `ScientificWorkflowEvolver` | `cap.research-workflow-evolve` | `workflow_evolution.v1` |

## Stage Notes

### 1. Knowledge Foundation

AutoSci creates or updates a wiki with paper, concept, topic, person, method,
idea, experiment, foundation, summary, and output pages. Solar should not copy
OmegaWiki as a control plane. Instead, it should represent memory changes as
typed `research_memory_update.v1` evidence and graph changes as
`research_graph_update.v1` evidence. AutoSci wiki conversion code belongs under
the backend adapter package.

Human test:

```text
Given an AutoSci wiki diff, a reviewer can identify which entities changed,
which graph edges changed, and which Solar evidence artifacts justify the
update without reading AutoSci internals.
```

### 2. Literature Discovery

AutoSci has two discovery modes:

- Deliberate next-read discovery through `/discover`.
- Fresh-paper monitoring through `/daily-arxiv`.

Solar should represent both as `ScientificLiteratureDiscoverer` with different
task inputs and the same `literature_discovery.v1` output contract. Discovery
must not mutate research memory unless a later ingestion node accepts a paper.

Human test:

```text
Discovery output is a ranked candidate list with sources, scoring rationale,
dedup state, degraded-source warnings, and no hidden ingestion side effect.
```

### 3. Paper Ingestion and Analysis

AutoSci `/ingest` resolves sources, enriches with Semantic Scholar and DeepXiv,
writes paper pages, lifts concepts/methods/people, adds graph/citation edges,
and optionally invokes `/discover`. Solar should split these responsibilities:

- `ScientificPaperIngestor`: resolves and normalizes the paper artifact.
- `ScientificPaperAnalyzer`: extracts metadata, TLDR, datasets, contribution
  types, limitations, and result summaries.
- `ScientificMethodExtractor`: lifts named reusable methods.
- `ScientificGraphUpdater`: records paper-concept, paper-paper, and citation
  relationships.

Human test:

```text
The reviewer can inspect a normalized `research_paper.v1` artifact, a
`research_method.v1` artifact, and a `research_graph_update.v1` artifact before
any memory store is mutated.
```

### 4. Claim and Method Semantics

AutoSci does not expose a standalone claim extraction skill in the inspected
`main` branch. Claims are implicit in paper hypotheses, idea hypotheses,
experiment hypotheses, method sections, results, and verdicts. Solar should
make them explicit through `ScientificClaimExtractor` and `research_claims.v1`.

Human test:

```text
No claim is marked verified at extraction time. Each claim has a source anchor,
testability status, and links to paper/method/evidence artifacts.
```

### 5. Ideation and Evaluation

AutoSci `/ideate` performs a five-phase pipeline: landscape scan, dual-model
brainstorm, first-pass filter and deep validation, wiki write, and optional
pilot experiments. Solar should split this into:

- `ScientificIdeaGenerator` for candidate generation.
- `ScientificIdeaEvaluator` for novelty, feasibility, wiki gap alignment, and
  review evidence.
- `ScientificExperimentDesigner` and `ScientificExperimentRunner` for pilot
  work, never hidden inside the idea generator.

Human test:

```text
An idea has a candidate artifact, an evaluation artifact, and optional pilot
artifacts. Failed ideas are recorded as anti-repetition memory with explicit
failure reasons.
```

### 6. Experiment Lifecycle

AutoSci separates design, deployment, status monitoring, collection, and
verdict:

- `/exp-design` creates experiment plans and wiki pages.
- `/exp-run` prepares code, requires manual inspection before deploy, deploys,
  monitors, and collects.
- `/exp-status` reports running/anomaly/completed-pending-collect state.
- `/exp-eval` turns completed results into idea support/refutation verdicts.

Solar should preserve this separation as native nodes and require bounded mode
or explicit human approval before real external execution.

Human test:

```text
Experiment execution can run in fixture, dry-run, bounded local sandbox, known
safe benchmark, or explicitly approved external mode. Each run emits
`experiment_status.v1` and `experiment_result.v1` before any verdict gate runs.
```

### 7. Report and Publication

AutoSci maps idea and experiment evidence to paper plans, LaTeX drafts, compile
checks, posters, surveys, and rebuttals. Solar should distinguish:

- `ScientificReportPlanner`: evidence map and report/paper outline.
- `ScientificReportDrafter`: report sections and compiled report evidence.
- `ScientificPublicationProducer`: paper PDF, poster HTML/PNG, rebuttal files,
  and publication bundle metadata.

Human test:

```text
Report sections link to typed evidence artifacts. Unsupported or inconclusive
claims are not presented as successful findings.
```

### 8. Full Lifecycle and Resume

AutoSci `/research` is an orchestrator with stage progress persisted in
`wiki/outputs/pipeline-progress.md`. In Solar, this becomes a TaskGraph
template family. It should not become a physical operator or backend action
that owns the whole workflow.

Human test:

```text
A full lifecycle TaskGraph lists each research node, dependency, read/write
scope, required capability, evidence output, and gate. It does not contain a
single "call AutoSci research" node.
```

### 9. Workflow Evolution

AutoSci uses `/check`, `/refine`, failed idea memory, Review LLM feedback, and
pipeline iteration to improve research workflow quality. Solar should represent
this as `ScientificWorkflowEvolver`, producing `workflow_evolution.v1` with
recommended changes. It must not silently mutate protected core runtime.

The `paper` / `arxiv-v1` snapshot makes this more explicit through SciEvolve:
`/dream` evolves memory metadata and context ranking, `/forge` proposes or
applies bounded skill protocol patches, and `/morph` proposes or applies bounded
SciDAG template/operator-prompt patches. In Solar, these remain evidence-gated
workflow-evolution nodes. They must not become permission to mutate Solar core
runtime or generic repository files.

Human test:

```text
Evolution output cites failed nodes, gate rejection reasons, weak schemas,
ambiguous manuals, or routing issues, and separates proposed edits from
accepted changes.
```

### 10. Support Utilities

AutoSci `/ask`, `/edit`, and `/reset` are not hidden inside broader memory
updates:

- `/ask` is a wiki-grounded read path. Without crystallization, it maps to a
  support query node that produces a cited answer report. With explicit
  crystallization, the write-back portion becomes `ScientificMemoryUpdater` and
  must emit `research_memory_update.v1`.
- `/edit` is a manual user-directed update path. It maps directly to
  `ScientificMemoryUpdater`; raw-source addition, deletion, and wiki edits must
  be reported as explicit memory update evidence.
- `/reset` is destructive maintenance, not a research capability. It should
  stay outside native research TaskGraphs unless a human explicitly invokes a
  maintenance gate. The dry-run deletion plan is review evidence; it is not a
  successful research workflow artifact.

Human test:

```text
A reviewer can tell whether the action was read-only answer synthesis, explicit
memory write-back, manual edit, or destructive reset before any backend command
is allowed to mutate state.
```

### 11. SciDAG Augmentation

The `paper` / `arxiv-v1` snapshot adds DAG-augmented variants for ideation,
experiment design, and paper planning. Solar should not import SciDAG as a
separate workflow owner. It should decompose each DAG operator into Solar-owned
logical nodes or treat the AutoSci SciDAG call as a backend implementation for a
single existing native node only when the node still emits the same typed
Evidence ABI as its non-DAG counterpart.

Human test:

```text
The graph shows native Solar stage semantics and typed evidence. It does not
contain a black-box "run SciDAG" replacement for ideation, experiment design, or
paper planning.
```

## Open Questions

- AutoSci `main` lacks a first-class claim extraction command. Solar should
  define one generically and let the AutoSci adapter derive claims from papers,
  ideas, methods, and experiment hypotheses.
- AutoSci skills rely on Claude/Review LLM interaction. Solar gates should use
  deterministic evaluators for pass/fail/inconclusive and record model outputs
  as evidence, not as final acceptance.
- Later phases should decide whether the first adapter fixtures target AutoSci
  `main`, `arxiv-v1`, or both. The Phase 0 inventory now includes both, but
  adapter compatibility should be explicit.
- Runtime adapter phases should provide fixture-mode smoke tests that do not
  require external APIs, browsers, or GPU.
