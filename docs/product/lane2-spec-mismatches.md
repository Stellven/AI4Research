# Lane 2 — spec-vs-code mismatches (independence guard #2/#3)

**Date:** 2026-07-06 · **Author:** implementation session for Lane 2 (fake-operator scenario
harness). Per the mandatory independence guards, this file records every place the Lane 2 spec
(`opensolar-requirements.md`, `opensolar-target-design.md`, `opensolar-implementation-plan.md`,
`runtime-validation-ladder.md`) disagrees with the **actual code in this worktree**, plus the
seams that were verified TRUE. Where the spec is wrong about the code, Lane 2 is implemented
against the code's reality, not silently adapted to the doc. Guard #3: where a scenario cannot
reproduce its class through the real seam **on this branch**, that is stated here and the class is
marked, not decorated with an always-green test.

The spec-review dispositions file (`opensolar-spec-review-dispositions.md` §justifications) was
**not** consulted while writing this — the reading below is independent.

---

## 0. Working-tree / base-branch mismatch (blocks the plan's join order, not the harness)

- **Spec:** plan §0 — "Base branch: `integration/rc8-runtime-mode-contract` … Local `pkg/migration`
  is stale — do not base on it." Every lane branches off it (`contract/lane1-compiler`, etc.).
- **Code:** the active worktree is on `feat/p0-gui-react`. `git rev-list --left-right --count
  integration/rc8-runtime-mode-contract...feat/p0-gui-react` = **239 / 2** — i.e. this branch is
  239 commits *behind* the intended base and 2 ahead. The planning docs
  (`docs/product/*.md`) are **staged but uncommitted** here (index state `A`); they exist in no
  commit on any branch (`git cat-file -e <branch>:docs/product/opensolar-implementation-plan.md`
  fails for feat/p0-gui-react, integration, and contract/lane1-compiler).
- **Consequence:** the Lane 2 files authored here are net-new and self-contained (they touch only
  `harness/tools/fake_operator.py`, `tests/harness/run_scenario.py`,
  `tests/harness/scenarios/**`, `tests/harness/test_lane2_scenarios.py`, a CI job, and this doc),
  so they carry cleanly, **but the branch must be rebased onto the real base before merge** and the
  planning docs must be committed somewhere first. Lane 2's *harness* does not depend on the base
  difference; Lane 2's *green scenarios for other lanes' classes* do (see §2).

## 1. The "existing CI-safe fake-operator path" is a dry-run pane stub, not a pipeline simulator

- **Spec:** ladder P1.5 — "A CI-safe fake-operator path already exists in the rc6 install-matrix
  work — this rung generalizes it into a scenario harness"; R9 — "The full pipeline SHALL run under
  a deterministic fake-operator backend … (scripted artifacts, exit codes, delays, verdicts,
  faults)."
- **Code:** the only pre-existing "fake" operator hooks are
  `SOLAR_GRAPH_DISPATCH_FAKE_WORKERS` and `SOLAR_GRAPH_DISPATCH_FAKE_EVALUATORS`
  (`harness/lib/graph_node_dispatcher.py:5268` and `:5351`). Both are gated on `dry_run` and merely
  **fabricate tmux pane descriptors** (`{"pane": "solar-harness-lab:0.0", …}`) so worker/evaluator
  *discovery* returns something without a live tmux server. They write no artifacts, no exit codes,
  no verdicts; they do not run build → eval → repair → closeout. They are **not** referenced by
  `scripts/smoke-install-matrix.sh` (grep: no `FAKE` hit there).
- **Reality used:** the real, hermetically-testable operator seam is the **operator-pool command
  backend**:
  - `operator_runtime.submit(envelope)` (`harness/lib/operator_runtime.py:427`) validates the
    envelope, checks dispatchability, acquires a lease, writes the envelope to
    `run/operator-inbox/<op>/<task_id>.json`, and (unless `SOLAR_OPERATORD_AUTO_KICK=0`) kicks
    `operatord daemon --operator <op> --once`.
  - `operatord._build_command(config, envelope)` (`harness/tools/operatord.py:340`) runs, for
    `backend == "command"`, `bash -lc <launch_cmd>` — or, when the envelope carries a `command`,
    that command verbatim (`operatord.py:351-364`). The daemon materializes the envelope context as
    env (`SOLAR_OPERATOR_ENVELOPE_JSON`, `TASK_DIR`, `NODE_ID`, `SID`, `RESULT_PATH`, `HANDOFF`,
    `GRAPH`, `HARNESS_DIR`, `SPRINTS_DIR` — `operatord.py:275-307`), runs it as a real subprocess
    with a real timeout, captures the log, and writes `run/operator-results/<op>/<task_id>/result.json`
    via `operator_runtime.write_result` (`operator_runtime.py:648`).
  - This is **proven hermetic** by `tests/harness/test_operatord_daemon.py` (temp HARNESS_DIR,
    `submit` → `daemon --once` → assert on `result.json`; `test_command_backend_uses_materialized_dispatch_file`,
    `test_pm_dispatch_result_path_and_complete_hook`).
