# Mirage As Unified Data Substrate For Codex And Solar Harness

## Goal

Make `solar-harness mirage` the canonical read/search surface for Codex, Solar Harness panes, and future tools. Solar keeps ownership of execution, wiki ingest, provenance, and status; Mirage provides the cross-source file/search abstraction.

## Target Architecture

```text
Codex / Claude / Solar panes
  │
  ├─ read/search → solar-harness mirage search|exec
  │                 ├─ /knowledge → ~/Knowledge
  │                 ├─ /raw       → ~/Knowledge/_raw
  │                 ├─ /sprints   → Solar sprint artifacts
  │                 ├─ /cortex    → Cortex store/code
  │                 ├─ /qmd       → qmd/mineru semantic search
  │                 └─ /drive     → optional Google Drive, read-only
  │
  └─ write knowledge → solar-harness wiki ingest/export/capture
                       not direct final-page writes
```

## Canonical Entry Point

> **Any cross-source read or search starts with `solar-harness mirage search`.**

```bash
# Canonical entry: search across Knowledge, QMD, Cortex, sprints
solar-harness mirage search "<query>" --json

# Canonical entry: read a file via logical mount
solar-harness mirage exec -- 'cat /knowledge/path.md'
solar-harness mirage exec -- 'cat /sprints/sprint-YYYYMMDD-xyz.contract.md'
```

This is the single entry point for all cross-source lookups. Do not bypass it.

## Anti-Patterns (Do Not Use)

| Anti-Pattern | Why Wrong | Use Instead |
|-------------|-----------|-------------|
| `rg ~/Knowledge "query"` | Bypasses provenance + mount boundaries | `solar-harness mirage search "query" --json` |
| `sqlite3 ~/.solar/solar.db "SELECT ..."` | Bypasses access controls, no source tagging | `solar-harness mirage search` or domain command |
| `ls ~/.solar/harness/sprints/` | Direct host traversal, no boundary | `solar-harness mirage exec -- 'ls /sprints/'` |
| `cat ~/Knowledge/wiki/page.md` | Host absolute path, no audit trail | `solar-harness mirage exec -- 'cat /knowledge/wiki/page.md'` |
| Full home mount in Codex workspace | Exposes credentials and secrets | Use logical mounts only |
| Direct write to `/knowledge` or `/sprints` | These mounts are read-only | Write via `solar-harness wiki ingest` or coordinator |

## Examples

```bash
# Search
solar-harness mirage search "Solar Harness dispatch flow" --json

# Read a sprint contract
solar-harness mirage exec -- 'cat /sprints/sprint-20260508-data-plane-closeout.contract.md'

# Read Knowledge doc
solar-harness mirage exec -- 'cat /knowledge/references/some-paper.md'

# Read Cortex entry
solar-harness mirage exec -- 'cat /cortex/sources.db'  # if cortex mount enabled

# Write a draft to /raw (only writable mount)
solar-harness mirage exec -- "echo 'draft' > /raw/$(date +%Y-%m-%d)/draft.md"
```

## What Goes Through Mirage vs Dedicated APIs

| Operation | Use |
|-----------|-----|
| Cross-source read/search | `solar-harness mirage search/exec` |
| Knowledge page write | `solar-harness wiki ingest/export` |
| Sprint status update | `solar-harness` coordinator/status |
| Config change | `solar-config-ui` or `/api/config` POST |
| QMD semantic search | `solar-harness wiki qmd-search` or via mirage `/qmd` |

## Codex Integration Rule

Codex should use:

```bash
solar-harness mirage search "<query>" --json   # canonical entry
solar-harness mirage exec -- 'cat /knowledge/path.md'
```

Codex must not:

- Mount the full home directory.
- Direct-write finalized Obsidian pages.
- Write Google Drive without explicit operator approval.
- Use host absolute paths (`~/...`, `/Users/...`, `/etc/...`) in exec.
- Treat raw grep results as accepted knowledge without provenance.

## Solar Harness Integration Rule

Solar Harness uses Mirage for cross-source discovery and keeps existing domain commands for mutation:

- Search/read: `solar-harness mirage ...` ← canonical entry
- Knowledge mutation: `solar-harness wiki ingest ...`
- Sprint mutation: coordinator/status/evaluator only.
- Config mutation: `solar-config-ui`.

## Security Guarantees

- Host absolute paths (`~/...`, `/etc/...`, `/Users/...`) are **blocked** in `mirage exec`.
- `/knowledge`, `/sprints`, `/solar`, `/cortex` mounts are **read-only**.
- `/drive` is read-only by default; write requires `--allow-write-drive` flag.
- No full home mount is permitted.
- Credential paths in `/solar` are covered by `deny_subpaths` redaction.

## Minimum Implementation Steps

1. Keep `solar-harness mirage doctor/search/exec` stable and JSON-first.
2. Any cross-source read starts at `solar-harness mirage search` — this is the canonical entry.
3. Status-server `/api/status` exposes `mirage` health block.
4. Config UI at `http://127.0.0.1:8789` controls Mirage enabled/workspace/Drive.
5. Eval checks: no full home mount, Drive read-only, sourced bounded output, host paths blocked.

