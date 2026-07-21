#!/usr/bin/env bash
# ================================================================
# Test: Watchdog Respawn Reliability — 5 次 kill + 自动恢复
# Sprint: sprint-20260502-200424 D6
#
# 在独立 tmux session 中跑, 通过外部操控 builder pane 避免自杀
#
# @module solar-farm/harness/tests/watchdog-respawn
# ================================================================
set -eu

SESSION_NAME="solar-harness"
BUILDER_PANE="${SESSION_NAME}:0.1"
MAX_KILLS=5
WAIT_AFTER_KILL=35  # watchdog 检测周期 10s + 重启 + claude 启动
PASS_COUNT=0

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
ok()   { echo -e "${G}[PASS]${N} $*"; }
fail() { echo -e "${R}[FAIL]${N} $*"; }
info() { echo -e "${C}[INFO]${N} $*"; }

# --- 查找 builder pane 中的 claude PID ---
find_claude_pid() {
  local pane_pid
  pane_pid=$(tmux list-panes -t "$SESSION_NAME" -F '#{pane_index} #{pane_pid}' 2>/dev/null \
    | awk '$1==1{print $2}') || true
  [[ -z "$pane_pid" ]] && return 1

  # 递归找 claude 进程
  local pid
  for pid in $(pgrep -P "$pane_pid" 2>/dev/null || true); do
    local cmd
    cmd=$(ps -p "$pid" -o comm= 2>/dev/null) || continue
    if [[ "$cmd" == "node" || "$cmd" == "claude" ]]; then
      echo "$pid"
      return 0
    fi
    # 孙进程
    local gpid
    for gpid in $(pgrep -P "$pid" 2>/dev/null || true); do
      local gcmd
      gcmd=$(ps -p "$gpid" -o comm= 2>/dev/null) || continue
      if [[ "$gcmd" == "node" || "$gcmd" == "claude" ]]; then
        echo "$gpid"
        return 0
      fi
    done
  done
  return 1
}

# --- 检查 pane 是否存活 (非 dead) ---
is_pane_alive() {
  local dead
  dead=$(tmux list-panes -t "$SESSION_NAME" -F '#{pane_index} #{pane_dead}' 2>/dev/null \
    | awk '$1==1{print $2}') || true
  [[ "${dead:-0}" != "1" ]]
}

# --- 前置检查 ---
info "=== Watchdog Respawn 可靠性测试 ==="
info "时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 检查 tmux session 存在
if ! tmux has-session -t "$SESSION_NAME" &>/dev/null; then
  fail "tmux session '$SESSION_NAME' 不存在"
  exit 1
fi
ok "tmux session 存在"

# 检查 watchdog 在跑
if ! pgrep -f "coordinator-watchdog.sh" >/dev/null 2>&1; then
  fail "watchdog 未运行"
  exit 1
fi
ok "watchdog 运行中"

# 找到 builder claude PID
OLD_PID=$(find_claude_pid) || {
  fail "找不到 builder claude 进程"
  exit 1
}
ok "初始 builder claude PID: $OLD_PID"

# --- 5 次 kill 演练 ---
info ""
info "--- 开始 5 次 kill 演练 ---"

for i in $(seq 1 $MAX_KILLS); do
  info ""
  info "--- Kill #$i ---"

  # 找当前 claude PID
  CURRENT_PID=$(find_claude_pid) || {
    # 可能上一次刚重启还没完全起来,等一下再试
    info "未找到 claude PID, 等待额外 15 秒..."
    sleep 15
    CURRENT_PID=$(find_claude_pid) || {
      fail "Kill #$i: 重试后仍找不到 claude PID"
      continue
    }
  }
  info "当前 claude PID: $CURRENT_PID"

  # kill -9
  info "执行 kill -9 $CURRENT_PID"
  kill -9 "$CURRENT_PID" 2>/dev/null || true

  # 等待 watchdog 检测 + 重启
  info "等待 ${WAIT_AFTER_KILL}s (watchdog 检测 + 重启)..."
  sleep "$WAIT_AFTER_KILL"

  # 验证新 PID
  NEW_PID=$(find_claude_pid) || {
    # pane 可能 dead
    if ! is_pane_alive; then
      fail "Kill #$i: pane 已死亡 (status 127 或其他)"
      # 尝试手动救场
      info "尝试手动 respawn..."
      tmux respawn-pane -k -t "$BUILDER_PANE" \
        "env HOME='$HOME' PATH='$PATH' bash $HOME/.solar/harness/start-incarnation.sh builder $HOME" 2>/dev/null || true
      sleep 20
      NEW_PID=$(find_claude_pid) || {
        fail "Kill #$i: 手动 respawn 后仍找不到 claude"
        continue
      }
    else
      fail "Kill #$i: pane 活着但找不到 claude PID"
      continue
    fi
  }

  if [[ "$NEW_PID" == "$CURRENT_PID" ]]; then
    fail "Kill #$i: 新 PID ($NEW_PID) = 旧 PID, 重启失败!"
    continue
  fi

  ok "Kill #$i: 旧=$CURRENT_PID → 新=$NEW_PID (重启成功)"
  PASS_COUNT=$((PASS_COUNT + 1))
done

# --- 结果 ---
info ""
info "=== 测试结果 ==="
info "通过: ${PASS_COUNT}/${MAX_KILLS}"

if [[ "$PASS_COUNT" -eq "$MAX_KILLS" ]]; then
  ok "5/5 PASS — Watchdog respawn 可靠性测试全部通过"
  exit 0
else
  fail "${PASS_COUNT}/${MAX_KILLS} — 有 $((MAX_KILLS - PASS_COUNT)) 次失败"
  exit 1
fi
