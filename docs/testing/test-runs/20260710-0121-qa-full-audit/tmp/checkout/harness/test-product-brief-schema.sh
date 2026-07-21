#!/bin/bash
# test-product-brief-schema.sh — D4: Product brief schema validation
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SCHEMA="$HARNESS_DIR/schemas/product-brief.schema.json"
PASS=0 FAIL=0

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-product-brief-schema.sh ==="

# T1: Schema file exists and is valid JSON
echo ""
echo "--- T1: Schema file exists ---"
if python3 -c "import json; json.load(open('$SCHEMA'))" 2>/dev/null; then
  pass "T1a: schema is valid JSON"
else
  fail "T1a: schema is not valid JSON"
fi

# T2: Required fields check
echo ""
echo "--- T2: Required fields ---"
REQUIRED="title source intent problem priority lane_hint acceptance non_goals stop_rules handoff_to"
for field in $REQUIRED; do
  if python3 -c "import json; s=json.load(open('$SCHEMA')); assert '$field' in s['required']" 2>/dev/null; then
    pass "T2: $field in required"
  else
    fail "T2: $field missing from required"
  fi
done

# T3: lane_hint enum includes delivery/lab/strategy
echo ""
echo "--- T3: lane_hint enums ---"
for lane in delivery lab strategy; do
  if python3 -c "import json; s=json.load(open('$SCHEMA')); assert '$lane' in s['properties']['lane_hint']['enum']" 2>/dev/null; then
    pass "T3: lane_hint includes $lane"
  else
    fail "T3: lane_hint missing $lane"
  fi
done

# T4: Valid sample passes validation
echo ""
echo "--- T4: Valid sample ---"
python3 -c "
import json
schema = json.load(open('$SCHEMA'))
sample = {
    'title': 'Test brief',
    'source': 'user',
    'intent': 'Fix cache miss',
    'problem': 'Cache stops matching at block 67',
    'priority': 'P0',
    'lane_hint': 'lab',
    'acceptance': ['Diagnosis report produced'],
    'non_goals': ['Modify cache logic'],
    'stop_rules': ['Verdict classified'],
    'handoff_to': 'planner'
}
# Validate required fields
for f in schema['required']:
    assert f in sample, f'Missing required: {f}'
# Validate enums
assert sample['priority'] in schema['properties']['priority']['enum']
assert sample['lane_hint'] in schema['properties']['lane_hint']['enum']
assert sample['handoff_to'] in schema['properties']['handoff_to']['enum']
print('VALID')
" 2>/dev/null && pass "T4: valid sample passes" || fail "T4: valid sample fails"

# T5: Invalid sample (missing required) fails
echo ""
echo "--- T5: Invalid sample ---"
python3 -c "
import json
schema = json.load(open('$SCHEMA'))
sample = {'title': 'Incomplete'}
for f in schema['required']:
    if f not in sample:
        print('INVALID_CORRECTLY_DETECTED')
        break
else:
    print('ERROR: should have detected missing fields')
" 2>/dev/null | grep -q "INVALID_CORRECTLY_DETECTED" && pass "T5: invalid sample detected" || fail "T5: invalid sample not detected"

# T6: Template file exists
echo ""
echo "--- T6: Template exists ---"
test -f "$HARNESS_DIR/templates/product-brief.template.md" && pass "T6: template exists" || fail "T6: template missing"

# T7: farm-layout.json valid
echo ""
echo "--- T7: farm-layout.json ---"
if python3 -c "import json; d=json.load(open('$HARNESS_DIR/farm-layout.json')); assert len(d['windows']) == 2; assert len(d['windows'][0]['panes']) == 4; assert len(d['windows'][1]['panes']) == 4" 2>/dev/null; then
  pass "T7: farm-layout.json has 2 windows x 4 panes"
else
  fail "T7: farm-layout.json invalid"
fi

# Summary
echo ""
echo "=== Results: $PASS PASS / $FAIL FAIL ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL_TESTS_PASS"
exit 0
