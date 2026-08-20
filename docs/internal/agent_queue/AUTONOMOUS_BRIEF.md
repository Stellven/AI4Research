# Autonomous brief: finish `research.evidence_to_poc.v1`

You are taking over a live engineering task from a previous agent. Work
autonomously for as long as it takes. Do not stop to ask for approval between
steps. The owner has explicitly asked that you keep going until the goal is
verified and complete, and has said this should take hours.

---

## 0. Access

```
repo    git@github.com:Stellven/AI4Research.git      (SSH ALWAYS, never HTTPS)
branch  task/research-evidence-to-poc-fixed
HEAD    ca58238ad
```

Work on that branch. If `git remote -v` shows an `https://` URL, convert it
first: `git remote set-url origin git@github.com:Stellven/AI4Research.git`.
HTTPS has no credential helper here and will fail with "could not read Username".

Working directory in the previous session was the worktree
`autosci-fixed-workflow/wt-evidence-to-poc`. Paths below are relative to it.

---

## 1. The owner, and what they actually want

### The goal, in their words

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

Most recent, and currently UNRESOLVED:

> "so retrieval is poor? you should be getting 50-60 research papers"

> "why is it a source pack when we set up everything?"

### Standing instructions (always on)

* **"try to decouple the changes so that it only affects the workflow I am
  working on and not every workflow."** Scope changes to
  `research.evidence_to_poc.v1`. Do not change shared-lib behaviour for other
  workflows. Example of the right shape: the deepcopy fix added `__deepcopy__`
  to our own journal type rather than removing `deepcopy` from the shared
  resolver.
* **"yes rebuild as necessary - why are you recreating things, you might do
  worse."** Rebind Solar's existing machinery; do not reimplement it. Search the
  tree before writing anything.
* **"don't make assumptions on ambiguities, search for existing work always."**
* **"there has to be a harness telling every single thing that happened on a
  low-level to identify where the issues are coming from, because right now you
  are just guessing and implementing fixes based on what you think without
  evidence."** Measure. Never infer. This is the owner's core complaint about
  prior work.
* **"keep going, why do you keep stopping? set a goal until the workflow is
  working end to end, keep working and monitoring, fix what happened."**
* Single-threaded. No subagents, no parallel fan-out.
* Plain hyphens in prose, never em dashes.
* Never `pkill -f` or broad `pgrep -f` - see traps.

### How the owner judges work

They care about **truthful** green, not green. They have repeatedly caught
contrived success and they will catch it again. If something cannot be verified,
say so plainly rather than reporting it as done. A run that goes green while its
evidence says something false is worse than a run that fails.

---

## 2. What the system is

`research.evidence_to_poc.v1` is a fixed 15-stage Solar workflow, contract at
`harness/config/workflows/research.evidence_to_poc.v1.workflow.json`, currently
**v1.7 with 15/15 stages gated** by `deterministic_command`.

**Part A (research, 8 stages):** `seed_fetch`, `source_discovery`,
`source_validation`, `evidence_synthesis`, `report_draft`, `independent_review`,
`report_revision`, `final_acceptance`.

**Part B (PoC, 7 stages):** `poc_handoff`, `idea_evaluation`,
`experiment_design`, `experiment_approval`, `experiment_run`,
`claim_verification`, `final_delivery`.

Three stages make model calls (`evidence_synthesis`, `report_draft`,
`independent_review`, plus `report_revision` when a revision is required).
Everything else is deterministic.

**Provider:** Claude CLI with Haiku.
```
SOLAR_RESEARCH_MODEL_PROVIDER=claude SOLAR_RESEARCH_MODEL=claude-haiku-4-5-20251001
```
Codex still works via `SOLAR_RESEARCH_MODEL_PROVIDER=codex` (`gpt-5.5`). The
adapter verifies the recorded provider matches the selected one, so you cannot
silently run one and record the other.

### How to run it

```bash
SOLAR_RESEARCH_MODEL_PROVIDER=claude SOLAR_RESEARCH_MODEL=claude-haiku-4-5-20251001 \
timeout 5400 python3 harness/tools/fixed_research_uat.py start-to-final \
  --evidence-root <scratch>/evidence-<name> \
  --source-pack "$PWD/artifacts/dashboard-uat-input-20260818/source-pack" \
  --source-authority-root "$PWD/artifacts/dashboard-uat-input-20260818" \
  --request-file <scratch>/p1.txt \
  --workspace-root <scratch>/ws-<name> \
  --policy-actor "Suraj" \
  --policy-statement "I authorize the bounded evidence-lineage benchmark for this gate verification run." \
  --timeout-seconds 5100 --poll-seconds 20
```

