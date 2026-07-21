#!/bin/bash
# ================================================================
# Solar Harness — Session Event API
#
# Append-only event stream for sprint lifecycle tracking.
# Replaces load_last_state/save_state string comparison with
# structured event slicing.
#
# 用法:
#   session.sh append <sid> <event_json>
#   session.sh get <sid> [--from=N] [--to=M]
#   session.sh tail <sid> N
#
# @module solar-farm/harness/session
# ================================================================
set -eu

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
SPRINTS_DIR="$HARNESS_DIR/sprints"
ARCHIVE_DIR="$SPRINTS_DIR/archive"
[[ -f "$HARNESS_DIR/lib/portable.sh" ]] && . "$HARNESS_DIR/lib/portable.sh"

# --- 检查归档 sprint ---
check_archived() {
  local sid="$1"
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"
  local archived_file="$ARCHIVE_DIR/${sid}.events.jsonl"
  local summary_file="$SPRINTS_DIR/${sid}.summary.md"

  if [[ ! -f "$events_file" ]] && [[ -f "$archived_file" ]]; then
    echo "# archived-sprint: ${sid} 已归档，事件流在 archive/" >&2
    if [[ -f "$summary_file" ]]; then
      echo "# 摘要:" >&2
      head -20 "$summary_file" | sed 's/^/# /' >&2
    fi
    return 0  # archived
  fi
  return 1  # not archived
}

# --- append: 原子追加事件到 events.jsonl ---
# 使用 flock 保证并发安全
cmd_append() {
  local sid="$1"
  local event_json="$2"
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"

  # 验证 JSON 合法性
  if ! echo "$event_json" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    echo "error: invalid JSON" >&2
    return 1
  fi

  # 自动补全 ts 字段 (如果没提供)
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  event_json=$(echo "$event_json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if 'ts' not in d:
    d['ts'] = '${ts}'
if 'sid' not in d:
    d['sid'] = '${sid}'
json.dump(d, sys.stdout, ensure_ascii=False)
" 2>/dev/null)

  # mkdir 原子锁 (macOS/Linux 兼容)
  local lock_dir="${events_file}.lockdir"
  local max_wait=10  # 最多等 10 秒
  local waited=0
  while ! mkdir "$lock_dir" 2>/dev/null; do
    sleep 0.1
    waited=$((waited + 1))
    if [[ $waited -ge $((max_wait * 10)) ]]; then
      # 超时：检查锁是否是旧的 (>30s)
      local lock_age
      lock_age=$(solar_file_mtime "$lock_dir" 2>/dev/null || echo 0)
      local now
      now=$(date +%s)
      if [[ $((now - lock_age)) -gt 30 ]]; then
        rm -rf "$lock_dir"  # 清除旧锁
        continue
      fi
      echo "error: lock timeout" >&2
      return 1
    fi
  done
  # 保证释放锁
  trap "rm -rf '$lock_dir'" EXIT
  echo "$event_json" >> "$events_file"
  rm -rf "$lock_dir"
  trap - EXIT

  if [[ "${SOLAR_SESSION_SH_NO_BRIDGE:-0}" != "1" && -f "$HARNESS_DIR/lib/runtime_bridge.py" ]]; then
    python3 - "$HARNESS_DIR/lib/runtime_bridge.py" "$sid" "$event_json" <<'PY' 2>/dev/null || true
import json
import subprocess
import sys

bridge, sid, raw = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.loads(raw)
payload = d.get("data") if isinstance(d.get("data"), dict) else d.get("payload")
if not isinstance(payload, dict):
    payload = dict(d)
subprocess.run(
    [
        "python3",
        bridge,
        "event",
        sid,
        str(d.get("event") or "session_event"),
        str(d.get("by") or d.get("actor") or "session.sh"),
        json.dumps(payload, ensure_ascii=False),
        "--quiet",
    ],
    check=False,
)
PY
  fi

  echo "ok: appended to ${sid}.events.jsonl"
}

# --- get: 切片读取事件 ---
# --from=N: 从第 N 条开始 (0-indexed, 默认 0)
# --to=M:   到第 M 条结束 (不含, 默认全部)
cmd_get() {
  local sid="$1"
  shift
  local from=0 to=""
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from=*) from="${1#--from=}" ;;
      --to=*)   to="${1#--to=}" ;;
    esac
    shift
  done

  if [[ ! -f "$events_file" ]]; then
    if check_archived "$sid"; then
      echo "[]"
      return 0
    fi
    echo "# legacy-sprint: ${sid} 无事件流 (创建于 events.jsonl 功能之前)" >&2
    echo "[]"
    return 0
  fi

  # 用 python3 做切片 (awk 对 JSON 不可靠)
  python3 -c "
