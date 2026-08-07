#!/usr/bin/env bash
# test-prd-first-governance.sh — PRD-first PM/Planner governance checks
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-prd-first-governance.sh ==="

echo ""
echo "--- T1: PRD schema/template exist ---"
python3 -c "import json; json.load(open('$HARNESS_DIR/schemas/prd.schema.json'))" 2>/dev/null \
  && pass "T1a: prd schema valid JSON" || fail "T1a: prd schema invalid"
test -f "$HARNESS_DIR/templates/prd.template.md" \
  && pass "T1b: prd template exists" || fail "T1b: prd template missing"

echo ""
echo "--- T2: validate.sh supports prd ---"
tmp="$(mktemp)"
cat > "$tmp" <<'EOF'
# PRD — test

## 背景 / Context
ctx
## 用户问题 / Problem
problem
## 用户目标 / Goals
goal
## 用户故事 / User Stories
story
## 功能需求 / Requirements
req
## 验收标准 / Acceptance Criteria
accept
## 非目标 / Non-Goals
none
## 约束 / Constraints
constraints
## 风险 / Risks
risks
## 开放问题 / Open Questions
questions
## 架构交接 / Planner Handoff
handoff
EOF
bash "$HARNESS_DIR/schemas/validate.sh" prd "$tmp" >/dev/null \
  && pass "T2: valid PRD passes" || fail "T2: valid PRD rejected"
rm -f "$tmp"

echo ""
echo "--- T3: coordinator has PRD-first gates ---"
grep -q 'active_blocked_missing_prd' "$HARNESS_DIR/coordinator.sh" \
  && pass "T3a: active missing PRD blocked" || fail "T3a: missing PRD gate absent"
grep -q 'active_blocked_missing_plan' "$HARNESS_DIR/coordinator.sh" \
  && pass "T3b: active missing plan blocked" || fail "T3b: missing plan gate absent"
grep -q 'pm_requirements_file' "$HARNESS_DIR/coordinator.sh" \
  && pass "T3c: PM requirements resolver present" || fail "T3c: PM resolver absent"

echo ""
echo "--- T4: new sprint entry points to PM PRD ---"
grep -q 'pm_intake_created' "$HARNESS_DIR/solar-harness.sh" \
  && pass "T4a: sprint history starts at PM intake" || fail "T4a: PM intake history absent"
grep -q 'writes PRD' "$HARNESS_DIR/solar-harness.sh" \
  && pass "T4b: next step says PRD" || fail "T4b: next step not PRD"

echo ""
echo "=== Results: $PASS PASS / $FAIL FAIL ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL_TESTS_PASS"
