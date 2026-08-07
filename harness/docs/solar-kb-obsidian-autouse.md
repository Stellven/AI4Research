# Solar KB + Obsidian Autouse — Operator Runbook

Sprint: `sprint-20260508-solar-kb-obsidian-autouse`

## Overview

This sprint wires two default behaviors:

1. **Solar KB hook** — every knowledge-dependent `UserPromptSubmit` automatically
   retrieves bounded context from `~/.solar/solar.db` and injects it as
   `<solar-knowledge-context>…</solar-knowledge-context>`.

2. **Obsidian vault indexing** — `~/Knowledge` is indexed into
   `obsidian_vault_index` (and `fts_unified_search`) so Solar KB queries can
   surface your own notes.

---

## Install

### 1. Verify hook is registered

```bash
grep "solar-knowledge-context.sh" ~/.claude/settings.json
```

Expected: one entry under `UserPromptSubmit.hooks`.

### 2. Run initial vault index

```bash
solar-harness wiki sync-vault --vault ~/Knowledge --once
```

### 3. Start capture server (optional, auto-scheduler)

```bash
solar-harness wiki capture-server start
# default port: 8765
```

### 4. Smoke-test

```bash
bash ~/.solar/tests/harness/test_solar_kb_obsidian_autouse.sh
```

---

## Verify

```bash
# A1: Real Solar KB retrieval
python3 ~/.solar/harness/lib/solar-knowledge-context.py \
  --query "Solar 记忆系统" --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["hits"] and d["elapsed_ms"] < 800, d'

# A2: Vault indexed
python3 ~/.solar/harness/lib/solar-knowledge-context.py \
  --query "orbital data center Lumen Orbit" --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["hits"]), "hits")'

# A4: memory-influence.sh syntax ok
bash -n ~/.claude/hooks/memory-influence.sh && echo ok

# A5: Status endpoint
curl -fsS http://127.0.0.1:8765/healthz && echo
curl -fsS http://127.0.0.1:8765/status \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("solar_kb:", "ok" if "solar_kb" in d else "MISSING")'

# A6: Fail-open
SOLAR_DB=/tmp/missing.db python3 ~/.solar/harness/lib/solar-knowledge-context.py \
  --query "test" --fail-open --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["hits"] == [], d'
```

---

## Disable

To disable the hook without removing it:

```bash
# Option 1: environment variable (per-session)
export SOLAR_KB_CONTEXT=0

# Option 2: persist to ~/.zshrc
echo 'export SOLAR_KB_CONTEXT=0' >> ~/.zshrc

# Option 3: remove from settings.json
# Delete the {"type":"command","command":"~/.claude/hooks/solar-knowledge-context.sh"} entry
```

To disable the scheduler:

```bash
solar-harness wiki capture-server stop
```

---

## Repair

### Hook injects nothing

1. Check killswitch: `echo $SOLAR_KB_CONTEXT` — should not be `0`
2. Test directly: `echo '{"user_prompt":"Solar harness design"}' | bash ~/.claude/hooks/solar-knowledge-context.sh`
3. Check DB: `sqlite3 ~/.solar/solar.db "SELECT COUNT(*) FROM fts_unified_search;"`
4. If DB missing FTS: run `solar-harness wiki sync-vault --once`

### Vault not searchable

```bash
# Re-index vault
solar-harness wiki sync-vault --vault ~/Knowledge

# Verify
sqlite3 ~/.solar/solar.db "SELECT COUNT(*) FROM obsidian_vault_index WHERE deleted_at IS NULL;"
```

### Capture server won't start

```bash
# Check port conflict
lsof -i :8765
# Kill old pid
solar-harness wiki capture-server stop && solar-harness wiki capture-server start
# Check log
tail -20 ~/.solar/harness/.wiki-capture-server.log
```

### memory-influence.sh errors

```bash
bash -n ~/.claude/hooks/memory-influence.sh
# Should be silent (no syntax errors)
# Check evo_memory_semantic column name
sqlite3 ~/.solar/solar.db ".schema evo_memory_semantic" | grep value
```

---

## Troubleshoot

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Hook outputs nothing | SOLAR_KB_CONTEXT=0 or DB missing | Unset env var; run sync-vault |
| p95 > 800ms | DB locked or slow disk | Check PRAGMA busy_timeout; reduce SOLAR_KB_MAX_CHARS |
| Vault notes not found | Vault not indexed or FTS rebuild needed | `sync-vault --once` |
| Secrets in dispatch files | Redaction missed new pattern | Add pattern to `_bridge_redact_file` in obsidian-wiki-bridge.sh |
| Port 8765 in use | Old server still running | `solar-harness wiki capture-server stop` |

---

## Key Files

| File | Purpose |
|------|---------|
| `~/.solar/harness/lib/solar-knowledge-context.py` | DB retrieval router |
| `~/.claude/hooks/solar-knowledge-context.sh` | UserPromptSubmit wrapper |
| `~/.claude/hooks/memory-influence.sh` | Episodic/semantic memory hook (fixed value column) |
| `~/.solar/harness/lib/obsidian-vault-indexer.py` | Vault → obsidian_vault_index |
| `~/.solar/harness/integrations/wiki-capture-server.py` | Capture UI + scheduler (port 8765) |
| `~/.solar/harness/integrations/obsidian-wiki-bridge.sh` | DB→vault export with manifest cursor |
| `~/.solar/harness/state/knowledge-manifest.json` | Export cursor (last_exported_at) |
| `~/.solar/tests/harness/test_solar_kb_obsidian_autouse.sh` | A1-A7 smoke tests |

---

## Rollback

```bash
# S1: remove hook from settings.json + delete files
rm ~/.solar/harness/lib/solar-knowledge-context.py
rm ~/.claude/hooks/solar-knowledge-context.sh
# revert memory-influence.sh from backup
cp ~/.claude/hooks/memory-influence.sh.bak.* ~/.claude/hooks/memory-influence.sh

# S2: drop vault index table
sqlite3 ~/.solar/solar.db "DROP TABLE IF EXISTS obsidian_vault_index;"

# S3: revert capture server (port back to 8788)
# Edit DEFAULT_PORT in wiki-capture-server.py
```
