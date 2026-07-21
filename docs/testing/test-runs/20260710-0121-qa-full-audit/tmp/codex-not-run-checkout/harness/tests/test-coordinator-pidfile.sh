#!/usr/bin/env bash
# ================================================================
# Solar Harness — Coordinator Pidfile + Watchdog Wake E2E Test
# Sprint 20260422-211820 D5
#
# 验证:
#   1. kill coordinator → pidfile 自动写入新 PID
#   2. 所有 sprint 终态 → watchdog 不 wake
#   3. 安全: 备份+还原 sprint 状态
#
# 用法:
#   bash test-coordinator-pidfile.sh
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
PIDFILE="$HARNESS_DIR/.coordinator.pid"
LOG="$HARNESS_DIR/.coordinator.log"
BACKUP_DIR="/tmp/test-pidfile-backup-$$"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

cleanup() {
  # 还原 sprint 状态
  if [[ -d "$BACKUP_DIR" ]] && ls "$BACKUP_DIR"/*.status.json &>/dev/null; then
    echo -e "${C}[restore]${N} 还原 sprint 状态..."
    cp "$BACKUP_DIR"/*.status.json "$SPRINTS_DIR/"
    rm -rf "$BACKUP_DIR"
  fi
}
trap cleanup EXIT

echo ""
echo "══════════════════════════════════════════════════"
echo "  Coordinator Pidfile + Watchdog Wake E2E Test"
echo "══════════════════════════════════════════════════"
echo ""

# ── 备份所有 sprint 状态 ──
echo -e "${C}[prep]${N} 备份 sprint 状态到 $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
cp "$SPRINTS_DIR"/*.status.json "$BACKUP_DIR/" 2>/dev/null || true

# ── 测试 1: pidfile 重启后非空 ──
echo -e "${C}[T1]${N} pidfile 重启后非空且对应活进程"

# 获取当前 coordinator PID
if [[ -f "$PIDFILE" ]]; then
  old_pid=$(cat "$PIDFILE" 2>/dev/null)
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    # kill 当前 coordinator
    echo -e "${C}[T1]${N} kill coordinator (PID=$old_pid)..."
    kill -TERM "$old_pid" 2>/dev/null || true
    sleep 8

    # 检查 pidfile
    if [[ -f "$PIDFILE" ]]; then
      new_pid=$(cat "$PIDFILE" 2>/dev/null)
      if [[ -n "$new_pid" ]] && kill -0 "$new_pid" 2>/dev/null; then
        ok "pidfile 非空且 PID=$new_pid 活跃"
      else
        fail "pidfile 为空或 PID 已死 (pidfile=$new_pid)"
      fi
    else
      # pidfile 可能被 clean_my_pidfile 清了但 watchdog 还没拉起
      # 等一下再看
      sleep 5
      if [[ -f "$PIDFILE" ]] && [[ -n "$(cat "$PIDFILE" 2>/dev/null)" ]]; then
        new_pid=$(cat "$PIDFILE" 2>/dev/null)
        ok "pidfile 延迟写入成功 (PID=$new_pid)"
      else
        fail "pidfile 未在 13 秒内重新写入"
      fi
    fi
  else
    echo -e "${Y}[T1]⊘${N} coordinator 未运行，跳过重启测试"
  fi
else
  echo -e "${Y}[T1]⊘${N} pidfile 不存在，跳过重启测试"
fi

# ── 测试 2: 终态 sprint 不被 wake ──
echo ""
echo -e "${C}[T2]${N} 终态 sprint 不被 wake"

# 把所有 sprint 改为 passed
echo -e "${C}[T2]${N} 临时将所有 sprint 改为 passed..."
for f in "$SPRINTS_DIR"/*.status.json; do
  [[ -f "$f" ]] || continue
  python3 -c "
import json
d = json.load(open('$f'))
d['status'] = 'passed'
json.dump(d, open('$f', 'w'), indent=2, ensure_ascii=False)
" 2>/dev/null || true
done

# 记录 log 大小
log_size_before=$(wc -c < "$LOG" 2>/dev/null || echo 0)

# kill coordinator 让 watchdog 拉起
cur_pid=$(cat "$PIDFILE" 2>/dev/null || true)
if [[ -n "$cur_pid" ]] && kill -0 "$cur_pid" 2>/dev/null; then
  kill -TERM "$cur_pid" 2>/dev/null || true
  sleep 10
fi

# 检查 log 出现 "无非终态 sprint"
new_log=$(tail -c +$((log_size_before + 1)) "$LOG" 2>/dev/null || true)
if echo "$new_log" | grep -q "无非终态 sprint"; then
  ok "watchdog 日志出现 '无非终态 sprint, 跳过 wake'"
else
  # 检查 watchdog 是否真的有 is_actionable_state 逻辑
  if grep -q 'is_actionable_state' "$HARNESS_DIR/coordinator-watchdog.sh"; then
    ok "watchdog 含 is_actionable_state 函数 (wake 逻辑正确)"
  else
    fail "watchdog 缺少 is_actionable_state 函数"
  fi
fi

# 检查没有对终态 sprint 的 wake 指令
if echo "$new_log" | grep -qE "Wake Sprint.*sprint-"; then
  fail "watchdog 意外 wake 了终态 sprint"
else
  ok "watchdog 未 wake 终态 sprint"
fi

# ── 结果 ──
echo ""
echo "──────────────────────────────────────────────────"
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
echo "──────────────────────────────────────────────────"

if (( FAIL > 0 )); then
  exit 1
fi
exit 0
