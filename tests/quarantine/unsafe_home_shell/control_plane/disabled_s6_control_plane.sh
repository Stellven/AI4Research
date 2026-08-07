#!/usr/bin/env bash
# S6 Control Plane test suite — sprint-20260509-solar-product-platform
# Tests: state DB, task queue, pane lease, autopilot, harness subcommands
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
LIB="$HARNESS_DIR/lib"
PASS=0; FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (got: $actual)"; fi
}

# Isolated temp dir for state.db and queue/lease dirs
TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT
export HARNESS_STATE_DB="$TMPDIR_TEST/state.db"
export HARNESS_DIR_OVERRIDE="$TMPDIR_TEST"

# ── T1: py_compile all four modules ──────────────────────────────────────────
echo "T1: py_compile"
for mod in solar_state_db task_queue pane_lease autopilot; do
  python3 -m py_compile "$LIB/${mod}.py" 2>&1 && ok "${mod}.py compiles" || fail "${mod}.py compile error"
done

# ── T2: bash -n solar-harness.sh ─────────────────────────────────────────────
echo "T2: bash -n solar-harness.sh"
bash -n "$HARNESS_DIR/solar-harness.sh" 2>&1 && ok "solar-harness.sh syntax ok" || fail "syntax error"

# ── T3: schema validates (well-formed JSON) ───────────────────────────────────
echo "T3: task-lifecycle.schema.json valid"
python3 -c "
import json, sys
s = json.load(open('$HARNESS_DIR/schemas/task-lifecycle.schema.json'))
assert s.get('\$schema'), 'missing \$schema'
assert 'properties' in s, 'missing properties'
assert 'x-state-transitions' in s, 'missing x-state-transitions'
assert 'x-status-json-mapping' in s, 'missing x-status-json-mapping'
print('ok')
" 2>/dev/null | grep -q "ok" && ok "schema valid JSON + required fields" || fail "schema invalid"

# ── T4: solar_state_db init ───────────────────────────────────────────────────
echo "T4: solar_state_db init"
OUT=$(python3 "$LIB/solar_state_db.py" init 2>/dev/null)
check "init ok" "$OUT" '"ok": true'
check "init db path" "$OUT" 'state.db'

# ── T5: task-upsert + task-status ────────────────────────────────────────────
echo "T5: task-upsert + task-status"
SID="sprint-test-s6"
python3 "$LIB/solar_state_db.py" task-upsert --sprint "$SID" --slice S0 --status pending --gate G0 --priority 100 2>/dev/null
OUT=$(python3 "$LIB/solar_state_db.py" task-status --sprint "$SID" --slice S0 2>/dev/null)
check "task upsert ok" "$OUT" '"slice_id": "S0"'
check "task status pending" "$OUT" '"status": "pending"'
check "task gate G0" "$OUT" '"gate": "G0"'

# ── T6: gate-pass unblocks dependent slices ───────────────────────────────────
echo "T6: gate-pass unblocks dependents"
# Insert S1 blocked by S0
python3 "$LIB/solar_state_db.py" task-upsert --sprint "$SID" --slice S1 --status blocked --gate G2 --blocked-by S0 2>/dev/null
# Mark S0 gate passed → should unblock S1
OUT=$(python3 "$LIB/solar_state_db.py" gate-pass --sprint "$SID" --gate G0 2>/dev/null)
check "gate-pass ok" "$OUT" '"ok": true'
check "gate G0 unblocked S1" "$OUT" '"S1"'
OUT=$(python3 "$LIB/solar_state_db.py" task-status --sprint "$SID" --slice S1 2>/dev/null)
check "S1 now pending" "$OUT" '"status": "pending"'

# ── T7: task queue enqueue + pop ──────────────────────────────────────────────
echo "T7: task queue enqueue + pop"
mkdir -p "$TMPDIR_TEST/run/queue" "$TMPDIR_TEST/run/pane-leases"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 -c "
import sys, os
sys.path.insert(0, '$LIB')
from pathlib import Path
os.environ['HARNESS_DIR'] = '$TMPDIR_TEST'
# Reload module with overridden HARNESS_DIR
import importlib
import task_queue
importlib.reload(task_queue)

r1 = task_queue.enqueue('sprint-q-test', 'build_s1|role=builder', 100)
assert r1['result'] == 'enqueued', f'bad result: {r1}'

r2 = task_queue.enqueue('sprint-q-test', 'build_s1|role=builder', 100)
assert r2['result'] == 'duplicate', f'expected duplicate: {r2}'

d = task_queue.depth('sprint-q-test')
assert d == 1, f'depth={d}'

item = task_queue.pop('sprint-q-test')
assert item is not None
assert item.get('intent') == 'build_s1|role=builder'
assert task_queue.depth('sprint-q-test') == 0
print('ok')
" 2>/dev/null)
[[ "$OUT" == *"ok"* ]] && ok "enqueue + dedup + pop + depth" || fail "queue test failed (got: $OUT)"

