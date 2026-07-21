#!/bin/bash
# Evolve Subagent Tracker — 子代理完成追踪
# SubagentStop: 子代理完成时记录结果（补充 PostToolUse 的 Task 追踪）
# SubagentStop 提供更精确的 duration 和 success 信息
#
# Hook 输入 (SubagentStop):
#   { agent_type, model, duration_ms, success, ... }

set -u

readonly DB_FILE="$HOME/.solar/solar.db"
readonly EVOLVE_TS="$HOME/.claude/core/solar-farm/evolve.ts"

if [[ ! -f "$DB_FILE" ]] || [[ ! -f "$EVOLVE_TS" ]]; then
    exit 0
fi

INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# ── 提取字段 ─────────────────────────────────────────────
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // .subagent_type // "unknown"' 2>/dev/null)
MODEL=$(echo "$INPUT" | jq -r '.model // "default"' 2>/dev/null)
DURATION=$(echo "$INPUT" | jq -r '.duration_ms // 0' 2>/dev/null)
SUCCESS=$(echo "$INPUT" | jq -r '.success // true' 2>/dev/null)

# 判断 outcome
if [[ "$SUCCESS" == "true" ]]; then
    OUTCOME="pass"
else
    OUTCOME="fail"
fi

# 模型标识
MODEL_ID="${MODEL}"
if [[ -z "$MODEL_ID" ]] || [[ "$MODEL_ID" == "default" ]] || [[ "$MODEL_ID" == "null" ]]; then
    MODEL_ID="claude-${AGENT_TYPE}"
fi

# 推断 task_type — 从 agent_type 推断
TASK_TYPE="general"
case "$AGENT_TYPE" in
    coder|coder:*)       TASK_TYPE="coding" ;;
    tester|testing:*)    TASK_TYPE="testing" ;;
    reviewer|review:*)   TASK_TYPE="review" ;;
    docs|doc:*)          TASK_TYPE="writing" ;;
    researcher|explore:*) TASK_TYPE="research" ;;
    architect:*)         TASK_TYPE="design" ;;
esac

LATENCY_ARG=""
if [[ -n "$DURATION" ]] && [[ "$DURATION" != "0" ]] && [[ "$DURATION" != "null" ]]; then
    LATENCY_ARG="--latency $DURATION"
fi

# ── 异步写入 ─────────────────────────────────────────────
(
    bun "$EVOLVE_TS" record \
        --model "$MODEL_ID" \
        --task "$TASK_TYPE" \
        --outcome "$OUTCOME" \
        --caller claude-task \
        --agent "$AGENT_TYPE" \
        --interaction subagent-stop \
        --summary "auto:subagent-stop:${AGENT_TYPE}" \
        $LATENCY_ARG \
    2>/dev/null
) &

exit 0
