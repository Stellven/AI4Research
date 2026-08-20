# Handover: research.evidence_to_poc.v1

**From:** Claude session, 2026-08-19 -> 2026-08-20
**To:** the Codex agent, when quota returns
**Branch:** `task/research-evidence-to-poc-fixed`
**Worktree:** `autosci-fixed-workflow/wt-evidence-to-poc`
**Base of this session:** `caa20200f` -> **HEAD `723148627`**, 27 commits, tree clean

Read this before touching anything. The single most useful thing in it is the
pattern in section 3, because it accounts for ten of the thirteen defects fixed.

---

## 0. What the owner actually asked for, in their words

Read this first. Everything below is downstream of it, and several of my early
mistakes came from not weighting these enough.

### Standing instructions (treat as always-on)

- **"try to decoiple the changes ot hat it only affects th eowkrlfo i wam working
  on and not everyworkflow"** -- scope changes to
  `research.evidence_to_poc.v1`. Do not edit shared lib behaviour for other
  workflows. This is why the deepcopy fix uses a `__deepcopy__` on our own
  journal type instead of removing `deepcopy` from the shared resolver.
- **"yes rebuild as necessary why are you recreating things you might do worse"**
  -- rebind Solar's existing machinery, do not reimplement it. This is why claim
  support uses `claim_support_assessment` rather than a new checker.
- **"dont make assumptions on ambiguities, search for existing work always"** --
  search the tree before designing. Doing this found `rsi_demo`, `claim_compiler`,
  `controversy_matrix` and changed the design twice.
- **"there has to be a harness telling every single thing that happened on a
  low-level to identify where the issues are coming from because right now you
  are just guessing and implementing fixes based on what you think without
  evidence"** -- this is the core complaint. Measure, do not infer.
- **"i am very surprised you dont have access to the docker images and the
  telemetry harness because everything was there, i built a telemetry, a big
  pipeline for the runs for docker UAT"** -- `internal/codex-docker-uat/` is the
  owner's own work and is better than what this workflow had. Use it.
- **"keep going, why do you keep stopping? set a goal until workflow is working
  end to end, keep working and monitoring, fix what happened"** -- do not stop
  at each finding to report. Drive to a green run.
- Single-threaded work, no subagents. Plain hyphens, no em dashes.

### The goal

- **"my end goal hopefully is to have a static workflow and no planner so the DAG
  is present but everything else should be solar handled"**
- **"so usually solar governs with gates so why arent we using solar gates"** --
  this drove the move from 2 of 15 gated stages to 15 of 15.
- **"the reason i went with fixed workflow is because if i let the planner in it
  introduced a lot of issues"**

### On quality of the research output

- **"the report should be a real deep research report like ones solar would
  produce"**
- **"but remember you have to check the claims: if they contradict, are they
  actually supported by their evidence, etc. there is a lot, which is why you
  should indeed check the solar system and wire together"** -- this is the
  requirement that produced the claim-grounding work in section 4. **Support is
  now done; contradiction is NOT.** See section 7.3.
- **"but for the sources judged by where they came from not what they are about,
  solar itself should check evaluators and stuff like that, i remember checking
  it and provenance"**

### On the provider

- **"wait what the heck, the whole time with the runs were you using gpt 5.3 or
  5.5?"** -- I had been using an exhausted model on the basis of a stale note.
- **"so what do we do now, can we switch the physical operator to claude haiku or
  a small model?"** -> the workflow now runs on `claude-haiku-4-5`.

### On Part B (most recent, and NOT yet done)

- **"part B should run experiments, benchmarks, etc. you can pull autosci
  directly"** -- see section 7.3a. Part B currently runs a bounded
  evidence-lineage benchmark, not real experiments.
- **"or have you run part B yet or no? has it verified run benchmarks?"** -- yes,
  once, and the numbers are in section 1.
- **"what is the timing for both parts?"** -- section 1.


---

## 1. Where the workflow stands

`research.evidence_to_poc.v1`, contract **v1.7**, **15 of 15 stages gated** with
real `deterministic_command` gates (it was 2 of 15 at the start of the session).

**It has run green end to end once**, on `claude-haiku-4-5-20251001`, sprint
`sprint-20260819-234544-...-ab5de2af863a`:

