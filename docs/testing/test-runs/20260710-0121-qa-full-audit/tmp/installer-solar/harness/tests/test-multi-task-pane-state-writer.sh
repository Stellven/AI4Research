#!/usr/bin/env bash
# test-multi-task-pane-state-writer.sh
#
# Smoke test for multi_task_pane_state_writer.py.
# Runs writer in --dry-run and --probe (live) modes against the current tmux
# environment and asserts schema_version + pane count == 8 + state-enum membership.
# Exit 0 = all tests pass.

set -euo pipefail

WRITER="python3 ${HOME}/.solar/harness/tools/multi_task_pane_state_writer.py"
STATE_FILE="${HOME}/.solar/harness/state/pane-state.json"
PASS=0
FAIL=0

pass() { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }

echo "=== test-multi-task-pane-state-writer.sh ==="

# ---------- T1: dry-run produces valid JSON ----------
echo ""
echo "--- T1: dry-run produces valid JSON ---"
DRY_OUT=$($WRITER --dry-run 2>/dev/null)
if echo "$DRY_OUT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    pass "dry-run output is valid JSON"
else
    fail "dry-run output is not valid JSON"
fi

# ---------- T2: schema_version ----------
echo ""
echo "--- T2: schema_version ---"
SV=$(echo "$DRY_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['schema_version'])" 2>/dev/null || echo "ERROR")
if [ "$SV" = "multi_task_screen.pane_state.v1" ]; then
    pass "schema_version == multi_task_screen.pane_state.v1"
else
    fail "schema_version = '$SV' (expected multi_task_screen.pane_state.v1)"
fi

# ---------- T3: pane count == 8 ----------
echo ""
echo "--- T3: pane count == 8 ---"
PCOUNT=$(echo "$DRY_OUT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['panes']))" 2>/dev/null || echo "0")
if [ "$PCOUNT" = "8" ]; then
    pass "pane count == 8"
else
    fail "pane count = $PCOUNT (expected 8)"
fi

# ---------- T4: state-enum membership ----------
echo ""
echo "--- T4: state-enum membership ---"
ENUM_RESULT=$(echo "$DRY_OUT" | python3 -c "
import json, sys
valid = {'ok','warn','error','idle','active','blocked','dry_run','ready','working','pending'}
data = json.load(sys.stdin)
bad = [(p['id'], p['state']) for p in data['panes'] if p['state'] not in valid]
print('BAD:' + str(bad) if bad else 'OK')
" 2>/dev/null || echo "ERROR")
if [ "$ENUM_RESULT" = "OK" ]; then
    pass "all pane states in valid enum"
else
    fail "invalid states: $ENUM_RESULT"
fi

# ---------- T5: required fields on every pane ----------
echo ""
echo "--- T5: required fields {id,role,state,model,low_confidence,mtime} ---"
FIELDS_RESULT=$(echo "$DRY_OUT" | python3 -c "
import json, sys
required = {'id','role','state','model','low_confidence','mtime'}
data = json.load(sys.stdin)
bad = [p['id'] for p in data['panes'] if not required.issubset(p.keys())]
print('MISSING:' + str(bad) if bad else 'OK')
" 2>/dev/null || echo "ERROR")
if [ "$FIELDS_RESULT" = "OK" ]; then
    pass "all panes have required fields"
else
    fail "missing fields: $FIELDS_RESULT"
fi

# ---------- T6: low_confidence is bool ----------
echo ""
echo "--- T6: low_confidence type == bool ---"
BOOL_RESULT=$(echo "$DRY_OUT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
bad = [p['id'] for p in data['panes'] if not isinstance(p['low_confidence'], bool)]
print('NOT_BOOL:' + str(bad) if bad else 'OK')
" 2>/dev/null || echo "ERROR")
if [ "$BOOL_RESULT" = "OK" ]; then
    pass "low_confidence is bool on all panes"
else
    fail "non-bool low_confidence: $BOOL_RESULT"
fi

# ---------- T7: live mode (--probe) writes file ----------
echo ""
echo "--- T7: --probe writes state/pane-state.json ---"
rm -f "$STATE_FILE"
$WRITER --probe 2>/dev/null
if [ -s "$STATE_FILE" ]; then
    pass "state file written and non-empty"
else
    fail "state file missing or empty after --probe"
fi

# ---------- T8: live file validates ----------
echo ""
echo "--- T8: live file schema + pane count + state-enum ---"
LIVE_RESULT=$(python3 -c "
import json
d = json.load(open('${STATE_FILE}'))
assert d['schema_version'] == 'multi_task_screen.pane_state.v1', 'schema_version mismatch'
assert len(d['panes']) == 8, 'pane count = ' + str(len(d['panes'])) + ' != 8'
valid = {'ok','warn','error','idle','active','blocked','dry_run','ready','working','pending'}
for p in d['panes']:
    assert p['state'] in valid, 'invalid state ' + p['state'] + ' for ' + p['id']
    assert isinstance(p['low_confidence'], bool), 'low_confidence not bool for ' + p['id']
print('OK')
" 2>/dev/null || echo "ERROR")
if [ "$LIVE_RESULT" = "OK" ]; then
    pass "live file: schema_version + 8 panes + valid states + low_confidence types"
else
    fail "live file validation: $LIVE_RESULT"
fi

# ---------- T9: atomic write leaves no .tmp residue ----------
echo ""
echo "--- T9: atomic write leaves no .tmp residue ---"
$WRITER --probe 2>/dev/null
TMP_FILE="${STATE_FILE}.tmp"
if [ ! -f "$TMP_FILE" ]; then
    pass "no .tmp residue after write"
else
    fail ".tmp file still exists after write (${TMP_FILE})"
fi

# ---------- T10: --set changes one pane state ----------
echo ""
echo "--- T10: --set main:0 working ---"
$WRITER --set main:0 working 2>/dev/null
SET_RESULT=$(python3 -c "
import json
d = json.load(open('${STATE_FILE}'))
p = next((x for x in d['panes'] if x['id'] == 'main:0'), None)
assert p is not None, 'pane main:0 not found'
assert p['state'] == 'working', 'state = ' + p['state'] + ' (expected working)'
assert p['low_confidence'] == False, 'low_confidence should be False after --set'
print('OK')
" 2>/dev/null || echo "ERROR")
if [ "$SET_RESULT" = "OK" ]; then
    pass "--set main:0 working: state=working, low_confidence=False"
else
    fail "--set result: $SET_RESULT"
fi

# ---------- Summary ----------
echo ""
echo "=== Results: PASS=${PASS}  FAIL=${FAIL} ==="
if [ "${FAIL}" -eq 0 ]; then
    echo "EXIT 0 — all tests passed"
    exit 0
else
    echo "EXIT 1 — ${FAIL} test(s) failed"
    exit 1
fi
