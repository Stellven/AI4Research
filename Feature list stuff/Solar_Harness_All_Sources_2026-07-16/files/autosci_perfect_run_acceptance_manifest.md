# AutoSci Perfect-Run Output & Acceptance Manifest

**Purpose:** Reference checklist for comparing a migrated AutoSci implementation with the original AutoSci `main` branch.

## Definition of a “perfect run”

A perfect run means:

- setup succeeds;
- the research wiki is initialized and structurally valid;
- at least one idea survives novelty/review screening and passes pilot screening;
- a full experiment suite is created;
- all required experiments move `planned → running → completed`;
- at least one main experiment has `outcome: succeeded`;
- the linked idea moves `proposed → in_progress → tested → validated`;
- a paper plan, LaTeX draft, and compiled PDF are generated;
- no unresolved compilation blockers remain;
- optional poster and rebuttal artifacts can also be generated;
- every stage is traceable through persistent files, state transitions, and `wiki/log.md`.

For deterministic migration testing, use one fixed local paper, disable external discovery during initialization, and run stages manually before testing the `/research` orchestrator.

---

# A. Canonical deterministic command sequence

```bash
# Shell setup
chmod +x setup.sh
./setup.sh --lang en

# Start the agent runtime
claude
```

Inside AutoSci:

```text
/setup

/init "verified inference-time agent skill synthesis" --no-introduction

/check
/visualize --all

/ideate "reduce held-out regressions in verified agent-skill synthesis" --max-ideas 3
```

If the migrated orchestrator exposes the internal idea-verification stages separately:

```text
/novelty <idea-slug> --write
/review <idea-slug> --difficulty hard --focus method
/exp-pilot-run <idea-slug> --env local
/exp-pilot-eval <idea-slug>
```

Then:

```text
/exp-design <idea-slug>

/exp-run <experiment-slug> --review --env local
/exp-status
/exp-run <experiment-slug> --collect
/exp-eval <experiment-slug>
```

Repeat deploy, collect, and evaluate for every required experiment block.

Writing:

```text
/paper-plan <validated-idea-slug> --venue ICLR
/survey <validated-idea-slug> --format latex
/paper-draft wiki/outputs/<paper-plan-file>.md --review
/refine paper/main.tex --max-rounds 3 --target-score 8 --focus writing
/paper-compile paper/ --fix
```

Optional lifecycle completion:

```text
/poster paper/ --review --anonymous --no-logos
/rebuttal raw/reviews/test-review.md --paper-slug <paper-slug> --venue ICLR --stress-test
```

---

# B. Integrated `/research` command sequence

Use this only after all component capabilities pass individually.

```text
/research "reduce held-out regressions in verified agent-skill synthesis" --venue ICLR
```

After experiments are deployed:

```text
/exp-status --pipeline <pipeline-slug>
```

When sessions have finished:

```text
/research --start-from stage3-collect
```

A completed integrated run must leave:

```text
wiki/outputs/pipeline-progress.md
wiki/outputs/PIPELINE_REPORT.md
```

with the pipeline status marked completed.

---

# C. Expected final directory structure

