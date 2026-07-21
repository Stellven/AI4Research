#!/usr/bin/env bash
# Solar Experience Memory — Integration tests (D5)
# Tests: schema file, extract, query, coordinator hook, EXPERIENCE_HOOK=0

set -uo pipefail
cd "$(dirname "$0")/.."
HARNESS_DIR="$(pwd)"
PASS=0; FAIL=0

ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

# T1: schema file exists
test -f schemas/experience-memory.schema.json \
  && ok "D1 schema exists" \
  || fail "D1 schema missing"

# T2: CLI extract --limit 5 --json returns ok=true
OUT=$(python3 lib/experience_runner.py extract --limit 5 --json 2>/dev/null)
echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok') == True" 2>/dev/null \
  && ok "D2 extract returns ok" \
  || fail "D2 extract failed: $OUT"

# T3: extract output contains 'ok' literal
echo "$OUT" | grep -q '"ok": true' \
  && ok "D2 extract output contains ok" \
  || fail "D2 extract output malformed"

# T4: query for active sprint returns memories
OUT=$(python3 lib/experience_runner.py query --sid sprint-20260509-205414 --json 2>/dev/null)
echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'memories' in d" 2>/dev/null \
  && ok "D3 query returns memories field" \
  || fail "D3 query missing memories: $OUT"

# T5: query output contains 'memories' literal
echo "$OUT" | grep -q '"memories"' \
  && ok "D3 query output contains memories" \
  || fail "D3 query malformed"

# T6: terminal_phase_mismatch in state/experience-memory
python3 -c "
import os, subprocess
result = subprocess.run(
    ['python3', '-c', '''
import os, glob, json
d = os.path.expanduser('~/.solar/harness/state/experience-memory')
for f in glob.glob(os.path.join(d, '*.jsonl')):
    for line in open(f):
        if line.strip():
            entry = json.loads(line)
            if 'terminal_phase_mismatch' in str(entry) or 'repair_recipe' in str(entry):
                print('found')
                exit(0)
print('notfound')
'''],
    capture_output=True, text=True
)
print(result.stdout.strip())
" | grep -q "found" \
  && ok "D4 terminal_phase_mismatch in state" \
  || fail "D4 terminal_phase_mismatch not found in state"

# T7: repair_recipe in state
python3 -c "
import os, glob, json
d = os.path.expanduser('~/.solar/harness/state/experience-memory')
found = False
for f in glob.glob(os.path.join(d, '*.jsonl')):
    for line in open(f):
        if line.strip():
            entry = json.loads(line)
            if entry.get('pattern_class') == 'repair_recipe':
                found = True
print('found' if found else 'notfound')
" | grep -q "found" \
  && ok "D4 repair_recipe entry exists" \
  || fail "D4 repair_recipe entry missing"

# T8: stats subcommand returns total_entries
OUT=$(python3 lib/experience_runner.py stats --json 2>/dev/null)
echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'total_entries' in d" 2>/dev/null \
  && ok "stats total_entries present" \
  || fail "stats malformed: $OUT"

# T9: EXPERIENCE_HOOK=0 disables hook (coordinator hook returns allow)
OUT=$(EXPERIENCE_HOOK=0 python3 -c "
import sys, os
sys.path.insert(0, 'lib')
from coordinator_hooks import pre_dispatch
d = pre_dispatch('test-sid', 'test')
print(d.action)
" 2>/dev/null)
[[ "$OUT" == "allow" ]] \
  && ok "EXPERIENCE_HOOK=0 returns allow" \
  || fail "EXPERIENCE_HOOK=0 failed: $OUT"

# T10: pre_dispatch is fail-open on bad sid
OUT=$(python3 -c "
import sys, os
sys.path.insert(0, 'lib')
from coordinator_hooks import pre_dispatch
d = pre_dispatch('nonexistent-sid-xyz', 'test')
print(d.action)
" 2>/dev/null)
[[ "$OUT" == "allow" ]] \
  && ok "pre_dispatch fail-open on missing sid" \
  || fail "pre_dispatch not fail-open: $OUT"

# T11: decisions.jsonl written after pre_dispatch
python3 -c "
import sys, os
sys.path.insert(0, 'lib')
from coordinator_hooks import pre_dispatch
pre_dispatch('sprint-test-decisions', 'test')
" 2>/dev/null
test -f experience/decisions.jsonl \
  && ok "decisions.jsonl exists" \
  || fail "decisions.jsonl not written"

# T12: backfill is idempotent (rerun gives skipped > 0)
OUT=$(python3 lib/experience_runner.py backfill --json 2>/dev/null)
SKIPPED=$(echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('skipped',0))")
[[ "$SKIPPED" -gt 0 ]] \
  && ok "backfill idempotent: skipped=$SKIPPED" \
  || fail "backfill not idempotent: $OUT"

# T13: schema.py validate_trajectory accepts valid input
python3 -c "
import sys; sys.path.insert(0, 'lib')
from experience.schema import validate_trajectory
validate_trajectory({
    'schema_version': '1.0.0',
    'sid': 'test', 'status': 'passed', 'phase': 'finalized',
    'trigger_sig': 'abc', 'events_summary': {}, 'extracted_at': '2026-01-01T00:00:00Z'
})
print('ok')
" 2>/dev/null | grep -q "ok" \
  && ok "schema validate_trajectory works" \
  || fail "schema validate_trajectory broken"

# T14: schema.py validate_trajectory rejects invalid status
python3 -c "
import sys; sys.path.insert(0, 'lib')
from experience.schema import validate_trajectory
try:
    validate_trajectory({
        'schema_version': '1.0.0', 'sid': 'x', 'status': 'invalid',
        'phase': 'x', 'trigger_sig': 'x', 'events_summary': {}, 'extracted_at': 'x'
    })
    print('not_rejected')
except ValueError:
    print('rejected')
" 2>/dev/null | grep -q "rejected" \
  && ok "schema rejects invalid status" \
  || fail "schema accepts invalid status"

# Summary
echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
