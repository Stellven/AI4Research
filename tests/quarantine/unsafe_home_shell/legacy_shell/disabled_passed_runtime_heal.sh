#!/usr/bin/env bash
# test-passed-runtime-heal.sh — 4 scenarios for runtime handle_passed heal
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HOME/.solar/harness/sprints"
COORD_LOG="$HARNESS_DIR/.coordinator.log"
PASS=0 FAIL=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    echo "  PASS: $label"
    PASS=$((PASS+1))
  else
    echo "  FAIL: $label — expected='$expected' actual='$actual'"
    FAIL=$((FAIL+1))
  fi
}

cleanup() {
  for i in $(seq 1 3); do
    rm -f "$SPRINTS_DIR/test-runtime-heal-${i}-$$.status.json"
    rm -f "$SPRINTS_DIR/test-runtime-heal-${i}-$$.finalized"
  done
}
trap cleanup EXIT

echo "=== test-passed-runtime-heal.sh ==="

make_mock_passed() {
  local idx="$1"
  local sid="test-runtime-heal-${idx}-$$"
  cat > "$SPRINTS_DIR/${sid}.status.json" << SJ
{"id":"$sid","title":"runtime heal test $idx","status":"passed","round":1,"history":[{"ts":"2026-04-20T12:00:00Z","event":"contract_created","by":"user"},{"ts":"2026-04-20T12:01:00Z","event":"implementation_completed","by":"builder","round":1},{"ts":"2026-04-20T12:02:00Z","event":"eval_completed","by":"evaluator","verdict":"PASS"}],"updated_at":"2026-04-20T12:02:00Z"}
SJ
  echo "$sid"
}

# --- Scenario A: create mock passed sprint without finalized ---
echo ""
echo "--- Scenario A: mock passed sprint without finalized ---"
SID_A=$(make_mock_passed 1)
echo "  Created: $SID_A (status=passed, no .finalized)"
ST=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${SID_A}.status.json'))['status'])")
assert_eq "status is passed" "passed" "$ST"
[[ ! -f "$SPRINTS_DIR/${SID_A}.finalized" ]] && assert_eq "no .finalized" "true" "true" || assert_eq "no .finalized" "true" "false"

# --- Scenario B: wait for coordinator to auto-finalize ---
echo ""
echo "--- Scenario B: wait 7min for coordinator auto-finalize ---"
echo "  Waiting..."
WAITED=0
FOUND=false
while (( WAITED < 420 )); do
  if grep -q "\\[heal\\].*${SID_A}" "$COORD_LOG" 2>/dev/null; then
    FOUND=true
    break
  fi
  sleep 10
  WAITED=$((WAITED + 10))
done
if $FOUND; then
  echo "  [heal] detected after ${WAITED}s"
  PASS=$((PASS+1))
else
  echo "  FAIL: [heal] not detected after 7min"
  FAIL=$((FAIL+1))
fi

# --- Scenario C: verify loop_count arithmetic doesn't crash ---
echo ""
echo "--- Scenario C: loop_count arithmetic ---"
# Verify coordinator is still running (didn't crash from loop arithmetic)
PID=$(pgrep -f "bash.*coordinator.sh" 2>/dev/null || true)
assert_eq "coordinator still running" "yes" "${PID:+yes}"
# Verify mod30 probe exists
PROBE_COUNT=$(grep '\[probe\] mod30' "$COORD_LOG" 2>/dev/null | wc -l | tr -d ' ')
echo "  Probe count: $PROBE_COUNT (expect >0)"
[[ "$PROBE_COUNT" -gt 0 ]] && PASS=$((PASS+1)) || { echo "  FAIL: no probe output"; FAIL=$((FAIL+1)); }

# --- Scenario D: multiple passed sprints all get finalized ---
echo ""
echo "--- Scenario D: multiple passed sprints ---"
SID_B=$(make_mock_passed 2)
SID_C=$(make_mock_passed 3)
echo "  Created: $SID_B, $SID_C"

# Wait for heal on both
WAITED=0
B_FOUND=false C_FOUND=false
while (( WAITED < 420 )); do
  grep -q "\\[heal\\].*${SID_B}" "$COORD_LOG" 2>/dev/null && B_FOUND=true
  grep -q "\\[heal\\].*${SID_C}" "$COORD_LOG" 2>/dev/null && C_FOUND=true
  $B_FOUND && $C_FOUND && break
  sleep 10
  WAITED=$((WAITED + 10))
done
$B_FOUND && { echo "  PASS: $SID_B healed"; PASS=$((PASS+1)); } || { echo "  FAIL: $SID_B not healed"; FAIL=$((FAIL+1)); }
$C_FOUND && { echo "  PASS: $SID_C healed"; PASS=$((PASS+1)); } || { echo "  FAIL: $SID_C not healed"; FAIL=$((FAIL+1)); }

echo ""
echo "=== Results: $PASS PASS, $FAIL FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
