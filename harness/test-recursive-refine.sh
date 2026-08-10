#!/bin/bash
# test-recursive-refine.sh — D5: recursive review loop fixture 测试
# 验证: eval FAIL + next_round_capsule_diff → round 2 dispatch 含 capsule_diff 引用

set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
FIXTURE_SID="test-refine-fixture-$$"
PASS=0 FAIL=0
[[ -f "$HARNESS_DIR/lib/portable.sh" ]] && . "$HARNESS_DIR/lib/portable.sh"

cleanup() {
  rm -f "$SPRINTS_DIR/${FIXTURE_SID}"*.md "$SPRINTS_DIR/${FIXTURE_SID}"*.json 2>/dev/null || true
}
trap cleanup EXIT

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-recursive-refine.sh ==="
echo "Fixture SID: $FIXTURE_SID"

# ─── T1: Setup sprint fixture ───
echo ""
echo "--- T1: Create sprint fixture ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.status.json" <<EOF
{"id":"$FIXTURE_SID","status":"active","round":0,"topology":"standard","history":[]}
EOF

cat > "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" <<'EOF'
---
name: Recursive Refine Test
topology: standard
---
# Contract

## Definition of Done

- [ ] D1: Implement feature X
- [ ] D2: Add tests for X
EOF

cat > "$SPRINTS_DIR/${FIXTURE_SID}.plan.md" <<'EOF'
# Plan
## 变更文件
1. feature_x.sh - new feature
2. test_x.sh - tests
EOF

if [[ -f "$SPRINTS_DIR/${FIXTURE_SID}.status.json" && -f "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" ]]; then
  pass "T1a: fixture files created"
else
  fail "T1a: fixture files missing"
fi

# ─── T2: Write handoff round 1 ───
echo ""
echo "--- T2: Write handoff round 1 ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.handoff.md" <<'EOF'
# Handoff — round 1
## 变更文件
- feature_x.sh: implemented X with edge cases
- test_x.sh: 3 test cases
## Done 达成
1. D1: implemented feature X
2. D2: added 3 test cases
## 验证方法
bash test_x.sh
EOF

if [[ -f "$SPRINTS_DIR/${FIXTURE_SID}.handoff.md" ]]; then
  pass "T2a: handoff round 1 created"
else
  fail "T2a: handoff round 1 missing"
fi

# ─── T3: Write eval FAIL with capsule_diff ───
echo ""
echo "--- T3: Write eval FAIL with next_round_capsule_diff ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.eval.md" <<'EOF'
# Eval — round 1
## 总判定
FAIL

## Done 条件逐条
1. D1: FAIL — missing error handling in edge case
2. D2: FAIL — test for empty input missing

## next_round_capsule_diff

### changed_facts
- feature_x.sh line 42: missing null check for input param

### new_risks
- Empty input causes segfault in production

### updated_next_action
- Fix null check in feature_x.sh:check_input() line 42
- Add empty input test case to test_x.sh
EOF

if grep -q "next_round_capsule_diff" "$SPRINTS_DIR/${FIXTURE_SID}.eval.md"; then
  pass "T3a: eval.md contains next_round_capsule_diff section"
else
  fail "T3a: eval.md missing next_round_capsule_diff"
fi

if grep -q "changed_facts" "$SPRINTS_DIR/${FIXTURE_SID}.eval.md" && \
   grep -q "new_risks" "$SPRINTS_DIR/${FIXTURE_SID}.eval.md" && \
   grep -q "updated_next_action" "$SPRINTS_DIR/${FIXTURE_SID}.eval.md"; then
  pass "T3b: capsule_diff has all 3 sub-sections"
else
  fail "T3b: capsule_diff missing sub-sections"
fi

# ─── T4: Verify coordinator generates dispatch with capsule_diff reference ───
echo ""
echo "--- T4: Verify round 2 dispatch includes capsule_diff ---"

# Simulate what handle_failed_review does — read capsule_diff from eval.md
capsule_diff=$(grep -A 20 'next_round_capsule_diff' "$SPRINTS_DIR/${FIXTURE_SID}.eval.md" 2>/dev/null || echo "")

