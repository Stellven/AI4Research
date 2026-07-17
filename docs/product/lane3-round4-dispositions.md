# Lane 3 round-4 fix-round dispositions

**Date:** 2026-07-07 · Branch `contract/lane3-ledger`, fix-round appended on `e9d5b856`
(commits `19001c66..ca53a555`, 8 commits, append-only — no rebase; Lane 4's
`contract/lane4-deepdive` is based on `e9d5b856` and must merge this fix-round before its
contract gates and before P2).

Work order: `~/opensolar-state/run-archive/lane3-ledger/round4-review-findings.md` (9 findings,
each with an ▶EXECUTED probe). Method: every probe reconstructed verbatim as a red test/probe
BEFORE the fix; before/after probe logs archived under
`~/opensolar-state/run-archive/lane3-ledger/round4-probes/`
(`before-20260707T144307Z.log` at `e9d5b856`, `after-20260707T151641Z.log` at `ca53a555`).

| id | sev | disposition | fix commit | red-first evidence |
|----|-----|-------------|-----------|--------------------|
| G1 | High | **FIXED** — mechanical hold gates on the RECORDED pass (`node_recorded_status` + ledger projection), not the downgraded effective status; F-CLASS-10 driver/scenario now assert the v5 shape (fault still discriminates: legacy terminally fails it) | `5b1e307b` | probe case B/B′ reproduced as failing `test_v5_shape_*` in `test_ac_r4_replays.py`; after-log: all three cases held, verdict archived non-consumable |
| G2 | Med | **FIXED** — `_ledger_gate_verdict_block` blocks only on content records; `human_verdict` always blocks; kind-less keeps the stricter content effect (D6) | `e4ce5f4d` | failing `test_mechanical_fail_record_does_not_block_gate` / `test_infrastructure_…`; after-log: mechanical/infra `blocked=false`, content/human `blocked=true` |
| G3 | High | **FIXED** — `recover_quota_failed_nodes` (pool) and `_enqueue_source_audit_followup` (research) record through the flag-gated seam; widened repo-wide scan also surfaced `evolution_engine`'s two sweep writers (recorded) and two closeout-script false positives (allowlisted with reasons); audit now scans all of `harness/lib` for status writes AND node_results mutations with an explicit per-file/function allowlist (D10) | `9288e40b` | stash-proof `round4-red-g3-writer-surface.log` (7 failures against pre-hook lib); after-log: both reopens leave `status_transition` records |
| G4 | Med | **FIXED** — guard compares `on_human_review` (raw vs the stage's `evaluator_gate.on_human_review`); flip AND delete fail closed; D3 amended with the exhaustive compared-field list and honest NOT-compared bounds | `d9e33e7a` | failing `test_tampered_on_human_review_trips` / `test_removed_…`; after-log: tamper → 3 structure-mismatch errors |
| G5 | Med-High | **HONEST DOWNGRADE (option b)** — no real observed-writes source exists (result.json has no artifact list; `scan_effect` is narrative matching; no workspace scan; the handoff is executor-authored — a fake source was rejected). Catalog class 21 `verified_here` → `partial` with `pending_remainder` naming the missing producer; F-CLASS-21 re-framed consult-only (red-green pair kept for the consult half); D5a records the gap + owning follow-up; AC-R6.3 is **unmet on the live path** | `ca53a555` | probe shows `dispatcher_passes_observed=false`, live `violations=[]` (unchanged mechanically — that is the honest state) + catalog row now partial |
| G6 | Med | **FIXED** — projection folds every APPLIED record (incl. terminal→terminal and terminal→non-terminal); absorbing = no exit without an applied audited record (against UNRECORDED and `applied=False` only); F-CLASS-23 (unrecorded lie) and F-CLASS-09 (`applied=False` clobber) still discriminate; D1a reconciles AC-R4.3's wording | `10532576` | failing `test_projection_applies_recorded_passed_to_failed`; after-log: direct `passed→failed` projects `failed`, `applied=False` still absorbed |
| G7 | Med | **FIXED** — one resolution rule (`HARNESS_SPRINTS_DIR > HARNESS_DIR > SOLAR_HARNESS_DIR > install default`): `_ledger_route` → `gate_ledger.default_sprints_dir()`; dispatcher honors `SOLAR_HARNESS_DIR`/`HARNESS_SPRINTS_DIR`; `operator_runtime.HARNESS_DIR` honors `SOLAR_HARNESS_DIR`. Dispatcher nothing-set fallback stays the source tree (never `~/.solar`) — bounds + flag-off visibility in D11 | `57f1a2a9` | failing 4-combo subprocess test `test_sprints_dir_resolution.py`; after-log: all four combos `all_agree=true` inside the sandbox |
| G8 | Low-Med | **FIXED** — `submitted` route record appended only after the auto-kick block succeeds (kick and no-kick paths keep AC-R5.1 evidence; bootstrap failure leaves none) | `6d2836f7` | failing `test_submit_bootstrap_failure_leaves_no_untruthful_submitted_record`; after-log: `untruthful_submitted_survives=false` |
| G9 | Low | **FIXED** — `is_gate_consumable` fails closed: absent `eval_generation` + supplied `current_generation` ⇒ non-consumable. Note for future writers: `human_verdict` records must stamp `eval_generation` to be consumable on repaired nodes | `19001c66` | failing `test_missing_generation_with_current_generation_not_consumable`; after-log: `no_generation_current_5=false` |

## Exit-gate evidence (all at `ca53a555`)

- **Probes:** all nine reconstructed reviewer probes re-executed —
  `round4-probes/before-…Z.log` (every finding reproduced at `e9d5b856`) vs
  `round4-probes/after-…Z.log` (every finding shows the fixed/honest behavior).
- **P1.5 re-run (env-pinned `HARNESS_DIR=$PWD/harness SOLAR_HARNESS_DIR=$PWD/harness`):**
  `gate_ledger/` 117 passed (was 85; +32 fix-round tests) · `test_lane2_scenarios.py` 36 passed ·
  `workflow_contract/` 105 passed · `supervision/` (`SOLAR_P16_REAL_PROCESS=1`) 48 passed ·
  full `graph/` dir 278 passed with the IDENTICAL 18-test pre-existing failure set as
  `e9d5b856` (diffed) · pre-existing reds unchanged: `test_multi_task_runner_status_surface.py`
  collection error, `test_agent_actor_schema.py` 7, `test_operatord_daemon.py` 6 —
  base-vs-head failure sets diffed IDENTICAL. Log: `round4-fix-final-gate-20260707T152215Z.log`.
- **Flag-off bit-parity:** original `flag_off_parity_driver.py` PLUS a round-4 extension
  (`flag_off_parity_driver_r4.py`: the newly-hooked `multi_task_runner`/`research/cli`/
  `evolution_engine` paths and both `submit()` paths) run on HEAD vs the `e9d5b856` lib —
  **zero non-sandbox-path diff lines** on both. Evidence: `round4-flag-off-bit-parity.diff`.
  Honest bound: G7 is flag-off-VISIBLE in env combos the parity driver does not pin
  (`SOLAR_HARNESS_DIR`-only, `HARNESS_SPRINTS_DIR` for the dispatcher) — that is the fix
  (alignment with graph_scheduler's shipped resolution), disclosed in D11.

## P3-validity precondition, post-fix

The round-4 review correctly found the precondition ("Lane 3's verdict-content + provenance
rules are active on the real path") NOT met at `e9d5b856`. Post-fix: R4's guarantees
(mechanical-hold on the real v5 shape, verdict-kind-aware gate consult, repo-wide audited
writer surface, truth-mirroring projection) and R5's route-record truthfulness hold as tested.
**AC-R6.3 remains explicitly unmet on the live path** (G5 downgrade, class 21 partial) — P3
claims must not rely on root-violation blocking until an observed-writes producer lands.

## Sequencing

- **Lane 4** must merge this fix-round (`19001c66..ca53a555`) before its contract gates and
  before P2 — its base `e9d5b856` carries all nine findings.
- **Lane 5** must re-run its endpoint tests against the G6-fixed projection semantics
  (`project_node_status` now folds every applied record; see D1a) and inherit D11's sprints-dir
  resolution.
