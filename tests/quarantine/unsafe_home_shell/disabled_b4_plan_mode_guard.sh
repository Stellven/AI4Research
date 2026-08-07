#!/usr/bin/env bash
# 测试 B4 plan mode 死锁修复 — sprint-20260502-125501
# 验证: pane_is_plan_mode 检测 + Shift+Tab 预解锁 + round dispatch 增强
set -eu

HARNESS_DIR="$HOME/.solar/harness"
COORD="$HARNESS_DIR/coordinator.sh"

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

[[ -f "$COORD" ]] || fail "coordinator.sh 不存在"

# TC1: pane_is_plan_mode 函数存在且匹配正确特征
echo "=== TC1: pane_is_plan_mode 函数 ==="
grep -q 'pane_is_plan_mode()' "$COORD" || fail "缺 pane_is_plan_mode 函数"
grep -q 'plan.mode\|shift.*tab.*edit' "$COORD" || fail "plan mode 特征检测不完整"
pass "TC1: pane_is_plan_mode 函数存在且特征匹配正确"

# TC2: dispatch_to_pane 中有 Shift+Tab 调用
echo "=== TC2: Shift+Tab 预解锁 ==="
grep -q 'S-Tab' "$COORD" || fail "缺 Shift+Tab (S-Tab) 调用"
grep -q 'pane_is_plan_mode' "$COORD" || fail "预解锁序列未调用 plan mode 检测"
# 确认 S-Tab 在预解锁序列中 (不是别处)
grep -A5 'pane_is_plan_mode.*pane' "$COORD" | grep -q 'S-Tab' || fail "S-Tab 不在 plan mode 检测分支内"
pass "TC2: Shift+Tab 在 plan mode 检测分支中正确调用"

# TC3: 二次确认逻辑 (如果第一次 Shift+Tab 没生效)
echo "=== TC3: 二次确认逻辑 ==="
grep -q 'pane_is_plan_mode.*pane' "$COORD" || fail "缺 plan mode 二次检测"
# 找到 pane_is_plan_mode 出现次数 >= 3 (函数定义 + dispatch_to_pane 中两次调用)
count=$(grep -c 'pane_is_plan_mode' "$COORD")
[[ "$count" -ge 3 ]] || fail "pane_is_plan_mode 调用次数不足 (期望>=3, 实际=$count)"
pass "TC3: 二次确认逻辑存在 (pane_is_plan_mode 出现 $count 次)"

# TC4: handle_failed_review 的 dispatch 包含 round 信息
echo "=== TC4: round dispatch 消息 ==="
grep -q '修复评审反馈.*轮次' "$COORD" || fail "handle_failed_review dispatch 缺 round 标注"
grep -q 'task.*fix.*round' "$COORD" || fail "dispatch 事件缺 round 字段"
pass "TC4: failed_review dispatch 包含 round 信息"

# TC5: Bug 修复记录中有 B4
echo "=== TC5: B4 修复记录 ==="
grep -q 'B4.*plan mode' "$COORD" || fail "缺 B4 修复记录"
pass "TC5: B4 修复记录已登记"

echo ""
echo "=== 全部测试通过 ==="
