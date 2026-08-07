#!/bin/bash
# test-telemetry.sh — sprint-20260503-195627 D5: telemetry 端到端 fixture 测试
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
TELEMETRY_DIR="$HARNESS_DIR/telemetry"
TELEMETRY_FILE="$TELEMETRY_DIR/runs.jsonl"
FIXTURE_SID="test-telemetry-$$"
PASS=0 FAIL=0

cleanup() {
  rm -f "$SPRINTS_DIR/${FIXTURE_SID}"*.md "$SPRINTS_DIR/${FIXTURE_SID}"*.json 2>/dev/null || true
  # Restore backup
  if [[ -f "$TELEMETRY_FILE.bak.$$" ]]; then
    mv "$TELEMETRY_FILE.bak.$$" "$TELEMETRY_FILE"
  fi
}
trap cleanup EXIT

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-telemetry.sh ==="
echo "Fixture SID: $FIXTURE_SID"

# Source telemetry lib
# shellcheck source=/dev/null
HARNESS_DIR="$HARNESS_DIR" SPRINTS_DIR="$SPRINTS_DIR" source "$HARNESS_DIR/lib/telemetry.sh"

# ─── T1: Backup existing runs.jsonl ───
echo ""
echo "--- T1: Backup telemetry data ---"

if [[ -f "$TELEMETRY_FILE" ]]; then
  cp "$TELEMETRY_FILE" "$TELEMETRY_FILE.bak.$$"
  pass "T1a: backed up existing runs.jsonl"
  # Clear for clean test
  : > "$TELEMETRY_FILE"
else
  _ensure_telemetry_dir
  touch "$TELEMETRY_FILE"
  pass "T1a: created fresh runs.jsonl"
fi

# ─── T2: Create fixture sprint ───
echo ""
echo "--- T2: Create fixture sprint ---"

cat > "$SPRINTS_DIR/${FIXTURE_SID}.status.json" <<EOF
{"id":"$FIXTURE_SID","status":"passed","round":1,"topology":"standard",
 "builder_persona":"glm-5","evaluator_persona":"glm-5",
 "history":[{"ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","event":"auto_chain","by":"chain-watcher"}]}
EOF

cat > "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" <<'EOF'
---
name: Telemetry Test
topology: standard
---
# Contract

## Definition of Done

- [ ] D1: Feature A
- [ ] D2: Feature B
- [ ] D3: Feature C
EOF

if [[ -f "$SPRINTS_DIR/${FIXTURE_SID}.status.json" && -f "$SPRINTS_DIR/${FIXTURE_SID}.contract.md" ]]; then
  pass "T2a: fixture files created"
else
  fail "T2a: fixture files missing"
fi

# ─── T3: telemetry_emit_run — verify run written ───
echo ""
echo "--- T3: telemetry_emit_run — write one run ---"

before_lines=$(wc -l < "$TELEMETRY_FILE" | tr -d ' ')

telemetry_emit_run "$FIXTURE_SID" "passed" 2>/dev/null
rc=$?

after_lines=$(wc -l < "$TELEMETRY_FILE" | tr -d ' ')

if [[ $rc -eq 0 ]]; then
  pass "T3a: telemetry_emit_run exit 0"
else
  fail "T3a: telemetry_emit_run exit $rc"
fi

new_lines=$(( after_lines - before_lines ))
if [[ "$new_lines" -eq 1 ]]; then
  pass "T3b: runs.jsonl grew by 1 line"
else
  fail "T3b: runs.jsonl grew by $new_lines lines (expected 1)"
fi

# Verify the JSON has all required fields
last_line=$(tail -1 "$TELEMETRY_FILE")
field_count=$(echo "$last_line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(len(d))" 2>/dev/null || echo 0)

if [[ "$field_count" -ge 11 ]]; then
  pass "T3c: run has $field_count fields (>= 11)"
else
  fail "T3c: run has $field_count fields (expected >= 11)"
fi

# Verify key fields
has_sid=$(echo "$last_line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('sid',''))" 2>/dev/null)
has_verdict=$(echo "$last_line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('verdict',''))" 2>/dev/null)
has_topo=$(echo "$last_line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('topology',''))" 2>/dev/null)
has_total=$(echo "$last_line" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('total_dones',0))" 2>/dev/null)

if [[ "$has_sid" == "$FIXTURE_SID" ]]; then
  pass "T3d: sid=$has_sid correct"
else
  fail "T3d: sid=$has_sid (expected $FIXTURE_SID)"
fi

if [[ "$has_verdict" == "passed" ]]; then
  pass "T3e: verdict=passed correct"
else
  fail "T3e: verdict=$has_verdict (expected passed)"
