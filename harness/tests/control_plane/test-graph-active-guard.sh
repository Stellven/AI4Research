#!/usr/bin/env bash
# Regression: active DAG parents must be driven through graph-dispatch, not the
# generic parent builder dispatch path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR_REAL="${HARNESS_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
COORD="$HARNESS_DIR_REAL/coordinator.sh"

PASS=0
FAIL=0

ok() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "T1: coordinator syntax"
bash -n "$COORD" && ok "coordinator bash -n" || fail "coordinator bash -n"

echo "T2: graph_dispatch_active guarded before parent builder dispatch"
if grep -q '"$phase" == "graph_dispatch_active"' "$COORD"; then
  ok "graph_dispatch_active condition present"
else
  fail "graph_dispatch_active condition missing"
fi

if python3 - "$COORD" <<'PY'
import sys
p=sys.argv[1]
s=open(p, encoding="utf-8").read()
guard=s.index('if [[ "$phase" == "graph_dispatch_active" || "$phase" == "planning_complete" ]]; then')
missing=s.index('task_graph missing; refuse parent builder dispatch', guard)
planner=s.index('dispatch_to_planner "$sid" "gate_missing_task_graph"', missing)
blocked=s.index('"active_blocked_missing_task_graph"', planner)
returned=s.index('return 0', blocked)
parent=s.index('Sprint 进入 active → 建设者写实现计划')
assert guard < missing < planner < blocked < returned < parent
PY
then
  ok "missing graph refuses parent builder dispatch before generic parent builder dispatch"
else
  fail "missing graph guard absent or ordered after parent builder dispatch"
fi

echo "T3: startup recovery covers active/planning_complete DAG states"
if python3 - "$COORD" <<'PY'
import sys
s=open(sys.argv[1], encoding="utf-8").read()
start=s.index('Startup actionable-state recovery')
snippet=s[start:s.index('if [[ "$planning_recovery_count" -gt 0 ]]', start)]
assert '"$rst" == "active"' in snippet
assert '"$rphase" == "planning_complete"' in snippet
assert '"$rphase" == "graph_dispatch_active"' in snippet
assert 'DAG-ready builder handoff' in snippet
PY
then
  ok "startup recovery replays active/planning_complete DAG handoff"
else
  fail "startup recovery still misses active/planning_complete DAG handoff"
fi

echo "T4: DAG failed_review suppresses legacy builder repair"
if python3 - "$COORD" <<'PY'
import sys
s=open(sys.argv[1], encoding="utf-8").read()
helper=s.index('failed_review_graph_native_guard()')
handler=s.index('handle_failed_review()')
guard=s.index('failed_review_legacy_builder_blocked', handler)
legacy=s.index('failed_review_returned_to_builder', handler)
assert helper < handler < guard < legacy
assert 'active_nodes' in s[helper:handler]
assert 'failed_nodes' in s[helper:handler]
PY
then
  ok "failed_review DAG guard blocks legacy builder repair before dispatch"
else
  fail "failed_review DAG guard missing or ordered after legacy builder repair"
fi

echo ""
echo "=== Graph Active Guard: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