`--workspace-root` must EXIST before launching or it fails instantly with
`FileNotFoundError`. A run takes ~12 minutes wall clock: ~2.4 min of execution,
the rest poll overhead of roughly 50s per stage.

`p1.txt` contains:
> Research and compare retrieval-augmented generation evaluation methods and
> reliability benchmarks using at least three real public scholarly sources.

### How to watch it

```bash
# one-shot digest
python3 harness/tools/fixed_research_forensics.py --evidence-root <root>

# forensic watch: snapshots every N seconds, prints on change and on every failure
python3 harness/tools/fixed_research_forensics.py --evidence-root <root> --watch --interval 20
```

This reads the THREE places a failure hides, because the previous session found
one in each: the gate sidecar, the operator dispatch result, and the node result
the operator wrote itself. **Use it. Do not answer "what is the run doing" with
`ls` and `tail`** - hours were lost that way before this existed.

---

## 3. The pattern. This is the single most useful thing in this document.

The previous session fixed fourteen defects. **Zero were model failures. Zero
were component failures. Every one was a seam, and most were the same shape:**

> **The operator imposed a condition on the model that the operator itself made
> unsatisfiable.**

Instances:

* the reviser was told to preserve limitations, then judged against a list that
  had grown after it answered
* the reviser was required to render limitations the reviewer wrote *after* the
  report was generated
* the reviewer demanded a Method-section correction while byte-exact
  preservation forbade changing the Method section
* the operator appended a second `## Limitations` heading itself, the reviewer
  flagged the duplicate as CRITICAL, and the operator recreated it every retry
* the synthesis model was scored on a lexical support test nobody told it about
* the adapter capped `evidence_synthesis` at one model call while the operator
  was designed to retry three times
* a conclusion was required to cite CLAIM ids while the same field name on a
  claim holds SOURCE ids

**When a stage fails repeatedly with a competent model, check what the operator
is demanding before you touch the model or the prompt.** That was the answer
most times out of fourteen.

Corollary, proven repeatedly: **unit tests caught none of these.** Each needs two
real components joined. Prefer a live run over another unit test.

The previous agent walked into this pattern itself, twice, while writing the
document warning about it. Knowing the pattern is not protection. When you add a
bound, a retry, or a requirement in one component, go looking for the other
component that already restates it.

---

## 4. Verified current state (facts, not claims)

* **Three consecutive green runs**, 15/15, at three different commits
  (`evidence-e2e2`, `evidence-e2e5`, `evidence-e2e7` under the scratch dir).
* Every gate `deterministic_command`, durations 0.06-0.10s, **none 0.0**.
  `PASS / gate_kind none / duration 0.0` is the signature of a gate that did not
  run; it appears nowhere now.
* 95 related tests pass. Five failures in
  `test_rc10_codex_{profile_lifecycle,unattended_launch}` are pre-existing and
  unrelated (`No module named 'file_lock_compat'`), confirmed by stashing.
* Claim grounding: 6-8 claims per run, **0 rejected, 1 attempt**, term coverage
  0.5-0.96, `unsupported_rate` 0.0 verified by independent recomputation.
* Revision loop converges: last run attempt 2, `verdict: accept`,
  `method_changed: True`, `retention 0.9868` against a 0.8 floor.
* Part B executes for real: `unshare -Urn` + `fixed_research_benchmark.py`,
  8/8 integrity checks, `integrity_rate 1.0`, `claim_verification: verified`.
* AutoSci claim extraction runs inside the workflow: `poc/idea/` holds
  `research_paper.v1.json` and `research_claims.v1.json`, 8 claims, 1 testable.

---

## 5. THE CRITICAL UNRESOLVED FINDING - start here

**Live retrieval has never run. Not once.**

Every run used `acquisition_mode: source_pack` and read a canned **5-line**
`sources.jsonl` from `artifacts/dashboard-uat-input-20260818/source-pack/`.
So all three green runs verified the governance end to end with retrieval
effectively stubbed out. "5 sources" was an input constant, not a retrieval
result.

