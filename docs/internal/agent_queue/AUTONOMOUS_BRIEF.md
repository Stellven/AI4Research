# Autonomous brief: finish `research.evidence_to_poc.v1`

You are taking over a live engineering task. Work autonomously for as long as it
takes. Do not stop between steps to ask permission. The owner has asked that you
keep going until the goal is verified and complete, and expects this to take
hours.

This brief gives you the goal, the evidence, and what "done" means. **It does not
tell you how to implement anything.** Where a previous agent made a design
choice, it is recorded as history with its reasoning so you can judge it, not as
an instruction to follow. If you see a better way, take it.

---

## 0. Access

```
repo      git@github.com:Stellven/AI4Research.git      (SSH always, never HTTPS)
branch    task/research-evidence-to-poc-fixed
worktree  autosci-fixed-workflow/wt-evidence-to-poc
```

HTTPS has no credential helper here and fails with "could not read Username".

---

## 1. The owner and the goal

### In their words

> "my end goal hopefully is to have a static workflow and no planner so the DAG
> is present but everything else should be solar handled"

> "so usually solar governs with gates so why arent we using solar gates"

> "the reason i went with fixed workflow is because if i let the planner in it
> introduced a lot of issues"

> "the report should be a real deep research report like ones solar would
> produce"

> "but remember you have to check the claims: if they contradict, are they
> actually supported by their evidence, etc. there is a lot, which is why you
> should indeed check the solar system and wire together"

> "part B should run experiments, benchmarks, etc. you can pull autosci
> directly"

> "it should go through autosci - autosci will extract claims from research
> report and do whatever it needs"

Most recent, and unresolved:

> "so retrieval is poor? you should be getting 50-60 research papers"

> "why is it a source pack when we set up everything?"

### Standing instructions

* Scope changes to this workflow: *"try to decouple the changes so that it only
  affects the workflow I am working on and not every workflow."*
* Rebind what Solar already has rather than writing your own: *"why are you
  recreating things, you might do worse."* Search the tree first.
* *"don't make assumptions on ambiguities, search for existing work always."*
* Measure, never infer: *"there has to be a harness telling every single thing
  that happened on a low-level ... right now you are just guessing and
  implementing fixes based on what you think without evidence."*
* Single-threaded. No subagents.
* Plain hyphens in prose, no em dashes.

### How the owner judges work

They want **truthful** green, not green. They have repeatedly caught contrived
success. A run that passes while its evidence says something false is worse than
a run that fails. If you cannot verify something, say so rather than reporting it
done.

---

## 2. The system

A fixed 15-stage Solar workflow. Contract:
`harness/config/workflows/research.evidence_to_poc.v1.workflow.json`, currently
v1.7, all 15 stages gated by `deterministic_command`.

Part A: `seed_fetch`, `source_discovery`, `source_validation`,
`evidence_synthesis`, `report_draft`, `independent_review`, `report_revision`,
`final_acceptance`.

Part B: `poc_handoff`, `idea_evaluation`, `experiment_design`,
`experiment_approval`, `experiment_run`, `claim_verification`, `final_delivery`.

Model calls happen at `evidence_synthesis`, `report_draft`, `independent_review`,
and `report_revision` when a revision is needed. Everything else is
deterministic.

Runs on Claude CLI with Haiku:
`SOLAR_RESEARCH_MODEL_PROVIDER=claude SOLAR_RESEARCH_MODEL=claude-haiku-4-5-20251001`.
Codex works too (`codex`, `gpt-5.5`). The adapter verifies the recorded provider
matches the selected one.

The entrypoint is `harness/tools/fixed_research_uat.py start-to-final`. Prior
invocations are in git history and in the documents in section 8;
`--workspace-root` must exist before launching. A run is roughly 12 minutes wall
clock, of which about 2.4 minutes is execution and the rest poll overhead.

Forensic telemetry exists at `harness/tools/fixed_research_forensics.py`
(`--watch` for a live feed). It reads the three places a failure hides: the gate
sidecar, the operator dispatch result, and the node result the operator wrote
itself. A previous session lost hours answering "what is the run doing" with `ls`
and `tail` before it existed. Use it, or something better.

---

## 3. The thing most worth knowing