- **Consequence:** `fake_operator.py` is built as a **real operator worker** invoked through this
  command backend, not as a generalization of the pane stub. This is faithful to R9's intent
  (a deterministic backend that produces scripted artifacts/exit-codes/delays/verdicts) and is
  non-mock (the real dispatcher/lease/result path executes).
- **Verified TRUE (recorded for honesty):** the "command-backend operator interface" the design
  assumes **does exist** and behaves as the spec implies. The mismatch is only about *which*
  existing hook generalizes, and about how much of the end-to-end pipeline is reachable today (§2).

## 2. Lanes 1 and 3 are unbuilt — ~17 classes have no green "fixed path" on this branch

- **Spec:** the coverage matrix marks classes 01, 04, 05, 06, 07, 09, 10, 13, 16, 29, 30 (and the
  compile/ledger/manifest halves of 08/19/21/23) as SOLVED by R2 (compiler), R4 (gate ledger), or
  R6 (artifact manifest), each "verified by" a P1.5 scenario. The Lane 2 mapping expects scenarios
  04/05/07 (admission/obligation), 06/16/21 (manifest), 09/10/11/13/29/30 (ledger verdict content)
  to go green.
- **Code:** none of the retiring mechanisms exist yet. Absent on `feat/p0-gui-react`, on
  `integration/rc8-runtime-mode-contract`, and on `contract/lane1-compiler`:
  `harness/lib/workflow_contract.py`, `harness/lib/workflow_router.py`,
  `harness/lib/plan_validator.py`, `harness/lib/gate_ledger.py`,
  `harness/lib/artifact_manifest.py`, `harness/config/workflows/`.
