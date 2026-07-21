#!/bin/bash
# Solar SubagentStart Tracker
# SubagentStart hook: 记录子代理启动事件到 session 日志
# 触发: SubagentStart (Agent tool 启动子代理时)
# 性能: <10ms (纯 bash + 单次 jq)

set -u

# ── 常量 ──────────────────────────────────────────────────
readonly SOLAR_DIR="$HOME/.solar"
readonly LOG_FILE="$SOLAR_DIR/session-state.jsonl"
readonly SESSION_ID_FILE="$SOLAR_DIR/.session-id"
readonly SUBAGENT_STATE_FILE="/tmp/solar_active_subagent"
readonly LOG_RETENTION_DAYS=7

# ── 确保 .solar 目录存在 ────────────────────────────────
if [[ ! -d "$SOLAR_DIR" ]]; then
    mkdir -p "$SOLAR_DIR" 2>/dev/null || exit 0
fi

# ── Session ID 管理 (跨调用持久化) ─────────────────────
if [[ -f "$SESSION_ID_FILE" ]]; then
    SESSION_ID=$(cat "$SESSION_ID_FILE" 2>/dev/null)
    if [[ -z "$SESSION_ID" ]]; then
        SESSION_ID="$(date +%s)_$$"
        echo "$SESSION_ID" > "$SESSION_ID_FILE"
    fi
else
    SESSION_ID="$(date +%s)_$$"
    echo "$SESSION_ID" > "$SESSION_ID_FILE"
fi

# ── 读取 stdin (一次性) ──────────────────────────────────
INPUT=$(cat)

# ── 生成时间戳和 subagent_id ─────────────────────────────
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
START_S=$(date +%s)
SUBAGENT_ID="${TS}_$$"

# ── 提取字段 (单次 jq 调用，容错处理) ─────────────────────
EXTRACTED=$(echo "$INPUT" | jq -r '
    (.subagent_type // .agent_type // .type // "unknown") + "\t" +
    (.description // .desc // .task // "unknown") + "\t" +
    (.tool_input.subagent_type // .tool_input.type // "")
' 2>/dev/null)

# 解析 jq 输出 (tab 分隔)
AGENT_TYPE=$(echo "$EXTRACTED" | cut -f1)
DESCRIPTION=$(echo "$EXTRACTED" | cut -f2)

# 验证关键字段
if [[ -z "$AGENT_TYPE" || "$AGENT_TYPE" == "null" || "$AGENT_TYPE" == "unknown" ]]; then
    # 连 type 也提取不到，静默退出
    exit 0
fi

if [[ -z "$DESCRIPTION" || "$DESCRIPTION" == "null" ]]; then
    DESCRIPTION="unnamed"
fi

# ── 追加到 JSONL 日志 ───────────────────────────────────
printf '{"ts":"%s","event":"subagent_started","agent_type":"%s","description":"%s","subagent_id":"%s","session_id":"%s"}\n' \
    "$TS" "$AGENT_TYPE" "$DESCRIPTION" "$SUBAGENT_ID" "$SESSION_ID" \
    >> "$LOG_FILE" 2>/dev/null

# ── 将 subagent_id + 启动时间写入临时文件 (供 Stop hook 读取) ──
printf '%s\t%s' "$SUBAGENT_ID" "$START_S" > "$SUBAGENT_STATE_FILE" 2>/dev/null

# ── 清理过期日志 (每 100 次调用检查一次) ────────────────
COUNTER_FILE="/tmp/solar_subagent_start_cleanup_counter"
if [[ -f "$COUNTER_FILE" ]]; then
    COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo "0")
    COUNT=$((COUNT + 1))
else
    COUNT=1
fi
echo "$COUNT" > "$COUNTER_FILE"

if [[ $((COUNT % 100)) -eq 0 && -f "$LOG_FILE" ]]; then
    (
        CUTOFF=$(date -u -v-"${LOG_RETENTION_DAYS}"d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)
        if [[ -n "$CUTOFF" && "$(uname)" == "Darwin" ]]; then
            TEMP=$(mktemp)
            while IFS= read -r line; do
                LINE_TS=$(echo "$line" | jq -r '.ts // ""' 2>/dev/null)
                if [[ "$LINE_TS" > "$CUTOFF" || "$LINE_TS" < "2000-01-01" ]]; then
                    echo "$line"
                fi
            done < "$LOG_FILE" > "$TEMP"
            mv "$TEMP" "$LOG_FILE"
        fi
    ) &
fi

exit 0
