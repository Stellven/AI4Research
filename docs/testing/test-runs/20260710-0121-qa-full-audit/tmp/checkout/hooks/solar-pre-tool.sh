#!/bin/bash
# Solar Flow Engine - PreToolUse Hook
# 工具调用前检查权限和宣告状态

STATE_FILE="$PWD/.solar/flow-state.json"
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# 如果没有状态文件，正常放行
if [[ ! -f "$STATE_FILE" ]]; then
    echo '{"continue": true}'
    exit 0
fi

# 检查是否激活
ACTIVE=$(jq -r '.active // false' "$STATE_FILE" 2>/dev/null)
if [[ "$ACTIVE" != "true" ]]; then
    echo '{"continue": true}'
    exit 0
fi

# 读取状态
PHASE=$(jq -r '.flow.current_phase // "P3"' "$STATE_FILE")
AGENT=$(jq -r '.flow.current_agent // "Coder"' "$STATE_FILE")
# 注意：jq 的 // 操作符会把 false 当作 falsy，所以用 tostring
ANNOUNCED=$(jq -r '.agent_announcement.announced | tostring' "$STATE_FILE" 2>/dev/null)
[[ -z "$ANNOUNCED" ]] && ANNOUNCED="false"

# 获取 Agent emoji
get_emoji() {
    case "$1" in
        "Researcher") echo "🔬" ;;
        "Architect") echo "🏗️" ;;
        "Coder") echo "💻" ;;
        "Tester") echo "🧪" ;;
        "Reviewer") echo "👁️" ;;
        *) echo "🤖" ;;
    esac
}

EMOJI=$(get_emoji "$AGENT")

# 检查是否需要宣告 (写操作前必须宣告)
if [[ "$ANNOUNCED" == "false" ]]; then
    if [[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]]; then
        MESSAGE="【Solar 提醒】执行 $TOOL_NAME 前，请先输出 Agent 宣告。\\n"
        MESSAGE+="当前 Agent: $EMOJI $AGENT\\n\\n"
        MESSAGE+="请先输出宣告框，说明 Task 和 Plan。"

        cat << EOF
{
  "continue": true,
  "systemMessage": "$MESSAGE"
}
EOF
        exit 0
    fi
fi

# Agent 工具权限检查
case "$AGENT" in
    "Researcher")
        # Researcher 不能修改代码
        if [[ "$TOOL_NAME" == "Edit" ]]; then
            echo '{"continue": false, "reason": "【Solar 阻止】Researcher 阶段不允许修改代码。请先完成研究，使用 /phase next 进入设计阶段。"}' >&2
            exit 2
        fi
        ;;
    "Architect")
        # Architect 不能执行命令
        if [[ "$TOOL_NAME" == "Bash" ]]; then
            # 允许只读命令
            COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
            if [[ "$COMMAND" != *"ls"* && "$COMMAND" != *"cat"* && "$COMMAND" != *"git status"* && "$COMMAND" != *"git log"* ]]; then
                echo '{"continue": false, "reason": "【Solar 阻止】Architect 阶段只做设计，不执行命令。请使用 /phase next 进入实现阶段。"}' >&2
                exit 2
            fi
        fi
        ;;
esac

echo '{"continue": true}'
