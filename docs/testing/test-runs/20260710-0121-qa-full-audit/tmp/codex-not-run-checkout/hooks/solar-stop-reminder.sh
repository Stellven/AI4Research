#!/bin/bash
# Solar Stop Hook — 合规检查 + 通知
# Claude 回复结束前触发
# 检查 STATE.md In-Progress 任务 + OS 通知

source "$(dirname "${BASH_SOURCE[0]}")/hook-logger.sh"
_START_MS=$(hook_time_ms)

STATE_FILE="${SOLAR_STATE_FILE:-$HOME/.solar/STATE.md}"
TASK_COUNT=0

# 1. 检查 STATE.md 中的 In-Progress 任务
if [[ -f "$STATE_FILE" ]]; then
    IN_PROGRESS=$(grep -A20 "## In-Progress" "$STATE_FILE" | grep -v "^--$" | grep -v "^## " | wc -l | tr -d ' ')
    if [[ "$IN_PROGRESS" -gt 0 && "$IN_PROGRESS" -lt 20 ]]; then
        TASK_COUNT=$IN_PROGRESS
    fi
fi

# 2. 构建提醒 JSON
if [[ "$TASK_COUNT" -gt 0 ]]; then
    cat << EOF
{"decision":"approve","systemMessage":"⏸️ 有 $TASK_COUNT 个进行中事项需要关注。检查 STATE.md Progress 和 TaskList 确认是否需要更新状态后再结束。"}
EOF
    # OS 通知
    osascript -e 'display notification "有 '$TASK_COUNT' 个进行中事项" with title "Solar ⏸️" sound name "Glass"' 2>/dev/null &
else
    echo '{"decision":"approve"}'
fi

hook_log "Stop" "solar-stop-reminder" "ok" "$(( $(hook_time_ms) - _START_MS ))" "tasks=$TASK_COUNT"

exit 0
