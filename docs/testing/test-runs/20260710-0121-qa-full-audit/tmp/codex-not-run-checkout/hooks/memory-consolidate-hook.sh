#!/bin/bash
# Memory Consolidate Hook — SessionEnd
# 会话结束时同步 Mem0 → Solar SQLite + 清理计数器
#
# 触发: SessionEnd (静默, exit 0)
# 功能:
#   1. 从 Mem0 (Docker :8888) 拉取所有 solar 用户记忆
#   2. 去重后插入 cortex_sources (需要先确保 mem0-sync task 存在)
#   3. 清理会话计数器文件 (.mem0-extract-counter-*, .mem0-recall-counter-*)
#   4. 写同步统计到 session-state.jsonl

set -u

readonly MEM0_URL="http://localhost:8888"
readonly SOLAR_DIR="$HOME/.solar"
readonly DB_PATH="$SOLAR_DIR/solar.db"
readonly STATE_LOG="$SOLAR_DIR/session-state.jsonl"
readonly SYNC_TASK_ID="mem0-sync"
readonly SYNC_CREDIBILITY=0.75

# --- Guard: DB must exist ---
[[ ! -f "$DB_PATH" ]] && exit 0

# --- Guard: curl + jq available ---
command -v curl >/dev/null 2>&1 || exit 0
command -v jq    >/dev/null 2>&1 || exit 0

# ---------------------------------------------------------------------------
# 1. Fetch all memories from Mem0 (5s timeout)
# ---------------------------------------------------------------------------
MEMORIES_JSON=$(curl -s --max-time 5 "$MEM0_URL/memories?user_id=solar" 2>/dev/null) || exit 0
[[ -z "$MEMORIES_JSON" ]] && exit 0

# Mem0 returns {"results": {"results": [...]}}  or  {"results": [...]}
# Try both paths
MEMORIES=$(echo "$MEMORIES_JSON" | jq -c '(.results.results // .results // [])' 2>/dev/null)
[[ -z "$MEMORIES" || "$MEMORIES" == "[]" || "$MEMORIES" == "null" ]] && exit 0

TOTAL=$(echo "$MEMORIES" | jq 'length' 2>/dev/null)
[[ -z "$TOTAL" || "$TOTAL" -eq 0 ]] && exit 0

# ---------------------------------------------------------------------------
# 2. Ensure the parent task row exists in cortex_tasks (FK constraint)
# ---------------------------------------------------------------------------
sqlite3 "$DB_PATH" "
    INSERT OR IGNORE INTO cortex_tasks
        (task_id, task_type, topic, status, current_phase)
    VALUES
        ('$SYNC_TASK_ID', 'analysis', 'Mem0 auto-sync', 'completed', 0);
" 2>/dev/null

# ---------------------------------------------------------------------------
# 3. Iterate and sync
# ---------------------------------------------------------------------------
NEW_COUNT=0
SKIP_COUNT=0

# Use a temp file for the loop body to avoid subshell variable scope loss
TEMP_INSERT=$(mktemp "$SOLAR_DIR/.mem0-consolidate-XXXXXX.sql")
> "$TEMP_INSERT"

echo "$MEMORIES" | jq -c '.[]' 2>/dev/null | while IFS= read -r item; do
    MEMORY_TEXT=$(echo "$item" | jq -r '.memory // ""' 2>/dev/null)
    MEMORY_ID=$(echo "$item"   | jq -r '.id // ""' 2>/dev/null)

    [[ -z "$MEMORY_TEXT" ]] && continue

    # De-duplicate: check first 50 chars in cortex_sources.finding
    # Escape for LIKE: % → \%, _ → \_  (use sqlite ESCAPE clause)
    SHORT_RAW="${MEMORY_TEXT:0:50}"
    # Minimal SQL-escape for LIKE pattern
    SHORT_ESCAPED=$(echo "$SHORT_RAW" | sed "s/%/\\\\%/g; s/_/\\\\_/g" | tr "'" "'\"'\"'")

    EXISTS=$(sqlite3 "$DB_PATH" \
        "SELECT COUNT(*) FROM cortex_sources WHERE finding LIKE '%${SHORT_ESCAPED}%' ESCAPE '\\';" 2>/dev/null || echo 0)

    if [[ "$EXISTS" -gt 0 ]]; then
        continue
    fi

    # Build citation_key from Mem0 id (first 12 chars for uniqueness)
    CIT_KEY="mem0_${MEMORY_ID:0:12}"

    # SQL-escape single quotes in the memory text
    ESCAPED_TEXT=$(echo "$MEMORY_TEXT" | tr "'" "'\"'\"'")

    # Append INSERT to temp SQL file
    echo "INSERT OR IGNORE INTO cortex_sources (citation_key, title, finding, task_id, credibility, expert_model) VALUES ('${CIT_KEY}', 'Mem0 auto-extract', '${ESCAPED_TEXT}', '$SYNC_TASK_ID', $SYNC_CREDIBILITY, 'mem0');" >> "$TEMP_INSERT"

