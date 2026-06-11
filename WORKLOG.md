# WORKLOG

## Current State

- Source of truth for this migration: `MIGRATION_PLAN.md` per user override.
- User override: local commits are allowed, and pushes are allowed only to the
  current migration branch on the user's fork remote (`origin`). Never push to
  `upstream`.
- Current phase: P1 / WS4 installer skeleton.
- Branch state: local branch `pkg/migration`; future pushes, when used, must go
  only to `origin pkg/migration`.

## Step 0 Results

- `git rev-parse --short HEAD`: `a3a0eca`.
- `git merge-base --is-ancestor a3a0eca HEAD`: passed.
- `git log --oneline a3a0eca..HEAD`: empty; no commits above baseline.
- `git show -s --format=%H%n%an%n%ae%n%s 070396f`: merge author is an upstream account and subject is PR #13 capsule-proof-adapter-runtime.
- `git diff 070396f^1 070396f --stat`: returned a very large change set, about 3,143 files and roughly 639,950 insertions.
- Targeted PR #13 path check touched `AGENTS.md`, many `harness/config/*`, many `harness/lib/*`, and many `harness/tools/*` files, including operator and pane-related surfaces.
- This contradicts the Step 0 expectation that the PR #13 check confirms infra/CI-only scope with no operator or pane-dispatch seam changes.
- `git log --format=... --follow -- install-core.sh`: one upstream-authored commit found.
- `git log --format=... -- core/daemon`: three upstream-authored commits found.
- Pinned schema file check: all 12 source schema files listed in `MIGRATION_PLAN.md` are present.

## Gate Status

- PR #13 provenance mismatch is recorded and accepted by user as non-blocking because the commit is upstream-authored and no third-party contamination was found.
- User clarified that `MIGRATION_PLAN.md` and `WORKLOG.md` are local/internal working files and do not need to be committed.
- Local branch `pkg/migration` exists and is checked out.
- Local archive branch and local archive tag exist. Nothing was pushed.
- Local commit `3291998` (`WS0: purge runtime and personal artifacts`) removed tracked runtime output, committed local DB/state artifacts, stale backups, superseded installer artifacts, and OS files named by WS0; `.gitignore` was hardened for those categories.
- Pre-commit checks for `3291998`: `git diff --cached --check` passed; staged modified/added privacy scan covered `.gitignore` and found no forbidden tokens.
- Local knowledge retrieval attempt for contributor-doc work:
  `solar-harness context inject --query "OpenSolar packaging migration AGENTS contributor doc" --format markdown`
  failed because `solar-harness` is not on PATH in this checkout.
- `AGENTS.md` was rewritten as a contributor-facing guide and explicitly marked
  as not installed runtime content.
- Verification for `AGENTS.md`: `git diff --check -- AGENTS.md` passed; targeted
  privacy scan over `AGENTS.md` found no forbidden-token matches.
- Local commit `bcd35ba` (`WS0: rewrite agent contributor guide`) records only
  the `AGENTS.md` rewrite. No push was run.
- `package.json` and `bun.lock` were updated to remove the broken `file:../TVS`
  dependency. The default `dashboard` script now runs the TVS-free web dashboard;
  TVS-backed terminal dashboard scripts were removed from the default manifest.
- Verification for package manifest repair: `python3 -m json.tool package.json`
  passed; `git diff --check -- package.json bun.lock` passed; targeted scan for
  the removed file dependency returned no matches; targeted privacy scan over
  `package.json` and `bun.lock` found no forbidden-token matches.
- Install gate: `bun install --frozen-lockfile` failed inside the sandbox because
  Bun could not write to its temp directory. Rerun outside the sandbox with the
  same command and `TMPDIR=/tmp` passed; Bun installed `@types/bun`, `typescript`,
  and `bonjour-service` with no TVS file dependency.
- Local commit `f13dc8c` (`WS1: remove local TVS package dependency`) records
  only `package.json` and `bun.lock`. No push was run.
- Import audit for Python requirements:
  `harness/lib` base requirements were reduced to `jsonschema`, `pydantic`,
  `PyYAML`, and `rich`; heavier feature imports were left for later optional
  component manifests because they are not required by the base harness install.
  `mempalace/*.py` imports require `chromadb`, `langdetect`, `mcp`, `PyYAML`,
  and `sentence-transformers`.
- Verification for `requirements/harness.txt`: full `python3 -m pip install
  --dry-run --ignore-installed -r requirements/harness.txt` passed outside the
  sandbox after the sandboxed run failed due network/DNS restrictions.
- Verification for `requirements/mempalace.txt`: full dry-run resolved package
  names but started downloading a very large transitive embedding/runtime stack,
  so the process was stopped deliberately. Top-level validation with
  `python3 -m pip install --dry-run --ignore-installed --no-deps -r
  requirements/mempalace.txt` passed.
- Requirement file checks: `git diff --check -- requirements/harness.txt
  requirements/mempalace.txt` passed; targeted privacy scan over both files
  found no forbidden-token matches.
- Local commit `6aa69f1` (`WS1: add Python requirement manifests`) records only
  `requirements/harness.txt` and `requirements/mempalace.txt`. No push was run.
- Schema consolidation mismatch found during `core/db/schema/` preparation:
  `MIGRATION_PLAN.md` says `core/ontology/schema-v2.sql` wins and
  `core/ontology/schema.sql` is archived. Applying only v2 to a fresh SQLite DB
  failed because v2 line 204 reads `ont_preference_history` and line 218 reads
  `ont_preference_dimensions`; both tables are created by ontology v1, not v2.
  The runtime code also still depends on v1 tables: `core/ontology/manager.ts`,
  `core/ontology/timeline.ts`, `core/ontology/reflection.ts`,
  `core/ontology/agent-integration.ts`, and
  `core/ontology/personality-learner.sh` query or mutate v1 tables such as
  `ont_preference_dimensions`, `ont_relationships`, `ont_agent_rules`,
  `ont_global_rules`, `ont_versions`, and `ont_preference_history`.
- Decision: keep ontology v1 in the root schema apply order as a compatibility
  base, then apply v2 timeline/snapshot additions after it. This is a local
  implementation correction to match verified code dependencies; it does not
  rewrite ontology internals and keeps fresh DB init possible. The archived copy
  remains in `core/db/schema/archive/ontology-v1.sql` for provenance.
- Detailed mismatch record: the ratified plan's "v2 wins, v1 archived" language
  is directionally right for future cleanup, but it is not executable against
  the pinned baseline as-is. The v2 file is an additive migration, not a
  standalone replacement, because it selects from v1 tables during migration and
  leaves current runtime modules coupled to v1 table names. The alternatives
  considered were: (1) follow the plan literally and ship only v2, which fails
  fresh DB init; (2) rewrite runtime ontology code to v2, which violates the
  "packaging, not rewrite" constraint; or (3) include v1 as an apply-order
  compatibility base while still archiving the source copy for provenance. I
  chose option 3 because it is the smallest local correction that preserves the
  packaging contract, keeps existing runtime behavior intact, and remains
  reversible when a future real ontology migration is authored. Follow-up gate:
  installer `db-init` must apply the root schema set in filename order and the
  CI schema test must keep verifying fresh apply plus idempotent reapply.
- Schema consolidation created `core/db/schema/*.sql` in ordered apply form:
  nerve, backlog/message-listener compatibility, hive, derived cortex,
  resource, SMI, ontology v1 compatibility, ontology v2, shortcuts, and
  experience. `core/db/schema/archive/ontology-v1.sql` keeps the v1 source copy;
  `core/db/schema/optional/tech-hotspot-radar.sql` keeps the optional component
  schema outside the core apply glob as specified.
- `40-cortex.sql` derivation evidence: enumerated references in the specified
  hooks/rules/kernel only require `cortex_sources(citation_key,title,finding,
  task_id,credibility,expert_model,created_at)`, `sys_favorites(title,question,
  answer,tags,importance,created_at)`, and FTS columns
  `fts_unified_search(doc_id,title,doc_type,content)`. No underivable required
  columns were found for those statements.
