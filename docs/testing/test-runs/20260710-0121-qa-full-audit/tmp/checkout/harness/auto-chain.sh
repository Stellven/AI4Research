#!/bin/bash
# Solar Auto-Chain — 上一个 sprint PASSED 后自动起队列下一个
# 由规划者起一次,后台常驻
QUEUE=~/.solar/harness/queue/sprint-queue.txt
LOG=~/.solar/harness/.auto-chain.log
PIDFILE=~/.solar/harness/.auto-chain.pid
HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SPRINTS_DIR="$HARNESS_DIR/sprints"

# 单实例锁
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "auto-chain 已在运行 (PID $(cat "$PIDFILE"))" >&2
  exit 0
fi
echo $$ > "$PIDFILE"
trap "rm -f $PIDFILE" EXIT

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
log "auto-chain 启动 PID=$$"

# 取队列下一个非注释行
next_line() {
  grep -v '^#' "$QUEUE" 2>/dev/null | grep -v '^$' | head -1
}
consume_line() {
  local line="$1"
  local tmp=$(mktemp)
  awk -v target="$line" '$0 != target' "$QUEUE" > "$tmp" && mv "$tmp" "$QUEUE"
}

while true; do
  # 是否有 active/planning/reviewing sprint?
  ACTIVE=$(grep -lE ""status":"(active|planning|approved|reviewing|failed_review|drafting)"" ~/.solar/harness/sprints/*.status.json 2>/dev/null | head -1)
  if [[ -n "$ACTIVE" ]]; then
    sleep 30
    continue
  fi

  # 没有正在跑 → 起队列下一个
  LINE=$(next_line)
  [[ -z "$LINE" ]] && { log "队列空,继续等"; sleep 60; continue; }

  TITLE="${LINE%%|*}"
  REQUIREMENT="${LINE#*|}"
  log "起新 sprint: $TITLE"
  
  # 创建 sprint
  RESULT=$(~/.solar/bin/solar-harness sprint "[Auto-Chain] $TITLE: $REQUIREMENT" 2>&1)
  SID=$(echo "$RESULT" | grep -oE 'sprint-[0-9-]+' | head -1)
  log "  → $SID"
  
  # 简单 Done (规划者也可以再修)
  ~/.solar/bin/solar-harness update-contract "$SID" done "- [ ] D1: $REQUIREMENT
  <!-- verify: cmd=\"echo placeholder\" expected_exit=0 output_pattern=\".*\" -->
- [ ] D2: handoff 含实测证据 (改动文件列表 + 验证命令输出)
  <!-- verify: cmd=\"test -f ~/.solar/harness/sprints/$SID.handoff.md\" expected_exit=0 output_pattern=\".*\" -->" >> "$LOG" 2>&1
  
  # active
  python3 "$HARNESS_DIR/lib/runtime_status.py" "$SPRINTS_DIR/$SID.status.json" "active" "auto_chain_started" "auto-chain" '{}' >/dev/null 2>&1 || true
  
  # 消费队列
  consume_line "$LINE"
  log "  active triggered, 等下次轮询"
  sleep 60
done
