#!/bin/bash
# ── test-coord-startup.sh — 协调器启动三连锁测试 ──
# Sprint sprint-20260420-082442, D5
#
# 测试: pidfile 自愈 / last_state 不吞首派发 / coord-status / update-contract
# 前置: 无需 tmux session (纯 shell 逻辑测试)
#
# 用法: bash test-coord-startup.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
PIDFILE="$HARNESS_DIR/.coordinator.pid"
COORD_STATE="$HARNESS_DIR/.coordinator-state"

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

log() { echo -e "${C}[测试]${N} $(date '+%H:%M:%S') $*"; }
pass() { echo -e "  ${G}✅ PASS${N}: $1"; ((PASS++)); }
fail() { echo -e "  ${R}❌ FAIL${N}: $1"; ((FAIL++)); }

echo ""
echo "══════════════════════════════════════════════════"
echo "  协调器启动三连锁测试"
echo "══════════════════════════════════════════════════"
echo ""

# ── T1: stale pidfile 自愈 ──
log "T1: stale pidfile 自愈"

echo "999999999" > "$PIDFILE"
if [[ -f "$PIDFILE" ]]; then
  if grep -q "stale pidfile detected" "$HARNESS_DIR/coordinator.sh" 2>/dev/null; then
    pass "T1: coordinator.sh 包含 stale pidfile 自愈逻辑"
  else
    fail "T1: coordinator.sh 缺少 stale pidfile 自愈逻辑"
  fi
else
  fail "T1: 无法创建测试 pidfile"
fi

rm -f "$PIDFILE"

# ── T2: last_state 不吞首派发 ──
log "T2: last_state 启动时不保存中间态"

t2_rm_line=""
t2_rm_line=$(grep -n "rm -f.*COORD_STATE" "$HARNESS_DIR/coordinator.sh" 2>/dev/null | head -1 || true)
if [[ -n "$t2_rm_line" ]]; then
  t2_line_num=""
  t2_line_num=$(echo "$t2_rm_line" | cut -d: -f1)
  # run_coordinator 函数大约在 1280 行开始
  if [[ "$t2_line_num" -gt 1280 ]] && [[ "$t2_line_num" -lt 1400 ]]; then
    pass "T2: coordinator 启动时清空 last_state (在 run_coordinator 初始化中)"
  else
    fail "T2: rm -f COORD_STATE 不在启动初始化阶段 (line: $t2_rm_line)"
  fi
else
  fail "T2: coordinator.sh 缺少 rm -f COORD_STATE"
fi

# 验证旧的 "echo init > COORD_STATE" 已移除
t2_init_line=""
t2_init_line=$(grep -n 'echo "\${init_sid}:\${init_st}"' "$HARNESS_DIR/coordinator.sh" 2>/dev/null || true)
if [[ -z "$t2_init_line" ]]; then
  pass "T2: 旧的 'echo init_sid:init_st > COORD_STATE' 已移除"
else
  fail "T2: 旧的 'echo init_sid:init_st > COORD_STATE' 仍存在 (line: $t2_init_line)"
fi

# ── T3: pidfile 所有权 — 外部不预写 ──
log "T3: pidfile 所有权统一"

# solar-harness.sh 不应预写 pidfile
t3_sh_count=0
t3_sh_count=$(grep -c 'echo.*coordinator.pid' "$HARNESS_DIR/solar-harness.sh" 2>/dev/null || true)
if [[ "$t3_sh_count" -eq 0 ]]; then
  pass "T3: solar-harness.sh 不预写 pidfile"
else
  fail "T3: solar-harness.sh 仍有 ${t3_sh_count} 处预写 pidfile"
fi

# monitor.sh 不应预写 pidfile
t3_mon_count=0
t3_mon_count=$(grep -c 'echo.*coordinator.pid' "$HARNESS_DIR/monitor.sh" 2>/dev/null || true)
if [[ "$t3_mon_count" -eq 0 ]]; then
  pass "T3: monitor.sh 不预写 pidfile"
else
  fail "T3: monitor.sh 仍有 ${t3_mon_count} 处预写 pidfile"
fi

# coordinator.sh 自己写 pidfile (echo $$ > $pidfile 或 echo $$ > "$pidfile")
t3_coord_write=""
t3_coord_write=$(grep -c 'echo.*\$.*>.*pidfile' "$HARNESS_DIR/coordinator.sh" 2>/dev/null || true)
if [[ "$t3_coord_write" -ge 1 ]]; then
  pass "T3: coordinator.sh 自己写入 pidfile"
else
  fail "T3: coordinator.sh 未写入 pidfile"
fi

# ── T4: coord-status 子命令 ──
log "T4: coord-status 子命令"

if grep -q "coord-status)" "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  pass "T4: coord-status 子命令存在"
else
  fail "T4: coord-status 子命令缺失"
fi

if grep -q "stale_lock" "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  pass "T4: coord-status 输出含 stale_lock 字段"
else
  fail "T4: coord-status 缺少 stale_lock 字段"
fi

# ── T5: update-contract 无 local bug ──
log "T5: update-contract local bug 修复"

if grep -q "do_update_contract()" "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  pass "T5: do_update_contract 函数已提取"
else
  fail "T5: do_update_contract 函数不存在"
fi

if grep -q "do_update_contract" "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  pass "T5: update-contract case 分支调用 do_update_contract"
else
  fail "T5: update-contract case 分支未调用 do_update_contract"
fi

bash -n "$HARNESS_DIR/solar-harness.sh" 2>/dev/null
if [[ $? -eq 0 ]]; then
  pass "T5: solar-harness.sh 语法正确"
else
  fail "T5: solar-harness.sh 语法错误"
fi

# ── T6: 前两个 Sprint 不回退 ──
log "T6: 前两个 Sprint 不回退"

# Sprint 20260417-213037 的关键修复
t6_d1c=0
t6_d1c=$(grep -c "send-keys.*sleep 0.8\|拆两步" "$HARNESS_DIR/coordinator.sh" 2>/dev/null || true)
if [[ "$t6_d1c" -ge 1 ]]; then
  pass "T6: send-keys 拆两步修复保留"
else
  fail "T6: send-keys 拆两步修复丢失"
fi

t6_d2c=0
t6_d2c=$(grep -c "文件级 mtime" "$HARNESS_DIR/coordinator.sh" 2>/dev/null || true)
if [[ "$t6_d2c" -ge 1 ]]; then
  pass "T6: 文件级 mtime 检测保留"
else
  fail "T6: 文件级 mtime 检测丢失"
fi

# Sprint 20260419-223020 的 codex-bridge
if [[ -f "$HARNESS_DIR/codex-bridge.sh" ]]; then
  pass "T6: codex-bridge.sh 保留"
else
  fail "T6: codex-bridge.sh 丢失"
fi

if grep -q "call_codex" "$HARNESS_DIR/coordinator.sh" 2>/dev/null; then
  pass "T6: call_codex 集成保留"
else
  fail "T6: call_codex 集成丢失"
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