- Schema verification: applying `for f in core/db/schema/*.sql; do sqlite3
  /tmp/solar-schema-test.db < "$f"; done` to a fresh DB passed. Reapplying the
  same ordered root set to the same DB also passed, confirming idempotency for
  the root schema set. A parallel introspection query briefly hit a SQLite lock
  while reapply was running; rerunning it serially passed and confirmed the
  cortex/favorites/FTS table columns.
- Additional schema checks: `rg --pcre2` for root `CREATE TABLE/VIEW/INDEX/
  TRIGGER` statements missing `IF NOT EXISTS` returned no matches; `git diff
  --check -- core/db/schema` passed; targeted privacy scan over `core/db/schema`
  found no forbidden-token matches.
- Local commit `3ef6bf8` (`WS1: consolidate database schemas`) records only
  `core/db/schema/**`. No push was run.
- Local commit `4f256c8` (`WS1: add portable hook helpers`) records
  `hooks/lib/portable.sh`, the portable date call in `honcho-session-end.sh`,
  and the Python-based cross-platform state update path in
  `state-auto-updater.sh`.
- Portability verification for `4f256c8`: `bash -n` over the three touched hook
  files passed; `date_add -30M` ran on Linux; sandboxed `HOME` insert and
  replace tests for `state-auto-updater.sh` passed without touching the real
  home directory; `git diff --cached --check` passed; targeted privacy scan over
  the touched files found no forbidden tokens. No push was run.
- Installer dependency handling update: `harness/installer/install.sh` no
  longer exits when Bun or a TVS root is absent. This is intentionally narrow:
  the old harness installer remains a pattern source, while the future WS4
  component installer will own full component selection and required/optional
  dependency gating. For now, missing Bun or TVS is reported as unavailable
  optional capability, not a base harness install failure.
- Doctor alignment update: `harness/installer/doctor.sh` now records TVS as
  `optional_missing` when its bridge, Bun, or root checkout is absent, and that
  optional absence no longer forces the overall verdict to `fail`. This matches
  the user override to keep TVS optional while the shipped dashboard path remains
  TVS-free.
- Verification for installer dependency handling: `bash -n` over
  `harness/installer/install.sh` and `harness/installer/doctor.sh` passed; static
  grep found no old Bun/TVS hard-stop messages; a sandboxed `HOME` doctor run
  with no TVS root returned `verdict=ok` and
  `services.tvs_renderer.status=optional_missing`; `git diff --check` passed;
  targeted privacy scan over the touched files found no forbidden tokens.
- Local commit `0d055a5` (`WS1: treat TVS as optional in harness installer`)
  records only `harness/installer/install.sh` and
  `harness/installer/doctor.sh`. No push was run.
- P0 privacy gate mismatch: after the initial WS0 purge, a tracked-file privacy
  scan still found 104 files containing personal paths, personal account data,
  private-network examples, or private host defaults. This is broader than the
  specific WS0 deletion list in `MIGRATION_PLAN.md`. The plan is still correct
  in intent, but incomplete for the pinned tree's actual residue.
- Decision: extend WS0 cleanup only where it serves the ratified day-100/privacy
  contract. Obvious development-history artifacts and private sync leftovers are
  deleted. Retained runtime scripts/tests are parameterized or changed to
  neutral examples rather than rewritten. Local-only `MIGRATION_PLAN.md` and
  `WORKLOG.md` are excluded from product privacy scans because the user declared
  them local working documents that must not be committed.
- Local commit `5b2e584` (`WS0: purge private history artifacts`) deletes 13
  tracked files: legacy private deploy sync docs/helper, extracted/raw harness
  artifacts, closeout/audit/handover markdown, a collected S05 artifact JSON,
  and the private Mac-mini sync auditor skill. No push was run.
- Post-delete indexed privacy scan count: 92 tracked files still contain
  personal path/private-network tokens. These are retained configs, LaunchAgent
  plists, scripts, tests, and a few docs/examples that require templating or
  neutral parameterization rather than deletion.
- Retained-file privacy scrub: mechanically replaced personal absolute paths,
  private host/user/IP defaults, personal owner fields, stale repo URLs, and
  personal emails with neutral examples, reserved documentation IPs, or installer
  template placeholders. LaunchAgent plists now use placeholders such as
  `{{HARNESS_DIR}}`, `{{SOLAR_HOME}}`, and `{{USER_NAME}}` rather than live user
  paths. The scrub also removed tracked local/release metadata
  (`harness/.workdir`, stale `harness/release/artifacts/*`) and added ignore
  rules to keep those generated artifacts out.
- Verification for retained-file privacy scrub: strict tracked scan for personal
  paths/private IP/email tokens returned zero matches; broader tracked scan for
  the known personal account/name residue returned zero matches; `git diff
  --check` passed; JSON validation passed for 6 changed JSON files; PyYAML
  validation passed for 29 changed YAML files; Python `plistlib` parsed all 17
  tracked plists; `python3 -m compileall -q` over modified Python-bearing areas
  passed; `bash -n` over modified shell files passed.
- Local commit `07539b9` (`WS0: scrub retained private defaults`) records the
  retained-file privacy scrub and generated-artifact ignore cleanup. No push was
  run.
- P0 exit checks from a clean local clone at `/tmp/opensolar-p0.UUJERX/repo`:
  `TMPDIR=/tmp bun install --frozen-lockfile` passed; tracked personal-token
  privacy grep returned zero matches; `git diff --check` passed; fresh SQLite
  schema apply plus idempotent reapply of `core/db/schema/*.sql` passed and
  confirmed `cortex_sources`, `sys_favorites`, and `fts_unified_search`.
- P0 status: exit criterion passed locally. No push was run.

## WS4 Design Note

- Interfaces: root `install.sh` stays a thin Bash 3.2 entry and delegates to
  `lib/installer/main.sh`; component manifests are sourceable
  `components.d/<name>/component.sh` files with `component_install` and
  `component_verify`.
- Initial components for P1: `kernel`, `core-runtime`, `harness`, `skills-md`,
  and `codex-bridge`, with `kernel,harness` as safe defaults and
  `core-runtime` auto-selected only when `bun` is available or explicitly named.
- File list for this increment: `install.sh`, `lib/installer/{common,paths,
  components,copy-engine,db-init,receipt,doctor,main}.sh`, minimal
  `components.d/*/component.sh`, `bin/solar`, and generated alpha kernel copy
  support under `kernel/`.
- Receipt: write `install-receipt.json` atomically into `$SOLAR_HOME`, recording
  selected components, copied roots, schema files, source dir, git sha, and
  install paths; no settings/MCP/hook registration yet.
- Test plan: `bash -n` installer files, `./install.sh --list-components`,
  sandboxed `HOME=$(mktemp -d)` install with `--yes --components kernel,harness
  --fake-keys --skip-llm-cli`, `bin/solar doctor --json`, idempotent rerun, and
  local uninstall dry path once the dispatcher exists.
- Non-goals in this increment: no kernel excision, no settings.json hook merge,
  no MCP registration, no daemon launch, no native Windows bootstrap.

- WS4 P1 skeleton implementation decision: alpha keeps the current monolithic
  `CLAUDE.md` as generated `~/.claude/solar/SOLAR.md`, behind a sentinel import
  in the user's `~/.claude/CLAUDE.md`. This follows the P1 sequencing rule that
  installer safety lands before P2 kernel surgery. Full fragment generation,
  hook/settings merge, MCP registration, and kernel content excision remain P2.
- TVS handling for this increment: per user override, no rights-request action
  is needed now. The package default remains the TVS-free web/dashboard path;
  terminal UI surfaces stay outside this P1 skeleton and will remain optional
  unless a later explicit verdict changes that.
- WS4 files added locally: thin `install.sh`, installer modules under
  `lib/installer/`, component manifests under `components.d/`, and real
  `bin/solar` plus `bin/solar-daemon` entries to satisfy `package.json`.
- Copy-engine adjustment found during sandbox test: the first harness install
  copied root dot-state files from `harness/`. I tightened the generic copy
  excludes to preserve the old sync script's contract: copy code and packaged
  assets, not local runtime state. The harness component now also preserves
  executable modes, links `solar-harness`, and writes `.runtime-source`.
- Dry-run adjustment: component verification and doctor are skipped in dry-run
  because no files are expected to exist. Verified with sandboxed
  `HOME=/tmp/solar-p1.1fouRc/dry-home`; no home directory was created.
