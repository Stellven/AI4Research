#!/usr/bin/env bash
# ================================================================
# Sprint 20260423-151839 D11 — SSH Migrate E2E Test
#
# 用 localhost 自连测试 export --push + import ssh://
# SSH localhost 不可用时 SKIP 而非 FAIL
# 退出码 0 = PASS, 2 = SKIP
#
# @module solar-farm/harness/tests
# ================================================================
set -euo pipefail

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; N='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }

HARNESS_DIR="$HOME/.solar/harness"
MIGRATE_DIR="$HARNESS_DIR/migrate"

SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5"

# ── Check SSH localhost ──
echo "检查 ssh localhost..."
if ! ssh $SSH_OPTS localhost "echo ok" &>/dev/null; then
  echo ""
  echo "SKIP: ssh localhost 不可用"
  echo "  配置方法: ssh-copy-id localhost"
  echo ""
  exit 2
fi
ok "ssh localhost 可用"

echo ""
echo "═══ Test: SSH Migrate E2E ═══"
echo ""

TEST_BUNDLE="/tmp/ssh-test-bundle-$$.tar"
TEST_BUNDLE_OUT="/tmp/ssh-test-export-$$"

cleanup() {
  rm -rf "$TEST_BUNDLE_OUT" 2>/dev/null || true
  rm -f "$TEST_BUNDLE" "${TEST_BUNDLE}.sha256" 2>/dev/null || true
  rm -f /tmp/ssh-test-bundle*.tar /tmp/ssh-test-bundle*.sha256 2>/dev/null || true
}
trap cleanup EXIT

# ── Test 1: Export ──
echo "--- Test 1: Export ---"
bash "$MIGRATE_DIR/export.sh" --out "$TEST_BUNDLE_OUT" 2>/dev/null
EXPORT_TAR=$(ls -t "$TEST_BUNDLE_OUT"/solar-bundle-*.tar 2>/dev/null | head -1)
if [[ -n "$EXPORT_TAR" ]]; then
  ok "Export 成功: $(basename "$EXPORT_TAR")"
else
  fail "Export 失败"
fi

# ── Test 2: Export --push to localhost ──
echo "--- Test 2: Export --push localhost ---"
PUSH_PATH="/tmp/ssh-test-bundle-$$.tar"
bash "$MIGRATE_DIR/export.sh" --out "$TEST_BUNDLE_OUT" --push "localhost:$PUSH_PATH" --cleanup-local 2>/dev/null
if ssh $SSH_OPTS localhost "test -f '$PUSH_PATH'" &>/dev/null; then
  ok "Bundle 推送到 localhost 成功"

  # Verify SHA256
  REMOTE_SHA=$(ssh $SSH_OPTS localhost "shasum -a 256 '$PUSH_PATH' | cut -d' ' -f1" 2>/dev/null)
  REMOTE_SHA_FILE=$(ssh $SSH_OPTS localhost "cat '${PUSH_PATH}.sha256' | cut -d' ' -f1" 2>/dev/null)
  if [[ "$REMOTE_SHA" == "$REMOTE_SHA_FILE" ]]; then
    ok "远程 SHA256 匹配"
  else
    fail "远程 SHA256 不匹配: bundle=$REMOTE_SHA file=$REMOTE_SHA_FILE"
  fi
else
  fail "Bundle 未到达 localhost"
fi

# ── Test 3: Cleanup local after --cleanup-local ──
echo "--- Test 3: --cleanup-local ---"
EXPORT_TAR_2=$(ls -t "$TEST_BUNDLE_OUT"/solar-bundle-*.tar 2>/dev/null | head -1)
if [[ -z "$EXPORT_TAR_2" ]]; then
  ok "本机 bundle 已清理 (--cleanup-local)"
else
  fail "本机 bundle 未清理"
fi

# ── Test 4: import ssh:// dry-run ──
echo "--- Test 4: import ssh:// --dry-run ---"
bash "$MIGRATE_DIR/import.sh" "ssh://localhost${PUSH_PATH}" --dry-run 2>/dev/null
DRY_EXIT=$?
if [[ $DRY_EXIT -eq 0 ]]; then
  ok "import ssh:// --dry-run 成功"
else
  fail "import ssh:// --dry-run 失败 (exit=$DRY_EXIT)"
fi

# Cleanup remote
ssh $SSH_OPTS localhost "rm -f '$PUSH_PATH' '${PUSH_PATH}.sha256'" 2>/dev/null || true

# ── Summary ──
echo ""
echo "════════════════════════════════════════"
if [[ $FAIL -eq 0 ]]; then
  echo -e "  ${G}PASS${N}: ${PASS}/${PASS} 全部通过"
else
  echo -e "  ${R}FAIL${N}: ${FAIL} 失败, ${PASS} 通过"
fi
echo "════════════════════════════════════════"
echo ""

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
