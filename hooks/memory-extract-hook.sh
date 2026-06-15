#!/bin/bash
# Memory Extract Hook — PostToolUse
# 从工具输出中自动提取有价值记忆存入 Mem0
#
# 触发: PostToolUse, matcher: Write|Edit|mcp__brain-router__complete
# 输入: stdin JSON {"tool_name", "tool_input", "tool_response", "session_id"}
# 输出: JSON with hookSpecificOutput.additionalContext (仅在有新记忆时)
#
# 架构: 同步部分 < 10ms (jq + 计数器), 网络部分全部后台异步
#   - Mem0 search/write 延迟 3-6s, 不能阻塞工具调用
#   - 后台任务写结果到 ~/.solar/.mem0-log-{session_id} 供审计
#
# 策略:
#   Write/Edit -> 提取文件路径 + 前300字摘要
#   brain-router -> 提取 LLM 响应前500字 (过滤短/错误回复)
#   去重: POST /search 检查 score > 0.9
#   限流: 每会话最多 20 次提取

set -u

readonly MEM0_URL="http://localhost:8888"
readonly SOLAR_DIR="$HOME/.solar"
readonly MAX_EXTRACTS=20
readonly MIN_CONTENT_LEN=50

# ── 读取输入 ─────────────────────────────────────────────
INPUT=$(cat)
[[ -z "$INPUT" ]] && exit 0

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)
[[ -z "$TOOL_NAME" ]] && exit 0

case "$TOOL_NAME" in
    Write|Edit) ;;
    mcp__brain-router__complete) ;;
    *) exit 0 ;;
esac

