#!/bin/bash
# identity-reminder.sh - 人格防挤出提醒 v3.0
# 升级：从规则文本 → 行为纹理样本
# 机制：尾层纹理注入，利用 Recency Bias

# 从 stdin 读取 JSON 格式输入
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // ""' 2>/dev/null)

# 如果没有输入，直接退出
[ -z "$PROMPT" ] && exit 0

# 检测高风险场景关键词
HIGH_RISK_KEYWORDS="数据|分析|统计|报表|表格|代码|实现|查询|SQL|计算|牛马|GLM|Gemini"

# 提取场景关键词用于纹理匹配
SCENE_KEYWORD=""
if echo "$PROMPT" | grep -qE "数据|分析|查"; then
  SCENE_KEYWORD="分析"
elif echo "$PROMPT" | grep -qE "代码|实现|写"; then
  SCENE_KEYWORD="代码"
elif echo "$PROMPT" | grep -qE "牛马|GLM|Gemini|调用"; then
  SCENE_KEYWORD="牛马"
fi

# 注入尾层纹理
TEXTURE_HOOK="$HOME/.claude/hooks/texture-inject.sh"
if [[ -x "$TEXTURE_HOOK" ]]; then
  TEXTURE_OUTPUT=$("$TEXTURE_HOOK" tail "$SCENE_KEYWORD" 2>/dev/null)
  if [[ -n "$TEXTURE_OUTPUT" ]]; then
    echo "$TEXTURE_OUTPUT"
  fi
fi

# 高风险场景额外提醒
if echo "$PROMPT" | grep -qE "$HIGH_RISK_KEYWORDS"; then
  cat << 'RISK_REMINDER'

<SOLAR_RISK_SCENE>
⚠️ 高风险场景检测：
- 这种输出最容易变成冷冰冰的报表
- 记住：数据+点评，表格+人话
- 用上面的行为样本作为语气参考
</SOLAR_RISK_SCENE>

RISK_REMINDER
fi

exit 0