- **Consequence (Guard #1 honesty):** for these classes the "fixed path" that would flip a scenario
  from red to green **has not been written**. A scenario asserting they are retired can only be
  shown **red** (the fault reproduces) here; it cannot be shown green until the owning lane lands.
  Writing such a scenario as passing would require the harness itself to re-implement the compiler /
  ledger / manifest — that would be testing a mock, which the no-mock rule and Guard #3 forbid.
  These classes are therefore **catalogued as `pending_lane_1` / `pending_lane_3`** in
  `tests/harness/scenarios/catalog.json` with the exact missing module named, and their scenario
  files are authored to run **red-only** (asserting current-code behavior *fails* the class), so
  that when the owning lane merges, flipping the `expect` to the retired behavior is a one-line
  change with the red half already proven. This is the plan's own discipline ("a live failure is
  converted to a fixture before its fix merges") applied honestly to lane ordering.

## 3. Deviation from "F-CLASS-01…30.scenario.json" (30 always-present files)

- **Spec:** Lane 2 file list — "`tests/harness/scenarios/F-CLASS-01…30.scenario.json`."
- **Decision (Guard #3):** only classes whose retiring mechanism is **present and exercisable on
  this branch** get a runnable `*.scenario.json` that is red-green-proven now. The remaining
  classes are recorded in a single `tests/harness/scenarios/catalog.json` with
  `status ∈ {verified_here, pending_lane_0, pending_lane_1, pending_lane_3, non_hermetic_p1_6,
  delegated_lane_6}` and the specific missing seam. Rationale: 30 JSON files that cannot run their
  class (because the fix is unbuilt) would be decorative and read as "covered" when they are not —
  the guards explicitly prefer an honest gap. The catalog is the complete 30-class ledger; the
  scenario files are the subset with real red→green evidence.
- The plan's own hermetic split is preserved and layered on top: **F-CLASS-22** (real process death)
  is `non_hermetic_p1_6`; **F-CLASS-24** (installer) is `delegated_lane_6`.

## 4. Timeout env-knob naming and layering

- **Spec:** AC-R7.5 and the Lane 2 description — "timeouts injected via the existing
  `SOLAR_*_TIMEOUT_SEC*` env knobs so scenarios run in seconds"; the per-stage field is
  `evaluator_gate.result_timeout_sec`.
- **Code:** the knob that actually bounds a running operator worker is
  `SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS` (`operatord.py:511`, suffix `_SECONDS`, default `3600`).
  On expiry the worker is SIGTERM'd, `exit_code` is set to `124`, and `result_status` becomes
  `failed_timeout` (`operatord.py:872-908`). `SOLAR_OPERATORD_RESULT_TIMEOUT_SEC` exists but is read
  only by a **different** waiter, `harness/lib/multi_task_runner.py:45`. `SOLAR_GRAPH_DISPATCH_TIMEOUT_SEC`
  belongs to the pane dispatcher. There is **no** single unified per-stage `result_timeout_sec`
  today — that is a Lane 1 contract field.
- **Consequence:** the wedge/timeout scenario (28) and the bounded-wait half of 08 inject
  `SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS` (real, verified) to run in seconds. The
  `evaluator_gate.on_capacity_unavailable=wait` / `result_timeout_sec` contract semantics
  (AC-R7.5) are `pending_lane_1`; on this branch the bounded-wait guarantee is provided by the
  operatord task timeout, which is the mechanism actually present.

## 5. Seams verified TRUE (no mismatch — recorded so the report is not all-negative)

| Claimed seam | Verdict | Evidence |
|---|---|---|
| Command-backend operator runs arbitrary command, writes `result.json` | TRUE | `operatord.py:340-395`, `operator_runtime.py:648`; `test_operatord_daemon.py::test_command_backend_uses_materialized_dispatch_file` |
| Disabled/non-dispatchable operator is unselectable at submit (class 19 / R8/AC-R8.1) | TRUE | `operator_runtime.py:469-479` raises `RuntimeError("… not dispatchable: state=disabled")` |
| Duplicate active lease rejected → single-flight (class 12 / R4) | TRUE | `operator_runtime.py:205-216` raises `"Duplicate active lease rejected"` |
| Bounded operator timeout → classified terminal (classes 28/08-hang / R7) | TRUE | `operatord.py:872-908` → `exit 124`, `failed_timeout` |
| Auth-absent / quota → flow-control state (classes 20/27 / R7/R8) | TRUE | `operatord.py:984-999` + `operator_flow_control`; `test_operatord_daemon.py::test_failed_auth_task_sets_auth_expired`, `::test_failed_quota_task_sets_cooldown` |
| Kill/SIGTERM mid-run → draining + final status, route/result recorded (class 17 / R5/R7) | TRUE | `operatord.py:574-594`; `test_operatord_daemon.py::test_signal_leaves_final_status` |
| Result carries `model_route` (provider/model/backend) for route proof (class 18 / R5) | PARTIAL | `write_result` records `model_route` (`operator_runtime.py:681-687`) but there is **no append-only `kind: route_record` ledger** yet — that is R5/AC-R5.1, `pending_lane_3`. Route facts exist per-result; the ledger does not. |
| `physical-operators.json` shipped default | ALREADY PRESENT | exists on feat/p0-gui-react and integration; `contract/lane0-spine` evolves it (v2 schema draft). Lane 2 writes its own hermetic registry regardless. |

---

## Net effect on the Lane 2 mapping table

`verified_here` (real red→green through the operator-pool command backend, this branch): the
operator-execution / lease / supervision / route-fact families — **08** (zero-evaluator + busy
singleton bounded-wait), **12** (duplicate-lease single-flight), **17** (kill-mid-run leaves a
result/route fact), **19** (disabled-operator unselectable), **20** (auth-absent), **27**
(no-capacity/quota), **28** (wedge timeout classification). These retire via mechanisms already in
`operator_runtime.py` / `operatord.py`.

`pending_lane_1` (needs the compiler/router/validator): **01** (byte-identical golden), **02/03**
(routing), **04** (task_type admission), **05/07** (obligation legality), **11** (content gate),
**25/26** (validator token/wording). `pending_lane_3` (needs the ledger/manifest): **06**
(manifest discovery), **09/10** (mechanical-vs-content), **13** (stale generation), **16/21**
(artifact roots), **23** (parent-status truth), **29** (critic-block-vs-passed), **30** (backfilled
non-consumable). `pending_lane_0`: the allowlist half of **19** (spine). `non_hermetic_p1_6`:
**22**. `delegated_lane_6`: **24**.

The full 30-row ledger with the precise missing module per class lives in
`tests/harness/scenarios/catalog.json`.