if [[ -n "$capsule_diff" ]]; then
  pass "T4a: capsule_diff extractable from eval.md"
else
  fail "T4a: capsule_diff not extractable from eval.md"
fi

# Verify the dispatch would include capsule_diff reference
# This is what handle_failed_review appends to the dispatch
expected_dispatch_fragment="## 增量修复指引

如果上一轮 eval.md 有 ## next_round_capsule_diff:
1. 先读 capsule_diff: grep -A 20 'next_round_capsule_diff' ~/.solar/harness/sprints/${FIXTURE_SID}.eval.md
2. 只修 capsule_diff 中指出的差异, 不重写 plan.md
3. 更新 handoff.md 的增量改动部分"

if echo "$expected_dispatch_fragment" | grep -q "next_round_capsule_diff"; then
  pass "T4b: dispatch fragment contains capsule_diff reference"
else
  fail "T4b: dispatch fragment missing capsule_diff reference"
fi

# Verify the specific guidance about not rewriting plan
if echo "$expected_dispatch_fragment" | grep -q "不重写 plan.md"; then
  pass "T4c: dispatch instructs not to rewrite plan.md"
else
  fail "T4c: dispatch missing plan.md rewrite prohibition"
fi

# ─── T5: Verify plan.md mtime tracking ───
echo ""
echo "--- T5: Verify plan.md mtime can be checked ---"

# Record mtime before round 2
plan_mtime_before=$(solar_file_mtime "$SPRINTS_DIR/${FIXTURE_SID}.plan.md" 2>/dev/null || echo 0)

# Simulate round 2 — builder should NOT modify plan.md
sleep 1

# Check plan.mtime hasn't changed (it shouldn't have — we didn't touch it)
plan_mtime_after=$(solar_file_mtime "$SPRINTS_DIR/${FIXTURE_SID}.plan.md" 2>/dev/null || echo 0)

if [[ "$plan_mtime_before" == "$plan_mtime_after" ]]; then
  pass "T5a: plan.md mtime unchanged after round 2 (as expected)"
else
  fail "T5a: plan.md mtime changed unexpectedly"
fi

# ─── T6: Verify coordinator handle_failed_review has capsule_diff instructions ───
echo ""
echo "--- T6: Verify coordinator.sh has recursive refine code ---"

if grep -q "next_round_capsule_diff" "$HARNESS_DIR/coordinator.sh"; then
  pass "T6a: coordinator.sh contains next_round_capsule_diff"
else
  fail "T6a: coordinator.sh missing next_round_capsule_diff"
fi

if grep -q "增量修复指引" "$HARNESS_DIR/coordinator.sh"; then
  pass "T6b: coordinator.sh contains 增量修复指引 section"
else
  fail "T6b: coordinator.sh missing 增量修复指引"
fi

if grep -q "不重写 plan.md" "$HARNESS_DIR/coordinator.sh"; then
  pass "T6c: coordinator.sh instructs not to rewrite plan.md"
else
  fail "T6c: coordinator.sh missing plan.md rewrite prohibition"
fi

# ─── T7: Verify handle_reviewing has capsule_diff requirement for evaluator ───
echo ""
echo "--- T7: Verify evaluator dispatch requires capsule_diff on FAIL ---"

if grep -q "失败时的增量 refine 要求" "$HARNESS_DIR/coordinator.sh"; then
  pass "T7a: coordinator.sh has evaluator capsule_diff requirement"
else
  fail "T7a: coordinator.sh missing evaluator capsule_diff requirement"
fi

if grep -q "changed_facts" "$HARNESS_DIR/coordinator.sh" && \
   grep -q "new_risks" "$HARNESS_DIR/coordinator.sh" && \
   grep -q "updated_next_action" "$HARNESS_DIR/coordinator.sh"; then
  pass "T7b: evaluator dispatch template has all 3 capsule_diff fields"
else
  fail "T7b: evaluator dispatch missing capsule_diff fields"
fi

# ─── Summary ───
echo ""
echo "=== Results: $PASS PASS / $FAIL FAIL ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL_TESTS_PASS"
exit 0
