# Session record: research.evidence_to_poc.v1, 2026-08-20 (Claude session 2)

**Base:** `a8e9d31` (the autonomous brief) -> local HEAD, 12 commits, tree clean.
**Not pushed** per the owner's standing instruction; everything is local commits
on `claude/research-evidence-poc-vqy1cw`.

The goal from the brief: all nine done-criteria holding in one live run,
verified from artifacts. That run exists.

---

## 1. The verified green run

Sprint `sprint-20260820-102129-...-25cbc9d526a6` (run 8 of 8), on
`claude-haiku-4-5-20251001`, acquisition mode `hybrid`, request "reliability
evaluation of retrieval-augmented generation systems". Every number below was
recomputed from artifacts by an independent checker, not read from an
operator's own verdict field:

1. **Live retrieval ran at scale.** 63 candidates: 58 live from arxiv (22),
   europe_pmc (~21), crossref (~18), plus the 5-source pack. 49 accepted by
   the relevance gate (45 live), against a policy floor of 10. Every claim
   cites accepted sources only. semantic_scholar and openalex answered HTTP
   429 through this container's proxy on every trial (many trials, not one).
2. **15/15 stages passed**, every gate `deterministic_command`, non-zero
   durations, zero dispatch failures. The UAT detected the boundary itself
   and exited `status: passed` -- first time ever (see 3.4).
3. **Claim grounding recomputed independently:** 14 claims, 0 unquoted, 0
   unsupported, unsupported_rate 0.0; 3 candidate claims rejected during the
   bounded repair loop (3 attempts used).
4. **Grounded byte-verified report compiled live:** report/grounded/final.md,
   report AST, research_eval.json `passed`, 14/14 exact quote spans, 14
   themed sections. The writer's report is a real deep report (15KB, 10
   sections, quantitative findings all traceable to sources; "157 studies"
   traces to the Europe PMC scoping review that says it).
5. **Deliverable hygiene:** zero review-process sentences in the report or the
   delivery; the review's 11 process notes live in
   `review_recorded_limitations` / `review_scope_notes`.
6. **Part B ran the declared operators.** All seven Part-B stages dispatch
   through the resolver as `<node_id>_operator`; B5 executed through
   `experiment_run_worker` (scientific_lifecycle run_experiment) with a real
   sandboxed executor; B6 ran ScientificClaimVerifier's `verify_claim`.
7. **Part B tested something real:** 8/8 lineage digests AND per-claim
   grounding replication of all 14 published claims from retained bytes,
   inside `unshare -Urn`. Artifacts state `tested` and `not_tested`
   explicitly. AutoSci outcome `supports`; 14/14 verifier verdicts supported.
8. **Contradictions answered, not assumed:** the synthesis is asked, per
   claim, which validated sources disagree (verbatim-verified quotes) and
   which claim pairs conflict; `contradiction_analysis.checked: true`. This
   run found none; run 6 found and described one claim-pair tension.
9. **Every stage's production evaluator accepted** (see 3.1 for why this is
   now a criterion).

Run 6 (`...-ce69ea2193da`) also passes all nine artifact criteria; its UAT
exited dirty on the stale boundary path fixed in 3.4. The verification script
is not committed; it lived in the session scratchpad
(`verify_done_criteria.py`) and its checks are described above.

## 2. What changed (12 commits, each with its own reasoning)

- Python 3.11 compatibility (two 3.12-only f-strings on the workflow's import
  path) and two stale-test repairs.
- Live retrieval on: budget stated once in `fixed_research_workflow`
  (max_candidates 60, minimum_live_sources 10, min_contributing_providers 3),
  carried by the hash-verified policy artifact, consumed by the adapter;
  UAT `--acquisition-mode` and a provider-aware model-CLI preflight.
- Review-process commentary never ships as a scientific limitation (revision
  loop and poc_handoff seams).
- Contradiction detection and per-claim themes in the synthesis schema,
  verified with the same discipline as support.
