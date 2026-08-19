# Session handoff - 2026-08-19

Worktree: `autosci-fixed-workflow/wt-evidence-to-poc`
Branch: `task/research-evidence-to-poc-fixed`, base `7302ab2ba`, **21 commits**.
Working tree clean.

Work single-threadedly. Do not create subagents.

## The one finding that matters

Twelve defects were found and fixed this session. **Every one was a seam
between two components, not a component.** Not one was a model producing bad
output.

| where | defect |
|---|---|
| relevance | judged by provenance, not aboutness |
| relevance | one common word admitted any source |
| retrieval | a cascade with a threshold, described as a union |
| routing | every prompt pinned to one workflow |
| Part B | could not chain: wrong argument per stage |
| bridge | unstated `mode` defaulted to `fixture`, fabricating evidence |
| executor | `ok: True` on a stage that timed out and wrote nothing |
| executor | a killed run left a 0-byte log |
| preflight | Landlock grant excluded conda/pyenv Python |
| gate | `<resolved_root>` overshot by one directory level |
| gate | harness cwd is not the sprints root |
| gate | claims checked on a stage that has none |
| gate | required an artifact a later stage writes |
| schema | `additionalProperties: false` forbade the field the prompt asked for |
| adapter | import path that resolves in tests and fails at dispatch |

Unit tests caught none of these and could not have: each needs two real
components connected. Two were things verified in isolation minutes earlier
that still failed under the real entry path. **Prefer a live run over another
unit test.**

## Verified working

- **Gates are real.** `source_validation` and `evidence_synthesis` carry
  `deterministic_command` gates (contract v1.5). Confirmed in a live run:
  `gate_kind: deterministic_command`, real command, non-zero duration, and
  `on_fail: fail` genuinely blocking (`dispatch-ready rc=2`). Before this,
  every stage recorded `PASS / content / independent_verification` with
  `gate_kind: none`, `command: ""`, `duration: 0.0`.
- **Three prompts, correct behaviour.** RAG request -> 5 sources accepted,
  6 claims, report produced. CRISPR and Mamba requests against a RAG-only pack
  -> 0 accepted, **no report**, stopped at stage 3. That is the original
  contrivance dead in both directions.
- **Retrieval**, 9 spaced trials: arXiv 9/9, Europe PMC 6/9, OpenAlex 3/3,
  Semantic Scholar 0/9 (429 without a key).
- **Docker install smoke**: PASS 16/16. Note gitleaks is absent and its check
  silently degrades to a pass.
- 82 research-synthesis tests pass.

## The rebind (the big change)

Part A had its own source format, claim model and report assembler. All three
existed in `harness/lib/research` and the local versions were worse - the
assembler emitted every findings heading twice.

    validated_pack.py    accepted sources -> DeepResearch pack
                         (sources.jsonl + evidence.jsonl + extracts/)
                         evidence rows carry span_start/span_end/content_hash
    synthesis_plan.py    claims -> solar.grounded_synthesis_plan.v2
    evidence_synthesis   now asks for the verbatim sentence per cited source
                         and verifies it is an exact substring before storing

`compile_grounded_report` then re-checks every quote independently (exact
substring of the evidence content, and sharing tokens with the claim) and
hashes it into the report. Two layers verify, neither trusting the other.

Result: **15 artifacts** where there were 2, including `claim_evidence.jsonl`
and `section_checks.jsonl` - the tables `evidence/ledger.py` computes a real
unsupported rate from.

Verified end to end on **claude-haiku-4-5**: 5 claims, 6 quotes, 6/6 surviving
verbatim verification, plan sufficient, 15 artifacts.

## Provider is now selectable

`SOLAR_RESEARCH_MODEL_PROVIDER=codex|claude`, `SOLAR_RESEARCH_MODEL=<id>`.

Codex quota was the whole workflow's ceiling: `gpt-5.3-codex-spark` exhausted
until Aug 24. **Every run today used spark because a stale handoff note said
`gpt-5.5` was exhausted; it had recovered and was free the whole time.** Probe
model availability at the start of a session, do not trust this file for it.

Claude CLI notes: `--json-schema` takes inline JSON, not a path, and cannot
resolve the 2020-12 meta-schema by URL - the CLI copy of the schema must drop
`$schema` or the whole argument is rejected and the constraint silently lost.

