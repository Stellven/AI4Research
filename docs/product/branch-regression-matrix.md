# Branch Regression Matrix

Date: 2026-07-01

This matrix compares the Sihao baseline to the productized runtime line and the
current integration branch. It is intentionally a regression and migration-risk
map, not a release sign-off.

## Branch Resolution

The requested branch names resolve as follows in this worktree:

| Label | Ref used | Commit | Notes |
| --- | --- | --- | --- |
| `main` | `main` | `a3a0ecaa` | Sihao baseline. Also local `openJiuwen-Solar` and `origin/main` point here. |
| `pkg/migration` | `pkg/migration` | `92f5cb90` | Earlier productization branch with rc5-era desktop/install/dashboard work. |
| `openJiuwen-Solar` | `upstream/openJiuwen-Solar` | `cdc7e903` | Current upstream productized branch. Local `openJiuwen-Solar` is stale at `a3a0ecaa`, so this report uses the upstream branch for meaningful comparison. |
| `integration/rc8-runtime-mode-contract` | `integration/rc8-runtime-mode-contract` | `ad4f2551` | Integration branch with runtime contract fixes, passing Codex-only smoke, and review docs. |

Branch delta summary:

| Comparison | Relevant diff summary |
| --- | --- |
| `main..pkg/migration` | Desktop/runtime/install surface added heavily: 93 inspected files, about 29.7k insertions and 959 deletions across requested areas. |
| `pkg/migration..upstream/openJiuwen-Solar` | rc6-rc8 hardening: 44 inspected files, about 6.8k insertions and 335 deletions. |
| `upstream/openJiuwen-Solar..integration/rc8-runtime-mode-contract` | Runtime-contract integration only: 9 inspected files, about 1.9k insertions and 37 deletions. |
| `upstream/openJiuwen-Solar..feature/setup-wizard` | Setup wizard branch is behind upstream by 10 commits and has 0 commits ahead; it is not integrated into this runtime branch. |

Representative commands used:

```bash
git log --oneline --decorate --max-count=30 main
git log --oneline --decorate --max-count=30 pkg/migration
git log --oneline --decorate --max-count=30 upstream/openJiuwen-Solar
git log --oneline --decorate --max-count=30 integration/rc8-runtime-mode-contract

git diff --stat main..pkg/migration -- <area paths>
git diff --stat pkg/migration..upstream/openJiuwen-Solar -- <area paths>
git diff --stat upstream/openJiuwen-Solar..integration/rc8-runtime-mode-contract -- <area paths>
```

## Component Matrix