fi

if [[ "$has_topo" == "standard" ]]; then
  pass "T3f: topology=standard correct"
else
  fail "T3f: topology=$has_topo (expected standard)"
fi

if [[ "$has_total" -eq 3 ]]; then
  pass "T3g: total_dones=3 correct (from contract)"
else
  fail "T3g: total_dones=$has_total (expected 3)"
fi

# ─── T4: stats command output ───
echo ""
echo "--- T4: solar-harness stats output ---"

stats_out=$(bash "$HARNESS_DIR/solar-harness.sh" stats 2>&1)

if echo "$stats_out" | grep -q "总数"; then
  pass "T4a: stats shows 总数"
else
  fail "T4a: stats missing 总数"
fi

if echo "$stats_out" | grep -q "通过"; then
  pass "T4b: stats shows 通过"
else
  fail "T4b: stats missing 通过"
fi

if echo "$stats_out" | grep -q "standard"; then
  pass "T4c: stats shows standard topology"
else
  fail "T4c: stats missing standard topology"
fi

# ─── T5: stats sprint <sid> ───
echo ""
echo "--- T5: solar-harness stats sprint ---"

sprint_out=$(bash "$HARNESS_DIR/solar-harness.sh" stats sprint "$FIXTURE_SID" 2>&1)

if echo "$sprint_out" | grep -q "$FIXTURE_SID"; then
  pass "T5a: stats sprint shows sid"
else
  fail "T5a: stats sprint missing sid"
fi

if echo "$sprint_out" | grep -q "passed"; then
  pass "T5b: stats sprint shows verdict"
else
  fail "T5b: stats sprint missing verdict"
fi

# ─── T6: _topology_degrade_check — mixture with low pass rate ───
echo ""
echo "--- T6: _topology_degrade_check — mixture degradation ---"

# Clear and write 6 mixture runs: 5 FAIL + 1 PASS = 16.7%
: > "$TELEMETRY_FILE"
for i in 1 2 3 4 5; do
  echo '{"sid":"mixture-test-'$i'","topology":"mixture","rounds":3,"start_ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","end_ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","duration_sec":60.0,"verdict":"failed","fail_dones":["D1"],"total_dones":3,"builder_persona":"","evaluator_persona":"","codex_reviewed":false}' >> "$TELEMETRY_FILE"
done
echo '{"sid":"mixture-test-6","topology":"mixture","rounds":1,"start_ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","end_ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","duration_sec":30.0,"verdict":"passed","fail_dones":[],"total_dones":3,"builder_persona":"","evaluator_persona":"","codex_reviewed":false}' >> "$TELEMETRY_FILE"

degraded=$(_topology_degrade_check "mixture" 2>/dev/null || echo "")

if [[ "$degraded" == "standard" ]]; then
  pass "T6a: mixture degraded to standard (1/6 pass = 16.7%)"
else
  fail "T6a: mixture not degraded (got: '$degraded', expected 'standard')"
fi

# ─── T7: _topology_degrade_check — standard should NOT degrade ───
echo ""
echo "--- T7: _topology_degrade_check — standard no degrade ---"

degraded_std=$(_topology_degrade_check "standard" 2>/dev/null || echo "")
if [[ -z "$degraded_std" ]]; then
  pass "T7a: standard not degraded (correct)"
else
  fail "T7a: standard degraded to '$degraded_std' (should not)"
fi

# ─── T8: _topology_degrade_check — insufficient samples ───
echo ""
echo "--- T8: _topology_degrade_check — insufficient samples ---"

: > "$TELEMETRY_FILE"
for i in 1 2 3; do
  echo '{"sid":"few-test-'$i'","topology":"deliberation","rounds":3,"start_ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","end_ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","duration_sec":60.0,"verdict":"failed","fail_dones":[],"total_dones":2,"builder_persona":"","evaluator_persona":"","codex_reviewed":false}' >> "$TELEMETRY_FILE"
done

degraded_few=$(_topology_degrade_check "deliberation" 2>/dev/null || echo "")
if [[ -z "$degraded_few" ]]; then
  pass "T8a: deliberation not degraded with only 3 samples (< 5 min)"
else
  fail "T8a: deliberation degraded with insufficient samples"
fi

# ─── T9: _topology_degrade_check — no data ───
echo ""
echo "--- T9: _topology_degrade_check — no data ---"

: > "$TELEMETRY_FILE"
degraded_empty=$(_topology_degrade_check "mixture" 2>/dev/null || echo "")
if [[ -z "$degraded_empty" ]]; then
  pass "T9a: no degradation with empty runs.jsonl"
else
  fail "T9a: degraded with no data"
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
