# Lane 3 spec-vs-code dispositions — gate ledger + artifact manifest

**Date:** 2026-07-07 · Branch `contract/lane3-ledger` (off `contract/integration` @ c6bc47ba,
the merge of lanes 0/0.5/1/2). Companion to `opensolar-target-design.md` §1.4/§1.5 and the
round-1/round-2 review dispositions. Per the independence guards: every place the implementation
deviates from the spec's wording is recorded here with the code-verified reason — nothing was
silently adapted.

## D1 — "single status writer" implemented as audited-surface recording, not literal routing

Design §1.4 (round-1 3.1): *"set_node_status becomes the single status writer … the other
writers are routed **or audited** into it."* The literal-routing arm is not implementable
bit-identically:

- `set_node_status` has a monotonic rank guard (`_status_rank`); the real writers perform
  deliberate downgrades it refuses — `_account_eval_dispatch_failures` → `needs_human_review`
  (the in-code comment at the site already documents this), `_start_node_repair_from_eval_fail`
  → `failed_review`, reconcile's `pending` resets (which also *pop* node_results, a side effect
  `set_node_status` does not have).
- `mark_node_result` force-writes and has different `node_results`/gate side effects.

Resolution (the disposition's own "or audited" arm): every writer on the C4 surface calls the
single recording seam `gate_ledger.record_status_transition` at its write site (no-op flag-off).
AC-R4.3's audit test (`test_status_writer_surface.py`) enumerates the full surface via AST scan
— any NEW direct write outside it fails the suite — and the runtime property tests prove
no-transition-without-record, rank-guard suppression records nothing, and terminal absorbing.
Flag-off byte-parity is proven (`~/opensolar-state/run-archive/lane3-ledger/flag-off-bit-parity.diff`
— the only diff line is the sandbox tmp path embedded in a sidecar path).

## D1a — "terminal statuses absorbing" means absorbing against unrecorded/unapplied writes (round-4 G6)

AC-R4.3's wording "terminal statuses are absorbing" is implemented in
`project_node_status` as: a terminal status absorbs **unrecorded** writes
(they leave no record, so they cannot project) and **neutralized** would-be
writes (`applied: false`, the doctor-on-contract shape). Any APPLIED record —
including terminal→terminal (`passed→failed` on a real content FAIL) and
terminal→non-terminal (quota-fallback reopen) — projects, because applied
records exist only via audited writers and a projection that contradicts a
recorded write is itself a status-truth lie (the round-4 G6 finding: the
pass-only reopen rule laundered a real `passed→failed` force-write into a
stale "passed"). Disposition: **absorbing = no exit from a terminal status
without an applied audited record.** Consumers (Lane 5 dashboard endpoint)
inherit these semantics.

## D2 — author enum extended with `operator`

Design §1.4's `author.type` enum (`evaluator|doctor|policy|human|scheduler`) predates the F7
amendment that moved route records to the operatord seam. Route records are authored by the
executing operator; the enum gains `operator` for exactly that kind.

## D3 — the dispatcher guard is a structural projection compare, not a hash recompute

Design §1.2 says the guard "verif[ies] the graph matches instantiate() output … (hash check)".
Two code facts make a literal runtime hash check impossible:

- `workflow_contract._hashable_view` excludes only `status` per node; the runtime adds
  `updated_at`/`assigned_to`/`dispatch_id`/eval fields on dispatch, so any live graph re-hashes
  differently from its instantiation (false tamper alarm on every running sprint).
- `instantiate(contract, inputs)` takes arbitrary substitutions; the graph does not durably
  record `inputs`, so the reference instantiation is not reconstructible at dispatch time.

Resolution: `_workflow_contract_guard` fail-closes on (a) unregistered `workflow_contract_id`,
(b) version mismatch, (c) structural mismatch of the contract-determined node projection
against the registered contract's stages. Planner-generated contracts (`stages_mode:
planner_generated`, e.g. `pm.generic.v1`) are checked for registration+version only — their
stages are `plan_validator`'s jurisdiction per design §0. Stored-hash integrity at instantiation
time remains proven by Lane 1's golden tests.

**Compared fields (exhaustive, round-4 G4 disclosure).** Per stage/node: node-id set equality,
`depends_on` (ordered), `task_type`, `capability_capsule_id ∈ allowed_capsules` (when both
sides are non-empty), `evaluator_gate.kind`, `on_human_review` (raw compare vs the stage's
`evaluator_gate.on_human_review`; added by the round-4 fix — a tamper to `warn_and_continue`
previously passed the guard and let dependents dispatch on un-human-reviewed work).

**NOT compared (known bounds).** Substituted path fields (`write_scope`/`outputs` — they embed
unrecoverable instantiation inputs), `proof_obligations`, `acceptance`, `allowed_operators`,
`timeouts`, `dashboard_label`, `node_kind`/`logical_operator`, and the graph-level substituted
fields (`artifact_roots`, `validator_command`). A tamper limited to output paths passes the
guard; the manifest root-violation catch claimed here in earlier revisions is NOT live (see
D5a/round-4 G5) — until an observed-writes source exists, path tampers on the contracted path
are bounded only by the declared-output presence rows in the manifest, not by root blocking.

## D4 — `on_human_review` needed a second half in `ready_nodes`

Plan §2 Lane 0 (review 7.2) scopes the fix to "a per-node `on_human_review` policy consult in
the skip-propagation loop". Code fact: `ready_nodes` requires every dep `_is_passed`, so a
skip-loop-only change would leave `warn_and_continue` dependents un-skipped but never ready —
trading the skip cascade for a silent `pending` wedge, which violates R7's no-silent-wait rule.
Implemented in both places (`terminalize_dependency_blocked_nodes` + `ready_nodes`), both gated
on flag+contracted, `block_dependents`/absent = legacy, `DEPENDENCY_BLOCK_STATUSES` untouched.
Flag-off proven bit-identical even when a graph carries the field.

## D5 — manifest write/consult seams

Design §1.5 says the manifest is written "at build-complete and repair-complete" and consumed by
`_proof_artifact_presence`, evaluator support, wrapper, publish, dashboard.

- Write site implemented at the verdict seam (`node_verdict` PASS path, before the proof gate)
  — the dispatcher-observable "build complete"; a repair's next verdict cycle re-writes it with
  the new generation. There is no single earlier dispatcher point that sees final artifacts.
- Consult implemented in `_proof_artifact_presence` (manifest presence view overrides the
  filename scan; `guard_decision` keeps the scan's allow/block semantics since presence alone
  is not an "allow") and `_evaluate_proof_obligations` (root violations block regardless of
  declared obligations). The consult keys on flag + manifest-existence because the function has
  no graph access — a manifest only ever exists on the contracted path, so its existence is the
  contracted signal.
- Wrapper/dashboard/evaluator-support consumers are Lane 5 per the plan; `publish_canonical`
  ships in the module ready for the publish step.

## D5a — AC-R6.3 root-violation blocking is NOT live: no observed-writes source exists (round-4 G5, honest downgrade)

AC-R6.3 ("a node attempting to write outside declared roots is blocked and reported") requires
knowing which paths the node ACTUALLY wrote. That signal does not exist anywhere on the live
path — verified against code, option (a) of the round-4 fix order was not implementable
without inventing one:

- `operator_runtime.write_result` / operatord's result.json carry status/exit/log fields only —
  no artifact or file list.
- `capability_effects.scan_effect` matches capability evidence in narrative text — not file
  writes.
- No pre/post-dispatch workspace snapshot or write-scan exists.
- The handoff body is executor-authored narrative — using it as "observed writes" would be a
  self-reported (fake) source, exactly what R4/R6 exist to prevent.

Decision (option b): the mechanism stays parameter-driven (`write_manifest(observed=…)` builds
and `presence_map` surfaces `artifact_root_violation`, and `_evaluate_proof_obligations` blocks
on it — all proven by tests), but **AC-R6.3 is unmet on the live path**: `node_verdict` passes
no `observed=`, so production manifests always carry `violations: []`. Catalog class 21 is
downgraded `verified_here` → `partial` with the missing producer named in `pending_remainder`;
the F-CLASS-21 scenario is re-framed consult-only. Owning follow-up: whichever lane adds an
observed-writes producer (operator result artifact lists, or a post-dispatch workspace scan)
must wire it through `node_verdict` and prove AC-R6.3 end-to-end. D3's earlier claim that path
tampers are "caught downstream by the manifest root checks" is withdrawn (see the amended D3).

## D6 — `verdict_kind` default classification vocabulary

AC-R4.1: "`verdict_kind=mechanical` is set by the gate runner, not inferred from strings."
`node_verdict` gains an explicit `verdict_kind` parameter (callers state it); when absent, the
runner classifies from its OWN closed constant set `MECHANICAL_EVAL_REASONS`
(`research_eval_json_missing`, `eval_json_missing`, `eval_json_unreadable`,
`evaluator_temporarily_busy`, `eval_dispatch_unavailable`, `eval_closeout_invalid`) — a
runner-owned vocabulary, not free-text matching. Anything outside the set defaults to `content`
(fail-open toward the stricter content semantics: a content FAIL keeps its legacy effect).

## D7 — F-CLASS-13 red-mode semantics

The stale-eval **archive** behavior predates Lane 3 (714eb781): with the ledger off the node
still does not flip. The class's Lane 3 retirement — and what its `gate_replay` scenario
discriminates on — is the durable, non-consumable evidence record (`archived: true`,
`stale_reason`, fail-closed `is_gate_consumable`). Same shape for F-CLASS-30: the self-graded
*rejection* is the pre-existing 4df6477d guard; Lane 3 adds the provable provenance trail
(and closes a hole found while driving the scenario: `node_verdict`'s entry record now marks a
self-graded PASS `gate_consumable: false`).

## D8 — Lane 3 edited two Lane 2 files (additively)

The serialized-files rule assigns `run_scenario.py`/`catalog.json` to Lane 2, but Lane 2 is
complete and merged; the parallel-lanes collision concern no longer applies. Lane 3 added the
`gate_replay` mode (a new `elif` branch + `SCENARIOS_DIR` constant; existing modes untouched)
and flipped the 10 `pending_lane_3` catalog rows to `verified_here` with scenario files. The
red-green pytest gate picks them up unchanged (36 scenario-gate tests, was 16).

## D9 — ledger gate consult uses `repair_attempts` as the current generation

`_ledger_gate_verdict_block` and the AC tests take the node's `repair_attempts` as
`current_generation` when filtering consumable verdicts (matching
`_eval_payload_stale_for_current_repair`'s definition of "current"). Design §1.4 names
`eval_generation` without defining its source; this is the code's only existing generation
authority.

## D10 — writer-surface audit widened repo-wide; epic-graph writers exempted with reasons (round-4 G3)

AC-R4.3's audit was scoped to `graph_scheduler.py`/`graph_node_dispatcher.py`; the round-4
review found two unaudited direct writers on shipped paths. The audit now scans every module
under `harness/lib` for node-status writes AND `node_results` mutations (they change effective
status via `node_status()`'s fold), with an explicit per-file/per-function allowlist.

Newly recorded writers: `multi_task_runner.recover_quota_failed_nodes` (quota-fallback
terminal→pending reopen, product pool path), `research/cli._enqueue_source_audit_followup`
(terminal followup-node reopen, contracted research path), and — surfaced by the widened scan —
`evolution_engine.repair_deepresearch_gates` / `restore_nonrequired_deepresearch_repairs`
(quality-gate debt sweeps over research sprint graphs). All record through the flag-gated
best-effort seam (no-op when `SOLAR_GATE_LEDGER` is off).

Exempted with reasons (see `AUDITED_WRITERS` in `test_status_writer_surface.py`):
`task_graph_io.compile_mirror` (writes a compat mirror copy), `task_graph_io`/
`task_graph_state_io.backfill_state_from_legacy` (loaders extracting already-recorded status),
`compat/legacy_adapter.dispatch` (writes status.json, not the graph), and the epic-level
writers `epic_projection_closeout._sync_graph_from_children`,
`epic_decomposer.sync_graph_from_children`/`activate_ready` — epic graphs carry no
`workflow_contract_id` and are outside Lane 3's sprint-graph ledger scope; recording epic-node
transitions is the epic/dashboard lane's follow-up.

Known audit bounds: the scan is receiver-shaped (`node`/`nodes[...]`/`live`/`ids[...]`/
`merged`); a writer that aliases a node dict to an unrelated name evades the regex, and
mutations through a variable bound from `node_results` under a different name are likewise
invisible. The explicit allowlist review is the human backstop.

## D11 — one sprints-dir resolution for Lane-3 evidence; dispatcher keeps its source-tree fallback (round-4 G7)

Three resolvers disagreed when `HARNESS_DIR` was unset (route records could land in the live
`~/.solar/harness/sprints` while gates read elsewhere). Now all Lane-3 evidence paths resolve by
the graph_scheduler rule: `HARNESS_SPRINTS_DIR > HARNESS_DIR > SOLAR_HARNESS_DIR > install
default`. `operator_runtime._ledger_route` goes through `gate_ledger.default_sprints_dir()`;
the dispatcher's `_harness_dir()`/`SPRINTS_DIR` honor `SOLAR_HARNESS_DIR` and
`HARNESS_SPRINTS_DIR`; `operator_runtime.HARNESS_DIR` honors `SOLAR_HARNESS_DIR`.

Two honest bounds:

- **Flag-off visibility.** This is a flag-off-visible path change in the env combos that were
  previously split-brained (`SOLAR_HARNESS_DIR`-only, `HARNESS_SPRINTS_DIR` for the dispatcher):
  the modules now agree with graph_scheduler's long-shipped resolution instead of diverging
  from it. The flag-off parity driver pins `HARNESS_DIR`, where behavior is bit-identical.
- **Nothing-set combo.** With NO env set, the dispatcher still falls back to the SOURCE TREE
  (`Path(__file__).parents[1]`), not `~/.solar/harness` — a dev checkout must never write into
  the live runtime. In the installed tree the two fallbacks coincide (`~/.solar/harness` IS the
  source tree), so the residual divergence exists only in dev checkouts with no env, which the
  resolution test documents and does not exercise.

## Pre-existing reds (proven unchanged)

- `tests/harness/graph/test_multi_task_runner_status_surface.py` — collection ERROR, identical
  on the integration base (the long-known B1 red).
- `tests/harness/test_agent_actor_schema.py` — 7 fixture failures, identical set on base.
- `tests/harness/test_operatord_daemon.py` — 6–7 env-sensitive failures (singleton/lease
  contention against machine state; varies run-to-run, base showed one MORE failure than HEAD).
  Identical on the untouched `contract/lane2-harness` worktree; the scenario engine's sandboxed
  coverage of the same seams is green.

Evidence: `~/opensolar-state/run-archive/lane3-ledger/pre-existing-reds-head-vs-base.log`,
`pre-existing-red-operatord-daemon.md`.
