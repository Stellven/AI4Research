#!/bin/bash
# STATE.md + context.json 强制注入 Hook
# Phase 1: 状态强制注入机制
# Phase 2: Master Brain 身份注入 (2026-02-10)

source "$HOME/.claude/hooks/hook-logger.sh"
_START_MS=$(hook_time_ms)
#
# 核心原理（专家共识）：
# 1. 探索派建议: 利用 Recency Bias，注入到 Prompt 末尾
# 2. 稳健派建议: 作为 <system_state> 结构化注入
# 3. 审判官建议: 外部强制，不依赖 LLM "记得读"
#
# 此 Hook 在 SessionStart 列表最后执行，确保状态信息获得最高注意力权重

# ========== Phase 2: Master Brain 身份注入 ==========
CONTEXT_FILE="$HOME/.solar/context.json"

if [ -f "$CONTEXT_FILE" ]; then
    # 使用jq提取Master Brain身份信息
    MASTER_IDENTITY=$(jq -r '.MasterContextObject.system_identity.role' "$CONTEXT_FILE" 2>/dev/null)

    # 如果成功提取到Master Brain身份，则输出身份提醒
    if [ "$MASTER_IDENTITY" = "Master Brain" ]; then
        echo "╔═══════════════════════════════════════════════════════════════════════════╗"
        echo "║  🧠 MASTER BRAIN 身份注入                                                 ║"
        echo "╠═══════════════════════════════════════════════════════════════════════════╣"
        echo "║  身份: Master Brain                                                       ║"
        echo "║  协议: solar-protocol.md                                                  ║"
        echo "║  铁律: 只编排不执行 - 任务必须委派给牛马                                  ║"
        echo "╚═══════════════════════════════════════════════════════════════════════════╝"
        echo ""
    fi
fi

# ========== Phase 1: STATE.md 注入 ==========
STATE_FILE="$HOME/.solar/STATE.md"

# 如果 STATE.md 不存在，静默退出
if [[ ! -f "$STATE_FILE" ]]; then
    exit 0
fi

# 读取 STATE.md 内容
STATE_CONTENT=$(cat "$STATE_FILE")

# 提取关键部分
MISSION=$(grep -A5 "^# Mission" "$STATE_FILE" | tail -n +2 | head -3)
CONSTRAINTS=$(grep -A10 "^# Constraints" "$STATE_FILE" | tail -n +2 | head -6)
CURRENT_PLAN=$(grep -A10 "^# Current Plan" "$STATE_FILE" | tail -n +2 | head -8)
PROGRESS=$(grep -A10 "^# Progress" "$STATE_FILE" | tail -n +2 | head -6)
NEXT_ACTIONS=$(grep -A15 "^# Next Actions" "$STATE_FILE" | tail -n +2 | head -10)

# 检查是否有有效内容
if [[ -z "$MISSION" && -z "$PROGRESS" && -z "$NEXT_ACTIONS" ]]; then
    exit 0
fi

# 构建注入内容（使用专家建议的格式）
cat << 'HEADER'

╔═══════════════════════════════════════════════════════════════════════════╗
║  🧠 STATE.MD 强制注入 (Recency Bias - 此内容应获得最高注意力权重)         ║
╠═══════════════════════════════════════════════════════════════════════════╣
HEADER

echo "║"
echo "║  【Mission - 当前最高目标】"
echo "$MISSION" | while read -r line; do
    [[ -n "$line" ]] && echo "║  $line"
done
echo "║"

if [[ -n "$CONSTRAINTS" ]]; then
    echo "║  【Constraints - 不可破坏的约束】"
    echo "$CONSTRAINTS" | while read -r line; do
        [[ -n "$line" ]] && echo "║  $line"
    done
    echo "║"
fi

if [[ -n "$CURRENT_PLAN" ]]; then
    echo "║  【Current Plan - Top 5 优先任务】"
    echo "$CURRENT_PLAN" | while read -r line; do
        [[ -n "$line" ]] && echo "║  $line"
    done
    echo "║"
fi

if [[ -n "$PROGRESS" ]]; then
    echo "║  【Progress - 当前进度】"
    echo "$PROGRESS" | while read -r line; do
        [[ -n "$line" ]] && echo "║  $line"
    done
    echo "║"
fi

if [[ -n "$NEXT_ACTIONS" ]]; then
    echo "║  【Next Actions - 立即执行事项】"
    echo "$NEXT_ACTIONS" | while read -r line; do
        [[ -n "$line" ]] && echo "║  $line"
    done
    echo "║"
fi

cat << 'FOOTER'
╠═══════════════════════════════════════════════════════════════════════════╣
║  ⚠️  此状态来自 ~/.solar/STATE.md                                       ║
║  ⚠️  如果上下文压缩/会话重启，必须从此恢复状态                           ║
║  ⚠️  执行任务时优先用牛马 (mcp__brain-router__complete)                  ║
╚═══════════════════════════════════════════════════════════════════════════╝

FOOTER

_END_MS=$(hook_time_ms)
hook_log "SessionStart" "state-inject" "ok" "$(($_END_MS - $_START_MS))" "STATE.md path=$STATE_FILE"

exit 0