- Grounded report compiled beside the writer's draft (contract v1.8,
  report_draft depends on source_validation).
- Part B through the resolver; `SandboxedBenchmarkExecutor`; the benchmark
  replays claim grounding; B6 runs verify_claim; a claim-less run is
  honestly inconclusive.
- Claude CLI prompt over stdin (128KB argv ceiling), structured_output
  preferred over re-parsing, and prompt steering past the CLI's misleading
  StructuredOutput tool description.
- Synthesis provider failures consume the declared retry budget and never
  discard banked grounded claims; a mistyped source id is repair feedback.
- The adapter downgrades an evaluator-rejected result to failed before
  persisting; the gate and the operator agree on what "verbatim" means; the
  UAT reads node status through the runtime-state plane and looks for the
  delivery where the contract says it is.

## 3. Four seams the live runs exposed (all the handover's pattern)

1. **Green-by-sidecar.** report_draft declared ~98 grounded files with no
   linked evidence rows; the production evaluator refused the dispatch; the
   adapter persisted the operator's own "completed" status; the node-complete
   gate trusted it and the stage passed while the refusal lived only in the
   dispatch record. Fixed twice over: evidence rows exist, and a rejected
   completed result is downgraded to failed before it is persisted.
2. **Data read as infrastructure.** That failed dispatch's stdout contained a
   retrieval limitation string mentioning "rate limited"; operator flow
   control classified it as a provider rate limit and wrote a 60-minute
   cooldown for the report-draft worker into the tracked
   `physical-operators.json`. NOT fixed in code (shared flow-control
   machinery); the registry was restored. If a failed dispatch ever prints
   rate-limit-shaped DATA again, the worker will cool down again.
3. **Two normalizers, one section.** The writer titled its method "Method:
   Evidence Synthesis and Limitations"; the limitations merge injected
   recorded limitations into it; preservation froze the mixture as the
   method; the reviewer demanded the split the retention floor forbade.
4. **The boundary the UAT could never see.** save_graph persists a spec-only
   graph; statuses live in a runtime-state sidecar. The UAT's raw JSON read
   saw "pending" forever -- the actual cause of trap 1b (polling to timeout
   after 15/15) -- and the stale `poc/final` delivery path behind it had been
   unreachable dead code.

## 4. Not verified / open

- **Codex-provider runs**: nothing here was exercised with `codex` (no CLI in
  this container). The provider seam is unchanged and guarded by tests, but a
  live Codex run since these changes has not happened.
- **openalex and semantic_scholar live**: only 429s from this container's
  egress. The providers' code paths are unchanged; their yield from another
  network is unmeasured.
- **Flow-control misclassification** (3.2) is a live landmine left in place.
- **Part B still does not run domain experiments.** The honest scope is
  stated in every artifact: lineage digests plus grounding replication from
  retained bytes; no external reproduction of the claims' subject matter.
  The extracted testable report claims remain recorded and unexecuted.
- The 16 failing tests in `harness/tests/scenarios` are pre-existing and
  identical before and after every change of this session (codex CLI absence,
  root-user and container specifics, one order-dependent flake in
  `test_p7_retrieval_dispatcher`).

## 5. What this session got wrong

- Called live retrieval done after a service-level probe; the first full run
  then surfaced the unlinked-evidence rejection, the cooldown poisoning, and
  the UAT boundary blindness. A live run remains worth more than any probe.
- Trusted "verbatim" to mean one thing; the operator and the gate computed it
  differently (whitespace) and a healthy stage was refused.
- Believed the CLI's `--json-schema` made structured output unconditional;
  Haiku declined the tool twice and answered in prose.
- Wrote a monitor with a 60-minute timeout that the harness capped at 30; a
  run finished unwatched once before this was noticed.
- The first run consumed by this session (run 1) is NOT a green run despite
  15/15 PASS gates: one stage's evaluator had said no. It is kept in the
  session record as the counterexample.
