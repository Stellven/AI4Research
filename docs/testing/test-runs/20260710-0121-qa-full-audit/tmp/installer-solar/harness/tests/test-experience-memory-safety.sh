#!/usr/bin/env bash
# Solar Experience Memory — Safety tests (D6)
# Verifies: no raw pane dumps, no secrets, bounded context

set -uo pipefail
cd "$(dirname "$0")/.."
HARNESS_DIR="$(pwd)"
PASS=0; FAIL=0

ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

# T1: No raw pane transcript dumps (no tmux capture-pane output) in state
HITS=$(python3 -c "
import os, glob, json
d = os.path.expanduser('~/.solar/harness/state/experience-memory')
count = 0
for f in glob.glob(os.path.join(d, '*.jsonl')):
    for line in open(f):
        if 'capture-pane' in line or 'tmux capture' in line.lower():
            count += 1
print(count)
")
[[ "$HITS" -eq 0 ]] \
  && ok "no raw pane capture output in state" \
  || fail "raw pane captures found: $HITS hits"

# T2: No secret patterns in state/experience-memory files
HITS=$(python3 -c "
import os, glob, re
d = os.path.expanduser('~/.solar/harness/state/experience-memory')
patterns = [
    re.compile(r'(?i)password\s*[=:]\s*\S{8,}'),
    re.compile(r'(?i)api[_-]?key\s*[=:]\s*\S{8,}'),
    re.compile(r'(?i)secret\s*[=:]\s*\S{8,}'),
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
]
count = 0
for f in glob.glob(os.path.join(d, '*.jsonl')):
    content = open(f).read()
    for p in patterns:
        count += len(p.findall(content))
print(count)
")
[[ "$HITS" -eq 0 ]] \
  && ok "no secrets in state/experience-memory" \
  || fail "potential secrets found: $HITS hits"

# T3: No secrets in trajectory files
HITS=$(python3 -c "
import os, glob, re
d = os.path.expanduser('~/.solar/harness/experience/trajectory')
patterns = [
    re.compile(r'(?i)password\s*[=:]\s*\S{8,}'),
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r'ghp_[A-Za-z0-9]{36,}'),
]
count = 0
for f in glob.glob(os.path.join(d, '*.json')):
    content = open(f).read()
    for p in patterns:
        count += len(p.findall(content))
print(count)
")
[[ "$HITS" -eq 0 ]] \
  && ok "no secrets in trajectory files" \
  || fail "potential secrets in trajectory files: $HITS hits"

# T4: advisory field bounded < 2048 chars in all entries
python3 -c "
import os, glob, json, sys
d1 = os.path.expanduser('~/.solar/harness/experience/entries')
d2 = os.path.expanduser('~/.solar/harness/state/experience-memory')
fails = 0
for d in [d1, d2]:
    for f in glob.glob(os.path.join(d, '*.json')) + glob.glob(os.path.join(d, '*.jsonl')):
        for line in open(f):
            if not line.strip(): continue
            try:
                entry = json.loads(line)
                adv = entry.get('advisory', '')
                if len(adv) > 2048:
                    fails += 1
                    print(f'OVERSIZED advisory in {f}: {len(adv)} chars')
            except: pass
sys.exit(fails)
" 2>/dev/null \
  && ok "all advisories bounded < 2048 chars" \
  || fail "some advisories exceed 2048 chars"

# T5: repair_recipe bounded < 2048 chars
python3 -c "
import os, glob, json, sys
dirs = [
    os.path.expanduser('~/.solar/harness/experience/entries'),
    os.path.expanduser('~/.solar/harness/state/experience-memory'),
]
fails = 0
for d in dirs:
    for f in glob.glob(os.path.join(d, '*.json')) + glob.glob(os.path.join(d, '*.jsonl')):
        for line in open(f):
            if not line.strip(): continue
            try:
                entry = json.loads(line)
                rr = entry.get('repair_recipe', '')
                if len(rr) > 2048:
                    fails += 1
            except: pass
sys.exit(fails)
" 2>/dev/null \
  && ok "all repair_recipes bounded < 2048 chars" \
  || fail "some repair_recipes exceed 2048 chars"

# T6: coordinator hook advisory block bounded < 2KB
python3 -c "
import sys, os, json
sys.path.insert(0, os.path.expanduser('~/.solar/harness/lib'))
from coordinator_hooks import pre_dispatch
d = pre_dispatch('sprint-20260509-205414', 'test')
adv = d.to_dict().get('advisory', '')
assert len(adv.encode()) < 2048, f'advisory {len(adv.encode())} bytes >= 2048'
print('ok')
" 2>/dev/null | grep -q "ok" \
  && ok "coordinator hook advisory < 2KB" \
  || fail "coordinator hook advisory too large"

# T7: no TODO/FIXME/mock/stub in implementation files
HITS=$(grep -rl 'TODO\|FIXME\|mock\|stub\|模拟' \
    lib/experience/ lib/coordinator_hooks.py 2>/dev/null | wc -l | tr -d ' ')
[[ "$HITS" -eq 0 ]] \
  && ok "no TODO/FIXME/mock/stub in implementation" \
  || fail "found TODO/mock/stub in implementation: $HITS files"

# T8: experience runner invocable
python3 lib/experience_runner.py --help 2>/dev/null || true
python3 lib/experience_runner.py stats --json >/dev/null 2>&1 \
  && ok "experience_runner.py invocable" \
  || fail "experience_runner.py failed"

# T9: decisions.jsonl entries are valid JSON
if [[ -f experience/decisions.jsonl ]]; then
  INVALID=$(python3 -c "
import json
count = 0
for line in open('experience/decisions.jsonl'):
    if not line.strip(): continue
    try: json.loads(line)
    except: count += 1
print(count)
" 2>/dev/null)
  [[ "$INVALID" -eq 0 ]] \
    && ok "decisions.jsonl all valid JSON" \
    || fail "decisions.jsonl has $INVALID invalid lines"
else
  ok "decisions.jsonl not yet written (no dispatches tested)"
fi

# T10: secret strip filter works
python3 -c "
import sys; sys.path.insert(0, 'lib')
from experience.extractor import _strip_secrets
result = _strip_secrets('api_key=mysupersecrettoken123')
assert 'mysupersecrettoken' not in result, f'secret not stripped: {result}'
print('ok')
" 2>/dev/null | grep -q "ok" \
  && ok "secret strip filter works" \
  || fail "secret strip filter broken"

# Summary
echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
