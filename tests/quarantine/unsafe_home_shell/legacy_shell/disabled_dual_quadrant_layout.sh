#!/bin/bash
# test-dual-quadrant-layout.sh — D6: Layout smoke test (dry-run, no tmux required)
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
PASS=0 FAIL=0

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-dual-quadrant-layout.sh ==="
echo "Mode: ${SOLAR_HARNESS_DRY_RUN:-not-set} (dry-run = no tmux required)"

# ─── T1: farm-layout.json exists and valid JSON ───
echo ""
echo "--- T1: farm-layout.json ---"
LAYOUT="$HARNESS_DIR/farm-layout.json"
if [[ -f "$LAYOUT" ]] && python3 -c "import json; json.load(open('$LAYOUT'))" 2>/dev/null; then
  pass "T1a: farm-layout.json exists and valid JSON"
else
  fail "T1a: farm-layout.json missing or invalid"
fi

# ─── T2: Window 0 roles = pm,planner,builder,evaluator ───
echo ""
echo "--- T2: Window 0 roles ---"
roles=$(python3 -c "import json; d=json.load(open('$LAYOUT')); print(','.join(p['role'] for p in d['windows'][0]['panes']))" 2>/dev/null) || roles=""
if [[ "$roles" == "pm,planner,builder,evaluator" ]]; then
  pass "T2: window 0 roles = $roles"
else
  fail "T2: window 0 roles = '$roles' (expected pm,planner,builder,evaluator)"
fi

# ─── T3: Window 1 roles = architect,lab-builder,lab-evaluator,observer ───
echo ""
echo "--- T3: Window 1 roles ---"
roles=$(python3 -c "import json; d=json.load(open('$LAYOUT')); print(','.join(p['role'] for p in d['windows'][1]['panes']))" 2>/dev/null) || roles=""
if [[ "$roles" == "architect,lab-builder,lab-evaluator,observer" ]]; then
  pass "T3: window 1 roles = $roles"
else
  fail "T3: window 1 roles = '$roles' (expected architect,lab-builder,lab-evaluator,observer)"
fi

# ─── T4: All 5 new persona files exist and non-empty ───
echo ""
echo "--- T4: New persona files ---"
for f in pm architect lab-builder lab-evaluator observer; do
  pf="$HARNESS_DIR/personas/$f.md"
  if [[ -s "$pf" ]]; then
    pass "T4: personas/$f.md exists and non-empty"
  else
    fail "T4: personas/$f.md missing or empty"
  fi
done

# ─── T5: pm.md contains required keywords ───
echo ""
echo "--- T5: pm.md keywords ---"
PM_MD="$HARNESS_DIR/personas/pm.md"
for kw in "product brief" "acceptance" "priority" "stop_rules"; do
  if grep -qi "$kw" "$PM_MD" 2>/dev/null; then
    pass "T5: pm.md contains '$kw'"
  else
    fail "T5: pm.md missing '$kw'"
  fi
done

# ─── T6: pm.md forbids writing code ───
echo ""
echo "--- T6: pm.md constraints ---"
if grep -qi "不直接写代码" "$PM_MD" 2>/dev/null; then
  pass "T6a: pm.md explicitly forbids writing code"
else
  fail "T6a: pm.md does not explicitly forbid writing code"
fi
if grep -qi "不直接改 sprint status\|不.*implementation" "$PM_MD" 2>/dev/null; then
  pass "T6b: pm.md explicitly forbids pushing sprint to implementation"
else
  fail "T6b: pm.md does not explicitly forbid pushing sprint to implementation"
fi

# ─── T7: persona-config.sh recognizes new personas ───
echo ""
echo "--- T7: persona-config recognizes new personas ---"
for persona in pm architect lab-builder lab-evaluator observer; do
  cn=$(bash "$HARNESS_DIR/lib/persona-config.sh" --print-config "$persona" 2>/dev/null | grep "^CN=" | sed "s/^CN='//;s/'$//") || cn=""
  if [[ -n "$cn" ]]; then
    pass "T7: $persona → CN=$cn"
  else
    fail "T7: $persona not recognized by persona-config"
  fi
done

# ─── T8: bash -n on all modified shell files ───
echo ""
echo "--- T8: bash -n syntax check ---"
for f in solar-harness.sh pane-launcher.sh coordinator-watchdog.sh; do
  if bash -n "$HARNESS_DIR/$f" 2>/dev/null; then
    pass "T8: $f syntax OK"
  else
    fail "T8: $f syntax error"
  fi
done

# ─── T9: solar-harness.sh has 扩展/extend command ───
echo ""
echo "--- T9: 扩展 command exists ---"
if grep -qE '扩展\|extend\)' "$HARNESS_DIR/solar-harness.sh" 2>/dev/null; then
  pass "T9: solar-harness.sh has 扩展|extend case"
else
  fail "T9: solar-harness.sh missing 扩展|extend case"
fi

# ─── T10: schema + template + layout 三件套 ───
echo ""
echo "--- T10: Product brief 三件套 ---"
test -f "$HARNESS_DIR/schemas/product-brief.schema.json" && pass "T10a: schema exists" || fail "T10a: schema missing"
test -f "$HARNESS_DIR/templates/product-brief.template.md" && pass "T10b: template exists" || fail "T10b: template missing"
test -f "$HARNESS_DIR/farm-layout.json" && pass "T10c: layout exists" || fail "T10c: layout missing"

# ─── Summary ───
echo ""
echo "=== Results: $PASS PASS / $FAIL FAIL ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL_TESTS_PASS"
exit 0
