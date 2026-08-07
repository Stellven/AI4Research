#!/usr/bin/env bash
# D3: builder worktree 行为一致
set -eu
HARNESS_DIR="$HOME/.solar/harness"
G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
PASS=0; FAIL=0
ok() { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

echo "[D3] Builder worktree 一致性测试"

# 1. 两个启动器都引用 worktree.sh
if grep -q 'worktree.sh' "$HARNESS_DIR/pane-launcher.sh" 2>/dev/null; then
  ok "pane-launcher 引用 worktree.sh"
else
  fail "pane-launcher 未引用 worktree.sh"
fi

if grep -q 'worktree.sh' "$HARNESS_DIR/start-incarnation.sh" 2>/dev/null; then
  ok "start-incarnation 引用 worktree.sh"
else
  fail "start-incarnation 未引用 worktree.sh"
fi

# 2. 共享 worktree.sh 存在
if [[ -f "$HARNESS_DIR/lib/worktree.sh" ]]; then
  ok "lib/worktree.sh 存在"
else
  fail "lib/worktree.sh 不存在"
fi

# 3. worktree.sh 有复用逻辑 (watchdog 重启场景)
if grep -q '复用\|reuse\|已有\|already' "$HARNESS_DIR/lib/worktree.sh" 2>/dev/null; then
  ok "worktree.sh 有复用逻辑"
else
  fail "worktree.sh 缺少复用逻辑 (watchdog 重启时会重复创建)"
fi

# 4. watchdog respawn 传 work_dir 参数
if grep -q 'start-incarnation.sh.*persona.*_esc_w\|start-incarnation.sh.*persona.*work' "$HARNESS_DIR/coordinator-watchdog.sh" 2>/dev/null; then
  ok "watchdog respawn 传 work_dir 参数"
else
  fail "watchdog respawn 未传 work_dir 参数"
fi

# 5. 共享 worktree 逻辑语法正确
if bash -n "$HARNESS_DIR/lib/worktree.sh" 2>/dev/null; then
  ok "worktree.sh 语法正确"
else
  fail "worktree.sh 语法错误"
fi

echo ""
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
(( FAIL > 0 )) && exit 1
echo "PASS"
exit 0
