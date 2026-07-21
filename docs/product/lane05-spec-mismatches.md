# Lane 0.5 — spec/code mismatches and clarifications

**Date:** 2026-07-06 · **Branch:** `contract/lane05-supervision` (off `contract/lane0-spine`).
Per the lane ground rules, nothing here was silently absorbed into the implementation; every item
below is either encoded fail-closed or deferred to its owning lane with the decision documented.

## M1 — The watchdog is harness-global; design §1.9 assumes run-scoped supervision

`coordinator-watchdog.sh` has no run-id concept: one daemon supervises the whole harness, and its
respawn sites (`do_check` coordinator restart, `check_panes` pane respawn, `ensure_tmux_sessions`
rebuild) act on "the active sprint" resolved from `.pane-assignments` / newest actionable
`*.status.json`. The registry's terminal marker is per `run_id`.

**Resolution encoded:** `run_process_registry` treats the sprint sid as the run id (same convention
the wrapper and sprints dir use). The watchdog call-site hook (Lane 0 stub) must resolve the active
sid exactly the way its wake logic already does, then gate respawn on
`run_process_registry.py is-terminal --run-id <sid>`. If no active sid resolves, respawn behavior is
unchanged (fail-open for the global harness, fail-closed per run) — flag this at Lane 0 review.

## M2 — `workflow_contract` (Lane 1) does not exist on this base; its compile API is undefined

Design §1.6 requires "contract compile if contracted". Lane 1's `harness/lib/workflow_contract.py`
is not on `contract/lane0-spine` (also observed by Lane 2). `check_contract_compiles` therefore
fails closed when a contract is requested and the module is missing.

**Addendum (same day):** Lane 1 landed on `contract/lane1-compiler` with the real API
`load_contract(path)` (raises `ContractSchemaError`) + `compile_checks(contract, capsule_registry,
operator_registry, provider_policy=None)` (empty list ⇔ compiles). Preflight now calls exactly that
API when present (verified against the Lane 1 branch source; deterministic tests fake the API in
`sys.modules` since the module is on a sibling branch), with a generic single-arg entrypoint probe
kept as an API-drift fallback — every path stays fail-closed. A cross-branch integration run of
`check_contract_compiles` against the real module happens when the lanes merge.

## M3 — Provider policy is captured at import time in `multi_task_runner`

`DEFAULT_OPERATOR_PROVIDER_ORDER` reads `SOLAR_MULTI_TASK_DEFAULT_PROVIDERS` once at module import
(harness/lib/multi_task_runner.py:1025). A long-lived process that mutates the env after import
diverges from preflight, which re-reads the env at call time (`run_preflight._provider_policy`,
identical parsing). Not fixed here (that constant is Lane 3 dispatcher territory under the
serialized-files rule); documented so a policy-flip-without-restart is a known hazard.

## M4 — Preflight reuses private selector helpers

Design §1.6 lists "backend CLI present" under operator health. The real logic lives in private
helpers `multi_task_runner._operator_backend_runnable` and `_operator_ref`. Preflight calls them
rather than duplicating (duplication is how the five-authorities drift started). If a later lane
renames them, `check_role_routes` fails closed with `selector modules unavailable` rather than
passing silently. Accepted trade-off; owner may ask Lane 3 to promote them to public names.

## M5 — Sprints-dir env name split (shell vs python)

Shell (`coordinator-watchdog.sh`, wrappers) exports `SPRINTS_DIR`; the python lib reads
`HARNESS_SPRINTS_DIR` (harness/lib/multi_task_runner.py:54). `run_preflight.sprints_dir` honors
`SPRINTS_DIR` first, then `HARNESS_SPRINTS_DIR`, then `$HARNESS_DIR/sprints`, so both call-site
families land the report in the same place. Unifying the names is a candidate Lane 0 cleanup.

## M6 — AC-R7.4 "zero surviving processes" vs zombies (P1.6 discovery)

Found red-first at the P1.6 real-process tier: a killed-but-unreaped child (zombie) still answers
`kill(pid, 0)`, so a literal reading of "zero surviving run-scoped processes" counted already-dead
children as survivors whenever the registering parent (wrapper) had not reaped yet. The registry's
liveness predicate (`_running`) treats zombies as exited. This is a clarification of AC-R7.4, not a
weakening: a zombie holds no runtime resources and cannot respawn anything.

## M7 — CLI naming collision risk: `preflight` vs `preflight-run`

`solar-harness.sh` already has `preflight|launch-preflight` (launch-dependency check,
solar-harness.sh:3189). Design §1.6's CLI is `solar-harness preflight-run`. The Lane 0 stub must use
`preflight-run` exactly and must not touch the existing `preflight` verb; this lane ships only the
python CLI (`python3 harness/lib/run_preflight.py`), no shell wiring.

## Coverage note (plan → tests)

Plan scenarios "20/27" (F-CLASS-20 auth preservation, F-CLASS-27 no-live-workers) are covered
deterministically in `harness/tests/supervision/test_run_preflight.py`; F-CLASS-21 (installed-harness
contamination) by the path-consistency tests; F-CLASS-22/28 (process residue, supervision faults) by
the registry tests plus the opt-in P1.6 real-daemon proof (`SOLAR_P16_REAL_PROCESS=1`). The Lane 2
fake-operator scenario harness can wrap these as taxonomy scenario files when the catalogs merge.