A previous session fixed fourteen defects. **None were model failures. None were
component failures. All were seams**, and most were one shape:

> the operator imposed a condition on the model that the operator itself made
> unsatisfiable.

Examples: a reviser judged against a list that grew after it answered; a reviewer
demanding a Method correction that byte-exact preservation forbade; an operator
appending a duplicate heading it then flagged as critical; a model scored on a
lexical test nobody told it about; an adapter capping calls below the retry
budget the operator was designed to use.

Unit tests caught none of them. Each needed two real components joined. A live
run is worth more than another unit test here.

The previous agent walked into this pattern twice while documenting it. Knowing
about it is not protection.

---

## 4. Verified state (facts from artifacts, not claims)

* Three consecutive green runs, 15/15, at three different commits.
* Every gate `deterministic_command`, durations 0.06-0.10s, none 0.0.
  `PASS / gate_kind none / duration 0.0` is the signature of a gate that did not
  run. It appears nowhere now.
* 95 related tests pass. Five failures in
  `test_rc10_codex_{profile_lifecycle,unattended_launch}` are pre-existing and
  unrelated (`No module named 'file_lock_compat'`), confirmed by stashing.
* Claim grounding holds: 6-8 claims per run, 0 rejected, 1 attempt, term
  coverage 0.5-0.96, unsupported rate 0.0 recomputed independently.
* The revision loop converges when a revision is required.
* Part B executes something real: a sandboxed benchmark, 8/8 integrity checks.
* AutoSci claim extraction runs inside the workflow and pulls claims from the
  accepted report.

---

## 5. What is wrong, with the evidence

### 5.1 Live retrieval has never run

Every run so far used `acquisition_mode: source_pack` and read a canned 5-line
`sources.jsonl`. So the three green runs verified governance with retrieval
effectively stubbed out. "5 sources" was an input constant, not a result.

The retrieval pipeline itself exists and is real: arXiv, Europe PMC, OpenAlex,
Crossref, Semantic Scholar, with a minimum-provider rule, round-robin candidate
selection, per-provider retry and title dedup, in
`harness/plugins/autosci/services/production_research.py`. The workflow has
`live_search` and `hybrid` modes and code that branches on them, currently never
exercised. The candidate budget is presently a small literal in the adapter,
passed through as each provider's page size.

The owner expects 50-60 papers. Nothing about that is impossible; it has simply
never been switched on.

One caution: arXiv was once declared unreliable on the basis of a single failed
trial. Nine spaced trials later showed 9/9. Do not diagnose a provider from one
sample.

### 5.2 The published deliverable is polluted, and one line in it is false

The report and the delivery carry the reviewer's own process commentary as if it
were scientific limitation. Shipped examples:

* "cannot verify whether claim_source_lineage changes were possible without
  access to the evidence synthesis generation process"
* "No access to the original report draft to measure whether changes were
  actually made"
* "This review evaluates only the report's structure..."

6 of 17 limitations in `delivery/final_delivery.json` are of this kind. One is
factually wrong: it states the report "uses evidence from all five" sources while
the report correctly says four, because one source was excluded for minimal
content. A reviewer-authored sentence contradicts the report it is attached to,
and it shipped.

### 5.3 Part B does not use the operators the contract declares

The contract names `ScientificIdeaEvaluator`, `ScientificExperimentRunner`,
`ScientificClaimVerifier`. All are registered and resolvable, among 33 bound
physical operators. The adapter bypasses the resolver for Part B and runs a
bespoke duplicate hardcoded to a single benchmark id. So the DAG declares one
thing and something else executes.

### 5.4 Part B does not run real experiments

AutoSci's `run_experiment` supports genuine outcomes
(`supports | partially_supports | refutes | inconclusive | failed`), hash-bound
approval, and sandbox modes. It requires an `experiment_executor` service. No
such service exists anywhere in the tree, so that path fails closed. Part B
currently replays artifact digests instead.

**A trap worth knowing.** The AutoSci bridge exposes `run_experiment`, but it
loads a fixture and says so in its own recorded limitation: *"Fixture result is
deterministic and not a real benchmark run."* Its metrics are
`result_json_written: true`. Using it as the executor would replace a real
sandboxed check with something that reports "supports" without running anything.
The bridge does accept an injected real result, which matches its manifest:
*"this plugin only converts bounded backend outputs into Solar evidence."*

