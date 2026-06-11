#!/bin/bash
# Auto-favorites Extract — PostToolUse hook
# 检测有价值回复自动 INSERT 到 sys_favorites
# 触发条件: box字符架构图 / ≥3列表格 / 铁律/规则定义 / 架构关键词
# 去重: question 字段哈希前缀

set -euo pipefail

LOG="$HOME/.solar/logs/auto-favorites.log"
DB="$HOME/.solar/db/solar.db"

log_err() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [auto-favorites] $1" >> "$LOG" 2>/dev/null || true
}

# 读取 stdin payload
INPUT=$(cat)

# 提取 tool_name 和 tool_response (Claude Code 实际字段名是 tool_response, tool_result 是历史误用)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
# tool_response 可能是 string (旧格式) 或 object (Bash:{output,...} / Read:{content,...} / Write:{filePath,...})
# 多 fallback 提取实际文本: output > text > content > 整个对象 tostring
TOOL_RESULT=$(echo "$INPUT" | jq -r '
  (.tool_response // .tool_result // "") |
  if type == "object" then
    (.output // .text // .content // (. | tojson))
  else
    (. // "")
  end
' 2>/dev/null || echo "")

# 只在有输出内容时检测
if [[ -z "$TOOL_RESULT" ]] || [[ "$TOOL_RESULT" == "null" ]]; then
    exit 0
fi

# 检测条件 (满足任一)
# 注意: grep -c 0 行匹配时 stdout 仍输出 "0" + exit 1, || echo "0" 会拼成 "0\n0" 导致后续 [[ -lt ]] 算术比较失败
# 用 || true 让 exit 1 转 0,保留 grep -c 自身的 stdout (单个数字)
HAS_BOX=$( { echo "$TOOL_RESULT" | grep -cE '[┌└│─┬┴├┤┼]' 2>/dev/null || true; } | head -1)
HAS_TABLE=$( { echo "$TOOL_RESULT" | grep -cE '\|[^|]+\|[^|]+\|[^|]+\|' 2>/dev/null || true; } | head -1)
HAS_KEYWORD=$( { echo "$TOOL_RESULT" | grep -cE '(架构设计|技术方案|铁律定义|规则定义|根因分析|对比分析|专家会审|架构图)' 2>/dev/null || true; } | head -1)
HAS_BOX=${HAS_BOX:-0}
HAS_TABLE=${HAS_TABLE:-0}
HAS_KEYWORD=${HAS_KEYWORD:-0}

# 至少需要: 3行box字符 或 3行表格 或 1个关键词
if [[ $HAS_BOX -lt 3 ]] && [[ $HAS_TABLE -lt 3 ]] && [[ $HAS_KEYWORD -lt 1 ]]; then
    exit 0
fi

# 提取标题 (前80字符, 去掉控制字符)
TITLE=$(echo "$TOOL_RESULT" | tr -d '\000-\037' | head -c 80 | sed 's/^[[:space:]]*//' || echo "auto-captured")

# 去重: 用内容前256字节的 SHA 哈希
CONTENT_HASH=$(echo "$TOOL_RESULT" | head -c 256 | shasum | cut -c1-16 2>/dev/null || echo "$(date +%s)")
QUESTION="auto-${CONTENT_HASH}"

# 检查是否已存在
EXISTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sys_favorites WHERE question='$QUESTION';" 2>/dev/null || echo "0")

if [[ "$EXISTS" -gt 0 ]]; then
    log_err "skip:duplicate hash=$QUESTION"
    exit 0
fi

# 提取 tags
TAGS='["auto-captured"'
if [[ $HAS_BOX -ge 3 ]]; then
    TAGS="${TAGS},\"architecture\""
fi
if [[ $HAS_TABLE -ge 3 ]]; then
    TAGS="${TAGS},\"comparison\""
fi
if [[ $HAS_KEYWORD -ge 1 ]]; then
    TAGS="${TAGS},\"analysis\""
fi
TAGS="${TAGS}]"

# 截取内容 (sqlite3 单引号转义)
CONTENT=$(echo "$TOOL_RESULT" | head -c 4000 | sed "s/'/''/g")

# INSERT
sqlite3 "$DB" "INSERT INTO sys_favorites (title, question, answer, tags, importance, created_at) VALUES ('${TITLE}', '${QUESTION}', '${CONTENT}', '${TAGS}', 7, datetime('now'));" 2>/dev/null

INSERT_EXIT=$?
if [[ $INSERT_EXIT -eq 0 ]]; then
    log_err "ok:inserted title=$(echo "$TITLE" | head -c 40) hash=$QUESTION"
else
    log_err "error:sqlite3_insert_failed exit=$INSERT_EXIT"
fi

exit 0
