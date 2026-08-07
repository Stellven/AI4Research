#!/usr/bin/env bash
# ================================================================
# Solar Harness — Watchdog Singleton E2E Test
# Sprint 20260422-222017 D5
#
# 验证: watchdog 多实例去重 (pidfile 自治)
# 流程: pkill 全清 → nohup 启 3 次 → 断言只有 1 个活进程
#
# 用法:
#   bash test-watchdog-singleton.sh
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
WATCHDOG="$HARNESS_DIR/coordinator-watchdog.sh"
PIDFILE="$HARNESS_DIR/.watchdog.pid"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

# 记录测试前 watchdog 状态
orig_pid=""
if [[ -f "$PIDFILE" ]]; then
  orig_pid=$(cat "$PIDFILE" 2>/dev/null)
fi

ensure_watchdog_alive() {
  # 测试后必须确保有一个 watchdog 活着
  if ! [[ -f "$PIDFILE" ]] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo -e "${C}[restore]${N} 重新启动 watchdog..."
    bash "$WATCHDOG" start 2>/dev/null || true
  fi
}

echo ""
echo "══════════════════════════════════════════════════"
echo "  Watchdog Singleton E2E Test"
echo "══════════════════════════════════════════════════"
echo ""

# ── Step 1: 清理所有 watchdog 进程 ──
echo -e "${C}[step1]${N} 清理所有 watchdog 进程..."
pkill -f 'coordinator-watchdog.sh' 2>/dev/null || true
sleep 2
rm -f "$PIDFILE"

# 确认全清
alive=$(pgrep -fc 'coordinator-watchdog.sh' 2>/dev/null || echo 0)
# pgrep -fc 包含 grep 自身, 所以用 pgrep -f | grep -v grep
actual_alive=$(pgrep -f 'coordinator-watchdog.sh' 2>/dev/null | grep -v "$$" | wc -l | tr -d ' ' || echo 0)
if [[ "$actual_alive" -eq 0 ]]; then
  ok "所有 watchdog 进程已清理"
else
  echo -e "${Y}⚠${N} 仍有 ${actual_alive} 个 watchdog 残留, 强制 kill..."
  pkill -9 -f 'coordinator-watchdog.sh' 2>/dev/null || true
  sleep 1
fi

# ── Step 2: 连续启动 3 次 ──
echo -e "${C}[step2]${N} 连续启动 watchdog 3 次..."
bash "$WATCHDOG" start 2>/dev/null || true
sleep 1
bash "$WATCHDOG" start 2>/dev/null || true
sleep 1
bash "$WATCHDOG" start 2>/dev/null || true
sleep 3

# ── 断言 1: 只有 1 个 watchdog 进程 ──
actual_alive=$(pgrep -f 'coordinator-watchdog.sh' 2>/dev/null | grep -v "$$" | wc -l | tr -d ' ' || echo 0)
if [[ "$actual_alive" -eq 1 ]]; then
  ok "只有 1 个 watchdog 进程 (${actual_alive})"
else
  fail "期望 1 个 watchdog, 实际 ${actual_alive} 个"
fi

# ── 断言 2: pidfile 指向活进程 ──
if [[ -f "$PIDFILE" ]]; then
  wpid=$(cat "$PIDFILE" 2>/dev/null)
  if [[ -n "$wpid" ]] && kill -0 "$wpid" 2>/dev/null; then
    ok "pidfile 指向活进程 (PID=${wpid})"
  else
    fail "pidfile PID=${wpid:-empty} 已死或不存在"
  fi
else
  fail "pidfile 不存在"
fi

# ── 恢复 ──
ensure_watchdog_alive

# ── 结果 ──
echo ""
echo "──────────────────────────────────────────────────"
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
echo "──────────────────────────────────────────────────"

if (( FAIL > 0 )); then
  exit 1
fi
exit 0