done

# Execute batch INSERT
if [[ -s "$TEMP_INSERT" ]]; then
    INSERTED=$(sqlite3 "$DB_PATH" < "$TEMP_INSERT" 2>/dev/null && echo "ok" || echo "fail")
    if [[ "$INSERTED" == "ok" ]]; then
        NEW_COUNT=$(grep -c "^INSERT" "$TEMP_INSERT" 2>/dev/null || echo 0)
    fi
    SKIP_COUNT=$(( TOTAL - NEW_COUNT ))
fi
rm -f "$TEMP_INSERT"

# ---------------------------------------------------------------------------
# 4. Cleanup session counter files
# ---------------------------------------------------------------------------
rm -f "$SOLAR_DIR"/.mem0-extract-counter-* 2>/dev/null
rm -f "$SOLAR_DIR"/.mem0-recall-counter-*   2>/dev/null

# ---------------------------------------------------------------------------
# 5. Sync to MemPalace drawers (semantic memory layer)
# ---------------------------------------------------------------------------
MEMPL_SYNCED=0
if [[ -d "$HOME/.mempalace/palace" ]]; then
    TEMP_MEMPL=$(mktemp "$SOLAR_DIR/.mempl-sync-XXXXXX.py")
    cat > "$TEMP_MEMPL" << 'PYEOF'
import sys, hashlib
try:
    import chromadb
    client = chromadb.PersistentClient(path=sys.argv[1])
    col = client.get_or_create_collection('mempalace_drawers')
    synced = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        doc_id = hashlib.md5(line.encode()).hexdigest()[:16]
        existing = col.get(ids=[doc_id])
        if not existing['ids']:
            col.add(
                ids=[doc_id],
                documents=[line[:500]],
                metadatas=[{'wing': 'wing_solar', 'room': 'mem0_sync', 'source': 'memory-consolidate-hook'}]
            )
            synced += 1
    print(synced)
except Exception as e:
    print(f"0")
PYEOF
    MEMPL_SYNCED=$(echo "$MEMORIES" | jq -r '.[].memory // ""' 2>/dev/null | \
        "$HOME/.mempalace/venv/bin/python3" "$TEMP_MEMPL" "$HOME/.mempalace/palace" 2>/dev/null || echo 0)
    rm -f "$TEMP_MEMPL"
fi

# ---------------------------------------------------------------------------
# 6. Log to session-state.jsonl
# ---------------------------------------------------------------------------
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Try to read session_id from stdin JSON (SessionEnd may pass it)
STDIN_DATA=""
if [[ ! -t 0 ]]; then
    STDIN_DATA=$(cat 2>/dev/null | head -c 4096)
fi
SESSION_ID=$(echo "$STDIN_DATA" | jq -r '.session_id // "default"' 2>/dev/null || echo "default")

printf '{"ts":"%s","event":"mem0_consolidate","total":%d,"new":%d,"skipped":%d,"mempl_synced":%d,"source":"memory-consolidate-hook","session_id":"%s"}\n' \
    "$TS" "$TOTAL" "$NEW_COUNT" "$SKIP_COUNT" "${MEMPL_SYNCED:-0}" "$SESSION_ID" >> "$STATE_LOG" 2>/dev/null

exit 0