## Telemetry

`harness/tools/fixed_research_run_telemetry.py`

    --live   phase, active node, per-stage state, gate verdict/kind,
             and every model call with the provider and model that served it
    (none)   post-run snapshot with commit provenance

Use this instead of `ls` and `tail`. Tailing logs is how a timed-out stage was
nearly reported as a success and a stale server's output was read as the
current run's. Node state comes from the sprint status file - not the graph
nodes, not the per-node runstate sidecar (which records attribution only).

## In flight at handoff

A live `claude-haiku-4-5` run of prompt p1, evidence root
`<scratch>/gate-runs/evidence-p1`. At handoff: `active=source_discovery`,
1 stage done, 0 model calls. It is testing whether the Haiku path holds through
the real workflow rather than a direct service call.

## Next, in order

1. **Finish the live Haiku run.** Nothing else is blocked on it, but it is the
   first end-to-end proof of the provider switch.
2. **Wire `report_draft` to `compile_grounded_report`.** The adapters exist and
   are tested; the operator still uses the old assembler, so the workflow does
   not yet produce the 15-artifact report. Needs `evidence_synthesis` to write
   the pack (it has the inputs; `report_draft` does not) and a contract change
   to declare the pack directory as an output, or the "operator changed
   unreported files" check fires. That is a v1.6 change.
3. **Real quality metrics.** `grounded_synthesis` hardcodes
   `unsupported_rate: 0.0` and `citation_accuracy: 1.0`, so binding
   `evaluate_artifacts` today gives a gate that cannot fail. `ledger.py` can
   compute both now that `claim_evidence.jsonl` exists. **Do this before
   binding the evaluator gate.**
4. **Unpin `PHYSICAL_OPERATOR_BY_NODE`** - but widen, do not remove. It is a
   safety guard enforced at four sites in `graph_node_dispatcher.py`
   ("operator identity mismatch"), not an assignment. One operator -> the
   capsule's `preferred` list. Fixes the `state=cooldown` failure class and
   enables concurrency.
5. Part B B3-B7. Never completed. `$exp-design` exceeded 40 minutes; AutoSci is
   at `autosci-spike/upstream-autosci-codex` and `$research` owns the whole
   half behind one boundary gate. Its Stage 3 is async and needs an external
   scheduler under Codex.

## Open, lower priority

- `harness/tools/research/` is a stale divergent copy of `harness/lib/research/`
  (May 31 vs Aug 7; the lib copy carries provider/query/retrieved_at/
  response_status). Bind `lib`. Resolve before wiring the evaluator.
- 18 `DeepDive*` logical operators are named by
  `deepdive_requirement_compiler.py` and **0 are registered**, so contradiction
  scanning cannot be bound by the Planner or by a contract.
- The intent gateway discards the constraints you state and substitutes
  boilerplate about task_graph. `SOLAR_INTENT_REWRITE_CMD` is unset, so the
  model rewriter never runs. Verified against a real `requirement_ir.json`.
- Failed runs orphan their status server; the next run then talks to the old
  one. Kill by PID, never `pkill -f status-server.py` (it matches the invoking
  shell).
- UI: sprint title truncated mid-word in the backend
  (`workflow_intake.py:227`, `request[:80]`); roster shows Builder while an
  Evaluator gate failed; green-for-done conflicts with `DESIGN.md` and needs
  that file amended first.
- Serper key is live in `~/.solar-secrets/serper.env` (mode 600) and was pasted
  into a chat transcript - rotate it. Measured 2/8 scholarly on a paper query;
  it is a contradiction/web channel, not a bibliographic provider, and needs
  its own keyed retrieval policy.
- Semantic Scholar API key still needed: 0/9 without one, and it is the only
  provider offering `influentialCitationCount` and `venue`.

## Evidence roots

`<scratch>/gate-runs/evidence-p{1,2,3}` (three-prompt gate runs),
`artifacts/adversarial-prompt-a{,-final}-20260818` (the original contrivance,
before and after), `artifacts/dashboard-full-uat-r13/r14-20260818`.

## Update 2026-08-19 17:35 -- the Haiku run failed, and it is a seam, not the model

