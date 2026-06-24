#!/bin/bash
# ================================================================
# Solar Harness — Phase State Machine
#
# 7-phase Sprint lifecycle: spec → plan → build → test → review → ship
# Plus fail-loop: review → build (on FAIL with rounds remaining)
#
# Usage:
#   phase-state-machine.sh current <sid>
#   phase-state-machine.sh transition <sid> <from> <to>
#   phase-state-machine.sh entry_gate <sid> <phase>
#   phase-state-machine.sh exit_gate <sid> <phase>
#   phase-state-machine.sh init <sid>
#   phase-state-machine.sh list
#
# bash 3.2 compatible (no declare -A)
# ================================================================
set -eu

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
SPRINTS_DIR="$HARNESS_DIR/sprints"

# ---- Helpers ----

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
ok()   { echo -e "${G}[phase]${N} $*"; }
err()  { echo -e "${R}[phase]${N} $*" >&2; }
info() { echo -e "${C}[phase]${N} $*"; }

status_file() { echo "${SPRINTS_DIR}/${1}.status.json"; }

get_phase() {
  local sf
  sf=$(status_file "$1")
  if [[ ! -f "$sf" ]]; then
    echo "unknown"
    return 1
  fi
  python3 -c "
import json, sys
d = json.load(open('${sf}'))
print(d.get('phase', 'legacy'))
" 2>/dev/null || echo "legacy"
}

set_phase() {
  local sid="$1" phase="$2"
  local sf
  sf=$(status_file "$sid")
  python3 -c "
import json, datetime
sf = '${sf}'
d = json.load(open(sf))
old = d.get('phase', 'legacy')
d['phase'] = '${phase}'
d['updated_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
d.setdefault('history', []).append({
    'ts': d['updated_at'],
    'event': 'phase_transition',
    'by': 'phase-state-machine',
    'data': {'from': old, 'to': '${phase}'}
})
json.dump(d, open(sf, 'w'), indent=2)
print('${phase}')
"
}

# ---- Valid transitions (case/esac for bash 3.2 compat) ----

is_valid_transition() {
  local from="$1" to="$2"
  case "${from}|${to}" in
    "spec|plan")    return 0 ;;
    "plan|build")   return 0 ;;
    "build|test")   return 0 ;;
    "test|review")  return 0 ;;
    "review|ship")  return 0 ;;
    "review|build") return 0 ;;  # fail loop
    *)              return 1 ;;
  esac
}

# ---- Entry gates ----

entry_gate_spec() { return 0; }

entry_gate_plan() {
  # Contract must have real Done criteria (not placeholder)
  local contract="${SPRINTS_DIR}/${1}.contract.md"
  if [[ ! -f "$contract" ]]; then
    err "No contract file found"
    return 1
  fi
  if grep -qE '\(条件[0-9]+\)|\(criterion[ 0-9]*\)' "$contract" 2>/dev/null; then
    err "Done criteria still has placeholders"
    return 1
  fi
  return 0
}

entry_gate_build() {
  # Plan must exist
  local plan="${SPRINTS_DIR}/${1}.plan.md"
  if [[ ! -f "$plan" ]]; then
    err "No plan.md found"
    return 1
  fi
  return 0
}

entry_gate_test() {
  # Handoff must exist (builder finished)
  local handoff="${SPRINTS_DIR}/${1}.handoff.md"
  if [[ ! -f "$handoff" ]]; then
    err "No handoff.md found"
    return 1
  fi
  return 0
}

entry_gate_review() {
  # Eval report must exist (test/eval ran)
  local evalf="${SPRINTS_DIR}/${1}.eval.md"
  if [[ ! -f "$evalf" ]]; then
    err "No eval.md found"
    return 1
  fi
  return 0
}

entry_gate_ship() {
  # Eval must have PASS verdict
  local evalf="${SPRINTS_DIR}/${1}.eval.md"
  if [[ ! -f "$evalf" ]]; then
    err "No eval.md found"
    return 1
  fi
  if ! grep -qi 'verdict.*PASS\|PASS' "$evalf"; then
    err "Eval verdict is not PASS"
    return 1
  fi
  return 0
}

entry_gate() {
  local sid="$1" phase="$2"
  case "$phase" in
    spec)   entry_gate_spec ;;
    plan)   entry_gate_plan "$sid" ;;
    build)  entry_gate_build "$sid" ;;
    test)   entry_gate_test "$sid" ;;
    review) entry_gate_review "$sid" ;;
    ship)   entry_gate_ship "$sid" ;;
    *)      err "Unknown phase: $phase"; return 1 ;;
  esac
}

