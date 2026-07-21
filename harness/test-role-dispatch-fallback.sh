#!/usr/bin/env bash
# tests/test-role-dispatch-fallback.sh — role worker selection fallback regression

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"

PASS=0
FAIL=0

check() {
  local label="$1" got="$2" want="$3"
  if [[ "$got" == "$want" ]]; then
    echo "  ✅ $label"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $label"
    echo "       want: $want"
    echo "        got: $got"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== test-role-dispatch-fallback.sh ==="

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

export COORD_NO_MAIN=1
export HOME="${HOME:-${HOME}}"
# shellcheck disable=SC1091
. "$HARNESS_DIR/coordinator.sh"

ROLE_TRIED="$TMP_DIR/tried.txt"
QUEUE_CALLED="$TMP_DIR/queue-called.txt"
EVENTS="$TMP_DIR/events.txt"

role_candidate_panes() {
  local role="$1"
  [[ "$role" == "pm" ]] || return 1
  printf '%s\n' 'solar-harness:0.0' 'solar-harness-lab:0.3'
}

pane_target_exists() { return 0; }
pane_assignment_held_by_other() { return 1; }
pane_lease_held_by_other() { return 1; }
sprint_queue_priority() { echo 50; }
log() { :; }
emit_event() { echo "$*" >> "$EVENTS"; }
queue_enqueue() {
  echo "$*" > "$QUEUE_CALLED"
  echo ok
}

dispatch_to_pane() {
  local pane="$1"
  echo "$pane" >> "$ROLE_TRIED"
  [[ "$pane" == "solar-harness-lab:0.3" ]]
}

dispatch_to_role "pm" "sprint-test-role-fallback" "pm_prd" "/tmp/dispatch.md" "msg"
rc=$?

tried="$(paste -sd, "$ROLE_TRIED")"
queue_seen="no"
[[ -f "$QUEUE_CALLED" ]] && queue_seen="yes"

check "dispatch_to_role returns success after fallback candidate" "$rc" "0"
check "first failed candidate and second fallback were both tried" "$tried" "solar-harness:0.0,solar-harness-lab:0.3"
check "queue not used when fallback succeeds" "$queue_seen" "no"

>"$ROLE_TRIED"
rm -f "$QUEUE_CALLED"
>"$EVENTS"

role_candidate_panes() {
  local role="$1"
  [[ "$role" == "planner" ]] || return 1
  printf '%s\n' 'solar-harness:0.1' 'solar-harness-lab:0.0'
}

dispatch_to_pane() {
  local pane="$1"
  echo "$pane" >> "$ROLE_TRIED"
  return 3
}

dispatch_to_role "planner" "sprint-test-terminal-notify" "passed_notify" "/tmp/dispatch.md" "msg"
rc=$?

tried="$(paste -sd, "$ROLE_TRIED")"
queue_seen="no"
[[ -f "$QUEUE_CALLED" ]] && queue_seen="yes"
event_seen="$(cat "$EVENTS")"

check "terminal passed_notify hook abort is treated as non-blocking" "$rc" "0"
check "terminal notify tries planner candidates before suppressing" "$tried" "solar-harness:0.1,solar-harness-lab:0.0"
check "terminal passed_notify is not queued after hook abort" "$queue_seen" "no"
case "$event_seen" in
  *dispatch_suppressed*terminal_phase_wake_detected*) got="yes" ;;
  *) got="no" ;;
esac
check "terminal notify suppression emits event" "$got" "yes"

echo ""
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
