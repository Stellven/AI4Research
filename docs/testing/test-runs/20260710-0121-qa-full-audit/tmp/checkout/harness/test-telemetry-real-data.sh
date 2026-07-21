#!/bin/bash
# test-telemetry-real-data.sh — sprint-20260503-203232 D2
# 端到端: 8 个真实 fixture sprint → telemetry_emit_run → stats 验证
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
TELEMETRY_DIR="$HARNESS_DIR/telemetry"
TELEMETRY_FILE="$TELEMETRY_DIR/runs.jsonl"
PASS=0 FAIL=0
FIXTURE_PREFIX="test-tele-real-$$"

cleanup() {
  # Remove fixture sprint files
  for f in "$SPRINTS_DIR"/${FIXTURE_PREFIX}-*.status.json "$SPRINTS_DIR"/${FIXTURE_PREFIX}-*.contract.md; do
    rm -f "$f" 2>/dev/null || true
  done
  # Restore backup
  if [[ -f "${TELEMETRY_FILE}.bak.$$" ]]; then
    mv "${TELEMETRY_FILE}.bak.$$" "$TELEMETRY_FILE"
  fi
}
trap cleanup EXIT

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-telemetry-real-data.sh ==="

# Source telemetry lib
# shellcheck source=/dev/null
HARNESS_DIR="$HARNESS_DIR" SPRINTS_DIR="$SPRINTS_DIR" source "$HARNESS_DIR/lib/telemetry.sh"

# ─── T1: Backup + clean slate ───
echo ""
echo "--- T1: Backup runs.jsonl ---"

if [[ -f "$TELEMETRY_FILE" ]]; then
  cp "$TELEMETRY_FILE" "${TELEMETRY_FILE}.bak.$$"
  pass "T1a: backed up existing runs.jsonl"
else
  _ensure_telemetry_dir
  touch "$TELEMETRY_FILE"
  pass "T1a: created fresh runs.jsonl"
fi
: > "$TELEMETRY_FILE"

# ─── T2: Create 5 mixture FAIL fixture sprints ───
echo ""
echo "--- T2: Create 5 mixture FAIL sprints ---"

for i in 1 2 3 4 5; do
  sid="${FIXTURE_PREFIX}-fail-${i}"
  cat > "$SPRINTS_DIR/${sid}.status.json" <<EOF
{"id":"$sid","status":"failed","round":3,"topology":"mixture","builder_persona":"glm-5","evaluator_persona":"glm-5","history":[{"ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","event":"auto_chain","by":"chain-watcher"}]}
EOF
  cat > "$SPRINTS_DIR/${sid}.contract.md" <<'EOF'
---
name: Mixture Fail Test
topology: mixture
---
## Definition of Done
- [ ] D1: Feature A
- [ ] D2: Feature B
- [ ] D3: Feature C
EOF
done

pass "T2a: 5 mixture FAIL fixture sprints created"

# ─── T3: Create 3 mixture PASS fixture sprints ───
echo ""
echo "--- T3: Create 3 mixture PASS sprints ---"

for i in 1 2 3; do
  sid="${FIXTURE_PREFIX}-pass-${i}"
  cat > "$SPRINTS_DIR/${sid}.status.json" <<EOF
{"id":"$sid","status":"passed","round":1,"topology":"mixture","builder_persona":"glm-5","evaluator_persona":"glm-5","history":[{"ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","event":"auto_chain","by":"chain-watcher"}]}
EOF
  cat > "$SPRINTS_DIR/${sid}.contract.md" <<'EOF'
---
name: Mixture Pass Test
topology: mixture
---
## Definition of Done
- [ ] D1: Feature A
- [ ] D2: Feature B
- [ ] D3: Feature C
EOF
done

pass "T3a: 3 mixture PASS fixture sprints created"

# ─── T4: Emit telemetry for all 8 sprints ───
echo ""
echo "--- T4: telemetry_emit_run x8 ---"

before_lines=$(wc -l < "$TELEMETRY_FILE" | tr -d ' ')

for i in 1 2 3 4 5; do
  sid="${FIXTURE_PREFIX}-fail-${i}"
  telemetry_emit_run "$sid" "failed" '["D1","D2"]' 2>/dev/null
done

for i in 1 2 3; do
  sid="${FIXTURE_PREFIX}-pass-${i}"
  telemetry_emit_run "$sid" "passed" '[]' 2>/dev/null
done

after_lines=$(wc -l < "$TELEMETRY_FILE" | tr -d ' ')
new_lines=$(( after_lines - before_lines ))

if [[ "$new_lines" -eq 8 ]]; then
  pass "T4a: runs.jsonl grew by 8 lines ($before_lines → $after_lines)"
else
  fail "T4a: runs.jsonl grew by $new_lines (expected 8)"
fi

# ─── T5: Verify stats overview ───
echo ""
echo "--- T5: stats overview ---"

stats_out=$(bash "$HARNESS_DIR/solar-harness.sh" stats 2>&1)

if echo "$stats_out" | grep -q "8"; then
  pass "T5a: stats shows total=8"
else
  fail "T5a: stats missing total count"
fi

if echo "$stats_out" | grep -qE "37\.5"; then
  pass "T5b: stats shows 37.5% pass rate"
else
  fail "T5b: stats missing 37.5% (output: $(echo "$stats_out" | head -3))"
fi

if echo "$stats_out" | grep -q "mixture"; then
  pass "T5c: stats shows mixture topology"
else
  fail "T5c: stats missing mixture topology"
fi

if echo "$stats_out" | grep -qE "D1|D2"; then
  pass "T5d: stats shows Top FAIL Done (D1/D2)"
else
  fail "T5d: stats missing Top FAIL Done"
fi

# ─── T6: Verify stats topology mixture ───
echo ""
echo "--- T6: stats topology mixture ---"

topo_out=$(bash "$HARNESS_DIR/solar-harness.sh" stats topology mixture 2>&1)

if echo "$topo_out" | grep -q "mixture"; then
  pass "T6a: stats topology shows mixture header"
else
  fail "T6a: stats topology missing mixture"
fi

if echo "$topo_out" | grep -qE "37\.5"; then
  pass "T6b: stats topology shows 37.5%"
else
  fail "T6b: stats topology missing 37.5%"
fi

# ─── T7: Verify stats sprint <sid> ───
echo ""
echo "--- T7: stats sprint detail ---"

sid_detail="${FIXTURE_PREFIX}-pass-1"
sprint_out=$(bash "$HARNESS_DIR/solar-harness.sh" stats sprint "$sid_detail" 2>&1)

if echo "$sprint_out" | grep -q "$sid_detail"; then
  pass "T7a: stats sprint shows sid"
else
  fail "T7a: stats sprint missing sid"
fi

if echo "$sprint_out" | grep -q "passed"; then
  pass "T7b: stats sprint shows verdict=passed"
else
  fail "T7b: stats sprint missing verdict"
fi

if echo "$sprint_out" | grep -q "mixture"; then
  pass "T7c: stats sprint shows topology=mixture"
else
  fail "T7c: stats sprint missing topology"
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
