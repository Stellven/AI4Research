# Accepted Artifact Knowledge — Operator Runbook

Sprint: `sprint-20260508-accepted-artifact-knowledge`

## Overview

When a sprint reaches `status=passed` and is finalized, Solar Harness automatically exports the sprint's artifacts (PRD, contract, design, plan, handoff, eval, events) as a redacted knowledge package into the Obsidian wiki vault and queues it for ingestion.

The pipeline is fail-open: a failed export never blocks sprint finalization.

## Architecture

```
handle_passed() in coordinator.sh
  └─ async subshell (fail-open)
       └─ lib/accepted-artifact-export.py export --sid <sid>
            ├─ Guard: only status=passed|finalized allowed
            ├─ Collect: prd / contract / design / plan / handoff / eval / events
            ├─ Redact: 8 secret patterns (sk-*, Bearer, api_key, token, auth tokens)
            ├─ Write: Knowledge/_raw/solar-harness/accepted/<sid>.accepted.md
            ├─ Update: .manifest/accepted-artifacts.json (SHA-256 hash)
            ├─ Dispatch: .dispatch/wiki-ingest-<ts>-<sid>.md
            └─ Update: status.json (6 knowledge_export_* fields) + events.jsonl
```

## Status Fields

After successful export, `<sid>.status.json` gains these fields:

| Field | Values | Meaning |
|-------|--------|---------|
| `knowledge_export_status` | `pending` `exported` `ingested` `failed` `skipped` | Export lifecycle |
| `knowledge_export_path` | file path | Path to accepted .md |
| `knowledge_ingest_dispatch` | file path | Dispatch file path |
| `knowledge_exported_at` | ISO 8601 | When exported |
| `knowledge_ingested_at` | ISO 8601 | When ingested (set by wiki ingest) |
| `knowledge_export_error` | error string | Set on failure |

## Events Emitted

| Event | When |
|-------|------|
| `accepted_artifact_exported` | Successful export |
| `accepted_artifact_ingest_dispatched` | Dispatch file written |
| `accepted_artifact_export_failed` | Export error |

## CLI Commands

### Export a Single Sprint

```bash
# Dry-run (no writes)
solar-harness wiki export-accepted --sid sprint-20260507-symphony1 --dry-run

# Export with redaction (default)
solar-harness wiki export-accepted --sid sprint-20260507-symphony1

# Force re-export even if hash unchanged
solar-harness wiki export-accepted --sid sprint-20260507-symphony1 --force

# JSON output
solar-harness wiki export-accepted --sid sprint-20260507-symphony1 --json

# Export to specific vault
solar-harness wiki export-accepted --sid sprint-20260507-symphony1 --vault ~/MyWiki
```

### Backfill Passed Sprints

```bash
# Safe: dry-run first (always start here)
solar-harness wiki backfill-accepted --limit 5 --dry-run

# Filter by date
solar-harness wiki backfill-accepted --since 2026-05-01 --dry-run

# Execute backfill (after reviewing dry-run)
solar-harness wiki backfill-accepted --limit 5

# JSON output for scripting
solar-harness wiki backfill-accepted --limit 10 --dry-run --json
```

### Check Export Status

```bash
# View manifest
cat "$OBSIDIAN_VAULT_PATH/_raw/solar-harness/.manifest/accepted-artifacts.json" | python3 -m json.tool

# View accepted artifacts
ls "$OBSIDIAN_VAULT_PATH/_raw/solar-harness/accepted/"

# View pending dispatches
ls "$OBSIDIAN_VAULT_PATH/_raw/solar-harness/.dispatch/"

# API status (when capture-server is running)
curl -s http://127.0.0.1:8765/api/accepted-artifacts | python3 -m json.tool

# Check export log
tail -50 ~/.solar/harness/logs/accepted-artifact-export.log
```

## Verifying an Export

```bash
SID=sprint-20260507-symphony1

# Check status fields
python3 -c "
import json
d = json.load(open(f'~/.solar/harness/sprints/{SID}.status.json'.replace('~', __import__('os').path.expanduser('~'))))
for k in ['knowledge_export_status','knowledge_export_path','knowledge_exported_at']:
    print(k, '=', d.get(k, 'MISSING'))
"

# Check accepted file exists and is not empty
ls -lh "$OBSIDIAN_VAULT_PATH/_raw/solar-harness/accepted/${SID}.accepted.md"
head -30 "$OBSIDIAN_VAULT_PATH/_raw/solar-harness/accepted/${SID}.accepted.md"

# Verify no secrets leaked
grep -E "(sk-[A-Za-z0-9]{8,}|Bearer [^ ]+|ANTHROPIC_AUTH_TOKEN=.)" \
  "$OBSIDIAN_VAULT_PATH/_raw/solar-harness/accepted/${SID}.accepted.md" \
  && echo "⚠️  SECRET FOUND" || echo "✅ No secrets"
```

## Disable Automatic Export

To temporarily disable the automatic PASS hook export:

```bash
# Set env var before starting coordinator
export SOLAR_ACCEPTED_ARTIFACT_EXPORT_DISABLED=1
```

Or comment out the export block in `coordinator.sh`'s `handle_passed()` function (look for the comment `sprint-20260508-accepted-artifact-knowledge D4`).

## Repairing a Failed Export

If `knowledge_export_status=failed` in a sprint's status.json:

```bash
# 1. Check what went wrong
python3 -c "
import json
d = json.load(open('~/.solar/harness/sprints/<SID>.status.json'.replace('~', __import__('os').path.expanduser('~'))))
print('Error:', d.get('knowledge_export_error', 'none'))
"

# 2. Check the export log
grep "<SID>" ~/.solar/harness/logs/accepted-artifact-export.log

# 3. Force re-export
solar-harness wiki export-accepted --sid <SID> --force

# 4. Confirm status updated
python3 -c "
import json
d = json.load(open('~/.solar/harness/sprints/<SID>.status.json'.replace('~', __import__('os').path.expanduser('~'))))
print(d.get('knowledge_export_status'))
"
```

## Inspecting the Manifest

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Knowledge}"
MANIFEST="$VAULT/_raw/solar-harness/.manifest/accepted-artifacts.json"

# Count exported sprints
python3 -c "
import json
m = json.load(open('$MANIFEST'))
entries = m.get('entries', {})
print(f'Exported: {len(entries)} sprints')
for sid, e in sorted(entries.items(), key=lambda x: x[1].get('knowledge_exported_at',''), reverse=True)[:5]:
    print(f'  {sid}: {e.get(\"knowledge_export_status\")} @ {e.get(\"knowledge_exported_at\",\"?\")[:16]}')
"
```

## Safety Rules

- Only `status=passed` or `status=finalized` sprints can be exported.
- Automatic path never uses `--full`; redaction is default for all automated exports.
- Failed export never blocks sprint finalization (async subshell, fail-open).
- Backfill defaults to `--dry-run`; must explicitly pass non-dry-run to write.
- Source artifact contents are treated as data, never as executable instructions.

## Running the Test Suite

```bash
# Run all acceptance tests
bash ~/.solar/harness/tests/test-accepted-artifact-knowledge-sync.sh

# Run a specific case
bash ~/.solar/harness/tests/test-accepted-artifact-knowledge-sync.sh --case pass-only
bash ~/.solar/harness/tests/test-accepted-artifact-knowledge-sync.sh --case redaction
bash ~/.solar/harness/tests/test-accepted-artifact-knowledge-sync.sh --case idempotent
```