import json, sys
lines = [l.strip() for l in open('${events_file}') if l.strip()]
total = len(lines)
from_idx = min(${from}, total)
to_val = '${to}'
to_idx = min(int(to_val), total) if to_val else total
result = []
for line in lines[from_idx:to_idx]:
    try:
        result.append(json.loads(line))
    except:
        result.append({'raw': line})
print(json.dumps(result, ensure_ascii=False, indent=2))
" 2>/dev/null
}

# --- tail: 读取最后 N 条事件 ---
cmd_tail() {
  local sid="$1"
  local n="${2:-10}"
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"

  if [[ ! -f "$events_file" ]]; then
    if check_archived "$sid"; then
      echo "[]"
      return 0
    fi
    echo "# legacy-sprint: ${sid} 无事件流 (创建于 events.jsonl 功能之前)" >&2
    echo "[]"
    return 0
  fi

  python3 -c "
import json
lines = [l.strip() for l in open('${events_file}') if l.strip()]
n = min(${n}, len(lines))
result = []
for line in lines[-n:]:
    try:
        result.append(json.loads(line))
    except:
        result.append({'raw': line})
print(json.dumps(result, ensure_ascii=False, indent=2))
" 2>/dev/null
}

# --- count: 统计事件数 ---
cmd_count() {
  local sid="$1"
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"

  if [[ ! -f "$events_file" ]]; then
    if check_archived "$sid"; then
      echo "0"
      return 0
    fi
    echo "# legacy-sprint: ${sid} 无事件流 (创建于 events.jsonl 功能之前)" >&2
    echo "0"
    return 0
  fi

  wc -l < "$events_file" | tr -d ' '
}

# --- last: 获取最后一条事件 ---
cmd_last() {
  local sid="$1"
  local events_file="$SPRINTS_DIR/${sid}.events.jsonl"

  if [[ ! -f "$events_file" ]]; then
    if check_archived "$sid"; then
      echo "{}"
      return 0
    fi
    echo "# legacy-sprint: ${sid} 无事件流 (创建于 events.jsonl 功能之前)" >&2
    echo "{}"
    return 0
  fi

  tail -1 "$events_file" | python3 -c "
import json, sys
line = sys.stdin.read().strip()
if line:
    try:
        print(json.dumps(json.loads(line), ensure_ascii=False, indent=2))
    except:
        print(json.dumps({'raw': line}))
else:
    print('{}')
" 2>/dev/null
}

# --- 主入口 ---
case "${1:-}" in
  append)
    [[ -z "${2:-}" ]] && { echo "usage: session.sh append <sid> <event_json>" >&2; exit 1; }
    [[ -z "${3:-}" ]] && { echo "usage: session.sh append <sid> <event_json>" >&2; exit 1; }
    cmd_append "$2" "$3"
    ;;
  get)
    [[ -z "${2:-}" ]] && { echo "usage: session.sh get <sid> [--from=N] [--to=M]" >&2; exit 1; }
    cmd_get "$2" "${@:3}"
    ;;
  tail)
    [[ -z "${2:-}" ]] && { echo "usage: session.sh tail <sid> [N]" >&2; exit 1; }
    cmd_tail "$2" "${3:-10}"
    ;;
  count)
    [[ -z "${2:-}" ]] && { echo "usage: session.sh count <sid>" >&2; exit 1; }
    cmd_count "$2"
    ;;
  last)
    [[ -z "${2:-}" ]] && { echo "usage: session.sh last <sid>" >&2; exit 1; }
    cmd_last "$2"
    ;;
  help|--help|-h|"")
    echo "Solar Harness — Session Event API"
    echo ""
    echo "用法:"
    echo "  session.sh append <sid> <event_json>   追加事件 (append-only, flock)"
    echo "  session.sh get <sid> [--from=N] [--to=M]  切片读取"
    echo "  session.sh tail <sid> [N]               最后 N 条 (默认 10)"
    echo "  session.sh count <sid>                  事件总数"
    echo "  session.sh last <sid>                   最后一条事件"
    echo ""
    echo "events.jsonl 格式:"
    echo '  {"ts":"ISO","sid":"sprint-x","event":"xxx","by":"role","data":{}}'
    ;;
  *)
    echo "unknown command: $1" >&2
    exit 1
    ;;
esac
