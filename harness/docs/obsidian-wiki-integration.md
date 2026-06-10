# Obsidian Wiki Integration — Operator Guide

Sprint: sprint-20260507-obsidian-wiki  
Source: https://github.com/Ar9av/obsidian-wiki  
Maintained by: Solar Harness

---

## Overview

The `solar-harness wiki` subcommands give Solar a durable, Obsidian-native knowledge vault. Sprint artifacts, decisions, and handoffs are automatically exported to a structured vault directory (`_raw/solar-harness/`), where the upstream `obsidian-wiki` skill chain (wiki-update, wiki-ingest, wiki-query) can ingest and index them.

**Why**: Solar currently relies on ephemeral conversation context and SQLite Cortex. The wiki layer adds a human-readable, agent-accessible secondary store that survives session restarts and context compression.

**Design constraints**:
- Non-interactive installation (upstream `setup.sh` is interactive; we bypass it)
- Safe symlinks only — never overwrite real directories
- Default export mode redacts credentials and truncates raw transcript dumps
- Status-server integration degrades gracefully (warn, not fatal) when wiki is absent

---

## Prerequisites

- `git` in `PATH`
- Python 3.10+ (stdlib only; no pip install needed)
- Obsidian desktop app (optional — vault works without it for CLI use)

---

## Quick Start

```bash
# 1. Install integration (first-time setup)
solar-harness wiki install --vault "$HOME/Documents/Solar Wiki"

# 2. Verify status
solar-harness wiki status

# 3. Export a sprint artifact
solar-harness wiki export-sprint sprint-20260507-symphony3
```

---

### Example 1: First-time install to default repo path

```bash
solar-harness wiki install --vault "$HOME/Documents/Solar Wiki"
```

What happens:
- Clones `Ar9av/obsidian-wiki` to `~/.solar/harness/vendor/obsidian-wiki` (unless `--repo` given)
- Writes `~/.obsidian-wiki/config` with `OBSIDIAN_VAULT_PATH` and `OBSIDIAN_WIKI_REPO`
- Creates vault skeleton: `index.md`, `log.md`, `hot.md`, `.manifest.json`, `_raw/`, `projects/`, `concepts/`, `entities/`, `skills/`, `references/`, `synthesis/`, `journal/`
- Installs safe skill symlinks for `~/.codex/skills`, `~/.claude/skills`, `~/.agents/skills`

Expected output:
```
[wiki] config written: ~/.obsidian-wiki/config
[wiki] vault skeleton ready: ~/Documents/Solar Wiki
[wiki] skill symlinks installed (codex: OK, claude: OK, agents: OK)
[wiki] install complete
```

---

### Example 2: Custom vault path and custom upstream repo

```bash
solar-harness wiki install \
  --vault "/Volumes/Backup/KnowledgeVault" \
  --repo  "$HOME/dev/obsidian-wiki" \
  --refresh
```

- `--vault`: Any writable path; created if absent.
- `--repo`: Use a local clone instead of auto-downloading.
- `--refresh`: Runs `git pull --ff-only` on the repo before install.

Install is idempotent: re-running does not re-clone or break an existing vault.

---

### Example 3: Export current sprint to wiki (redacted)

```bash
solar-harness wiki export-sprint sprint-20260507-symphony3 --redact
```

Output file: `$OBSIDIAN_VAULT_PATH/_raw/solar-harness/sprint-20260507-symphony3.md`

File structure:
```markdown
---
source: solar-harness
sprint_id: sprint-20260507-symphony3
exported_at: 2026-05-07T21:00:00Z
redacted: true
visibility: internal
---

## Contract Summary
...

## Plan Summary
...

## Handoff Summary
...

## Eval Verdict
PASS

## Events (42 total)
| type | count |
|------|-------|
| task_completed | 10 |
| lint_pass | 4 |
...
```

Redaction rules applied automatically:
- `token=<REDACTED>`, `api_key=<REDACTED>`, `password=<REDACTED>`
- Bearer/Basic auth headers → `<REDACTED>`
- Strings ≥ 32 hex/base64 chars → `<REDACTED>`
- stdout/stderr blobs truncated to first 200 chars + `[...truncated]`

Use `--full` to skip redaction (still truncates binary blobs > 10 KB).

---

### Example 4: Trigger wiki update for Codex to process

```bash
solar-harness wiki update --project "$HOME/Solar" --mode append
```

This writes an agent-readable instruction file:
```
$OBSIDIAN_VAULT_PATH/_raw/solar-harness/.dispatch/wiki-update-20260507T210000.md
```

