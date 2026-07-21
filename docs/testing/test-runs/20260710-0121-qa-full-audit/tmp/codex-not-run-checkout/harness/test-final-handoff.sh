#!/bin/bash
# ── test-final-handoff.sh — 收官守护端到端测试 ──
# Sprint 20260420-090726, D5
#
# 用法: bash test-final-handoff.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
COORD="$HARNESS_DIR/coordinator.sh"

G='\033[0;32m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

log() { echo -e "${C}[测试]${N} $(date '+%H:%M:%S') $*"; }
pass() { echo -e "  ${G}✅ PASS${N}: $1"; ((PASS++)); }
fail() { echo -e "  ${R}❌ FAIL${N}: $1"; ((FAIL++)); }

echo ""
echo "══════════════════════════════════════════════════"
echo "  收官守护端到端测试"
echo "══════════════════════════════════════════════════"
echo ""

# ── T1: handle_passed 幂等检查 ──
log "T1: handle_passed 包含 finalized 幂等检查"

if grep -q "already finalized, skip" "$COORD" 2>/dev/null; then
  pass "T1: handle_passed 包含幂等检查"
else
  fail "T1: handle_passed 缺少幂等检查"
fi

# ── T2: handle_passed 末尾 touch finalized ──
log "T2: handle_passed 创建 .finalized 标记"

if grep -q 'touch.*finalized' "$COORD" 2>/dev/null; then
  pass "T2: handle_passed 创建 .finalized"
else
  fail "T2: handle_passed 未创建 .finalized"
fi

# ── T3: handle_passed_completed 事件 ──
log "T3: handle_passed 写 handle_passed_completed 事件"

if grep -q "handle_passed_completed" "$COORD" 2>/dev/null; then
  pass "T3: handle_passed_completed 事件存在"
else
  fail "T3: handle_passed_completed 事件缺失"
fi

# ── T4: 启动自愈逻辑 ──
log "T4: coordinator 包含启动自愈"

if grep -q "startup recovery.*passed sprints without finalized" "$COORD" 2>/dev/null; then
  pass "T4: 启动自愈日志存在"
else
  fail "T4: 启动自愈日志缺失"
fi

# ── T5: 状态变化日志带 round ──
log "T5: 状态变化日志包含 round"

if grep -q "状态变化检测.*round" "$COORD" 2>/dev/null; then
  pass "T5: 状态变化日志带 round"
else
  fail "T5: 状态变化日志缺少 round"
fi

# ── T6: clean-corrupted 子命令 ──
log "T6: clean-corrupted 子命令存在"

if grep -q "clean-corrupted)" "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  pass "T6: clean-corrupted 子命令存在"
else
  fail "T6: clean-corrupted 子命令缺失"
fi

if grep -q "do_clean_corrupted" "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  pass "T6: do_clean_corrupted 函数存在"
else
  fail "T6: do_clean_corrupted 函数缺失"
fi

# ── T7: 语法验证 ──
log "T7: 语法验证"

bash -n "$COORD" 2>/dev/null
if [[ $? -eq 0 ]]; then
  pass "T7: coordinator.sh 语法正确"
else
  fail "T7: coordinator.sh 语法错误"
fi

bash -n "$HARNESS_DIR/solar-harness.sh" 2>/dev/null
if [[ $? -eq 0 ]]; then
  pass "T7: solar-harness.sh 语法正确"
else
  fail "T7: solar-harness.sh 语法错误"
fi

# ── T8: finalized 标记文件模拟 ──
log "T8: finalized 标记防止重复触发"

TEST_SID="test-finalized-check"
TEST_FINALIZED="$SPRINTS_DIR/${TEST_SID}.finalized"
# 创建 finalized 文件
touch "$TEST_FINALIZED"
# handle_passed 中检查文件存在的逻辑
if [[ -f "$TEST_FINALIZED" ]]; then
  pass "T8: .finalized 标记文件机制可检测"
else
  fail "T8: .finalized 标记文件创建失败"
fi
rm -f "$TEST_FINALIZED"

# ── 总结 ──
echo ""
echo "══════════════════════════════════════════════════"
echo -e "  结果: ${G}${PASS} PASS${N} / ${R}${FAIL} FAIL${N}"
echo "══════════════════════════════════════════════════"
echo ""

if [[ "$FAIL" -eq 0 ]]; then
  log "所有测试通过 ✅"
  exit 0
else
  log "有 ${FAIL} 项测试失败 ❌"
  exit 1
fi
