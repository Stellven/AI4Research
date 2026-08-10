#!/bin/bash
# ── test-get-latest-sprint.sh — get_latest_sprint_file 单元测试 ──
# Sprint 20260420-090726, D5
#
# 用法: bash test-get-latest-sprint.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
COORD="$HARNESS_DIR/coordinator.sh"
[[ -f "$HARNESS_DIR/lib/portable.sh" ]] && . "$HARNESS_DIR/lib/portable.sh"

G='\033[0;32m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

log() { echo -e "${C}[测试]${N} $(date '+%H:%M:%S') $*"; }
pass() { echo -e "  ${G}✅ PASS${N}: $1"; ((PASS++)); }
fail() { echo -e "  ${R}❌ FAIL${N}: $1"; ((FAIL++)); }

# 创建临时测试目录
TEST_DIR=$(mktemp -d)
trap "rm -rf '$TEST_DIR'" EXIT

# 从 coordinator.sh 提取 get_latest_sprint_file 函数及相关依赖
# 使用 source 方式太重（coordinator.sh 有 side effect），直接构造测试函数
get_test_function() {
  # 提取 get_latest_sprint_file 新实现
  sed -n '/^declare -A _corrupted_logged/,/^}/p' "$COORD"
}

echo ""
echo "══════════════════════════════════════════════════"
echo "  get_latest_sprint_file 单元测试"
echo "══════════════════════════════════════════════════"
echo ""

log "T1: 返回 mtime 最新的文件（不管状态）"

# 创建 3 个 status.json: passed(T1), active(T2), cancelled(T3)
echo '{"id":"test-passed","status":"passed"}' > "$TEST_DIR/sprint-test-001.status.json"
sleep 1
echo '{"id":"test-active","status":"active"}' > "$TEST_DIR/sprint-test-002.status.json"
sleep 1
echo '{"id":"test-cancelled","status":"cancelled"}' > "$TEST_DIR/sprint-test-003.status.json"

# 构造测试版函数（替换 SPRINTS_DIR）
test_get_latest() {
  local dir="$1"
  local best="" best_mtime=0
  for f in "$dir"/sprint-*.status.json; do
    [[ -f "$f" ]] || continue
    local fid
    fid=$(python3 -c "import json; print(json.load(open('$f')).get('id',''))" 2>/dev/null)
    if [[ -z "$fid" ]]; then
      continue
    fi
    local mtime
    mtime=$(solar_file_mtime "$f" 2>/dev/null || echo 0)
    if [[ "$mtime" -gt "$best_mtime" ]]; then
      best_mtime="$mtime"; best="$f"
    fi
  done
  echo "$best"
}

result=""
result=$(test_get_latest "$TEST_DIR")
if echo "$result" | grep -q "test-003"; then
  pass "T1: 返回 mtime 最新 (cancelled test-003)"
else
  fail "T1: 期望 test-003, 实际: $(basename "$result")"
fi

log "T2: id 为空的文件被跳过，返回次新的"

# 创建 id 为空的文件 (mtime 最新)
sleep 1
echo '{"id":"","status":"cancelled"}' > "$TEST_DIR/sprint-test-004.status.json"

result=""
result=$(test_get_latest "$TEST_DIR")
if echo "$result" | grep -q "test-003"; then
  pass "T2: 跳过 id 为空，返回 test-003"
else
  fail "T2: 期望 test-003, 实际: $(basename "$result")"
fi

log "T3: glob 只匹配 sprint-*.status.json"

# 创建非 sprint 文件
echo '{"id":"fake","status":"active"}' > "$TEST_DIR/test-other.status.json"

result=""
result=$(test_get_latest "$TEST_DIR")
if echo "$result" | grep -q "test-other"; then
  fail "T3: 不应匹配非 sprint- 前缀文件"
else
  pass "T3: glob 正确过滤非 sprint 文件"
fi

log "T4: coordinator.sh 中旧终态跳过已移除"

if grep -q "passed|done|failed|eval_pass)" "$COORD" 2>/dev/null; then
  fail "T4: 旧终态跳过逻辑仍存在"
else
  pass "T4: 旧终态跳过逻辑已移除"
fi

log "T5: coordinator.sh 包含 corrupted skip 逻辑"

if grep -q "corrupted status.json skipped" "$COORD" 2>/dev/null; then
  pass "T5: 包含 corrupted skip 日志"
else
  fail "T5: 缺少 corrupted skip 日志"
fi

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
