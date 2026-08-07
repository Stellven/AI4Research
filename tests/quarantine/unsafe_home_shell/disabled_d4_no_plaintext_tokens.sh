#!/bin/env bash
# D4: 无明文 token
set -eu
HARNESS_DIR="$HOME/.solar/harness"
G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
PASS=0; FAIL=0
ok() { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

echo "[D4] 无明文 Token 测试"

# 1. secrets 文件存在且权限正确
if [[ -f "$HOME/.solar/secrets/zhipu.env" ]]; then
  ok "secrets/zhipu.env 存在"
  PERM=$(stat -f '%Lp' "$HOME/.solar/secrets/zhipu.env" 2>/dev/null || stat -c '%a' "$HOME/.solar/secrets/zhipu.env" 2>/dev/null)
  if [[ "$PERM" == "600" ]]; then
    ok "secrets/zhipu.env 权限 600"
  else
    fail "secrets/zhipu.env 权限 $PERM (需要 600)"
  fi
else
  fail "secrets/zhipu.env 不存在"
fi

# 2. model-config.sh 读 secrets 文件
if grep -q 'secrets/zhipu.env' "$HARNESS_DIR/model-config.sh" 2>/dev/null; then
  ok "model-config.sh 引用 secrets 文件"
else
  fail "model-config.sh 未引用 secrets 文件"
fi

# 3. 无明文 auth token (排除 secrets 文件本身和测试)
PLAINTEXT=$(grep -rl 'cee4edb0\|q0unUsiCytMqBo07' "$HARNESS_DIR"/*.sh 2>/dev/null | grep -v test- || true)
if [[ -z "$PLAINTEXT" ]]; then
  ok "harness 脚本无明文 token"
else
  fail "以下脚本仍有明文 token: $PLAINTEXT"
fi

# 4. persona-config.sh 引用 secrets
if grep -q 'secrets\|ZHIPU_AUTH_TOKEN\|model-config' "$HARNESS_DIR/lib/persona-config.sh" 2>/dev/null; then
  ok "persona-config.sh 通过 secrets/model-config 获取 token"
else
  fail "persona-config.sh 未引用 secrets"
fi

# 5. pane-launcher.sh 无硬编码 token
if grep -v '^#' "$HARNESS_DIR/pane-launcher.sh" 2>/dev/null | grep -q 'cee4edb0'; then
  fail "pane-launcher.sh 仍有硬编码 token"
else
  ok "pane-launcher.sh 无硬编码 token"
fi

echo ""
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
(( FAIL > 0 )) && exit 1
echo "PASS"
exit 0
