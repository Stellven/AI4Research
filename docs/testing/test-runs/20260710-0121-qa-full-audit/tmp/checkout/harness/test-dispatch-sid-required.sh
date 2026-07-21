#!/usr/bin/env bash
# test-dispatch-sid-required.sh — Unit tests for dispatch_with_gate sid validation
# Sprint: sprint-20260507-symphony3 / S7

set -eu

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"

# ── Safety guards ──
[[ "${SESSION_NAME:-}" == "solar-harness" ]] && {
  echo "REFUSE: cannot run tests on live solar-harness session"; exit 1
}

export TEST_TMP
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

# ── Stub dispatch_with_gate for isolated testing ──
# Source the function definition inline (mirrors coordinator.sh implementation)
cat > "$TEST_TMP/dispatch_with_gate.sh" <<'FUNCEOF'
# dispatch_with_gate — wrapper that enforces sid is present and valid
# Usage: dispatch_with_gate <pane> <instruction_file> <sid>
# Returns:
#   0 — dispatched (or DISPATCH_MOCK mode)
#   1 — invalid sid (empty or placeholder "dispatch")
dispatch_with_gate() {
  local pane="${1:?dispatch_with_gate: pane required}"
  local instruction_file="${2:-}"
  local sid="${3:-}"

  # sid validation — guard against empty or placeholder
  if [[ -z "$sid" ]]; then
    echo "[dispatch_with_gate] ERROR: sid is required (empty)" >&2
    return 1
  fi
  if [[ "$sid" == "dispatch" ]]; then
    echo "[dispatch_with_gate] ERROR: sid 'dispatch' is a placeholder, not a real sprint id" >&2
    return 1
  fi
  # sid must match sprint id pattern: sprint-YYYYMMDD-* or similar
  if ! [[ "$sid" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "[dispatch_with_gate] ERROR: sid '${sid}' contains invalid characters" >&2
    return 1
  fi

  # In test mode, just record the dispatch
  local record_dir="${DISPATCH_GATE_RECORD:-}"
  if [[ -n "$record_dir" ]]; then
    echo "${sid}" > "$record_dir/${sid}.dispatched"
    return 0
  fi

  # Real dispatch (not exercised in unit tests)
  dispatch_to_pane "$pane" "" "$sid"
}
FUNCEOF

source "$TEST_TMP/dispatch_with_gate.sh"

# ── Test framework ──
PASS=0
FAIL=0

assert() {
  local desc="$1" expr="$2"
  if eval "$expr" 2>/dev/null; then
    echo "  ✅ PASS: $desc"
    (( PASS++ )) || true
  else
    echo "  ❌ FAIL: $desc"
    (( FAIL++ )) || true
  fi
}

echo "=== test-dispatch-sid-required.sh ==="
echo ""

# ── TC1: Empty sid → return 1 ──
echo "TC1: Empty sid returns exit code 1"
RC=0; dispatch_with_gate "some-pane" "/dev/null" "" 2>/dev/null || RC=$?
assert "exit code is 1 for empty sid" '[[ "$RC" -eq 1 ]]'
echo ""

# ── TC2: Placeholder sid "dispatch" → return 1 ──
echo "TC2: Placeholder sid 'dispatch' returns exit code 1"
RC=0; dispatch_with_gate "some-pane" "/dev/null" "dispatch" 2>/dev/null || RC=$?
assert "exit code is 1 for placeholder sid" '[[ "$RC" -eq 1 ]]'
echo ""

# ── TC3: Valid sid → return 0 ──
echo "TC3: Valid sprint id returns exit code 0"
RECORD_DIR="$TEST_TMP/records"
mkdir -p "$RECORD_DIR"
export DISPATCH_GATE_RECORD="$RECORD_DIR"
dispatch_with_gate "some-pane" "/dev/null" "sprint-20260507-symphony3" 2>/dev/null
RC=$?
assert "exit code is 0 for valid sid" '[[ "$RC" -eq 0 ]]'
assert "dispatch record file created" '[[ -f "$RECORD_DIR/sprint-20260507-symphony3.dispatched" ]]'
unset DISPATCH_GATE_RECORD
echo ""

# ── TC4: Sid with special characters → return 1 ──
echo "TC4: Sid with invalid characters (spaces/semicolons) returns exit code 1"
RC=0; dispatch_with_gate "some-pane" "/dev/null" "sprint;rm -rf /" 2>/dev/null || RC=$?
assert "exit code is 1 for sid with semicolons" '[[ "$RC" -eq 1 ]]'
RC=0; dispatch_with_gate "some-pane" "/dev/null" "sprint with spaces" 2>/dev/null || RC=$?
assert "exit code is 1 for sid with spaces" '[[ "$RC" -eq 1 ]]'
echo ""

# ── TC5: Concurrent dispatches with different sids → no cross-contamination ──
echo "TC5: Concurrent dispatches with different sids — no cross-contamination"
RECORD_DIR2="$TEST_TMP/concurrent"
mkdir -p "$RECORD_DIR2"
export DISPATCH_GATE_RECORD="$RECORD_DIR2"

for i in $(seq 1 5); do
  dispatch_with_gate "pane-$i" "/dev/null" "sprint-concurrent-$i" 2>/dev/null &
done
wait

COUNT=$(ls "$RECORD_DIR2"/*.dispatched 2>/dev/null | wc -l | tr -d ' ')
assert "5 concurrent dispatches all recorded" '[[ "$COUNT" -eq 5 ]]'

# Verify each file contains its own sid
OK=0
for i in $(seq 1 5); do
  f="$RECORD_DIR2/sprint-concurrent-$i.dispatched"
  if [[ -f "$f" ]] && grep -q "sprint-concurrent-$i" "$f"; then
    (( OK++ )) || true
  fi
done
assert "all 5 dispatch records contain correct sid" '[[ "$OK" -eq 5 ]]'
unset DISPATCH_GATE_RECORD
echo ""

# ── Summary ──
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