| | stages | execution | wall clock |
|---|---|---|---|
| Part A (seed_fetch .. final_acceptance) | 8 | 2.1 min | ~6 min |
| Part B (poc_handoff .. final_delivery) | 7 | 0.2 min | ~5.3 min |
| total | 15 | 2.4 min | ~11-12 min |

Only three stages do real work: `evidence_synthesis` 50s, `independent_review`
36s, `report_draft` 34s. Every other stage is 1-2 seconds. The remaining wall
clock is ~50s of poll/dispatch overhead per stage. If you want the run faster,
that overhead is the target, not the model.

Part B genuinely executed its benchmark:

```
experiment_run      completed, exit 0
  checks_passed 8/8, integrity_rate 1.0, duration 2.8ms
  sandbox: linux_user_and_network_namespace, network disabled
claim_verification  verified
  "Every retained Part-A artifact in the accepted handoff matched its
   controller-bound SHA-256 digest during replay."
```

Say what that is honestly: it re-verifies Part A's artifact digests under
replay. The operator states its own limit -- "Part B tests evidence-lineage
integrity; it does not independently establish external scientific validity."
It is a provenance check, not a scientific replication.

**Current HEAD is AHEAD of that green run.** Since then, claim grounding was
added and the preservation checks were rewritten. The last run at the newer code
(`evidence-e2e3`) reached 6/15 and died at `report_revision`; that failure is
diagnosed and fixed in `723148627` but **has not yet been re-run**. First job:
re-run and confirm 15/15 at HEAD (section 7).

---

## 2. Provider

The workflow runs on the **Claude CLI with Haiku**, not Codex:

```
SOLAR_RESEARCH_MODEL_PROVIDER=claude SOLAR_RESEARCH_MODEL=claude-haiku-4-5-20251001
```

Codex still works -- `SOLAR_RESEARCH_MODEL_PROVIDER=codex` selects
`CodexResearchModelService` and `gpt-5.5`. The adapter guard now verifies the
recorded provider matches the one selected, so you cannot silently run one and
record the other.

Note for your own planning: a prior handoff claimed `gpt-5.5` was exhausted. It
was not; it was free all along and the note was stale. **Probe model
availability, do not trust a note about it** -- including this one.

---

## 3. The pattern. Read this part twice.

**Thirteen defects fixed. Zero were model failures. Zero were component
failures. Every one was a seam, and ten were the same shape:**

> **The operator imposed a condition on the model that the operator itself made
> unsatisfiable.**

Concretely:

- the reviser was told to preserve limitations, then judged against a list that
  had grown after it answered
- the reviser was required to render limitations the reviewer wrote *after* the
  report was generated
- the reviser was told "fix the Method section" by the reviewer and "never
  change the Method section" by the preservation check, at the same time
- the operator appended a second `## Limitations` heading itself, then the
  reviewer flagged the duplicate as CRITICAL, and the operator recreated it on
  every retry
- the synthesis model was scored on a lexical support test nobody had told it
  about
- the adapter capped `evidence_synthesis` at one model call while the operator
  was designed to retry up to three times, so a stage doing exactly what it was
  built to do was refused (I introduced this one myself, in the middle of
  writing this document about the pattern)

When you see a stage failing repeatedly with a model that is otherwise
competent, **check what the operator is asking of it before you touch the model
or the prompt.** In this codebase that has been the answer ten times out of
thirteen. I walked into it myself once, which is the best evidence that knowing
about the pattern is not sufficient protection against it -- when you add a
bound, a retry, or a requirement in one component, go and look for the other
component that already restates it.

The corollary, proven repeatedly: **unit tests did not catch a single one of
these.** Each needs two real components joined. Prefer a live run over another
unit test.

---

## 4. What was fixed, and why each mattered

### Provider provenance (`1bb14c2cc`)
`ClaudeResearchModelService` overrode `__call__` without the three lines its
Codex parent uses to stamp `provider` / `model` / `provider_usage` on the
returned payload, so `provider_usage_from` fell back to a row labelled
`"injected"` and the adapter refused it. Separately `_record_invocation`
hardcoded `codex_subscription`, so every Haiku call was journalled as Codex.
Fixing only the crash would have produced a green run whose evidence named the
wrong provider, which is worse than the crash. The label is now the
`usage_provider` class attribute and the guard resolves the expected value from
`SOLAR_RESEARCH_MODEL_PROVIDER`.

