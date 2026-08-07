# Lane 4 — spec/code mismatches and dispositions

**Date:** 2026-07-07 · **Branch:** `contract/lane4-deepdive` (off `contract/lane3-ledger` @ `e9d5b856`).
Per the lane independence guards, every place the implementation deviates from the spec wording, or
depends on a code fact the spec did not state, is recorded here with its disposition — nothing was
silently adapted. Companion to `lane4-deepdive-parity-report.md` (vendor provenance) and
`rsi-deepdive-workflow-lock.md` / `opensolar-target-design.md` §1.8.

## L1 — vendor source: the mirror compiler is newer than the codex ref

Design §1.8 names the mirror `main @ e2480290` as primary and the `upstream/codex/*` refs as
cross-check. The two compiler blobs differ by exactly two lines the **mirror adds** on insight
(`D10–D18`) nodes (`gates` / `verification_gates`). Chose the mirror (primary, newer, more complete).
The delta is inert for the demo (`insight_mode=False`). Full per-file provenance + blob hashes in the
parity report. **Disposition:** accept mirror; documented.

## L2 — the compiler's committed test lives only on the codex ref

The prompt/design say to vendor "its committed tests." The mirror @ e2480290 ships **no**
`test_deepdive_requirement_compiler.py` (only `test_figure_grounding.py`, already vendored here). The
test exists on `upstream/codex/evaluator-control-plane`
(`tests/harness/research_survey/test_deepdive_requirement_compiler.py`) and is byte-identical to what
the mirror compiler needs. **Disposition:** ported the test from the codex ref (recorded in the parity
report); it runs green (9 tests) against the mirror compiler because the only delta is insight-node
keys the test does not assert.

## L3 — `validate_rsi_demo_report.py` was absent on the Lane 3 base

Design §1.8 says to locate it ("may exist only on feat/rc8-demo-golden-path"). It is absent on this
base. **Disposition:** ported byte-identical from `feat/rc8-demo-golden-path`. Ported **only** the
copied-workspace report validator, not the source-pack validator (`validate_rsi_source_pack.py`) or
`demo-rsi/source-pack/` — those gate the offline seed pack (a live-run input), not the adapter's
output, and are out of Lane 4's deterministic scope. The ported test drops the two source-pack cases
and keeps every report-validator case (22 tests).

**Round 5 hardening delta:** the original byte-identical validator counted raw rows for the minimum
source/claim gates. The reviewer duplicate-id probe showed one repeated source id and one repeated
claim id could satisfy those gates. Lane 4 now intentionally deviates from the historical validator:
`sources.json` and `claims.json` must contain non-empty unique ids, duplicate ids are validation
errors, and the minimum gates count unique ids. This is a safety improvement over the faithful port,
not evidence that the original port was inaccurate.

## L4 — the adapter builds the report body from `sections.jsonl`, not `final.md`

Design §1.8 says the adapter "maps native jsonl exports → the five demo artifacts." The report body
could come from the monolithic `final.md` or from the per-section `sections.jsonl`. **Decision:**
assemble `report.md`/`report.html` from `sections.jsonl` (the structured, builder-authored per-section
content), falling back to `final.md` only when no sections exist. Rationale: this is the concrete
F-055 bypass (memory `deepresearch-synth-hardcoded-content`) — the engine's `cli.py` synthesizer emits
a hardcoded boilerplate `final.md` body regardless of topic; consuming the structured section rows
avoids that surface entirely and the adapter never imports/invokes the synthesizer. **Disposition:**
documented deviation; `test_report_derives_from_native_content_not_boilerplate` locks it.

## L5 — `claims.json.source_id` is a derived join, not a native field

Code fact the spec did not state: native `claims.jsonl` rows carry **no** `source_id` (columns:
`id, claim_text, claim_type, stance, confidence, section_ref, content_hash`). The validator, however,
requires every claim to link to a valid `source_id`. **Disposition:** the adapter derives it via the
real join `claim.id → claim_evidence(claim_id) → evidence(id).source_id`, picking the strongest link
(max `strength`, tie-break earliest `claim_evidence` line). Claims that resolve to **no existing**
source are **dropped and recorded** in the manifest's `dropped_claim_ids` — never mislinked to a
fallback (that would fabricate provenance). `test_unresolvable_claims_are_dropped_not_mislinked` locks
it.

