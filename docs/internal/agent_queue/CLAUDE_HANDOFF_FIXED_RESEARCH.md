# Claude handoff: finish the fixed Solar research-to-PoC UAT

Paste the following task into one Claude Code session. Work single-threadedly;
do not create subagents.

## Objective

Continue the existing isolated implementation until it has a real dashboard-
created local UAT, frozen-source Docker build/UAT, and an evidence-backed
apply-back to the main development worktree. Do not redesign the dashboard or
replace Solar Harness with a standalone script.

## Worktrees and authority

- Implementation worktree:
  `/home/ssubr/openjiuwen-solar-integration/autosci-fixed-workflow/wt-evidence-to-poc`
- Branch: `task/research-evidence-to-poc-fixed`
- Base: `7302ab2ba0bba261b539e0e5d1d55068d33c59fb`
- Apply-back target only after every acceptance gate passes:
  `/home/ssubr/openjiuwen-solar-integration/fix-issues/issue-9/repo`
- The apply-back target is currently clean at `4d60f1e03` but 152 commits
  behind implementation base `7302ab2ba`. Do not cherry-pick the feature onto
  that stale tree. First establish and record the intended fast-forward/base
  update; then apply the reviewed feature commit and rerun tests in the target.
- Read first:
  `/home/ssubr/openjiuwen-solar-integration/STATE.md`
  and
  `docs/internal/agent_queue/TASK_RESEARCH_EVIDENCE_TO_POC_CODEX_FULL.md`.
- Preserve all current tracked/untracked work. Never reset, checkout-over,
  clean, or delete it. Do not push.

## Architecture that must remain

Solar owns the router, fixed TaskGraph, exact worker assignment, operator
runtime/operatord, evaluator, ledger, state, dashboard projection, and final
acceptance. The registered v1.3 contract has exactly 15 visible nodes:

`seed_fetch -> source_discovery -> source_validation -> evidence_synthesis ->
report_draft -> independent_review -> report_revision -> final_acceptance ->
poc_handoff -> idea_evaluation -> experiment_design -> experiment_approval ->
experiment_run -> claim_verification -> final_delivery`.

A1-A3 and deterministic A8/B nodes are exact command-backed AutoSci/Solar
workers. A4-A7 are fresh schema-bound Codex subscription workers. B5 executes
the repository-owned `unshare -Urn` no-network integrity benchmark. The typed
policy `evidence_lineage_integrity_v1` authorizes that exact fixed benchmark so
the user sees no B4 pause. No generic worker fallback, Planner topology,
nested AutoSci scheduler, fixture result, mock acceptance, or manual node state
editing is allowed.

## Current evidence

- Frozen five-paper source pack:
  `artifacts/dashboard-uat-input-20260818/source-pack`
- Freeze manifest:
  `artifacts/dashboard-uat-input-20260818/freeze-manifest.json`
- Real public retrieval preflight:
  `artifacts/preflight-public-retrieval-20260818`
  (Semantic Scholar 429; OpenAlex 12; raw provider bytes retained).
- Negative real dashboard run and screenshots:
  `artifacts/dashboard-local-uat-20260818`
  (stale installed launcher created an Epic; preserve as failure evidence).
- Corrected dashboard-intake-function proof:
  `artifacts/dashboard-intake-function-r4-20260818`
  with sprint
  `sprint-20260818-145954-wf-research-evidence-to-poc-v1-612084df5346`.
- Latest reproducibility manifest:
  `artifacts/source-freeze-preflight-r7-20260818/uat/entry-manifest.json`
  (35 load-bearing files, including the dashboard projection route; canonical
  inventory digest
  `bbb02687099c02cdf8930624e7fd6adc2c078b3b0c74086171791a7951966984`).
- The corrected retained sprint now projects A1 as `dispatched/active`, with
  exact worker `autosci-research-synthesis-seed-fetch-worker`, exact capsule
  `cap.research-seed-snapshot`, no false missing-capability warning, and route
  decision `fixed_contract_binding`.
- Latest focused validation: `179 passed, 105 warnings`; the immediately prior
  broader fixed/dashboard set was `186 passed, 86 warnings`. Superseded
  2026-08-18: the fixed/dashboard/contract/uat set is `340 passed` after the
  four dashboard-to-final corrections.
