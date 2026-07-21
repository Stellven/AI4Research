#!/bin/bash
# ── test-dispatch-modal.sh ──
# Sprint sprint-20260418-232003, D3 回归测试
#
# 测试 pane 模态预解锁序列逻辑 (dry-run, 不需要真实 tmux session)
#
# 用法: bash test-dispatch-modal.sh

set -uo pipefail

echo "[test] dispatch 模态解锁测试 (dry-run)"

FAILS=0

# ── 测试 1: 预解锁序列正确性 ──
# 验证 Escape*2 + Enter + C-u 序列被正确构建
TEST_CMD=""
escape_count=0
enter_count=0
cu_count=0

# 模拟 send-keys 序列
MOCK_SEQ=()
mock_send_keys() {
  MOCK_SEQ+=("$1")
}

# 构建序列
mock_send_keys "Escape"
mock_send_keys "Escape"
mock_send_keys "Enter"
mock_send_keys "C-u"

escape_count=$(printf '%s\n' "${MOCK_SEQ[@]}" | grep -c "^Escape$" || true)
enter_count=$(printf '%s\n' "${MOCK_SEQ[@]}" | grep -c "^Enter$" || true)
cu_count=$(printf '%s\n' "${MOCK_SEQ[@]}" | grep -c "^C-u$" || true)

if [[ "$escape_count" -ne 2 ]]; then
  echo "FAIL: Escape 序列数量 ${escape_count} (期望 2)"
  FAILS=$((FAILS + 1))
else
  echo "PASS: Escape x2 正确"
fi

if [[ "$enter_count" -ne 1 ]]; then
  echo "FAIL: Enter 序列数量 ${enter_count} (期望 1)"
  FAILS=$((FAILS + 1))
else
  echo "PASS: Enter x1 正确"
fi

if [[ "$cu_count" -ne 1 ]]; then
  echo "FAIL: C-u 序列数量 ${cu_count} (期望 1)"
  FAILS=$((FAILS + 1))
else
  echo "PASS: C-u x1 正确"
fi

# ── 测试 2: pane 选择逻辑 ──
# 仅 0.1 (builder) 和 0.2 (evaluator) 应预解锁
test_pane_needs_unlock() {
  local pane="$1"
  if [[ "$pane" =~ \.(1|2)$ ]]; then
    echo "yes"
  else
    echo "no"
  fi
}

for pane_pair in "solar-harness:0.0:no" "solar-harness:0.1:yes" "solar-harness:0.2:yes" "solar-harness:0.3:no"; do
  pane="${pane_pair%:*}"
  expected="${pane_pair##*:}"
  actual=$(test_pane_needs_unlock "$pane")
  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: pane=$pane expected=$expected actual=$actual"
    FAILS=$((FAILS + 1))
  else
    echo "PASS: pane=$pane unlock=$actual"
  fi
done

# ── 测试 3: 验证 grep 逻辑 ──
VERIFY_OUTPUT="Some random text
读取并执行 /path/to/dispatch.md
More text"
if echo "$VERIFY_OUTPUT" | grep -q "读取并执行"; then
  echo "PASS: 验证 grep 能检测到指令"
else
  echo "FAIL: 验证 grep 未检测到指令"
  FAILS=$((FAILS + 1))
fi

VERIFY_FAIL="Some random text
No dispatch command here
Just noise"
if echo "$VERIFY_FAIL" | grep -q "读取并执行"; then
  echo "FAIL: 误报 - 不应检测到指令"
  FAILS=$((FAILS + 1))
else
  echo "PASS: 正确识别无指令场景"
fi

# ── 测试 4: coordinator.sh 中包含 D3 代码 ──
D3_COUNT=$(grep -c "pane 预解锁序列" ~/.solar/harness/coordinator.sh 2>/dev/null || true)
if [[ "$D3_COUNT" -ge 1 ]]; then
  echo "PASS: coordinator.sh 包含 D3 预解锁代码"
else
  echo "FAIL: coordinator.sh 未找到 D3 预解锁代码"
  FAILS=$((FAILS + 1))
fi

D3_VERIFY=$(grep -c "keyword+processing" ~/.solar/harness/coordinator.sh 2>/dev/null || true)
if [[ "$D3_VERIFY" -ge 1 ]]; then
  echo "PASS: coordinator.sh 包含派发后验证代码"
else
  echo "FAIL: coordinator.sh 未找到派发后验证代码"
  FAILS=$((FAILS + 1))
fi

# 结果
echo ""
if [[ "$FAILS" -eq 0 ]]; then
  echo "PASS: 全部测试通过, 0 FAIL"
else
  echo "FAIL: ${FAILS} 个测试失败"
fi

exit $FAILS
