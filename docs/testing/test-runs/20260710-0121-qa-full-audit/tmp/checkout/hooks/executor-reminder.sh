#!/bin/bash
# Executor Reminder — 条件触发版
# UserPromptSubmit hook: 追加提醒让 Claude 记得输出 <Executor> 标签
# 前 3 轮无条件触发，之后仅检测到技术任务关键词时触发

source "$HOME/.claude/hooks/hook-logger.sh"
_START_MS=$(hook_time_ms)

INPUT=$(cat)
USER_PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // empty' 2>/dev/null)

# 计数器
COUNT_FILE="$HOME/.solar/.prompt-count"
COUNT=0
if [[ -f "$COUNT_FILE" ]]; then
    COUNT=$(cat "$COUNT_FILE" 2>/dev/null)
fi
echo $((COUNT + 1)) > "$COUNT_FILE"

# 前 3 轮 → 触发
if [[ $COUNT -le 3 ]]; then
    echo "<Executor>self</Executor>"
    hook_log "UserPromptSubmit" "executor-reminder" "ok" "$(( $(hook_time_ms) - _START_MS ))" "triggered=yes,count=$COUNT"
    exit 0
fi

# 关键词检测 → 触发
if echo "$USER_PROMPT" | grep -qiE "分析|代码|实现|开发|优化|调试|测试|研究|编码|coding|implement|develop|debug"; then
    echo "<Executor>self</Executor>  (检测到技术任务 — 确认你已考虑委派给牛马)"
    hook_log "UserPromptSubmit" "executor-reminder" "ok" "$(( $(hook_time_ms) - _START_MS ))" "triggered=yes,count=$COUNT"
    exit 0
fi

hook_log "UserPromptSubmit" "executor-reminder" "skip" "$(( $(hook_time_ms) - _START_MS ))" "triggered=no,count=$COUNT"

exit 0
