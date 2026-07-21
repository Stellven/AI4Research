#!/usr/bin/env bash
# D2: wake / 自动恢复无人工阻塞
set -eu
HARNESS_DIR="$HOME/.solar/harness"
G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
PASS=0; FAIL=0
ok() { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

echo "[D2] 自动恢复无阻塞测试"

# 1. pane-launcher.sh 无 read -r (排除注释行)
if grep -v '^#' "$HARNESS_DIR/pane-launcher.sh" 2>/dev/null | grep -q 'read -r'; then
  fail "pane-launcher.sh 仍有 read -r 阻塞"
else
  ok "pane-launcher.sh 无 read -r 阻塞"
fi

# 2. start-incarnation.sh 无 read -r
if grep -q 'read -r' "$HARNESS_DIR/start-incarnation.sh" 2>/dev/null; then
  fail "start-incarnation.sh 仍有 read -r 阻塞"
else
  ok "start-incarnation.sh 无 read -r 阻塞"
fi

# 3. wake 链路不调 pane-launcher (交互式)
# solar-harness.sh wake 应该用 start-incarnation 或无阻塞路径
if grep -q 'wake.*pane-launcher' "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  # wake 仍调 pane-launcher, 但 pane-launcher 已无 read -r, OK
  if ! grep -q 'read -r' "$HARNESS_DIR/pane-launcher.sh"; then
    ok "wake 调 pane-launcher 但已无阻塞"
  else
    fail "wake 调 pane-launcher 且仍有阻塞"
  fi
else
  ok "wake 不调 pane-launcher (无阻塞)"
fi

# 4. watchdog respawn 用 start-incarnation (无阻塞)
if grep -q 'respawn.*start-incarnation' "$HARNESS_DIR/coordinator-watchdog.sh" 2>/dev/null; then
  ok "watchdog respawn 用 start-incarnation"
else
  fail "watchdog respawn 未用 start-incarnation"
fi

echo ""
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
(( FAIL > 0 )) && exit 1
echo "PASS"
exit 0