```text
AutoSci/
├── .env
├── .venv/
├── .claude/
│   ├── settings.local.json
│   └── skills/
│
├── raw/
│   ├── papers/
│   │   └── SkillGen.pdf
│   ├── notes/
│   ├── web/
│   ├── tmp/
│   │   └── <prepared-local-source>.tex
│   └── discovered/
│       └── <externally-discovered-sources>/
│
├── .checkpoints/
│   ├── init-pdf-titles.json
│   ├── init-prepare.json
│   ├── init-plan.json
│   ├── init-sources.json
│   └── init-*.json
│
├── wiki/
│   ├── index.md
│   ├── log.md
│   ├── papers/
│   │   └── <paper-slug>.md
│   ├── concepts/
│   │   └── <concept-slug>.md
│   ├── methods/
│   │   └── <method-slug>.md
│   ├── topics/
│   │   └── <topic-slug>.md
│   ├── people/
│   │   └── <person-slug>.md
│   ├── ideas/
│   │   ├── <selected-idea-slug>.md
│   │   └── <filtered-idea-slug>.md
│   ├── experiments/
│   │   └── <experiment-slug>.md
│   ├── Summary/
│   │   └── <area-slug>.md
│   ├── foundations/
│   │   └── <foundation-slug>.md
│   ├── graph/
│   │   ├── edges.jsonl
│   │   ├── citations.jsonl
│   │   ├── context_brief.md
│   │   └── open_questions.md
│   ├── .obsidian/
│   │   ├── graph.json
│   │   └── app.json
│   ├── canvases/
│   │   ├── knowledge-map.canvas
│   │   ├── idea-evidence.canvas
│   │   └── focus-<node-id>.canvas
│   └── outputs/
│       ├── lint-report-<date>.md
│       ├── pipeline-progress.md
│       ├── PIPELINE_REPORT.md
│       ├── paper-plan-<slug>-<date>.md
│       ├── related-work-<slug>-<date>.md
│       ├── rebuttal-<slug>.md
│       └── rebuttal-<slug>.txt
│
├── experiments/
│   ├── pilot/
│   │   ├── <idea-slug>.yaml
│   │   ├── <idea-slug>/
│   │   │   └── report.md
│   │   └── code/
│   │       └── <idea-slug>/
│   │           ├── train.py
│   │           ├── config.yaml
│   │           ├── run.sh
│   │           ├── requirements.txt
│   │           ├── pilot.log
│   │           └── results/
│   │               └── seed_<N>.json
│   ├── designs/
│   │   └── <idea-slug>-master.md
│   └── code/
│       └── <experiment-slug>/
│           ├── train.py
│           ├── config.yaml
│           ├── run.sh
│           ├── requirements.txt
│           ├── data_loader.py        # when needed
│           └── utils.py              # when needed
│
├── logs/
│   └── exp-<experiment-slug>.log
│
├── results/
│   └── <experiment-slug>/
│       └── seed_<N>.json
│
├── checkpoints/
│   └── <experiment-slug>/
│
├── paper/
│   ├── main.tex
│   ├── main.pdf
│   ├── math_commands.tex
│   ├── references.bib
│   ├── sections/
│   │   ├── introduction.tex
│   │   ├── related_work.tex
│   │   ├── method.tex
│   │   ├── experiments.tex
│   │   ├── conclusion.tex
│   │   └── appendix.tex             # when applicable
│   ├── figures/
│   │   ├── <figure>.pdf
│   │   └── plot_<figure>.py         # when plots are generated
│   └── tables/
│       └── <table>.tex              # when needed
│
└── poster/
    ├── dag.json
    ├── outline.html
    ├── poster.html
    ├── poster.png
    └── images/
```

Some files are conditional. A migrated implementation is comparable when it preserves the same semantic artifacts and lifecycle states even if it uses different internal IDs or directories.

---

# D. Stage-by-stage output contract

## 0. Setup

### Commands

```text
./setup.sh --lang en
/setup
```

### Persistent outputs

```text
.venv/
.env
.claude/settings.local.json
.claude/skills/
CLAUDE.md
```

### Perfect-run checks

- dependencies installed;
- runtime can locate all AutoSci capabilities;
- required API configuration is accepted;
- no fatal setup errors.

---

## 1. Wiki initialization and ingestion

### Command

```text
/init "<topic>" --no-introduction
```

### Persistent outputs

```text
.checkpoints/init-*.json
raw/tmp/*
wiki/index.md
wiki/log.md
wiki/papers/*.md
wiki/concepts/*.md
wiki/methods/*.md
wiki/topics/*.md
wiki/people/*.md             # when importance rules create them
wiki/Summary/*.md
wiki/graph/edges.jsonl
wiki/graph/citations.jsonl
wiki/graph/context_brief.md
wiki/graph/open_questions.md
```

