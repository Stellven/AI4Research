# OpenSolar → Community-Distributable Package: Migration Plan

## Context

The OpenSolar repo ("Solar" — an AI-orchestration framework layered on Claude Code: a CLAUDE.md kernel + 32 rules + 89 hooks + 136 agents + bun/TS `core/` + Python `harness/` + ~38 skills, installed into `~/.claude` and `~/.solar`) today only installs correctly on its author's machines. Goal: a stranger on a fresh machine runs a short interactive setup (or a fully unattended one in CI) and gets a working, doctorable, cleanly-uninstallable Solar. **Packaging work, not a rewrite** — `core/` TS, `harness/` Python, and skill internals are not rewritten.

User direction: platforms = macOS + Linux first-class, **Windows via installer-auto-provisioned WSL2** (single command; only one admin/reboot step may remain manual); installer tech decided via deep research into exemplars (OpenClaw, OpenHands, Aider/Ollama/Goose/Claude Code, SuperClaude/BMAD/claude-flow, rustup/uv/Homebrew/oh-my-zsh/nvm/chezmoi); the distributable must read as "day 100" polish — no personal artifacts, no development history.

## Baseline provenance (verified — pinned)

- Audited tree = **`a3a0eca`** (2026-06-05). All fork refs — `main`, `openJiuwen-Solar`, `claude/eager-bell-caedu6` — point to this same commit (verified via local git AND GitHub API `list_branches`).
- History: 99 commits, one continuous lineage 2026-05-19 → 2026-06-05, authored solely by upstream's two accounts (`lisihao` / `sihaoli` — same person; interleaved work, lisihao merges PRs containing sihaoli commits). Root commit `d2f0cea` is a 2,282-file bulk import (mislabeled `Revert "Harden harness route startup checks"`) — the public extraction; no pre-import baseline exists in-repo.
- **Teammate check: clean.** GitHub API `list_commits(author=coconut-chicken)` → zero commits; no extra branches on the remote. The audited tree contains no teammate contamination.
- The "partial Codex-migration / modularization" artifacts in the tree are **upstream-authored** (present since root import or lisihao's June-1 commit): `install-core.sh` + `package.json` v3 bin model (`bin/` never existed in ANY commit), `core/daemon/` (TVS-free daemon entrypoint, unreferenced by kernel), `codex-bridge/` (documented README feature), `AGENTS.md`, `.clawhub/lock.json`. Treatment is explicit per-artifact below.
- **P0 step 0**: assert `git merge-base --is-ancestor a3a0eca HEAD` and that any commits above `a3a0eca` are this migration's own; if foreign commits appear, privacy/forbidden-token audit the delta before proceeding.

## Why the current state fails a stranger (verified by 3-agent codebase audit)

1. **Personal data committed**: `/Users/lisihao` in 1700+ lines (`harness/config/*.yaml`, `harness/launchd/*.plist`, `deploy/launchd/*.plist`, 52MB `harness/sprints/`), personal email + Google Drive mount in `harness/config/mirage.solar.yaml`, `Macmini-2-Macbook.sh` with home IPs. Committed runtime state: `core/db/solar.db` (958KB — the only committed DB, confirmed), `.solar/`, `insight-reports/`, `harness/runs|intents/`, `.DS_Store`, stale backups.
2. **Broken references**: root `install.sh` inits DB from `core/schema.sql` which is **confirmed absent** — real schemas live in 12 pinned files (see WS1); `package.json` declares nonexistent `bin/solar`; dependency `"tvs": "file:../TVS"` breaks `bun install` on every fresh clone; hooks query DB tables (`cortex_sources`, `sys_favorites`, `fts_unified_search`) no schema creates.
3. **Kernel dangles**: installed `CLAUDE.md` hard-references 7 components with no source in repo (brain-router MCP, skill_retriever MCP, solar-farm, plan-act, xiaoai secretary, ml-intern, gstack) — also referenced from `hooks/intent-engine-hook.sh` and several `rules/*.md`.
4. **macOS lock-in**: BSD `sed -i ''`/`date -v` in ~6 hooks + email-to-calendar; `launchctl` in 6 component installers; `/opt/homebrew/bin/python3.11` hardcoded 6+ places; `deploy/install-deps.sh` exits on non-Darwin.
5. **No manifests**: no requirements.txt (python deps ad-hoc: chromadb, sentence-transformers, mcp, pyyaml); Rust components source-only; repo ships **no settings.json** — the 89 hooks are currently never wired into Claude Code (registration is new authoring work, bounded).
6. **No installer contract**: root `install.sh` has no flags/preflight/interactivity/uninstall; only `harness/installer/install.sh` (426 lines) has the right shape (preflight, `--non-interactive`, `--fake-keys`, doctor, upgrade) — it's the in-repo pattern source.
7. Docs disagree on the repo URL (lisihao/Solar vs anthropics/solar; actual: suraj-subrahmanyan/opensolar). No real secrets committed; all endpoints public.

## Research basis (5-track web deep-research, primary sources, adversarially verified)

- **Installer contract** (rustup/uv/Homebrew/oh-my-zsh/nvm/deno): interactive wizard default on TTY (rustup "1) Proceed 2) Customize 3) Cancel" + options summary); single `--yes`; env-var twin for every knob; non-interactive auto-detect triad `NONINTERACTIVE` > `$CI` > `[ ! -t 0 ]` with printed reason; `--dry-run`; PATH edits announced + `--no-modify-path`; idempotent re-run; uv-style **install receipt JSON** for residue-free uninstall/update; functions-only script with `main "$@"` last line; fail loud with exact remedy.
- **Component/flag vocabulary** (BMAD): `--yes --components ... --set key=value --list-components`; manifest records exactly what's on disk → quick-update + drift detection.
- **Category failure modes** (SuperClaude #87, ruflo #1597/#670): never overwrite `~/.claude/CLAUDE.md`; uninstall must stop daemons and remove live SQLite residue.
- **Claude Code native seams** (verified vs official docs 2026-06): `@import` works in user `~/.claude/CLAUDE.md` (one-time approval, 4-hop depth); `claude mcp add <name> --scope user -- <cmd>` sanctioned; settings.json hooks schema documented + sanctioned; **`~/.claude/rules/*.md` AUTO-LOADS at session start** → Solar's 32 lazy-load rules must NOT go there (relocate to `~/.claude/solar/rules/`); plugins cannot load root CLAUDE.md nor bootstrap `~/.solar` → custom installer required, plugin packaging phase-2; skills have no native `requires:` frontmatter → dependency gating lives in component manifests.
- **Windows reality** (Claude Code/Homebrew/nvm/OpenHands): WSL2-first is a documented accepted pattern; per user direction we go further — `install.ps1` auto-provisions WSL2 (see WS8) instead of docs-only.
- **Wizard exemplar** (OpenClaw `onboard`, Goose `configure`): every wizard question flag-addressable; chain installer → wizard but skip without TTY; secrets via env refs that fail fast; user-level daemons (LaunchAgent / systemd --user + linger); `doctor`/`update`/`uninstall --dry-run` lifecycle.

## Resolved decisions (provenance + coupling verified)

- **Codex/v3 artifacts**: `codex-bridge/` ships as OFF-by-default optional component (documented README feature, zero runtime deps). `AGENTS.md` is rewritten as a contributor-facing doc (Codex-convention file; not installed). `.clawhub/lock.json` deleted (OpenClaw registry residue). `install-core.sh` deleted (orphan; references never-existing `bin/`). `core/daemon/` **stays in core-runtime** — verified TVS-free (`server.ts` imports only scheduler/queue/workflow/plugin-host) and it's the daemon behind `package.json` dev/daemon scripts; `bin/solar-daemon` wraps it as planned.
- **Dashboard/TVS (resolved by import-graph)**: the **daemon (`core/daemon/server.ts`) and web dashboard (`core/dashboard/server.ts`, serves `demos/solar-dashboard.html` + `demos/orchestrator-dashboard.html`) are TVS-free** → both ship in core-runtime and form a REQUIRED CI gate (daemon boots; dashboard route serves 200). TVS (`tvs/termplane/...`) is hard-imported ONLY by terminal-TUI surfaces: `core/ui/**`, `core/daemon/ui-watcher.ts`, `demos/agent-dashboard.ts`, plus harness `tvs_render_cli` (which already degrades via `SOLAR_TVS_ROOT` with a clear error). These form optional component `tvs-tui`. **TVS source is NOT in this repo and has no license grant → vendoring requires obtaining it.** P0 owner action: request TVS source + redistribution license from upstream (lisihao). If granted by P1 → vendor as workspace package, fold `tvs-tui` into core-runtime, add TUI render smoke to CI. If not → `tvs-tui` stays optional behind user-supplied `SOLAR_TVS_ROOT`, its package.json scripts are pruned from defaults, and `dashboard:web` is THE shipped dashboard. TVS is never redistributed without explicit license.
- The two dashboard HTML files in `demos/` are runtime assets of core-runtime → relocate to `core/dashboard/assets/` (path fix in `core/dashboard/server.ts` only) so `demos/` stays dev-only.

## Target architecture

**Installed layout** (user machine):

```text
~/.claude/CLAUDE.md            # user's own; gets ONE sentinel-marked block: @~/.claude/solar/SOLAR.md
~/.claude/solar/               # all Solar kernel assets, namespaced & uninstall-safe
  SOLAR.md                     # GENERATED kernel (per selected components, zero dangling refs)
  SOLAR.local.md               # user extension point, never touched on upgrade
  rules/  hooks/  agents/  prompts/  intents.conf      # rules here, NOT ~/.claude/rules/ (auto-load trap)
~/.claude/settings.json        # Solar hook entries merged in (identified by ~/.claude/solar/hooks/ path prefix)
~/.claude/skills/<name>/       # selected skills (native auto-discovery)
~/.solar/                      # runtime root (SOLAR_HOME override)
  install-receipt.json  config.env  .env (0600)  db/solar.db  venv/  harness/  mempalace/  bin/
```

**Repo layout** (new pieces):

```text
install.sh                      # rewritten thin entry (~150 lines, bash-3.2-safe)
install.ps1                     # Windows entry: WSL2 auto-provision + arg passthrough (WS8)
lib/installer/{common,preflight,components,wizard,copy-engine,render-template,
               kernel-gen,settings-merge,db-init,paths,receipt,doctor,uninstall}.sh
components.d/<name>/{component.sh,hooks.json,intents.conf,defaults.env}
kernel/{kernel.manifest,fragments/*.md,components/*.md}
templates/config/*.template  templates/daemons/*.{plist,service}.template
requirements/{harness,mempalace}.txt
core/db/schema/*.sql            # consolidated from the 12 pinned schema files, all IF NOT EXISTS
bin/{solar,solar-daemon}        # satisfies existing package.json bin declarations
docs/{COMPONENTS.md,UNINSTALL.md,WINDOWS.md}  INSTALL.md  get-solar.sh (curl|bash bootstrap)
.github/workflows/install-matrix.yml
```

**Components (v1)**: `kernel` (kernel+rules+hooks+agents/base; coreutils+python3-for-JSON only) · `core-runtime` (core/ TS incl. daemon + web dashboard + dashboard assets; requires bun; **dashboard is a required CI gate**) · `harness` (python3; tmux optional) · `skills-md` · `skills-browser` (requires cargo) · `skills-office` · `skills-obsidian` · `skills-calendar` (darwin-only) · `mempalace` (python3 + venv) · `codex-bridge` (OFF) · `daemons` (darwin/linux, OFF) · `agents-extra` · `tvs-tui` (core/ui + ui-watcher + agent-dashboard TUI; requires vendored TVS or `SOLAR_TVS_ROOT`; OFF until TVS rights resolve). Splitting `kernel` from `core-runtime` means a stranger without bun still gets a working Claude Code overlay.

**Component manifest** (`components.d/<name>/component.sh`, bash-sourceable):

```bash
COMPONENT_NAME="mempalace"; COMPONENT_DESC="Semantic memory MCP server"
COMPONENT_DEFAULT="off"            # on|off|auto (auto = on iff requirements met)
COMPONENT_PLATFORMS="darwin linux" # wsl ≡ linux
COMPONENT_REQUIRES_BINS="python3"; COMPONENT_REQUIRES_COMPONENTS="kernel"
COMPONENT_PYTHON_REQS="requirements/mempalace.txt"
COMPONENT_CONFIG_VARS="VAULT_PATH:required:Path to knowledge vault"
COMPONENT_KERNEL_FRAGMENTS="components/mempalace.md"
COMPONENT_MCP_SERVERS="mempalace:$SOLAR_HOME/venv/bin/python $SOLAR_HOME/mempalace/server.py"
component_install(){ copy_payload mempalace "$SOLAR_HOME/mempalace"; }
component_verify(){ [ -f "$SOLAR_HOME/mempalace/server.py" ]; }
component_uninstall(){ :; }  # receipt removes files; only extra teardown here (daemons etc.)
```

**Installer flow**: parse args → detect OS/TTY/CI → load manifests → resolve selection (flags/env/wizard/safe default `kernel,harness`+`core-runtime` if bun, printed) → preflight table (aggregate requires_bins; fail-fast with remedy or offer skip of optional components) → wizard if TTY (banner → preflight → numbered multi-select with defaults pre-marked → required-var prompts for selected components only → options summary → 1/2/3) → execute per component in topo order (dirs → copy → venv/pip → db-init → render templates → kernel-gen → CLAUDE.md sentinel → settings-merge hooks → `claude mcp add` → PATH) → write receipt atomically → per-component verify + doctor → summary + next steps.

**Flags/env** (every flag has `SOLAR_*` env twin): `--yes/--non-interactive`, `--components LIST`, `--list-components`, `--set KEY=VALUE`, `--dry-run`, `--solar-home`, `--claude-dir`, `--no-modify-path`, `--no-hooks`, `--no-mcp`, `--skip-llm-cli`, `--fake-keys`, `--force` (overwrite collisions, still backed up), `--reset-db`, `--channel/--version`, `--verbose/--quiet/--help`. Non-interactive + missing required var → fail loud with exact `--set` remedy.

**Receipt** (`~/.solar/install-receipt.json`): schema, version, git_sha, source_dir, os, per-component file lists + config_vars, sentinel locations (CLAUDE.md / settings.json / shell rc), mcp_servers, daemons, backups. Powers doctor drift-check, idempotent re-run diff, `solar update`, residue-free uninstall.

**Config templating** (chezmoi pattern, pure bash): flat `{{VAR}}` placeholders only (no template logic — conditionality lives at component level); render fails loudly listing unresolved vars. Precedence: `--set` > `SOLAR_<KEY>` env > interactive prompt (required vars only) > `components.d/<c>/defaults.env`. Machine data: `~/.solar/config.env` (created once, never overwritten); secrets in `~/.solar/.env` (0600; `--fake-keys` reuses harness write_env pattern). Personal identity (guardian name etc.) becomes `{{SOLAR_GUARDIAN_NAME}}`.

**Kernel generation**: `kernel.manifest` lists ordered fragments with `requires=<component|always>`; `kernel-gen.sh` includes fragments for selected components, renders vars, writes `~/.claude/solar/SOLAR.md` ("GENERATED — do not edit" header). Root `CLAUDE.md` is split into `kernel/fragments/` (identity, memory protocol, iron rules, checkpoints, mode triggers, rules index, base agent roster) + `kernel/components/*.md`; sections for the 7 unshipped externals are dropped (or parked in component fragments for the future). Root `CLAUDE.md` becomes contributor instructions. `intent-engine-hook.sh` reads generated `~/.claude/solar/intents.conf` assembled from per-component `intents.conf`. The `@~/.claude/solar/SOLAR.md` import is verified working (one-time approval dialog — document it); fallback = inline assembled content inside the sentinel block.

## Workstreams

**WS0 — Archive & "day 100" purge (S/M)**. FIRST: push tag `archive/pre-community-<date>` + branch `archive/personal-history`; then assert baseline (P0 step 0). Public v1 is later cut as an **orphan branch with squashed history** (user's "show day 100, not the history"; personal data lives in git history too). Delete from worktree: `harness/sprints/**`, `harness/runs/`, `harness/intents/`, `core/db/solar.db`, `.solar/`, `insight-reports/`, `CLAUDE.md.backup.*`, `agents/secretary.md.bak`, `.DS_Store` (all), `Macmini-2-Macbook.sh`, `package-lock.json` (bun.lock canonical), `install-core.sh`, `.clawhub/`, `deploy/install-deps.sh` + `deploy/SETUP.md` (absorbed), empty `secretary/openclaw/`, `GITHUB-PURGE-NOTICE.md` (obsolete after cut). Rewrite `AGENTS.md` as contributor doc. Convert to templates (→WS3): 5 personal `harness/config/*` + all launchd plists. Harden `.gitignore` (db/wal/shm, .solar/, runs, sprints, intents, insight-reports, .bak, .DS_Store, .env).

**WS1 — Dependency & manifest repair (M)**.

- `package.json`: remove `"tvs": "file:../TVS"`; tvs-importing TS (core/ui/**, ui-watcher, agent-dashboard) moves behind `tvs-tui` (see Resolved decisions); keep `bin` entries (real files in WS5); prune TUI scripts from defaults if TVS not vendored.
- Create `requirements/{harness,mempalace}.txt` (audit `harness/lib/*.py` imports).
- **DB consolidation — pinned source files (confirmed present at baseline)**: `core/{backlog,hive,message-listener,nerve,resource,smi}/schema.sql`, `core/ontology/schema.sql` + `schema-v2.sql` (dedup decision: v2 wins, v1 archived), `core/shortcuts/shortcuts-schema.sql` + `shortcuts-seed.sql`, `harness/experience/index.db.schema.sql`, `harness/scripts/tech-hotspot-radar/schema.sql` (ships with its optional component, not core). `core/schema.sql` confirmed absent — the install.sh reference is dead. P0 re-verifies this exact list before db-init work starts.
- **`40-cortex.sql` derivation (no guessing)**: enumerate EVERY SQL statement touching `cortex_sources`/`sys_favorites`/`fts_unified_search` across `hooks/{sma-session-start-preload,memory-consolidate-hook,design-cortex-reminder,auto-favorites-extract}.sh`, `rules/{output-persist,01-three-core-laws,no-tmp-artifacts}.md`, `CLAUDE.md`; derive the union column set per table; any underivable column → flagged in the schema file header and the plan-of-record, NOT guessed. Verification: doctor queries each table; a CI test executes each enumerated hook query against a freshly-initialized DB.
- `db-init.sh` applies `core/db/schema/*.sql` in order, idempotent (`IF NOT EXISTS`); destructive reset only behind `--reset-db` (reuse `deploy/init-database.sh` seed logic minus its CI-hanging y/N prompt).
- Portability: `hooks/lib/portable.sh` (`sed_i()`, `date_add()`, `solar_python()`); fix the ~6 BSD-sed/date hooks + email-to-calendar; replace hardcoded `/opt/homebrew/bin/python3.11` with `$SOLAR_PYTHON`/`env python3`. Rust components install only if cargo present. Downgrade `harness/installer/install.sh` hard-exits (bun/TVS) to component-conditional warnings.

**WS2 — Kernel generation & excision (M/L)**. Build `kernel/` fragments from current CLAUDE.md; excise/park the 7 external components' sections (xiaoai, gstack, GLM 全量模式, skill 分层检索, brain-router rosters, plan-act, solar-farm triggers); audit `rules/*.md` mentioning them (move into owning component payload or strip; checklist generated by WS7 forbidden-token grep). Trim agents: `agents/base/` (10–15 referenced by kernel/rules) ship with kernel; rest → `agents-extra`. **Rules install to `~/.claude/solar/rules/` (lazy, kernel-indexed) — NOT `~/.claude/rules/`** (native auto-load would force ~150KB into every session). Sentinel-block integration with user CLAUDE.md (backup first, replace-between-sentinels idempotent, uninstall removes).

**WS3 — Config templating (M)**. `render-template.sh` + `templates/config/*.template` + `templates/daemons/*.template`; `~/.solar/config.env` + `.env` generation. (Format/precedence in Target architecture.)

**WS4 — Installer core (L)**. Create `install.sh` + `lib/installer/*.sh` + `components.d/`. REUSE explicitly: `harness/installer/install.sh` (arg-parse loop, OS detect, apt/yum/brew dep matrix, non-destructive write_config/write_env, init_state_db heredoc, summary box) → `common/preflight`; `scripts/sync-harness-runtime.sh` → `copy-engine.sh` (its exclude list IS the never-clobber-runtime-state contract); root `install.sh` backup logic + 14-point check → per-component `component_verify()`; `harness/installer/doctor.sh` JSON schema reused wholesale. Hooks registration: per-component `hooks.json` holds settings.json entries; `settings-merge.sh` backs up, merges via python3 (never sed), Solar entries identified by `~/.claude/solar/hooks/` command prefix → idempotent add/remove; start with the ~15 kernel-critical hooks, rest ride with owning components; `--no-hooks` skips. MCP: `claude mcp add <name> --scope user -- <cmd>` only if `claude` CLI present, recorded in receipt, `claude mcp remove` on uninstall — never hand-edit `~/.mcp.json`.

**WS5 — Lifecycle commands (M)**. `bin/solar` dispatcher: `doctor | update | uninstall [--keep-data] | backup | restore | components list`; `bin/solar-daemon` (wraps `bun run core/daemon/server.ts`). `update` = pull/tarball per channel + re-run `install.sh --non-interactive --components <receipt>` (reuse `upgrade.sh` --dry-run + snapshot). `uninstall` = receipt-driven: stop/remove daemons (generalize `core/security/uninstall-security.sh` launchctl loop), remove receipt-listed files, strip all sentinel blocks, `--keep-data` preserves db/config.env/.env. `backup/restore` reuse `harness/installer/restore.sh`.

**WS6 — Daemons component (M)**. OFF by default. darwin: render plist → `~/Library/LaunchAgents` + launchctl; linux/WSL2-with-systemd: render unit → `~/.config/systemd/user` + `systemctl --user enable --now` + `loginctl enable-linger` note; no systemd → skip with reason. Wrap the 6 existing macOS component installers: launchd bits move behind this component; their DB tables move to `core/db/schema/` (WS1).

**WS7 — CI & gates (M)**. `.github/workflows/install-matrix.yml`: matrix {ubuntu-latest, macos-latest} × {minimal, full-non-rust}; each job in sandbox `HOME=$(mktemp -d)` (reuse `scripts/smoke-install.sh` technique): `./install.sh --yes --components ... --fake-keys --skip-llm-cli` → `bin/solar doctor --json` verdict==ok → **core-runtime gate: daemon boots + `dashboard:web` serves 200** → re-run for idempotency (receipt diff empty) → `bin/solar uninstall --yes` → residue assertion (HOME diff). macOS leg pinned to `/bin/bash` (3.2). Plus jobs: shellcheck over installer; PSScriptAnalyzer lint of `install.ps1` (GH Windows runners lack nested virt → no live WSL2 job; real hardware covered by manual checklist); privacy-gate (gitleaks with `harness/gitleaks.toml` + forbidden tokens: `/Users/lisihao`, `haogege1977`, LAN IPs, 7 excised component names); kernel-gen-check (min+max assemblies; forbidden tokens + unresolved `{{`); dry-run-check (zero writes); lychee docs link check. Cortex-schema test from WS1. Existing solar-ci.yml smoke suites must stay green after the purge (fix fixtures, not code).

**WS8 — Docs + Windows path (M)**.

- `install.ps1` (Windows entry, real automation not docs-only): detect WSL via `wsl.exe --status`; if absent → self-elevate, `wsl --install -d Ubuntu-24.04 --no-launch`, register RunOnce continuation, require the **single documented admin+reboot step**; if present → ensure distro exists, ensure systemd (`/etc/wsl.conf` `[boot] systemd=true` + `wsl --shutdown` if needed, required for daemons component), then run the Linux installer inside: `wsl -d Ubuntu-24.04 -- bash -lc 'curl -fsSL <get-solar.sh> | bash -s -- <ALL forwarded flags>'` — full `SOLAR_*`/flag passthrough so `--yes` CI installs work identically. Native (non-WSL) Windows runtime stays out of scope (re-architecture).
- Create root `INSTALL.md` (canonical; absorbs INSTALL-AGENT.md, SKILLS-INSTALL.md, DEPLOY.md, deploy/SETUP.md), `docs/COMPONENTS.md` (generated from manifests), `docs/UNINSTALL.md`, `docs/WINDOWS.md` (the one admin/reboot step, systemd note, capability table). Rewrite README quickstart; normalize ALL URLs to the real repo. `get-solar.sh` curl|bash bootstrap (clones channel tag, execs `install.sh "$@"`; functions-wrapped, main-at-end).

## Sequencing

| Phase | Content | Size | Exit criterion |
|---|---|---|---|
| **P0** | Baseline assertion (step 0) + schema-file list re-verification + **TVS rights request sent to upstream** + WS0 purge + WS1 repair | M | `bun install` succeeds on fresh clone; privacy grep clean on worktree; cortex column derivation complete or flagged |
| **P1 (alpha)** | WS4 skeleton + components kernel/core-runtime/harness/skills-md/codex-bridge + wizard-lite + `--yes` + receipt + db-init. Alpha ships current monolithic CLAUDE.md as SOLAR.md via sentinel import (safety contract first, content surgery in P2). TVS verdict lands → tvs-tui fate fixed | L | Stranger checklist passes on Ubuntu container + macOS: clone → install → Claude session loads kernel → daemon + web dashboard boot-gate green → uninstall residue-free |
| **P2** | WS2 kernel-gen + excision + agents trim; WS3 templating; hooks/MCP registration | L | kernel-gen-check green; zero forbidden tokens in installed tree |
| **P3** | WS5 lifecycle; WS6 daemons; remaining skill components + mempalace; `install.ps1` | M | doctor/update/uninstall round-trip green in CI; ps1 lint green |
| **P4 (beta→v1)** | WS7 full matrix + gates; WS8 docs; orphan-branch public release cut + GitHub Release with get-solar.sh | M | install-matrix green both OSes; manual fresh-VM checklist (macOS, Ubuntu, **Win11+auto-provisioned WSL2**) signed off |

## Verification

- Per-component `component_verify()` + `doctor --json` (file existence, `sqlite3 .tables`, bun smoke, venv import, **daemon boot + dashboard HTTP 200**).
- CI matrix as WS7 (install → doctor → dashboard gate → idempotent re-run → uninstall → residue diff; dry-run writes nothing; shellcheck + PSScriptAnalyzer; privacy/kernel/link gates; cortex hook-query test).
- Manual fresh-VM release checklist: macOS VM, Ubuntu 24.04 container, Win11 (run `install.ps1` end-to-end incl. the one reboot) — clone → interactive install (defaults) → `solar doctor` → open `claude`, confirm import approval prompt → trigger session-start hook → open web dashboard → `solar update` no-op → `solar uninstall` → `~/.claude/CLAUDE.md` byte-identical to pre-install backup; no `~/.solar`; `launchctl list` / `systemctl --user` clean.

## Risks & mitigations (top 8)

1. **Purge loses author data** → tag + archive branch pushed before any deletion; public release is orphan cut; private history survives on private remote.
2. **TVS unobtainable → TUI can't ship** → resolved design: dashboard requirement is met TVS-free (daemon + web dashboard in core-runtime, CI-gated); `tvs-tui` optional behind `SOLAR_TVS_ROOT`; rights request is a P0 action with P1 decision deadline; no redistribution without license.
3. **bash 3.2 (macOS default)** → 3.2-safe style for `lib/installer/`; CI macOS leg runs `/bin/bash install.sh`; shellcheck gate.
4. **settings.json merge corrupts user config** → timestamped backup; python3 JSON merge (never sed); Solar entries keyed by command-path prefix; `--no-hooks`; doctor validates JSON parses.
5. **CLAUDE.md clobbering** (category's worst failure) → sentinel-block-only writes, backup first, uninstall restores; import verified, inline fallback ready; `solar backup/restore`.
6. **Cortex schema wrong → hooks error at runtime** → columns derived from exhaustive statement enumeration (WS1), underivable columns flagged not guessed; `IF NOT EXISTS` lets a future canonical schema win; doctor queries each table; CI executes each hook query against fresh DB.
7. **Kernel excision breaks hidden dependents** → forbidden-token CI grep over assembled kernel + payload; component-gated intents.conf; alpha ships unmodified kernel so excision regressions isolate to the P2 diff.
8. **WSL2 auto-provision fragility** (elevation, reboot continuation, systemd variance) → single documented manual step (admin+reboot) with RunOnce continuation; `install.ps1` is a thin bootstrapper — all real logic stays in the battle-tested Linux path; PSScriptAnalyzer in CI + mandatory real-hardware item in release checklist; daemon component degrades with reason when systemd absent.

## Out of scope (explicit)

Rewriting `core/` TS or `harness/` Python internals · porting/open-sourcing the 7 external components (excised instead) · full English translation of rules/agents corpus (operative kernel directives get English rendering; persona flavor stays) · **native (non-WSL) Windows runtime** (re-architecture; auto-provisioned WSL2 is the Windows path) · prebuilt Rust binaries · npm wrapper · Claude Code plugin/marketplace packaging (phase 2 — `components.d/` maps 1:1 onto `.claude-plugin/` later) · `web/` dashboard productization.

## Key files (implementation anchors)

- `install.sh` — rewrite (thin entry); current copy logic decomposes into `components.d/`
- `install.ps1` — new Windows WSL2 bootstrapper
- `harness/installer/install.sh` + `doctor.sh` + `upgrade.sh` — pattern source to generalize
- `scripts/sync-harness-runtime.sh` — becomes `lib/installer/copy-engine.sh`
- `package.json` — remove `tvs` file-dep; `bin/` becomes real; prune TUI scripts pending TVS verdict
- `CLAUDE.md` — fragment into `kernel/`; root copy becomes contributor doc
- `core/dashboard/server.ts` — asset-path fix (demos html → core/dashboard/assets/); the shipped dashboard
- `hooks/intent-engine-hook.sh` — reads generated intents.conf
- `core/db/schema/` (new) ← 12 pinned schema files + derived 40-cortex.sql
- `scripts/smoke-install.sh`, `.github/workflows/solar-ci.yml` — extend; `.github/workflows/install-matrix.yml` (new)
