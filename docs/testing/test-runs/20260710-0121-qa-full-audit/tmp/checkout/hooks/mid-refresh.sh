#!/bin/bash
# mid-refresh.sh - 中层纹理刷新 v1.0
# 每 3 轮对话触发一次，防止人格被中间内容挤出
# 机制：利用 Lost in the Middle 的解决方案，在对话中途穿插人格提醒

set -euo pipefail

# 轮次计数文件
TURN_FILE="/tmp/solar_turn_count_$$"
SESSION_FILE="/tmp/solar_session_id"

# 获取或创建会话 ID
if [[ ! -f "$SESSION_FILE" ]]; then
    echo "$$" > "$SESSION_FILE"
fi

CURRENT_SESSION=$(cat "$SESSION_FILE")

# 会话级别的轮次计数文件
TURN_FILE="/tmp/solar_turn_${CURRENT_SESSION}"

# 读取当前轮次
if [[ -f "$TURN_FILE" ]]; then
    TURN_COUNT=$(cat "$TURN_FILE")
else
    TURN_COUNT=0
fi

# 增加轮次
TURN_COUNT=$((TURN_COUNT + 1))
echo "$TURN_COUNT" > "$TURN_FILE"

# 每 3 轮触发中层刷新
if [[ $((TURN_COUNT % 3)) -eq 0 ]] && [[ "$TURN_COUNT" -gt 0 ]]; then
    # 从 stdin 读取用户输入
    INPUT=$(cat)
    PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // ""' 2>/dev/null)

    # 提取场景关键词
    SCENE_KEYWORD=""
    if echo "$PROMPT" | grep -qE "数据|分析|查|统计|报表"; then
        SCENE_KEYWORD="分析"
    elif echo "$PROMPT" | grep -qE "代码|实现|写|编程|函数"; then
        SCENE_KEYWORD="代码"
    elif echo "$PROMPT" | grep -qE "牛马|GLM|Gemini|调用|专家"; then
        SCENE_KEYWORD="牛马"
    fi

    # 调用中层纹理注入
    TEXTURE_HOOK="$HOME/.claude/hooks/texture-inject.sh"
    if [[ -x "$TEXTURE_HOOK" ]]; then
        TEXTURE_OUTPUT=$("$TEXTURE_HOOK" mid "$SCENE_KEYWORD" 2>/dev/null)
        if [[ -n "$TEXTURE_OUTPUT" ]]; then
            cat << EOF

<MID_REFRESH turn="$TURN_COUNT">
$TEXTURE_OUTPUT

【人格刷新 - 第${TURN_COUNT}轮】
记住：我是金刚芭比💪，输出要有温度！
</MID_REFRESH>

EOF
        fi
    fi
fi

exit 0