### Expected terminal report

- local papers ingested;
- discovered papers ingested, if discovery enabled;
- pages created and updated;
- failed or skipped papers;
- visualization refresh status.

### Perfect-run checks

- every input paper has exactly one paper page;
- re-running ingestion does not create duplicates;
- paper frontmatter and required body sections exist;
- graph edges contain valid endpoints and evidence;
- `wiki/index.md` lists all created entities.

---

## 2. Wiki health

### Command

```text
/check
```

Optional:

```text
/check --fix
```

### Outputs

```text
terminal lint report
wiki/outputs/lint-report-<date>.md     # optional persisted report
wiki/log.md
```

### Perfect-run checks

- zero red/blocking issues;
- no broken links;
- no missing required fields;
- no invalid lifecycle values;
- no dangling graph edges;
- reverse links are consistent.

---

## 3. Visualization

### Command

```text
/visualize --all
```

### Outputs

```text
wiki/.obsidian/graph.json
wiki/.obsidian/app.json
wiki/canvases/knowledge-map.canvas
wiki/canvases/idea-evidence.canvas
```

Optional focused output:

```text
/visualize --focus ideas/<idea-slug> --depth 2
```

produces:

```text
wiki/canvases/focus-<node-id>.canvas
```

---

## 4. Idea generation

### Command

```text
/ideate "<direction>" --max-ideas 3
```

### Persistent outputs

```text
wiki/ideas/<top-idea>.md
wiki/ideas/<filtered-idea>.md
wiki/graph/edges.jsonl
wiki/graph/context_brief.md
wiki/graph/open_questions.md
wiki/log.md
```

### Expected terminal output

```text
IDEA_REPORT
```

containing:

- landscape-search summary;
- number of generated candidates;
- number surviving filtering;
- ranked ideas;
- novelty and review scores;
- filtered ideas and explicit reasons;
- pilot result when run;
- suggested next actions.

### Perfect-run state

Selected idea:

```yaml
status: proposed
novelty_score: 3-5
priority: 1-5
pilot_result: "pass — ..."
failure_reason: ""
linked_experiments: []
```

Filtered ideas:

```yaml
status: failed
failure_reason: "[filter] <specific reason>"
priority: 1
```

Required graph relations:

```text
idea --addresses_gap--> concept/topic
idea --inspired_by--> paper/method/concept
```

---

## 5. Novelty verification

### Command

```text
/novelty <idea-slug> --write
```

### Outputs

```text
terminal Novelty Report
wiki/ideas/<idea-slug>.md        # novelty_score updated
wiki/log.md
```

### Perfect-run report fields

- score 1–5;
- 3–5 closest prior works;
- differences from each;
- independent reviewer assessment;
- anti-repetition check;
- proceed / modify / abandon recommendation.

---

## 6. Independent review

### Command

```text
/review <idea-slug> --difficulty hard --focus method
```

### Output

```text
terminal Review Report
```

### Perfect-run report fields

- score 1–10;
- verdict;
- strengths;
- weaknesses by severity;
- concrete fixes;
- reviewer questions;
- wiki-entity mapping;
- dialogue history in hard/adversarial mode.

The original skill is read-only; a migrated system may persist the report, but persistence is not required for semantic equivalence.

---

## 7. Pilot specification

### Created by

```text
/ideate
```

or manually before:

```text
/exp-pilot-run <idea-slug>
```

### Output

```text
experiments/pilot/<idea-slug>.yaml
```

### Required structure

```yaml
pilot_spec:
  hypothesis: ...
  approach_sketch: ...

  implementation:
    repo: ...
    entry_point: ...
    modifications: ...
    files_to_create: [...]

  setup:
    model: ...
    dataset: ...
    hardware: ...
    framework: ...
    batch_size: ...
    max_steps: ...
    learning_rate: ...
    seeds: ...
    other_hparams: ...

  metrics:
    - name: ...
      why: ...

  baseline:
    method: ...
    source: ...
    expected_value: ...

  success_criterion:
    pass: ...
    fail: ...
    inconclusive: ...
```