# ── T8: pane_lease 3-state classification (no tmux) ──────────────────────────
echo "T8: pane_lease state classification"
OUT=$(python3 -c "
import sys, os
sys.path.insert(0, '$LIB')
os.environ['HARNESS_DIR'] = '$TMPDIR_TEST'
from pathlib import Path
lease_dir = Path('$TMPDIR_TEST/run/pane-leases')
lease_dir.mkdir(parents=True, exist_ok=True)

# Inject a fake expired lease file
import json, datetime
expired_ts = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
fake = {'pane': 'solar-harness:0.9', 'sprint_id': 'test', 'dispatch_id': 'd-expired',
        'acquired_at': expired_ts, 'expires_at': expired_ts, 'ttl_sec': 600}
(lease_dir / 'solar-harness_0_9.json').write_text(json.dumps(fake))
(lease_dir / 'solar-harness_0_9.json.lock').write_text('')
(lease_dir / 'solar-harness_0_8.json.lock').write_text('')

# pane_state should return 'no_pane' (tmux not running in test env)
from pane_lease import pane_state
s = pane_state('solar-harness:0.9')
assert s in ('no_pane', 'dead'), f'expected no_pane or dead, got {s}'

# reap should remove expired lease
from pane_lease import reap
r = reap()
assert r['reaped'] >= 1, f'reap count: {r}'
assert not (lease_dir / 'solar-harness_0_9.json').exists()
assert not (lease_dir / 'solar-harness_0_9.json.lock').exists()
assert not (lease_dir / 'solar-harness_0_8.json.lock').exists()

# release should remove its lock, including the already-gone case
from pane_lease import release
future_ts = (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
active = {'pane': 'solar-harness:0.7', 'sprint_id': 'test', 'dispatch_id': 'd-active',
          'acquired_at': expired_ts, 'expires_at': future_ts, 'ttl_sec': 600}
(lease_dir / 'solar-harness_0_7.json').write_text(json.dumps(active))
(lease_dir / 'solar-harness_0_7.json.lock').write_text('')
rel = release('solar-harness:0.7', 'd-active', 'test_release')
assert rel['released'] is True, rel
assert not (lease_dir / 'solar-harness_0_7.json').exists()
assert not (lease_dir / 'solar-harness_0_7.json.lock').exists()
(lease_dir / 'solar-harness_0_6.json.lock').write_text('')
rel = release('solar-harness:0.6', 'd-missing', 'missing_release')
assert rel['released'] is True, rel
assert not (lease_dir / 'solar-harness_0_6.json.lock').exists()
print('ok')
" 2>/dev/null)
check "pane_lease 3-state + reap/release lock cleanup" "$OUT" "ok"

# ── T9: autopilot fault-report (no tmux, no faults baseline) ─────────────────
echo "T9: autopilot fault-report baseline"
# Reset HARNESS_DIR to harness for fault-report scanning sprints
OUT=$(HARNESS_STATE_DB="$TMPDIR_TEST/state.db" python3 "$LIB/autopilot.py" fault-report --sprint "sprint-test-nonexistent-xyz" 2>/dev/null)
check "fault-report ok" "$OUT" '"ok": true'
check "fault-report sprint" "$OUT" '"sprint_id"'

# ── T10: solar-harness subcommand routing ─────────────────────────────────────
echo "T10: solar-harness s6-autopilot + leases subcommands"
OUT=$(bash "$HARNESS_DIR/solar-harness.sh" s6-autopilot help 2>/dev/null || true)
check "s6-autopilot help" "$OUT" "Solar S6 Autopilot"
OUT=$(bash "$HARNESS_DIR/solar-harness.sh" leases help 2>/dev/null || true)
check "leases help" "$OUT" "Solar Pane Leases"

# ── T11: schema x-status-json-mapping covers existing status.json states ──────
echo "T11: schema maps all existing status.json states"
python3 -c "
import json
schema = json.load(open('$HARNESS_DIR/schemas/task-lifecycle.schema.json'))
mapping = schema.get('x-status-json-mapping', {}).get('mappings', {})
expected = {'queued', 'drafting', 'planning', 'active', 'reviewing', 'passed', 'finalized'}
missing = expected - set(mapping.keys())
assert not missing, f'mapping missing states: {missing}'
print('ok')
" 2>/dev/null | grep -q "ok" && ok "schema maps all status.json states" || fail "schema missing mappings"

# ── T12: parent-check reports correctly ───────────────────────────────────────
echo "T12: parent-check before + after all slices pass"
PSID="sprint-parent-check-test"
python3 "$LIB/solar_state_db.py" task-upsert --sprint "$PSID" --slice S0 --status passed 2>/dev/null
python3 "$LIB/solar_state_db.py" task-upsert --sprint "$PSID" --slice S1 --status in_progress 2>/dev/null
OUT=$(python3 "$LIB/solar_state_db.py" parent-check --sprint "$PSID" 2>/dev/null)
check "parent-check not ready" "$OUT" '"ready": false'
# Mark S1 passed
python3 "$LIB/solar_state_db.py" task-upsert --sprint "$PSID" --slice S1 --status passed 2>/dev/null
OUT=$(python3 "$LIB/solar_state_db.py" parent-check --sprint "$PSID" 2>/dev/null)
check "parent-check ready when all passed" "$OUT" '"ready": true'

echo ""
echo "=== S6 Control Plane: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
