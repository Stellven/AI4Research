#!/bin/bash
# Solar Memory - Experience Reminder Hook
# 在首次 Write/Edit 前提醒查询经验

STATE_FILE="$HOME/.solar/experience-checked"
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# 只检查 Write 和 Edit
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    echo '{"continue": true}'
    exit 0
fi

# 检查当前会话是否已经提醒过
SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%Y%m%d)}"
CHECK_FILE="$STATE_FILE.$SESSION_ID"

if [[ -f "$CHECK_FILE" ]]; then
    # 已经提醒过，直接放行
    echo '{"continue": true}'
    exit 0
fi

# 标记已提醒
mkdir -p "$(dirname "$STATE_FILE")"
touch "$CHECK_FILE"

# 获取文件路径，用于生成上下文
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
CONTEXT=$(basename "$FILE_PATH" 2>/dev/null || echo "unknown")

# 查询经验（快速，只取关键提醒）
EXPERIENCE=$(bun ~/.claude/core/memory/memory-hook.ts query "$CONTEXT" 2>/dev/null | grep -E "^(📋|⚠️)" | head -3)

if [[ -n "$EXPERIENCE" ]]; then
    MESSAGE="【记忆提醒】开始编码前请注意:\\n"
    MESSAGE+="$EXPERIENCE\\n"
    MESSAGE+="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    cat << EOF
{
  "continue": true,
  "systemMessage": "$MESSAGE"
}
EOF
else
    echo '{"continue": true}'
fi
