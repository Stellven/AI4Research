#!/bin/bash
# Solar TaskCompleted Hook
# Hook type: TaskCompleted (内置 TaskCreate/TaskUpdate 任务完成时触发)
# 功能: 记录内置任务完成事件到 session 日志，静默记录不打扰 Solar
# 性能: ~5ms (纯 bash + 单次 jq，零 fork 优化)
# 注意: 与 task-completion-tracker.sh 不同 -- 那个追踪 Skill/Task 工具，
#        这个追踪的是内置 TaskCreate 创建的任务 (event: builtin_task_completed)

set -u

# ── 常量 ──────────────────────────────────────────────────
readonly SOLAR_DIR="$HOME/.solar"
readonly LOG_FILE="$SOLAR_DIR/session-state.jsonl"
readonly SESSION_ID_FILE="$SOLAR_DIR/.session-id"

# ── 读取 stdin (一次性) ──────────────────────────────────
INPUT=$(cat)

# ── 空输入检查 ──────────────────────────────────────────
[[ -z "$INPUT" ]] && exit 0

# ── 快速预检: 非 completed/done 直接退出 (纯 bash, <1ms) ──
# 避免非完成事件触发 jq 开销
[[ "$INPUT" != *"completed"* && "$INPUT" != *"done"* ]] && exit 0

# ── 提取字段 (单次 jq，容错处理) ────────────────────────
# TaskCompleted stdin 预期字段: task_id, subject/status
# 用 // 运算符做容错，兼容不同字段名
PARSED=$(echo "$INPUT" | jq -r '
    .task_id // .id // "",
    .subject // .title // .name // .description // "",
    .status // .task_status // ""
' 2>/dev/null) || exit 0

# ── 解析 jq 输出 (零 fork: 用 read 分割) ───────────────
read -r TASK_ID SUBJECT STATUS <<< "$PARSED"

# ── 只处理 completed 状态 ───────────────────────────────
[[ "$STATUS" != "completed" && "$STATUS" != "done" ]] && exit 0

# ── 校验必要字段 ────────────────────────────────────────
[[ -z "$SUBJECT" || "$SUBJECT" == "null" ]] && exit 0

# ── 确保 .solar 目录存在 ────────────────────────────────
[[ ! -d "$SOLAR_DIR" ]] && mkdir -p "$SOLAR_DIR" 2>/dev/null

# ── Session ID (零 fork: 只在文件不存在时 fork date) ───
if [[ -f "$SESSION_ID_FILE" ]]; then
    SESSION_ID=$(<"$SESSION_ID_FILE")
    if [[ -z "$SESSION_ID" ]]; then
        SESSION_ID="$(date +%s)_$$"
        echo "$SESSION_ID" > "$SESSION_ID_FILE"
    fi
else
    SESSION_ID="$(date +%s)_$$"
    echo "$SESSION_ID" > "$SESSION_ID_FILE"
fi

# ── 时间戳 (bash 内建 printf %T，零 fork) ───────────────
TS=$(printf '%(%Y-%m-%dT%H:%M:%SZ)T' -1)

# ── 写入日志 (纯 printf，零 fork) ───────────────────────
if [[ -n "$TASK_ID" && "$TASK_ID" != "null" ]]; then
    printf '{"ts":"%s","event":"builtin_task_completed","task_id":"%s","subject":"%s","session_id":"%s"}\n' \
        "$TS" "$TASK_ID" "$SUBJECT" "$SESSION_ID" >> "$LOG_FILE" 2>/dev/null
else
    printf '{"ts":"%s","event":"builtin_task_completed","subject":"%s","session_id":"%s"}\n' \
        "$TS" "$SUBJECT" "$SESSION_ID" >> "$LOG_FILE" 2>/dev/null
fi

exit 0