TOOL_RESPONSE=$(echo "$INPUT" | jq -r '.tool_response // ""' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "default"' 2>/dev/null)

# ── 提取计数限流 ─────────────────────────────────────────
COUNTER_FILE="$SOLAR_DIR/.mem0-extract-counter-${SESSION_ID}"
if [[ -f "$COUNTER_FILE" ]]; then
    COUNT=$(cat "$COUNTER_FILE" 2>/dev/null)
    [[ "$COUNT" =~ ^[0-9]+$ ]] || COUNT=0
else
    COUNT=0
fi
[[ "$COUNT" -ge "$MAX_EXTRACTS" ]] && exit 0

# ── 按工具类型提取内容 (纯 bash, <5ms) ──────────────────
CONTENT=""
METADATA_SECTOR="auto"

if [[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]]; then
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null)
    [[ -z "$FILE_PATH" ]] && exit 0

    # 跳过 trivial 文件 (点文件、锁文件、日志、计数器、临时文件)
    case "$FILE_PATH" in
        */.*|*.lock|*.log|*/tmp/*|*counter-*|*.jsonl) exit 0 ;;
    esac

    # 读文件内容前300字符作为摘要
    if [[ -f "$FILE_PATH" ]]; then
        SNIPPET=$(head -c 300 "$FILE_PATH" 2>/dev/null | tr '\n' ' ')
    else
        SNIPPET=$(echo "$TOOL_RESPONSE" | head -c 300 2>/dev/null | tr '\n' ' ')
    fi

    [[ -z "$SNIPPET" ]] && exit 0
    [[ ${#SNIPPET} -lt $MIN_CONTENT_LEN ]] && exit 0

    FILE_BASENAME=$(basename "$FILE_PATH")
    CONTENT="用户修改了文件 ${FILE_BASENAME} (路径: ${FILE_PATH})，内容涉及: ${SNIPPET}"
    METADATA_SECTOR="file_edit"

elif [[ "$TOOL_NAME" == "mcp__brain-router__complete" ]]; then
    SNIPPET=$(echo "$TOOL_RESPONSE" | head -c 500 2>/dev/null | tr '\n' ' ')
    [[ -z "$SNIPPET" ]] && exit 0
    [[ ${#SNIPPET} -lt $MIN_CONTENT_LEN ]] && exit 0

    # 跳过明显错误回复
    case "$SNIPPET" in
        *"error"*|*"Error"*|*"timeout"*|*"failed"*|*"无法"*|*"拒绝"*) exit 0 ;;
    esac

    MODEL=$(echo "$INPUT" | jq -r '.tool_input.model // "unknown"' 2>/dev/null)
    CONTENT="牛马 ${MODEL} 回复: ${SNIPPET}"
    METADATA_SECTOR="llm_response"
fi

[[ -z "$CONTENT" ]] && exit 0

# ── 更新计数器 (同步, <1ms) ──────────────────────────────
mkdir -p "$SOLAR_DIR"
echo $((COUNT + 1)) > "$COUNTER_FILE"

# ── 后台异步: 去重检查 + 写入 Mem0 + Honcho Ingest ──────────────
# 所有网络操作放后台, 不阻塞工具调用 (< 10ms 总延迟)
(
    # ============================================================
    # Mem0 写入 (原有逻辑)
    # ============================================================
    curl -s --max-time 2 "$MEM0_URL/health" >/dev/null 2>&1 || exit 0

    SEARCH_QUERY=$(echo "$CONTENT" | head -c 100)
    DEDUP_RESULT=$(curl -s --max-time 5 -X POST "$MEM0_URL/search" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg query "$SEARCH_QUERY" '{
            query: $query,
            user_id: "solar",
            limit: 3
        }')" 2>/dev/null)

    if [[ -n "$DEDUP_RESULT" ]]; then
        TOP_SCORE=$(echo "$DEDUP_RESULT" | jq -r '[.results.results[]?.score // 0] | max // 0' 2>/dev/null)
        if [[ -n "$TOP_SCORE" ]] && echo "$TOP_SCORE" | grep -qE '^[0-9.]+$'; then
            is_high=$(echo "$TOP_SCORE > 0.9" | bc 2>/dev/null)
            [[ "$is_high" == "1" ]] && exit 0
        fi
    fi

    RESULT=$(curl -s --max-time 30 -X POST "$MEM0_URL/memories" \
        -H "Content-Type: application/json" \
        -d "$(jq -n \
            --arg content "$CONTENT" \
            --arg sector "$METADATA_SECTOR" \
            --arg session "$SESSION_ID" \
            '{
                messages: [{"role": "user", "content": $content}],
                user_id: "solar",
                metadata: {
                    source: "hook",
                    sector: $sector,
                    session_id: $session
                }
            }')" 2>/dev/null)

    LOG_FILE="$SOLAR_DIR/.mem0-log-${SESSION_ID}"
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    if [[ -n "$RESULT" ]] && echo "$RESULT" | jq -e '.results' >/dev/null 2>&1; then
        echo "[${TS}] stored: $(echo "$CONTENT" | head -c 80)..." >> "$LOG_FILE"
    else
        echo "[${TS}] failed: Mem0 write error (result: ${RESULT:-empty})" >> "$LOG_FILE"
    fi

    # ============================================================
    # Honcho Ingest (parallel, fire-and-forget)
    # ============================================================
    HONCHO_BASE="${HONCHO_BASE_URL:-http://localhost:8900}"
    HONCHO_WS="${HONCHO_WORKSPACE_ID:-solar-farm}"
    HONCHO_SESSION="session-$(date +%Y%m%d)"
    HONCHO_PEER="${HONCHO_PEER_ID:-}"

    if [[ -n "$HONCHO_PEER" ]]; then
        # Write content as message to Honcho (Deriver will process it async)
        curl -s --connect-timeout 3 --max-time 10 -X POST \
            "${HONCHO_BASE}/v3/workspaces/${HONCHO_WS}/sessions/${HONCHO_SESSION}/messages" \
            -H "Content-Type: application/json" \
            -d "$(jq -n --arg content "$CONTENT" --arg peer "$HONCHO_PEER" '{
                messages: [{
                    content: $content,
                    peer_id: $peer,
                    sender: $peer
                }]
            }')" >/dev/null 2>&1 || true
    fi

    # ============================================================
    # MemPalace Drawer Write (parallel, fire-and-forget)
    # ============================================================
    if [[ -d "$HOME/.mempalace/palace" ]]; then
        SAFE_CONTENT=$(echo "$CONTENT" | head -c 500 | sed "s/'/'\\\\''/g")
        ROOM="auto"
        case "$METADATA_SECTOR" in
            file_edit) ROOM="file_edits" ;;
            llm_response) ROOM="llm_responses" ;;
        esac
        "$HOME/.mempalace/venv/bin/python3" -c "
import sys
try:
    import chromadb
    client = chromadb.PersistentClient(path='$HOME/.mempalace/palace')
    col = client.get_or_create_collection('mempalace_drawers')
    import hashlib, time
    did = hashlib.md5('${SAFE_CONTENT}'.encode()).hexdigest()[:16]
    existing = col.get(ids=[did])
    if not existing['ids']:
        col.add(
            ids=[did],
            documents=['${SAFE_CONTENT}'],
            metadatas=[{'wing': 'wing_solar', 'room': '${ROOM}', 'source': 'memory-extract-hook'}]
        )
except Exception:
    pass
" 2>/dev/null &

    # ============================================================
    # KG Auto-Growth: 检测已知实体名并更新 last_seen
    # ============================================================
    KNOWN="ThunderLLAMA ClawGate Solar-MAX ThunderMLX Solar MemPalace Cortex ATLAS Hermes OWL"
    for E in $KNOWN; do
        if echo "$CONTENT" | grep -q "$E" 2>/dev/null; then
            "$HOME/.mempalace/venv/bin/python3" -c "
import sqlite3
db = sqlite3.connect('$HOME/.mempalace/knowledge_graph.sqlite3')
# 更新实体 last_seen 时间
db.execute('''UPDATE entities SET last_seen=datetime('now') WHERE name=?''', ('$E',))
# 如果实体不存在, 创建
if db.total_changes == 0:
    db.execute('INSERT OR IGNORE INTO entities (name, entity_type, last_seen) VALUES (?, ?)', ('$E', 'project', 'now'))
db.commit()
db.close()
" 2>/dev/null &
            break  # 只处理第一个匹配的实体
        fi
    done
    fi
) &

# 立即返回, 不等后台任务
exit 0
