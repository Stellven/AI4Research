#!/usr/bin/env bash
# ================================================================
# Solar Harness — Loud Notify E2E Test
# Sprint 20260422-222017 D4
#
# 验证: check_planner_notice 在 planner pane 空闲时发送 loud notice
# 流程: rm read_marker + 写新 notice → 等 70 秒 → 断言 log + pane
#
# 用法:
#   bash test-loud-notify.sh
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
LOG="$HARNESS_DIR/.coordinator.log"
NOTICE="$HARNESS_DIR/.planner-last-notice"
READ_MARKER="$HARNESS_DIR/.planner-last-notice.read"
PANE_PLANNER="solar-harness:0.0"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

echo ""
echo "══════════════════════════════════════════════════"
echo "  Loud Notify E2E Test"
echo "══════════════════════════════════════════════════"
echo ""

# ── 前提: planner pane 空闲检测 ──
echo -e "${C}[prep]${N} 检查 planner pane 空闲状态..."
last_lines=$(tmux capture-pane -t "$PANE_PLANNER" -p 2>/dev/null | tail -10 || true)
if echo "$last_lines" | grep -qE '(✳|⏺|Esc to interrupt)'; then
  echo -e "${Y}⊘${N} Planner pane 当前忙碌, 跳过测试"
  exit 0
fi
if ! echo "$last_lines" | grep -qE '(❯|╭──)'; then
  echo -e "${Y}⊘${N} Planner pane 未检测到就绪提示符, 跳过测试"
  exit 0
fi
ok "Planner pane 空闲"

# ── 前提: coordinator 运行中 ──
pidfile="$HARNESS_DIR/.coordinator.pid"
if ! [[ -f "$pidfile" ]] || ! kill -0 "$(cat "$pidfile")" 2>/dev/null; then
  echo -e "${Y}⊘${N} Coordinator 未运行, 跳过测试"
  exit 0
fi
ok "Coordinator 运行中"

# ── 测试: 触发 loud notice ──
log_size_before=$(wc -c < "$LOG" 2>/dev/null || echo 0)

# 清除 read marker + 写新 notice
rm -f "$READ_MARKER"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)	passed	test-loud-notify	dummy-test-title" > "$NOTICE"
ok "写入测试 notice + 清除 read marker"

# 等 70 秒让 coordinator 触发 check_planner_notice (mod10 ≈ 60s)
echo -e "${C}[wait]${N} 等待 70 秒 (coordinator mod10 周期)..."
sleep 70

# ── 断言 1: coordinator.log 出现 [planner-notify] ──
new_log=$(tail -c +$((log_size_before + 1)) "$LOG" 2>/dev/null || true)
if echo "$new_log" | grep -q '\[planner-notify\]'; then
  ok "coordinator.log 出现 [planner-notify]"
else
  fail "coordinator.log 未出现 [planner-notify]"
fi

# ── 断言 2: planner pane 包含 📬 Sprint passed ──
pane_after=$(tmux capture-pane -t "$PANE_PLANNER" -p 2>/dev/null || true)
if echo "$pane_after" | grep -q '📬 Sprint passed: test-loud-notify'; then
  ok "Planner pane 包含 loud notice 消息"
else
  fail "Planner pane 未出现 loud notice 消息"
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