## L6 — the "D-graph golden" is the native compiler DAG; Lane 1 owns the contract-instantiate golden

The prompt phrases the golden as "instantiate `research.deepdive.rsi_demo` … and commit the golden;
assert the compiler's output is admissible." Lane 1 **already** committed the contract-instantiate
golden (`tests/harness/workflow_contract/goldens/research.deepdive.rsi_demo.instantiated.golden.json`).
Re-committing it in Lane 4 would duplicate. **Disposition (interpretation, documented):** Lane 4's
distinct golden is the vendored front-end's native `build_deepdive_evidence_dag` output
(`deepdive_dgraph.golden.json`) — the "D-graph" (D1–D9), byte-stable — and Lane 4 separately **asserts
admissibility**: the shipped contract `compile_checks == []` under the real registries, the Lane 1
remap is load-bearing (D2→`audit_inventory` is rejected `TASK_TYPE_NOT_ADMITTED`), and the shipped
D1–D6 operators are a subset (compression) of the native D1–D9. This ties the vendored compiler to the
shipped contract without duplicating Lane 1.

## L7 — the eval-artifacts "good" fixture is tuned to pass the *full* engine gate

`research eval-artifacts` (`research.evaluator.evaluate_artifacts`) is strict: per-line citation
grounding (token overlap, hyphenated words kept whole by `TOKEN_RE`), ≥220-char sections with ≥1
citation, source-type diversity, and a passed `research_eval.json` status. **Disposition:** rather than
loosen thresholds or hand-write a synthetic payload, the fixture's seed data (`native_fixture_builder`)
is authored so a **real** engine export genuinely passes the gate (`ok=True`, zero errors). Two
warnings remain and are non-blocking by design: `section_coverage_low_analysis_density` (the demo
prose is deliberately plain) and `source_type_validation_invalid` (the engine's stricter label set);
neither affects the pass verdict. The "bad" fixtures inject genuine content flaws (`thin_section`,
`dangling_citation`) that the real gate rejects.

## L8 — `compile_checks` provider policy is a dict, not a list

Code fact: `resolve_role_operators` reads `provider_policy["allowed_providers"]`, so the run policy
must be a dict. The tests pass the shipped contract's own `provider_policy` object (and also the
`None` unconstrained case). **Disposition:** documented; no code change (this is the Lane 1 API).

## Respected boundaries (no-touch-list)

- **No dispatcher/scheduler/engine edits.** The vendored compiler + adapter are additive, and
  **inert**: `harness/lib/research/__init__.py` is untouched, so `import research` never imports the
  new modules. Adjacent regression (`workflow_contract + gate_ledger + lane2 + research_unit`) is
  **468 passed before and after** the vendor; the full combined set (with all new suites) is **521
  passed**. No `graph_scheduler.py` / `graph_node_dispatcher.py` / `operator_runtime.py` diff.
- **No new `SOLAR_DEMO_REPORT_MODE` engine conditionals** (no-touch §9): the adapter is a plain module
  invoked explicitly; behavior comes from contract fields + native data, not env branches.
- **No mirror dependency in any CI gate** (design 9.1a): compiler, brief expander, profiles, tests,
  and the isolation doc are all vendored in-repo.

## Pre-existing reds (proven unchanged, not chased)

Identical to the Lane 3 base (`lane3-spec-mismatches.md`), and I edited none of these files:
`tests/harness/graph/test_multi_task_runner_status_surface.py` (collection ImportError — B1),
`tests/harness/test_agent_actor_schema.py` (7 failed), `tests/harness/test_operatord_daemon.py`
(6 failed, env-sensitive). Evidence: `~/opensolar-state/run-archive/lane4-deepdive/`.