The live `claude-haiku-4-5` run of p1 (evidence root
`<scratch>/gate-runs/evidence-p1`, sprint
`sprint-20260819-212653-wf-research-evidence-to-poc-v1-f40de28fe29b`) was
stopped by hand after failing four times on `evidence_synthesis`. It was
retrying with a guaranteed failure and spending a real Haiku call each time.

### What is confirmed, from artifacts

* Every retry made a real, successful Haiku call: four `exchange.json` records,
  all `status: completed`, `exit_code: 0`, 47.8s / 55.2s / 79.7s.
* Every retry produced a good artifact: `synthesis/evidence_synthesis.json`
  holds 5 claims across 4 distinct sources with 7 verified quotes. The model
  did its job on every attempt.
* Every retry was then rejected by the harness:
  `result.json` -> `status: failed`, `exit_code: 2`,
  `log_tail: {"ok": false, "error": "model stage used a non-Codex provider"}`.
* `synthesis/research_node_result.json` was never written, while every earlier
  stage has one. The node never reached its gate, so there is no
  `evidence_synthesis-eval.json` -- the claims gate did not fail, it never ran.

So the provider switch is sound at the service layer and blocked one layer up.

### The guard

`harness/plugins/autosci/bin/fixed_research_node_adapter.py:391`, in
`_verify_model_usage`:

    if any(str(item.get("provider") or "") != "codex_subscription" for item in usage):
        raise AdapterError("model stage used a non-Codex provider")

This is a real provenance check and must stay a check. Widen it to the provider
the adapter actually selected -- an allowlist keyed off
`SOLAR_RESEARCH_MODEL_PROVIDER` (`codex` -> `codex_subscription`,
`claude` -> `claude_subscription`) -- so a service recording something other
than what was requested still fails. Do not delete it, and do not make the
Claude service label itself `codex_subscription` to slip past; that would make
the recorded provenance a lie, which is the one thing this workflow exists to
prevent. The two sibling checks below it (`session_mode == "ephemeral"`, status
completed) need the same treatment.

Note `operator_id` is still `codex-research-evidence-synthesis-worker`. The
physical operator name is Codex-shaped even when the CLI is Claude; that is
cosmetic next to the guard but it is why the failure reads as a Codex problem.

### The open question -- do not guess this, read it

`CodexResearchModelService.__call__` ends by setting
`payload["provider"] = "codex_subscription"` and
`payload["provider_usage"] = [usage]` (codex_research.py:542-544).
`ClaudeResearchModelService.__call__` overrides `__call__` wholesale and sets
neither. The adapter also merges usage from the service's invocation journal
(`_record_invocation` writes `"provider": "codex_subscription"` at
codex_research.py:290).

Which of those two paths supplied the usage row that tripped the guard is NOT
established. If it came from the journal the provider would have read
`codex_subscription` and the guard would have passed -- so it did not, but the
actual recorded value has not been read. Read the merged
`model_provider_usage` out of a failing run before changing anything. The whole
point of this session's telemetry work is not to fix on a theory.

### Also found while reading, useful for task 2

Both stages already declare their output directory in the contract:
`evidence_synthesis` declares `artifacts/research_evidence_to_poc/synthesis/`
and `report_draft` declares `.../report/`, each `type: directory`. So a source
pack written to `synthesis/source_pack/` and a compiled report written to
`report/grounded/` are already inside declared outputs. The "operator changed
unreported files" problem the plan above anticipated may not arise at all --
verify against the actual check rather than assuming either way.

`compile_grounded_report` refuses a non-empty `output_dir` and refuses an
`output_dir` overlapping any source pack, so those two must be siblings, not
nested.

### State

Working tree clean apart from untracked run byproducts under `artifacts/` and
`harness/artifacts/autosci/`, which are outputs, not work. No source change was
made after the run started, deliberately: editing `report_draft` mid-run would
have changed what the in-flight run executed and made its telemetry
unattributable.

## Update 2026-08-19 17:42 -- the open question above is answered

Answered by reading the code path, not by re-running. The envelopes on disk are
the request side only; the usage list is built in-process and discarded when the
node fails, so there is nothing to read from the failed run itself. The path is
deterministic, so it does not need one.

### What tripped the guard

`ClaudeResearchModelService.__call__` returns the model's payload directly. The
Codex parent ends its `__call__` by setting three keys the Claude override never
sets (codex_research.py:542-544):

    payload["provider"] = "codex_subscription"
    payload["model"] = self.model
    payload["provider_usage"] = [usage]

