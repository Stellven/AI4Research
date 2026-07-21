#!/bin/bash
# Solar SubagentStop Tracker
# SubagentStop hook: 记录子代理完成事件到 session 日志
# 触发: SubagentStop (Agent tool 子代理完成时)
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

# ── 生成结束时间戳 ──────────────────────────────────────
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
END_S=$(date +%s)

# ── 从 Start hook 临时文件读取启动时间 ─────────────────
DURATION_S=-1
SUBAGENT_ID="unknown"
if [[ -f "$SUBAGENT_STATE_FILE" ]]; then
    START_INFO=$(cat "$SUBAGENT_STATE_FILE" 2>/dev/null)
    SUBAGENT_ID=$(echo "$START_INFO" | cut -f1)
    START_S=$(echo "$START_INFO" | cut -f2)
    # 计算耗时 (秒)
    if [[ -n "$START_S" && "$START_S" != "null" ]]; then
        DURATION_S=$((END_S - START_S))
        # 防止负数 (时钟漂移)
        if [[ $DURATION_S -lt 0 ]]; then
            DURATION_S=0
        fi
    fi
    # 清理临时文件
    rm -f "$SUBAGENT_STATE_FILE" 2>/dev/null
fi

# ── 提取字段 (单次 jq 调用，容错处理) ─────────────────────
EXTRACTED=$(echo "$INPUT" | jq -r '
    (.subagent_type // .agent_type // .type // "unknown") + "\t" +
    (.description // .desc // .task // "unknown") + "\t" +
    ((.exit_code // 0) | tostring)
' 2>/dev/null)

# 解析 jq 输出 (tab 分隔)
AGENT_TYPE=$(echo "$EXTRACTED" | cut -f1)
DESCRIPTION=$(echo "$EXTRACTED" | cut -f2)
EXIT_CODE=$(echo "$EXTRACTED" | cut -f3)

# 验证关键字段
if [[ -z "$AGENT_TYPE" || "$AGENT_TYPE" == "null" || "$AGENT_TYPE" == "unknown" ]]; then
    exit 0
fi

if [[ -z "$DESCRIPTION" || "$DESCRIPTION" == "null" ]]; then
    DESCRIPTION="unnamed"
fi

if [[ -z "$EXIT_CODE" || "$EXIT_CODE" == "null" ]]; then
    EXIT_CODE=0
fi

# ── 判断状态 ────────────────────────────────────────────
if [[ "$EXIT_CODE" == "0" ]]; then
    STATUS="success"
else
    STATUS="failed"
fi

# ── 追加到 JSONL 日志 ───────────────────────────────────
printf '{"ts":"%s","event":"subagent_completed","agent_type":"%s","description":"%s","status":"%s","duration_s":%d,"subagent_id":"%s","session_id":"%s"}\n' \
    "$TS" "$AGENT_TYPE" "$DESCRIPTION" "$STATUS" "$DURATION_S" "$SUBAGENT_ID" "$SESSION_ID" \
    >> "$LOG_FILE" 2>/dev/null

# ── 清理过期日志 (每 100 次调用检查一次) ────────────────
COUNTER_FILE="/tmp/solar_subagent_stop_cleanup_counter"
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
