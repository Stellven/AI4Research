#!/bin/bash
# Honcho SessionStart Hook
# 查询 Honcho peer card 并注入到会话上下文
#
# 触发: SessionStart
# 行为:
#   1. 检查 HONCHO_API_KEY 是否设置
#   2. 如果设置，调用 Honcho API 获取 peer card
#   3. 格式化输出 <honcho-profile> 标签
#   4. 如果未设置，静默退出 (优雅降级)
#
# @module solar-farm/honcho-session-start

set -u

# 消耗 stdin
cat > /dev/null 2>&1 || true

# 检查 jq
if ! command -v jq &>/dev/null; then
    exit 0
fi

# 检查 HONCHO_API_KEY (optional for self-hosted)
HONCHO_KEY="${HONCHO_API_KEY:-self-hosted}"

# 配置 - Default to local self-hosted Honcho
HONCHO_BASE="${HONCHO_BASE_URL:-http://localhost:8900}"
WORKSPACE="${HONCHO_WORKSPACE_ID:-solar}"
USER_PEER="user"
AI_PEER="solar"

# 获取 peer card (GET, 最多 3 秒超时)
CARD_RESPONSE=$(curl -s --connect-timeout 3 --max-time 5 \
    -H "Authorization: Bearer $HONCHO_KEY" \
    -H "Content-Type: application/json" \
    "${HONCHO_BASE}/v3/workspaces/${WORKSPACE}/peers/${USER_PEER}/card?target=${AI_PEER}" \
    2>/dev/null) || true

if [[ -z "$CARD_RESPONSE" ]]; then
    exit 0
fi

# 解析 peer card
INSIGHTS=$(echo "$CARD_RESPONSE" | jq -r '.peer_card[]? // empty' 2>/dev/null | head -5)
if [[ -z "$INSIGHTS" ]]; then
    # 也尝试不带 target 的查询
    CARD_RESPONSE=$(curl -s --connect-timeout 3 --max-time 5 \
        -H "Authorization: Bearer $HONCHO_KEY" \
        -H "Content-Type: application/json" \
        "${HONCHO_BASE}/v3/workspaces/${WORKSPACE}/peers/${USER_PEER}/card" \
        2>/dev/null) || true
    INSIGHTS=$(echo "$CARD_RESPONSE" | jq -r '.peer_card[]? // empty' 2>/dev/null | head -5)
fi

if [[ -z "$INSIGHTS" ]]; then
    exit 0
fi

# 格式化输出
FORMATTED=$(echo "$INSIGHTS" | sed 's/^/- /')

echo "<honcho-profile>"
echo "## Honcho Dialectic Profile"
echo "$FORMATTED"
echo "(source: Honcho AI-native memory)"
echo "</honcho-profile>"

exit 0