---

## 8. Pilot implementation and run

### Command

```text
/exp-pilot-run <idea-slug> --env local
```

### Outputs

```text
experiments/pilot/code/<idea-slug>/train.py
experiments/pilot/code/<idea-slug>/config.yaml
experiments/pilot/code/<idea-slug>/run.sh
experiments/pilot/code/<idea-slug>/requirements.txt
experiments/pilot/code/<idea-slug>/pilot.log
experiments/pilot/code/<idea-slug>/results/seed_<N>.json
terminal PILOT_REPORT
```

### Perfect-run checks

- sanity run passes;
- human approval gate is respected;
- baseline is present;
- declared metrics are emitted;
- no crash, OOM, divergence, or missing result file.

---

## 9. Pilot verdict

### Command

```text
/exp-pilot-eval <idea-slug>
```

### Outputs

```text
experiments/pilot/<idea-slug>/report.md
wiki/ideas/<idea-slug>.md
wiki/log.md
terminal PILOT_VERDICT_REPORT
```

### Perfect-run state

```yaml
pilot_result: "pass — <metric summary>"
status: proposed
failure_reason: ""
```

A pilot pass means only “no obvious collapse”; it is not final idea validation.

---

## 10. Full experiment design

### Command

```text
/exp-design <idea-slug>
```

### Outputs

```text
experiments/designs/<idea-slug>-master.md
wiki/experiments/<experiment-slug>.md
wiki/ideas/<idea-slug>.md
wiki/graph/edges.jsonl
wiki/graph/context_brief.md
wiki/graph/open_questions.md
wiki/log.md
terminal DESIGN_REPORT
```

### Required experiment-page structure

```yaml
title: ...
slug: ...
status: planned
linked_idea: <idea-slug>
evaluates_methods: [...]
hypothesis: ...
tags: [...]

setup:
  model: ...
  dataset: ...
  hardware: ...
  framework: ...

metrics: [...]
baseline: ...
outcome:
key_result: ...
date_planned: ...
date_completed:
run_log:
started:
estimated_hours:

remote:
  server:
  gpu:
  session:
  started:
  completed:
```

Body:

```text
Objective
Setup
Procedure
Results
Analysis
Idea updates
Follow-up
```

### Perfect-run checks

- one or more experiment blocks exist;
- a main experiment exists;
- baselines, metrics, and quantitative success criteria are explicit;
- the idea lists every experiment in `linked_experiments`;
- graph has `idea --tested_by--> experiment`.

---

## 11. Experiment implementation and deployment

### Command

```text
/exp-run <experiment-slug> --review --env local
```

### Outputs

```text
experiments/code/<experiment-slug>/
logs/exp-<experiment-slug>.log
wiki/experiments/<experiment-slug>.md
wiki/log.md
terminal DEPLOY_REPORT
```

### Perfect-run state after deploy

```yaml
status: running
run_log: logs/exp-<experiment-slug>.log
started: <timestamp>
estimated_hours: <positive integer>
```

### Perfect-run checks

- generated code implements both proposal and baseline;
- code review/sanity check passes;
- human approval gate is respected;
- process is actually launched.

---

## 12. Experiment monitoring

### Command

```text
/exp-status
```

or:

```text
/exp-status --pipeline <pipeline-slug>
```

### Output

```text
terminal status table
wiki/log.md
```

### Perfect-run status categories

```text
running
completed_pending_collect
collected
```

There should be no anomaly state in a perfect run.

---

## 13. Result collection

### Command

```text
/exp-run <experiment-slug> --collect
```

or collect all ready runs:

```text
/exp-status --collect-ready
```

### Outputs

```text
results/<experiment-slug>/seed_<N>.json
wiki/experiments/<experiment-slug>.md
wiki/log.md
terminal RUN_REPORT
```

### Perfect-run experiment state

