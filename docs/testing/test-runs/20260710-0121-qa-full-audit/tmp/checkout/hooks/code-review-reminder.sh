#!/bin/bash
# Solar Code Review Reminder
# PostToolUse hook: 连续代码修改后提醒 Solar 使用 /review 审查
# 触发: PostToolUse (仅处理 Edit/Write，其余静默退出)
# 性能: 非匹配事件 <2ms (纯 bash case); Edit/Write 事件 <10ms (计数器读写)

set -u

# ── 常量 ──────────────────────────────────────────────────
readonly SOLAR_DIR="$HOME/.solar"
readonly SESSION_ID_FILE="$SOLAR_DIR/.session-id"

# 提醒阈值: 只在连续 Edit/Write 次数 == 这些值时输出
readonly REMIND_AT=(3 6)

# ── 读取 stdin ───────────────────────────────────────────
INPUT=$(cat)

# ── 快速预检: 非 Edit/Write 直接退出 (<2ms) ─────────────
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
case "$TOOL_NAME" in
    Edit|Write) ;;
    *)          exit 0 ;;
esac

# ── 确保 .solar 目录存在 ────────────────────────────────
[[ ! -d "$SOLAR_DIR" ]] && mkdir -p "$SOLAR_DIR" 2>/dev/null

# ── Session ID ──────────────────────────────────────────
SESSION_ID=""
if [[ -f "$SESSION_ID_FILE" ]]; then
    SESSION_ID=$(cat "$SESSION_ID_FILE" 2>/dev/null)
fi
[[ -z "$SESSION_ID" ]] && SESSION_ID="default"

# ── 计数器文件 ──────────────────────────────────────────
readonly COUNTER_FILE="$SOLAR_DIR/.edit-counter-${SESSION_ID}"
# 修改文件列表文件
readonly FILES_FILE="$SOLAR_DIR/.edit-files-${SESSION_ID}"

# ── 检查 skill 完成标记 (由 task-completion-tracker.sh 在 skill 完成时写入) ──
# 标记文件是消耗品: 读取后立即删除，避免重复触发重置
readonly SKILL_MARKER="$SOLAR_DIR/.skill-completed-${SESSION_ID}"
NEED_RESET=false
if [[ -f "$SKILL_MARKER" ]]; then
    NEED_RESET=true
    rm -f "$SKILL_MARKER" 2>/dev/null
    # 同时清空文件列表，因为 skill 完成代表一个阶段结束
    rm -f "$FILES_FILE" 2>/dev/null
fi

# ── 读取当前计数器 ─────────────────────────────────────
if [[ "$NEED_RESET" == true ]]; then
    # 有 skill_completed → 重置计数，当前编辑算第 1 次
    COUNT=1
else
    if [[ -f "$COUNTER_FILE" ]]; then
        COUNT=$(cat "$COUNTER_FILE" 2>/dev/null)
        # 校验: 非数字重置
        [[ "$COUNT" =~ ^[0-9]+$ ]] || COUNT=0
    else
        COUNT=0
    fi
    COUNT=$((COUNT + 1))
fi

# ── 提取被修改的文件路径 ───────────────────────────────
FILE_PATH=""
if [[ "$TOOL_NAME" == "Edit" ]]; then
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
elif [[ "$TOOL_NAME" == "Write" ]]; then
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi

# 追加到文件列表 (只保留最近 10 个)
if [[ -n "$FILE_PATH" ]]; then
    # 提取文件名 (去掉路径)
    FILE_BASE=$(basename "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")
    if [[ -f "$FILES_FILE" ]]; then
        # 保留最近 9 个 + 新增 1 个
        EXISTING=$(tail -9 "$FILES_FILE" 2>/dev/null)
        printf '%s\n%s\n' "$EXISTING" "$FILE_BASE" > "$FILES_FILE"
    else
        echo "$FILE_BASE" > "$FILES_FILE"
    fi
fi

# ── 持久化计数器 ───────────────────────────────────────
echo "$COUNT" > "$COUNTER_FILE"

# ── 判断是否需要提醒 ───────────────────────────────────
SHOULD_REMIND=false
for THRESHOLD in "${REMIND_AT[@]}"; do
    [[ "$COUNT" -eq "$THRESHOLD" ]] && SHOULD_REMIND=true && break
done

if [[ "$SHOULD_REMIND" == false ]]; then
    exit 0
fi

# ── 构建修改文件列表 ───────────────────────────────────
FILE_LIST=""
if [[ -f "$FILES_FILE" ]]; then
    # 去重并取最近 5 个
    FILE_LIST=$(awk '!seen[$0]++' "$FILES_FILE" 2>/dev/null | tail -5 | paste -sd ',' - 2>/dev/null)
fi

# ── 输出提醒 (JSON additionalContext 格式，PostToolUse 必须用此格式) ──
MSG="已连续 ${COUNT} 次代码修改，建议使用 /review 审查质量。修改的文件: ${FILE_LIST:-未知}"

# 用 jq 安全构建 JSON (处理特殊字符)
jq -n \
  --arg msg "$MSG" \
  '{
    "hookSpecificOutput": {
      "hookEventName": "PostToolUse",
      "additionalContext": $msg
    }
  }'

exit 0
