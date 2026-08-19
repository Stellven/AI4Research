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
