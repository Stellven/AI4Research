#!/usr/bin/env bash
# ================================================================
# Solar Harness — Migrate Intent E2E Test (sprint-20260424-082117 D6)
#
# 测试意图引擎 hook 对迁移触发词的识别
#
# 用法:
#   bash test-migrate-intent.sh
#   退出码 0 = PASS, 1 = FAIL
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HOOK="$HOME/.claude/hooks/intent-engine-hook.sh"
PASS=0
FAIL=0

G='\033[0;32m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

echo ""
echo "══════════════════════════════════════════════════"
echo "  Migrate Intent E2E Test"
echo "══════════════════════════════════════════════════"
echo ""

# Helper: send prompt to hook, capture stdout
run_hook() {
    local prompt="$1"
    echo "{\"prompt\":\"$prompt\"}" | bash "$HOOK" 2>/dev/null || true
}

# ── Test 1: deploy 触发词 ──
echo "Test 1: 迁移到 mini-m4"
OUT=$(run_hook "迁移到 mini-m4 并部署")
if echo "$OUT" | grep -q 'type="migrate"' && echo "$OUT" | grep -q 'subcmd="deploy"'; then
    ok "deploy 触发词识别正确"
else
    fail "deploy 触发词未识别: $OUT"
fi

# ── Test 2: export 触发词 ──
echo "Test 2: 打包 Solar"
OUT=$(run_hook "打包 Solar")
if echo "$OUT" | grep -q 'type="migrate"' && echo "$OUT" | grep -q 'subcmd="export"'; then
    ok "export 触发词识别正确"
else
    fail "export 触发词未识别: $OUT"
fi

# ── Test 3: rollback 触发词 ──
echo "Test 3: 回滚迁移"
OUT=$(run_hook "回滚迁移")
if echo "$OUT" | grep -q 'type="migrate"' && echo "$OUT" | grep -q 'subcmd="rollback"'; then
    ok "rollback 触发词识别正确"
else
    fail "rollback 触发词未识别: $OUT"
fi

# ── Test 4: import 触发词 ──
echo "Test 4: 从 bundle.tar 恢复"
OUT=$(run_hook "从 /tmp/bundle.tar 恢复")
if echo "$OUT" | grep -q 'type="migrate"' && echo "$OUT" | grep -q 'subcmd="import"'; then
    ok "import 触发词识别正确"
else
    fail "import 触发词未识别: $OUT"
fi

# ── Test 5: verify 触发词 ──
echo "Test 5: 验证迁移包"
OUT=$(run_hook "验证迁移包 /tmp/test.tar")
if echo "$OUT" | grep -q 'type="migrate"' && echo "$OUT" | grep -q 'subcmd="verify"'; then
    ok "verify 触发词识别正确"
else
    fail "verify 触发词未识别: $OUT"
fi

# ── Test 6: 歧义输入 ──
echo "Test 6: 歧义输入 '迁移'"
OUT=$(run_hook "迁移")
if echo "$OUT" | grep -q 'type="migrate_ambiguous"'; then
    ok "歧义输入正确识别为 ambiguous"
else
    fail "歧义输入未正确处理: $OUT"
fi

# ── Test 7: 不相关输入不误触发 ──
echo "Test 7: 不相关输入 '今天天气好'"
OUT=$(run_hook "今天天气好")
if echo "$OUT" | grep -q 'migrate'; then
    fail "不相关输入误触发迁移"
else
    ok "不相关输入未触发迁移"
fi

# ── Test 8: deploy to 英文触发 ──
echo "Test 8: deploy to mini-m4"
OUT=$(run_hook "deploy to mini-m4")
if echo "$OUT" | grep -q 'type="migrate"' && echo "$OUT" | grep -q 'subcmd="deploy"'; then
    ok "英文 deploy to 触发正确"
else
    fail "英文 deploy to 未识别: $OUT"
fi

# ── Test 9: 不相关输入 '今天搬家了' 不触发 ──
echo "Test 9: 不相关输入 '今天搬家了'"
OUT=$(run_hook "今天搬家了")
if echo "$OUT" | grep -q 'migrate'; then
    fail "'今天搬家了' 误触发迁移"
else
    ok "'今天搬家了' 未触发迁移"
fi

# ── Test 10: push 触发词 ──
echo "Test 10: 迁移推送到 mini-m4"
OUT=$(run_hook "迁移推送到 mini-m4")
if echo "$OUT" | grep -q 'type="migrate"' && echo "$OUT" | grep -q 'subcmd="push"'; then
    ok "push 触发词识别正确"
else
    fail "push 触发词未识别: $OUT"
fi

# ── Summary ──
echo ""
echo "──────────────────────────────────────────────────"
echo -e "  ${C}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
echo "──────────────────────────────────────────────────"
echo ""

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
