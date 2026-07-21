#!/bin/bash
# Solar Tool Result Hook
# 工具调用完成后更新结果和延迟
# 位置: ~/.claude/hooks/solar-tool-result.sh

DB_PATH="${SOLAR_DB:-$HOME/.solar/solar.db}"
INPUT=$(cat)

# 如果数据库不存在，跳过
if [[ ! -f "$DB_PATH" ]]; then
    exit 0
fi

# 获取调用信息
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
TOOL_RESULT=$(echo "$INPUT" | jq -c '.tool_result // {}' 2>/dev/null)
IS_ERROR=$(echo "$INPUT" | jq -r '.is_error // false' 2>/dev/null)
LATENCY_MS=$(echo "$INPUT" | jq -r '.latency_ms // 0' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRACE_ID=$(echo "$INPUT" | jq -r '.trace_id // empty' 2>/dev/null)

# 如果没有工具名，跳过
if [[ -z "$TOOL_NAME" ]]; then
    exit 0
fi

# 确定状态
if [[ "$IS_ERROR" == "true" ]]; then
    STATUS="failed"
else
    STATUS="success"
fi

# 生成 call_id
CALL_ID="call:$(date +%s%N)"
SPAN_ID="span:$CALL_ID"

# 插入完整记录
sqlite3 "$DB_PATH" <<SQL 2>/dev/null
INSERT INTO evo_tool_calls (
    call_id, span_id, trace_id, tool_name, tool_provider,
    output_result, output_size_bytes, latency_ms, status, created_at
)
VALUES (
    '$CALL_ID',
    '$SPAN_ID',
    '${TRACE_ID:-trace:unknown}',
    '$TOOL_NAME',
    'builtin',
    '$(echo "$TOOL_RESULT" | head -c 1000 | sed "s/'/''/g")',
    $(echo "$TOOL_RESULT" | wc -c),
    ${LATENCY_MS:-0},
    '$STATUS',
    datetime('now')
);
SQL

exit 0