The dispatch file instructs Claude or Codex to run the `wiki-update` skill.
To execute it:
```bash
claude --skill wiki-update < "$OBSIDIAN_VAULT_PATH/_raw/solar-harness/.dispatch/wiki-update-<ts>.md"
```

Solar does not directly invoke the skill — it delegates via dispatch file to avoid interfering with active builder panes.

---

### Example 5: Query the wiki (quick mode)

```bash
solar-harness wiki query "What decisions were made in symphony3?" --quick
```

Prints a synchronous local search result immediately. Without `--quick`, Solar
creates a deep-query dispatch file for an agent to process:

```bash
solar-harness wiki query "What decisions were made in symphony3?"
```

Flags:
- `--quick`: Runs local grep-style retrieval and prints evidence immediately
- Empty query string is rejected immediately (exit code 2)

```bash
# This will fail with exit 2:
solar-harness wiki query ""
```

---

### Example 6: Dispatch upstream obsidian-wiki maintenance skills

Solar installs the upstream skills and exposes thin wrappers that write
agent-readable dispatch files:

```bash
solar-harness wiki ingest --source "$HOME/Downloads/paper.pdf" --mode append
solar-harness wiki ingest --mode raw
solar-harness wiki vault-status --insights
solar-harness wiki lint --fix
solar-harness wiki rebuild --mode archive-only
solar-harness wiki export-graph --public
solar-harness wiki colorize --mode by-category
solar-harness wiki history --target codex --query "rust ownership"
```

These wrappers do not directly run agents. They write files under:

```
$OBSIDIAN_VAULT_PATH/_raw/solar-harness/.dispatch/
```

An agent then processes the file with the corresponding skill (`wiki-ingest`,
`wiki-status`, `wiki-lint`, `wiki-rebuild`, `wiki-export`, `graph-colorize`, or
`wiki-history-ingest`).

---

### Example 7: Send a dispatch to a builder pane

```bash
dispatch_file=$(solar-harness wiki vault-status --insights | tail -1)
solar-harness wiki run-dispatch "$dispatch_file" --lab-builder 1
```

Target options:
- `--lab-builder 1|2|3|4`: send to a Parallel Builder Lab pane
- `--main-builder`: send to the main Product Delivery builder pane
- `--pane <target>`: send to an explicit tmux target such as `solar-harness-lab:0.2`
- `--dry-run`: parse and select the target without sending keys

`run-dispatch` marks the dispatch frontmatter as `status: dispatched` and records
`target_pane`. The agent is responsible for changing it to `completed` after it
finishes and writes a result file.

---

### Example 8: Auto-dispatch pending wiki work

```bash
solar-harness wiki dispatch-watch --once --limit 4
```

This scans:

```
$OBSIDIAN_VAULT_PATH/_raw/solar-harness/.dispatch/
```

and sends `status: pending` wiki dispatch files to Parallel Builder Lab panes in
round-robin order. Use `--dry-run` to preview without sending:

```bash
solar-harness wiki dispatch-watch --dry-run --limit 10
```

For a lightweight loop:

```bash
solar-harness wiki dispatch-watch --loop --interval 30 --limit 4
```

---

## Web Capture Page

Start a local paste page:

```bash
solar-harness wiki capture-server start --open
```

Default URL:

```text
http://127.0.0.1:8788
```

What it does:

1. You paste copied web content into the page.
2. The server writes a Markdown file under:

```text
~/Knowledge/_raw/web-captures/
```

3. Or you select multiple files with the file picker. Uploaded PDFs, Markdown,
   JSONL, logs, text files, and images are copied under:

```text
~/Knowledge/_raw/file-uploads/
```

4. A background scheduler scans every 60 seconds.
5. New or changed captures/uploads are converted into `wiki-ingest` dispatch files.
6. Dispatches are sent round-robin to `solar-harness-lab` builder panes 1-4.

Useful commands:

```bash
solar-harness wiki capture-server status
solar-harness wiki capture-server restart --port 8788 --open
solar-harness wiki capture-server stop
```

Manual trigger from the page:

```text
Run ingest now
```

The server is local-only (`127.0.0.1`) and uses Python stdlib only.

---

## Import Solar SQLite Knowledge

Solar's older knowledge graph lives mainly in `~/.solar/solar.db`. Export it to
the Obsidian raw staging area and immediately trigger `wiki-ingest`:

```bash
solar-harness wiki import-solar-db --scope solar --per-table-limit 25
```

Default export directory:

