#!/bin/bash
# Evolve Auto-Record Hook — 全量交互追踪
# PostToolUse: 追踪所有模型调用入口
#   - brain-router → 外部模型 (deepseek/glm/gemini/gpt)
#   - Task → Claude 子代理 (opus/sonnet/haiku + 牛马子代理)
#   - Skill → 技能调用
#
# 异步写入，不阻塞主流程 (< 5ms overhead)

set -u

readonly DB_FILE="$HOME/.solar/solar.db"
readonly EVOLVE_TS="$HOME/.claude/core/solar-farm/evolve.ts"

# ── 辅助函数 (必须在 exit 之前) ─────────────────────────
infer_task() {
    local text="$1"
    case "$text" in
        *"代码"*|*"code"*|*"implement"*|*"开发"*|*"编程"*|*"debug"*|*"修复"*|*"bug"*|*"函数"*|*"class"*)
            echo "coding" ;;
        *"分析"*|*"analysis"*|*"研究"*|*"调研"*|*"对比"*|*"评估"*)
            echo "analysis" ;;
        *"设计"*|*"architecture"*|*"架构"*|*"方案"*)
            echo "design" ;;
        *"写"*|*"文章"*|*"文案"*|*"writing"*|*"compose"*|*"报告"*|*"文档"*)
            echo "writing" ;;
        *"review"*|*"审查"*|*"检查代码"*)
            echo "review" ;;
        *"测试"*|*"test"*|*"qa"*|*"benchmark"*)
            echo "testing" ;;
        *"research"*|*"explore"*|*"探索"*)
            echo "research" ;;
        *)
            echo "general" ;;
    esac
}

# ── 快速预检 ─────────────────────────────────────────────
if [[ ! -f "$DB_FILE" ]] || [[ ! -f "$EVOLVE_TS" ]]; then
    exit 0
fi

INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# ── 提取 tool_name ───────────────────────────────────────
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // .name // ""' 2>/dev/null)

# ── 分类处理 ─────────────────────────────────────────────

case "$TOOL_NAME" in
    mcp__brain-router__complete)
        MODEL=$(echo "$INPUT" | jq -r '.tool_input.model // ""' 2>/dev/null)
        [[ -z "$MODEL" ]] && exit 0

        OUTPUT=$(echo "$INPUT" | jq -r '.tool_output // ""' 2>/dev/null)
        PROMPT=$(echo "$INPUT" | jq -r '.tool_input.prompt // ""' 2>/dev/null)
        SYSTEM=$(echo "$INPUT" | jq -r '.tool_input.system // ""' 2>/dev/null)

        if echo "$OUTPUT" | jq -e '.error' >/dev/null 2>&1; then
            OUTCOME="fail"
        else
            OUTCOME="pass"
        fi

        COMBINED="${PROMPT} ${SYSTEM}"
        TASK_TYPE=$(infer_task "$COMBINED")

        (
            bun "$EVOLVE_TS" record \
                --model "$MODEL" \
                --task "$TASK_TYPE" \
                --outcome "$OUTCOME" \
                --caller brain-router \
                --interaction brain-router \
                --summary "auto:${TOOL_NAME}" \
            2>/dev/null
        ) &
        ;;

    Task)
        SUBAGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // "unknown"' 2>/dev/null)
        MODEL=$(echo "$INPUT" | jq -r '.tool_input.model // "default"' 2>/dev/null)
        PROMPT=$(echo "$INPUT" | jq -r '.tool_input.prompt // ""' 2>/dev/null)
        DESCRIPTION=$(echo "$INPUT" | jq -r '.tool_input.description // ""' 2>/dev/null)

        OUTPUT=$(echo "$INPUT" | jq -r '.tool_output // ""' 2>/dev/null)
        if echo "$OUTPUT" | grep -qiE "error|fail|timeout"; then
            OUTCOME="fail"
        else
            OUTCOME="pass"
        fi

        COMBINED="${PROMPT} ${DESCRIPTION}"
        TASK_TYPE=$(infer_task "$COMBINED")

        MODEL_ID="${MODEL}"
        if [[ -z "$MODEL_ID" ]] || [[ "$MODEL_ID" == "default" ]]; then
            MODEL_ID="claude-${SUBAGENT_TYPE}"
        fi

        (
            bun "$EVOLVE_TS" record \
                --model "$MODEL_ID" \
                --task "$TASK_TYPE" \
                --outcome "$OUTCOME" \
                --caller claude-task \
                --agent "$SUBAGENT_TYPE" \
                --interaction task-subagent \
                --summary "auto:${TOOL_NAME}:${SUBAGENT_TYPE}" \
            2>/dev/null
        ) &
        ;;

    Skill)
        SKILL_NAME=$(echo "$INPUT" | jq -r '.tool_input.skill // .tool_input.name // "unknown"' 2>/dev/null)
        SKILL_ARGS=$(echo "$INPUT" | jq -r '.tool_input.args // ""' 2>/dev/null)

        MODEL_ID="skill:${SKILL_NAME}"

        OUTPUT=$(echo "$INPUT" | jq -r '.tool_output // ""' 2>/dev/null)
        if echo "$OUTPUT" | grep -qiE "error|fail|timeout"; then
            OUTCOME="fail"
        else
            OUTCOME="pass"
        fi

        COMBINED="${SKILL_NAME} ${SKILL_ARGS}"
        TASK_TYPE=$(infer_task "$COMBINED")

        (
            bun "$EVOLVE_TS" record \
                --model "$MODEL_ID" \
                --task "$TASK_TYPE" \
                --outcome "$OUTCOME" \
                --caller skill \
                --agent "$SKILL_NAME" \
                --interaction skill \
                --summary "auto:${TOOL_NAME}:${SKILL_NAME}" \
            2>/dev/null
        ) &
        ;;
esac

exit 0