The operator then calls `provider_usage_from(response, usage_kind="llm")`
(base.py). With none of `provider_usage` / `model_provider_usage` / `usage`
present, it falls to its final branch:

    return [{"provider": str(response.get("provider") or "injected"), ...}]

so the row reads `provider: "injected"`. That is what the guard rejected. It was
never the journal.

Worth flagging on its own: that fallback turns "the service reported no usage"
into a plausible-looking usage row rather than an error. A silent `"injected"`
is how a stage with no provenance at all passes for a stage with some.

### The more serious half, which fixing the crash would hide

`_record_invocation` is inherited unchanged and hardcodes
`"provider": "codex_subscription"` (codex_research.py:290) into the dict it
appends to both `self.invocation_usage` and `self.invocation_journal`
(codex_research.py:309-310). Every Haiku call in the killed run was therefore
journalled as a Codex subscription call.

So the adapter merges journal rows that claim Codex. Repair the crash naively --
set `payload["provider"] = "codex_subscription"` in the Claude service, or lean
on the journal rows -- and the run goes green while its recorded evidence says
Codex ran when Haiku ran. That is a worse outcome than the crash, because the
crash is loud. The guard firing was correct behaviour on a real mislabelling; it
just named the wrong cause.

### The fix, in one shape

1. Make the label an attribute rather than a literal:
   `usage_provider = "codex_subscription"` on the Codex service,
   `"claude_subscription"` on the Claude subclass, and have
   `_record_invocation` write `self.usage_provider`.
2. Have `ClaudeResearchModelService.__call__` set `provider` / `model` /
   `provider_usage` on the returned payload exactly as the parent does. Better,
   lift those three lines into a small shared helper so a future third provider
   cannot forget them -- this defect is precisely that omission.
3. Widen `_verify_model_usage` to an allowlist keyed off
   `SOLAR_RESEARCH_MODEL_PROVIDER` (`codex` -> `codex_subscription`,
   `claude` -> `claude_subscription`) so a service recording a provider other
   than the one requested still fails. Same for the `session_mode` sibling
   check, which "ephemeral" happens to satisfy for both CLIs today but only by
   coincidence.
4. Consider making `provider_usage_from`'s `"injected"` fallback raise for these
   nodes instead. A stage that reports no provenance should fail, not synthesise
   a row.

Verification: after the change, a Haiku run's merged `model_provider_usage` must
read `claude_subscription`, and pointing `SOLAR_RESEARCH_MODEL_PROVIDER` back at
`codex` must still read `codex_subscription`. Checking only that the run goes
green would pass on the broken version too.

## Correction 2026-08-19 18:50 -- the unreported-files note above is wrong

The 17:35 entry said the contract already declares `synthesis/` and `report/` as
directory outputs, so writing a pack or a compiled report inside them "may not
arise at all". That reasoning does not hold, and acting on it would waste a run.

`fixed_research_node_adapter.py:696-702` builds the allowlist from the
OPERATOR's own declared artifacts, not from the contract:

    output_paths = {str(item.get("path") ...) for item in result.get("output_artifacts") ...}
    allowed = output_paths | provider_archives | {result_rel}
    unexpected = sorted(path for path in changed if path not in allowed)

`_inventory` walks `work_dir` with `rglob("*")` and records one entry per FILE,
and membership is an exact string match. A declared directory therefore covers
none of its children. Every file `write_source_pack` emits -- `sources.jsonl`,
`evidence.jsonl`, `manifest.json`, and each file under `extracts/` -- must
appear individually in the operator's `output_artifacts`, or the node fails with
"operator changed unreported files".

That is a real constraint on task 2, not a formality, and it is the reason the
original plan called for a contract change. The contract's directory
declarations are still needed; they are just not what this particular check
reads. Enumerate the pack files from the manifest `write_validated_pack`
returns and declare each one with its sha256, the same way `write_artifact`
already does for single files.

The same applies to `report/grounded/`: `compile_grounded_report` publishes
around fifteen files, and every one of them must be declared by `report_draft`.

## Correction 2026-08-19 19:05 -- trap 3 was overstated