Why: `fixed_research_uat.py` **requires** `--source-pack` and never sets
`acquisition_mode`, so the adapter falls back to its default `"source_pack"`
at `fixed_research_node_adapter.py:561`.

The owner expects **50-60 papers**. Two things block that:

1. **Mode.** `acquisition_mode` must be `live_search` or `hybrid`. The plumbing
   already branches on it and is currently dead code in these runs:
   * `fixed_research_node_adapter.py:604` `public_discovery` gate
   * `_retrieval_policy_ref` dependency injection
   * `source_validation.py:267-273` live-source minimum requirements
   It originates from graph/intake substitutions
   (`harness/lib/workflow_intake.py:256`), NOT from the UAT tool.

2. **Budget.** `fixed_research_node_adapter.py:641` hardcodes
   `LiteratureDiscoveryService(stage_dir, limit=12)`, and that `limit` is passed
   straight through as each provider's page size (`max_results`, `pageSize`,
   `per-page`, `rows`). Service default is 8. For 50-60 papers this needs to be
   ~60 and configurable, not a literal.

**The retrieval pipeline itself is real and already built** (previous session):
arXiv, Europe PMC, OpenAlex, Crossref, Semantic Scholar, with
`MIN_DISCOVERY_PROVIDERS = 2`, round-robin candidate selection so one provider
cannot crowd out others, per-provider retry, and title-based dedup. It is in
`harness/plugins/autosci/services/production_research.py`.

Note: arXiv was once wrongly blamed as unreliable on the basis of a single
failed trial. Nine spaced trials later showed 9/9. **Do not diagnose a provider
from one sample.**

Expect live mode to surface things that have never executed: the live-source
minimums in `source_validation`, the retrieval policy reference, network
failures, and rate limits. That is the point of running it.

---

## 6. Work queue, in order. Do all of it.

Each item has an acceptance test. Do not mark an item done without it.

### 6.1 Make retrieval real (highest priority)

* Make `acquisition_mode` settable for a run (`live_search` or `hybrid`).
* Make the discovery limit configurable and raise it toward 50-60.
* Run live and report, from artifacts: candidates per provider, how many survive
  the relevance gate, how many carry usable text, and how many reach the report.

**Accept when:** a live run reaches 15/15 with `acquisition_mode: live_search`,
`candidate_count` in the tens, and `source_validation` accepting a substantial
set from at least two distinct providers.

### 6.2 Separate review-scope limitations from report-scope limitations

The published report currently carries the REVIEWER's own process commentary as
if it were scientific limitation. Real examples that shipped:

* "cannot verify whether claim_source_lineage changes were possible without
  access to the evidence synthesis generation process"
* "No access to the original report draft to measure whether changes were
  actually made"
* "This review evaluates only the report's structure..."

6 of 17 limitations in `delivery/final_delivery.json` are process meta-commentary.
**One is factually wrong**: it says "Five scholarly sources are available; the
report uses evidence from all five" while the report correctly says four
(`openalex-rag-04` was excluded for minimal content). A reviewer-authored
sentence contradicts the report it is attached to, and it shipped.

Cause: `report_revision` accumulates reviewer limitations into the same list the
report body renders, and `final_delivery` aggregates upstream limitations
wholesale. The artifact `limitations` field was already fixed to publish only
the accepted preserved set; the rendered body and the delivery aggregation were
not.

**Accept when:** a live run's `revision/report.md` and `delivery/final_delivery.md`
contain no statement about the review process, the reviser's access, or
`claim_source_lineage`, and no statement contradicting the report's own source
count.

### 6.3 Wire the grounded compiler into `report_draft`

Fully de-risked already. `validated_pack.py` -> `synthesis_plan.py` ->
`compile_grounded_report` publishes 19 files from real artifacts with 8/8 exact
quote spans and zero gaps.

Design constraints, already established - do not rediscover them:

* **Do not replace** `report_draft`'s LLM report. `report_revision`,
  `final_acceptance` and the preservation chain all consume its `conclusions`
  structure, and that chain is what currently goes green.
* `report_draft` is in the adapter's model-stage set, so a purely deterministic
  stage there trips "completed model stage emitted no provider usage".
* Therefore: keep the writer call and **additionally** compile into
  `report/grounded/`, with `report/source_pack/` as a SIBLING (the compiler
  refuses an `output_dir` overlapping a source pack, and refuses a non-empty one).
