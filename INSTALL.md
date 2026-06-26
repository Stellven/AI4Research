# Installing Solar

This is the canonical install guide for Solar. It covers interactive and
unattended installs, component selection, the installed layout, Windows
(WSL2), agent-driven installs, verification, and the lifecycle commands.

- **Components reference:** [`docs/COMPONENTS.md`](docs/COMPONENTS.md)
- **Uninstalling:** [`docs/UNINSTALL.md`](docs/UNINSTALL.md)
- **Windows / WSL2:** [`docs/WINDOWS.md`](docs/WINDOWS.md)

---

## Requirements

| Platform | Status |
|---|---|
| macOS (Apple Silicon or Intel) | first-class |
| Linux (x86_64 / arm64) | first-class |
| Windows 11 | via installer-provisioned **WSL2** — see [`docs/WINDOWS.md`](docs/WINDOWS.md) |

Base tools (the `kernel` + `harness` default install):

- `bash` (the macOS system `/bin/bash` 3.2 is supported)
- `git`
- `python3` — used for DB init, JSON merges, and templating (the `sqlite3`
  CLI is **not** required; the installer uses Python's bundled SQLite)

Optional, per component (the installer detects these and only enables a
component when its requirements are met, or tells you what is missing):

- `bun` — for the `core-runtime` component (TypeScript core, daemon, web dashboard)
- `cargo` — for the `skills-browser` component

Runtime launch tools for `solar-harness start <workdir>`:

- Bash 4 or newer — on macOS, install Homebrew Bash if `/bin/bash` is 3.2
- `python3`
- `tmux`
- `jq`
- Claude Code CLI (`claude`) on `PATH`

Run `~/.solar/bin/solar-harness preflight` to check these before opening tmux
panes. Preflight is deterministic: it proves launch dependencies and filesystem
plumbing, not live Claude behavior. After `solar-harness start`, live Claude
pane behavior and real delegation are owner-manual until Claude starts,
responds, and any trust/auth/quota prompts are resolved.

No root/`sudo` is needed. Nothing is written outside your home directory.

---

## Quick install

Clone and run the installer:

```bash
git clone --branch v1.0.0-rc.6 https://github.com/suraj-subrahmanyan/OpenSolar.git
cd OpenSolar
./install.sh
```

On a terminal (TTY) this runs interactively: it shows a banner, OS/tool
summary, default components, and a numbered choice to proceed, customize, or
cancel. After any required component config prompts, it prints a final summary
and asks for confirmation. Cancelling exits cleanly with code `130` and writes
nothing.

### Unattended / CI install

```bash
./install.sh --yes --components kernel,harness
```

`--yes` (alias `--non-interactive`) accepts the resolved defaults with no
prompts. The installer auto-detects non-interactive contexts (`$CI`, no TTY)
and prints the reason.

---

## Components

The default selection is `kernel` + `harness`, plus `core-runtime` when `bun`
is available. Everything else is off by default and opt-in.

| Component | Default | Summary |
|---|---|---|
| `kernel` | on | Claude Code kernel overlay: namespaced rules, hooks, agents |
| `core-runtime` | auto (needs `bun`) | TypeScript core runtime, daemon, web dashboard |
| `harness` | on | Python harness runtime payload |
| `skills-md` | off | Generic markdown skills for Claude Code discovery |
| `skills-office` | off | Office productivity skills (email, notes, tasks) |
| `skills-obsidian` | off | Obsidian vault skills |
| `skills-calendar` | off | macOS Calendar skills (darwin only) |
| `skills-browser` | off | Browser automation skills (needs `cargo`) |
| `codex-bridge` | off | File-based handoff bridge for external coding agents |
| `mempalace` | off | Semantic memory MCP server (needs a vault path) |
| `daemons` | off | User-level background daemon for the runtime |

See [`docs/COMPONENTS.md`](docs/COMPONENTS.md) for the full per-component
detail (platforms, required binaries, config vars), generated from the
component manifests.

### Selecting components

```bash
./install.sh --list-components                      # show all components
./install.sh --yes --components kernel,harness,core-runtime
```

Some components require a config value. Provide it with `--set` (or the
matching `SOLAR_<KEY>` environment variable). For example, `mempalace`
requires a vault path:

```bash
./install.sh --yes --components kernel,mempalace --set VAULT_PATH=/path/to/vault
```

In non-interactive mode a missing required value fails loudly with the exact
`--set` remedy.

---

## Flags

```text
--yes, --non-interactive    Accept resolved defaults (no prompts)
--components LIST            Comma-separated component list
--set KEY=VALUE             Set a config var (repeatable; highest precedence)
--no-hooks                  Skip settings.json hook registration
--no-mcp                    Skip MCP server registration
--list-components           Show component manifests
--solar-home PATH           Runtime root (default: ~/.solar)
--claude-dir PATH           Claude user dir (default: ~/.claude)
--dry-run                   Print actions without writing any files
--fake-keys                 Write test-only placeholder env files
--skip-llm-cli              Skip LLM CLI checks (for CI)
--skip-py-deps              Validate Python requirements only (deps-light CI)
--help                      Show help
```

Every flag has a `SOLAR_*` environment-variable twin. `--dry-run` is fully
side-effect-free: it may run the TTY wizard so choices shape the plan, but it
writes nothing.

---

## What gets installed (layout)

```text
~/.claude/CLAUDE.md            # your own file; gets ONE sentinel-marked block:
                               #   <!-- BEGIN OPENSOLAR --> @~/.claude/solar/SOLAR.md ...
~/.claude/solar/               # all Solar kernel assets, namespaced + uninstall-safe
  SOLAR.md                     # generated kernel (per selected components)
  rules/  hooks/  agents/      # installed under solar/, NOT ~/.claude/rules (no auto-load)
  intents.conf
~/.claude/settings.json        # Solar hook entries merged in (keyed by the solar/hooks/ path)
~/.claude/skills/<name>/       # selected skill components

~/.solar/                      # runtime root (override with --solar-home / $SOLAR_HOME)
  install-receipt.json         # what was installed — powers doctor/update/uninstall
  config.env  .env (0600)      # machine config + secrets (created once, never clobbered)
  db/solar.db                  # runtime database
  bin/{solar,solar-daemon,solar-harness}
  harness/  venv/  mempalace/  # per selected components
```

The installer never overwrites your `~/.claude/CLAUDE.md` wholesale — it backs
it up and edits only the sentinel-marked block, which the uninstaller removes
cleanly.

---

## Windows (WSL2)

Native (non-WSL) Windows is out of scope; WSL2 is the Windows runtime path.
Run the bootstrapper from PowerShell:

```powershell
.\install.ps1 -- --yes --components kernel,harness
```

It provisions WSL2 if needed (one admin approval + one reboot), then runs the
Linux installer inside WSL with your flags forwarded verbatim. Full details,
the single manual step, and the systemd note are in
[`docs/WINDOWS.md`](docs/WINDOWS.md).

---

## Installing via an AI coding agent

If you ask Claude, Codex, Cursor, Copilot, or another code agent to install
Solar for you, hold it to this protocol:

1. Before each command, report **purpose + command + expected output**.
2. Never use `sudo`/root; keep everything under `~/.claude` and `~/.solar`.
3. Stop on the first failure and show the exact output — never claim success
   without running the verification below.
4. Do not invent paths or commands; do not write real API keys.
5. Do not install optional third-party skills without asking first (see
   *Optional third-party skills* below).

A minimal agent install + self-check:

```bash
git clone --branch v1.0.0-rc.6 https://github.com/suraj-subrahmanyan/OpenSolar.git && cd OpenSolar
./install.sh --yes --components kernel,harness
~/.solar/bin/solar doctor --json   # expect "verdict": "ok"
```

---

## Optional third-party skills

The base install is intentionally conservative. Skills bundled in the
`skills-*` components install under `~/.claude/skills/`. Third-party skill
packs are optional enhancements, installed separately under `~/.claude/skills/`
and only after you approve them. Never overwrite a user's existing skills.

---

## Verify the install

```bash
~/.solar/bin/solar doctor --json
```

Expect `"verdict": "ok"` and the installed components listed. Then start
Claude Code and confirm the kernel loads:

```bash
claude
# On first run, approve the one-time @~/.claude/solar/SOLAR.md import prompt.
```

For Product Delivery harness runtime readiness:

```bash
~/.solar/bin/solar-harness preflight
~/.solar/bin/solar-harness start "$(pwd)"
~/.solar/bin/solar-harness status
```

`status` reports required failures, manual-pending/auth-quota blocked Claude
panes, and optional warnings separately. It should say "ready for manual Claude
start" only when launch plumbing is ready; it must not claim live Claude is
verified unless Claude actually launched and responded.

---

## Lifecycle

All lifecycle operations go through `~/.solar/bin/solar`:

```bash
solar doctor [--json]              # health + drift check
solar update [extra install flags] # re-run the installer for the recorded components
solar ui [--once] [--watch N] [--no-color] # read-only terminal dashboard
solar backup [--out FILE]          # archive config + secrets + receipt + db
solar restore <archive>            # restore from a backup archive
solar components list              # list installed components
solar uninstall [--yes] [--keep-data] [--dry-run]
```

`solar ui` is TVS-free and read-only. It shows install health, harness
preflight/readiness, tmux/coordinator/runtime artifacts when present, and the
manual boundary for live Claude panes and real delegation.

`solar update` re-runs the installer from the source directory recorded in the
receipt, for exactly the components you installed. Uninstalling is documented
in [`docs/UNINSTALL.md`](docs/UNINSTALL.md); it is receipt-driven and
residue-free (with `--keep-data` to preserve your database, config, and
secrets).

---

## Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| `./install.sh: Permission denied` | `ls -l install.sh` | `chmod +x install.sh` |
| `core-runtime` skipped | `command -v bun` | install `bun`, re-run with `--components ...,core-runtime` |
| `skills-browser` skipped | `command -v cargo` | install Rust/`cargo`, then re-select the component |
| component "requires VAULT_PATH" | — | pass `--set VAULT_PATH=/path` (see the component's required vars) |
| kernel not loading in Claude | open `claude` | approve the one-time `@~/.claude/solar/SOLAR.md` import prompt |
| want to see actions first | — | `./install.sh --dry-run --components ...` (writes nothing) |

For a full health report, run `~/.solar/bin/solar doctor --json`.