The earlier entry said `grounded_synthesis` hardcodes `unsupported_rate: 0.0`
and `citation_accuracy: 1.0`, so binding `evaluate_artifacts` "gives a gate that
cannot fail" and the metrics must be fixed first. The first half is true; the
conclusion is not, and the ordering it implies is unnecessary.

Those two fields are constants, so their two thresholds in `evaluate_artifacts`
can indeed never fire. But the property they would measure is enforced earlier
and far more harshly. `_compile_plan` refuses to publish anything unsupported --
it raises and aborts the whole compile on:

* `evidence_quote_missing` / `evidence_quote_too_short` / `_too_long`
* `evidence_quote_not_exact` -- the quote is not a substring of the evidence text
* `claim_not_grounded` -- no token overlap between claim and quote
* `claim_support_missing` -- a claim with no surviving link
* `claim_uncertainty_missing`

So an unsupported claim cannot reach `research_eval.json` at all. `0.0` is true
by construction rather than measured. It is still worth replacing with a real
computation from `ledger.py`, because a constant stops being true the moment the
compiler's enforcement changes, but that is hygiene, not a prerequisite.

`evaluate_artifacts` is also nowhere near inert. Beyond those two thresholds it
checks `eval_status`, all four counts, report AST sections, per-section
coverage, source diversity, source-type validation, source authority, the
profile gate, `final.md` presence and non-emptiness, evidence-citation presence,
citation grounding, and metadata noise. `compile_grounded_report` already calls
it with `strict_profile=True`, which promotes profile warnings to errors.

Practical consequence for task 2: the thing likely to stop the first wired run
is source diversity or authority under the strict profile, given how thin the
RAG pack is -- not the citation metrics. Expect that failure and read its
`errors` list rather than assuming the wiring is broken.

### Detail fix to the 18:50 entry

That entry listed `manifest.json` among the pack files. `write_source_pack`
writes no such file. It writes exactly `sources.jsonl`, `evidence.jsonl`, and
one `extracts/<source>.txt` per source, and RETURNS a manifest dict in memory
holding `sources_path`, `evidence_path`, `extracts_dir` and `provider_evidence`.

The returned dict does not enumerate the extract files, so it cannot be used
directly to declare outputs. Each `extract_path` is recorded per row inside
`sources.jsonl`. Simplest correct approach for the operator: `rglob` the pack
directory after writing and declare what is actually there, which is the same
thing `_inventory` walks and therefore cannot drift from it.

## Task 2 de-risked 2026-08-19 19:20 -- the compile chain works on real artifacts

Dry-run against the live run's own artifacts (script kept at
`<scratch>/try_compile.py`), reading `source_validation.json` and
`evidence_synthesis.json` from the sprint workdir and writing only to scratch.
No operator code was changed and the in-flight run was not touched.

    pack:  source_count 5, evidence_count 5, skipped 0, usable True
    plan:  evidence_status sufficient, 1 section, 5 claims, 0 gaps
    compile: ok, retrieval closeout pass, artifact preflight pass,
             final closeout pass, 19 files published

So `validated_pack.py` -> `synthesis_plan.py` -> `compile_grounded_report`
already works end to end on this workflow's real output. What remains for task 2
is operator wiring and output declaration, not new adapter logic.

I predicted source diversity or authority would refuse this under
`strict_profile=True`. That was wrong: it passed with
`source_authority_average 0.35` and `source_high_authority_count 0` and no
errors. Do not plan around that failure.

### Exact file counts to declare

* pack, 7 files: `sources.jsonl`, `evidence.jsonl`, and 5 `extracts/*.md`
  (one per source, so the count follows the accepted source count)
* grounded report, 19 files: `final.md`, `report_ast.json`,
  `research_eval.json`, `claims.jsonl`, `claim_evidence.jsonl`,
  `evidence.jsonl`, `sources.jsonl`, `sections.jsonl`, `section_checks.jsonl`,
  `evidence_gaps.json`, `final.bibliography.json`, `synthesis_plan.json`,
  `final_closeout.json`, `run.finalized`, and one `<source_id>-<hash>.md` per
  source

Both counts vary with source count, which is why the operator should rglob the
directory after writing rather than hardcode a list.

### The output is genuinely grounded, and it is one section long