- Verification for WS4 P1 skeleton:
  `bash -n install.sh lib/installer/*.sh components.d/*/component.sh bin/solar
  bin/solar-daemon` passed; targeted forbidden-token scan over
  `install.sh lib/installer components.d bin/solar bin/solar-daemon` returned no
  matches; `git diff --check -- install.sh lib/installer components.d bin/solar
  bin/solar-daemon` passed.
- Minimal sandbox gate:
  `/tmp/solar-p1d.qqQZ1B/home` ran
  `./install.sh --yes --components kernel,harness --fake-keys --skip-llm-cli`;
  installer doctor returned `verdict=ok`; installed
  `$HOME/.solar/bin/solar doctor --json` returned `verdict=ok`; idempotent
  reinstall kept exactly one sentinel block; `solar uninstall --yes` removed
  `~/.solar`, `~/.claude/solar`, and the empty created `~/.claude` directory;
  residue assertion returned empty.
- Core-runtime component smoke:
  `/tmp/solar-p1core3.ASzTFu/home` ran
  `./install.sh --yes --components kernel,core-runtime,harness --fake-keys
  --skip-llm-cli`; installer doctor returned `verdict=ok`; verified installed
  `core/daemon/server.ts`, `core/dashboard/server.ts`, and executable
  `bin/solar-daemon`; uninstall residue assertion returned empty. The actual
  daemon/dashboard boot gate is still pending for the next P1/WS7 increment.
- Local commit `5fb6d2f` (`WS4: add installer skeleton`) records the thin
  installer entry, installer libraries, P1 component manifests, and lifecycle
  commands. No push was run.
- Local follow-up commit `fdf00ff` (`WS4: mark daemon wrapper executable`)
  corrects the file mode for `bin/solar-daemon`. No push was run.
- Early WS7/P1 workflow increment: added `.github/workflows/install-matrix.yml`
  with Ubuntu + macOS jobs and two profiles, `minimal` and `full-non-rust`.
  The workflow delegates to `scripts/smoke-install-matrix.sh`, which runs in a
  temp `HOME`, installs, runs `solar doctor --json`, reruns for idempotency,
  checks one sentinel, optionally boots daemon + dashboard, uninstalls, and
  asserts empty residue. `scripts/smoke-install.sh` now forwards to the matrix
  smoke script for backwards compatibility.
- Runtime asset relocation: moved the two shipped dashboard HTML files from
  `demos/` into `core/dashboard/assets/` and changed only
  `core/dashboard/server.ts` asset paths. This implements the target decision
  that the web dashboard is part of `core-runtime`, while `demos/` stays
  dev-only.
- Core-runtime installer update: `components.d/core-runtime/component.sh` now
  runs `bun install --frozen-lockfile` in `$SOLAR_HOME` after copying
  `package.json` and `bun.lock`, so a clean installed core runtime has its Bun
  dependencies.
- Clean-room boot mismatch 1: `core/daemon/message-executor.ts` imported
  `./skill-dispatcher`, but `core/daemon/skill-dispatcher.ts` did not exist in
  the worktree or git history. Decision: add a minimal real Markdown skill
  dispatcher that resolves installed `SKILL.md` files and fails loudly on
  missing skills. This is not a mock; it is the smallest implementation needed
  for the existing daemon import to boot.
- Clean-room boot mismatch 2: `message-executor.ts` also imported
  `../orchestrator`, `../orchestrator/types`, and
  `../orchestrator/retry-policy`, none of which existed in the worktree or git
  history. Decision: add a compact compatibility orchestrator module with
  single-node graph construction/execution, event emission, retry policy, and
  control-method surfaces already called by the daemon. The compatibility module
  intentionally uses neutral risk (`0`) rather than a new heuristic so this
  increment does not introduce scheduling/scoring behavior. This is limited to
  making the existing daemon path real and bootable; it does not rewrite
  orchestration internals beyond the missing module contract.
- Clean-room boot mismatch 3: reply/security/listener surfaces imported
  `../config/privacy`, which also did not exist. Decision: add an env-backed
  config module with no personal data embedded (`SOLAR_*` envs first, safe
  empty/example fallbacks).
- DB-path mismatch: installer/target layout uses `~/.solar/db/solar.db`, while
  many TS runtime files still defaulted to legacy `~/.solar/solar.db`. The full
  smoke gate caught this by detecting an empty legacy DB created during daemon
  boot. Decision: mechanically align TS DB defaults to
  `process.env.SOLAR_DB_PATH || ~/.solar/db/solar.db`, and set
  `SOLAR_DB_PATH` from `bin/solar-daemon`. Added a permanent smoke assertion
  that fails if `~/.solar/solar.db` is created again.
- Skills uninstall residue: the first full smoke left `~/.claude/skills`
  behind. Decision: `skills-md` writes
  `~/.claude/solar/installed-skills.txt`, and `bin/solar uninstall` removes only
  those recorded skill directories before removing `~/.claude/skills` only if it
  becomes empty.
- Local environment note: the command sandbox blocks Bun local listeners
  (`Bun.serve` returned `EPERM` for a trivial Unix socket). The same check passed
  outside the sandbox. Therefore full smoke runs locally with escalation, still
  using a temp `HOME`; GitHub runners should not need special handling.
- Verification for early install-matrix increment:
  `bash -n install.sh lib/installer/*.sh components.d/*/component.sh bin/solar
  bin/solar-daemon scripts/smoke-install.sh scripts/smoke-install-matrix.sh`
  passed; targeted forbidden-token scan over the new workflow/smoke/installer
  and touched runtime files returned no matches; `git diff --check` over the
  same paths passed; `rg "\.solar/solar\.db" core -g '*.ts'` returned no
  matches.
- Smoke evidence: `./scripts/smoke-install-matrix.sh minimal` passed locally in
  sandbox `/tmp/solar-install.IGKID3`. Full profile
  `./scripts/smoke-install-matrix.sh full-non-rust` passed outside the command
  sandbox in `/tmp/solar-install.qHZAHo` after skills-uninstall cleanup. After
  adding the legacy-DB assertion, `/tmp/solar-install.c3zqJ7` failed as expected
  because runtime code still created `~/.solar/solar.db`; after DB-path
  alignment, full profile passed in `/tmp/solar-install.k2FygK`. After removing
  the unnecessary risk heuristic from the compatibility orchestrator, the final
  full profile passed in `/tmp/solar-install.73mhd8`. Successful full runs
  booted daemon and served dashboard HTTP 200, then uninstalled with empty
  residue.
- Next action: commit the early install-matrix/core-runtime gate increment
  locally, then optionally push only to `origin pkg/migration` per user policy.
- Local commit `8e6e468` (`WS7: add install matrix smoke gate`) records the
  early install-matrix workflow, smoke script, dashboard asset relocation,
  core-runtime boot fixes exposed by clean-room smoke, DB-path alignment, and
  residue-free skills uninstall handling. No upstream push was run.
- Pushed `pkg/migration` to `origin` (`git@github.com:suraj-subrahmanyan/OpenSolar.git`).
  This was the first allowed fork-only push; no push to `upstream` was run.

## Session 2 (takeover) — inherited-state verification

- Session start pin: `pkg/migration` HEAD = `8e6e468a0271a4c27a78ef0b6b3efd2ef8ffbec0`,
  worktree clean (only untracked local working files `MIGRATION_PLAN.md`,
  `WORKLOG.md`). `origin/pkg/migration` verified equal to local HEAD.
- First write action: pushed `archive/pre-community-2026-06-10` (tag) and
  `archive/personal-history` (branch) to `origin`; both point at baseline
  `a3a0ecaae82eed1e87d8dabb9eab520796c4a1bd`. No upstream push.
- CI triage: `gh` CLI absent and no GitHub token on this machine; used the
  unauthenticated public REST API instead (job logs are admin-only, but
  step results and check-run annotations are public and were sufficient).
- install-matrix run for `8e6e468` (run id 27297105731): all 4 jobs failed at
  step "Install and uninstall smoke" with annotation "Invalid shell option.
  Shell must be a valid built-in (bash, sh, cmd, powershell, pwsh) or a
  format string containing '{0}'". Root cause: `shell: /bin/bash` is not a
  valid Actions shell value, so the smoke step NEVER executed on any leg —
  the smoke has still never run in CI on either OS.
