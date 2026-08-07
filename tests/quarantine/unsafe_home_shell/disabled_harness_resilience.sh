#!/usr/bin/env bash
# test-harness-resilience.sh — D6: 总体韧性验证
set -eu
HARNESS_DIR="$HOME/.solar/harness"
G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
PASS=0; FAIL=0
ok() { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

echo "[D6] Harness 韧性总体验证"

# 1. D2: 自动恢复无阻塞
if bash "$HARNESS_DIR/tests/test-d2-wake-no-block.sh" >/dev/null 2>&1; then
  ok "D2 自动恢复无阻塞"
else
  fail "D2 自动恢复无阻塞"
fi

# 2. D3: builder worktree 一致
if bash "$HARNESS_DIR/tests/test-d3-builder-worktree-consistency.sh" >/dev/null 2>&1; then
  ok "D3 builder worktree 一致"
else
  fail "D3 builder worktree 一致"
fi

# 3. D4: 无明文 token
if bash "$HARNESS_DIR/tests/test-d4-no-plaintext-tokens.sh" >/dev/null 2>&1; then
  ok "D4 无明文 token"
else
  fail "D4 无明文 token"
fi

# 4. D5: tmux send-keys 路径安全
if bash "$HARNESS_DIR/tests/test-d5-tmux-path-escape.sh" >/dev/null 2>&1; then
  ok "D5 tmux 路径安全"
else
  fail "D5 tmux 路径安全"
fi

# 5. 关键脚本语法正确
for f in solar-harness.sh pane-launcher.sh start-incarnation.sh coordinator-watchdog.sh model-config.sh; do
  if bash -n "$HARNESS_DIR/$f" 2>/dev/null; then
    ok "$f 语法正确"
  else
    fail "$f 语法错误"
  fi
done

# 6. lib 共享脚本语法正确
for f in "$HARNESS_DIR"/lib/*.sh; do
  bf=$(basename "$f")
  if bash -n "$f" 2>/dev/null; then
    ok "lib/$bf 语法正确"
  else
    fail "lib/$bf 语法错误"
  fi
done

echo ""
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
(( FAIL > 0 )) && exit 1
echo "PASS"
exit 0
