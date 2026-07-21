#!/usr/bin/env bash
# qmd-embed-runner.sh — background embedding runner for solar-wiki.

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
[[ -f "$HARNESS_DIR/lib/qmd-resolver.sh" ]] && . "$HARNESS_DIR/lib/qmd-resolver.sh"
QMD_BIN="${QMD_BIN:-$(solar_qmd_bin_or_empty 2>/dev/null || true)}"
solar_export_qmd_runtime_path "$QMD_BIN"
COLLECTION="${QMD_WIKI_COLLECTION:-solar-wiki}"
RUN_DIR="$HARNESS_DIR/run"
STATE_DIR="$HARNESS_DIR/state"
LOCK_DIR="$RUN_DIR/qmd-embed.lockdir"
LOCK_PID_FILE="$LOCK_DIR/pid"
STATUS_FILE="$STATE_DIR/qmd-embed-status.json"
LOG_FILE="$RUN_DIR/qmd-embed.log"
FORCE="${SOLAR_QMD_EMBED_FORCE:-0}"
MODE="${SOLAR_QMD_EMBED_MODE:-gentle}"
[[ "$FORCE" == "1" ]] && MODE="force"

case "$MODE" in
  idle)
    MIN_IDLE_SEC="${SOLAR_QMD_EMBED_MIN_IDLE_SEC:-900}"
    MAX_LOAD_1M="${SOLAR_QMD_EMBED_MAX_LOAD_1M:-4.0}"
    CHECK_INTERVAL="${SOLAR_QMD_EMBED_CHECK_INTERVAL:-20}"
    MAX_RUNTIME_SEC="${SOLAR_QMD_EMBED_MAX_RUNTIME_SEC:-0}"
    ;;
  gentle)
    MIN_IDLE_SEC="${SOLAR_QMD_EMBED_MIN_IDLE_SEC:-0}"
    MAX_LOAD_1M="${SOLAR_QMD_EMBED_MAX_LOAD_1M:-8.0}"
    CHECK_INTERVAL="${SOLAR_QMD_EMBED_CHECK_INTERVAL:-15}"
    # Large vaults can spend several minutes just chunking; too-short slices
    # repeatedly kill qmd before any vectors are written.
    MAX_RUNTIME_SEC="${SOLAR_QMD_EMBED_MAX_RUNTIME_SEC:-1800}"
    ;;
  force)
    MIN_IDLE_SEC="${SOLAR_QMD_EMBED_MIN_IDLE_SEC:-0}"
    MAX_LOAD_1M="${SOLAR_QMD_EMBED_MAX_LOAD_1M:-999.0}"
    CHECK_INTERVAL="${SOLAR_QMD_EMBED_CHECK_INTERVAL:-20}"
    MAX_RUNTIME_SEC="${SOLAR_QMD_EMBED_MAX_RUNTIME_SEC:-0}"
    ;;
  *)
    MODE="gentle"
    MIN_IDLE_SEC="${SOLAR_QMD_EMBED_MIN_IDLE_SEC:-0}"
    MAX_LOAD_1M="${SOLAR_QMD_EMBED_MAX_LOAD_1M:-8.0}"
    CHECK_INTERVAL="${SOLAR_QMD_EMBED_CHECK_INTERVAL:-15}"
    MAX_RUNTIME_SEC="${SOLAR_QMD_EMBED_MAX_RUNTIME_SEC:-1800}"
    ;;
esac
NICE_LEVEL="${SOLAR_QMD_EMBED_NICE:-15}"
# QMD embedding is a background maintenance task, not an interactive query path.
# Prefer CPU by default so native Metal crashes do not wedge the knowledge index;
# set SOLAR_QMD_EMBED_ALLOW_GPU=1 or NODE_LLAMA_CPP_GPU=auto to opt back in.
if [[ -z "${NODE_LLAMA_CPP_GPU:-}" && "${SOLAR_QMD_EMBED_ALLOW_GPU:-0}" != "1" ]]; then
  export NODE_LLAMA_CPP_GPU=false
fi

mkdir -p "$RUN_DIR" "$STATE_DIR"

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

status_json() {
  local state="$1"
  local detail="${2:-}"
  local pending_before="${3:-}"
  local pending_after="${4:-}"
  local idle_seconds="${5:-}"
  local load_1m="${6:-}"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  cat > "$STATUS_FILE" <<EOF
{
  "state": "$state",
  "collection": "$COLLECTION",
  "mode": "$MODE",
  "updated_at": "$ts",
  "pending_before": "${pending_before}",
  "pending_after": "${pending_after}",
  "idle_seconds": "${idle_seconds}",
  "min_idle_seconds": "${MIN_IDLE_SEC}",
  "load_1m": "${load_1m}",
  "max_load_1m": "${MAX_LOAD_1M}",
  "max_runtime_seconds": "${MAX_RUNTIME_SEC}",
  "nice": "${NICE_LEVEL}",
  "detail": "$(printf '%s' "$detail" | json_escape)",
  "log": "$LOG_FILE"
}
EOF
}

pending_count() {
  [[ -n "$QMD_BIN" ]] || { echo ""; return; }
  "$QMD_BIN" status 2>/dev/null | awk '
    /Pending:/ {print $2; found=1; exit}
    END {if (!found) print "0"}
  '
}