- Fix committed `114e139` (`WS7: fix install matrix workflow shell`): use
  built-in `bash` shell; on macOS prepend a `$RUNNER_TEMP/system-bash/bash ->
  /bin/bash` symlink to `GITHUB_PATH` so every PATH/shebang bash in the smoke
  process tree is system bash, and add a permanent assertion step that
  `BASH_VERSION` is `3.2.*` on the macOS leg (this is the required
  "macOS leg runs /bin/bash (3.2)" confirmation, enforced every run).
  Also bumped `actions/checkout` v4 -> v5 (runner node24 deprecation
  annotation; forced node24 lands 2026-06-16). YAML parse, forbidden-token
  scan, and `git diff --check` passed before commit.
- Workflow triage across the fork: the only workflow files on any branch are
  `install-matrix.yml`, `solar-ci.yml`, `solar-nightly-release.yml` (verified
  on `pkg/migration`, `origin/main`, `origin/openJiuwen-Solar`). The only run
  ever executed on the fork is the failed install-matrix run above; schedules
  are not firing (fork schedules dormant). No Mirage/drive-probe workflows
  exist anywhere.
- Removed `solar-nightly-release.yml` in commit `6800165` (`WS0: remove
  personal nightly release workflow`): it requires upstream-personal
  infrastructure (`vars.SOLAR_NIGHTLY_RUNNER` self-hosted runner, personal
  `vars.SOLAR_TVS_ROOT`, external release deps via nightly_release_doctor)
  — personal residue under the WS0 day-100 contract. Removed only on
  `pkg/migration`; fork `main` stays a pristine baseline mirror (a3a0eca)
  and its schedules are dormant, so no action there. `harness/` release
  tooling itself is untouched (product code, exercised by solar-ci).
- `solar-ci.yml` is legitimate product CI but its push trigger only covers
  `main`, so it has never run on this branch. Plan: run all five suites
  locally first, fix fixtures if needed, then extend its triggers to
  `pkg/migration` so green is provable in CI.
- Local solar-ci replication: all five suites were run from a fresh venv
  (pytest, requests, pyyaml, beautifulsoup4) mirroring the workflow steps.
  python-smoke, hf-ai-influence-smoke, harness-shell-smoke, and
  verification-release-gate passed directly. release-packaging-smoke
  initially "failed" only because my local mirror was stricter than the
  real job: `release/build.sh --dry-run` exits rc=2 by upstream design and
  the workflow itself tolerates any rc (`test "$dry_run_rc" -ge 0`); the
  job's remaining steps (output greps, plugin_loader validate --json,
  py_compile) all passed when replicated faithfully. Verdict: suites green
  at this tree, no fixture fixes needed. Commit `ac8738d` (`WS7: run
  solar-ci on migration branch`) adds `pkg/migration` to the push trigger
  and bumps checkout to v5.
- Static import gate (commit `a7162f9`, `WS7: add core import resolution
  gate`): `scripts/check-core-imports.sh` + documented allowlist + a
  `core-static` CI job in install-matrix. Gate 1: `bun build` must fully
  resolve the daemon + web dashboard entrypoint closure (19 modules,
  passes). Gate 2: lenient tsc sweep over all 131 core/ TS files fails on
  any TS2307 unresolved module outside `scripts/core-import-allowlist.txt`.
  Negative-tested with a planted ghost import (gate fails, names file and
  module). The gate is import-resolution only by contract: upstream core/
  carries ~100 pre-existing type errors (TS2345/TS2339/etc.) that are out
  of packaging scope and intentionally not gated.
- Import sweep findings (new, beyond the three known compat modules):
  `core/nerve/agents/recorder.ts`, `core/nerve/evolution-council.ts`, and
  `core/nerve/evolution-engine.ts` import npm packages `better-sqlite3`
  and `@anthropic-ai/sdk` that package.json does not declare. Verified no
  file in the repo imports any of those three modules — they are inert
  dev-side payload, so the dependencies were deliberately NOT added; the
  allowlist documents them and the gate fails if a shipped surface ever
  starts importing them. Also present but out of scope: TS2304 undefined
  names in `core/ui/v2/index.ts` and a TS2308 duplicate re-export in
  `core/ontology/index.ts` (type-level warts in optional/TVS surfaces, not
  resolution failures).

## Session 2 — fresh-eyes review of predecessor-authored code

- Scope reviewed: `install.sh`, all `lib/installer/*.sh`, all
  `components.d/*/component.sh`, `bin/solar`, `bin/solar-daemon`,
  `scripts/smoke-install-matrix.sh`, and the three compat modules
  (`core/daemon/skill-dispatcher.ts`, `core/orchestrator/*`,
  `core/config/privacy.ts`). Recorded decisions were not re-litigated.
- Defect 1 (fixed, `d1cccb1`): resolve_components silently dropped unknown
  `--components` names — a typo looked like a successful install. Now dies
  loudly listing known components; verified both rejection and the valid
  path.
- Defect 2 (fixed, `4ce3e80`): copy-engine's `cp -R` fallback ignored the
  exclude list, so machines without rsync would copy local runtime state
  (runs/, state/, caches, release artifacts) into installs, violating the
  sync contract. Fallback now enforces the same contract post-copy via
  `find -prune`. Also switched rsync directory excludes from `dir/***` to
  the equivalent trailing-slash form because newer macOS ships openrsync
  as rsync and the `***` form is not safely portable. Verified with a
  fixture tree on both the rsync path and a PATH-masked no-rsync path.
- Defect 3 (fixed, `5baebc5`): both doctor implementations failed the
  verdict when SOLAR.md was absent even for installs that legitimately
  exclude the kernel component. Kernel path is now fail-critical only when
  the receipt lists kernel (or lists nothing). Verified codex-bridge-only
  install: verdict=ok, kernel reported missing, uninstall residue-free.
- Standing decision executed (`7f65f4d`): the three compat modules now
  carry "Compatibility implementation — pending upstream original" headers
  and AGENTS.md gained a "Compatibility Modules" section with the
  do-not-extend rule. Entrypoint closure re-verified after the edits.
- Reviewed and judged NOT defects (left alone): `--no-hooks/--no-mcp/
  --no-modify-path/--quiet/--verbose` parsed and ignored (vacuously true in
  P1 — none of those subsystems are installed yet; P2/P3 wire them);
  bin/solar doctor text mode identical to --json (WS5 owns lifecycle UX);
  kernel sentinel append-on-corrupt-half-sentinel edge (smoke's
  sentinel-count assertion catches it; P2 sentinel rework owns robustness);
  duplicated doctor logic between installer and bin/solar (skeleton
  decision, not restyled); compat modules content (no defects found);
  smoke's fixed /tmp/solar.sock path (CI jobs are VM-isolated).

## Session 2 — driving install-matrix to green (CI round 1)

- Pushed `8e6e468..7f65f4d` (8 commits). Results at `7f65f4d`: Solar CI
  fully green on pkg/migration (first CI proof of the post-purge suites);
  install-matrix: core-static green, ubuntu/minimal green (first
  installer leg ever green in CI), ubuntu/full + both macOS legs failed
  in the smoke step.
- Fork job logs require admin auth, so commit `2b86b4d` (`WS7: surface
  smoke failure tail as annotation`) makes the workflow emit the smoke
  log tail as a `::error::` annotation on failure — annotations are
  publicly readable, which turns CI into a usable debugger here. (My
  first draft used `if ! cmd` with `status=$?` inside the branch, which
  reads the negation's status (0) and would have masked failures —
  caught and fixed before commit.)
- CI round 2 at `2b86b4d` decoded both real failures from annotations:
  1. macOS minimal AND full: db-init dies with "Runtime error near line
     33: no such module: fts5" — the macOS runner's sqlite3 CLI is built
     without FTS5, so the cortex schema's fts_unified_search virtual
     table cannot be created.
  2. ubuntu full: the post-uninstall residue assertion lists thousands of
     files under `home/.bun/install/cache/...` — `bun install` run with
     the sandbox HOME writes bun's user-level cache there, and uninstall
     correctly does not delete third-party caches.