* `report_draft` currently depends only on `evidence_synthesis`, and `read_scope`
  is exactly the dependency artifact paths, so it **cannot read
  `source_validation.json`**. Add `source_validation` to its `depends_on`
  (already transitively ordered, so no DAG change).
* Declare **every** pack and report file individually - the unreported-files
  check reads the operator's own `output_artifacts`, file by file, exact string
  match. A declared directory covers none of its children. Counts vary with
  source count, so `rglob` after writing.

A prepared but UNAPPLIED patch script exists at
`<scratch>/apply_compile_wiring.py`. Read it before running it; it does the
contract bump and imports only, not the full operator change.

**Accept when:** a live run produces `report/grounded/final.md`,
`report_ast.json` and `research_eval.json`, all preflights pass, and the run
still reaches 15/15.

### 6.4 Route Part B through the resolver

The contract declares `ScientificIdeaEvaluator`, `ScientificExperimentRunner`,
`ScientificClaimVerifier` - all registered - but
`fixed_research_node_adapter.py:661` short-circuits the resolver for every Part B
stage and calls `execute_part_b` from `fixed_research_poc.py` instead. That
bespoke code duplicates `idea.evaluate_ideas`, `experiment.design_experiment`,
`experiment.approve_experiment`, `delivery.verify_claim` one-for-one, hardcoded
to a single `BENCHMARK_ID`.

So the DAG says `ScientificExperimentRunner` and a bespoke digest replay runs.
That is a provenance discrepancy independent of what the benchmark does.

Feasible today: `scientific_lifecycle/registry.py:registration_entries()` already
binds 33 physical operators including `idea_evaluate_worker`,
`experiment_design_worker`, `experiment_approval_gate_worker`,
`experiment_run_worker`, `claim_verify_worker`, `publication_produce_worker`.
Nothing needs writing to make them dispatchable; the adapter never asks.

**Accept when:** Part B stages dispatch through the resolver to the declared
operators, and the run still reaches 15/15.

### 6.5 Bind an `experiment_executor` so Part B runs real experiments

`run_experiment` in `scientific_lifecycle/action/experiment.py` requires
`context.services["experiment_executor"]` and fails closed without it.
`production_services_from_environment` (production_research.py:1763) provides
`fetch_url`, `discover_sources`, `model_generate`, `review_model_generate`,
`secret_values` - and nothing else. So AutoSci's real experiment path cannot run.

It supports genuine outcomes: `supports | partially_supports | refutes |
inconclusive | failed`, hash-bound approval matching the exact plan, and sandbox
modes `isolated | container | process_restricted`.

**DO NOT use the bridge's `run_experiment` as the executor.** It loads
`tests/.../sample_autosci_raw_experiment_result.json` and states its own
limitation: *"Fixture result is deterministic and not a real benchmark run."* Its
metrics are `result_json_written: true`. Routing execution through it would
replace a real sandboxed 8/8 check with a fixture that reports "supports"
without running anything - more scientific-looking and less true.

The bridge DOES accept an injected real result
(`_experiment_result_payload` reads `experiment_result_evidence` /
`result_evidence` / `experiment_result` and overrides the fixture). That matches
the plugin manifest: *"this plugin only converts bounded backend outputs into
Solar evidence."* **Execute, then convert. Never let the bridge invent the
result.**

The open design question, which the previous agent deliberately did not guess:
*what should Part B actually experiment on?* Today it replays digests. The report
now yields testable claims via AutoSci extraction. Decide what a falsifiable
outcome means for a claim like "query rewriting improves retrieval alignment",
implement an executor for a narrow real class of claim, and record honestly what
is and is not being tested.

**Accept when:** `experiment_run` dispatches through AutoSci's operator with a
real executor, and the recorded outcome reflects something actually executed -
with the artifact stating exactly what was tested.

### 6.6 Contradiction detection

The owner asked whether claims contradict. **Support is done; contradiction is
not.** Solar's `build_contradiction_matrix`
(`research/survey/gates/controversy_matrix.py`) is deterministic but only GROUPS
already-labelled `relation_type` rows - it does not derive them. Our synthesis is
never asked which validated sources DISAGREE with a claim.

Needs: a synthesis prompt/schema addition for contradicting sources, real
`relation` values in the plan (`supports` / `contradicts` / `qualifies` /
`contextualizes` are already supported by `compile_grounded_report`), then the
matrix works as-is.

