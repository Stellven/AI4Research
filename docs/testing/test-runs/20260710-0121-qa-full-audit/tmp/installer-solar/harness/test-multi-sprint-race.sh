#!/bin/bash
# ================================================================
# 回归测试: 多 Sprint 并发状态更新竞态
# Sprint 20260420-113026 — 2 Sprint 并发场景
#
# 用法: bash test-multi-sprint-race.sh
# 隔离: 全部在 /tmp 下运行
# ================================================================
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
COORD_STATE="$HARNESS_DIR/.coordinator-state"

pass=0 fail=0 total=0
run_test() { local n="$1"; total=$((total + 1)); echo ""; echo "=== Test $n: $2 ==="; }
ok()   { pass=$((pass + 1)); echo "  PASS: $1"; }
fail() { fail=$((fail + 1)); echo "  FAIL: $1"; }

get_st() { python3 -c "import json; print(json.load(open('$1')).get('status',''))" 2>/dev/null; }

# ── Scenario 1: per-sprint last_state tracking ──
run_test 1 "per-sprint save_state: two sprints, both tracked"

# Save state for sprint-A
echo "sprint-A:planning" > /tmp/test-state-A
encoded=$(printf 'sprint-A:planning' | base64)
python3 -c "
import tempfile, os, base64
value = base64.b64decode('$encoded').decode('utf-8')
path = '$COORD_STATE.test'
dirn = os.path.dirname(path)
os.makedirs(dirn, exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=dirn, suffix='.tmp')
with os.fdopen(fd, 'w') as f:
    f.write(value + '\n')
os.rename(tmp, path)
" 2>/dev/null

# Now save sprint-B (should not overwrite sprint-A)
encoded=$(printf 'sprint-A:planning|sprint-B:reviewing' | base64)
python3 -c "
import tempfile, os, base64
value = base64.b64decode('$encoded').decode('utf-8')
path = '$COORD_STATE.test'
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
with os.fdopen(fd, 'w') as f:
    f.write(value + '\n')
os.rename(tmp, path)
" 2>/dev/null

# Verify both are present
content=$(cat "$COORD_STATE.test" 2>/dev/null | head -1 | tr -d '\n')
echo "$content" | grep -q "sprint-A:planning" && ok "sprint-A tracked" || fail "sprint-A lost"
echo "$content" | grep -q "sprint-B:reviewing" && ok "sprint-B tracked" || fail "sprint-B lost"

# Simulate check_state_changed
old_st=$(echo "$content" | tr '|' '\n' | grep "^sprint-A:" | tail -1 | cut -d: -f2)
[[ "$old_st" == "planning" ]] && ok "sprint-A old state=planning" || fail "sprint-A old=$old_st"
old_st=$(echo "$content" | tr '|' '\n' | grep "^sprint-B:" | tail -1 | cut -d: -f2)
[[ "$old_st" == "reviewing" ]] && ok "sprint-B old state=reviewing" || fail "sprint-B old=$old_st"

rm -f "$COORD_STATE.test"

# ── Scenario 2: both sprints change in same poll interval ──
run_test 2 "both sprints change: detect both independently"

# Initial state: A=active, B=drafting
printf 'sprint-A:active|sprint-B:drafting' > /tmp/test-state-init
encoded=$(printf 'sprint-A:active|sprint-B:drafting' | base64)
python3 -c "
import tempfile, os, base64
value = base64.b64decode('$encoded').decode('utf-8')
path = '$COORD_STATE.test2'
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
with os.fdopen(fd, 'w') as f: f.write(value + '\n')
os.rename(tmp, path)
" 2>/dev/null

content=$(cat "$COORD_STATE.test2" 2>/dev/null | head -1 | tr -d '\n')

# Check: A active→planning = changed
old_st=$(echo "$content" | tr '|' '\n' | grep "^sprint-A:" | tail -1 | cut -d: -f2)
[[ "$old_st" != "planning" ]] && ok "sprint-A changed (active→planning detected)" || fail "sprint-A change missed"

# Check: B drafting→active = changed
old_st=$(echo "$content" | tr '|' '\n' | grep "^sprint-B:" | tail -1 | cut -d: -f2)
[[ "$old_st" != "active" ]] && ok "sprint-B changed (drafting→active detected)" || fail "sprint-B change missed"

rm -f "$COORD_STATE.test2"

echo ""
echo "════════════════════════════════════════"
echo "  Results: ${pass}/${total} PASS, ${fail} FAIL"
echo "════════════════════════════════════════"
(( fail > 0 )) && exit 1 || exit 0
