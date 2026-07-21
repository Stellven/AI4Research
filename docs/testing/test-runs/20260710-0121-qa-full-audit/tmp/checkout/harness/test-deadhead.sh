#!/bin/bash
# ================================================================
# Solar Harness — 断头回归测试
#
# 检查 D1(archive), D2(CACHE_BOUNDARY), D3(token-tracker) 真实运行
#
# 用法:
#   test-deadhead.sh              运行全部检查
#   test-deadhead.sh -v           详细模式
#
# @module solar-farm/harness/test-deadhead
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
ARCHIVE_DIR="$SPRINTS_DIR/archive"
REPORTS_DIR="$HOME/.solar/reports"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'

VERBOSE=false
[[ "${1:-}" == "-v" ]] && VERBOSE=true

pass=0
fail=0
total=0

check() {
  local name="$1" result="$2"
  total=$((total + 1))
  if eval "$result"; then
    echo -e "  ${G}PASS${N} ${name}"
    pass=$((pass + 1))
  else
    echo -e "  ${R}FAIL${N} ${name}"
    fail=$((fail + 1))
  fi
}

echo -e "${C}[Deadhead Test]${N} 断头回归测试"
echo ""

# --- T1: archive 目录非空 (D1) ---
echo -e "${C}[T1]${N} archive 目录非空 (archive.sh auto 真实运行)"
archive_count=$(ls "$ARCHIVE_DIR"/ 2>/dev/null | wc -l | tr -d ' ')
$VERBOSE && echo "  archive 文件数: ${archive_count}"
check "archive 有 ${archive_count} 个文件" "[[ ${archive_count} -gt 0 ]]"

# --- T2: 最新 dispatch.md 包含 CACHE_BOUNDARY (D2) ---
echo -e "${C}[T2]${N} dispatch.md 包含 CACHE_BOUNDARY (generate_dispatch 真实调用)"
latest_dispatch=$(ls -t "$SPRINTS_DIR"/*.dispatch.md 2>/dev/null | head -1)
if [[ -n "$latest_dispatch" ]]; then
  cb_count=$(grep -c "CACHE_BOUNDARY" "$latest_dispatch" 2>/dev/null | tr -d '[:space:]')
  $VERBOSE && echo "  最新 dispatch: $(basename "$latest_dispatch"), CACHE_BOUNDARY: ${cb_count}"
  check "CACHE_BOUNDARY 出现 ${cb_count} 次" "[[ ${cb_count} -ge 1 ]]"
else
  check "dispatch.md 存在" "false"
  $VERBOSE && echo "  无 dispatch.md 文件"
fi

# --- T2b: generate_dispatch 在所有 handle_* 中 ---
echo -e "${C}[T2b]${N} 所有 handle_* 使用 generate_dispatch"
handle_count=$(grep -c "^handle_" "$HARNESS_DIR/coordinator.sh")
gd_count=$(grep "generate_dispatch" "$HARNESS_DIR/coordinator.sh" | grep -v "^[0-9]*:generate_dispatch\|^[0-9]*:  cat" | wc -l | tr -d ' ')
$VERBOSE && echo "  handle_* 函数: ${handle_count}, generate_dispatch 调用: ${gd_count}"
check "handle_* (${handle_count}) 全部用 generate_dispatch (${gd_count} 调用)" "[[ ${gd_count} -ge ${handle_count} ]]"

# --- T3: token-savings 报告 >= 2 (D3) ---
echo -e "${C}[T3]${N} token-savings 报告数 (token-tracker 真实运行)"
report_count=$(ls "$REPORTS_DIR"/token-savings-*.md 2>/dev/null | wc -l | tr -d ' ')
$VERBOSE && echo "  报告数: ${report_count}"
check "token-savings 报告 ${report_count} 个 (>=2)" "[[ ${report_count} -ge 2 ]]"

# --- T4: handle_passed 包含 archive auto 调用 ---
echo -e "${C}[T4]${N} handle_passed 包含 archive.sh auto 调用 (D1 接线)"
has_archive_auto=$(grep -c "archive.sh.*auto" "$HARNESS_DIR/coordinator.sh" || echo "0")
$VERBOSE && echo "  archive auto 调用: ${has_archive_auto}"
check "archive.sh auto 在 coordinator 中 (${has_archive_auto} 处)" "[[ ${has_archive_auto} -ge 1 ]]"

# --- T5: handle_passed 包含 token-tracker 调用 ---
echo -e "${C}[T5]${N} handle_passed 包含 token-tracker report 调用 (D3 接线)"
has_token_tracker=$(grep -c "token-tracker.*report" "$HARNESS_DIR/coordinator.sh" || echo "0")
$VERBOSE && echo "  token-tracker 调用: ${has_token_tracker}"
check "token-tracker report 在 coordinator 中 (${has_token_tracker} 处)" "[[ ${has_token_tracker} -ge 1 ]]"

# --- T6: archive auto 有 24h 保护 ---
echo -e "${C}[T6]${N} archive.sh auto 有 24h 保护 (D4)"
has_24h=$(grep -c "86400\|24h" "$HARNESS_DIR/archive.sh" || echo "0")
$VERBOSE && echo "  24h 保护: ${has_24h} 处"
check "archive.sh 包含 24h 保护 (${has_24h} 处)" "[[ ${has_24h} -ge 1 ]]"

# --- T7: archive 有 archived_at 事件 ---
echo -e "${C}[T7]${N} 归档写入 archived_at 事件 (D4)"
has_archived_event=$(grep -c "archived.*archive.sh" "$HARNESS_DIR/archive.sh" || echo "0")
$VERBOSE && echo "  archived_at 事件: ${has_archived_event} 处"
check "archive.sh 写入 archived_at 事件 (${has_archived_event} 处)" "[[ ${has_archived_event} -ge 1 ]]"

# --- 汇总 ---
echo ""
echo -e "─────────────────────────────────"
if [[ "$fail" -eq 0 ]]; then
  echo -e "${G}通过 ${pass}/${total} — 无断头${N}"
  exit 0
else
  echo -e "${R}通过 ${pass}/${total} / 失败 ${fail}${N}"
  exit 1
fi