### Node-completion gating, contract v1.6 then v1.7 (`7d6c85193`, `15c6095b2`)
Two stages had written `"status": "failed"`, `status_is_terminal: true` into
their own results -- `final_acceptance` saying it "rejected the research result"
-- and both were recorded as `verdict PASS, gate_kind none, duration 0.0` while
the DAG marched past them. Presence checks cannot catch this because a failed
dispatch leaves behind whatever it wrote before raising.

`validate_evidence_to_poc.py --node-complete STAGE` now reads the operator's own
recorded status and fails on anything but `completed`; a missing result is a
failure, not a pass. **`PASS / gate_kind none / duration 0.0` is the signature of
a gate that did not run.** If you see it, the stage is unchecked.

The stage -> result-directory map is **derived from the contract**, not
hardcoded. Hardcoding it cost a full run: `poc_handoff` writes to `poc/handoff/`,
not `poc/`, and all six Part B stages nest the same way.

### The deepcopy seam (`2e428d006`)
`default_production_resolver` does `services=deepcopy(injected)`
(runtime.py:723), so operators mutate copied journals while the adapter reads
the originals. `_merge_codex_invocation_usage`, whose docstring promises to
"bind every attempted call, including calls hidden by operator failure", could
never see a single call. Invisible on success because the payload carries its
own usage; fatal on failure, the one case it exists for. Fixed with
`SharedInvocationJournal.__deepcopy__` returning self, so the shared lib
resolver is untouched.

### report_revision, four defects (`319e26405`, `a18ac7e35`, `886ebd51e`, `723148627`)
This node failed on every run and blocked everything downstream:
`final_acceptance` rejected, `poc_handoff` retried eight times, run timed out.

The root cause, found by diffing the live exchange: **the reviser echoed a
recorded limitation with a trailing full stop added.** 172 characters required,
173 declared, otherwise identical. One punctuation mark failed the node. Earlier
replays could not reproduce it because they compared the recorded strings to
themselves.

Preservation now means the accepted content is not silently **lost**:
limitations compare on normalised text with trailing punctuation stripped;
conclusions compare on substantive text with decoration removed while evidence
ids stay exact; the method must survive by word retention against a 0.8 floor
rather than be byte-identical. Method changes are recorded as `method_change`
with before/after digests **beside** `preservation`, never inside it -- the
adapter recomputes that object and refuses the node if it differs.

### The per-stage call ceiling (`d45fcc158`)
`max_calls = MAX_REVISION_ATTEMPTS * 2 if node_id == "report_revision" else 1`.
Adding a bounded grounding-repair loop to `evidence_synthesis` immediately
tripped it. The ceiling is now a table read from the operators' own constants,
so an attempt bound raised in one place cannot leave the other behind. Stages
absent from the table still get exactly one call.

### Claim grounding, at the cause (`d952df36f`)
Solar's own `claim_support_assessment` rated 2 of the 5 published claims
UNVERIFIED (term coverage 0.12-0.43 against a 0.45 floor) and a third carried no
verified quote, while `research_eval.json` reported `unsupported_rate: 0.0`.

Byte-level quote verification and actual support are different properties. A
quote can be genuinely verbatim while the claim built on it is about something
else.

`evidence_synthesis` now refuses to publish a claim without at least one
verbatim quote AND at least one cited source passing the support check, feeding
each rejection back to the model, bounded to three attempts. Solar's checker is
rebound, not reimplemented, and its aggregation rule from `NaiveClaimCompiler` is
followed: assess against the FULL source text, count a claim supported when ANY
cited source supports it.

**Result: 6 claims, 0 rejected, 1 attempt, coverage 0.50-0.96, unsupported_rate
0.00 verified independently.** The bounded retry loop never fired. Telling the
model what the test actually was proved sufficient -- the same lesson as
section 3.

---

## 5. Telemetry: use it, do not rebuild it

`harness/tools/fixed_research_forensics.py`, ported from the pattern in
`internal/codex-docker-uat/entrypoint.sh` (which the owner built and which is far
better than what existed here).

