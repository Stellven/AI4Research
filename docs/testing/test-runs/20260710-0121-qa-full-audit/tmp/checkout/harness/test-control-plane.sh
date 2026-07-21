#!/usr/bin/env bash
# test-control-plane.sh — D4 回归测试 (fixture-first, 不引用 live sprint)
set -euo pipefail
HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SPRINTS_DIR="$HARNESS_DIR/sprints"
. "$HARNESS_DIR/lib/run-state.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

# ── Fixture ──
FIXTURE_SID="sprint-fixture-cp-$$"
FIXTURE_FILE="$SPRINTS_DIR/${FIXTURE_SID}.status.json"
cleanup() { rm -f "$SPRINTS_DIR/${FIXTURE_SID}".* 2>/dev/null; }
trap cleanup EXIT

create_fixture() {
  cat > "$FIXTURE_FILE" <<JSON
{
  "id": "${FIXTURE_SID}",
  "status": "drafting",
  "round": 0,
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "history": []
}
JSON
}

# ── T1: help 输出含 Usage + read-only ──
out=$(bash "$HARNESS_DIR/control-plane.sh" --help 2>&1)
echo "$out" | grep -q "Usage" && pass || fail "T1a: help no Usage"
echo "$out" | grep -qi "read-only" && pass || fail "T1b: help missing read-only marker"

# ── T2: status (空参) 不崩 ──
bash "$HARNESS_DIR/control-plane.sh" status >/dev/null 2>&1 && pass || fail "T2: status (no arg) crashed"

# ── T3-T7: helper on fixture ──
create_fixture

[[ "$(rs_read_status "$FIXTURE_SID")" == "drafting" ]] && pass || fail "T3: read drafting"

bash "$HARNESS_DIR/control-plane.sh" status "$FIXTURE_SID" 2>&1 | grep -q "status:" && pass || fail "T4: status <sid> output missing"

rs_transition "$FIXTURE_SID" "active" "test_transition" "test_runner" >/dev/null 2>&1 && pass || fail "T5a: transition failed"
[[ "$(rs_read_status "$FIXTURE_SID")" == "active" ]] && pass || fail "T5b: transition result not active"

# T6: 幂等 — 重复 transition 同状态不出错, history 增长
rs_transition "$FIXTURE_SID" "active" "test_transition" "test_runner" >/dev/null 2>&1 && pass || fail "T6a: idempotent transition failed"
hist_count=$(python3 -c "import json; print(len(json.load(open('$FIXTURE_FILE')).get('history',[])))")
[[ "$hist_count" -eq 2 ]] && pass || fail "T6b: history count expected 2, got $hist_count"

# T7: 错误路径 — nonexistent sprint 返回非零
if rs_read_status "nonexistent-sid-$$" 2>/dev/null; then
  fail "T7: read nonexistent should fail"
else
  pass
fi

# ── T8: plan-verdict 真实接入 (D3 核心) ──
# 重置 fixture 到 active (plan-verdict 的前置状态)
rs_transition "$FIXTURE_SID" "planning" "test_setup" "test_runner" >/dev/null 2>&1
rs_transition "$FIXTURE_SID" "active" "test_setup2" "test_runner" >/dev/null 2>&1

bash "$HARNESS_DIR/solar-harness.sh" plan-verdict "$FIXTURE_SID" approve "test reason" \
  && pass || fail "T8a: plan-verdict approve failed"
new_st=$(rs_read_status "$FIXTURE_SID")
[[ "$new_st" == "approved" ]] && pass || fail "T8b: status expected approved, got $new_st"

# 检查 history 含 verdict + reason
verdict_in_hist=$(python3 -c "
import json
d = json.load(open('$FIXTURE_FILE'))
for h in d.get('history',[]):
    if h.get('event')=='plan_reviewed':
        print(h.get('verdict','')+'|'+h.get('reason',''))
" | tail -1)
[[ "$verdict_in_hist" == "APPROVE|test reason" ]] && pass || fail "T8c: history verdict/reason mismatch: [$verdict_in_hist]"

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
if (( FAIL == 0 )); then
  echo "ALL_TESTS_PASS"
  exit 0
fi
echo "SOME_TESTS_FAILED"
exit 1
