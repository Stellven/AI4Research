#!/usr/bin/env bash
# Regression test: queued wake routing must not fall through to generic builder.

set -uo pipefail
cd "$(dirname "$0")/.."
PASS=0
FAIL=0

ok() { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

SCRIPT="solar-harness.sh"
STATE_MAPPER="lib/state-mapper.sh"

python3 - <<'PY'
from pathlib import Path
s = Path("solar-harness.sh").read_text()
queued = s.index("    queued)")
drafting = s.index("    drafting|drafting_held)")
wildcard = s.index("    *)", drafting)
assert queued < drafting < wildcard
assert "wake_workflow_guard_to_planner" in s
assert "wake_workflow_guard_to_builder" in s
assert "wake_workflow_guard_to_pm" in s
assert "route_by_workflow_guard" in s[queued:drafting]
guard = s.index("route_by_workflow_guard()")
assert "runtime_status.py" in s[guard:queued]
assert '"auto_held":false' in s[guard:queued]
assert "未知状态: ${st}，派发给 PM 做状态诊断" in s
PY
[[ $? -eq 0 ]] && ok "wake routes queued through workflow guard before wildcard" || fail "queued workflow guard missing or ordered incorrectly"

grep -q "contract_ready and legacy handoff_to=builder must still enter PM" "$STATE_MAPPER" \
  && ok "state mapper keeps queued contract_ready/builder legacy at PM intake" \
  || fail "state mapper still exposes legacy queued shortcut"

grep -q "phase in ('prd_ready',) or handoff_to == 'planner'" "$STATE_MAPPER" \
  && ok "state mapper routes queued prd_ready to planner" \
  || fail "state mapper does not route queued prd_ready to planner"

bash -n "$SCRIPT" \
  && ok "solar-harness.sh syntax ok" \
  || fail "solar-harness.sh syntax failed"

bash -n "$STATE_MAPPER" \
  && ok "state-mapper.sh syntax ok" \
  || fail "state-mapper.sh syntax failed"

python3 - <<'PY'
from pathlib import Path
s = Path("coordinator.sh").read_text()
assert "status_has_bypass_pm()" in s
assert "sprint_bypasses_pm_gate()" in s
assert "planner_artifacts_ready" in s
assert "task_graph.json" in s
PY
[[ $? -eq 0 ]] && ok "coordinator gate requires workflow guard/task_graph" || fail "coordinator workflow guard missing"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
