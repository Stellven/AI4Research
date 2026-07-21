# Solar KB Default Context — Runbook

**Sprint**: sprint-20260508-kb-qmd-default-fallback  
**Updated**: 2026-05-08

## How Default KB Retrieval Works

When Claude receives a knowledge-relevant prompt (`UserPromptSubmit` hook), the flow is:

```
UserPromptSubmit
  → ~/.claude/hooks/solar-knowledge-context.sh
      extracts first 120 chars of user_prompt as QUERY
      calls solar-knowledge-context.py --query QUERY --format hook ...
          1. FTS5 search: fts_unified_search MATCH query
          2. Vault index: obsidian_vault_index LIKE query  (if table exists)
          3. Cortex fallback: cortex_sources LIKE query[:60]
          4. Semantic: evo_memory_semantic LIKE query[:60]
          5. QMD fallback: qmd search <keywords> -c solar-wiki --json
      format as <solar-knowledge-context> block
      output injected as UserPromptSubmit context
```

## DB Path

```
~/.solar/solar.db
```

Check FTS coverage:
```bash
sqlite3 ~/.solar/solar.db "SELECT COUNT(*) FROM fts_unified_search"
sqlite3 ~/.solar/solar.db "SELECT COUNT(*) FROM cortex_sources"
```

## QMD Fallback Path

Binary resolution order:
1. `$QMD_BIN` environment variable (if set and exists as a file)
2. `~/.npm-global/bin/qmd` (hardcoded known path)
3. `shutil.which("qmd")` (PATH search)

Collection used: `solar-wiki`

For long Chinese queries (>4 chars), the retriever strips function/action words to extract the topical noun phrase before calling qmd. This handles prompts like "帮我基于大模型热力学分析注意力机制" → searches "大模型热力学".

## How to Verify

**Full retrieval check (A1)**:
```bash
python3 ~/.solar/harness/lib/solar-knowledge-context.py \
  --query '大模型热力学' --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["hits"]), "hits")'
```

**Hook injection check (A2)**:
```bash
printf '{"user_prompt":"帮我基于大模型热力学分析注意力机制"}' \
  | ~/.claude/hooks/solar-knowledge-context.sh \
  | grep '<solar-knowledge-context>'
```

**Run full regression**:
```bash
bash ~/.solar/harness/tests/test-solar-kb-qmd-fallback.sh
```

## How to Disable

Set environment variable before running Claude:
```bash
SOLAR_KB_CONTEXT=0 claude
```

Or permanently in your shell profile:
```bash
export SOLAR_KB_CONTEXT=0
```

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `"hits": []` for known note | DB FTS not indexed + qmd wrong collection | Check `solar-harness wiki qmd-status`; re-embed if needed |
| `"error": "db_missing"` | `~/.solar/solar.db` not present | Run `solar-harness doctor` |
| Hook silent / no output | Prompt doesn't match NEEDS_KB heuristic | Check regex in `solar-knowledge-context.sh` |
| `"error": "database is locked"` | Another process holds write lock on DB | Wait 1s and retry; check for stuck migrations |
| qmd returns 0 hits | qmd index stale or collection not synced | `solar-harness wiki qmd-embed status`; trigger re-embed |
| Hook calls wrong script | `HOOK_SCRIPT` points to `solar-unified-context.py` | Fix to `solar-knowledge-context.py` (fixed in this sprint) |

## Dispatch Context Note (D4)

Coordinator-dispatched panes use `tmux send-keys` to inject text into a Claude session. This mechanism does **not** trigger `UserPromptSubmit` hooks — hooks only fire for interactive user input in the Claude Code CLI.

Consequence: builder and evaluator panes dispatched by `solar-harness` do **not** receive automatic KB context injection via this hook.

Mitigation options (not implemented in this sprint):
- Manually prepend sourced KB context to the dispatch `.dispatch.md` text at coordinator dispatch time
- Add a separate KB context step in the coordinator pipeline before dispatching

For now, builders in dispatched panes should run explicit searches:
```bash
solar-harness mirage search "<query>" --json
# or
python3 ~/.solar/harness/lib/solar-knowledge-context.py --query "<query>"
```
