#!/bin/bash
# Solar PostToolUseFailure Recorder
# Hook: 记录工具调用失败事件，自动分类失败类别
# 触发: PostToolUseFailure (任何工具调用失败时)
# 性能: 目标 < 30ms (单次 jq 提取+分类+JSONL构建 + sqlite3 写入)

source "$HOME/.claude/hooks/hook-logger.sh"
_START_MS=$(hook_time_ms)

set -u

# ── 常量 ──────────────────────────────────────────────────
readonly SOLAR_DIR="$HOME/.solar"
readonly LOG_FILE="$SOLAR_DIR/session-state.jsonl"
readonly SESSION_ID_FILE="$SOLAR_DIR/.session-id"
readonly DB_FILE="$SOLAR_DIR/solar.db"

# ── 读取 stdin (一次性) ──────────────────────────────────
INPUT=$(cat)

# ── 快速预检: 空 input 直接退出 ──────────────────────────
if [[ -z "$INPUT" ]]; then
    hook_log "PostToolUseFailure" "post-tool-failure-recorder" "skip" "$(( $(hook_time_ms) - _START_MS ))" "empty_input"
    exit 0
fi

# ── 确保 .solar 目录存在 ────────────────────────────────
[[ -d "$SOLAR_DIR" ]] || mkdir -p "$SOLAR_DIR" 2>/dev/null || exit 0

# ── Session ID (跨调用持久化) ───────────────────────────
if [[ -f "$SESSION_ID_FILE" ]]; then
    SESSION_ID=$(cat "$SESSION_ID_FILE" 2>/dev/null)
    if [[ -z "$SESSION_ID" ]]; then
        SESSION_ID="$(date +%s)_$$"
        echo "$SESSION_ID" > "$SESSION_ID_FILE"
    fi
else
    SESSION_ID="$(date +%s)_$$"
    echo "$SESSION_ID" > "$SESSION_ID_FILE"
fi

# ── 时间戳 ──────────────────────────────────────────────
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── 单次 jq: 提取 + 分类 + 构建 JSONL (零额外子进程) ───
# 输出格式: tool_name<TAB>error_msg<TAB>category<TAB>jsonl_line
# 如果提取失败 (空 tool 或 error)，输出空行
RESULT=$(echo "$INPUT" | jq -r --arg ts "$TS" --arg sid "$SESSION_ID" '
  . as $orig |
  (($orig.tool_name // $orig.name // "")) | if . == "" then empty else . end |
  . as $tool |
  (($orig.error // $orig.message // $orig.stderr // "")) |
  if . == "" then empty else . end |
  . as $err |
  ($err | ascii_downcase) as $el |
  (if ($el | test("permission|denied|eacces|unauthorized|forbidden")) then "PERMISSION"
   elif ($el | test("enoent|enospc|timeout|out of memory|disk full|no space|oom")) then "RESOURCE"
   elif ($el | test("network|econnrefused|etimedout|dns|fetch|econnreset|eai|socket")) then "NETWORK"
   elif ($el | test("typeerror|syntaxerror|undefined|null|invalid|cannot read|is not a|expected")) then "LOGIC"
   else "UNKNOWN" end) as $cat |
  ($err[0:200]) as $err_short |
  # 输出: tool<TAB>error<TAB>category<TAB>jsonl
  [$tool, $err, $cat, ({ts:$ts, event:"tool_failure", tool:$tool, category:$cat, error:$err_short, session_id:$sid} | tostring)] | @tsv
' 2>/dev/null)

# 空结果 → 静默退出
if [[ -z "$RESULT" ]]; then
    hook_log "PostToolUseFailure" "post-tool-failure-recorder" "skip" "$(( $(hook_time_ms) - _START_MS ))" "empty_result"
    exit 0
fi

# ── 解析 jq 输出 (内建字符串操作) ───────────────────────
TOOL_NAME="${RESULT%%	*}"
REMAINDER="${RESULT#*	}"
ERROR_MSG="${REMAINDER%%	*}"
REMAINDER="${REMAINDER#*	}"
CATEGORY="${REMAINDER%%	*}"
JSONL_LINE="${REMAINDER#*	}"

# ── 追加到 session-state.jsonl ──────────────────────────
echo "$JSONL_LINE" >> "$LOG_FILE" 2>/dev/null

# ── 写入 sqlite (SQL 转义用 bash 内建) ─────────────────
if [[ -f "$DB_FILE" ]]; then
    SQL_TOOL="${TOOL_NAME//\'/\'\'}"
    SQL_ERROR="${ERROR_MSG:0:500}"
    SQL_ERROR="${SQL_ERROR//\'/\'\'}"
    SQL_SESSION="${SESSION_ID//\'/\'\'}"

    sqlite3 "$DB_FILE" "CREATE TABLE IF NOT EXISTS failure_log (id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT NOT NULL,tool_name TEXT NOT NULL,category TEXT NOT NULL,error TEXT,session_id TEXT);INSERT INTO failure_log (ts,tool_name,category,error,session_id) VALUES ('${TS}','${SQL_TOOL}','${CATEGORY}','${SQL_ERROR}','${SQL_SESSION}');" 2>/dev/null
fi

# ── 输出失败提醒给 Solar ────────────────────────────────
case "$CATEGORY" in
    PERMISSION) SUGGESTION="检查权限或请求监护人授权" ;;
    RESOURCE)   SUGGESTION="检查资源可用性或清理空间" ;;
    NETWORK)    SUGGESTION="检查网络连接或稍后重试" ;;
    LOGIC)      SUGGESTION="检查参数或调用审判官分析" ;;
    *)          SUGGESTION="检查错误信息或切换策略" ;;
esac

ERROR_DISPLAY="${ERROR_MSG:0:100}"

cat <<EOF
<tool-failure>
工具 ${TOOL_NAME} 失败: [${CATEGORY}] ${ERROR_DISPLAY}
建议: ${SUGGESTION}
</tool-failure>
EOF

# OS 通知
osascript -e 'display notification "工具执行失败，请检查" with title "Solar ⚠️" sound name "Basso"' 2>/dev/null &

hook_log "PostToolUseFailure" "post-tool-failure-recorder" "ok" "$(( $(hook_time_ms) - _START_MS ))" "tool=$TOOL_NAME,category=$CATEGORY"

exit 0