| Component | Classification | What changed from main | Evidence commits | Still not proven | Recommended next validation |
| --- | --- | --- | --- | --- | --- |
| Desktop packaging | improved/productized | `main` had no Electron desktop package. `pkg/migration` added `desktop/`, Electron builder config, renderer build, app resources, icons, runtime helpers, package checks, and desktop tests. `upstream/openJiuwen-Solar` added rc8 prepackage hardening and static bundle rebuild. Integration branch does not change desktop packaging. | `065b097a`, `59a31a60`, `446a1c5b`, `c48507fb`, `cdc7e903` | Clean artifact install is not proven by this Codex smoke. | Build macOS DMG, Linux AppImage, Windows portable/exe from this branch; install on clean users; verify bundled harness and dashboard launch. |
| Install scripts | migrated but risky | `install.sh`, `install.ps1`, `get-solar.sh`, smoke scripts, release scripts, and installer contract checks were added or modified after main. The installer moved from dev-harness assumptions toward release-channel/bootstrap behavior. | `0182e0fd`, `41b9cfd1`, `1d9fddf0`, `e2749449`, `c48507fb` | Release URL/tag/source consistency still needs explicit gate review. | Run install scripts in sandbox homes and clean VMs; verify channel/tag matches the repo and artifact being released. |
| Windows WSL setup | migrated but risky / still unverified | Main had no Windows WSL product path. Product branches added `install.ps1`, WSL detection, Windows docs, WSL evidence doctor, runtime-detect tests, and WSL-host status-server binding support. | `89780a93`, `aad55fb4`, `8ee6d508`, `93757748`, `855be1f5` | Fresh Windows WSL bootstrap remains unproven in this integration branch. | Fresh Windows 11 VM: no WSL, install app, accept elevation/reboot, verify Ubuntu-24.04, status server, dashboard, runtime selector, and a small task. |
| macOS LaunchAgent setup | known regression fixed / still unverified | Main had no macOS desktop LaunchAgent product path. Product branches added LaunchAgent templates and desktop-managed status-server supervision. rc8 work moved toward bundled runtime first and symlink/stale runtime hardening. | `cc402177`, `59a31a60`, `a10dfcfe`, `446a1c5b`, `e2749449` | Clean macOS app install was not exercised by the Codex smoke. | Fresh macOS user: install DMG, verify bundled harness sync, LaunchAgent load/kickstart, `/healthz`, dashboard session click, restart recovery. |
| Linux service setup | improved/productized / still unverified | Main was a local harness. Product branches added Linux service templates and desktop runtime service install/uninstall scripts. | `94351460`, `59a31a60`, `desktop/runtime/solar-status-server.service`, `templates/status-daemon/solar-status-server.service.template` | Linux AppImage/service bootstrap is not proven here. | Clean Linux user: install AppImage/package, verify service install, status-server startup, runtime selector, task completion, restart behavior. |
| Status-server startup | improved/productized | Main already had harness status-server code, but productization added desktop startup supervision, loopback/token hardening, WSL binding behavior, runtime info/settings endpoints, dashboard projection, and orchestration routes. | `62da5eec`, `cc402177`, `89780a93`, `cdc7e903`, `e2749449` | Cross-platform startup from packaged artifact remains unproven. | Status-server smoke under clean `$HOME`, Electron launch, WSL host reachability, macOS LaunchAgent restart, stale pid/port cleanup. |
| Bundled harness sync | known regression fixed / still unverified | Main had no packaged runtime sync. Product branches added bundled harness resources and sync into `~/.solar/harness`; rc8 fixed stale runtime sync, frontend `node_modules` exclusion, symlink rejection direction, and macOS bundled-first behavior. | `a10dfcfe`, `446a1c5b`, `c48507fb`, `e2749449`, `scripts/sync-harness-runtime.sh` | Clean artifact sync and rollback behavior still need platform evidence. | Clean macOS/Linux/Windows install with no `~/.solar`; verify `.desktop-runtime-version`, no symlink writes, preserved runtime state on upgrade. |
| Runtime selector Codex/Claude | improved/productized | Main was not a consumer-facing Codex/Claude selector product. `pkg/migration` added dashboard settings and Codex search/effort controls. `upstream/openJiuwen-Solar` added route selector enforcement and observability. Integration added Codex model aliases and isolated live E2E preservation. | `f62915e5`, `4614d9f6`, `a3b2079f`, `27fdcfc4`, `8e7f1dcf`, `154a1d48` | Claude-only runtime has not been live-proven; dashboard UX still has separate runtime/crew concepts. | Preflight UI: show PM/planner/builder/evaluator provider/model/operator before submit; run Claude-only completion or auth/quota fail-closed proof. |
| Provider fail-closed routing | known regression fixed | Main did not enforce product-mode provider isolation. Productized branches added provider selectors, provider policy in PM dispatch, role spillover restrictions, non-deprecated Codex operators, and route proof. Integration passed Codex-only OpenAI route proof. | `27fdcfc4`, `562b652d`, `8e7f1dcf`, `9e76194b`, `b787e9be`, `154a1d48` | Only Codex/OpenAI smoke has passed. Mixed/deprecated operator registry still needs release review. | Negative tests for selected Codex with Anthropic/Claude unavailable; selected Claude with Codex unavailable; final route-proof gate in UI/release checklist. |
| PM -> Planner -> Builder -> Evaluator | improved/productized | Main had a developer harness; productization added self-advancing multi-task DAGs, operator-pool dispatch, evaluator dispatch, role-compatible selection, closeout contracts, and route attribution. Integration passed a Codex-only smoke through planner/build/eval/closeout. | `0e4842b3`, `04b985f6`, `c710b732`, `9f2d7f35`, `30169c80`, `cd528d0a` | Smoke task is small; deep/long AI4Research tasks are not proven. | After branch review, run one realistic AI4Research task with source/evidence requirements; run Claude-only equivalent or fail-closed. |
| Graph scheduling | improved/productized / known regression fixed | Productization added graph scheduling, parent-ready closeout, self-advance, dependency terminalization, eval dispatch handling, and repair generation fencing. Integration fixed the active-repair parent terminalization race. | `0344d159`, `0e4842b3`, `d00903ab`, `d09e1ed0`, `5ba3bdee`, `cd528d0a` | Live smoke at `cd528d0a` did not trigger repair; repair lifecycle is deterministic-test proven only. | Controlled deterministic replay remains green; optionally later run a bounded live prompt that intentionally triggers one repair. |
| Proof artifacts / patch diff | known regression fixed | Main did not have the current node proof-obligation product contract. Product branches added proof sidecars and evaluator proof gates. Integration fixed missing patch-diff sidecar generation from sidecar obligations and exact failed-shape coverage. | `c7783029`, `d2339f21`, `92c5615d` | Proof requirements need product review for all task classes, not just smoke code task. | Expand proof-contract fixtures for report/deep-research nodes; verify dashboard renders proof artifacts clearly. |
| Repair lifecycle | known regression fixed | Productized runtime added evaluator FAIL -> repair builder -> re-eval behavior. Integration fixed stale eval generation and parent status race around active repair. | `d00903ab`, `d09e1ed0`, `5ba3bdee`, `cd528d0a` | Passing smoke did not exercise live repair. | Deterministic tests are green; later add one explicit live repair scenario after branch review, or keep as deterministic-only until product scope needs it. |
| Route proof | improved/productized | Main had no final provider/model/operator route-proof artifact. Integration branch adds `harness/lib/route_proof.py`, route-proof tests, and an isolated Codex smoke producing `route-proof.json`. | `2db50662`, `154a1d48`, `f01e81e2`, `ad4f2551` | Route-proof schema and UI release gate should be reviewed before release. | Make route proof a required release artifact and dashboard-visible execution contract summary. |
| Dashboard/static bundle | improved/productized / still unverified | Main had homepage/static harness surfaces, not the rc8 React dashboard product. Product branches added React dashboard, status projections, settings persistence, session routes, bundled static assets, visual/functional tests, and rc8 static rebuild. | `94aa4f9d`, `826a3c9b`, `9c3e3c8e`, `4d0370be`, `d2edac3d`, `cdc7e903` | This Codex smoke did not verify Electron dashboard UX, session click, or browser console stability. | Desktop functional test plus manual/Playwright session open on the passing sprint; verify no white screen and artifact open flows. |
| Setup wizard branch interaction | still unverified | The only visible `feature/setup-wizard` branch is behind `upstream/openJiuwen-Solar` by 10 commits and has 0 commits ahead. Its diff relative to upstream removes or changes parts of desktop bootstrap tests/main/dashboard assets, so it should not be assumed integrated. | `feature/setup-wizard` at `c48507fb`; upstream at `cdc7e903` | Setup wizard is separate from the runtime branch and not covered by Codex smoke. Server-side setup gate remains separate. Browser dashboard may bypass Electron preload gate until server-side gate exists. | Rebase/replay setup wizard onto this integration branch in a separate worktree; add server-side setup gate tests before merging. |

