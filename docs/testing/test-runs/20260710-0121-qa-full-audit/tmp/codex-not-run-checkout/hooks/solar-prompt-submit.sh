#!/bin/bash
# Solar Flow Engine - UserPromptSubmit Hook
# 用户提交时注入当前阶段和 Agent 信息

STATE_FILE="$PWD/.solar/flow-state.json"
INPUT=$(cat)

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
        "Docs") echo "📖" ;;
        "Ops") echo "⚙️" ;;
        "PM") echo "📊" ;;
        *) echo "🤖" ;;
    esac
}

EMOJI=$(get_emoji "$AGENT")

# 构建提醒信息
if [[ "$ANNOUNCED" == "false" ]]; then
    MESSAGE="【Solar】阶段: $PHASE | Agent: $EMOJI $AGENT\\n\\n"
    MESSAGE+="⚠️ 请先输出 Agent 宣告框:\\n"
    MESSAGE+="┌─ $EMOJI $AGENT ────────────────────────────────┐\\n"
    MESSAGE+="│ Task: [任务目标]                               │\\n"
    MESSAGE+="│ Plan:                                         │\\n"
    MESSAGE+="│   1. [步骤1]                                  │\\n"
    MESSAGE+="│   2. [步骤2]                                  │\\n"
    MESSAGE+="└─────────────────────────────────────────────────┘"
else
    MESSAGE="【Solar】$PHASE | $EMOJI $AGENT"
fi

cat << EOF
{
  "continue": true,
  "systemMessage": "$MESSAGE"
}
EOF
