#!/bin/bash
# Solar Session Reflect - SessionEnd Hook
# 会话结束时自动执行反思

# 异步执行反思，不阻塞会话结束
(
    # 执行反思
    RESULT=$(bun ~/.claude/core/memory/session-reflector.ts reflect 2>&1)

    # 记录到日志
    LOG_FILE="$HOME/.solar/logs/reflections.log"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Session ended - Reflection executed" >> "$LOG_FILE"
    echo "$RESULT" >> "$LOG_FILE"
    echo "---" >> "$LOG_FILE"
) &

exit 0
