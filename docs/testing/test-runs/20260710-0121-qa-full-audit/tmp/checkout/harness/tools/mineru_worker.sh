#!/usr/bin/env bash
# MinerU background queue worker — io.solar.mineru-worker
# Reads ~/.solar/queues/mineru.jsonl, processes queued PDF extraction jobs
# Idle guard: pauses when user is active (HIDIdleTime < 60s OR claude procs > 0)

set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
QUEUE_FILE="$HOME/.solar/queues/mineru.jsonl"
LOCK_FILE="$HOME/.solar/queues/mineru.worker.lock"
LOG_FILE="$HOME/.solar/logs/mineru-worker.log"
EXTRACT_PY="$HARNESS_DIR/lib/mineru_extract.py"

mkdir -p "$HOME/.solar/queues" "$HOME/.solar/logs"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE" 2>/dev/null || true; }

# Idle guard: returns 0 if idle (safe to run), 1 if user is active
is_idle() {
  # Check HIDIdleTime (nanoseconds → seconds)
  local idle_ns
  idle_ns=$(ioreg -c IOHIDSystem 2>/dev/null | awk '/HIDIdleTime/ {print $NF; exit}' || echo 0)
  local idle_s=$(( idle_ns / 1000000000 ))

  if [[ $idle_s -ge 60 ]]; then
    return 0  # idle
  fi

  # Also consider idle if no active claude processes
  local claude_count
  claude_count=$(pgrep -fc "claude" 2>/dev/null || echo 0)
  if [[ "$claude_count" -eq 0 ]]; then
    return 0
  fi

  return 1  # user is active
}

# Dequeue one job (returns json or empty)
dequeue_job() {
  [[ ! -f "$QUEUE_FILE" ]] && return 0
  local first_line
  first_line=$(head -1 "$QUEUE_FILE" 2>/dev/null || true)
  if [[ -z "$first_line" ]]; then return 0; fi

  # Remove first line from queue
  local tmp; tmp=$(mktemp)
  tail -n +2 "$QUEUE_FILE" > "$tmp" && mv "$tmp" "$QUEUE_FILE"
  echo "$first_line"
}

log "worker started (pid=$$)"

while true; do
  # Idle guard
  if ! is_idle; then
    log "user active — sleeping 30s"
    sleep 30
    continue
  fi

  # Check queue
  job=$(dequeue_job)
  if [[ -z "$job" ]]; then
    sleep 60
    continue
  fi

  # Parse job fields
  pdf=$(echo "$job" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('pdf',''))" 2>/dev/null || true)
  vault=$(echo "$job" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('vault',''))" 2>/dev/null || true)

  if [[ -z "$pdf" ]]; then
    log "bad job (no pdf field): $job"
    continue
  fi

  log "processing: $pdf"
  if python3 "$EXTRACT_PY" "$pdf" ${vault:+--vault "$vault"} --json >> "$LOG_FILE" 2>&1; then
    log "done: $pdf"
  else
    log "failed: $pdf"
  fi

  sleep 5  # brief pause between jobs
done