## Cross-Branch Read

The movement from `main` to productized runtime is not a small model swap. It is
a packaging and lifecycle migration:

- `main` is the Sihao developer harness baseline.
- `pkg/migration` adds the distributable product shell: desktop app, installer
  scripts, dashboard, service templates, status-server exposure, and early
  runtime selector work.
- `upstream/openJiuwen-Solar` hardens rc6-rc8 productization: bundled-runtime
  bootstrap, dashboard static bundle, macOS/Windows install path fixes, route
  selectors, provider fail-closed behavior, and Codex route observability.
- `integration/rc8-runtime-mode-contract` is narrower: it patches runtime
  contract failures exposed by Codex-only E2E attempts, adds route proof, model
  aliases, patch proof, repair lifecycle hardening, and the isolated live E2E
  script.

## Fixed Failures In The Integration Branch

- Codex physical operator models existed but model-registry aliases were
  missing: fixed by `154a1d48`.
- Codex-only route proof and evidence were fragmented: fixed by `2db50662` and
  covered by the passing smoke at `cd528d0a`.
- Patch proof was required by evaluator obligations but missing as a real file:
  fixed by `92c5615d`.
- Repair lifecycle could terminalize the parent graph while a repair/re-eval
  generation was still active: fixed by `cd528d0a`.
- Duplicate graph dispatcher implementation risk was reduced by routing the
  tools entrypoint to the lib implementation: `7f9718b5`.
- Installed-harness contamination in tests was guarded: `b20e44d3`.

## Not Proven Yet

- Clean macOS artifact install.
- Clean Windows WSL bootstrap.
- Clean Linux service install.
- Claude-only runtime completion or clean fail-closed behavior.
- Setup wizard integration.
- Direct browser dashboard gating via server-side setup gate.
- Deep research / live web research.
- AutoSci.
- Long report generation.
- Live repair lifecycle; deterministic repair tests pass, but the passing smoke
  did not require repair.

## Recommended Validation Order

1. Review and push `integration/rc8-runtime-mode-contract`.
2. Run cleanup hygiene for old `/tmp/solar-live-codex-e2e.*` process residue in
   a separate patch.
3. Run Claude-only equivalent or auth/quota fail-closed proof.
4. Verify macOS fresh install with bundled harness and LaunchAgent.
5. Verify Windows fresh install with WSL2 bootstrap.
6. Verify dashboard session open/artifact open against the passing smoke sprint.
7. Rebase/replay setup wizard separately and add a server-side setup gate.
8. Run one realistic AI4Research prompt after branch review, not before.
