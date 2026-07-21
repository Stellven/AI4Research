#!/bin/bash
# Solar Harness Status Inject Hook (UserPromptSubmit)
# 目的: 每次用户发消息时, 把 coordinator 最近的 Sprint PASS/FAIL 事件注入到 Claude context
# 解决"规划者静默"问题: Claude agent 只在用户发消息时激活, 不能后台轮询

set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/.solar/harness}"
SEEN_MARKER="${HARNESS_DIR}/.last-seen-by-planner"
[[ -f "$HARNESS_DIR/lib/portable.sh" ]] && . "$HARNESS_DIR/lib/portable.sh"
if ! type solar_file_mtime >/dev/null 2>&1; then
  solar_file_mtime() {
    stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
  }
fi

# 非 solar 项目直接静默退出
[[ -d "$HARNESS_DIR" ]] || { exit 0; }

# 超时保护: 2 秒硬限 (不阻塞用户打字)
timeout_bg() {
  ( sleep 2 && kill -9 $$ 2>/dev/null ) &
  local guard=$!
  trap "kill -9 $guard 2>/dev/null || true" EXIT
}
timeout_bg

# ---- 收集状态 ----
now_epoch=$(date +%s)

# 1) .planner-last-notice (未读判定 = mtime 比 seen_marker 新)
last_notice_content=""
last_notice_unread=false
if [[ -f "${HARNESS_DIR}/.planner-last-notice" ]]; then
  notice_mtime=$(solar_file_mtime "${HARNESS_DIR}/.planner-last-notice" 2>/dev/null || echo 0)
  seen_mtime=0
  [[ -f "$SEEN_MARKER" ]] && seen_mtime=$(solar_file_mtime "$SEEN_MARKER" 2>/dev/null || echo 0)
  if (( notice_mtime > seen_mtime )); then
    last_notice_content=$(cat "${HARNESS_DIR}/.planner-last-notice" 2>/dev/null | head -c 300)
    last_notice_unread=true
  fi
fi

# 2) coordinator.log 最近 60 秒的关键事件 (最多 5 行)
recent_events=""
if [[ -f "${HARNESS_DIR}/.coordinator.log" ]]; then
  cutoff=$((now_epoch - 60))
  # 简单方式: tail -200 然后 grep 关键词
  recent_events=$(tail -200 "${HARNESS_DIR}/.coordinator.log" 2>/dev/null \
    | grep -E '\[notify\] played|finalized:|\[planner-notify\]|Sprint PASSED|Sprint FAIL' \
    | tail -5 \
    | sed 's/\x1b\[[0-9;]*m//g' \
    | head -c 600)
fi

# 3) 未读 inbox count (finalized 文件比 seen_marker 新的数目)
unread_inbox=0
if [[ -f "$SEEN_MARKER" ]]; then
  seen_epoch=$(solar_file_mtime "$SEEN_MARKER" 2>/dev/null || echo 0)
  unread_inbox=$(find "${HARNESS_DIR}/sprints" -name '*.finalized' -newer "$SEEN_MARKER" 2>/dev/null | wc -l | tr -d ' ')
else
  unread_inbox=$(find "${HARNESS_DIR}/sprints" -name '*.finalized' -mmin -60 2>/dev/null | wc -l | tr -d ' ')
fi

# 4) coordinator 活性
coord_pid=""
coord_alive="unknown"
if [[ -f "${HARNESS_DIR}/.coordinator.pid" ]]; then
  coord_pid=$(cat "${HARNESS_DIR}/.coordinator.pid" 2>/dev/null)
  if [[ -n "$coord_pid" ]] && kill -0 "$coord_pid" 2>/dev/null; then
    coord_alive="alive"
  else
    coord_alive="DEAD"
  fi
fi

# ---- 判定是否注入 ----
# 无未读事件 + coordinator 正常 → 静默退出(不污染 context)
if [[ "$last_notice_unread" == "false" ]] && [[ -z "$recent_events" ]] && [[ "$unread_inbox" == "0" ]] && [[ "$coord_alive" == "alive" ]]; then
  # 更新 seen marker 使下次静默
  touch "$SEEN_MARKER" 2>/dev/null || true
  exit 0
fi

# ---- 构造输出 ----
ctx="<solar-harness-status>
"

if [[ "$last_notice_unread" == "true" ]]; then
  ctx+="📬 UNREAD last notice: ${last_notice_content}
"
fi

if [[ -n "$recent_events" ]]; then
  ctx+="recent coordinator events (60s window):
${recent_events}
"
fi

if [[ "$unread_inbox" -gt 0 ]]; then
  ctx+="unread sprint finalized files: ${unread_inbox}
"
fi

if [[ "$coord_alive" == "DEAD" ]]; then
  ctx+="⚠️ coordinator DEAD (pid=${coord_pid}). Watchdog should resurrect but verify.
"
elif [[ "$coord_alive" == "unknown" ]]; then
  ctx+="⚠️ coordinator pidfile missing. Check ~/.solar/harness/.coordinator.pid
"
else
  ctx+="coordinator: alive (pid=${coord_pid})
"
fi

ctx+="(If unread events shown: report them to 监护人 on first reply.)
</solar-harness-status>"

# 更新 seen marker (下次这些事件不重复注入)
touch "$SEEN_MARKER" 2>/dev/null || true

# 输出 JSON: additionalContext 注入到 Claude 的 prompt context
python3 -c "
import json, sys
ctx = sys.stdin.read()
print(json.dumps({
  'hookSpecificOutput': {
    'hookEventName': 'UserPromptSubmit',
    'additionalContext': ctx
  }
}))
" <<< "$ctx"

exit 0
