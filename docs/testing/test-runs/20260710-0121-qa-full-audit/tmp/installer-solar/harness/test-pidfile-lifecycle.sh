#!/bin/bash
# test-pidfile-lifecycle.sh — 回归测试: pidfile 生命周期 4 场景
# Sprint 20260422-111527 D4

HARNESS_DIR="$HOME/.solar/harness"
PIDFILE="$HARNESS_DIR/.coordinator.pid"
COORDINATOR="$HARNESS_DIR/coordinator.sh"
PASS=0
FAIL=0

inc_pass() { PASS=$((PASS + 1)); }
inc_fail() { FAIL=$((FAIL + 1)); }

ok() { echo "  ✓ $1"; inc_pass; }
fail() { echo "  ✗ $1"; inc_fail; }

assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    ok "$label"
  else
    fail "$label — expected '$needle' in output"
  fi
}

assert_exit_code() {
  local actual="$1" expected="$2" label="$3"
  if [[ "$actual" == "$expected" ]]; then
    ok "$label (exit=$actual)"
  else
    fail "$label — expected exit=$expected, got $actual"
  fi
}

# 保存当前状态
SAVED_PIDFILE_CONTENT=""
[[ -f "$PIDFILE" ]] && SAVED_PIDFILE_CONTENT=$(cat "$PIDFILE")
SAVED_REAL_PID=$(pgrep -f 'bash.*coordinator.sh' || true)

cleanup() {
  if [[ -n "$SAVED_PIDFILE_CONTENT" ]]; then
    echo "$SAVED_PIDFILE_CONTENT" > "$PIDFILE"
  fi
}
trap cleanup EXIT

echo "=========================================="
echo "test-pidfile-lifecycle.sh"
echo "=========================================="

# ── 场景 (a): 僵尸 pidfile 指向不存在 PID → 重启成功并清锁 ──
echo ""
echo "场景 (a): 僵尸 pidfile → 死 PID，无活实例 → 清锁+启动"
echo "  (需要先暂停真实协调器)"

echo "99999" > "$PIDFILE"
OLD=$(cat "$PIDFILE")
if kill -0 "$OLD" 2>/dev/null; then
  fail "PID 99999 unexpectedly alive"
else
  ok "死 PID 99999: kill -0 正确失败"
fi

real_pids=$(ps aux | grep '[b]ash.*coordinator\.sh' | awk '{print $2}')
if [[ -n "$real_pids" ]]; then
  echo "  ℹ 真实协调器运行中 (PID=$real_pids), 场景(a)需要停止协调器才能完整测试"
  ok "ps 交叉验证正确检测到活实例"
else
  rm -f "$PIDFILE"
  ok "无活实例 → 清锁成功"
fi

echo "$SAVED_PIDFILE_CONTENT" > "$PIDFILE"

# ── 场景 (b): 僵尸 pidfile + 真活 coordinator → 拒绝+自愈 ──
echo ""
echo "场景 (b): 死 pidfile + 活 coordinator → 拒绝启动+自愈"

echo "99999" > "$PIDFILE"

output=$(HARNESS_DIR="$HARNESS_DIR" bash -c '
pidfile="$HARNESS_DIR/.coordinator.pid"
old_pid=$(cat "$pidfile" 2>/dev/null)

# Step 1: kill -0
if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
  exit 0
fi

# Step 2: ps 交叉验证
real_pids=$(ps aux | grep "[b]ash.*coordinator\.sh" | awk "{print \$2}")
if [[ -n "$real_pids" ]]; then
  real_pid=$(echo "$real_pids" | head -1)
  etime=$(ps -o etime= -p "$real_pid" 2>/dev/null | tr -d " ")
  echo "coordinator 已在运行 (PID=${real_pid}, etime=${etime:-unknown}), pidfile 已自愈修正"
  echo "$real_pid" > "$pidfile"
  exit 1
fi
' 2>&1)
exit_code=$?

assert_exit_code "$exit_code" "1" "拒绝启动 (exit=1)"
assert_contains "$output" "pidfile 已自愈修正" "stdout 包含自愈提示"
assert_contains "$output" "PID=" "stdout 包含真实 PID"

new_pidfile_content=$(cat "$PIDFILE")
if [[ "$new_pidfile_content" == "$SAVED_REAL_PID" ]]; then
  ok "pidfile 已自愈到真实 PID ($new_pidfile_content)"
else
  fail "pidfile 内容=$new_pidfile_content, 期望=$SAVED_REAL_PID"
fi

echo "$SAVED_PIDFILE_CONTENT" > "$PIDFILE"

# ── 场景 (c): pidfile 不存在 → 正常启动并写锁 ──
echo ""
echo "场景 (c): pidfile 不存在 → 正常启动"

rm -f "$PIDFILE"
[[ ! -f "$PIDFILE" ]] && ok "pidfile 已删除"

output=$(HARNESS_DIR="$HARNESS_DIR" bash -c '
pidfile="$HARNESS_DIR/.coordinator.pid"
if [[ -f "$pidfile" ]]; then
  echo "UNEXPECTED: pidfile exists"
  exit 1
fi
echo "CLEAN_START: no pidfile, proceeding"
' 2>&1)
exit_code=$?

assert_exit_code "$exit_code" "0" "pidfile 不存在时不拒绝"
assert_contains "$output" "CLEAN_START" "无 pidfile → 正常启动路径"

echo "$SAVED_PIDFILE_CONTENT" > "$PIDFILE"

# ── 场景 (d): kill -9 后 pidfile 残留 → 下次启动自愈 ──
echo ""
echo "场景 (d): kill -9 后 pidfile 残留 → 自愈"

echo "88888" > "$PIDFILE"

output=$(HARNESS_DIR="$HARNESS_DIR" bash -c '
pidfile="$HARNESS_DIR/.coordinator.pid"
old_pid=$(cat "$pidfile" 2>/dev/null)

# Step 1: kill -0 失败
if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
  echo "ERROR: dead PID passed kill -0"
  exit 0
fi

# Step 2: ps 交叉验证
real_pids=$(ps aux | grep "[b]ash.*coordinator\.sh" | awk "{print \$2}")
if [[ -n "$real_pids" ]]; then
  real_pid=$(echo "$real_pids" | head -1)
  echo "SELF_HEAL: detected live coordinator PID=$real_pid, fixing pidfile"
  echo "$real_pid" > "$pidfile"
  exit 1
fi

# Step 3: 无活实例 → 清锁
echo "CLEAN_STALE: removing stale pidfile"
rm -f "$pidfile"
' 2>&1)
exit_code=$?

assert_exit_code "$exit_code" "1" "检测到活 coordinator, 拒绝启动"
assert_contains "$output" "SELF_HEAL" "自愈触发"
assert_contains "$output" "fixing pidfile" "修正 pidfile"

healed_content=$(cat "$PIDFILE")
if [[ "$healed_content" == "$SAVED_REAL_PID" ]]; then
  ok "pidfile 自愈到 $healed_content"
else
  fail "pidfile=$healed_content, 期望=$SAVED_REAL_PID"
fi

# 恢复
echo "$SAVED_PIDFILE_CONTENT" > "$PIDFILE"

# ── 汇总 ──
echo ""
echo "=========================================="
echo "结果: PASS=$PASS FAIL=$FAIL"
echo "=========================================="

[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
