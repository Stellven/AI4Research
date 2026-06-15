#!/bin/bash
# ── test-save-state-race.sh ──
# Sprint sprint-20260418-232003, D1 回归测试
#
# 模拟 100 次并发 save_state, 验证无 `:` 或空行出现
#
# 用法: bash test-save-state-race.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
COORD_STATE="$HARNESS_DIR/.coordinator-state"
TEST_STATE="$HARNESS_DIR/.test-race-state"
CONCURRENT=100

[[ -f "$HARNESS_DIR/lib/portable.sh" ]] && . "$HARNESS_DIR/lib/portable.sh"

echo "[test] save_state 竞态测试: ${CONCURRENT} 并发写"

# 备份原始 state
if [[ -f "$COORD_STATE" ]]; then
  cp "$COORD_STATE" "${COORD_STATE}.pre-test"
fi

# 用测试 state 文件 (不污染真实 state)
TEST_STATE_ARG="$TEST_STATE"

# 模拟 save_state 函数 (与 coordinator.sh 一致)
atomic_write() {
  local value="$1"
  if [[ -z "$value" ]] || [[ ! "$value" =~ [a-zA-Z] ]]; then
    return 1
  fi
  local encoded
  encoded=$(printf '%s' "$value" | solar_base64_one_line)
  python3 -c "
import tempfile, os, base64
value = base64.b64decode('$encoded').decode('utf-8')
path = '$TEST_STATE_ARG'
dirn = os.path.dirname(path)
os.makedirs(dirn, exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=dirn, suffix='.tmp')
with os.fdopen(fd, 'w') as f:
    f.write(value + '\n')
    f.flush()
    os.fsync(f.fileno())
os.rename(tmp, path)
" 2>/dev/null
}

# 清空测试文件
echo "init" > "$TEST_STATE"

# 启动 100 个并发写
PIDS=()
STATES=("active" "planning" "approved" "reviewing" "passed" "failed" "drafting" "cancelled")
for i in $(seq 1 $CONCURRENT); do
  state="${STATES[$((i % ${#STATES[@]}))]}"
  atomic_write "$state" &
  PIDS+=($!)
done

# 等待全部完成
for pid in "${PIDS[@]}"; do
  wait "$pid" 2>/dev/null
done

# 验证结果
echo "[test] 全部 ${CONCURRENT} 写完成, 验证..."

FAILS=0

# 检查 1: 文件存在
if [[ ! -f "$TEST_STATE" ]]; then
  echo "FAIL: state 文件不存在"
  FAILS=$((FAILS + 1))
fi

# 检查 2: 无空行
EMPTY_LINES=$(grep -c '^$' "$TEST_STATE" 2>/dev/null || true)
EMPTY_LINES=$(echo "$EMPTY_LINES" | tr -d '[:space:]')
if [[ "${EMPTY_LINES:-0}" -gt 0 ]]; then
  echo "FAIL: 发现 ${EMPTY_LINES} 个空行"
  FAILS=$((FAILS + 1))
fi

# 检查 3: 无只含冒号的行
COLON_LINES=$(grep -c '^:$' "$TEST_STATE" 2>/dev/null || true)
COLON_LINES=$(echo "$COLON_LINES" | tr -d '[:space:]')
if [[ "${COLON_LINES:-0}" -gt 0 ]]; then
  echo "FAIL: 发现 ${COLON_LINES} 个冒号行"
  FAILS=$((FAILS + 1))
fi

# 检查 4: 内容是有效状态值
ACTUAL=$(cat "$TEST_STATE" | head -1)
VALID=0
for s in "${STATES[@]}"; do
  if [[ "$ACTUAL" == "$s" ]]; then
    VALID=1
    break
  fi
done
if [[ "$VALID" -eq 0 ]]; then
  echo "FAIL: 最终值 [${ACTUAL}] 不是有效状态"
  FAILS=$((FAILS + 1))
fi

# 检查 5: 文件不是空的
if [[ ! -s "$TEST_STATE" ]]; then
  echo "FAIL: state 文件为空"
  FAILS=$((FAILS + 1))
fi

# 检查 6: GNU base64 默认 76 字符换行，长 coordinator fingerprint 仍必须可写
LONG_STATE="sprint-20260615-long-base64-fingerprint:drafting:prd_ready:planner:1234567890abcdef1234567890abcdef1234567890abcdef"
if ! atomic_write "$LONG_STATE"; then
  echo "FAIL: 长 fingerprint 写入失败"
  FAILS=$((FAILS + 1))
elif [[ "$(head -1 "$TEST_STATE")" != "$LONG_STATE" ]]; then
  echo "FAIL: 长 fingerprint 写入后内容不一致"
  FAILS=$((FAILS + 1))
fi

# 清理
rm -f "$TEST_STATE"
if [[ -f "${COORD_STATE}.pre-test" ]]; then
  mv "${COORD_STATE}.pre-test" "$COORD_STATE"
fi

# 结果
echo ""
if [[ "$FAILS" -eq 0 ]]; then
  echo "PASS: ${CONCURRENT} 并发写, 0 FAIL"
  echo "最终状态: ${ACTUAL}"
else
  echo "FAIL: ${FAILS} 个检查失败"
fi

exit $FAILS