```bash
# one-shot digest
python3 harness/tools/fixed_research_forensics.py --evidence-root <root>

# forensic watch: snapshots every N seconds, prints on change and on every failure
python3 harness/tools/fixed_research_forensics.py --evidence-root <root> --watch --interval 20
```

It reads the **three** places a failure hides, because this session found one in
each: the gate sidecar, the operator dispatch result, and the node result the
operator wrote itself. Absent is reported as absent.

Run against a failed run it reported, unprompted, two failed nodes, both dispatch
errors, the failed provider call, and eight `poc_handoff` retries that hours of
manual digging had missed. **Hours were lost before this existed. Do not answer
"what is the run doing" with `ls` and `tail`.**

One caution learned the hard way: a long unexplained gap in the timeline may be
the **host suspending**, not the workflow stalling. In the green run, snapshot #1
was at 23:46 and #22 at 00:50 when a 20s interval should have produced ~190 --
the monitor froze at the same instant the harness did. Check snapshot numbering
before diagnosing a stall.

---

## 6. Traps that will cost you a run

1. **`kill` by PID, never `pkill -f` / broad `pgrep -f`.** The pattern matches
   the invoking shell and the monitors. It killed a monitor here (exit 144).
2. **Never edit operator code while a run is in flight.** Dispatches import
   fresh, so the run silently spans two commits and its telemetry becomes
   unattributable. If you must, write atomically (temp file + `os.replace`).
3. **Orphaned status servers cross-talk.** A server from a dead run will be
   talked to by a new one. Check `ps` for `status-server.py` before launching.
4. **`additionalProperties: False` on the response schema means an unlisted
   field is refused, not ignored.** That is how `evidence_quotes` came back empty
   for a whole day. Add the field to `_response_schema` before asking for it.
5. **The "operator changed unreported files" check reads the OPERATOR's declared
   `output_artifacts`, file by file, exact string match.** A declared directory
   covers none of its children. `_inventory` walks with `rglob`.
6. **`compile_grounded_report` refuses a non-empty `output_dir` and any dir
   overlapping a source pack.** They must be siblings.
7. **`fixed_research_benchmark.py` refuses an `--output` whose parent does not
   resolve inside `--work-dir`,** and reports the reason on stdout, not stderr.
8. **`experiment_approval` pins `benchmark_policy.runner_sha256` to the exact
   bytes of `fixed_research_benchmark.py`.** Editing that script will fire the
   approval check. That is correct behaviour, not a bug.

---

## 7. What to do next, in order

**1. Re-run at HEAD and confirm 15/15.** This is the one thing that must happen
before anything else. HEAD carries claim grounding and the rewritten
preservation checks and has never completed a full run.

```bash
bash <scratch>/gate-runs/run_e2e.sh <name>     # or the equivalent below
python3 harness/tools/fixed_research_forensics.py \
    --evidence-root <scratch>/gate-runs/evidence-<name> --watch --interval 20
```

The run command is `harness/tools/fixed_research_uat.py start-to-final` with
`--evidence-root`, `--source-pack`, `--source-authority-root`, `--request-file`,
`--workspace-root`, `--policy-actor`, `--policy-statement`. The workspace root
must **exist** before launching or it fails immediately with `FileNotFoundError`.

**2. Wire `report_draft` to `compile_grounded_report`.** This was the task in
progress. Everything it needs is proven working against real artifacts:

- `validated_pack.py` -> `synthesis_plan.py` -> `compile_grounded_report`
  publishes 19 files from the run's own artifacts, all three preflights passing
- with grounded claims it produces 6 claims, 0 gaps, 8/8 exact quote spans

Design already settled, and the reasoning matters:

- **Do not replace** `report_draft`'s LLM report. `report_revision`,
  `final_acceptance` and the preservation chain all consume its `conclusions`
  structure, and that chain is what just went green.
- `report_draft` is in the adapter's model-stage set, so a purely deterministic
  stage there trips "completed model stage emitted no provider usage".
- Therefore: keep the writer call, **additionally** compile into
  `report/grounded/`, with `report/source_pack/` as a sibling.
- `report_draft` currently depends only on `evidence_synthesis`, and `read_scope`
  is exactly the dependency artifact paths, so it **cannot read
  `source_validation.json`**. Add `source_validation` to its `depends_on`
  (already transitively ordered, so no DAG change). Contract v1.8.