`final.md` is 2.3KB: a Findings list where each claim carries its own
uncertainty, cites evidence by id, is marked **LIMITED SUPPORT** when it rests
on a single source, followed by an explicit evidence-boundary statement and a
DOI-bearing source list. That is a real grounded report, and it is what the
owner asked for on claim-level verification.

It is not yet a full deep research report, for one specific reason:
`build_plan` in `synthesis_plan.py` puts every claim into a single hardcoded
`"Findings"` section, so the compiler has exactly one section to render. Solar's
report shape supports many. Grouping claims into themed sections is the next
piece of work after task 2, and it belongs in `build_plan`, not in the compiler.

## Sectioning landed 2026-08-19 19:35, and what still has to follow it

`build_plan` now groups claims by a per-claim `theme` (also accepting
`section` / `section_title` / `topic`), in first-appearance order, with slugged
unique section ids. Verified against the live run's real artifacts: unthemed
input still compiles to one section with 5 claims; the same claims carrying 4
distinct themes compile to 4 sections whose headings render in `final.md`.

Grouping deliberately runs AFTER validation. A claim can still be dropped for
citing absent evidence or carrying no verified quote, and grouping first would
publish a heading with nothing beneath it.

This is inert until the synthesis operator emits a label. Two edits, both
touching files the in-flight run was still using, so they were not made:

1. `codex_research.py` `_response_schema("evidence_synthesis")` -- add an
   optional `theme` string to each claim. Note `additionalProperties: False` on
   that schema: an unlisted field is not ignored, it is refused. That is exactly
   how `evidence_quotes` came back empty for a whole day.
2. `evidence_synthesis.py` `_normalize_claims` -- carry `theme` through onto the
   stored claim. Do not invent one when the model omits it; the single-section
   fallback exists for that case.

Prompt the model to label claims by theme, not to write section prose. The
compiler owns rendering; the model's job here is grouping.

## Open finding 2026-08-19 19:50 -- report_revision preservation, first dispatch

