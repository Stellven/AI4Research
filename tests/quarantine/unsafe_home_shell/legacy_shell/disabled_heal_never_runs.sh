#!/usr/bin/env bash
# test-heal-never-runs.sh — Bug 5 reproduction: handle_passed mod30 branch never fires
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HOME/.solar/harness/sprints"
COORD_LOG="$HARNESS_DIR/.coordinator.log"
TEST_SID="test-heal-probe-$$"

echo "=== Bug 5 Reproduction: mod30 branch never fires ==="

# 1. Check coordinator is running
PID=$(pgrep -f "bash.*coordinator.sh" 2>/dev/null || true)
if [[ -z "$PID" ]]; then
  echo "FAIL: coordinator not running — cannot test runtime behavior"
  exit 1
fi
echo "PASS: coordinator running (PID=$PID)"

# 2. Check coordinator.sh md5 matches disk
DISK_MD5=$(md5 -q "$HARNESS_DIR/coordinator.sh" 2>/dev/null || echo "unknown")
RUNNING_MD5=$(grep 'coordinator.sh md5=' "$COORD_LOG" 2>/dev/null | tail -1 | sed 's/.*md5=//' | awk '{print $1}' || echo "no-md5-logged")
if [[ "$RUNNING_MD5" == "no-md5-logged" ]]; then
  echo "SKIP: md5 probe not in running version (old binary — needs restart)"
  echo "  Disk md5: $DISK_MD5"
  echo "  FIX: restart coordinator to load new code"
else
  if [[ "$DISK_MD5" == "$RUNNING_MD5" ]]; then
    echo "PASS: running code matches disk (md5=$DISK_MD5)"
  else
    echo "FAIL: running code differs from disk (disk=$DISK_MD5, running=$RUNNING_MD5)"
    echo "  FIX: restart coordinator"
    exit 1
  fi
fi

# 3. Check if [probe] mod30 appears in recent log (new code loaded)
PROBE_COUNT=$(grep '\[probe\] mod30' "$COORD_LOG" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$PROBE_COUNT" -gt 0 ]]; then
  echo "PASS: [probe] mod30 branch reached ($PROBE_COUNT times)"
else
  echo "FAIL: [probe] mod30 never appeared — old code running or branch unreachable"
  exit 1
fi

# 4. Create mock passed sprint without finalized, wait for heal
cleanup_mock() {
  rm -f "$SPRINTS_DIR/${TEST_SID}.status.json"
  rm -f "$SPRINTS_DIR/${TEST_SID}.finalized"
}
trap cleanup_mock EXIT

cat > "$SPRINTS_DIR/${TEST_SID}.status.json" << SJ
{"id":"$TEST_SID","title":"heal probe test","status":"passed","round":1,"history":[{"ts":"2026-04-20T12:00:00Z","event":"contract_created","by":"user"},{"ts":"2026-04-20T12:01:00Z","event":"implementation_completed","by":"builder","round":1},{"ts":"2026-04-20T12:02:00Z","event":"eval_completed","by":"evaluator","verdict":"PASS"}],"updated_at":"2026-04-20T12:02:00Z"}
SJ

echo "Mock passed sprint created: $TEST_SID (no .finalized)"
echo "Waiting 7 minutes for coordinator mod30 scan to detect and heal..."

WAITED=0
MAX_WAIT=420  # 7 minutes
while (( WAITED < MAX_WAIT )); do
  if [[ -f "$SPRINTS_DIR/${TEST_SID}.finalized" ]]; then
    echo "PASS: coordinator auto-finalized $TEST_SID after ${WAITED}s"
    exit 0
  fi
  if grep -q "\\[heal\\].*${TEST_SID}" "$COORD_LOG" 2>/dev/null; then
    echo "PASS: [heal] log found for $TEST_SID"
    # May not have .finalized yet if handle_passed is still running
    sleep 5
    if [[ -f "$SPRINTS_DIR/${TEST_SID}.finalized" ]]; then
      echo "PASS: .finalized created"
    else
      echo "WARN: [heal] triggered but .finalized not yet created (handle_passed may have rejected it)"
    fi
    exit 0
  fi
  sleep 10
  WAITED=$((WAITED + 10))
  echo "  ... ${WAITED}s elapsed"
done

echo "FAIL: mock sprint not finalized after 7 minutes"
echo "  Check: grep '[heal]\\|$TEST_SID' $COORD_LOG | tail -5"
exit 1