- Declare **every** pack and report file individually (trap 5). Counts vary with
  source count, so `rglob` the directory after writing rather than hardcoding.

A prepared patch script is at `<scratch>/apply_compile_wiring.py`. Read it before
running it; it does the contract bump and the imports, not the full operator
change.

**3. Contradiction detection.** Solar's own deep-research workflow
(`research.deepdive.rsi_demo`) has a `D4 DeepDiveContradictionScanner` and this
workflow has nothing equivalent. `build_contradiction_matrix` in
`research/survey/gates/controversy_matrix.py` is deterministic but only **groups**
already-labelled `relation_type` rows; it does not derive them. So real
contradiction analysis needs the synthesis to be asked which validated sources
*disagree* with a claim, which it currently never is. The owner explicitly wants
this ("do the claims contradict, are they actually supported"). Support is now
done; contradiction is not.


### 7.3a Part B should run real experiments (owner request, not yet done)

The owner's ask: **"part B should run experiments, benchmarks, etc. you can pull
autosci directly"**. Here is exactly what exists and what is missing, checked in
the tree rather than assumed.

**What Part B does today.** `fixed_research_poc.py` runs one bounded benchmark,
`harness/tools/fixed_research_benchmark.py`, under `unshare -Urn` with networking
disabled. It re-hashes every Part A artifact in the accepted handoff and checks
each against its controller-bound SHA-256. Last run: 8/8 checks,
`integrity_rate 1.0`. That is a genuine, sandboxed, deterministic check, and the
operator states its own limit: *"Part B tests evidence-lineage integrity; it does
not independently establish external scientific validity."* It is a provenance
replay, not science.

**What AutoSci already provides.**
`harness/plugins/autosci/operators/scientific_lifecycle/action/experiment.py`
implements the real lifecycle: `design_experiment`, `approve_experiment`,
`run_experiment`, `monitor_experiment`. Notably `run_experiment` accepts outcomes
`supports | partially_supports | refutes | inconclusive | failed`, requires a
hash-bound approval matching the exact plan, and enforces
`SANDBOX_MODES = {isolated, container, process_restricted}`. That is real
hypothesis testing with falsification, which is what the owner is asking for.

Conversion adapters already exist:
`adapters/autosci_to_experiment_plan.py`, `..._to_experiment_result.py`,
`..._to_experiment_status.py`, plus `autosci_to_claim_verdict.py`.

**What is missing, and it is one thing.** `run_experiment` does:

```python
executor = context.services.get("experiment_executor")
if not callable(executor):
    raise ResearchOperatorError("experiment_executor service is unavailable", ...)
```

There is **no `experiment_executor` implementation in this tree**.
`production_services_from_environment` (production_research.py:1745) provides
`fetch_url`, `discover_sources`, `model_generate`, `review_model_generate` and
`secret_values` -- and nothing else. So AutoSci's `run_experiment` cannot execute
today; it would fail closed with `environment_unavailable`.

That is consistent with the plugin's own manifest: *"Solar owns workflow
semantics, capsules, Evidence ABI, and gates; this plugin only converts bounded
backend outputs into Solar evidence."* AutoSci here is an **adapter**, and the
executing backend is external. The setup guide adds: *"long-running experiment
launch require explicit approval and runtime evidence."*

**And it is worse than a missing executor: Part B is a reimplementation.**
Checked against the tree, `fixed_research_poc.py` duplicates one-for-one what
AutoSci already provides:

| bespoke, in `fixed_research_poc.py` | already exists in `scientific_lifecycle/action/` |
|---|---|
| `_idea_evaluation` | `idea.evaluate_ideas` |
| `_experiment_design` | `experiment.design_experiment` |
| `_experiment_approval` | `experiment.approve_experiment` |
| `_experiment_run` | `experiment.run_experiment` |
| `_claim_verification` | `delivery.verify_claim` |
| `_final_delivery` | `delivery.produce_publication` / `plan_report` / `draft_report` |

The bespoke version is hardcoded to a single `BENCHMARK_ID`
(`evidence-lineage-integrity`); the AutoSci version takes a plan and returns a
falsifiable outcome.