- 2026-08-18 fresh dashboard runs, newest last:
  `artifacts/dashboard-full-uat-20260818` (attribution defect),
  `-r2-` (intent gateway defect), `-r3-` (human-search diversion),
  `-r4-` (transient poll tick), `-r5-` (A1-A3 PASS, A4 Codex quota blocked).
  Start from `artifacts/dashboard-full-uat-r5-20260818/RUN-SUMMARY.md`.

## First commands

From the implementation worktree:

```bash
git status -sb
git diff --check
PYTHONPATH=harness/lib:harness/tools python3 -m pytest -q \
  tests/harness/workflow_contract/test_fixed_research_workflow.py \
  tests/harness/tools/test_fixed_research_uat.py \
  tests/harness/test_status_server_deliverables.py
```

Confirm the Docker daemon before planning any build. Superseded 2026-08-18:
`docker` on PATH resolves to the Windows Docker Desktop shim and fails because
Desktop's WSL integration is off, but a native Linux Docker Engine installed via
snap is running. Use `/snap/bin/docker version` (server 29.6.1 linux/amd64 on
`/var/run/docker.sock`). Still do not claim a container test without an actual
run against that daemon.

## Fresh dashboard UAT

Use a new evidence root; never reuse or patch the prior runs. Start the real
`harness/lib/symphony/status-server.py` with:

- `HARNESS_DIR=<worktree>/harness`
- `HARNESS_SPRINTS_DIR=<new-root>/sprints`
- `SOLAR_INTENT_GATEWAY_DIR=<new-root>/intents`
- `SOLAR_INTAKE_WORKSPACE_ROOT=<new-root>/workspace`
- `SOLAR_KNOWLEDGE_RAW_DIR=<new-root>/knowledge`
- `SOLAR_DASHBOARD_RESEARCH_PROFILE=fixed_hybrid_demo_v1`
- dashboard source pack/root pointing to the retained frozen pack
- actor `user`
- policy statement describing the fixed no-network benchmark
- Codex runtime/operator registry/state variables from the current task doc.

Open the existing React dashboard with the repository gstack browser, submit
the full RAG-evaluation research + PoC prompt through the actual form, and
capture before/after/final screenshots. The returned sprint must be
`research.evidence_to_poc.v1` v1.3—not an Epic.

Drive the dashboard-created sprint only with:

```bash
python3 harness/tools/fixed_research_uat.py dashboard-to-final \
  --evidence-root <new-root> \
  --request-id <dashboard-request-id> \
  --runtime-harness "$PWD/harness" \
  --workspace-root <new-root>/workspace \
  --codex-home "$HOME/.codex" \
  --status-url http://127.0.0.1:<port> \
  --policy-actor user \
  --policy-statement 'Run the fixed evidence-lineage benchmark without a visible approval pause; network is disabled for the benchmark.'
```

This driver may issue only public Solar graph-dispatch commands and poll
durable state. It must not create intake, inject artifacts, or edit node state.

## Acceptance gates

Require all 15 nodes durable PASS and consistent graph/status/evaluator/ledger/
manifest state. Require A2 real public provider attempts and raw hashes; A3 at
least three accepted live task-related sources plus the frozen pack; A4-A8 a
source-linked report, separate independent review, retained limitations, and
accepted final evidence; B1 exact accepted-Part-A handoff; B3 exact plan; B4
policy-derived approval; B5 real `unshare -Urn`, network disabled, raw/stdout/
stderr/timing/metrics; B6 four-artifact reconciliation; B7 identical JSON/MD
limitations and final bundle. The dashboard must show progress and expose the
declared final delivery.

After local success, freeze the exact source tree/manifest, build a dedicated
Docker UAT image without secrets baked in, mount a container-private read-only
Codex auth copy and evidence output, submit through the container dashboard,
and repeat the same acceptance gates. Preserve the container/image/source
identity and screenshots.

Only then review every diff file, exclude `.gstack/`, `artifacts/`, and private
agent/task notes from the product commit, commit the isolated branch, apply the
approved commit(s) to the target worktree, and rerun relevant tests there.

## Required final report

Use exactly: 已完成 · 已验证 · 未验证 · 风险 · 后续待办. Include commands,
results, evidence paths, changed-file purposes, Docker image/source identity,
and apply-back commit IDs. Any missing gate remains 未验证; do not say done.

## 2026-08-18 checkpoint: environment unblocked, four defects fixed

Read `artifacts/dashboard-full-uat-r5-20260818/RUN-SUMMARY.md` first. It has the
full failing payloads and evidence paths for everything below.

