#!/usr/bin/env bash
# Solar Harness Events Library — emit_event() v1
#
# Usage (source this file):
#   source "$HARNESS_DIR/lib/events.sh"
#   emit_event "coordinator" "state_change" "info" "sprint-xxx" '{"from":"active","to":"reviewing"}'
#
# API: emit_event <actor> <event> <severity> <sprint_id> [json_payload]
#   actor     : who emits (coordinator / runner / workspace-manager / hooks / solar-harness)
#   event     : snake_case event name
#   severity  : info | warn | error
#   sprint_id : sprint id string, or "" / "null" for system events
#   json_payload : optional JSON object string (default: {})
#
# Output:
#   Appends to:
#     $HARNESS_DIR/events/all.jsonl          (global)
#     $HARNESS_DIR/sprints/<sid>.events.jsonl   (per-sprint, if sprint_id is set)
#
# Thread safety: mkdir-based lock prevents torn writes.

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
_EVENTS_DIR="${_EVENTS_DIR:-${HARNESS_DIR}/events}"
_SPRINTS_DIR="${_SPRINTS_DIR:-${HARNESS_DIR}/sprints}"

# Ensure events directory exists
[[ -d "$_EVENTS_DIR" ]] || mkdir -p "$_EVENTS_DIR"

# _atomic_append <file> <line> — append a line atomically using mkdir lock
_atomic_append() {
  local file="$1"
  local line="$2"
  local lock_dir="${file}.lock"
  local max_wait=10
  local waited=0
  while ! mkdir "$lock_dir" 2>/dev/null; do
    sleep 0.05
    (( waited++ )) || true
    if (( waited >= max_wait )); then
      # lock timeout: write without lock rather than drop the event
      echo "$line" >> "$file"
      return
    fi
  done
  echo "$line" >> "$file"
  rmdir "$lock_dir" 2>/dev/null || true
}

_events_emit_impl() {
  local actor="${1:?emit_event: actor required}"
  local event_name="${2:?emit_event: event required}"
  local severity="${3:-info}"
  local sprint_id="${4:-}"
  local payload="${5:-}"
  [[ -z "$payload" ]] && payload="{}"

  # Validate severity
  case "$severity" in
    info|warn|error) ;;
    *) severity="info" ;;
  esac

  # Validate payload is JSON object; wrap in raw if not
  if ! python3 -c "import sys,json; d=json.loads(sys.argv[-1]); assert isinstance(d,dict)" \
       -- "$payload" 2>/dev/null; then
    local escaped
    escaped=$(python3 -c "import sys,json; print(json.dumps(sys.argv[-1]))" -- "$payload" 2>/dev/null || echo '""')
    payload="{\"raw\":${escaped}}"
  fi

  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  local sprint_id_json
  if [[ -z "$sprint_id" || "$sprint_id" == "null" ]]; then
    sprint_id_json="null"
  else
    sprint_id_json="\"${sprint_id}\""
  fi

  local json_line
  json_line="{\"ts\":\"${ts}\",\"sprint_id\":${sprint_id_json},\"actor\":\"${actor}\",\"event\":\"${event_name}\",\"severity\":\"${severity}\",\"payload\":${payload}}"

  # Append to global all.jsonl
  local all_log="${_EVENTS_DIR}/all.jsonl"
  _atomic_append "$all_log" "$json_line"

  # Append to per-sprint jsonl
  if [[ -n "$sprint_id" && "$sprint_id" != "null" ]]; then
    local sprint_log="${_SPRINTS_DIR}/${sprint_id}.events.jsonl"
    _atomic_append "$sprint_log" "$json_line"
    if [[ -f "${HARNESS_DIR}/lib/runtime_bridge.py" ]]; then
      python3 "${HARNESS_DIR}/lib/runtime_bridge.py" event "$sprint_id" "$event_name" "$actor" "$payload" --quiet 2>/dev/null || true
    fi
  fi
}

# query_events [sprint_id] [limit] [event_type] — filter events
query_events() {
  local sprint_id="${1:-}"
  local limit="${2:-50}"
  local event_filter="${3:-}"

  local source_file
  if [[ -n "$sprint_id" && "$sprint_id" != "null" ]]; then
    source_file="${_SPRINTS_DIR}/${sprint_id}.events.jsonl"
  else
    source_file="${_EVENTS_DIR}/all.jsonl"
  fi

  [[ -f "$source_file" ]] || return 0

  if [[ -n "$event_filter" ]]; then
    grep "\"event\":\"${event_filter}\"" "$source_file" 2>/dev/null | tail -"$limit"
  else
    tail -"$limit" "$source_file" 2>/dev/null
  fi
}

# list_event_types — unique event names from all.jsonl
list_event_types() {
  local source_file="${_EVENTS_DIR}/all.jsonl"
  [[ -f "$source_file" ]] || return 0
  python3 -c "
import json
seen = set()
for line in open('$source_file'):
    try:
        d = json.loads(line.strip())
        seen.add(d.get('event',''))
    except: pass
for e in sorted(seen):
    if e: print(e)
" 2>/dev/null
}

emit_event() { _events_emit_impl "$@"; }

# Also export as events_emit for callers that need to avoid name collision.
# Keep this bound to the implementation, not to emit_event, because some
# legacy callers source this library and then define their own emit_event shim.
events_emit() { _events_emit_impl "$@"; }
