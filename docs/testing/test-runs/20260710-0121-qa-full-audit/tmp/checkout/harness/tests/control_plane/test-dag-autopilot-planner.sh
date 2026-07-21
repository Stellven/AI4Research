#!/usr/bin/env bash
# DAG autopilot + planner contract regression tests
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
PASS=0
FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (got: $actual)"; fi
}

TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT
mkdir -p "$TMPDIR_TEST/sprints" "$TMPDIR_TEST/lib" "$TMPDIR_TEST/tools" "$TMPDIR_TEST/run/queue" "$TMPDIR_TEST/run/pane-leases" "$TMPDIR_TEST/events"

cp "$HARNESS_DIR_REAL/lib/graph_scheduler.py" "$TMPDIR_TEST/lib/graph_scheduler.py"
cp "$HARNESS_DIR_REAL/lib/task_queue.py" "$TMPDIR_TEST/lib/task_queue.py"
cp "$HARNESS_DIR_REAL/lib/pane_lease.py" "$TMPDIR_TEST/lib/pane_lease.py"
cp "$HARNESS_DIR_REAL/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/tools/solar-autopilot-monitor.py"

SID="sprint-test-dag-autopilot"
cat > "$TMPDIR_TEST/sprints/${SID}.status.json" <<JSON
{
  "sprint_id": "${SID}",
  "status": "active",
  "phase": "planning_complete",
  "handoff_to": "builder_parallel",
  "priority": "P0",
  "history": []
}
JSON
cat > "$TMPDIR_TEST/sprints/${SID}.contract.md" <<'EOF'
# Contract
EOF
cat > "$TMPDIR_TEST/sprints/${SID}.plan.md" <<'EOF'
# Plan
EOF
cat > "$TMPDIR_TEST/sprints/${SID}.task_graph.json" <<JSON
{
  "sprint_id": "${SID}",
  "required_gates": ["G0", "G1", "G2"],
  "nodes": [
    {
      "id": "S0",
      "goal": "foundation",
      "depends_on": [],
      "write_scope": ["/foundation"],
      "read_scope": ["/"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "gate": "G0",
      "acceptance": ["foundation passed"],
      "estimated_cost": 1,
      "status": "passed"
    },
    {
      "id": "S1",
      "goal": "parallel one",
      "depends_on": ["S0"],
      "write_scope": ["/a"],
      "read_scope": ["/"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "gate": "G1",
      "acceptance": ["S1 passed"],
      "estimated_cost": 1
    },
    {
      "id": "S2",
      "goal": "parallel two",
      "depends_on": ["S0"],
      "write_scope": ["/b"],
      "read_scope": ["/"],
      "required_skills": ["python"],
      "preferred_model": "glm-5.1",
      "gate": "G2",
      "acceptance": ["S2 passed"],
      "estimated_cost": 1
    },
    {
      "id": "S3",
      "goal": "join node",
      "depends_on": ["S1", "S2"],
      "write_scope": ["/c"],
      "read_scope": ["/"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "gate": "G3",
      "acceptance": ["S3 passed"],
      "estimated_cost": 1
    }
  ],
  "node_results": {
    "S0": {"status": "passed", "updated_at": "2026-05-09T00:00:00Z"}
  },
  "gate_results": {
    "G0": {"status": "passed", "node": "S0", "updated_at": "2026-05-09T00:00:00Z"}
  }
}
JSON

echo "T1: planner contract requires task_graph"
grep -q "task_graph.json" "$HARNESS_DIR_REAL/personas/planner.md" && ok "planner persona mentions task_graph" || fail "planner persona missing task_graph"
grep -q "graph-scheduler validate" "$HARNESS_DIR_REAL/templates/contract-template-v2.md" && ok "contract-template-v2 validates graph" || fail "contract-template-v2 missing graph validate"
grep -q "task_graph.json" "$HARNESS_DIR_REAL/templates/sprint-contract.md" && ok "sprint-contract mentions task_graph" || fail "sprint-contract missing task_graph"

echo "T2: autopilot apply enqueues only ready DAG nodes"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --apply --json --cooldown 0 2>/dev/null)
check "autopilot detects graph_ready_nodes" "$OUT" '"action": "graph_ready_nodes"'
check "autopilot enqueue result ok" "$OUT" '"ok": true'
QUEUE_FILE="$TMPDIR_TEST/run/queue/${SID}.jsonl"
[[ -s "$QUEUE_FILE" ]] && ok "task queue created" || fail "task queue missing"
QUEUE_TEXT=$(cat "$QUEUE_FILE")
check "S1 queued" "$QUEUE_TEXT" 'graph_node|node_id=S1'
check "S2 queued" "$QUEUE_TEXT" 'graph_node|node_id=S2'
if [[ "$QUEUE_TEXT" != *'graph_node|node_id=S3'* ]]; then ok "S3 not queued before join"; else fail "S3 queued too early"; fi

echo "T3: graph in-place marks assigned nodes not ready"
GRAPH_TEXT=$(cat "$TMPDIR_TEST/sprints/${SID}.task_graph.json")
check "S1 status assigned" "$GRAPH_TEXT" '"status": "assigned"'
check "S2 status assigned" "$GRAPH_TEXT" '"status": "assigned"'

echo "T4: task_graph sprint does not use legacy parent evaluator route"
cat > "$TMPDIR_TEST/sprints/${SID}.handoff.md" <<'EOF'
# Legacy sprint handoff should not trigger parent eval while DAG nodes are open.
EOF
python3 - "$TMPDIR_TEST/sprints/${SID}.status.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["handoff_to"] = "evaluator"
json.dump(d, open(p, "w"), indent=2)
PY
OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --json --cooldown 0 2>/dev/null)
if [[ "$OUT" != *'"ready_for_evaluator"'* ]]; then ok "task_graph blocks legacy parent evaluator"; else fail "task_graph leaked legacy parent evaluator route"; fi

echo "T5: missing task_graph does not fall back to builder dispatch"
SID2="sprint-test-missing-graph"
cat > "$TMPDIR_TEST/sprints/${SID2}.status.json" <<JSON
{
  "sprint_id": "${SID2}",
  "status": "active",
  "phase": "planning_complete",
  "handoff_to": "builder_parallel",
  "priority": "P0",
  "history": []
}
JSON
cat > "$TMPDIR_TEST/sprints/${SID2}.contract.md" <<'EOF'
# Contract
EOF
cat > "$TMPDIR_TEST/sprints/${SID2}.plan.md" <<'EOF'
# Plan
EOF
OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --apply --json --cooldown 0 2>/dev/null)
check "missing graph reported" "$OUT" '"action": "missing_task_graph"'
if [[ ! -f "$TMPDIR_TEST/run/queue/${SID2}.jsonl" ]]; then ok "missing graph not queued to builder"; else fail "missing graph got builder queue"; fi

echo ""
echo "=== DAG Autopilot Planner: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
