#!/bin/bash
# Solar User Profile Injector
# SessionStart hook: 注入用户画像到会话上下文
#
# 读取 ~/.solar/user-profile.json，格式化为简短提示注入
# 让 Solar 了解用户偏好，提供更个性化的服务
#
# @module solar-farm/user-profile-inject

set -u

readonly PROFILE_FILE="$HOME/.solar/user-profile.json"

# 消耗 stdin
cat > /dev/null 2>&1 || true

# 如果 profile 不存在，静默退出
if [[ ! -f "$PROFILE_FILE" ]]; then
    exit 0
fi

# 用 jq 提取关键字段 (比 awk 解析 JSON 可靠)
if ! command -v jq &>/dev/null; then
    # jq 不可用，静默退出
    exit 0
fi

STYLE=$(jq -r '.communicationStyle // "balanced"' "$PROFILE_FILE" 2>/dev/null)
FORMATS=$(jq -r '.preferredFormats[]?' "$PROFILE_FILE" 2>/dev/null | tr '\n' ',' | sed 's/,$//')
TOOLS=$(jq -r '.frequentTools[]?' "$PROFILE_FILE" 2>/dev/null | head -3 | tr '\n' ',' | sed 's/,$//')
TOPICS=$(jq -r '.frequentTopics[]?' "$PROFILE_FILE" 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//')
UPDATED=$(jq -r '.lastUpdated // "unknown"' "$PROFILE_FILE" 2>/dev/null)

# 构建简短注入 (< 300 字符)
OUTPUT="## 用户画像 (auto-detected)
风格: ${STYLE} | 格式偏好: ${FORMATS}
常用工具: ${TOOLS} | 关注话题: ${TOPICS}
(更新: ${UPDATED})"

# 风格映射提示
case "$STYLE" in
    concise)  OUTPUT+="
提示: 用户偏好简洁回复，避免冗余。" ;;
    detailed) OUTPUT+="
提示: 用户偏好详细分析，提供完整上下文。" ;;
    *)        ;;
esac

# 检查 TVS 偏好
if echo "$FORMATS" | grep -q "tvs"; then
    OUTPUT+="
数据展示使用 TVS 渲染 (ASCII卡片/进度条)。"
fi

echo "$OUTPUT"
exit 0
