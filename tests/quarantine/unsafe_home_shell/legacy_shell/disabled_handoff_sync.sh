#!/usr/bin/env bash
# test-handoff-sync.sh — handoff-submit 原子命令 4 场景测试
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HOME/.solar/harness/sprints"
TEST_SID="test-handoff-sync-$$"

cleanup() {
  rm -f "$SPRINTS_DIR/${TEST_SID}.status.json"
  rm -f "$SPRINTS_DIR/${TEST_SID}.handoff.md"
  rm -f "$SPRINTS_DIR/${TEST_SID}.events.jsonl"
}
trap cleanup EXIT

echo "=== test-handoff-sync.sh ==="
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

# Setup: mock sprint with status=approved, round=0
setup_mock() {
  cat > "$SPRINTS_DIR/${TEST_SID}.status.json" << SJ
{
  "id": "$TEST_SID",
  "title": "handoff-submit test",
  "status": "approved",
  "created_at": "2026-04-20T19:00:00Z",
  "round": 0,
  "history": [
    {"ts": "2026-04-20T19:00:00Z", "event": "contract_created", "by": "user"}
  ],
  "updated_at": "2026-04-20T19:00:00Z"
}
SJ
  cat > "$SPRINTS_DIR/${TEST_SID}.handoff.md" << 'HM'
# Handoff
## 变更文件
- test file
HM
}

echo ""
echo "--- Scenario A: normal handoff-submit ---"
setup_mock
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$TEST_SID" 2>&1
STATUS=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json'))['status'])")
PHASE=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json')).get('phase',''))")
HANDOFF_TO=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json')).get('handoff_to',''))")
TARGET_ROLE=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json')).get('target_role',''))")
ROUND=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json'))['round'])")
HAS_IMPL=$(python3 -c "import json; d=json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json')); print(any(h.get('event')=='implementation_completed' and h.get('round')==1 for h in d.get('history',[])))")
HAS_EVENT=$(grep -c 'handoff_submitted' "$SPRINTS_DIR/${TEST_SID}.events.jsonl" 2>/dev/null || echo 0)
assert_eq "status=reviewing" "reviewing" "$STATUS"
assert_eq "phase=implementation_complete" "implementation_complete" "$PHASE"
assert_eq "handoff_to=evaluator" "evaluator" "$HANDOFF_TO"
assert_eq "target_role=evaluator" "evaluator" "$TARGET_ROLE"
assert_eq "round=1" "1" "$ROUND"
assert_eq "history has implementation_completed" "True" "$HAS_IMPL"
assert_eq "events.jsonl has handoff_submitted" "1" "$HAS_EVENT"

echo ""
echo "--- Scenario B: no handoff.md → reject ---"
setup_mock
rm -f "$SPRINTS_DIR/${TEST_SID}.handoff.md"
OUTPUT=$(bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$TEST_SID" 2>&1) && RC=0 || RC=$?
assert_eq "exit code non-zero" "1" "$RC"
echo "  Output: $OUTPUT"

echo ""
echo "--- Scenario C: round increments correctly ---"
setup_mock
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$TEST_SID" 2>/dev/null
ROUND1=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json'))['round'])")
# Modify handoff to trigger new submission (must wait to ensure new mtime)
sleep 2
cat > "$SPRINTS_DIR/${TEST_SID}.handoff.md" << 'HM2'
# Handoff v2
## 变更文件
- test file updated
HM2
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$TEST_SID" 2>/dev/null
ROUND2=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json'))['round'])")
assert_eq "round 0→1" "1" "$ROUND1"
assert_eq "round 1→2 after re-submit" "2" "$ROUND2"

echo ""
echo "--- Scenario D: idempotent — same handoff no double round++ ---"
setup_mock
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$TEST_SID" 2>/dev/null
ROUND_AFTER=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json'))['round'])")
# Call again without changing handoff.md
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$TEST_SID" 2>/dev/null
ROUND_AGAIN=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${TEST_SID}.status.json'))['round'])")
assert_eq "round unchanged on idempotent call" "$ROUND_AFTER" "$ROUND_AGAIN"

echo ""
echo "=== Results: $PASS PASS, $FAIL FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
