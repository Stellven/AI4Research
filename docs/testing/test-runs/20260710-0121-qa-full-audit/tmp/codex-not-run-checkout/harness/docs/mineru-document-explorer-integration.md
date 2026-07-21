# MinerU Document Explorer Integration

Status: installed
Installed at: 2026-05-08
Vault: `~/Knowledge`
Collection: `solar-wiki`

## What Was Installed

- `mineru-document-explorer@1.0.9` via npm.
- CLI binary: `~/.npm-global/bin/qmd`.
- Source vendor copy: `~/.solar/harness/vendor/MinerU-Document-Explorer`.
- Skill symlinks:
  - `~/.agents/skills/mineru-document-explorer`
  - `~/.claude/skills/mineru-document-explorer`
  - `~/.codex/skills/mineru-document-explorer`

## Python Document Readers

Python document dependencies are installed in an isolated venv:

`~/.solar/harness/venvs/mineru-doc-explorer`

Installed packages:

- `pymupdf`
- `python-docx`
- `python-pptx`

## QMD Collections

The Obsidian vault is indexed as:

```bash
qmd collection add ~/Knowledge --name solar-wiki --mask '**/*.{md,pdf,docx,pptx}'
qmd wiki init solar-wiki
qmd context add qmd://solar-wiki "Solar Obsidian knowledge vault..."
```

Current expected status:

```bash
solar-harness wiki qmd-status
```

## Solar Harness Commands

```bash
solar-harness wiki qmd-status
solar-harness wiki qmd-search "Solar Harness Obsidian" -n 5 --json
solar-harness wiki qmd-update
solar-harness wiki qmd-mcp status
```

## Obsidian Wiki Integration

Both config files point wiki skills to QMD:

- `~/.obsidian-wiki/config`
- `~/Knowledge/.env`

Required values:

```bash
QMD_WIKI_COLLECTION=solar-wiki
QMD_PAPERS_COLLECTION=solar-wiki
```

## Background Services

MCP HTTP server:

- LaunchAgent: `~/Library/LaunchAgents/com.solar.qmd-mineru-document-explorer.plist`
- Endpoint: `http://localhost:8181/mcp`
- Health: `solar-harness wiki qmd-mcp status`

Index updater:

- LaunchAgent: `~/Library/LaunchAgents/com.solar.qmd-mineru-update.plist`
- Interval: 300 seconds
- Action: `qmd update`

## Verified Commands

```bash
qmd status
qmd search "Solar Harness Obsidian" -c solar-wiki -n 5 --json
qmd doc-grep qmd://solar-wiki/raw/file-uploads/20260507t233806z-01-why-should-we-train-ai-in-space.pdf "orbit|space|training"
solar-harness wiki qmd-search "Solar Harness Obsidian" -n 3 --json
```

## Notes

- `qmd search` is BM25 and works without embeddings.
- `qmd query` and vector search require embeddings; run `qmd embed -c solar-wiki` when ready to download local models.
- Agent deep reading must use collection-relative paths like `qmd://solar-wiki/path/to/file.pdf`, not absolute `/Users/...` paths.
