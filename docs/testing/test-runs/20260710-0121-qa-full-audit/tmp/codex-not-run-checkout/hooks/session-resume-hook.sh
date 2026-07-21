#!/bin/bash
# Solar Session Resume Hook
# source="resume" 时注入恢复上下文，source="new" 时静默退出
# 用途: 会话恢复时快速恢复态势，补充 solar-session-start.sh 的全量加载

# 1. 读取 stdin JSON，提取 source 字段 (jq 容错)
INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // "new"' 2>/dev/null)

# 非 resume 直接退出，让现有的 solar-session-start.sh 处理新会话
if [[ "$SOURCE" != *"resume"* ]]; then
    exit 0
fi

STATE_FILE="${SOLAR_STATE_FILE:-$HOME/.solar/STATE.md}"
LOG_FILE="$HOME/.solar/session-state.jsonl"

# 2. 提取最近 3 条 session-state.jsonl 事件
RECENT_EVENTS=""
if [[ -f "$LOG_FILE" ]]; then
    RECENT_EVENTS=$(tail -3 "$LOG_FILE" 2>/dev/null | while IFS= read -r line; do
        # 用 jq 解析每行 JSONL，提取 event + subject/task/skill + source
        event=$(echo "$line" | jq -r '.event // empty' 2>/dev/null)
        [[ -z "$event" ]] && continue

        subject=$(echo "$line" | jq -r '.subject // .task // .skill // .description // empty' 2>/dev/null)
        source=$(echo "$line" | jq -r '.source // empty' 2>/dev/null)

        desc="${subject:-$event}"
        label="$desc"
        [[ -n "$source" && "$source" != "solar" ]] && label="$desc ($source)"
        echo "  - [$event] $label"
    done)
fi

# 3. 提取 STATE.md 中 In-Progress 段落的 ⏳ 行
IN_PROGRESS_TASKS=""
if [[ -f "$STATE_FILE" ]]; then
    IN_PROGRESS_TASKS=$(awk '
        /^## In-Progress/ { in_section=1; next }
        /^## / && in_section { exit }
        in_section && /⏳/ {
            # 清理: 去除 "- ⏳ " 前缀、Markdown ** 加粗，截断到 80 字符
            line = $0
            gsub(/^[[:space:]]*-*[[:space:]]*⏳[[:space:]]*/, "", line)
            gsub(/\*\*/, "", line)
            gsub(/[[:space:]]*$/, "", line)
            if (length(line) > 80) line = substr(line, 1, 77) "..."
            tasks[tasks_count++] = line
        }
        END {
            if (tasks_count > 0) {
                for (i=0; i<tasks_count; i++) {
                    printf "  - %s\n", tasks[i]
                }
            }
        }
    ' "$STATE_FILE" 2>/dev/null)
fi

# 4. 组装恢复上下文
MSG="会话恢复模式。上次会话状态："

if [[ -n "$RECENT_EVENTS" ]]; then
    MSG+="
最近操作:
$RECENT_EVENTS"
fi

if [[ -n "$IN_PROGRESS_TASKS" ]]; then
    MSG+="
进行中任务:
$IN_PROGRESS_TASKS"
fi

MSG+="
建议: 读取 ~/.solar/STATE.md 恢复完整态势"

# 5. JSON 安全转义 (换行 -> \\n, 引号 -> \", 反斜杠 -> \\)
ESCAPED=$(printf '%s' "$MSG" | awk '
BEGIN { ORS="" }
{
    gsub(/\\/, "\\\\")
    gsub(/"/, "\\\"")
    gsub(/\n/, "\\n")
    print
}
')

# 6. 输出 (使用 hookSpecificOutput 格式，与 solar-session-start.sh 一致)
jq -n --arg ctx "$ESCAPED" '{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": ("<session-resume>\n" + $ctx + "\n</session-resume>")
  }
}'

exit 0