`report_revision` failed its first dispatch with:

    {"ok": false, "error": "Revision response did not declare the exact original
     conclusion, method, and limitation preservation set"}

and PASSED on the second dispatch, so it is not blocking. Recorded because the
evidence is suggestive and incomplete, and the next person should finish it
rather than re-derive it.

What the artifacts show, from the three `report_revision` writer exchanges:

| attempt | required lims | returned lims | status | prompt vs response |
|---|---|---|---|---|
| 1 | 9 | 9 | completed | identical on all three preservation fields |
| 1 | 9 | 0 | failed | provider-level call failure, empty response |
| 2 | 12 | 12 | completed | identical on all three preservation fields |

So every completed call echoed `required_preservation` from its prompt exactly
-- same conclusion ids, same limitations, same method sha256, same order. Yet a
dispatch was rejected for not declaring that set.

The suspicion, NOT established: `verify_revision_response_preservation`
recomputes its expectation with `revision_preservation_requirements(original_report,
required_limitations=...)` rather than comparing against the
`required_preservation` block the prompt actually stated. If those two disagree,
the model is rejected for doing exactly what it was told, which is unfixable
from the model side.

Note the required limitation count GREW between attempts, 9 then 12, because the
requirement is recomputed from the evolving report. That is the mechanism most
likely to make prompt and verifier disagree.

What is missing: the exchanges all live in one shared stage directory, so they
cannot be attributed to dispatch 1 versus dispatch 2 by path. Do that by
timestamp against the two `operator-results/*/…report_revision…/result.json`
windows before concluding. Do not assume the completed att=1 call is the one the
verifier rejected -- that is the assumption this entry exists to avoid.

Also seen: one Claude CLI call failed outright and returned nothing
(`failed_calls=1`), and the operator's retry recovered. Transient provider
failure, handled correctly, worth knowing when reading call counts.

## Finding 2026-08-19 20:05 -- a failed node was gated PASS and the DAG continued

This supersedes the "open finding" entry above, which guessed at the wrong
thing. The preservation mismatch is real but it is not the important part.

`report_revision` in sprint `...dbe3550dd426`:

* dispatch 1, 22:46:43 -> 22:50:00, FAILED:
  "Revision response did not declare the exact original conclusion, method, and
  limitation preservation set"
* dispatch 2, 22:50:09 -> 23:04:14, FAILED with a DIFFERENT error:
  "operator changed unreported files: ['artifacts/research_...']"
* no third dispatch exists
* `revision/research_node_result.json` records
  `"status": "failed"`, `"status_is_terminal": true`,
  `"output_artifacts": []`, error "Claude research agent failed ... exit=1"

And yet:

* `report_revision-eval.json` -> `verdict PASS`, `gate_kind "none"`,
  `exit_code 0`, `duration_seconds 0.0`
* `status.json` -> `failed_nodes: []`, report_revision not in `open_nodes`
* the DAG advanced to `final_acceptance` (also PASS, also `kind: none`,
  also 0.0s) and then `poc_handoff`

So a node whose operator failed twice, and whose own recorded result says
`failed`, was marked PASS and the workflow carried on. The contract declares
`"evaluator_gate": {"kind": "none", "on_fail": "fail"}` for both nodes, and
`on_fail: fail` never got the chance to mean anything because nothing evaluated.

`PASS / gate_kind none / duration 0.0` is the exact signature flagged earlier in
this session as a gate that did not run. It is not merely uninformative. Here it
actively overrode a terminal operator failure.

### Why the artifacts look fine

`revision/report.md` (15KB) and `revision/report_revision.json` are dated
18:49:59 local -- written by dispatch 1, one second before it failed. A failed
dispatch leaves its outputs on disk, so any downstream check that tests file
presence passes. `required_artifacts` in the contract lists exactly
`revision/report.md`, so final_acceptance had its file and passed.

That is the same failure mode as the source relevance work: a citation to
something absent reads like a citation to something present, and here an
artifact from a failed run reads like an artifact from a successful one.

### Fix, scoped to this workflow

Give `report_revision` a `deterministic_command` gate calling
`validate_evidence_to_poc.py`, with a new `--revision-only` mode that reads
`revision/research_node_result.json` and fails when `status != "completed"`, in
addition to checking the report exists and is non-empty. Same for
`final_acceptance`. That closes the hole here without touching how any other
workflow treats `kind: none`, which is what the owner asked for.

The deeper question -- whether `kind: none` should ever auto-write PASS over a
terminal node failure, for any workflow -- is a Solar-wide governance question
and should be raised separately, not fixed by editing shared code in this task.

## Finding 2026-08-19 20:15 -- a failed provider call masks its own cause

Dispatch 2 of `report_revision` failed with a DIFFERENT error from dispatch 1,
and the second error is an artifact of the first failure rather than a new
problem:

    operator changed unreported files: [
      '.../revision/service-evidence/claude/report_revision-4418890b.../events.jsonl',
      '.../exchange.json', '.../request.json', '.../response.json']

Those four files are the recorded evidence of the Claude call that FAILED
(`exit=1`) during that dispatch. The real cause is the provider failure; what
the operator reports is an undeclared-files violation, which points at the wrong
thing entirely.

The mechanism is that provider evidence is allowed only through
`model_provider_usage`: `_normalize_provider_archives` whitelists each usage
row's `archive_path` plus every path in its `evidence_paths`. The failed
dispatch's result carried `model_provider_usage: []`, so none of the four files
was allowed.

`error_result` in `base.py:445` builds the failure result via
`build_node_result(status="failed", ...)` with no `model_provider_usage`, which
explains the empty list at the operator boundary.

What does NOT add up, and is the thing to reproduce:
`_merge_codex_invocation_usage` in the adapter exists for exactly this case --
its docstring reads "Bind every attempted Codex call, including calls hidden by
operator failure" -- and it runs unconditionally for model stages, reading
`invocation_journal` off the writer and reviewer services. The Claude service
does call `_record_invocation(status="failed", ...)` before raising, so the
journal should hold that row and the merge should have restored it.

It did not. Reproduce with a forced non-zero exit from the CLI and find out
whether the merge runs on this path, whether `services` still holds the service
objects at that point, or whether the journal is empty for another reason. Do
not fix it by widening the allowlist to any file under `service-evidence/`: that
would silence the symptom and give up the guarantee that provider evidence is
declared.

Practical impact: a transient provider failure costs two dispatches and reports
a misleading cause on the second. It is also what let the preservation failure
in dispatch 1 go uninvestigated, since dispatch 2's error looked like a
different, more alarming problem.
