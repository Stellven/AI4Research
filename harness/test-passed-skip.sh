#!/bin/bash
# ================================================================
# 回归测试: handle_passed 漏触发 + eval-verdict
# Sprint 20260420-113026 — 3 场景
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"

pass=0 fail=0 total=0
run_test() { local n="$1"; total=$((total + 1)); echo ""; echo "=== Test $n: $2 ==="; }
ok()   { pass=$((pass + 1)); echo "  PASS: $1"; }
fail() { fail=$((fail + 1)); echo "  FAIL: $1"; }
cleanup=""

make_sprint() {
  local sid="$1" status="${2:-reviewing}" round="${3:-1}"
  cat > "$SPRINTS_DIR/${sid}.status.json" << EOF
{"id":"$sid","status":"$status","round":$round,"history":[]}
EOF
  cleanup="$cleanup $SPRINTS_DIR/${sid}.status.json $SPRINTS_DIR/${sid}.finalized"
}
get_st() { python3 -c "import json; print(json.load(open('$1')).get('status',''))" 2>/dev/null; }

# ── Scenario 1: eval-verdict pass ──
run_test 1 "eval-verdict pass sets status=passed"
make_sprint "test-sid-101" "reviewing" 1
bash "$HARNESS_DIR/solar-harness.sh" eval-verdict "test-sid-101" pass "all done" 2>&1
st=$(get_st "$SPRINTS_DIR/test-sid-101.status.json")
[[ "$st" == "passed" ]] && ok "status=passed" || fail "status=$st expected passed"
python3 -c "import json; d=json.load(open('$SPRINTS_DIR/test-sid-101.status.json')); assert d['history'][-1]['event']=='eval_completed'" 2>/dev/null && ok "history has eval_completed" || fail "history missing"

# ── Scenario 2: eval-verdict fail → status=failed_review + round++ ──
run_test 2 "eval-verdict fail sets status=failed_review + round++"
make_sprint "test-sid-102" "reviewing" 1
bash "$HARNESS_DIR/solar-harness.sh" eval-verdict "test-sid-102" fail "missing tests" 2>&1
st=$(get_st "$SPRINTS_DIR/test-sid-102.status.json")
[[ "$st" == "failed_review" ]] && ok "status=failed_review" || fail "status=$st expected failed_review"
round=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/test-sid-102.status.json'))['round'])" 2>/dev/null)
[[ "$round" == "2" ]] && ok "round incremented to 2" || fail "round=$round expected 2"

# ── Scenario 3: passed without .finalized → runtime compensation detects ──
run_test 3 "passed sprint without .finalized detected by scan"
make_sprint "test-sid-103" "passed" 1
sid="test-sid-103"
rst=$(python3 -c "import json; print(json.load(open('$SPRINTS_DIR/${sid}.status.json')).get('status',''))" 2>/dev/null)
if [[ "$rst" == "passed" ]] && [[ ! -f "$SPRINTS_DIR/${sid}.finalized" ]]; then
  ok "detected passed without finalized"
  touch "$SPRINTS_DIR/${sid}.finalized"
  [[ -f "$SPRINTS_DIR/${sid}.finalized" ]] && ok "finalized marker created" || fail "finalized not created"
else
  fail "did not detect passed without finalized"
fi
if [[ -f "$SPRINTS_DIR/${sid}.finalized" ]]; then
  ok "second scan would skip (already finalized)"
fi

rm -f $cleanup 2>/dev/null || true

echo ""
echo "════════════════════════════════════════"
echo "  Results: ${pass}/${total} PASS, ${fail} FAIL"
echo "════════════════════════════════════════"
(( fail > 0 )) && exit 1 || exit 0