**The contract already names the AutoSci operators, and they are not what runs.**
`idea_evaluation` declares `ScientificIdeaEvaluator`, `experiment_run` declares
`ScientificExperimentRunner`, `claim_verification` declares
`ScientificClaimVerifier`, and all three are registered in
`config/logical-operators.json`. But `fixed_research_node_adapter.py:638`
short-circuits the resolver for every Part B stage:

```python
part_b_stage = node_id in PART_B_EXECUTABLE_NODE_IDS
...
if part_b_stage:
    result = execute_part_b(...)
```

So the DAG says `ScientificExperimentRunner` and a bespoke digest replay
executes. That is a provenance discrepancy in its own right, independent of what
the benchmark does, and it is exactly the "why are you recreating things, you
might do worse" problem the owner flagged.

**So the work is:**

1. Implement or bind an `experiment_executor` service returning
   `{outcome, metrics, evidence_ids, criteria_results?, limitations?}`, honouring
   `sandbox`, `timeout_seconds` and `max_output_bytes` from the plan. The
   existing `fixed_research_benchmark.py` invocation is a working reference for
   the sandboxing.
2. Decide whether Part B swaps to the AutoSci lifecycle operators or keeps the
   lineage benchmark as an additional integrity stage. Ask the owner; both are
   defensible and it changes what the deliverable claims.
3. Route Part B through the resolver so the declared logical operators actually
   execute, instead of `execute_part_b` bypassing it. That alone closes the
   contract-versus-dispatch discrepancy even before the executor exists.

   This is feasible today. `scientific_lifecycle/registry.py:registration_entries()`
   already binds 33 physical operators, including every one Part B needs:

   ```
   scientific_lifecycle_action  idea_evaluate_worker
   scientific_lifecycle_action  experiment_design_worker
   scientific_lifecycle_action  experiment_approval_gate_worker
   scientific_lifecycle_action  experiment_run_worker
   scientific_lifecycle_action  claim_verify_worker
   scientific_lifecycle_action  publication_produce_worker
   ```

   So the operators are registered, bound and resolvable. Nothing needs writing
   to make them dispatchable; the adapter simply never asks for them. Only
   `experiment_run_worker` additionally needs the executor from step 1.
4. There is no AutoSci checkout anywhere on this machine outside this plugin
   (searched). So "pull autosci directly" means bind the in-repo
   `scientific_lifecycle` operators, not fetch an external repo.
   `autosci_bridge.py` (9700+ lines) is the integration point if a real external
   backend is later attached.

Until an executor exists, do not describe Part B as running experiments. It
replays digests.

**4. Themed sections are in but inert.** `build_plan` groups claims by a
per-claim `theme`, verified to produce 4 rendered sections. Nothing emits a theme
yet. Two edits: add an optional `theme` string to the claim schema in
`codex_research._response_schema("evidence_synthesis")` (mind trap 4), and carry
it through `_normalize_claims`. Do not invent a theme when the model omits one;
the single-section fallback exists for that.

**5. Lower priority:** `tools/research` is a stale duplicate of
`harness/lib/research`; the intent gateway discards constraints; five failures in
`test_rc10_codex_{profile_lifecycle,unattended_launch}` are pre-existing and
unrelated (`No module named 'file_lock_compat'`), confirmed by stashing.

---

## 8. Things I got wrong, so you do not repeat them

- I claimed the contract's directory declarations covered the unreported-files
  check. They do not; it reads the operator's own file-by-file declarations.
- I claimed binding `evaluate_artifacts` gives a gate that cannot fail. It has a
  dozen live checks; only two thresholds are defeated by constants.
- I predicted the strict profile would refuse our thin source pack on authority.
  It passed.
- I hardcoded the stage result-directory map and it was wrong for seven of
  fifteen stages, which killed a healthy run at 8/15.
- I read `preservation_feedback` as absent and concluded an attempt had passed.
  The field is recorded under a different name,
  `previous_attempt_rejected_because`, and the attempt had failed.

The common thread: each was an inference I could have checked and did not. The
codebase rewards reading the artifact over reasoning about it.

---

## 9. Where the detail lives

`docs/internal/agent_queue/SESSION_HANDOFF_20260819.md` is the running log of
this session with the full evidence for every finding above, including the
diffs, the measurements, and the corrections in the order they happened. This
document is the summary; that one is the record.
