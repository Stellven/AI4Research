#!/bin/bash
# Solar Task Completion Tracker
# PostToolUse hook: 记录 Skill/Task 工具完成事件到 session 日志
# 触发: PostToolUse (处理 Skill + Task tool，其余静默退出)
# 性能: 非匹配事件 <2ms (纯 bash 字符串匹配); Skill/Task 事件 <15ms (单次 jq)

set -u

# ── 常量 ──────────────────────────────────────────────────
readonly SOLAR_DIR="$HOME/.solar"
readonly LOG_FILE="$SOLAR_DIR/session-state.jsonl"
readonly SESSION_ID_FILE="$SOLAR_DIR/.session-id"
readonly LOG_RETENTION_DAYS=7

# gstack 技能列表
readonly GSTACK_SKILLS=(
    "browse" "review" "investigate" "qa" "qa-only" "ship"
    "benchmark" "office-hours" "autoplan" "careful" "guard"
    "freeze" "design-review" "design-consultation"
    "plan-ceo-review" "plan-eng-review" "plan-design-review"
    "retro" "canary" "cso" "codex" "land-and-deploy"
    "document-release" "setup-browser-cookies" "setup-deploy"
    "gstack-upgrade" "unfreeze"
)

# superpowers 技能列表
readonly SUPERPOWERS_SKILLS=(
    "brainstorming" "writing-plans" "executing-plans"
    "test-driven-development" "systematic-debugging"
    "verification-before-completion" "dispatching-parallel-agents"
    "subagent-driven-development" "using-git-worktrees"
    "finishing-a-development-branch" "receiving-code-review"
    "requesting-code-review" "writing-skills"
)

# ── 快速分类函数 ──────────────────────────────────────────
classify_source() {
    local skill="$1"
    local s

    for s in "${GSTACK_SKILLS[@]}"; do
        [[ "$skill" == "$s" ]] && echo "gstack" && return
    done

    for s in "${SUPERPOWERS_SKILLS[@]}"; do
        [[ "$skill" == "$s" ]] && echo "superpowers" && return
    done

    echo "other"
}

# ── 读取 stdin (一次性) ──────────────────────────────────
INPUT=$(cat)

# ── 快速预检: 非 Skill/Task 工具直接退出 (纯 bash, <2ms) ──────
IS_SKILL=false
IS_TASK=false
if [[ "$INPUT" == *"\"tool_name\":\"Skill\""* || "$INPUT" == *"\"tool_name\": \"Skill\""* ]]; then
    IS_SKILL=true
elif [[ "$INPUT" == *"\"tool_name\":\"Task\""* || "$INPUT" == *"\"tool_name\": \"Task\""* ]]; then
    IS_TASK=true
else
    exit 0
fi

# ── 确保 .solar 目录存在 ────────────────────────────────
if [[ ! -d "$SOLAR_DIR" ]]; then
    mkdir -p "$SOLAR_DIR" 2>/dev/null || exit 0
fi

# ── Session ID 管理 (跨调用持久化) ─────────────────────
if [[ -f "$SESSION_ID_FILE" ]]; then
    SESSION_ID=$(cat "$SESSION_ID_FILE" 2>/dev/null)
    # 校验: 如果 session ID 为空或文件损坏，重新生成
    if [[ -z "$SESSION_ID" ]]; then
        SESSION_ID="$(date +%s)_$$"
        echo "$SESSION_ID" > "$SESSION_ID_FILE"
    fi
else
    SESSION_ID="$(date +%s)_$$"
    echo "$SESSION_ID" > "$SESSION_ID_FILE"
fi

# ── 生成 ISO 8601 时间戳 ────────────────────────────────
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [[ "$IS_SKILL" == true ]]; then
    # ── 提取 skill 名称 (单次 jq 调用) ───────────────────────
    SKILL_NAME=$(echo "$INPUT" | jq -r '.tool_input.skill // ""' 2>/dev/null)
    if [[ -z "$SKILL_NAME" || "$SKILL_NAME" == "null" ]]; then
        exit 0
    fi

    # ── 分类 source ──────────────────────────────────────────
    SOURCE=$(classify_source "$SKILL_NAME")

    # ── 追加到 JSONL 日志 ───────────────────────────────────
    printf '{"ts":"%s","event":"skill_completed","skill":"%s","source":"%s","duration_hint":"completed","session_id":"%s"}\n' \
        "$TS" "$SKILL_NAME" "$SOURCE" "$SESSION_ID" \
        >> "$LOG_FILE" 2>/dev/null
elif [[ "$IS_TASK" == true ]]; then
    # ── 提取 Task 工具的 subagent_type 和 description ────────
    TASK_AGENT=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // ""' 2>/dev/null)
    TASK_DESC=$(echo "$INPUT" | jq -r '.tool_input.description // ""' 2>/dev/null)
    if [[ -z "$TASK_DESC" || "$TASK_DESC" == "null" ]]; then
        exit 0
    fi

    # ── 追加到 JSONL 日志 ───────────────────────────────────
    printf '{"ts":"%s","event":"task_completed","task":"%s","agent":"%s","source":"subagent","duration_hint":"completed","session_id":"%s"}\n' \
        "$TS" "$TASK_DESC" "$TASK_AGENT" "$SESSION_ID" \
        >> "$LOG_FILE" 2>/dev/null
fi

# ── 清理过期日志 (每 100 次调用检查一次) ────────────────
COUNTER_FILE="/tmp/solar_tracker_cleanup_counter"
if [[ -f "$COUNTER_FILE" ]]; then
    COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo "0")
    COUNT=$((COUNT + 1))
else
    COUNT=1
fi
echo "$COUNT" > "$COUNTER_FILE"

if [[ $((COUNT % 100)) -eq 0 && -f "$LOG_FILE" ]]; then
    (
        CUTOFF=$(date -u -v-"${LOG_RETENTION_DAYS}"d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null)
        if [[ -n "$CUTOFF" && "$(uname)" == "Darwin" ]]; then
            TEMP=$(mktemp)
            while IFS= read -r line; do
                LINE_TS=$(echo "$line" | jq -r '.ts // ""' 2>/dev/null)
                if [[ "$LINE_TS" > "$CUTOFF" || "$LINE_TS" < "2000-01-01" ]]; then
                    echo "$line"
                fi
            done < "$LOG_FILE" > "$TEMP"
            mv "$TEMP" "$LOG_FILE"
        fi
    ) &
fi

exit 0
