#!/bin/bash
# SMA Session Logger Hook
# Hook 类型: PostToolUse
#
# 功能:
# 1. 每次工具使用时记录到 session-state.jsonl
# 2. 每 100 次工具使用时触发 lifecycle-manager 老化评分检查 (非阻塞, 5秒超时)

set -euo pipefail

# 配置
SESSION_LOG="$HOME/.solar/session-state.jsonl"
LIFECYCLE_MANAGER="$HOME/.claude/core/solar-farm/lifecycle-manager.ts"
TOOL_COUNT_FILE="$HOME/.solar/.sma-tool-counter"
TOOL_COUNT_THRESHOLD=100
LIFECYCLE_TIMEOUT=5

# Step 1: 读取 stdin 到变量 (必须先读，因为只能读一次)
STDIN_JSON=$(cat)

# Step 2: 用 jq 提取字段
TOOL_NAME=$(echo "$STDIN_JSON" | jq -r '.tool_name // "unknown"' 2>/dev/null || echo "unknown")
SESSION_ID=$(echo "$STDIN_JSON" | jq -r '.session_id // "unknown"' 2>/dev/null || echo "unknown")

# Step 3: 写入 session-state.jsonl
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "{\"ts\":\"$TS\",\"event\":\"tool_use\",\"tool\":\"$TOOL_NAME\",\"session_id\":\"$SESSION_ID\"}" >> "$SESSION_LOG"

# Step 4: 每 100 次触发 lifecycle-manager 检查
COUNTER=0
if [ -f "$TOOL_COUNT_FILE" ]; then
    COUNTER=$(cat "$TOOL_COUNT_FILE" 2>/dev/null || echo 0)
fi
COUNTER=$((COUNTER + 1))

# 更新计数器
echo "$COUNTER" > "$TOOL_COUNT_FILE"

# 达到阈值时触发检查 (非阻塞)
if [ "$COUNTER" -ge "$TOOL_COUNT_THRESHOLD" ]; then
    # 重置计数器
    echo "0" > "$TOOL_COUNT_FILE"

    # 后台运行 lifecycle-manager status，带超时保护
    (
        if [ -f "$LIFECYCLE_MANAGER" ] && [ -f "$HOME/.solar/solar.db" ]; then
            timeout "$LIFECYCLE_TIMEOUT" bun "$LIFECYCLE_MANAGER" status > /dev/null 2>&1 || true
        fi
    ) &
    # 不等待后台进程，立即退出
fi

exit 0
