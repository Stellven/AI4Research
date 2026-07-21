#!/usr/bin/env bash
# test-status-auto-advance.sh — D3: 端到端实测状态自动推进 (fixture-first)
set -euo pipefail
HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SPRINTS_DIR="$HARNESS_DIR/sprints"
. "$HARNESS_DIR/lib/run-state.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

FIXTURE_SID="sprint-fixture-status-$$"
FIXTURE_FILE="$SPRINTS_DIR/${FIXTURE_SID}.status.json"
cleanup() { rm -f "$SPRINTS_DIR/${FIXTURE_SID}".* 2>/dev/null; }
trap cleanup EXIT

create_fixture() {
  cat > "$FIXTURE_FILE" <<EOF
{"id":"${FIXTURE_SID}","status":"active","round":1,"created_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","updated_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","history":[]}
EOF
  # Create a minimal handoff.md (required by do_handoff_submit)
  cat > "$SPRINTS_DIR/${FIXTURE_SID}.handoff.md" <<EOF2
# Handoff — ${FIXTURE_SID}
## 变更文件
- test: fixture

## Done 达成
1. D1: ✅ fixture test

## 验证方法
echo test
EOF2
}

# ── T1: handoff_submit → reviewing ──
create_fixture
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$FIXTURE_SID" >/dev/null 2>&1 && pass || fail "T1a: handoff-submit failed"
new_st=$(rs_read_status "$FIXTURE_SID")
[[ "$new_st" == "reviewing" ]] && pass || fail "T1b: expected reviewing, got $new_st"

new_phase=$(rs_read_field "$FIXTURE_SID" "phase")
[[ "$new_phase" == "implementation_complete" ]] && pass || fail "T1c: expected phase=implementation_complete, got $new_phase"

new_handoff=$(rs_read_field "$FIXTURE_SID" "handoff_to")
[[ "$new_handoff" == "evaluator" ]] && pass || fail "T1d: expected handoff_to=evaluator, got $new_handoff"

# Verify round bumped
new_round=$(rs_read_field "$FIXTURE_SID" "round")
[[ "$new_round" -eq 2 ]] && pass || fail "T1e: expected round=2, got $new_round"

# ── T2: eval_verdict pass → passed ──
bash "$HARNESS_DIR/solar-harness.sh" eval-verdict "$FIXTURE_SID" pass "all good" >/dev/null 2>&1 && pass || fail "T2a: eval-verdict pass failed"
new_st=$(rs_read_status "$FIXTURE_SID")
[[ "$new_st" == "passed" ]] && pass || fail "T2b: expected passed, got $new_st"

# Verify history has eval_completed with verdict=PASS
verdict_hist=$(python3 -c "
import json
d=json.load(open('$FIXTURE_FILE'))
for h in reversed(d.get('history',[])):
    if h.get('event')=='eval_completed':
        print(h.get('verdict','')+'|'+h.get('reason',''))
        break
")
[[ "$verdict_hist" == "PASS|all good" ]] && pass || fail "T2c: history verdict mismatch: [$verdict_hist]"

# ── T3: eval_verdict fail → failed_review + round bump ──
cleanup
create_fixture
# First submit handoff to get to reviewing
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$FIXTURE_SID" >/dev/null 2>&1
# Now eval fail
bash "$HARNESS_DIR/solar-harness.sh" eval-verdict "$FIXTURE_SID" fail "needs work" >/dev/null 2>&1 && pass || fail "T3a: eval-verdict fail failed"
new_st=$(rs_read_status "$FIXTURE_SID")
[[ "$new_st" == "failed_review" ]] && pass || fail "T3b: expected failed_review, got $new_st"

# Verify round bumped on fail
new_round=$(rs_read_field "$FIXTURE_SID" "round")
[[ "$new_round" -ge 3 ]] && pass || fail "T3c: expected round>=3 after fail, got $new_round"

# Verify history has FAIL verdict
fail_verdict=$(python3 -c "
import json
d=json.load(open('$FIXTURE_FILE'))
for h in reversed(d.get('history',[])):
    if h.get('event')=='eval_completed':
        print(h.get('verdict',''))
        break
")
[[ "$fail_verdict" == "FAIL" ]] && pass || fail "T3d: expected FAIL verdict, got [$fail_verdict]"

# ── T4: idempotent handoff_submit ──
cleanup
create_fixture
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$FIXTURE_SID" >/dev/null 2>&1
bash "$HARNESS_DIR/solar-harness.sh" handoff-submit "$FIXTURE_SID" >/dev/null 2>&1 && pass || fail "T4a: idempotent handoff-submit should succeed"
# Round should not bump on second submit (idempotent)
idem_round=$(rs_read_field "$FIXTURE_SID" "round")
[[ "$idem_round" -eq 2 ]] && pass || fail "T4b: idempotent should not bump round, got $idem_round"

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
if (( FAIL == 0 )); then
  echo "ALL_TESTS_PASS"
  exit 0
fi
echo "SOME_TESTS_FAILED"
exit 1