# ---- Exit gates (always pass for now, extensible later) ----

exit_gate() {
  local sid="$1" phase="$2"
  case "$phase" in
    spec|plan|build|test|review|ship) return 0 ;;
    *) err "Unknown phase: $phase"; return 1 ;;
  esac
}

# ---- Append phase_transition event to events.jsonl ----

append_event() {
  local sid="$1" from="$2" to="$3"
  if [[ -f "$HARNESS_DIR/lib/events.sh" ]]; then
    # Use the unified events library so phase transitions also reach
    # session-log v2 through runtime_bridge.py.
    # shellcheck source=/dev/null
    source "$HARNESS_DIR/lib/events.sh"
    events_emit "phase-state-machine" "phase_transition" "info" "$sid" "{\"from\":\"${from}\",\"to\":\"${to}\"}" 2>/dev/null && return 0
  fi
  local events_file="${SPRINTS_DIR}/${sid}.events.jsonl"
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf '{"ts":"%s","event":"phase_transition","by":"phase-state-machine","sid":"%s","data":{"from":"%s","to":"%s"}}\n' \
    "$ts" "$sid" "$from" "$to" >> "$events_file"
  if [[ -f "$HARNESS_DIR/lib/runtime_bridge.py" ]]; then
    python3 "$HARNESS_DIR/lib/runtime_bridge.py" event "$sid" "phase_transition" "phase-state-machine" "{\"from\":\"${from}\",\"to\":\"${to}\"}" --quiet 2>/dev/null || true
  fi
}

# ---- Commands ----

cmd_current() {
  local sid="$1"
  get_phase "$sid"
}

cmd_init() {
  local sid="$1"
  local sf
  sf=$(status_file "$sid")
  if [[ ! -f "$sf" ]]; then
    err "Sprint not found: $sid"
    return 1
  fi
  local current
  current=$(get_phase "$sid")
  if [[ "$current" == "unknown" ]]; then
    set_phase "$sid" "spec"
    append_event "$sid" "none" "spec"
    ok "Initialized phase: spec"
  else
    info "Phase already: $current"
  fi
}

cmd_transition() {
  local sid="$1" from="$2" to="$3"

  # Validate transition
  if ! is_valid_transition "$from" "$to"; then
    err "Invalid transition: $from | $to"
    echo "Valid: spec|plan, plan|build, build|test, test|review, review|ship, review|build"
    return 1
  fi

  # Verify current phase matches 'from'
  local current
  current=$(get_phase "$sid")
  if [[ "$current" != "$from" ]]; then
    err "Current phase is '$current', expected '$from'"
    return 1
  fi

  # Check entry gate for target phase
  if ! entry_gate "$sid" "$to"; then
    err "Entry gate failed for phase: $to"
    return 1
  fi

  # Check exit gate for current phase
  if ! exit_gate "$sid" "$from"; then
    err "Exit gate failed for phase: $from"
    return 1
  fi

  # Transition
  set_phase "$sid" "$to"
  append_event "$sid" "$from" "$to"
  ok "Transitioned: $from => $to"
}

cmd_entry_gate() {
  local sid="$1" phase="$2"
  if entry_gate "$sid" "$phase"; then
    ok "Entry gate PASS: $phase"
    return 0
  else
    return 1
  fi
}

cmd_exit_gate() {
  local sid="$1" phase="$2"
  if exit_gate "$sid" "$phase"; then
    ok "Exit gate PASS: $phase"
    return 0
  else
    return 1
  fi
}

cmd_list() {
  echo "spec => plan => build => test => review => ship"
  echo "                           ^            |"
  echo "                           +--- fail ---+"
}

# ---- Main ----

cmd="${1:-}"
shift || true

case "$cmd" in
  current)      cmd_current "$1" ;;
  init)         cmd_init "$1" ;;
  transition)   cmd_transition "$1" "$2" "$3" ;;
  entry_gate)   cmd_entry_gate "$1" "$2" ;;
  exit_gate)    cmd_exit_gate "$1" "$2" ;;
  list)         cmd_list ;;
  *)
    echo "Usage: phase-state-machine.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  current <sid>                    Show current phase"
    echo "  init <sid>                       Initialize phase to spec"
    echo "  transition <sid> <from> <to>     Transition between phases"
    echo "  entry_gate <sid> <phase>         Check entry gate"
    echo "  exit_gate <sid> <phase>          Check exit gate"
    echo "  list                             Show valid transitions"
    exit 1
    ;;
esac