- Fix for (1): db_init now applies the schema via python3's stdlib
  sqlite3 (`conn.executescript` per ordered file) instead of the sqlite3
  CLI. python3 is already a hard installer requirement and its bundled
  SQLite reliably includes FTS5; the sqlite3-CLI dependency disappears
  entirely (previously db init was silently SKIPPED when the CLI was
  absent — this also upgrades that to an unconditional init).
  Verified locally: fresh install creates 105 schema objects, an
  fts_unified_search INSERT + MATCH probe round-trips, uninstall is
  residue-free.
- Fix for (2): core-runtime's bun install now runs with
  `BUN_INSTALL_CACHE_DIR=$SOLAR_HOME/cache/bun`, keeping Solar's bun
  usage self-contained inside ~/.solar (removed wholesale on uninstall;
  a real user's own ~/.bun is never touched either way).
- Permanent CI assertions added per the clean-room-failure rule:
  `assert_db_schema` (three cortex tables present + live fts5 MATCH
  probe against the installed DB) and `assert_no_bun_home_leak`
  (`$HOME/.bun` must not exist after install) now run in every smoke
  profile.
## Owner actions needed (flagged, not simulated)

- P1 exit item "Claude session loads kernel": requires the `claude` CLI and
  an interactive one-time import approval. This is owner-verified by
  design — install on a real machine, open `claude`, confirm the
  `@~/.claude/solar/SOLAR.md` import approval prompt appears and the
  kernel content is loaded into the session. Not simulated here.
- P4 release checklist retains the real-hardware Windows 11 run
  (install.ps1 end-to-end including the one admin+reboot step).
- P1 "wizard-lite" status for transparency: the interactive path today is
  a resolved-selection summary plus a single proceed prompt; the numbered
  multi-select wizard remains WS4 work in a later phase. The
  non-interactive contract (--yes, --components, SOLAR_* env twins,
  --dry-run, --fake-keys, --skip-llm-cli) is complete and CI-gated, which
  is what the P1 exit criterion exercises.

- While re-running the full profile locally, found a REAL smoke defect:
  `bun run dashboard:web` spawns the actual server as a child process,
  so cleanup's single-pid kill leaked a live listener on port 3721; the
  NEXT run's dashboard then died with EADDRINUSE while wait_for_http
  spuriously passed against the stale listener (observed live: two
  leaked bun processes, the second run "passed" with its own dashboard
  dead). Smoke now starts daemon and dashboard as their own process
  groups (`set -m`) and kills the whole group, asserts port 3721 and
  /tmp/solar.sock are free BEFORE starting servers, and re-checks both
  processes are alive after their readiness gates. This closes both the
  leak and the spurious-pass mechanism.
- The process-group rework initially started daemon and dashboard
  concurrently, which surfaced a real race: both open the same fresh
  SQLite DB and the first opener's `PRAGMA journal_mode = WAL` needs an
  exclusive lock, so the daemon died with SQLITE_BUSY. The predecessor's
  sequential ordering (daemon -> socket up -> dashboard) was load-bearing;
  restored it with a comment explaining why, keeping the group-kill,
  precondition, and liveness improvements. Full profile then passed
  locally with zero leaked processes and no stale socket.
- Commits: `b01f7e0` (db-init via python sqlite3), `935e1de` (bun cache
  pinned into SOLAR_HOME), `880d990` (smoke lifecycle hardening +
  permanent assertions), `70763ef` (positive smoke-evidence notice
  annotation, since success previously left no API-readable trace).

## P1 CI matrix: GREEN on both OSes (verified with evidence)

- At `880d990` and re-confirmed at `70763ef`: install-matrix fully green —
  core import resolution, ubuntu minimal, ubuntu full-non-rust, macos
  minimal, macos full-non-rust. Solar CI green (all five suites). This is
  the first time the macOS legs have run anywhere, and the first fully
  green install matrix in CI.
- Positive evidence read back from the public notice annotations at
  `70763ef`, per leg: two "install complete" lines (initial + idempotent
  rerun), "db schema assertions passed" (cortex tables + live fts5 MATCH
  probe), and on both full legs "daemon socket gate: ok" + "dashboard
  http gate: ok"; every leg ends "smoke profile passed". The macOS legs
  additionally run the permanent "system bash 3.2" assertion step
  (verified green), satisfying the required /bin/bash (3.2) confirmation.
- P1 exit criterion status: all machine-verifiable items green in CI
  (install, doctor verdict ok, sentinel singleton, receipt, idempotent
  rerun, daemon + web dashboard boot gates, residue-free uninstall, db
  schema + fts probe, no bun-cache leak). The "Claude session loads
  kernel" item is owner-verified by design and remains flagged in
  "Owner actions needed" above. P1 is complete to its automatable
  boundary; proceeding to P2.

## WS2 Design Note (kernel-gen + excision + agents trim + rules)

Grounded in a 4-agent read-only analysis of CLAUDE.md, the 32 rules, the 135
agents, and a forbidden-token sweep of the installable payload (workflow
p2-ws2-understand, agent-verified). Design:

- **Fragments.** Root CLAUDE.md (481 lines) splits into `kernel/fragments/*.md`
  (always-kernel) + `kernel/components/*.md` (component-gated). Always-kernel:
  identity, memory, iron-rules, dod, checkpoints, lazy-load, rules-index,
  agents-base, announce, solar-max. Component: skills-md (the Superpowers
  auto-detect table). EXCISED whole: solar-farm rosters (19-44), xiaoai
  (46-55), GLM-only mode (183-198), skill_retriever MCP (341-413), gstack
  (415-481). Three tables get per-row surgery (iron-rules 57-69, pre-task
  self-check 112-140, mode-triggers 200-221): keep generic-discipline rows,
  drop rows that route to an excised external.
- **kernel.manifest + kernel-gen.sh.** Manifest lists ordered fragments with
  `requires=always|<component>`. `kernel-gen.sh` includes a fragment iff its
  requirement is met by the selected components, renders `{{VAR}}`, writes
  `~/.claude/solar/SOLAR.md` with a GENERATED header. Min assembly = kernel
  only; max = all P1 components. Both must be forbidden-token-clean and have
  no unresolved `{{`.
- **Rules.** Base kernel ships an allowlist of 21 rules (10 already clean +
  11 general-discipline rules after scrubbing incidental refs). 11 rules whose
  PURPOSE is an excised/optional component (delegate-*, solar-farm,
  solar-protocol, call-niuma, multi-expert, niuma-acceptance, master-brain,
  mempalace-diary, tvs-rendering) are PARKED: left in repo `rules/` for
  contributor visibility + future components, excluded from the install
  allowlist, not installed. Rules install to `~/.claude/solar/rules/` (never
  `~/.claude/rules/`).
- **Agents.** Base roster = exactly the 7 on the @Agent line (dev, qa, test,
  write, pm, secretary, researcher). They embed `mcp_tool: brain-router` +
  an external-model roster; scrub converts them to Claude-native (drop the
  brain-router frontmatter + external-model tables, keep the Claude Task
  tables + engineering principles). The other 128 ship only with an
  `agents-extra` component (off by default).
- **Hooks / intents.** `intent-engine-hook.sh` keeps its base signals
  (confirm/reject/save/execute/solar-start/solar-max/task-completed — all
  pure-shell, clean) and has its external-trigger blocks (brain-router
  mode-switch, solar-farm insight, xiaoai, plan-act, gstack skills) excised.
  Component intent triggers come from per-component `intents.conf` assembled
  into `~/.claude/solar/intents.conf`; in P1's shipped set none contribute
  triggers (all triggers were for excised externals), so the assembled file
  is minimal — the mechanism exists and is component-gated as specified.
- **Token scrub scope.** (1) gate-critical: literal forbidden tokens
  (brain-router, gstack, solar-farm, plan-act, ml-intern, skill_retriever,
  xiaoai/小爱, 昊哥) removed from shipped kernel assets. (2) privacy-critical:
  personal tokens (小爱/昊哥/xiaoai) parameterized out of the harness+core
  installed payload (parameterization, not internal rewrite — the WS0
  precedent). (3) documented residue: architectural names (solar-farm,
  gstack) deep in harness/core Python/TS internals are OUT OF SCOPE for
  rewriting and deferred to a WS7 gitleaks allowlist; 牛马 and 监护人 are
  persona vocabulary, NOT forbidden, and stay.
- **Gate.** A `kernel-gen-check` CI job builds min + max SOLAR.md assemblies
  and fails on any forbidden token or unresolved `{{`. Execution order:
  fragments+gen (commit A) -> scrub rules/agents/hook (commit B) -> scrub
  payload personal tokens (commit C) -> gate + assembly evidence (commit D).

## WS2 execution — kernel-gen + dangling-reference audit (commit A: 012bc95)

Authored kernel/fragments/*.md (11 always-kernel) + kernel/components/*.md
(4 P1 components) + kernel.manifest + lib/installer/kernel-gen.sh, and wired
the kernel component to call kernel_gen. Min/max assemblies verified
forbidden-token-clean with zero unresolved {{; minimal smoke green.

**Dangling-reference ruling (amends the kernel-gen-check contract — no silent
exceptions).** P2's contract is zero dangling references in the generated
kernel, not just zero forbidden tokens. The automated `kernel-gen-check`
gate (commit D) checks (a) zero forbidden tokens and (b) zero unresolved
`{{` over both min and max assemblies. Forbidden-token cleanliness already
forecloses references to the 7 externals' paths (core/solar-farm,
scripts/xiaoai, core/plan-act, mcp__brain-router, mcp__skill_retriever — each
contains a forbidden token). The remaining dangling risks are slash-command
and file references that are NOT forbidden tokens; these were audited by hand
during fragment authoring, each with a recorded disposition:

- `/insight` (was in lazy-load + checkpoints): its implementation is
  solar-farm (the "对话内3专家" panel; persistent path
  `core/solar-farm/insight-agent-v2.ts`). Since solar-farm is excised, the
  references were REMOVED, not kept — lazy-load drops the 洞察分析/深入洞察
  rows; checkpoints reworded "调用 /insight 深度研究" -> "补充研究".
- `/ontology load` (startup trigger): backed by core/ontology (ships with
  core-runtime) but there is no `/ontology` slash-command surface. Reworded
  to the truthful behavior "加载 Solar 上下文" (startup context load is real,
  via solar-session-start.sh), which promises no nonexistent command.
- `modes/*.md` (lazy-load step 2): no `modes/` dir exists anywhere in the
  repo. Reworded to "按上方模式触发表执行" (the in-kernel mode-trigger table is
  the actual handler).
- `delegate-check.sh` (pre-task self-check): the hook does not exist in the
  repo; the reference was dropped.
- `/save` (memory): RESOLVES to skills/save — kept.
- `~/Solar-MAX`, `STATE.md`, `DECISIONS.md` (solar-max): user-project
  convention files the mode instructs the user to create; not installed-tree
  refs — kept as documented mode behavior.

As defense-in-depth the kernel-gen-check additionally greps the assembled
kernel for a denylist of excised-subsystem path fragments
(core/solar-farm, scripts/xiaoai, core/plan-act, mcp__brain-router,
mcp__skill_retriever, insight-agent) so a future re-introduction fails CI
even if it were somehow not a bare forbidden token.

## WS2 execution — commits B/C/D

- Commit B (a1a08a9): rules + base-agents allowlists. 19-rule
  kernel/base-rules.txt (all literal-token-clean; intent-engine.md scrubbed
  to Phases 1-2); 7-agent kernel/base-agents.txt (Claude-native after a
  fanned-out + adversarially-verified scrub). copy_allowlist() fails loudly
  on a missing entry. 13 rules + 128 agents parked (in repo, not installed).
  Verified: install ships exactly 19 rules + 7 agents, zero forbidden tokens
  in installed rules/agents, parked rules absent, minimal smoke green.
- Commit C (f00c000): scrubbed 8 personal-token occurrences the earlier
  92-file pass missed (xiaoai IntentRule x2, 昊哥 in a regex/seed-list/ADR/
  setup seed/lessons log). py-compile + bash -n + JSON parse pass; harness
  intent-adapter / multi-task-entrypoint (solar-ci gate) / telemetry-audit
  tests green; zero personal tokens remain in harness + core.
- Commit D: scripts/check-kernel-gen.sh + a kernel-gen CI job. Builds min
  (kernel only, 246 lines) and max (all P1 components, 278 lines) SOLAR.md
  assemblies and fails on any forbidden token, unresolved {{, or
  excised-subsystem path fragment (denylist adds insight-agent); also scans
  the allowlisted base rules + base agents. Negative-tested: a planted
  gstack token fails both assemblies; passes again after restore.

- Documented residue (not personal-token, larger judgment): harness/brain/
  lessons.jsonl is 307 lines / 82KB of the author's development-sprint
  lessons (293 sprint-2026 entries), referenced by persona-config.sh. The
  one personal token in it was scrubbed (commit C), but the file is
  development history that a future WS0-style content pass should evaluate
  for day-100 compliance — flagged here, not silently shipped as "clean".
- Scope boundary for the installed-tree forbidden-token goal: SOLAR.md (all
  assemblies), the allowlisted base rules, and the 7 base agents are now
  forbidden-token-clean and CI-gated. The installed hooks tree is NOT yet
  curated — the kernel still copies all 87 hooks (22 carry forbidden
  tokens). Hook curation/scrub + settings.json registration is owned by
  task #9 (settings-merge), which will add the hooks to the clean-tree gate.
  P2's "zero forbidden tokens in installed tree" exit lands at the end of
  task #9, not task #8.

## WS3 + settings-merge + MCP Design Note (task #9)

- **Templating (WS3).** `lib/installer/render-template.sh` renders flat
  `{{VAR}}` placeholders (no logic) and fails loudly listing unresolved vars.
  `templates/config/*.template` -> `~/.solar/config.env` (machine data,
  created once, never overwritten) and `~/.solar/.env` (0600 secrets;
  --fake-keys reuses the existing harness pattern). Precedence: --set >
  SOLAR_<KEY> env > prompt (required vars only) > component defaults.env.
  The existing fake-key writer in the harness component migrates onto this.
- **Hook curation + payload.** The kernel stops copying all 87 hooks. A tight
  `kernel/base-hooks.txt` allowlist ships only the kernel-critical hooks +
  their dependencies, all forbidden-token-clean. Initial set: the scrubbed
  `intent-engine-hook.sh` (keystone, UserPromptSubmit) + its sole dependency
  `hook-logger.sh`. intent-engine-hook scrub: keep Phase-1 base signals
  1a-1i, Phase-2 @Agent, Phase-5 learning; excise 1j (brain-router mode),
  1k/1l (solar-farm /insight), 1m (xiaoai), 1n (plan-act), Phase-3
  (Superpowers, skills not shipped), Phase-4 (gstack). Two boot-reality path
  fixes: legacy `~/.solar/solar.db` -> `~/.solar/db/solar.db`, and the
  sibling source `~/.claude/hooks/hook-logger.sh` ->
  `~/.claude/solar/hooks/hook-logger.sh`. Additional kernel hooks ride with
  owning components later; the mechanism supports incremental registration.
- **settings.json merge.** `lib/installer/settings-merge.sh`: timestamped
  backup, python3 deep-merge (never sed), Solar entries keyed by the
  `~/.claude/solar/hooks/` command path prefix so add/remove is idempotent
  and never touches user-owned entries; doctor validates the JSON parses;
  `--no-hooks` skips. Per-component `hooks.json` supplies the settings
  entries; uninstall strips exactly the path-prefixed Solar entries.
- **MCP registration.** `lib/installer/mcp-register.sh` runs `claude mcp add
  <name> --scope user -- <cmd>` only when the `claude` CLI is present,
  records servers in the receipt, and `claude mcp remove` on uninstall;
  never hand-edits ~/.mcp.json; `--no-mcp` skips. The P1 component set
  declares no MCP servers (brain-router/skill_retriever excised, mempalace
  is a later component), so this is a working no-op now — mechanism present
  and component-gated.
- **Gate.** Extend the clean-tree forbidden-token check to the installed
  hooks tree (now an allowlist of clean files), completing P2's "zero
  forbidden tokens in installed tree" exit. settings-merge gets an
  idempotency + path-prefix-isolation test (merge twice -> identical; a
  user-owned hook entry survives add and remove).

## Task #9 execution — WS3 templating + settings-merge + MCP (commits F-E)

All five pieces landed and pushed, each one concern per commit:
- F (17925df): kernel hook curation. intent-engine-hook.sh scrubbed 640->319
  lines (kept Phase-1 base signals + Phase-2 @Agent + Phase-5/6/7
  learning/dashboard/completion; excised brain-router mode-switch, solar-farm
  /insight, xiaoai, plan-act, Superpowers, gstack). kernel/base-hooks.txt
  ships only the keystone + hook-logger. Two boot-reality path fixes
  (DB path; BASH_SOURCE-relative sibling source). Boot-reality correction:
  the @Agent case map omitted @Dev/@QA/@Test/@Write — realigned to exactly the
  7 installed base agents (all 7 verified to dispatch). Gate extended to scan
  installed hooks.
- G (e193e9b): settings-merge.sh — python3 deep-merge into ~/.claude/
  settings.json, Solar entries keyed by /solar/hooks/ path segment, idempotent
  add, backup ONLY on real change over pre-existing content (so fresh +
  idempotent leave no backup residue), --no-hooks skips. bin/solar uninstall
  strips by the same marker. Verified: fresh+idempotent -> 1 registration / 0
  backups / residue-free uninstall; a user settings.json (model key + user
  hook) fully preserved through add and remove. Permanent smoke assertion.
- H (353fb07): mcp-register.sh — claude mcp add <name> --scope user; recorded
  to registered-mcp.txt; bin/solar uninstall claude mcp remove. Skips without
  claude CLI / --skip-llm-cli / --no-mcp. No P1 component declares a server
  (working no-op); the real code path is exercised by a synthetic-component
  test with a fake claude binary (verified add + remove invocations).
- E (e176773): render-template.sh — flat {{VAR}} rendering, precedence
  --set > SOLAR_<KEY> env > defaults, fails loudly on unresolved vars.
  config_init writes ~/.solar/config.env once (never overwritten). New --set
  flag. Verified: rendered (no literal {{}}), user edit survives reinstall,
  fails rc=1 on unresolved var, residue-free. Permanent smoke assertion.

P2 "zero forbidden tokens in installed tree" status: SOLAR.md (all
assemblies), the 19 base rules, the 7 base agents, and the 2 base hooks are
all forbidden-token-clean and CI-gated by kernel-gen-check. The
harness/core architectural-name residue (solar-farm/gstack inside Python/TS
internals) remains documented out-of-scope for rewriting, deferred to a WS7
gitleaks allowlist. Personal tokens are gone everywhere installed.

## P2 COMPLETE — CI-verified (commit e176773)

install-matrix all green on both OSes: kernel-gen check, core import
resolution, ubuntu+macOS minimal, ubuntu+macOS full-non-rust. Solar CI all
5 suites green. macOS full-non-rust evidence annotation confirms every gate
ran: install complete (initial + idempotent), db schema assertions passed,
config.env rendered: ok, settings hook registration: ok, daemon socket gate:
ok, dashboard http gate: ok, smoke profile passed.

P2 exit criteria met: kernel-gen-check green; installed kernel tree (SOLAR.md
+ 19 rules + 7 agents + 2 hooks) forbidden-token-clean and CI-gated; personal
tokens gone from all installed payload. Documented out-of-scope residue:
harness/core architectural names (solar-farm/gstack in Python/TS internals),
deferred to a WS7 gitleaks allowlist; harness/brain/lessons.jsonl dev-history
flagged for a future WS0 content pass.

Owner-held items still flagged (not simulated): the "Claude session loads
kernel" manual check (needs claude CLI + the one-time @import approval); the
P4 real-hardware Windows run. P3 (WS5 lifecycle, WS6 daemons, mempalace +
remaining skill components, install.ps1) and P4 (full matrix/docs/release
cut) remain.

## P2 Residue & Open-Functionality Ledger

### 1a. Hooks 87 → 2: what is NOT shipped, and what that silently breaks

The base kernel ships exactly 2 of 87 hook files (kernel/base-hooks.txt):
`intent-engine-hook.sh` (the only one REGISTERED, on UserPromptSubmit) and
`hook-logger.sh` (a sourced dependency, not an event hook). 85 are not
shipped. No gate can detect a missing hook, so this is the only record.

**HEADLINE FINDING (load-bearing gap):** the shipped kernel (SOLAR.md)
*documents* a memory protocol (防止记忆丢失), cortex/favorites iron rules
(设计前查Cortex / 存Favorite), and tool-safety/quality disciplines, but ships
and registers NONE of the hooks that enforce them. Only UserPromptSubmit
intent detection is wired. The kernel currently describes behaviors it does
not actuate. These are not "excised" — they are clean, functional, and
silently absent.

**Bucket A — excised-external machinery (correctly dropped, 42).**
Forbidden-token-dirty (21, tied to brain-router / solar-farm / xiaoai /
plan-act / the self-evolution + session-memory-agent + orchestration stacks):
context-preload, design-cortex-reminder, evolve-auto-record,
evolve-pre-tool-advisor, evolve-subagent-tracker, honcho-session-end,
honcho-session-start, memory-auto-updater, memory-extract-hook,
memory-recall-hook, post-tool-dispatcher, skill-forge-update,
skill-improver-auto, sma-session-end-consolidate, sma-session-logger,
solar-session-start, solidifier-cron, state-inject, task-completion-tracker,
user-modeler-update, user-profile-inject.
Clean but bound to an excised/optional subsystem (21 — self-evolution,
mempalace [not a P1 component], the lessons.jsonl whisper system,
persona-learning): auto-boost-capability, capability-scorer,
scan-low-quality-capabilities, self-evolve-postmortem, post-tool-failure-recorder,
mem-health-check, mempal_precompact_hook, mempal_save_hook,
enhanced-memory-writer, agent-recall-precompact, agent-recall-start,
agent-recall-stop, memory-consolidate-hook, memory-influence,
sma-auto-consolidate, subconscious-learn, subconscious-whisper,
whisper-hook-v2, personality-anchor-hook, personality-injector, texture-inject.
Revisit Bucket-A-clean if/when mempalace or a self-evolution component ships.

**Bucket B — clean, load-bearing, SILENTLY MISSING (17). NAMED P3 follow-ups.**
These implement behaviors the shipped kernel promises and must be curated
(scrub any dirty sibling, fix the ~/.claude/solar/hooks sibling-source path
as done for intent-engine-hook, then register via per-component hooks.json):
- **P3-HOOK-1 memory protocol** (kernel "防止记忆丢失": STATE.md read on start /
  write on compact / update on end / /save on subtask):
  session-resume-hook (SessionStart, STATE.md read), pre-compact-anchor
  (PreCompact, STATE.md inject — verified clean+self-contained),
  state-auto-updater (SessionEnd, STATE.md Progress), state-read-enforcer
  (PreToolUse gate), state-read-tracker (PostToolUse), solar-stop-reminder
  (Stop), session-end-save (SessionEnd, /save), auto-checkpoint (periodic
  /save), context-monitor (PostToolUse, /save+STATE.md). NOTE the SessionStart
  STATE.md+identity injectors state-inject & solar-session-start are in Bucket
  A (dirty: brain-router/Master-Brain); session-resume-hook is their clean
  counterpart, so P3 either ships the clean one or scrubs the dirty pair.
- **P3-HOOK-2 cortex/favorites iron rules** (kernel "设计前查Cortex"/"存Favorite";
  the DB tables exist from the schema consolidation but nothing populates/reads
  them via hooks): auto-favorites-extract (PostToolUse → sys_favorites, verified
  clean), sma-session-start-preload (SessionStart → cortex_sources+sys_favorites
  preload), cortex-hook (UserPromptSubmit → cortex; also touches ontology/persona,
  trim those before shipping).
- **P3-HOOK-3 tool safety / quality** (referenced by no-tmp-artifacts + coding
  rules + DoD): pre-bash (command safety), pre-edit / post-edit (file check /
  auto-format), quality-gate (task-completion gate), task-guard.

**Bucket C — clean, neutral, omission is low-risk (26).** No kernel-promised
behavior depends on these; SOLAR.md itself carries the identity the
reminders would inject: asset-reminder, code-review-reminder,
executor-reminder, experience-reminder, identity-reminder, mid-refresh,
session-checkpoint, session-reflect, session-refresh-assets,
permission-auto-approve, remote-inbox-watcher, harness-next-hook,
solar-pre-tool, solar-post-tool, solar-prompt-submit, solar-stop,
solar-tool-result, solar-harness-status-inject, learning-capture,
planner-review-drafting, perf-auto-refresh, ses-session-end,
subagent-start-tracker, subagent-stop-tracker, ree-first-hook,
task-completed-hook. (Count: A=42, B=17, C=26 → 85. ✓)

### 1b. lessons.jsonl — RESOLVED this session (commit 71b4688)

harness/brain/lessons.jsonl shipped 307 lines / 82KB of the author's
development-sprint lessons (all source:eval, sprint-2026* IDs) into the
installed payload — accumulated dev-history, a day-100 violation in the same
category as the already-purged solar.db / runs/ / sprints/. RESOLVED by
scrubbing to empty (0 bytes): it is an append-only learning log whose correct
fresh-install state is empty, and every reader degrades gracefully on an
absent/empty file. Not deferred — done, gated, pushed.

### 1c. Forbidden-token claim, stated with its asterisk

"Forbidden-token-clean" means: the INSTALLED KERNEL TREE — generated SOLAR.md
(all assemblies), the 19 base rules, the 7 base agents, and the 2 base hooks —
is clean and CI-gated by kernel-gen-check, and ALL personal tokens
(小爱/昊哥/xiaoai/LAN IPs/lisihao paths) are gone from the entire installed
payload (kernel + harness + core). It does NOT mean the repo is globally
token-free: the architectural names `solar-farm` and `gstack` still appear in
harness/ and core/ Python/TS internals (47 + 28 occurrences) that are
explicitly OUT OF SCOPE for rewriting. Those are deferred to a WS7 gitleaks
allowlist (tracked below); they do not reach the installed *kernel*.

### Task 2 note — upstream export request drafted (commit 3a02949)

docs/UPSTREAM-EXPORT-REQUEST.md is a DRAFT (not sent) for the owner to forward
via their direct supervisor, team-framed: requests redistribution-compatible
export of TVS (termplane + llm submodule) and the upstream originals of the
three compat modules (skill-dispatcher, orchestrator/*, config/privacy), with
if-granted / if-not dispositions and no runtime-data/credential ask. The
owner forwards; this session does not send.

## P3 Handoff Note (for a Codex session)

Branch pkg/migration, HEAD 3a02949 (after this session). P1+P2 CI-green;
WS5 lifecycle DONE this session (ee74041). Standard gate for EVERY increment:
sandbox `HOME=$(mktemp -d)` smoke green + `solar doctor --json` verdict==ok +
residue-free uninstall; commit one concern, privacy scan + `git diff --check`,
push origin only.

Sequence:
1. **WS5 lifecycle — DONE (ee74041).** update/backup/restore in bin/solar,
   receipt-driven, round-trip verified.
2. **WS6 daemons (OFF by default).** darwin: render plist → ~/Library/
   LaunchAgents + launchctl; linux/WSL: render unit → ~/.config/systemd/user
   + `systemctl --user enable --now` + linger note; no systemd → skip with
   reason. Gate: component install/verify in sandbox; daemon start is only
   partially CI-testable (no user-session systemd/launchctl on GH runners) →
   render+lint+dry-run in CI, real start = manual checklist item.
3. **mempalace + remaining skill components.** mempalace MCP server +
   requirements (chromadb + sentence-transformers — multi-GB; decide CI dep
   policy: full vs deps-light). Skill components (browser/office/obsidian/
   calendar) are low-risk, fully CI-testable copy+verify — do these first.
   Gate: doctor + venv import smoke.
4. **WS8 install.ps1.** Windows WSL2 bootstrapper + PSScriptAnalyzer lint.
   Real E2E run is owner-held at P4 (GH runners lack nested virt) → ships as
   lint-gated code + docs/WINDOWS.md checklist.

Carry-forward TRACKED items:
- **1a hook follow-ups (P3-HOOK-1/2/3):** ship the 17 Bucket-B load-bearing
  hooks (memory protocol, cortex/favorites, tool-safety) via per-component
  hooks.json + settings-merge; scrub the dirty SessionStart STATE.md pair if
  identity injection is wanted; apply the BASH_SOURCE sibling-source path fix.
- **1b lessons.jsonl:** RESOLVED (scrubbed empty, 71b4688) — no carry-forward.
- **WS7 gitleaks allowlist:** add a harness/core allowlist for the
  out-of-scope architectural names (solar-farm/gstack internals) so the
  repo-wide privacy gate is green; keep the kernel-tree zero-tolerance gate.
- **WS9 launchers (post-Release):** deferred.
- **Owner kernel-load check:** install on a real machine, open `claude`,
  confirm the @~/.claude/solar/SOLAR.md import-approval prompt loads the
  kernel. Owner-held, not simulatable in CI.

### Handoff caveat — reconcile with live branch before starting
This note's state is a snapshot at HEAD 3a02949. pkg/migration is being
actively pushed to by a parallel build session, so by the time it is read the
branch may already have advanced — WS6 (or more) may be partially or fully
done. DO NOT trust this snapshot: `git fetch` + read the latest WORKLOG/commits
and re-run the sandbox smoke against live HEAD FIRST, and skip any sequence
step already completed, to avoid duplicating the parallel session's work.

## P3 Takeover (Claude, all of P3 incl. hooks as first-class)

Owner dissolved the Claude/Codex split: this session executes ALL of P3,
hook follow-ups as step 1. Inherited-state verdict:
- git fsck --full clean (only harmless dangling blobs); worktree clean
  (MIGRATION_PLAN.md + WORKLOG.md local-only, intact, end as described).
- HEAD == origin/pkg/migration == 3a02949 exactly; 3a02949 ≥ baseline. No
  foreign delta to absorb.
- CI GREEN at HEAD 3a02949 AND at WS5 ee74041 (install-matrix + Solar CI
  both success) — closes the open "check WS5 CI for ee74041" item: GREEN.
- WS5 surface: bin/solar has doctor/update/backup/restore/uninstall
  [--keep-data]/components list (all present). GAP (small, in-scope): the
  install-matrix smoke does not yet exercise `solar update` (no-op
  round-trip) — to be added so the P3 exit criterion (doctor/update/
  uninstall round-trip green IN CI) is met.
- Re-read the P2 ledger 1a: the 17 Bucket-B hooks are binding work items;
  the ledger governs over any summary.

## P3-HOOK-1 Design Note (memory protocol)

Ship the safe, non-blocking memory-protocol hooks that enforce the kernel's
防止记忆丢失 fragment, registered on the kernel component via hooks.json +
settings-merge. Of the ledger's 9 HOOK-1 candidates, ship 7 and PARK 2 with
evidence:
- PARK state-read-enforcer.sh: exits 2 to BLOCK all tool use until STATE.md
  is read — far too intrusive as a community default; the read-first
  discipline stays documented in the kernel, not hard-enforced.
- PARK auto-checkpoint.sh: time-triggered (每30分钟), no Claude Code event
  maps to it → belongs to cron/WS9, not a settings.json hook.
Ship (7): session-resume-hook (SessionStart), pre-compact-anchor (PreCompact;
normal path exit 0 inject, exit 2 only to block compaction by design),
state-auto-updater + session-end-save (SessionEnd), solar-stop-reminder
(Stop), state-read-tracker + context-monitor (PostToolUse). All clean. Path
fixes applied (the intent-engine-hook precedent): sibling source ->
$(dirname "${BASH_SOURCE[0]}")/ (pre-compact-anchor, solar-stop-reminder);
legacy DB ~/.solar/solar.db -> ~/.solar/db/solar.db (state-auto-updater,
session-end-save). The kernel-gen-check already scans every base-hooks.txt
entry, so new hooks are auto-gated for forbidden tokens.
