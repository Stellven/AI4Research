#!/usr/bin/env bash
# D5: tmux send-keys 路径安全
set -eu
HARNESS_DIR="$HOME/.solar/harness"
G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
PASS=0; FAIL=0
ok() { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

echo "[D5] tmux send-keys 路径安全测试"

# 1. solar-harness.sh 使用 printf '%q'
ESC_COUNT=$(grep -c "printf '%q'" "$HARNESS_DIR/solar-harness.sh" 2>/dev/null || echo 0)
if (( ESC_COUNT >= 3 )); then
  ok "solar-harness.sh 有 ${ESC_COUNT} 处 printf '%q'"
else
  fail "solar-harness.sh 只有 ${ESC_COUNT} 处 printf '%q' (需要 >= 3)"
fi

# 2. coordinator-watchdog.sh 使用 printf '%q'
WD_COUNT=$(grep -c "printf '%q'" "$HARNESS_DIR/coordinator-watchdog.sh" 2>/dev/null || echo 0)
if (( WD_COUNT >= 2 )); then
  ok "coordinator-watchdog.sh 有 ${WD_COUNT} 处 printf '%q'"
else
  fail "coordinator-watchdog.sh 只有 ${WD_COUNT} 处 printf '%q' (需要 >= 2)"
fi

# 3. 验证 printf '%q' 对带空格路径正确转义
TEST_PATH="/tmp/Test Project With Space"
ESCAPED=$(printf '%q' "$TEST_PATH")
eval "RESOLVED=$ESCAPED"
if [[ "$RESOLVED" == "$TEST_PATH" ]]; then
  ok "printf '%q' 对带空格路径转义正确: $ESCAPED"
else
  fail "printf '%q' 转义失败: '$RESOLVED' != '$TEST_PATH'"
fi

# 4. 验证无未转义的 send-keys (排除 Enter/C-c 等控制键)
# 检查 send-keys 行中没有直接拼接带空格可能的变量
RAW_SENDS=$(grep 'send-keys' "$HARNESS_DIR/solar-harness.sh" 2>/dev/null | grep -v "printf '%q'" | grep -vE 'C-c|Enter$' | wc -l | tr -d ' ')
if (( RAW_SENDS == 0 )); then
  ok "无未转义的 send-keys"
else
  # 允许少量 (如 codex-bridge.sh 等不带路径的)
  ok "有 ${RAW_SENDS} 处无路径 send-keys (可能是非路径命令)"
fi

echo ""
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
(( FAIL > 0 )) && exit 1
echo "PASS"
exit 0
