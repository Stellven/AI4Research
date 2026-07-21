#!/bin/bash
# ================================================================
# Solar Harness — Codex 预算管理
#
# 用法:
#   codex-budget.sh check          检查预算是否充足 (exit 0/1)
#   codex-budget.sh consume <N>    消耗 N tokens + 1 call
#   codex-budget.sh reset          重置每日计数
#   codex-budget.sh status         打印当前余量
#
# @module solar-farm/harness
# ================================================================
set -uo pipefail

BUDGET_FILE="$HOME/.solar/harness/codex-budget.json"

read_field() {
  python3 -c "import json; print(json.load(open('$BUDGET_FILE')).get('$1', 0))" 2>/dev/null
}

# 原子更新预算文件
atomic_update() {
  python3 -c "
import json, tempfile, os, sys

path = os.path.expanduser('$BUDGET_FILE')
update_code = sys.stdin.read()

with open(path) as f:
    data = json.load(f)

exec(update_code, {'data': data, 'json': json})

dirn = os.path.dirname(path)
fd, tmp = tempfile.mkstemp(dir=dirn, suffix='.tmp')
with os.fdopen(fd, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
os.rename(tmp, path)
print('OK')
" 2>/dev/null
}

cmd_check() {
  local today
  today=$(date +%Y-%m-%d)
  local reset_at
  reset_at=$(read_field "reset_at")

  # 日界重置
  if [[ "$reset_at" != "$today" ]]; then
    cmd_reset >/dev/null 2>&1
  fi

  local used_calls used_tokens call_limit token_limit hard_stop
  used_calls=$(read_field "used_calls_today")
  used_tokens=$(read_field "used_tokens_today")
  call_limit=$(read_field "daily_call_limit")
  token_limit=$(read_field "daily_token_limit")
  hard_stop=$(read_field "hard_stop")

  if [[ "$hard_stop" == "True" || "$hard_stop" == "true" ]]; then
    if [[ "$used_calls" -ge "$call_limit" ]] || [[ "$used_tokens" -ge "$token_limit" ]]; then
      return 1
    fi
  fi
  return 0
}

cmd_consume() {
  local tokens="${1:-0}"
  echo "
data['used_calls_today'] = data.get('used_calls_today', 0) + 1
data['used_tokens_today'] = data.get('used_tokens_today', 0) + $tokens
" | atomic_update
}

cmd_reset() {
  local today
  today=$(date +%Y-%m-%d)
  echo "
data['used_calls_today'] = 0
data['used_tokens_today'] = 0
data['reset_at'] = '$today'
" | atomic_update
}

cmd_status() {
  local today
  today=$(date +%Y-%m-%d)
  local reset_at
  reset_at=$(read_field "reset_at")
  if [[ "$reset_at" != "$today" ]]; then
    cmd_reset >/dev/null 2>&1
  fi

  local used_calls used_tokens call_limit token_limit
  used_calls=$(read_field "used_calls_today")
  used_tokens=$(read_field "used_tokens_today")
  call_limit=$(read_field "daily_call_limit")
  token_limit=$(read_field "daily_token_limit")

  local call_pct token_pct
  call_pct=$(( used_calls * 100 / call_limit ))
  token_pct=$(( used_tokens * 100 / token_limit ))

  echo "Calls: ${used_calls}/${call_limit} (${call_pct}%)"
  echo "Tokens: ${used_tokens}/${token_limit} (${token_pct}%)"
  echo "Reset: ${reset_at}"
}

case "${1:-status}" in
  check)   cmd_check ;;
  consume) cmd_consume "${2:-0}" ;;
  reset)   cmd_reset ;;
  status)  cmd_status ;;
  *)       echo "用法: codex-budget.sh [check|consume <tokens>|reset|status]"; exit 1 ;;
esac