```yaml
status: completed
outcome: succeeded
key_result: "<one-sentence quantitative finding>"
date_completed: <date>
```

Experiment body must have populated:

```text
Results
Analysis
```

The report must contain baseline values, mean ± standard deviation, and deltas for declared metrics.

---

## 14. Idea-level verdict

### Command

```text
/exp-eval <experiment-slug>
```

Run for every completed experiment linked to the idea.

### Outputs

```text
wiki/ideas/<idea-slug>.md
wiki/experiments/<experiment-slug>.md
wiki/graph/edges.jsonl
wiki/graph/context_brief.md
wiki/graph/open_questions.md
wiki/log.md
terminal VERDICT_REPORT
```

### Perfect-run state

```yaml
# idea
status: validated
failure_reason: ""
date_resolved: <date>
```

Experiment page includes:

```text
Idea updates
```

Graph includes:

```text
experiment --supports--> idea
```

Verdict:

```text
supported
```

---

## 15. Paper plan

### Command

```text
/paper-plan <validated-idea-slug> --venue ICLR
```

### Outputs

```text
wiki/outputs/paper-plan-<slug>-<date>.md
wiki/graph/edges.jsonl
wiki/graph/context_brief.md
wiki/log.md
terminal PAPER_PLAN_REPORT
```

### Required plan sections

- metadata;
- target ideas;
- evidence map;
- narrative arc;
- section-by-section outline;
- page budget;
- figure/table plan;
- citation plan;
- citation coverage;
- independent outline-review summary.

Graph includes:

```text
paper-plan --derived_from--> idea
paper-plan --derived_from--> source paper
```

---

## 16. Related work

### Command

```text
/survey <validated-idea-slug> --format latex
```

### Outputs

```text
wiki/outputs/related-work-<slug>-<date>.md
wiki/graph/edges.jsonl
wiki/log.md
terminal Related Work text and citation coverage
```

### Perfect-run checks

- papers grouped thematically;
- every citation maps to an existing wiki paper;
- each group ends by positioning the new work;
- BibTeX is verified or explicitly marked unconfirmed.

---

## 17. Paper draft

### Command

```text
/paper-draft wiki/outputs/<paper-plan-file>.md --review
```

### Outputs

```text
paper/main.tex
paper/math_commands.tex
paper/references.bib
paper/sections/*.tex
paper/figures/*
paper/tables/*                    # optional
wiki/log.md
terminal Paper Write Complete report
```

### Perfect-run checks

- all required sections exist;
- figures and tables referenced by the plan exist;
- all citation keys resolve;
- no generated technical claim lacks a wiki source;
- full-paper cross-review completes.

---

## 18. Paper refinement

### Command

```text
/refine paper/main.tex --max-rounds 3 --target-score 8 --focus writing
```

### Outputs

```text
paper/*.tex updated in place
possible wiki updates
wiki/log.md
terminal REFINE_REPORT
```

### Perfect-run checks

- target score reached or verdict `ready`;
- score history is recorded;
- unresolved issues are explicitly listed;
- no required experimental evidence is fabricated.

---

## 19. Compilation and submission checks

### Command

```text
/paper-compile paper/ --fix
```

### Outputs

```text
paper/main.pdf
wiki/log.md
terminal COMPILE_REPORT
```

### Perfect-run checks

```text
Compilation: SUCCESS
Page count: PASS
Anonymous: PASS or acceptable WARN
Unconfirmed citations: 0
Fonts embedded: PASS
TODO/FIXME markers: 0
Figures referenced: PASS
Abstract present: PASS
Blocking issues: none
```

---

## 20. Poster

### Command

```text
/poster paper/ --review --anonymous --no-logos
```

### Outputs

```text
poster/dag.json
poster/outline.html
poster/poster.html
poster/poster.png
poster/images/*
wiki/log.md
terminal POSTER_REPORT
```

---

## 21. Rebuttal

### Command

```text
/rebuttal raw/reviews/test-review.md --paper-slug <paper-slug> --venue ICLR --stress-test
```

