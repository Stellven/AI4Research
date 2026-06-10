# Solar Agent Install / Deploy / Self-Check Protocol

> For Claude, Codex, Cursor, Copilot, or any code agent installing Solar on behalf of a user.

This document is the authoritative agent-facing install protocol. The agent must not improvise commands, silently skip failures, or claim success without running the checks below.

---

## Scope

Solar installs in layers:

| Layer | Installed by `./install.sh` | Runtime location | Notes |
|---|---:|---|---|
| **L1 Solar Core** | yes | `~/.claude/` and `~/.solar/` | `CLAUDE.md`, rules, skills, agents, hooks, core files. |
| **L2 Solar Harness** | yes, when `harness/` exists | `~/.solar/harness` and `~/.solar/bin/solar-harness` | Requirement compiler, sprint control plane, DAG runtime, queue/lease/dispatch/eval. |
| **L2 optional packaged components** | yes, when present | `~/.solar/mempalace`, `~/.solar/codex-bridge` | Copied only if the repository contains those directories. |
| **Third-party skills** | no | `~/.claude/skills/` | Optional. Use `SKILLS-INSTALL.md` and ask before installing optional repositories. |
| **API keys** | no | local `.env` only | Optional. Copy `.env.template` to `.env`; never commit `.env`. |

---

## Non-negotiable rules for the installing agent

1. Before each command, report **purpose + command + expected output**.
2. Do not use `sudo` or root.
3. Stop on the first failure and show the exact output.
4. Do not invent missing paths or commands.
5. Do not write API keys; the user edits `.env` locally if needed.
6. Do not install optional third-party skills without asking the user first.
7. Completion requires L1 + L2 checks, not just clone success.

---

## Step 1 — System check

Purpose: confirm a supported OS and basic shell environment.

```bash
uname -sm
```

Expected examples:

```text
Darwin arm64
Darwin x86_64
Linux x86_64
Linux aarch64
```

Unsupported: native Windows. Use WSL2.

---

## Step 2 — Required dependencies

Purpose: confirm the minimum tools needed by the installer.

```bash
which git && git --version
which bash && bash --version | head -1
which sqlite3 && sqlite3 --version

# Optional but useful for L2 Harness work
which python3 jq tmux 2>/dev/null || true
```

Required to proceed: `git`, `bash`, and `sqlite3` must exist.

---

## Step 3 — Clone or update Solar

Purpose: get the public Solar repository.

```bash
if [ -d ~/Solar/.git ]; then
  cd ~/Solar && git pull --ff-only
else
  git clone https://github.com/suraj-subrahmanyan/opensolar.git ~/Solar
fi
```

Check:

```bash
test -f ~/Solar/install.sh && test -f ~/Solar/CLAUDE.md && echo OK
```

Expected: `OK`.

---

## Step 4 — Optional local env template

Purpose: create an optional local `.env` for API-backed features. Installation does not require keys.

```bash
cd ~/Solar
if [ -f .env.template ] && [ ! -f .env ]; then
  cp .env.template .env
  echo "Created .env from template. User may edit it later."
else
  echo "No env action needed."
fi
```

Do not fill in values yourself unless the user explicitly provides them in the local machine context.

---

## Step 5 — Run installer

Purpose: install L1 Solar Core and sync L2 Solar Harness runtime.

```bash
cd ~/Solar
./install.sh
```

Expected high-level output:

```text
🚀 Solar 一键部署 (L1 + L2 全栈)
...
🔍 安装自检
  ✅ [L1] ...
  ✅ [L2] ...
✅ Solar L1 + L2 安装完成 (14/14 通过)
```

If any check fails, stop and report the failing line.

---

## Step 6 — Independent L1/L2 self-check

Purpose: verify install artifacts without trusting installer logs only.

```bash
test -f ~/.claude/CLAUDE.md && \
test -d ~/.claude/rules && \
test -d ~/.claude/skills && \
test -d ~/.claude/agents && \
test -d ~/.solar && \
test -f ~/.solar/harness/coordinator.sh && \
test -x ~/.solar/harness/solar-harness.sh && \
test -L ~/.solar/bin/solar-harness && \
echo "Solar L1+L2 filesystem check PASS"
```

Expected:

```text
Solar L1+L2 filesystem check PASS
```

---

## Step 7 — Harness command self-check

Purpose: confirm the Harness CLI is usable.

```bash
~/.solar/bin/solar-harness help >/tmp/solar-harness-help.txt
cat /tmp/solar-harness-help.txt | head -40
```

Expected: help text that includes Harness commands. If this fails, inspect:

```bash
ls -la ~/.solar/bin/solar-harness ~/.solar/harness/solar-harness.sh
bash -n ~/.solar/harness/solar-harness.sh
```

---

## Step 8 — Runtime re-sync check

Purpose: confirm the repo-published Harness can be synced into the runtime directory.

```bash
cd ~/Solar
./scripts/sync-harness-runtime.sh
~/.solar/bin/solar-harness help >/tmp/solar-harness-help-after-sync.txt
grep -E "graph|context|help|start" /tmp/solar-harness-help-after-sync.txt | head -20 || true
```

Expected: sync completes and `solar-harness help` still works.

---

## Step 9 — Optional skill expansion

Purpose: install third-party skills only if the user asks.

Default behavior: do not install third-party skill packs.

If the user asks for skill expansion, follow:

```text
SKILLS-INSTALL.md
```

Important: Solar's base install already copies repository-bundled skills from `skills/` into `~/.claude/skills/`. Third-party skills are enhancements, not required for the base system.

---

## Step 10 — Final report to the user

Report in this format:

```text
Solar install report
- Repo: ~/Solar
- L1 Core: PASS/FAIL
- L2 Harness: PASS/FAIL
- Harness CLI: PASS/FAIL
- Runtime sync: PASS/FAIL
- Optional .env: created/skipped
- Optional third-party skills: installed/skipped
- Failures: none / exact failing command + output
- Next command for user: start Claude Code and type `solar`, or run `~/.solar/bin/solar-harness start`
```

---

## Troubleshooting quick table

| Symptom | Check | Likely fix |
|---|---|---|
| `./install.sh: Permission denied` | `ls -l ~/Solar/install.sh` | `chmod +x ~/Solar/install.sh` |
| `sqlite3` missing | `which sqlite3` | Install sqlite3 through system package manager. |
| Harness symlink missing | `ls -la ~/.solar/bin/solar-harness` | Re-run `cd ~/Solar && ./scripts/sync-harness-runtime.sh`. |
| `solar-harness help` fails | `bash -n ~/.solar/harness/solar-harness.sh` | Report syntax/output; do not guess. |
| Optional skills missing | `ls ~/.claude/skills` | Use `SKILLS-INSTALL.md` only after user approval. |

---

## Completion criteria

Installation is complete only when these are true:

```bash
test -f ~/.claude/CLAUDE.md
test -d ~/.claude/skills
test -d ~/.solar/harness
test -x ~/.solar/harness/solar-harness.sh
test -L ~/.solar/bin/solar-harness
~/.solar/bin/solar-harness help >/dev/null
```
