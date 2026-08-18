# Phase 23 Product Repair Log

Started: 2026-08-17
Objective: close the remaining user-visible product defects during the week of 2026-08-17.
Primary acceptance surface: the running Windows AI4Research desktop application and its actual WSL-backed Solar runtime.

## Severity policy

- **Blocker**: prevents a realistic user task from advancing or completing in the shipped/running product; loses or corrupts user data; breaks security/privacy; or displays a terminal success that the real execution did not reach.
- **Significant**: an implemented path produces materially wrong behavior or loses an important supported variant, but a realistic core task can still complete.
- **Mild**: localized usability, observability, evidence-quality, or non-core variant problem that does not stop the primary task.
- Report/evidence defects are tracked separately from product runtime severity. They are not product Blockers unless they also block or misrepresent the real product journey.

## Verification reset

Phase 23 does not inherit a product PASS/FAIL merely from Phase 22 reports or isolated journey tests. For Windows desktop issues, acceptance requires:

1. reproduce through the running Windows application or the exact runtime checkout it uses;
2. retain the sprint status, event, task-graph, dispatch, and process evidence for the same run;
3. identify the first failed production boundary;
4. repair the canonical repository, deploy/synchronize that repair into the runtime checkout, and rerun a fresh user task;
5. require observable state progress and a usable result, not merely a passing unit test or existing artifact.

## Active issues

### P23-001 — Windows App stalls at `prd_ready` and never dispatches the planner

- **Severity:** Blocker
- **Status:** CODE REPAIRED / LIVE WINDOWS ACCEPTANCE PENDING
- **Reported surface:** Windows AI4Research desktop application.
- **Observed user impact:** a submitted request remains at `State transition — PHASE prd ready`; the plan shows `0/3`, and Builder/Evaluator nodes remain pending indefinitely.
- **Scope confirmation:** all 5 status-bearing sprints currently present in the running `C:/p22all/harness/sprints` runtime are at `phase=prd_ready`, and all 5 have a failed planner dispatch claim. This is a systemic dispatch failure, not one malformed request.
- **Observed sprint:** `sprint-20260814-203922-intent-hi-tell-me-what-model-you-ar-15343056`
- **Running application checkout:** `C:/p22all`, commit `8d2259e198df7af486a5822d749e6b03f8d0f313`, branch `openJiuwen-Solar`.
- **Running status server:** Ubuntu/WSL process `python3 /mnt/c/p22all/harness/lib/symphony/status-server.py` with `HARNESS_DIR=/mnt/c/p22all/harness`.
- **Direct evidence:**
  - `C:/p22all/harness/sprints/sprint-20260814-203922-intent-hi-tell-me-what-model-you-ar-15343056.status.json`
  - `C:/p22all/harness/sprints/sprint-20260814-203922-intent-hi-tell-me-what-model-you-ar-15343056.events.jsonl`
  - `C:/p22all/harness/sprints/sprint-20260814-203922-intent-hi-tell-me-what-model-you-ar-15343056.task_graph.json`
- **First failed boundary:** planner operator selection/health admission.
- **Failure evidence:** `planner_dispatch_claim.state=failed`, with `failure_reason=role_pool_dispatch_failed_rc_1`; the durable event reports `no_dispatchable_operator_for_role: planner; provider_mode_role_spillover_disabled`.
- **Root cause:** the desktop runtime is configured for `codex`, so dispatch is restricted to the OpenAI provider. The enabled OpenAI planner records (`mini-codex-gpt55-medium-planner-1` and `-2`) use the Mac-only health-check path `/opt/homebrew/bin/codex`. In Ubuntu/WSL both are rejected as `health_check_failed: command_path_missing:/opt/homebrew/bin/codex`. Cross-provider spillover is intentionally disabled, leaving no admissible planner and no state-transition recovery.
- **Repair requirements:**
  1. resolve Codex CLI health/launch paths per host/runtime instead of pinning the Mac path for Windows/WSL;
  2. make a missing provider-compatible planner visible in the product as an actionable blocked/error state rather than an endless `prd_ready` spinner;
  3. add bounded retry/recovery after operator availability changes without duplicating planner dispatch;
  4. add Windows+WSL regression coverage using the same status-server intake and role-pool dispatch path.