### Outputs

```text
wiki/outputs/rebuttal-<slug>.md
wiki/outputs/rebuttal-<slug>.txt
possible updates to wiki/ideas/*.md
possible updates to wiki/methods/*.md
wiki/log.md
```

### Perfect-run checks

- every reviewer concern receives an ID and response;
- every factual answer traces to experiment or wiki evidence;
- no unsupported claim or fabricated result;
- stress-test completes;
- formal and rich-text outputs both exist.

---

# E. Lifecycle state invariants

## Idea

```text
proposed
  → in_progress
  → tested
  → validated
```

A perfect run ends in `validated`.

## Experiment

```text
planned
  → running
  → completed
```

A perfect main experiment ends with:

```yaml
outcome: succeeded
```

## Pipeline

```text
stage0/bootstrap
→ stage1/ideation
→ gate1/selection
→ stage2/design
→ stage3a/deploy
→ stage3b/await
→ stage3c/collect
→ stage4/verdict
→ gate2/paper-ready
→ stage5/paper
→ completed
```

---

# F. Required graph-edge invariants

At minimum, a complete run should create:

```text
paper     --introduces_concept / uses_concept / extends_concept--> concept
idea      --addresses_gap-----------------------------------------> concept/topic
idea      --inspired_by-------------------------------------------> paper/method/concept
idea      --tested_by---------------------------------------------> experiment
experiment--supports----------------------------------------------> idea
paper plan--derived_from------------------------------------------> idea/paper
paper     --cites-------------------------------------------------> paper
```

---

# G. Terminal reports expected in a complete run

These are often terminal-only in the original implementation:

```text
Setup summary
Init summary
Ingest summary
Lint Report
IDEA_REPORT
Novelty Report
Review Report
PILOT_REPORT
PILOT_VERDICT_REPORT
DESIGN_REPORT
DEPLOY_REPORT
Experiment Status Report
RUN_REPORT
VERDICT_REPORT
PAPER_PLAN_REPORT
Paper Write Complete report
REFINE_REPORT
COMPILE_REPORT
POSTER_REPORT
```

For the migrated orchestrator, persisting these reports is recommended, but semantic equivalence does not require identical filenames unless the original already defines one.

---

# H. Final acceptance criteria

A migrated AutoSci run is comparable with the original when all of the following are true:

- [ ] all user-facing commands resolve;
- [ ] each stage accepts the documented inputs;
- [ ] all required persistent artifacts are produced;
- [ ] all terminal reports contain the expected semantic fields;
- [ ] no stage requires hidden context from a previous agent;
- [ ] every handoff is artifact-based;
- [ ] rerunning ingestion is idempotent;
- [ ] idea and experiment lifecycle transitions are valid;
- [ ] all graph edges point to existing entities;
- [ ] pilot pass does not incorrectly mark an idea validated;
- [ ] final validation is based on completed experiment evidence;
- [ ] experiment results are preserved per seed;
- [ ] human approval gates cannot be bypassed;
- [ ] asynchronous runs can be resumed after process/session restart;
- [ ] `wiki/log.md` records each state-changing command;
- [ ] final paper compiles;
- [ ] no submission blockers remain;
- [ ] `wiki/outputs/PIPELINE_REPORT.md` accurately lists all stages and artifacts.

---

# I. Known current-spec inconsistencies to normalize in the migration

These should not be treated as functional failures if the migrated system resolves them cleanly:

1. `/ideate` documents `/novelty --write` before the idea page is created, while `/novelty --write` requires the idea page to exist.
2. `/paper-plan` documents a dated filename, while one `/research` example refers to `wiki/outputs/PAPER_PLAN.md`.
3. Several reports are terminal-only, so exact file persistence is not uniformly specified.
4. Result JSON contains experiment-specific metrics; the current project does not impose one universal result schema beyond requiring per-seed JSON outputs and declared metrics.

The migrated system should preserve the semantic contract while making these handoffs explicit and deterministic.
