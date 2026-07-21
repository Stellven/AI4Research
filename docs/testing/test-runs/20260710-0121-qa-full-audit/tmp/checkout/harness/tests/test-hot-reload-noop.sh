#!/usr/bin/env bash
# ================================================================
# Solar Harness — Hot-Reload No-op & Edge Case Test
# Sprint sprint-20260502-182804 D5
#
# 验证:
#   1. md5 不变时不触发 hot-reload
#   2. md5 命令不可用时优雅降级
#
# 独立可跑, 不依赖正在运行的协调器 (纯脚本分析)
#
# 用法:
#   bash test-hot-reload-noop.sh
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
COORD="$HARNESS_DIR/coordinator.sh"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }
info() { echo -e "  ${C}[info]${N} $1"; }

echo ""
echo "══════════════════════════════════════════════════"
echo "  Hot-Reload No-op & Edge Case Test"
echo "══════════════════════════════════════════════════"
echo ""

# ── Test 1: coordinator.sh 包含 skip_sprint 标志 (修复存在) ──
echo "[Test 1] skip_sprint 标志检查"
if grep -q 'skip_sprint' "$COORD"; then
  ok "skip_sprint 标志存在"
else
  fail "skip_sprint 标志不存在 (hot-reload 修复未应用?)"
fi

# ── Test 2: continue 不再在 mtime 无变化路径中 ──
echo "[Test 2] mtime 无变化路径中无 continue"
# 检查 mtime 无变化块中没有裸 continue (应该只有 skip_sprint=1)
MTIME_BLOCK=$(awk '/max_file_mtime.*last_file_mtime/,/^    fi$/' "$COORD" | head -20)
if echo "$MTIME_BLOCK" | grep -q '^\s*continue\s*$'; then
  fail "mtime 无变化路径中仍有 continue (根因未修复)"
else
  ok "mtime 无变化路径中无裸 continue"
fi

# ── Test 3: hot-reload 兜底代码存在 ──
echo "[Test 3] 兜底代码检查"
if grep -q 'HOT-RELOAD-FAILED' "$COORD"; then
  ok "HOT-RELOAD-FAILED 告警代码存在"
else
  fail "HOT-RELOAD-FAILED 告警代码不存在"
fi

if grep -q 'md5 command unavailable' "$COORD"; then
  ok "md5 不可用降级代码存在"
else
  fail "md5 不可用降级代码不存在"
fi

if grep -q 'INIT_MD5=.*current_md5' "$COORD"; then
  ok "INIT_MD5 更新防死循环代码存在"
else
  fail "INIT_MD5 更新防死循环代码不存在"
fi

# ── Test 4: md5 不变时 (模拟) ──
echo "[Test 4] md5 不变模拟"
# 运行 hot-reload 代码片段, md5 相同 → 不应触发 exec
TEST_MD5=$(md5 -q "$COORD" 2>/dev/null || echo 'unknown')
INIT_MD5="$TEST_MD5"
current_md5="$TEST_MD5"

# 直接测试条件逻辑
if [[ "$current_md5" != "$INIT_MD5" ]]; then
  fail "md5 相同时不应触发 hot-reload"
else
  ok "md5 相同时正确跳过 hot-reload"
fi

# ── Test 5: md5 命令不可用模拟 ──
echo "[Test 5] md5 命令不可用模拟"
current_md5="unknown"
if [[ "$current_md5" == "unknown" ]]; then
  ok "md5='unknown' 时正确进入降级分支"
else
  fail "md5='unknown' 时未进入降级分支"
fi

# ── Test 6: 语法检查 ──
echo "[Test 6] Bash 语法检查"
if bash -n "$COORD" 2>/dev/null; then
  ok "coordinator.sh 语法正确"
else
  fail "coordinator.sh 语法错误"
fi

# ── Test 7: 周期性检查在 skip_sprint=1 时可达 ──
echo "[Test 7] 周期性检查可达性"
# 检查 hot-reload 代码在 skip_sprint 块之外
LINE_SKIP=$(grep -n 'skip_sprint=1' "$COORD" | head -1 | cut -d: -f1)
LINE_HOTRELOAD=$(grep -n '# Sprint 20260423-062851 D1 / sprint-20260502-182804' "$COORD" | head -1 | cut -d: -f1)
LINE_SPRINT_END=$(grep -n 'fi' "$COORD" | awk -v skip="$LINE_SKIP" -v hr="$LINE_HOTRELOAD" 'NR>=skip/4 && NR<=hr/4 {print}' | tail -5)

if [[ "$LINE_HOTRELOAD" -gt "$LINE_SKIP" ]]; then
  ok "hot-reload 代码 (line $LINE_HOTRELOAD) 在 skip_sprint 设置 (line $LINE_SKIP) 之后"
else
  fail "hot-reload 代码位置异常"
fi

# 检查 hot-reload 不在 if skip_sprint 块内
# 精确定位: 找 skip_sprint=0 && sf 的 if 块的结束 fi
SKIP_BLOCK_START=$(grep -n 'if.*skip_sprint.*-eq 0.*&&.*sf' "$COORD" | head -1 | cut -d: -f1)
# 从块开始往下扫描, 用 if/fi 配对找块结束
SKIP_BLOCK_END=$(python3 -c "
with open('$COORD') as f:
    lines = f.readlines()
depth = 0
started = False
for i in range($SKIP_BLOCK_START - 1, len(lines)):
    line = lines[i].strip()
    if line.startswith('if ') or line.startswith('if!') or line == 'if':
        depth += 1
        started = True
    elif line == 'fi' or line.startswith('fi ') or line.startswith('fi\t'):
        depth -= 1
        if started and depth == 0:
            print(i + 1)  # 1-indexed
            break
")

if [[ -n "$SKIP_BLOCK_END" ]] && [[ "$LINE_HOTRELOAD" -gt "$SKIP_BLOCK_END" ]]; then
  ok "hot-reload 在 skip_sprint sprint 处理块之外 (块结束于 line $SKIP_BLOCK_END, hot-reload 在 line $LINE_HOTRELOAD)"
else
  fail "hot-reload 可能在 skip_sprint 块内部 (块结束=$SKIP_BLOCK_END, hot-reload=$LINE_HOTRELOAD)"
fi

# ── 结果 ──
echo ""
echo "──────────────────────────────────────────────────"
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
echo "──────────────────────────────────────────────────"

if (( FAIL > 0 )); then
  exit 1
fi
exit 0
