#!/bin/bash
# Design Cortex Reminder — 设计/核心模块修改前 Cortex 知识库检查提醒
# PreToolUse on Edit/Write:
#   检测是否在修改核心模块文件
#   如果是 + 本次 session 还没查过 Cortex → 输出提醒
#   每个 session 只提醒一次 (标记文件机制)

set -u

# ── 常量 ──────────────────────────────────────────────
readonly STATE_LOG="$HOME/.solar/session-state.jsonl"
readonly MARKER_DIR="$HOME/.solar"
readonly DB_PATH="$HOME/.solar/solar.db"

# 核心路径模式 (匹配 file_path 中包含这些字符串)
readonly CORE_PATTERNS=(
    "solar-farm/"
    "atlas/"
    "core/"
    "intent-engine"
    "evolve"
    "plan-search"
    "repair-"
    "complexity-"
    "classifier"
    "strategy"
    "lifecycle"
    "memory-controller"
    "cortex"
)

# ── 快速读取 stdin ───────────────────────────────────
INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# ── 提取字段 ─────────────────────────────────────────
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)

# ── 只处理 Edit 和 Write ─────────────────────────────
case "$TOOL_NAME" in
    Edit|Write) ;;
    *) exit 0 ;;
esac

# 没有 file_path 则跳过
if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# ── 检查是否匹配核心模块路径 ─────────────────────────
IS_CORE=false
for pattern in "${CORE_PATTERNS[@]}"; do
    if [[ "$FILE_PATH" == *"$pattern"* ]]; then
        IS_CORE=true
        break
    fi
done

if [[ "$IS_CORE" == "false" ]]; then
    exit 0
fi

# ── 提取文件名用于提示 ──────────────────────────────
FILENAME=$(basename "$FILE_PATH")

# ── 检查 session 标记 (一个 session 只提醒一次) ──────
# 没有 session_id 时用 "default"
if [[ -z "$SESSION_ID" ]]; then
    SESSION_ID="default"
fi
readonly MARKER_FILE="$MARKER_DIR/.cortex-reminded-$SESSION_ID"

if [[ -f "$MARKER_FILE" ]]; then
    # 已经提醒过，不再重复
    exit 0
fi

# ── 检查最近是否有 cortex_query 事件 ──────────────────
CORTEX_QUERIED=false
if [[ -f "$STATE_LOG" ]]; then
    # 取最近 30 行，检查是否有 cortex_query 相关事件
    RECENT=$(tail -30 "$STATE_LOG" 2>/dev/null)
    if [[ -n "$RECENT" ]]; then
        # 匹配 cortex_query / cortex_search / unified-query 等关键词
        if echo "$RECENT" | jq -r '.event // .task // ""' 2>/dev/null | grep -qiE 'cortex'; then
            CORTEX_QUERIED=true
        fi
        # 也检查 tool_name 中是否有 cortex 相关调用
        if echo "$RECENT" | jq -r '.tool_name // ""' 2>/dev/null | grep -qiE 'cortex|unified-query'; then
            CORTEX_QUERIED=true
        fi
    fi
fi

if [[ "$CORTEX_QUERIED" == "true" ]]; then
    # 已经查过 Cortex，无需提醒
    exit 0
fi

# ── 从 file_path 推断搜索关键词 ──────────────────────
# 取路径中最有意义的片段作为搜索建议
SEARCH_HINT="$FILENAME"
for pattern in "${CORE_PATTERNS[@]}"; do
    if [[ "$FILE_PATH" == *"$pattern"* ]]; then
        # 去掉尾部斜杠和特殊字符
        CLEAN_PATTERN="${pattern%/}"
        CLEAN_PATTERN="${CLEAN_PATTERN%-}"
        CLEAN_PATTERN="${CLEAN_PATTERN%-}"
        if [[ ${#CLEAN_PATTERN} -gt 3 ]]; then
            SEARCH_HINT="$CLEAN_PATTERN"
        fi
        break
    fi
done

# ── 创建标记文件 (防止重复提醒) ──────────────────────
mkdir -p "$MARKER_DIR"
touch "$MARKER_FILE"

# ── 输出提醒 (JSON additionalContext 格式，PreToolUse 必须用此格式) ──
MSG="检测到核心模块修改: ${FILENAME} (${FILE_PATH})。本次 session 尚未查 Cortex 知识库。建议先查: sqlite3 ~/.solar/solar.db \"SELECT title, substr(finding,1,120) FROM cortex_sources WHERE finding LIKE '%${SEARCH_HINT}%' ORDER BY credibility DESC LIMIT 5;\" 查完再改，避免重复造轮子。"

# 用 jq 安全构建 JSON
jq -n \
  --arg msg "$MSG" \
  '{
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "allow",
      "additionalContext": $msg
    }
  }'

exit 0