The open question, which the previous agent deliberately refused to guess: **what
should Part B actually experiment on?** The report now yields testable claims.
What counts as falsifying one is a judgement call, and it is yours to make and
justify.

### 5.5 Contradiction detection does not exist

The owner asked whether claims contradict. Support is now checked; contradiction
is not. Solar has a contradiction-matrix builder, but it groups already-labelled
relations rather than deriving them, and the synthesis is never asked which
sources disagree with a claim. The report compiler already understands
`supports` / `contradicts` / `qualifies` / `contextualizes`.

### 5.6 Report sectioning is built but inert

The plan builder groups claims by a per-claim theme and is verified to produce
multi-section reports. Nothing emits a theme yet.

### 5.7 A grounded report path exists but is not wired

Solar's grounded compiler produces a byte-verified report with exact quote spans,
a report AST, and an evaluation artifact. A previous session proved the chain
works on real artifacts (19 files, 8/8 exact quote spans, zero gaps) but never
wired it into the workflow.

Known consequences if you pursue it, offered as evidence rather than direction:
the current report artifact's structure is consumed by the revision, acceptance
and preservation chain that presently goes green; the compiler refuses an output
directory that is non-empty or overlaps a source pack; a stage's read scope is
exactly its declared dependencies; and the "operator changed unreported files"
check compares against the operator's own declared artifacts file by file, so a
declared directory covers none of its children.

---

## 6. What done means

The goal is met when all of the following hold **in one live run**, verified from
artifacts rather than logs:

1. Retrieval genuinely ran, at the scale the owner asked for, across multiple
   providers, with the surviving set traceable through validation into the
   report.
2. All 15 stages completed and gated, every gate a real command with a non-zero
   duration.
3. Every published claim is quoted verbatim from its source and genuinely
   supported by it, with the unsupported rate recomputed independently rather
   than asserted.
4. The report is a real deep research report of the kind Solar produces, with
   verifiable quote-level grounding.
5. The report and delivery contain nothing about the review process and nothing
   contradicting their own source counts.
6. Part B runs through the operators the contract declares.
7. Part B tests something real, and the artifact states precisely what was and
   was not tested.
8. Whether claims contradict each other is answered, not assumed.
9. The related test suite passes, and new behaviour has tests that would fail if
   it regressed.

Finish by reporting what is verified, what is not, and what you got wrong. The
owner values the last of those more than a clean narrative.

---

## 7. Environment facts that will otherwise cost you a run

Properties of the system, not advice about design.

1. `pkill -f` and broad `pgrep -f` match the invoking shell and any monitors.
   This killed a session's own shell three times, once discarding a queued edit
   silently.
2. The UAT process does not exit when the DAG completes; it polls until its own
   timeout, so a later run will overlap it.
3. Dispatches import operator code fresh, so editing during a run makes that
   run's telemetry unattributable across two commits.
4. Orphaned status servers cross-talk with new runs.
5. The field name `evidence_ids` means different things at different levels: on a
   claim it holds source ids, on a conclusion it holds claim ids.
6. `additionalProperties: False` on a response schema means an unlisted field is
   refused, not ignored. This once made a required field silently absent for a
   whole day.
7. The benchmark runner refuses an output path whose parent does not resolve
   inside its work directory, and reports the reason on stdout, not stderr.
8. Experiment approval pins the benchmark runner's sha256; editing that script
   fires the approval check by design.
9. A long unexplained gap in a run timeline may be the host suspending. Check
   whether your own telemetry stopped at the same instant.
10. Do not trust a stale note about model availability. One claimed a model was
    exhausted when it was free all along.

---

## 8. Where the history is

* `docs/internal/agent_queue/HANDOVER_TO_CODEX_20260820.md` - every defect with
  its reasoning and measurements.
* `docs/internal/agent_queue/SESSION_HANDOFF_20260819.md` - the running log with
  raw evidence, including the wrong turns.

Both contain conclusions that were reached and later corrected. The corrections
are the useful part. Treat every design decision in them as a previous agent's
judgement, not as a constraint on yours.
