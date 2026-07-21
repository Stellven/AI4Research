#!/usr/bin/env bash
# lib/bridge-ledger.sh — Bridge Ledger 生命周期管理
# 5 种事件: produced / consumed / reviewed / accepted / rejected / closed
LEDGER_FILE="${LEDGER_FILE:-$HOME/.solar/codex-bridge/bridge-ledger.jsonl}"

_ensure_ledger() {
  [[ -f "$LEDGER_FILE" ]] || { mkdir -p "$(dirname "$LEDGER_FILE")"; touch "$LEDGER_FILE"; }
}

# ledger_emit <event> <artifact> [extra_key1=val1,extra_key2=val2]
# event 白名单: produced|consumed|reviewed|accepted|rejected|closed
ledger_emit() {
  local event="$1" artifact="$2"
  local extra="${3:-}"
  [[ -z "$extra" ]] && extra="{}"

  case "$event" in
    produced|consumed|reviewed|accepted|rejected|closed) ;;
    *) echo "ledger_emit: invalid event: $event" >&2; return 1 ;;
  esac

  _ensure_ledger

  python3 - "$event" "$artifact" "$extra" "$LEDGER_FILE" <<'PY'
import json, sys, os, datetime

event, artifact, extra_str, ledger_file = sys.argv[1:]
ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

entry = {"ts": ts, "event": event, "artifact": artifact}
try:
    extra = json.loads(extra_str) if extra_str else {}
    entry.update(extra)
except json.JSONDecodeError:
    pass

line = json.dumps(entry, ensure_ascii=False)
with open(ledger_file, 'a') as f:
    f.write(line + '\n')
PY
}

# ledger_query <artifact_pattern> — 查询 artifact 相关事件
ledger_query() {
  local pattern="${1:-.}"
  _ensure_ledger
  grep "$pattern" "$LEDGER_FILE" 2>/dev/null || true
}

# ledger_events_for_sid <sid> — 查询 sprint 相关事件
ledger_events_for_sid() {
  local sid="$1"
  _ensure_ledger
  grep "$sid" "$LEDGER_FILE" 2>/dev/null || true
}