### The two blockers listed further down are stale

- **Docker works.** `docker` on PATH is the Windows Docker Desktop shim and
  fails, but a native Linux Docker Engine is installed via snap and running:
  client and server 29.6.1 linux/amd64 on `/var/run/docker.sock`, user in the
  `docker` group. Use `/snap/bin/docker` explicitly, or put `/snap/bin` ahead of
  the Windows path. Docker Desktop is not needed.
- **Loopback binding works.** `tests/harness/test_s04_orchestration_routes.py`
  now passes 14/14; the previous `PermissionError` is gone.

### The dashboard front door works

Five real runs through the actual React form and the real status server. Every
one created a genuine `research.evidence_to_poc.v1` v1.3 sprint, 15 fixed nodes,
`fixed_topology: true`, `single_threaded`, verified source-pack authority, bound
intent. None produced an Epic.

`artifacts/dashboard-full-uat-r5-20260818` reaches:

```
seed_fetch         passed
source_discovery   passed   (58s, real public providers)
source_validation  passed
evidence_synthesis blocked  (Codex quota)
```

### Four defects fixed in the previously-unexercised dashboard-to-final path

1. Intake never stamped the dashboard request id on the sprint status, so the
   sprint could not be attributed and the driver polled until timeout.
2. The driver dropped `SOLAR_INTENT_GATEWAY_DIR`, so the dispatch guard looked
   for the binding manifest under the default installed gateway and rejected a
   valid binding.
3. A2's exact worker was preempted by the generic human-in-the-loop search lane,
   because its provider capabilities collide with `HUMAN_SEARCH_CAPABILITIES`.
4. The driver aborted on a healthy poll tick, because `graph-dispatch` exits 2
   for any `ok: false` payload including "nothing to dispatch yet".

All four have regressions, including seam tests that wire the real intake to the
real dashboard reader. The two pre-existing attribution tests each hand-built
the other side's fixture, which is exactly how defect 1 survived.

### The one remaining blocker

Codex subscription quota is exhausted account-wide until **2026-08-19 23:46**,
confirmed by a direct `codex exec`. A4-A7 are Codex subscription workers, so
neither the local nor the container gate can be reached before then, and a
container run uses the same account.

When quota returns, resume with a **new** evidence root:

```bash
WT=/home/ssubr/openjiuwen-solar-integration/autosci-fixed-workflow/wt-evidence-to-poc
ROOT=$WT/artifacts/dashboard-full-uat-r6-<date>
mkdir -p "$ROOT"/{sprints,intents,workspace,knowledge,runtime/codex-state,screenshots,server}
sed "s#r5-20260818#r6-<date>#g" \
  "$WT/artifacts/dashboard-full-uat-r5-20260818/server/env.sh" > "$ROOT/server/env.sh"
cd "$WT" && . "$ROOT/server/env.sh"
python3 harness/lib/symphony/status-server.py   # binds 8765
```

Then submit through the real form with the repository browser at
`~/.solar/skills/gstack/browse/dist/browse` (`goto`, `snapshot -i` for fresh
refs, `fill @e4 "$(cat artifacts/dashboard-uat-input-20260818/request.md)"`,
`click @e6`), read the `request_id` out of the new `sprints/*.status.json`, and
run `dashboard-to-final` exactly as documented below.

Check `harness/run/operator-inbox` is empty first; stale entries from other
sprints fail the driver's quiescence precondition. The ones cleared on
2026-08-18 were preserved, not deleted, under
`artifacts/dashboard-full-uat-r2-20260818/preserved-stale-operator-inbox/`.

## Latest single-threaded checkpoint

- Dashboard projection overlays the scheduler-owned
  `<sid>.task_dag.state.json` on the stable graph specification and recognizes
  exact compiler-owned fixed worker/capsule bindings without requiring a
  legacy autopilot routing record. Regressions cover both the valid binding
  and a missing compiled candidate.
- The retained corrected sprint projects `seed_fetch` as workflow status
  `dispatched`, normalized status `active`, exact worker/capsule, and no false
  capability mismatch.
- Three HTTP contract-route tests cannot open a loopback socket in the current
  restricted sandbox (`PermissionError`); 26 sibling tests passed in that run.
  This is an environment limitation, not a substitute acceptance claim.
- Docker Desktop WSL integration is still absent. Do not apply the branch until
  the fresh browser-created full run and Docker run meet the acceptance gates.
