#!/usr/bin/env bash
# Graph Scheduler test suite — machine-executable DAG planning for Solar Harness
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
LIB="$HARNESS_DIR/lib"
BIN="$HARNESS_DIR/solar-harness.sh"
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

GRAPH="$TMPDIR_TEST/product-platform.task_graph.json"
WORKERS="$TMPDIR_TEST/workers.json"
CONFLICT="$TMPDIR_TEST/conflict.task_graph.json"
CYCLE="$TMPDIR_TEST/cycle.task_graph.json"
BATCHES="$TMPDIR_TEST/dispatch_batches.json"
ENQ_GRAPH="$TMPDIR_TEST/enqueue.task_graph.json"
CAP_GRAPH="$TMPDIR_TEST/capability.task_graph.json"
CAP_WORKERS="$TMPDIR_TEST/capability-workers.json"
INFER_GRAPH="$TMPDIR_TEST/infer-capability.task_graph.json"
INFER_SOURCE="$TMPDIR_TEST/infer-capability.contract.md"
PREREQ_GRAPH="$TMPDIR_TEST/prereq.task_graph.json"
BACKLOG_DIR="$TMPDIR_TEST/backlog-sprints"

cat > "$GRAPH" <<'JSON'
{
  "sprint_id": "sprint-test-dag",
  "required_gates": ["G0", "G1", "G2", "G3", "G4", "G5", "G6"],
  "nodes": [
    {
      "id": "S0",
      "goal": "snapshot foundation",
      "depends_on": [],
      "write_scope": ["/lib/product_snapshot.py", "/tests/snapshot"],
      "read_scope": ["~/.solar/harness"],
      "required_skills": ["bash", "python"],
      "preferred_model": "sonnet",
      "gate": "G0",
      "acceptance": ["snapshot roundtrip"],
      "estimated_cost": 1,
      "status": "passed"
    },
    {
      "id": "S1",
      "goal": "installer and container validation",
      "depends_on": ["S0"],
      "write_scope": ["/installer", "/tests/installer"],
      "required_skills": ["bash"],
      "preferred_model": "glm-5.1",
      "gate": "G1",
      "acceptance": ["install smoke"],
      "estimated_cost": 3
    },
    {
      "id": "S2",
      "goal": "skill lifecycle",
      "depends_on": ["S0"],
      "write_scope": ["/skills", "/tests/skills"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "gate": "G2",
      "acceptance": ["skill package test"],
      "estimated_cost": 2
    },
    {
      "id": "S6",
      "goal": "control plane",
      "depends_on": ["S0"],
      "write_scope": ["/lib/solar_state_db.py", "/lib/task_queue.py", "/lib/pane_lease.py"],
      "required_skills": ["python"],
      "preferred_model": "deepseek",
      "gate": "G6",
      "acceptance": ["queue and lease test"],
      "estimated_cost": 2
    },
    {
      "id": "S3",
      "goal": "data plane",
      "depends_on": ["S1", "S2", "S6"],
      "write_scope": ["/lib/data_plane"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "gate": "G3",
      "acceptance": ["data plane smoke"],
      "estimated_cost": 4
    },
    {
      "id": "S4",
      "goal": "extension framework",
      "depends_on": ["S3"],
      "write_scope": ["/integrations"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "gate": "G4",
      "acceptance": ["plugin contract"],
      "estimated_cost": 2
    },
    {
      "id": "S5",
      "goal": "self evolution",
      "depends_on": ["S3"],
      "write_scope": ["/evals", "/reports"],
      "required_skills": ["python"],
      "preferred_model": "deepseek",
      "gate": "G5",
      "acceptance": ["eval baseline"],
      "estimated_cost": 2
    },
    {
      "id": "S7",
      "goal": "release closeout",
      "depends_on": ["S4", "S5"],
      "write_scope": ["/release"],
      "required_skills": ["bash"],
      "preferred_model": "sonnet",
      "acceptance": ["release check"],
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

cat > "$WORKERS" <<'JSON'
{
  "workers": [
    {"pane": "solar-harness:0.0", "models": ["glm-5.1"], "skills": ["bash", "python"], "quota_exhausted": ["glm-5.1"]},
    {"pane": "solar-harness:0.1", "models": ["sonnet"], "skills": ["bash", "python"]},
    {"pane": "solar-harness:0.2", "models": ["deepseek"], "skills": ["python"]},
    {"pane": "solar-harness:0.3", "models": ["sonnet"], "skills": ["bash"], "busy": true}
  ]
}
JSON

cat > "$CAP_GRAPH" <<'JSON'
{
  "sprint_id": "sprint-capability",
  "nodes": [
    {
      "id": "R1",
      "goal": "Ruflo swarm orchestration",
      "depends_on": [],
      "write_scope": ["/reports/ruflo"],
      "required_skills": ["python"],
      "required_capabilities": ["ruflo.swarm"],
      "preferred_model": "sonnet",
      "acceptance": ["runtime-aware worker chosen"]
    }
  ]
}
JSON

cat > "$CAP_WORKERS" <<'JSON'
{
  "workers": [
    {"pane": "solar-harness:0.1", "models": ["sonnet"], "skills": ["python"], "provider": "generic", "capabilities": ["ruflo.swarm"], "capability_score": 1},
    {"pane": "solar-harness:0.2", "models": ["sonnet"], "skills": ["python"], "provider": "ruflo", "capabilities": ["ruflo.swarm", "ruflo.plugins", "ruflo.agent_catalog", "ruflo.memory", "ruflo.mcp", "ruflo.workflow_templates"], "capability_score": 9}
  ]
}
JSON

cat > "$INFER_GRAPH" <<'JSON'
{
  "sprint_id": "sprint-infer-capability",
  "nodes": [
    {
      "id": "R1",
      "goal": "Use Ruflo Claude Flow swarm orchestration to verify MCP workflow templates",
      "depends_on": [],
      "write_scope": ["/reports/ruflo-infer"],
      "read_scope": ["~/.solar/harness/vendor/ruflo"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "acceptance": ["required_capabilities inferred before assignment"],
      "estimated_cost": 1
    }
  ]
}
JSON

cat > "$INFER_SOURCE" <<'MD'
# Contract
需要使用 Ruflo / Claude Flow 的 swarm、MCP 和 workflow templates 能力，不能只按普通 Python 任务派发。
MD

cat > "$PREREQ_GRAPH" <<'JSON'
{
  "sprint_id": "sprint-prereq",
  "prerequisites": ["sprint-upstream:passed"],
  "dependency_policy": {
    "blocks_until": ["sprint-upstream:passed"]
  },
  "nodes": [
    {
      "id": "P1",
      "goal": "must wait for upstream",
      "depends_on": [],
      "write_scope": ["/tmp/prereq"],
      "required_skills": ["python"],
      "acceptance": ["blocked until upstream passed"]
    }
  ]
}
JSON

mkdir -p "$BACKLOG_DIR"
cp "$INFER_GRAPH" "$BACKLOG_DIR/sprint-backlog.task_graph.json"
cp "$INFER_SOURCE" "$BACKLOG_DIR/sprint-backlog.contract.md"

cat > "$CONFLICT" <<'JSON'
{
  "sprint_id": "sprint-conflict",
  "nodes": [
    {"id": "A", "goal": "A", "depends_on": [], "write_scope": ["/lib"], "acceptance": ["ok"]},
    {"id": "B", "goal": "B", "depends_on": [], "write_scope": ["/lib/foo.py"], "acceptance": ["ok"]},
    {"id": "C", "goal": "C", "depends_on": [], "acceptance": ["ok"]}
  ]
}
JSON

cat > "$CYCLE" <<'JSON'
{
  "sprint_id": "sprint-cycle",
  "nodes": [
    {"id": "A", "goal": "A", "depends_on": ["B"], "write_scope": ["/a"], "acceptance": ["ok"]},
    {"id": "B", "goal": "B", "depends_on": ["A"], "write_scope": ["/b"], "acceptance": ["ok"]}
  ]
}
JSON

echo "T1: py_compile"
python3 -m py_compile "$LIB/graph_scheduler.py" 2>&1 && ok "graph_scheduler.py compiles" || fail "compile error"
python3 -m py_compile "$LIB/capability_inference.py" 2>&1 && ok "capability_inference.py compiles" || fail "capability_inference.py compile error"
python3 -c "import json; s=json.load(open('$HARNESS_DIR/schemas/task-graph.schema.json')); assert s.get('title') == 'Solar Harness TaskGraph'; print('ok')" >/dev/null \
  && ok "task-graph.schema.json valid" || fail "task-graph.schema.json invalid"

echo "T2: validate + topo + critical path"
OUT=$(python3 "$LIB/graph_scheduler.py" validate --graph "$GRAPH" 2>/dev/null)
check "validate ok" "$OUT" '"ok": true'
check "validate node_count" "$OUT" '"node_count": 8'
OUT=$(python3 "$LIB/graph_scheduler.py" topo --graph "$GRAPH" 2>/dev/null)
check "topo starts S0" "$OUT" '"S0"'
OUT=$(python3 "$LIB/graph_scheduler.py" critical-path --graph "$GRAPH" 2>/dev/null)
check "critical path includes S3" "$OUT" '"S3"'

echo "T3: cycle detection"
set +e
OUT=$(python3 "$LIB/graph_scheduler.py" validate --graph "$CYCLE" 2>/dev/null)
RC=$?
set -e
if [[ "$OUT" == *'"ok": false'* && $RC -eq 0 ]]; then ok "cycle detected as validation error"; else fail "cycle validation failed (rc=$RC out=$OUT)"; fi

echo "T4: ready nodes and join gate"
OUT=$(python3 "$LIB/graph_scheduler.py" ready --graph "$GRAPH" 2>/dev/null)
check "S1 ready" "$OUT" '"S1"'
check "S2 ready" "$OUT" '"S2"'
check "S6 ready" "$OUT" '"S6"'
if [[ "$OUT" != *'"S3"'* ]]; then ok "S3 blocked until S1/S2/S6 pass"; else fail "S3 dispatched too early"; fi
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$LIB/graph_scheduler.py" ready --graph "$PREREQ_GRAPH" 2>/dev/null)
if [[ "$OUT" == *'"nodes": []'* && "$OUT" == *'"blocked_prerequisites"'* ]]; then ok "external prerequisite blocks ready nodes"; else fail "external prerequisite failed to block ready nodes (out=$OUT)"; fi
mkdir -p "$TMPDIR_TEST/sprints"
printf '{"status":"passed","phase":"eval_passed"}\n' > "$TMPDIR_TEST/sprints/sprint-upstream.status.json"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$LIB/graph_scheduler.py" ready --graph "$PREREQ_GRAPH" 2>/dev/null)
check "external prerequisite pass releases ready node" "$OUT" '"P1"'
python3 - <<PY
import json
from pathlib import Path
p = Path("$PREREQ_GRAPH")
g = json.loads(p.read_text())
g["prerequisites"] = [{"sprint_id": "sprint-upstream", "required_status": "planning_complete"}]
g["dependency_policy"] = {"blocks_until": [{"sprint_id": "sprint-upstream", "required_status": "planning_complete"}]}
p.write_text(json.dumps(g))
PY
printf '{"status":"passed","phase":"finalized"}\n' > "$TMPDIR_TEST/sprints/sprint-upstream.status.json"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$LIB/graph_scheduler.py" ready --graph "$PREREQ_GRAPH" 2>/dev/null)
check "terminal upstream satisfies earlier planning_complete prerequisite" "$OUT" '"P1"'

echo "T5: write_scope conflict split"
OUT=$(python3 "$LIB/graph_scheduler.py" batches --graph "$CONFLICT" --max-parallel 8 2>/dev/null)
check "conflict batches ok" "$OUT" '"ok": true'
check "conflict split into 3 batches" "$OUT" '"batch_count": 3'

echo "T6: batches output file"
OUT=$(python3 "$LIB/graph_scheduler.py" batches --graph "$GRAPH" --max-parallel 8 --out "$BATCHES" 2>/dev/null)
[[ -s "$BATCHES" ]] && ok "dispatch_batches.json written" || fail "dispatch_batches.json missing"
check "first batch has three nodes" "$OUT" '"nodes": ["S1", "S2", "S6"]'

echo "T7: worker matching with GLM quota fallback"
OUT=$(python3 "$LIB/graph_scheduler.py" assign --graph "$GRAPH" --workers "$WORKERS" --max-parallel 8 2>/dev/null)
check "assign ok" "$OUT" '"ok": true'
check "S1 assigned despite GLM exhausted" "$OUT" '"node": "S1"'
check "fallback model recorded" "$OUT" '"fallback_model": true'
check "S6 assigned deepseek" "$OUT" '"node": "S6"'

echo "T8: parent_ready_check blocks premature parent pass"
OUT=$(python3 "$LIB/graph_scheduler.py" parent-check --graph "$GRAPH" 2>/dev/null)
check "parent not ready" "$OUT" '"ready": false'
check "open nodes present" "$OUT" '"open_nodes"'

echo "T9: runtime-aware capability worker ranking"
OUT=$(python3 "$LIB/graph_scheduler.py" assign --graph "$CAP_GRAPH" --workers "$CAP_WORKERS" --max-parallel 2 2>/dev/null)
check "capability assign ok" "$OUT" '"ok": true'
check "Ruflo worker selected" "$OUT" '"pane": "solar-harness:0.2"'
check "capability score emitted" "$OUT" '"capability_score"'

echo "T10: capability enrichment from contract/node text"
OUT=$(python3 "$LIB/graph_scheduler.py" enrich-capabilities --graph "$INFER_GRAPH" --source "$INFER_SOURCE" --in-place 2>/dev/null)
check "enrich-capabilities ok" "$OUT" '"ok": true'
check "enrich changed R1" "$OUT" '"R1"'
OUT=$(python3 -c "import json; g=json.load(open('$INFER_GRAPH')); print(json.dumps(g['nodes'][0], ensure_ascii=False))")
check "Ruflo swarm inferred" "$OUT" '"ruflo.swarm"'
check "Ruflo MCP inferred" "$OUT" '"ruflo.mcp"'
OUT=$(python3 "$LIB/graph_scheduler.py" assign --graph "$INFER_GRAPH" --workers "$CAP_WORKERS" --max-parallel 2 2>/dev/null)
check "inferred capability selects Ruflo worker" "$OUT" '"pane": "solar-harness:0.2"'

echo "T11: backlog enrichment migrates existing graphs"
OUT=$(python3 "$LIB/graph_scheduler.py" enrich-backlog --sprints-dir "$BACKLOG_DIR" 2>/dev/null)
check "enrich-backlog ok" "$OUT" '"ok": true'
check "enrich-backlog changed one graph" "$OUT" '"changed_count": 1'
OUT=$(python3 -c "import json; g=json.load(open('$BACKLOG_DIR/sprint-backlog.task_graph.json')); print(json.dumps(g['nodes'][0], ensure_ascii=False))")
check "backlog graph has Ruflo capability" "$OUT" '"ruflo.swarm"'
OUT=$(python3 "$LIB/graph_scheduler.py" enrich-backlog --sprints-dir "$BACKLOG_DIR" --dry-run 2>/dev/null)
check "enrich-backlog idempotent" "$OUT" '"changed_count": 0'

echo "T12: enqueue-ready writes graph node payloads only for ready batch"
cp "$GRAPH" "$ENQ_GRAPH"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$LIB/graph_scheduler.py" enqueue-ready --graph "$ENQ_GRAPH" --workers "$WORKERS" --max-parallel 8 --in-place 2>/dev/null)
check "enqueue-ready ok" "$OUT" '"ok": true'
check "enqueue-ready S1" "$OUT" '"node": "S1"'
check "enqueue-ready S2" "$OUT" '"node": "S2"'
check "enqueue-ready S6" "$OUT" '"node": "S6"'
if [[ "$OUT" != *'"node": "S3"'* ]]; then ok "enqueue-ready did not enqueue blocked S3"; else fail "blocked S3 was enqueued"; fi
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$LIB/task_queue.py" depth --sprint sprint-test-dag 2>/dev/null)
check "queue depth 3" "$OUT" '"depth": 3'
OUT=$(python3 "$LIB/graph_scheduler.py" ready --graph "$ENQ_GRAPH" 2>/dev/null)
if [[ "$OUT" != *'"S1"'* && "$OUT" != *'"S2"'* && "$OUT" != *'"S6"'* ]]; then ok "in-place dispatched nodes no longer ready"; else fail "dispatched nodes still ready"; fi

echo "T13: mark results and release next layer"
for n in S1 S2 S6; do
  python3 "$LIB/graph_scheduler.py" mark --graph "$GRAPH" --node "$n" --status passed --in-place >/dev/null
done
OUT=$(python3 "$LIB/graph_scheduler.py" ready --graph "$GRAPH" 2>/dev/null)
check "S3 ready after join" "$OUT" '"S3"'
if [[ "$OUT" != *'"S4"'* ]]; then ok "S4 still blocked"; else fail "S4 dispatched too early"; fi

echo "T14: failure blocks descendants only"
python3 "$LIB/graph_scheduler.py" mark --graph "$GRAPH" --node S3 --status failed --in-place >/dev/null
OUT=$(python3 "$LIB/graph_scheduler.py" ready --graph "$GRAPH" 2>/dev/null)
if [[ "$OUT" != *'"S4"'* && "$OUT" != *'"S5"'* && "$OUT" != *'"S7"'* ]]; then ok "S3 failure blocks S4/S5/S7"; else fail "failure did not block descendants"; fi

echo "T15: queue can store graph node payload"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$LIB/task_queue.py" enqueue-node --sprint sprint-test-dag --node-id S1 --payload '{"node_id":"S1","goal":"installer"}' 2>/dev/null)
check "enqueue-node ok" "$OUT" '"ok": true'
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$LIB/task_queue.py" pop --sprint sprint-test-dag 2>/dev/null)
check "pop graph node intent" "$OUT" 'graph_node|node_id=S1'
check "pop graph node payload" "$OUT" '"payload"'

echo "T16: solar-harness subcommand routing"
OUT=$(bash "$BIN" graph-scheduler help 2>/dev/null || true)
check "graph-scheduler help" "$OUT" "Solar Graph Scheduler"
check "graph-scheduler help has enrichment" "$OUT" "enrich-capabilities"
OUT=$(bash "$BIN" graph-scheduler validate --graph "$CONFLICT" 2>/dev/null || true)
check "graph-scheduler validate route" "$OUT" '"ok": true'
OUT=$(bash "$BIN" graph-scheduler enrich-capabilities --graph "$INFER_GRAPH" --source "$INFER_SOURCE" 2>/dev/null || true)
check "graph-scheduler enrich route" "$OUT" '"ok": true'
OUT=$(bash "$BIN" graph-scheduler enrich-backlog --sprints-dir "$BACKLOG_DIR" --dry-run 2>/dev/null || true)
check "graph-scheduler enrich-backlog route" "$OUT" '"ok": true'

echo ""
echo "=== Graph Scheduler: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
