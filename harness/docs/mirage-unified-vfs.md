# Mirage Unified VFS

Sprint: sprint-20260508-mirage-unified-vfs  
Status: implemented

## Overview

Mirage provides a logical virtual filesystem over Solar's knowledge sources. It maps short paths like `/knowledge`, `/raw`, `/sprints`, `/solar`, `/cortex`, `/drive`, `/qmd`, `/projects` to their physical backing stores, enforcing read/write boundaries, secret redaction, and security policies — without requiring a kernel FUSE mount.

Solar agents use `solar-harness mirage exec -- 'find /knowledge -name "*.md"'` instead of hardcoding `~/Knowledge/...` paths.

## Installation

No extra dependencies beyond Python 3.9+ and PyYAML (already present):

```bash
# Verify
solar-harness mirage doctor
```

## Manifest: config/mirage.solar.yaml

```yaml
version: 1
workspace_id: solar-default
mounts:
  - path: /knowledge      # Obsidian vault (read-only)
  - path: /raw            # Staging area for new content (read-write)
  - path: /sprints        # Sprint artifacts (read-only)
  - path: /solar          # ~/.solar state (read-only, redacted)
  - path: /cortex         # Cortex knowledge base (read-only)
  - path: /projects       # Allowlisted project roots (empty by default)
  - path: /drive          # Google Drive (optional, read-only by default)
  - path: /qmd            # QMD/MinerU search (virtual, read-only)

policy:
  default_timeout_s: 30
  max_stdout_bytes: 1048576
  allowed_verbs: [ls, find, grep, cat, head, wc, jq, echo]
  redact_patterns:
    - "sk-[A-Za-z0-9]{20,}"
    - "Bearer [A-Za-z0-9._-]+"
    - "api_key=[^\\s\"']+"
```

## CLI Reference

### doctor

```bash
solar-harness mirage doctor [--json]
```

Probes: Mirage SDK (optional), all mounts, Google Drive credentials, QMD adapter, Solar DB.

Output fields: `enabled`, `config`, `sdk`, `drive`, `qmd`, `solar_db`, `mounts`, `workspace_id`.

Caches result to `state/mirage/last-probe.json` for the status-server.

### workspace

```bash
solar-harness mirage workspace create [--id ID] [--json]
solar-harness mirage workspace status [--id ID] [--json]
solar-harness mirage workspace destroy --id ID [--json]
```

Workspace state is persisted to `state/mirage/<id>.json`.  
`create` also ensures the `/raw` physical directory exists.

### mounts

```bash
solar-harness mirage mounts [--json]
```

Returns all configured mounts with `path`, `root`, `mode`, `source_type`, `ready`, `issues`.

### exec

```bash
solar-harness mirage exec [--json] [--allow-write-drive] [--allow-write-projects] -- 'COMMAND'
```

Executes shell command with:
- **Verb allowlist**: first token must be in `allowed_verbs` (ls, find, grep, cat, head, wc, jq, echo)
- **Path rewriting**: `/knowledge/...` → `~/Knowledge/...` (and all other mounts)
- **Write boundary**: redirects (>, >>, tee) to read-only mounts are blocked and logged
- **Secret redaction**: stdout is scanned for credential patterns before returning
- **Timeout**: default 30s; stdout truncated at 1MB

Example:
```bash
solar-harness mirage exec -- 'grep -R "embedding" /knowledge | head -20'
solar-harness mirage exec -- 'find /sprints -name "*.handoff.md" | head'
solar-harness mirage exec --json -- 'cat /solar/STATE.md'
```

### search

```bash
solar-harness mirage search "QUERY" [--json] [--max-hits N] [--max-chars N] \
  [--sources mirage_path,qmd,solar_db]
```

Unified search across three source adapters:
1. **mirage_path**: `rg --json` (fallback: grep) over all disk mounts
2. **qmd**: `solar-harness wiki qmd-search` virtual adapter
3. **solar_db**: `solar-knowledge-context.py --query --json` Cortex/Solar DB

Returns `{hits, degraded_sources, total_chars, truncated, query, elapsed_ms}`.

### provision

```bash
solar-harness mirage provision [--dry-run]
```

Shows the path-rewrite plan that would apply to a sample command. Useful for debugging manifest.

## Write Policy

| Mount | Mode | Write condition |
|-------|------|-----------------|
| /knowledge | ro | always denied |
| /raw | rw | always allowed |
| /sprints | ro | always denied |
| /solar | ro | always denied |
| /cortex | ro | always denied |
| /projects | ro | allowed with `--allow-write-projects` |
| /drive | ro | allowed with `--allow-write-drive` |
| /qmd | ro | always denied (virtual) |

Write denials emit `mirage_write_denied` events to both `state/mirage/events.jsonl` and `sprints/warn.events.jsonl`.

## Google Drive Credential Policy

Set `GOOGLE_APPLICATION_CREDENTIALS` to a service-account JSON path before running:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.solar/secrets/gcp-sa.json"
solar-harness mirage doctor
```

Missing credentials → drive status = `degraded` (not an error). All other mounts and commands continue to work.

Read operations on `/drive` require the Mirage SDK (`pip install mirage-sdk`).  
Write operations require both credentials and `--allow-write-drive` flag.

## Event Log

All mirage events are appended to `state/mirage/events.jsonl`.  
Warn-level events (`mirage_write_denied`, `mirage_mount_degraded`, `mirage_secret_redacted`) are also appended to `sprints/warn.events.jsonl`, which the status-server reads.

Event types and their fields:

| Event | Severity | Key fields |
|-------|----------|------------|
| `mirage_installed` | info | sdk_kind, version |
| `mirage_workspace_created` | info | workspace_id, mounts_count |
| `mirage_command_executed` | info | verb, logical_path, exit_code, elapsed_ms |
| `mirage_mount_degraded` | warn | mount_path, reason |
| `mirage_secret_redacted` | warn | mount_path, pattern_count |
| `mirage_write_denied` | warn | logical_path, reason |

## Status Server

When `solar-harness status-server` is running, `/status` includes a `mirage` section:

```json
{
  "mirage": {
    "enabled": true,
    "workspace_id": "solar-default",
    "mounts": [...],
    "drive": {"status": "degraded"},
    "qmd": {"status": "ok"},
    "last_probe_at": "2026-05-08T14:30:00Z",
    "stale": false
  }
}
```

The `mirage` section reads from `state/mirage/last-probe.json` (written by `doctor`). It is fast, fail-open, and requires no SDK import or network calls.

## Rollback

```bash
# Remove config
rm ~/.solar/harness/config/mirage.solar.yaml

# Remove state
rm -rf ~/.solar/harness/state/mirage/

# Remove lib files
rm ~/.solar/harness/lib/solar_mirage.py
rm ~/.solar/harness/lib/mirage_search.py
rm ~/.solar/harness/lib/mirage_events.py

# Revert solar-harness.sh: remove the mirage) case block
```

The `solar-harness mirage` subcommand will then return a "not found" error.

## Security Notes

- Path traversal and symlink escapes are blocked via `realpath()` comparison against mount root
- All secret patterns (API keys, Bearer tokens) are redacted from stdout before returning
- `/solar` has `redact_on_read: true` and `deny_subpaths` for `secrets/`, `.env`, `.token`
- The status-server binds to `127.0.0.1` only and includes no auth — internal use only
- Drive credentials are never logged or printed in JSON output