- **Acceptance:** a fresh Windows App request advances from intake/`prd_ready` to a genuinely dispatched and running planner, then to graph execution and a usable answer. The accepted run must contain matching current-run status/events/operator result evidence and must not depend on a fabricated worker or manually edited sprint state.
- **Code repair evidence (2026-08-17):**
  - `8d2259e198df7af486a5822d749e6b03f8d0f313` routes a Windows-hosted intake through `wsl.exe` and prevents the Bash entrypoint from being launched as a Win32 executable. Its four status-server intake regression tests pass on Windows.
  - `55ec2ea78f74ce157b0cec4314861a44bef2a040` sends the backend token on the desktop shell's initial navigation as well as later navigation.
  - the current `harness/tools/pm_dispatch.py` resolves a stale absolute `/opt/homebrew/bin/codex` record by the executable basename on the active host, invalidates a cached `command_path_missing` result when that executable appears, and passes `test_codex_operator_health_accepts_path_resolved_codex`.
  - the repaired webapp/desktop gate passes 9/9 on this Windows checkout, including a real backend, functional browser flow, SSE, rapid session switching, and desktop/mobile visual checks.
- **Why acceptance is still pending:** the packaged/running App has not yet been restarted and synchronized from this canonical commit, and no fresh permitted-model task has produced matching planner-through-result evidence. The previous runtime records used a model the user prohibited for live calls, so this repair did not silently launch it.

## Reclassified Phase 22 review findings

The earlier P22-044/P22-045/P22-047/P22-054/P22-069/P22-071 findings remain useful report/evidence-quality work, but they are **not Phase 23 product Blockers solely because they prevent a Phase 22 report row from being closed**. They will be reprioritized after the live Windows execution blockers are enumerated.

## Decision history

### 2026-08-17 — Phase 23 start and severity reset

- User supplied direct Windows App evidence showing a workflow stalled at the state-transition boundary.
- Independent inspection confirmed that earlier testing emphasized isolated Phase 22 evidence contracts and did not exercise the exact running desktop checkout/runtime pair.
- Product runtime blockers now take precedence over report closure work.
- P23-001 is the first confirmed Phase 23 Blocker.

### 2026-08-17 — Canonical-main recovery started

- The user designated the original `OpenSolar-Canonical` directory as the only
  continuing local development checkout and requested that its
  `openJiuwen-Solar` branch contain the latest accepted work.
- Review of integration commit `22e911dac390cd08bf5e1284faebcf91d4938aae`
  found that the temporary integration checkout omitted the uncommitted
  desktop initial-navigation token repair, did not audit remote-only branch
  tips, and reported a path-sensitive `119 passed` result that does not
  reproduce from `C:/p22all`.
- This Phase 23 repair preserves the existing Phase 22 report synchronization
  and desktop token change before moving the publishing branch back into the
  canonical directory. Scratch files and local run outputs remain excluded
  from commits.
- No remote push is authorized or performed by this recovery.

### 2026-08-17 — P23-002 canonical branch integration repaired

- The original `OpenSolar-Canonical` directory now owns the checked-out
  `openJiuwen-Solar` branch. The temporary `C:/p22all` checkout is no longer
  the publishing or development source of truth.
- Accepted branch work was integrated with immutable mappings recorded in
  `docs/integrations/autosci/phase-23-integration-ledger.md`:
  - Phase 22 closure/desktop token protection -> `55ec2ea78f74ce157b0cec4314861a44bef2a040`;
  - epic global WIP activation gate -> `7d7ae2a1d9f5264764b1a7eafbe499047c028ca9`;
  - Windows/WSL, browser-profile, governance, and integration-gate repairs ->
    `bc3e9ff59d6d11d7a90fd9a2fb4052b51fc76896`.
- Audited inventory:
  - 47 local non-ancestor branch tips classified;
  - 42 remote refs sharing 21 unique non-ancestor tips classified;
  - 3 accepted original-to-integrated mappings verified reachable;
  - 0 unclassified candidate fixes.
- Repairs in `bc3e9ff59` include:
  - WSL path conversion using `wsl.exe --exec` from a Windows checkout;
  - browser profile copies that omit volatile extension/cache trees;
  - current `.cjs` desktop test paths and explicit missing-path checks;
  - a CRLF-safe release version parser using TOML and Python AST;
  - portable webapp gate Python/Playwright dependency resolution and unique pytest temp directories;
  - portable S04 fake CLI coverage and stronger semantic preservation checks for moved Python tests;
  - useful stderr on epic activation failures and a working moved Epic shell test.
- Verification completed:
  - focused and integration Python suite: `144 passed`;
  - Epic/activation WSL shell suite: `PASS=20 FAIL=0`;
  - release coherence: `PASS`;
  - webapp/desktop gate: `PASS=9 FAIL=0 SKIP=0`;
  - `git diff --check`: pass.
- Historical scratch outputs and untracked Phase 22 inspection files remain
  uncommitted. They are not part of `openJiuwen-Solar` and were not deleted.
- No remote push was performed.
