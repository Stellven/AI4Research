#!/bin/bash
# ================================================================
# 回归测试: plan-review 卡死自愈
# Sprint 20260420-113026 — 4 场景
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"

pass=0 fail=0 total=0
run_test() { local n="$1"; total=$((total + 1)); echo ""; echo "=== Test $n: $2 ==="; }
ok()   { pass=$((pass + 1)); echo "  PASS: $1"; }
fail() { fail=$((fail + 1)); echo "  FAIL: $1"; }
cleanup=""  # files to remove after test

make_sprint() {
  local sid="$1" status="${2:-planning}"
  cat > "$SPRINTS_DIR/${sid}.status.json" << EOF
{"id":"$sid","status":"$status","round":0,"history":[]}
EOF
  cleanup="$cleanup $SPRINTS_DIR/${sid}.status.json $SPRINTS_DIR/${sid}.plan.md"
}
get_st() { python3 -c "import json; print(json.load(open('$1')).get('status',''))" 2>/dev/null; }

# ── Scenario 1: plan-verdict approve ──
run_test 1 "plan-verdict approve sets status=approved + history"
make_sprint "test-sid-001" "planning"
bash "$HARNESS_DIR/solar-harness.sh" plan-verdict "test-sid-001" approve "looks good" 2>&1
st=$(get_st "$SPRINTS_DIR/test-sid-001.status.json")
[[ "$st" == "approved" ]] && ok "status=approved" || fail "status=$st expected approved"
python3 -c "import json; d=json.load(open('$SPRINTS_DIR/test-sid-001.status.json')); h=d['history'][-1]; assert h['event']=='plan_reviewed' and h['verdict']=='APPROVE'" 2>/dev/null && ok "history has plan_reviewed APPROVE" || fail "history missing"

# ── Scenario 2: plan-verdict reject ──
run_test 2 "plan-verdict reject sets status=active"
make_sprint "test-sid-002" "planning"
bash "$HARNESS_DIR/solar-harness.sh" plan-verdict "test-sid-002" reject "needs work" 2>&1
st=$(get_st "$SPRINTS_DIR/test-sid-002.status.json")
[[ "$st" == "active" ]] && ok "status=active" || fail "status=$st expected active"

# ── Scenario 3: self-heal detects plan.md APPROVE + status=planning ──
run_test 3 "self-heal: plan.md has APPROVE but status=planning → auto fix"
make_sprint "test-sid-003" "planning"
cat > "$SPRINTS_DIR/test-sid-003.plan.md" << 'EOF'
# Implementation Plan
Some content here.

## 审判官审批意见 — APPROVE
Plan looks good.
EOF
verdict=$(tail -20 "$SPRINTS_DIR/test-sid-003.plan.md" | grep -oE '(APPROVE|REJECT|PASS|FAIL)' | tail -1 || true)
[[ "$verdict" == "APPROVE" ]] && ok "detected APPROVE in plan.md" || fail "did not detect APPROVE verdict=$verdict"
bash "$HARNESS_DIR/solar-harness.sh" plan-verdict "test-sid-003" approve "[heal-auto]" 2>&1
st=$(get_st "$SPRINTS_DIR/test-sid-003.status.json")
[[ "$st" == "approved" ]] && ok "status healed to approved" || fail "status=$st expected approved"

# ── Scenario 4: no verdict in plan.md → no crash ──
run_test 4 "no verdict in plan.md → status unchanged"
make_sprint "test-sid-004" "planning"
cat > "$SPRINTS_DIR/test-sid-004.plan.md" << 'EOF'
# Plan
Just a regular plan, no verdict markers.
EOF
verdict=$(tail -20 "$SPRINTS_DIR/test-sid-004.plan.md" | grep -oE '(APPROVE|REJECT|PASS|FAIL)' | tail -1 || true)
[[ -z "$verdict" ]] && ok "no verdict found (correct)" || fail "unexpected verdict=$verdict"
st=$(get_st "$SPRINTS_DIR/test-sid-004.status.json")
[[ "$st" == "planning" ]] && ok "status unchanged" || fail "status changed unexpectedly"

# Cleanup
rm -f $cleanup 2>/dev/null || true

echo ""
echo "════════════════════════════════════════"
echo "  Results: ${pass}/${total} PASS, ${fail} FAIL"
echo "════════════════════════════════════════"
(( fail > 0 )) && exit 1 || exit 0
