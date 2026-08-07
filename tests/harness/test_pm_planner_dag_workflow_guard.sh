#!/usr/bin/env bash
# Regression test: PM -> Planner -> task_graph -> Builder is mandatory.

set -euo pipefail
cd "$(dirname "$0")/.."

PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT
mkdir -p "$TMPDIR_TEST/sprints"

ok() { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

route_field() {
  HARNESS_DIR="$TMPDIR_TEST" SPRINTS_DIR="$TMPDIR_TEST/sprints" \
    python3 lib/workflow_guard.py route "$1" --field "$2"
}

write_status() {
  local sid="$1" status="$2" phase="${3:-}" handoff="${4:-}"
  python3 - "$TMPDIR_TEST/sprints/${sid}.status.json" "$sid" "$status" "$phase" "$handoff" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1])
sid,status,phase,handoff=sys.argv[2:6]
p.write_text(json.dumps({
  "id": sid,
  "status": status,
  "phase": phase,
  "handoff_to": handoff,
  "target_role": handoff,
}, ensure_ascii=False, indent=2))
PY
}

write_graph() {
  local sid="$1"
  cat > "$TMPDIR_TEST/sprints/${sid}.task_graph.json" <<JSON
{
  "sprint_id": "${sid}",
  "nodes": [
    {
      "id": "S1",
      "goal": "implement one isolated slice",
      "depends_on": [],
      "write_scope": ["lib/example.py"],
      "read_scope": ["${sid}.prd.md", "${sid}.plan.md"],
      "required_skills": ["graph-scheduler"],
      "preferred_model": "glm-5.1",
      "gate": "unit_test",
      "acceptance": ["test passes"],
      "estimated_cost": "S"
    }
  ]
}
JSON
}

assert_route() {
  local sid="$1" expected="$2" label="$3"
  local got
  got="$(route_field "$sid" route_role)"
  if [[ "$got" == "$expected" ]]; then ok "$label"; else fail "$label expected=$expected got=$got"; fi
}

SID="sprint-test-workflow-guard"
write_status "$SID" "queued" "contract_ready" "builder_main"
cat > "$TMPDIR_TEST/sprints/${SID}.contract.md" <<'MD'
bypass_pm: true
handoff_to: builder_main

用户原话：做一个功能。
MD
assert_route "$SID" "pm" "queued contract_ready + bypass_pm still routes PM"
route_field "$SID" violations | grep -q "builder_route_without_prd_design_plan_task_graph" \
  && ok "legacy builder shortcut is reported as violation" \
  || fail "legacy builder shortcut violation missing"

cat > "$TMPDIR_TEST/sprints/${SID}.prd.md" <<'MD'
# PRD
## 背景
测试。
## 验收标准
- 有 DAG。
MD
assert_route "$SID" "planner" "PRD only routes planner"

cat > "$TMPDIR_TEST/sprints/${SID}.design.md" <<'MD'
# Design
MD
cat > "$TMPDIR_TEST/sprints/${SID}.plan.md" <<'MD'
# Plan
MD
assert_route "$SID" "planner" "design+plan without task_graph stays planner"

write_graph "$SID"
assert_route "$SID" "builder_main" "PRD+design+plan+task_graph routes builder_main"

SID_BLOCKED="sprint-test-prereq-blocked"
SID_UPSTREAM="sprint-test-upstream"
write_status "$SID_BLOCKED" "queued" "epic_waiting_dependency" ""
cat > "$TMPDIR_TEST/sprints/${SID_BLOCKED}.prd.md" <<< "# PRD"
cat > "$TMPDIR_TEST/sprints/${SID_BLOCKED}.design.md" <<< "# Design"
cat > "$TMPDIR_TEST/sprints/${SID_BLOCKED}.plan.md" <<< "# Plan"
write_graph "$SID_BLOCKED"
python3 - "$TMPDIR_TEST/sprints/${SID_BLOCKED}.task_graph.json" "$SID_UPSTREAM" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1])
upstream=sys.argv[2]
g=json.loads(p.read_text())
g["prerequisites"]=[f"{upstream}:passed"]
g["dependency_policy"]={"blocks_until":[f"{upstream}:passed"]}
p.write_text(json.dumps(g, ensure_ascii=False, indent=2))
PY
write_status "$SID_UPSTREAM" "active" "planning_complete" "builder_main"
assert_route "$SID_BLOCKED" "none" "unmet external prerequisite blocks builder route"
route_field "$SID_BLOCKED" reason | grep -q "external_prerequisite_blocked" \
  && ok "external prerequisite block reason reported" \
  || fail "external prerequisite block reason missing"
write_status "$SID_UPSTREAM" "passed" "eval_passed" ""
assert_route "$SID_BLOCKED" "builder_main" "passed external prerequisite releases builder route"

SID2="sprint-test-invalid-graph"
write_status "$SID2" "active" "planning_complete" "builder_main"
cat > "$TMPDIR_TEST/sprints/${SID2}.prd.md" <<< "# PRD"
cat > "$TMPDIR_TEST/sprints/${SID2}.design.md" <<< "# Design"
cat > "$TMPDIR_TEST/sprints/${SID2}.plan.md" <<< "# Plan"
cat > "$TMPDIR_TEST/sprints/${SID2}.task_graph.json" <<< '{"nodes":[{"id":"S1"}]}'
assert_route "$SID2" "planner" "invalid task_graph blocks builder"
route_field "$SID2" violations | grep -q "invalid_task_graph" \
  && ok "invalid task_graph violation reported" \
  || fail "invalid task_graph violation missing"

SID3="sprint-test-node-level-planner-artifacts"
write_status "$SID3" "drafting" "spec" "pm"
cat > "$TMPDIR_TEST/sprints/${SID3}.prd.md" <<< "# PRD"
cat > "$TMPDIR_TEST/sprints/${SID3}.S1-design.md" <<< "# S1 Design"
cat > "$TMPDIR_TEST/sprints/${SID3}.S1-plan.md" <<< "# S1 Plan"
write_graph "$SID3"
assert_route "$SID3" "builder_main" "node-level planner artifacts count as planner-ready"

bash -n solar-harness.sh && ok "solar-harness.sh syntax ok" || fail "solar-harness.sh syntax failed"
bash -n coordinator.sh && ok "coordinator.sh syntax ok" || fail "coordinator.sh syntax failed"
python3 -m py_compile lib/workflow_guard.py && ok "workflow_guard.py compiles" || fail "workflow_guard.py compile failed"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
