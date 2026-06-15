#!/bin/bash
# Memory Recall Hook — UserPromptSubmit
# 搜索 Mem0 + FTS5 跨会话回忆并注入到对话中
set -u

RECALL_START=$(date +%s)
readonly MEM0_URL="http://localhost:8888"
readonly SOLAR_DIR="$HOME/.solar"
readonly RECALL_SCRIPT="$HOME/.claude/core/solar-farm/cross-session-recall.ts"
readonly MAX_RECALLS=10
readonly MIN_QUERY_LEN=5
readonly MIN_SCORE=28

INPUT=$(cat)
[[ -z "$INPUT" ]] && exit 0

# 提取用户消息（注意：实际字段是 .prompt 不是 .user_prompt）
PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""' 2>/dev/null)
[[ -z "$PROMPT" || ${#PROMPT} -lt $MIN_QUERY_LEN ]] && exit 0

# 跳过信号词
case "$PROMPT" in
    ok|OK|继续|批准|好的|嗯|是|否|保存|save|done|好|yes|no|确认|cancel) exit 0 ;;
esac

# 检查召回计数
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "default"' 2>/dev/null)
COUNTER_FILE="$SOLAR_DIR/.mem0-recall-counter-${SESSION_ID}"
if [[ -f "$COUNTER_FILE" ]]; then
    COUNT=$(cat "$COUNTER_FILE" 2>/dev/null)
    [[ "$COUNT" =~ ^[0-9]+$ ]] || COUNT=0
else
    COUNT=0
fi
[[ "$COUNT" -ge "$MAX_RECALLS" ]] && exit 0

# ============================================================
# Phase 0 + Phase 1 并行执行 (MemPalace + Mem0)
# ============================================================

TEMP_P0="$SOLAR_DIR/.recall-p0-$$"
TEMP_P1="$SOLAR_DIR/.recall-p1-$$"
mkdir -p "$SOLAR_DIR"

# Phase 0: MemPalace 语义搜索 (后台)
(
    MEMPL_OUTPUT=""
    if [[ -d "$HOME/.mempalace/palace" ]]; then
        SAFE_PROMPT=$(echo "$PROMPT" | sed "s/'/'\\\\''/g" | head -c 500)
        MEMPL_OUTPUT=$("$HOME/.mempalace/venv/bin/python3" -c "
import sys
try:
    import chromadb
    client = chromadb.PersistentClient(path='$HOME/.mempalace/palace')
    col = client.get_collection('mempalace_drawers')
    results = col.query(query_texts=['${SAFE_PROMPT}'], n_results=3)
    for i, (doc, dist) in enumerate(zip(results['documents'][0], results['distances'][0])):
        meta = results['metadatas'][0][i]
        wing = meta.get('wing', '?')
        room = meta.get('room', '?')
        if dist < 1.2:
            print(f'{i+1}. [{wing}/{room}] {doc[:150]}... (sim: {1-dist:.2f})')
except Exception:
    pass
" 2>/dev/null)
    fi
    [[ -n "$MEMPL_OUTPUT" ]] && echo "$MEMPL_OUTPUT" > "$TEMP_P0"
) &
PID_P0=$!

# Phase 1: Mem0 搜索 (后台)
(
    SEARCH_RESULT=$(curl -s --max-time 8 -X POST "$MEM0_URL/search" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg query "$PROMPT" '{
            query: $query,
            user_id: "solar",
            limit: 3
        }')" 2>/dev/null)

    if [[ -n "$SEARCH_RESULT" ]] && echo "$SEARCH_RESULT" | jq -e 'type' >/dev/null 2>&1; then
        MEMORIES=$(echo "$SEARCH_RESULT" | jq -c '.results.results // []' 2>/dev/null)
        if [[ -n "$MEMORIES" && "$MEMORIES" != "[]" && "$MEMORIES" != "null" ]]; then
            TEMP_MATCHES=$(mktemp)
            while IFS= read -r item; do
                MEMORY=$(echo "$item" | jq -r '.memory // ""' 2>/dev/null)
                SCORE=$(echo "$item" | jq -r '.score // 0' 2>/dev/null)
                [[ -z "$MEMORY" ]] && continue
                SCORE_INT=$(echo "$SCORE" | awk '{printf "%.0f", $1 * 100}')
                [[ "$SCORE_INT" -lt $MIN_SCORE ]] && continue
                echo "${SCORE_INT}|${SCORE}|${MEMORY}" >> "$TEMP_MATCHES"
            done < <(echo "$MEMORIES" | jq -c '.[]' 2>/dev/null)
            if [[ -s "$TEMP_MATCHES" ]]; then
                sort -t'|' -k1 -rn "$TEMP_MATCHES" | head -3 > "$TEMP_P1"
            fi
            rm -f "$TEMP_MATCHES"
        fi
    fi
) &
PID_P1=$!

# 等待两个阶段完成
wait $PID_P0 $PID_P1 2>/dev/null

# 收集 Phase 0 结果
MEMPL_OUTPUT=""
if [[ -f "$TEMP_P0" ]]; then
    MEMPL_OUTPUT=$(cat "$TEMP_P0" 2>/dev/null)
    if [[ -n "$MEMPL_OUTPUT" ]]; then
        mkdir -p "$SOLAR_DIR"
        echo $((COUNT + 1)) > "$COUNTER_FILE"
        echo "[MemPalace记忆] 语义搜索:"
        echo "$MEMPL_OUTPUT"
        echo ""
    fi
    rm -f "$TEMP_P0"
fi

# Phase 0b: KG 实体查找 (快速, 串行)
if [[ -d "$HOME/.mempalace/palace" ]]; then
    KNOWN_ENTITIES="ThunderLLAMA|ClawGate|Solar-MAX|ThunderMLX|Solar|MemPalace|Cortex|ATLAS|Hermes|OWL|Evolve|Mem0|Honcho"
    FOUND_ENTITY=$(echo "$PROMPT" | grep -oiE "$KNOWN_ENTITIES" 2>/dev/null | head -3 | sort -u)
    if [[ -n "$FOUND_ENTITY" ]]; then
        KG_OUTPUT=$("$HOME/.mempalace/venv/bin/python3" -c "
import sqlite3
db = sqlite3.connect('$HOME/.mempalace/knowledge_graph.sqlite3')
for entity in '''$FOUND_ENTITY'''.split('\n'):
    entity = entity.strip()
    if not entity: continue
    rows = db.execute('SELECT subject, predicate, object FROM triples WHERE lower(subject)=lower(?) OR lower(object)=lower(?) ORDER BY rowid DESC LIMIT 5', (entity, entity)).fetchall()
    if rows:
        print(f'  [{entity}]')
        for s, p, o in rows:
            print(f'    {s} → {p} → {o[:80]}')
db.close()
" 2>/dev/null)
        if [[ -n "$KG_OUTPUT" ]]; then
            echo "[KG关系] 用户消息涉及已知实体:"
            echo "$KG_OUTPUT"
            echo ""
        fi
    fi
fi

# 收集 Phase 1 结果
HAS_MEM0_OUTPUT=false
if [[ -f "$TEMP_P1" ]]; then
    HAS_MEM0_OUTPUT=true
    if [[ "$HAS_MEM0_OUTPUT" == true ]] && [[ -z "$MEMPL_OUTPUT" ]]; then
        mkdir -p "$SOLAR_DIR"
        echo $((COUNT + 1)) > "$COUNTER_FILE"
    fi
    echo "[记忆召回] 相关记忆:"
    LINE_NUM=0
    while IFS='|' read -r _score_int score memory; do
        LINE_NUM=$((LINE_NUM + 1))
        echo "${LINE_NUM}. ${memory} (相关度: ${score})"
    done < "$TEMP_P1"
    echo ""
    rm -f "$TEMP_P1"
fi

# ============================================================
# Phase 2: FTS5 跨会话回忆
# ============================================================

if [[ -f "$RECALL_SCRIPT" ]]; then
    FTS5_OUTPUT=$(bun run "$RECALL_SCRIPT" inject "$PROMPT" 2>/dev/null)
    if [[ -n "$FTS5_OUTPUT" ]]; then
        # 去重: 如果 FTS5 结果和 Phase 0/Phase 1 高度重叠(前60字匹配), 跳过
        if [[ -n "$MEMPL_OUTPUT" ]]; then
            FTS5_OVERLAP=$(echo "$FTS5_OUTPUT" | grep -cF "$(echo "$MEMPL_OUTPUT" | head -c 60)" 2>/dev/null || echo 0)
            [[ "$FTS5_OVERLAP" -gt 0 ]] && FTS5_OUTPUT=""
        fi
        if [[ -n "$FTS5_OUTPUT" ]]; then
            # 如果没有 Mem0 输出也更新计数器
            if [[ "$HAS_MEM0_OUTPUT" == false ]]; then
                mkdir -p "$SOLAR_DIR"
                echo $((COUNT + 1)) > "$COUNTER_FILE"
            fi
            echo "$FTS5_OUTPUT"
        fi
    fi
fi

# ============================================================
# Phase 3: Honcho Dialectic Recall (self-hosted, always runs)
# ============================================================

HONCHO_BASE="${HONCHO_BASE_URL:-http://localhost:8900}"
HONCHO_WORKSPACE="${HONCHO_WORKSPACE_ID:-solar-farm}"
HONCHO_USER_PEER="${HONCHO_USER_PEER_ID:-${HONCHO_PEER_ID:-}}"

# Honcho Dialectic provides REASONED recall (complementary to Mem0's keyword recall)
# Runs when HONCHO_USER_PEER_ID or HONCHO_PEER_ID is configured.
if [[ -n "$HONCHO_USER_PEER" ]]; then
    (
        HONCHO_RESULT=$(curl -s --connect-timeout 3 --max-time 10 -X POST \
            "${HONCHO_BASE}/v3/workspaces/${HONCHO_WORKSPACE}/peers/${HONCHO_USER_PEER}/chat" \
            -H "Content-Type: application/json" \
            -d "$(jq -n --arg query "$PROMPT" '{
                query: $query,
                stream: false,
                level: "low"
            }')" 2>/dev/null)

        if [[ -n "$HONCHO_RESULT" ]]; then
            HONCHO_CONTENT=$(echo "$HONCHO_RESULT" | jq -r '.content // ""' 2>/dev/null)
            if [[ -n "$HONCHO_CONTENT" && ${#HONCHO_CONTENT} -gt 20 ]]; then
                echo "[Honcho记忆] ${HONCHO_CONTENT}"
            fi
        fi
    ) &
fi

# Wait for background Honcho (max 10s)
wait

# ============================================================
# Recall Analytics: 记录本次召回统计
# ============================================================
RECALL_ELAPSED=$(( $(date +%s) - RECALL_START ))
HAS_P0=$([[ -n "$MEMPL_OUTPUT" ]] && echo 1 || echo 0)
HAS_P1=$([[ "$HAS_MEM0_OUTPUT" == true ]] && echo 1 || echo 0)
HAS_P2=$([[ -n "${FTS5_OUTPUT:-}" ]] && echo 1 || echo 0)
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
printf '{"ts":"%s","event":"recall_analytics","p0_mempl":%s,"p1_mem0":%s,"p2_fts5":%s,"elapsed_s":%s,"prompt_len":%s,"session_id":"%s"}\n' \
    "$TS" "$HAS_P0" "$HAS_P1" "$HAS_P2" "$RECALL_ELAPSED" "${#PROMPT}" "${SESSION_ID}" >> "$SOLAR_DIR/session-state.jsonl" 2>/dev/null

exit 0