```text
~/Knowledge/_raw/solar-db-export/
```

Tables exported by default:

```text
solar_kb_entries
knowledge_entities
knowledge_claims
cortex_sources
evo_memory_semantic
```

Modes:

```bash
# Preview only; writes nothing and dispatches nothing.
solar-harness wiki import-solar-db --scope solar --per-table-limit 5 --dry-run

# Export all rows from the selected tables. Use carefully.
solar-harness wiki import-solar-db --scope all --per-table-limit 100

# Export only; do not trigger the capture server's run-now endpoint.
solar-harness wiki import-solar-db --scope solar --per-table-limit 25 --no-dispatch
```

The capture server also scans `_raw/solar-db-export/**/*.md` every 60 seconds, so
exported DB knowledge is ingested automatically while the server is running.

---

## Status Check

```bash
# Human-readable
solar-harness wiki status

# JSON output (for scripting)
solar-harness wiki status --json
```

JSON fields:
| Field | Type | Meaning |
|-------|------|---------|
| `configured` | bool | Config file exists and vault is set |
| `repo_path` | string | Upstream repo clone location |
| `vault_path` | string | Obsidian vault directory |
| `config_path` | string | Active config file path |
| `skills_installed.codex` | bool | `~/.codex/skills` wiki symlink present |
| `skills_installed.claude` | bool | `~/.claude/skills` wiki symlink present |
| `skills_installed.agents` | bool | `~/.agents/skills` wiki symlink present |
| `last_exported_sprint` | string\|null | Last exported sprint ID |
| `last_checked_at` | string | ISO-8601 check timestamp |

Schema: `~/.solar/harness/schemas/obsidian-wiki-status.schema.json`

---

## HTTP Status Server Integration

When `solar-harness status-server` is running (port 8765), the `/status` endpoint includes:

```json
{
  "obsidian_wiki": {
    "ready": true,
    "configured": true,
    "vault_path": "~/Documents/Solar Wiki",
    "issues": []
  }
}
```

If wiki is not installed, the server responds with `ready: false` and `issues` list — it does not fail or return HTTP 500. This ensures the status dashboard always loads.

---

## Troubleshooting

### Symlink refused: "REFUSE: <path> exists as real dir/file"

Your target skill directory already exists as a real directory, not a symlink. The installer will not overwrite it.

**Fix**: Rename or move the existing directory:
```bash
mv ~/.claude/skills ~/.claude/skills.bak
solar-harness wiki install --vault "$HOME/Documents/Solar Wiki"
```

### Repo clone failed

```
[wiki] WARN: git clone failed (continuing without upstream skills)
```

The upstream `Ar9av/obsidian-wiki` repo could not be cloned (offline, rate-limit, or URL change). Vault skeleton is still created; skill symlinks are skipped.

**Fix**: Manually clone and pass `--repo`:
```bash
git clone https://github.com/Ar9av/obsidian-wiki ~/dev/obsidian-wiki
solar-harness wiki install --vault "$HOME/Documents/Solar Wiki" --repo ~/dev/obsidian-wiki
```

### Vault skeleton incomplete

```bash
solar-harness wiki install --vault "$HOME/Documents/Solar Wiki"
```

Re-running install is idempotent and will create any missing vault directories/files without disturbing existing content.

### Config not found after install

If `solar-harness wiki status` reports unconfigured, check:
```bash
cat ~/.obsidian-wiki/config
```

If missing, re-run install. If the file is at a custom path, set:
```bash
export OBSIDIAN_WIKI_CONFIG=~/.obsidian-wiki/config
solar-harness wiki status
```

---

## Security Model

- **No real directory overwrite**: `safe_symlink` checks with `-e` and `-L` before linking; refuses if target is a real file or directory.
- **Redaction**: Default export strips credentials matching common patterns; use `--full` only for internal-only vaults.
- **Test isolation**: All tests (`HARNESS_TEST=1`) use temp vaults and temp skill directories. Real `~/.obsidian-wiki/config` is never touched by tests (uses `.test` suffix).
- **Vault write scope**: Solar commands only write under `_raw/solar-harness/`. Vault page ingestion is the wiki skill's responsibility.

---

## Integration with Symphony Status Server

See `~/.solar/harness/lib/symphony/status-server.py` — `_obsidian_wiki_readiness()` function.

The wiki readiness check runs as a subprocess (`solar-harness wiki status --json`) with a 2-second timeout. Any failure (timeout, missing file, parse error) returns `ready: false` with an `issues` list — the main `/status` endpoint always responds HTTP 200.