idle_seconds() {
  ioreg -c IOHIDSystem 2>/dev/null | awk '/HIDIdleTime/ {print int($NF / 1000000000); exit}'
}

load_1m() {
  sysctl -n vm.loadavg 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i ~ /^[0-9.]+$/) {print $i; exit}}'
}

float_le() {
  awk -v a="${1:-999}" -v b="${2:-0}" 'BEGIN { exit (a <= b ? 0 : 1) }'
}

can_start() {
  [[ "$MODE" == "force" ]] && return 0
  local idle load
  idle="$(idle_seconds || true)"
  load="$(load_1m || true)"
  [[ -n "$idle" ]] || idle=0
  [[ -n "$load" ]] || load=999
  if [[ "$MODE" == "idle" && "$idle" -lt "$MIN_IDLE_SEC" ]]; then
    status_json "idle_wait" "user active; waiting for idle window" "$(pending_count || true)" "" "$idle" "$load"
    return 1
  fi
  if ! float_le "$load" "$MAX_LOAD_1M"; then
    status_json "${MODE}_wait" "system load too high; waiting for ${MODE} slot" "$(pending_count || true)" "" "$idle" "$load"
    return 1
  fi
  return 0
}

can_continue() {
  [[ "$MODE" == "force" ]] && return 0
  local idle load
  idle="$(idle_seconds || true)"
  load="$(load_1m || true)"
  [[ -n "$idle" ]] || idle=0
  [[ -n "$load" ]] || load=999
  if [[ "$MODE" == "idle" && "$idle" -lt "$MIN_IDLE_SEC" ]]; then
    return 1
  fi
  float_le "$load" "$MAX_LOAD_1M"
}

if [[ -z "$QMD_BIN" || ! -x "$QMD_BIN" ]]; then
  status_json "missing" "qmd binary not found"
  exit 0
fi

QMD_BIN_DIR="$(cd "$(dirname "$QMD_BIN")" && pwd)"
export PATH="$QMD_BIN_DIR:$PATH"

if ! can_start; then
  exit 0
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  lock_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
    status_json "locked" "another qmd embed run is active (pid=$lock_pid)"
    exit 0
  fi
  # Legacy/stale lockdirs did not always have a pid file, and native qmd
  # crashes can leave a dead pid file behind. This lockdir is private to the
  # embed runner, so a dead pid makes it safe to reap.
  rm -f "$LOCK_PID_FILE" 2>/dev/null || true
  rmdir "$LOCK_DIR" 2>/dev/null || true
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    status_json "locked" "another qmd embed run is active"
    exit 0
  fi
fi
printf '%s\n' "$$" > "$LOCK_PID_FILE"
trap 'rm -f "$LOCK_PID_FILE"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

before="$(pending_count || true)"
idle="$(idle_seconds || true)"
load="$(load_1m || true)"
status_json "running" "qmd embed started (${MODE})" "$before" "" "$idle" "$load"

{
  start_epoch="$(date +%s)"
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qmd embed -c $COLLECTION started; mode=$MODE pending_before=${before:-N/A}"
  /usr/bin/nice -n "$NICE_LEVEL" "$QMD_BIN" embed -c "$COLLECTION" &
  embed_pid=$!
  while kill -0 "$embed_pid" 2>/dev/null; do
    sleep "$CHECK_INTERVAL"
    now_epoch="$(date +%s)"
    elapsed=$((now_epoch - start_epoch))
    if [[ "$MAX_RUNTIME_SEC" != "0" && "$elapsed" -ge "$MAX_RUNTIME_SEC" ]]; then
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ${MODE} time slice ended; stopping qmd embed pid=$embed_pid elapsed=${elapsed}s"
      kill -TERM "$embed_pid" 2>/dev/null || true
      sleep 3
      kill -KILL "$embed_pid" 2>/dev/null || true
      wait "$embed_pid" 2>/dev/null || true
      after="$(pending_count || true)"
      status_json "paused" "${MODE} time slice ended; will continue next launchd tick" "$before" "$after" "$(idle_seconds || true)" "$(load_1m || true)"
      exit 0
    fi
    if ! can_continue; then
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ${MODE} guard tripped; stopping qmd embed pid=$embed_pid"
      kill -TERM "$embed_pid" 2>/dev/null || true
      sleep 3
      kill -KILL "$embed_pid" 2>/dev/null || true
      wait "$embed_pid" 2>/dev/null || true
      after="$(pending_count || true)"
      status_json "paused" "stopped because ${MODE} guard tripped" "$before" "$after" "$(idle_seconds || true)" "$(load_1m || true)"
      exit 0
    fi
  done
  set +e
  wait "$embed_pid"
  rc=$?
  set -e
  after="$(pending_count || true)"
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] qmd embed finished rc=$rc pending_after=${after:-N/A}"
  if [[ "$rc" -eq 0 ]]; then
    status_json "ok" "qmd embed completed" "$before" "$after" "$(idle_seconds || true)" "$(load_1m || true)"
  else
    status_json "error" "qmd embed failed rc=$rc" "$before" "$after" "$(idle_seconds || true)" "$(load_1m || true)"
  fi
  exit "$rc"
} >>"$LOG_FILE" 2>&1
