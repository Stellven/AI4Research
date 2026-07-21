#!/bin/bash
# Evolve Pre-Tool Advisor — 决策注入
# PreToolUse on mcp__brain-router__complete:
#   在 Solar 调用 brain-router 之前，查 evolve 推荐
#   如果推荐的模型跟 Solar 选的不一样 → 注入建议
#
# 这是闭环最关键的一环：让学习影响决策

set -u

readonly EVOLVE_TS="$HOME/.claude/core/solar-farm/evolve.ts"

if [[ ! -f "$EVOLVE_TS" ]]; then
    exit 0
fi

INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# ── 提取 Solar 选择的模型和 prompt ──────────────────────
SELECTED_MODEL=$(echo "$INPUT" | jq -r '.tool_input.model // ""' 2>/dev/null)
PROMPT=$(echo "$INPUT" | jq -r '.tool_input.prompt // ""' 2>/dev/null)
SYSTEM=$(echo "$INPUT" | jq -r '.tool_input.system // ""' 2>/dev/null)

if [[ -z "$SELECTED_MODEL" ]]; then
    exit 0
fi

# ── 推断 task_type ─────────────────────────────────────
COMBINED="${PROMPT} ${SYSTEM}"
TASK_TYPE="general"
case "$COMBINED" in
    *"代码"*|*"code"*|*"implement"*|*"开发"*|*"编程"*|*"debug"*|*"修复"*|*"bug"*|*"函数"*|*"class"*) TASK_TYPE="coding" ;;
    *"分析"*|*"analysis"*|*"研究"*|*"调研"*|*"对比"*|*"评估"*) TASK_TYPE="analysis" ;;
    *"设计"*|*"architecture"*|*"架构"*|*"方案"*) TASK_TYPE="design" ;;
    *"写"*|*"文章"*|*"文案"*|*"writing"*|*"compose"*|*"报告"*) TASK_TYPE="writing" ;;
    *"review"*|*"审查"*|*"检查代码"*) TASK_TYPE="review" ;;
    *"测试"*|*"test"*|*"qa"*|*"benchmark"*) TASK_TYPE="testing" ;;
    *"research"*|*"explore"*|*"探索"*) TASK_TYPE="research" ;;
esac

# ── 查 evolve 推荐 (3秒超时) ──────────────────────────
RECOMMEND=$(bun "$EVOLVE_TS" select "$TASK_TYPE" --json 2>/dev/null || echo "none")
if [[ "$RECOMMEND" == "none" ]] || [[ -z "$RECOMMEND" ]]; then
    exit 0
fi

RECOMMENDED_MODEL=$(echo "$RECOMMEND" | jq -r '.model // ""' 2>/dev/null)
Q_VALUE=$(echo "$RECOMMEND" | jq -r '.q_value // 0' 2>/dev/null)
SAMPLES=$(echo "$RECOMMEND" | jq -r '.samples // 0' 2>/dev/null)
IS_EXPLORE=$(echo "$RECOMMEND" | jq -r '.is_exploration // false' 2>/dev/null)
REASON=$(echo "$RECOMMEND" | jq -r '.reason // ""' 2>/dev/null)

if [[ -z "$RECOMMENDED_MODEL" ]]; then
    exit 0
fi

# ── 决策注入 ───────────────────────────────────────────
# 记录到 evolve_decisions (Solar 选择了什么 vs evolve 推荐什么)
(
    sqlite3 "$HOME/.solar/solar.db" \
        "INSERT INTO evolve_decisions (task_type, recommended_model, actual_model, q_value, samples, is_exploration, reason, source)
         VALUES ('$TASK_TYPE', '$RECOMMENDED_MODEL', '$SELECTED_MODEL', $Q_VALUE, $SAMPLES, $([ "$IS_EXPLORE" = "true" ] && echo 1 || echo 0), '${REASON:0:100}', 'pre-tool-advisor');" 2>/dev/null
) &

# 只有当 evolve 推荐和 Solar 选择不同时，才注入建议
if [[ "$RECOMMENDED_MODEL" != "$SELECTED_MODEL" ]]; then
    cat <<EOF
<evolve-advise>
Evolve recommends <strong>$RECOMMENDED_MODEL</strong> instead of $SELECTED_MODEL for <strong>$TASK_TYPE</strong> task.
  Q-value: $Q_VALUE | Samples: $SAMPLES | Reason: $REASON
  You chose: $SELECTED_MODEL | Evolve suggests: $RECOMMENDED_MODEL
  Consider switching if evolve has sufficient data (samples >= 5).
</evolve-advise>
EOF
fi

exit 0