**Accept when:** a run produces a contradiction matrix with real relations and
`compile_grounded_report` reports a non-fabricated `contradiction_count`.

### 6.7 Themed sections (small, inert until wired)

`build_plan` already groups claims by a per-claim `theme` and is verified to
produce multi-section reports. Nothing emits a theme yet. Two edits: add optional
`theme` to the claim schema in
`codex_research._response_schema("evidence_synthesis")` (mind the
`additionalProperties: False` trap), and carry it through `_normalize_claims`.
Do not invent a theme when the model omits one; the single-section fallback
exists for that.

---

## 7. Traps that will cost you a run

1. **`kill` by PID, never `pkill -f` / broad `pgrep -f`.** The pattern matches
   the invoking shell and the monitors. This happened THREE times in one session
   (exit 144). Once it killed the shell before a queued patch ran, so the edit
   silently did not apply. Use
   `ps -eo pid,cmd | grep X | grep -v grep | awk '{print $1}'`.
2. **The UAT process does not exit when the DAG completes.** After 15/15 it keeps
   polling until its own `--timeout-seconds`. Kill it by PID once
   `phase: completed`, or a later run overlaps it.
3. **Never edit operator code while a run is in flight.** Dispatches import
   fresh, so the run silently spans two commits and its telemetry becomes
   unattributable. If unavoidable, write atomically (temp file + `os.replace`).
4. **Orphaned status servers cross-talk.** Check `ps` for `status-server.py`
   before launching.
5. **Two id spaces share the field name `evidence_ids`.** On a CLAIM it lists the
   SOURCES it rests on (`openalex-rag-01`); on a CONCLUSION it lists the CLAIMS
   (`claim-001`). Whenever you add a field carrying ids, say which space it is in.
6. **`additionalProperties: False` on a response schema means an unlisted field
   is refused, not ignored.** That is how `evidence_quotes` came back empty for a
   whole day.
7. **The "operator changed unreported files" check reads the OPERATOR's declared
   `output_artifacts`, file by file, exact match.** `_inventory` walks with
   `rglob`. A declared directory covers none of its children.
8. **`fixed_research_benchmark.py` refuses an `--output` whose parent does not
   resolve inside `--work-dir`**, and reports the reason on stdout, not stderr.
9. **`experiment_approval` pins `benchmark_policy.runner_sha256` to the exact
   bytes of `fixed_research_benchmark.py`.** Editing that script fires the
   approval check. That is correct behaviour.
10. **A long unexplained gap in a run timeline may be the HOST SUSPENDING, not a
    stall.** Check forensic snapshot numbering: if snapshots also stopped, the
    machine slept.
11. **Do not trust a stale note about model availability.** A prior handoff
    claimed `gpt-5.5` was exhausted; it was free the whole time. Probe.

---

## 8. Definition of done

The goal is complete when ALL of the following hold **in one live run**, verified
from artifacts, not from logs or assertions:

1. `acquisition_mode: live_search` (or `hybrid`), with candidates in the tens
   from at least two distinct providers, and a substantial accepted set.
2. All 15 stages `completed` with gate `PASS`, every `gate_kind`
   `deterministic_command`, every duration non-zero.
3. `unsupported_rate` genuinely 0.0, recomputed independently by the gate, with
   claims that quote their sources verbatim and pass Solar's support assessment.
4. A grounded report published (`final.md`, `report_ast.json`,
   `research_eval.json`) with exact quote spans and no evidence gaps.
5. The published report and delivery contain no review-process commentary and no
   statement contradicting their own source counts.
6. Part B dispatches through the resolver to the declared AutoSci operators.
7. `experiment_run` records an outcome from something actually executed, with the
   artifact stating precisely what was and was not tested.
8. The full related test suite passes, and any new behaviour has a test that
   would fail if the behaviour regressed.

Report at the end: what is verified, what is not, and what you got wrong along
the way. The owner values the last of those more than a clean narrative.

---

## 9. Where the detail lives

* `docs/internal/agent_queue/HANDOVER_TO_CODEX_20260820.md` - the full narrative
  handover: every defect with its reasoning, the measurements, the corrections
  in the order they happened.
* `docs/internal/agent_queue/SESSION_HANDOFF_20260819.md` - the running log with
  raw evidence for every finding, including the diffs and the wrong turns.

Read both before making structural changes. They contain several conclusions that
were reached, then corrected, and the corrections are the valuable part.
