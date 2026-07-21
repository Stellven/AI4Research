#!/usr/bin/env bash
# ================================================================
# Solar Harness — Hot-Reload Trigger Test
# Sprint sprint-20260502-182804 D5
#
# 验证: md5 变化后, 协调器在加速模式下检测到并触发 hot-reload
# 前提: 需要一个运行中的测试协调器实例 (HOT_RELOAD_TICK_OVERRIDE=6)
#
# 用法:
#   bash test-hot-reload-trigger.sh [--dry-run]
#
# @module solar-farm/harness/tests
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
COORD="$HARNESS_DIR/coordinator.sh"
LOG="$HARNESS_DIR/.coordinator.log"
TEST_TMUX="solar-test-hotreload"
TICK_OVERRIDE=6
MAX_WAIT=90

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "  ${G}✓${N} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${R}✗${N} $1"; FAIL=$((FAIL+1)); }
info() { echo -e "  ${C}[info]${N} $1"; }

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

echo ""
echo "══════════════════════════════════════════════════"
echo "  Hot-Reload Trigger Test (sprint-20260502-182804)"
echo "══════════════════════════════════════════════════"
echo ""

# ── Step 1: 备份 coordinator.sh ──
BACKUP="/tmp/test-hot-reload-trigger-backup-$$"
cp "$COORD" "$BACKUP"
info "coordinator.sh 已备份到 $BACKUP"

restore() {
  if [[ -f "$BACKUP" ]]; then
    cp "$BACKUP" "$COORD"
    rm -f "$BACKUP"
    info "coordinator.sh 已还原"
  fi
  # 清理测试 tmux session
  if tmux has-session -t "$TEST_TMUX" 2>/dev/null; then
    tmux kill-session -t "$TEST_TMUX" 2>/dev/null || true
    info "测试 tmux session 已清理"
  fi
}
trap restore EXIT

if $DRY_RUN; then
  info "DRY RUN — 跳过实际测试"
  exit 0
fi

# ── Step 2: 启动测试协调器 ──
# 使用独立 tmux session, 不影响生产实例
OLD_LOG_SIZE=$(wc -c < "$LOG" 2>/dev/null || echo 0)

tmux kill-session -t "$TEST_TMUX" 2>/dev/null || true
tmux new-session -d -s "$TEST_TMUX" \
  -x 200 -y 50 \
  "HOT_RELOAD_TICK_OVERRIDE=$TICK_OVERRIDE bash $COORD 2>&1 | tee -a $LOG.test-hotreload"

info "测试协调器已启动 (tmux=$TEST_TMUX, TICK=$TICK_OVERRIDE)"
sleep 5

# 验证测试协调器在跑
if ! tmux has-session -t "$TEST_TMUX" 2>/dev/null; then
  fail "测试协调器未启动 (tmux session 不存在)"
  exit 1
fi
ok "测试协调器运行中"

# ── Step 3: 记录当前 md5 ──
OLD_MD5=$(md5 -q "$COORD" 2>/dev/null || echo 'unknown')
ok "当前 MD5=${OLD_MD5}"

# ── Step 4: 追加注释修改 md5 ──
MARKER="# hot-reload-test-trigger-$$-$(date +%s)"
echo "$MARKER" >> "$COORD"
NEW_MD5=$(md5 -q "$COORD" 2>/dev/null || echo 'unknown')
ok "修改后 MD5=${NEW_MD5}"

if [[ "$NEW_MD5" == "$OLD_MD5" ]]; then
  fail "MD5 未变化 (追加注释失败?)"
  exit 1
fi

# ── Step 5: 等待 hot-reload 触发 ──
info "等待最多 ${MAX_WAIT} 秒, 检测 [hot-reload] 日志..."
FOUND=false
for ((i=0; i<MAX_WAIT; i+=5)); do
  # 检查测试协调器 log (tmux pane 输出)
  PANE_OUTPUT=$(tmux capture-pane -t "$TEST_TMUX" -p 2>/dev/null || true)
  if echo "$PANE_OUTPUT" | grep -q '\[hot-reload\].*md5 changed'; then
    FOUND=true
    ok "检测到 [hot-reload] md5 changed (等待了 ${i}s)"
    break
  fi
  sleep 5
done

if ! $FOUND; then
  fail "等待 ${MAX_WAIT}s 后未检测到 [hot-reload] md5 changed"
  echo "tmux pane 最后 20 行:"
  tmux capture-pane -t "$TEST_TMUX" -p 2>/dev/null | tail -20 | sed 's/^/    /'
fi

# ── Step 6: 验证 PID 变化 ──
PIDFILE="$HARNESS_DIR/.coordinator.pid"
if [[ -f "$PIDFILE" ]]; then
  NEW_PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
  if [[ -n "$NEW_PID" ]] && kill -0 "$NEW_PID" 2>/dev/null; then
    ok "协调器仍在运行 (PID=${NEW_PID})"
    # 检查进程 etime
    ETIME=$(ps -p "$NEW_PID" -o etime= 2>/dev/null | tr -d ' ' || echo "unknown")
    info "进程 etime=${ETIME}"
  else
    fail "协调器 PID=${NEW_PID:-empty} 不活跃"
  fi
else
  fail "pidfile 不存在"
fi

# ── 结果 ──
echo ""
echo "──────────────────────────────────────────────────"
echo -e "  ${G}PASS: ${PASS}${N}  ${R}FAIL: ${FAIL}${N}"
echo "──────────────────────────────────────────────────"

# restore 由 trap EXIT 触发
if (( FAIL > 0 )); then
  exit 1
fi
exit 0
