#!/usr/bin/env bash
# Graph node dispatcher regression tests — DAG queue item -> explicit node dispatch
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
BIN="$HARNESS_DIR_REAL/solar-harness.sh"
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
mkdir -p "$TMPDIR_TEST/lib" "$TMPDIR_TEST/config" "$TMPDIR_TEST/sprints" "$TMPDIR_TEST/run/queue" "$TMPDIR_TEST/run/pane-leases"

cp "$HARNESS_DIR_REAL/lib/graph_scheduler.py" "$TMPDIR_TEST/lib/graph_scheduler.py"
cp "$HARNESS_DIR_REAL/lib/prerequisite_resolver.py" "$TMPDIR_TEST/lib/prerequisite_resolver.py"
cp "$HARNESS_DIR_REAL/lib/graph_node_dispatcher.py" "$TMPDIR_TEST/lib/graph_node_dispatcher.py"
cp "$HARNESS_DIR_REAL/lib/apo_plan_compiler.py" "$TMPDIR_TEST/lib/apo_plan_compiler.py"
cp "$HARNESS_DIR_REAL/lib/capability_capsules.py" "$TMPDIR_TEST/lib/capability_capsules.py"
cp "$HARNESS_DIR_REAL/lib/task_queue.py" "$TMPDIR_TEST/lib/task_queue.py"
cp "$HARNESS_DIR_REAL/lib/pane_lease.py" "$TMPDIR_TEST/lib/pane_lease.py"
cp "$HARNESS_DIR_REAL/lib/solar_skills.py" "$TMPDIR_TEST/lib/solar_skills.py"
cp "$HARNESS_DIR_REAL/lib/capability_effects.py" "$TMPDIR_TEST/lib/capability_effects.py"
cp "$HARNESS_DIR_REAL/lib/resource_telemetry.py" "$TMPDIR_TEST/lib/resource_telemetry.py"
cp "$HARNESS_DIR_REAL/lib/solar_db.py" "$TMPDIR_TEST/lib/solar_db.py"
cp "$HARNESS_DIR_REAL/lib/model_registry.py" "$TMPDIR_TEST/lib/model_registry.py"
cp "$HARNESS_DIR_REAL/lib/run-state.sh" "$TMPDIR_TEST/lib/run-state.sh"
cp "$HARNESS_DIR_REAL/config/model-registry.json" "$TMPDIR_TEST/config/model-registry.json"
cp "$HARNESS_DIR_REAL/config/solar-user-config.json" "$TMPDIR_TEST/config/solar-user-config.json"

SID="sprint-test-graph-node-dispatch"
GRAPH="$TMPDIR_TEST/sprints/${SID}.task_graph.json"
cat > "$TMPDIR_TEST/sprints/${SID}.contract.md" <<'EOF'
# Contract
EOF
cat > "$GRAPH" <<JSON
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
      "goal": "implement node S1 only; run browser QA on localhost, debug failures, convert PDF to markdown, and use specialist persona when useful",
      "depends_on": ["S0"],
      "write_scope": ["/a"],
      "read_scope": ["/"],
      "required_skills": ["python", "browser.browse", "document.convert", "persona.agent"],
      "required_capabilities": ["browser.browse", "document.convert", "persona.agent"],
      "preferred_model": "sonnet",
      "gate": "G1",
      "acceptance": ["S1 passed"],
      "estimated_cost": 1
    },
    {
      "id": "S2",
      "goal": "implement node S2 only",
      "depends_on": ["S0"],
      "write_scope": ["/b"],
      "read_scope": ["/"],
      "required_skills": ["python"],
      "preferred_model": "sonnet",
      "gate": "G2",
      "acceptance": ["S2 passed"],
      "estimated_cost": 1
    },
    {
      "id": "S3",
      "goal": "join after S1/S2",
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

echo "T1: py_compile"
python3 -m py_compile "$TMPDIR_TEST/lib/graph_node_dispatcher.py" "$TMPDIR_TEST/lib/graph_scheduler.py" "$TMPDIR_TEST/lib/task_queue.py" "$TMPDIR_TEST/lib/model_registry.py" \
  && ok "modules compile" || fail "compile failed"

echo "T1b: dispatcher reads model registry for worker capability"
MODELS_JSON=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" python3 - <<'PY'
import json
import os
import sys
sys.path.insert(0, os.path.join(os.environ["HARNESS_DIR"], "lib"))
import graph_node_dispatcher as g
print(json.dumps({
    "main_builder": g._models_for_pane("solar-harness-test:0.2"),
    "lab4": g._models_for_pane("solar-harness-test-lab:0.3"),
}, ensure_ascii=False))
PY
)
check "main builder model aliases include configured Opus" "$MODELS_JSON" "claude-opus"
check "lab4 model aliases include explicit Anthropic Sonnet" "$MODELS_JSON" "anthropic-sonnet"

echo "T2: dispatch-ready dry-run creates explicit node dispatch files"
if ! OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_GRAPH_DISPATCH_FAKE_WORKERS=1 python3 "$TMPDIR_TEST/lib/graph_node_dispatcher.py" dispatch-ready --graph "$GRAPH" --dry-run 2>&1); then
  echo "$OUT"
  exit 1
fi
check "dispatch-ready ok" "$OUT" '"ok": true'
check "S1 drained" "$OUT" '"node": "S1"'
check "S2 drained" "$OUT" '"node": "S2"'
if [[ "$OUT" != *'"node": "S3"'* ]]; then ok "S3 not dispatched before join"; else fail "S3 dispatched too early"; fi

S1_DISPATCH="$TMPDIR_TEST/sprints/${SID}.S1-dispatch.md"
S2_DISPATCH="$TMPDIR_TEST/sprints/${SID}.S2-dispatch.md"
[[ -s "$S1_DISPATCH" ]] && ok "S1 dispatch file exists" || fail "S1 dispatch file missing"
[[ -s "$S2_DISPATCH" ]] && ok "S2 dispatch file exists" || fail "S2 dispatch file missing"
S1_TEXT=$(cat "$S1_DISPATCH")
check "dispatch text has node id" "$S1_TEXT" "Node: \`S1\`"
check "dispatch text has write scope" "$S1_TEXT" "\`/a\`"
check "dispatch text has required capabilities section" "$S1_TEXT" "## Required Capabilities"
check "dispatch text lists browser capability" "$S1_TEXT" "\`browser.browse\`"
check "dispatch text forbids parent pass" "$S1_TEXT" "不要把 parent sprint 标成 passed"
check "dispatch text lists document capability" "$S1_TEXT" "\`document.convert\`"
check "dispatch text lists persona capability" "$S1_TEXT" "\`persona.agent\`"

echo "T3: dry-run does not enqueue or mutate graph status"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$TMPDIR_TEST/lib/task_queue.py" depth --sprint "$SID" 2>/dev/null)
check "queue empty" "$OUT" '"depth": 0'
GRAPH_TEXT=$(cat "$GRAPH")
if [[ "$GRAPH_TEXT" != *'"assigned_to"'* ]]; then ok "dry-run did not assign panes"; else fail "dry-run wrote assigned_to into graph"; fi
if [[ "$GRAPH_TEXT" != *'"status": "dispatched"'* ]]; then ok "dry-run did not mark dispatched"; else fail "dry-run marked graph dispatched"; fi
if [[ "$GRAPH_TEXT" != *'"id": "S3"'*'"status": "dispatched"'* ]]; then ok "S3 not marked dispatched"; else fail "S3 marked dispatched too early"; fi

echo "T4: drain-queue dry-run consumes pre-enqueued graph node payload"
SID2="sprint-test-graph-node-drain"
GRAPH2="$TMPDIR_TEST/sprints/${SID2}.task_graph.json"
cp "$GRAPH" "$GRAPH2"
python3 - "$GRAPH2" "$SID2" <<'PY'
import json, sys
p, sid = sys.argv[1], sys.argv[2]
d = json.load(open(p))
d["sprint_id"] = sid
for n in d["nodes"]:
    n.pop("status", None)
    n.pop("assigned_to", None)
    n.pop("dispatch_id", None)
d["nodes"][0]["status"] = "passed"
d["node_results"] = {"S0": {"status": "passed", "updated_at": "2026-05-09T00:00:00Z"}}
json.dump(d, open(p, "w"), indent=2)
PY
PAYLOAD=$(python3 - "$GRAPH2" "$SID2" <<'PY'
import json, sys
graph, sid = sys.argv[1], sys.argv[2]
d = json.load(open(graph))
node = next(n for n in d["nodes"] if n["id"] == "S1")
print(json.dumps({
    "type": "graph_node",
    "graph": graph,
    "sprint_id": sid,
    "node": node,
    "assignment": {"node": "S1", "pane": "solar-harness-test:0.2"},
    "dispatch_id": "graph-test-drain-S1"
}))
PY
)
HARNESS_DIR="$TMPDIR_TEST" python3 "$TMPDIR_TEST/lib/task_queue.py" enqueue-node --sprint "$SID2" --node-id S1 --payload "$PAYLOAD" >/dev/null
OUT=$(HARNESS_DIR="$TMPDIR_TEST" python3 "$TMPDIR_TEST/lib/graph_node_dispatcher.py" drain-queue --sprint "$SID2" --dry-run 2>/dev/null)
check "drain-queue ok" "$OUT" '"ok": true'
check "drain-queue S1" "$OUT" '"node": "S1"'
[[ -s "$TMPDIR_TEST/sprints/${SID2}.S1-dispatch.md" ]] && ok "drain dispatch file exists" || fail "drain dispatch file missing"

echo "T5: node-level evaluator dispatch and downstream release"
python3 - "$GRAPH" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
for n in d["nodes"]:
    if n["id"] == "S1":
        n["status"] = "reviewing"
json.dump(d, open(p, "w"), indent=2)
PY
cat > "$TMPDIR_TEST/sprints/${SID}.S1-handoff.md" <<'EOF'
# Handoff S1

## Capability / KB Usage Evidence

- Used Browser-use MCP for localhost browser QA.
- Used MarkItDown document.convert evidence for PDF conversion.
EOF
if ! OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_GRAPH_DISPATCH_FAKE_EVALUATORS=1 python3 "$TMPDIR_TEST/lib/graph_node_dispatcher.py" dispatch-evals --graph "$GRAPH" --dry-run 2>&1); then
  echo "$OUT"
  exit 1
fi
check "dispatch-evals ok" "$OUT" '"ok": true'
check "S1 eval dispatched" "$OUT" '"node": "S1"'
S1_EVAL_DISPATCH="$TMPDIR_TEST/sprints/${SID}.S1-eval-dispatch-q1.md"
[[ -s "$S1_EVAL_DISPATCH" ]] && ok "S1 eval dispatch file exists" || fail "S1 eval dispatch file missing"
S1_EVAL_TEXT=$(cat "$S1_EVAL_DISPATCH")
check "eval text node only" "$S1_EVAL_TEXT" "只评审本 DAG node"
check "eval text forbids parent pass" "$S1_EVAL_TEXT" "不要把 parent sprint 标成 passed"
check "eval text has required capabilities section" "$S1_EVAL_TEXT" "## Required Capabilities"
check "eval text lists browser capability" "$S1_EVAL_TEXT" "\`browser.browse\`"
check "eval text lists document capability" "$S1_EVAL_TEXT" "\`document.convert\`"
cat > "$TMPDIR_TEST/sprints/${SID}.S1-eval.json" <<'EOF'
{"verdict":"PASS","status":"passed","summary":"fixture evaluator pass with worker evidence"}
EOF
OUT=$(HARNESS_DIR="$TMPDIR_TEST" PYTHONPATH="$TMPDIR_TEST/lib" SOLAR_HARNESS_SESSION="solar-harness-test" python3 - <<'PY'
import graph_node_dispatcher as g

g._pane_exists = lambda pane: pane in {
    "solar-harness-test:0.1",
    "solar-harness-test:0.3",
    "solar-harness-test-lab:0.3",
}
g._pane_title = lambda pane: {
    "solar-harness-test:0.1": "Planner",
    "solar-harness-test:0.3": "Evaluator",
    "solar-harness-test-lab:0.3": "Lab Builder",
}.get(pane, "")
g.read_lease = lambda pane: {}
panes = [item["pane"] for item in g._discover_evaluators(False)]
print(",".join(panes))
PY
)
if [[ "$OUT" != *"solar-harness-test:0.1"* ]]; then ok "planner pane excluded from evaluator candidates"; else fail "planner pane included as evaluator ($OUT)"; fi
check "primary evaluator candidate retained" "$OUT" "solar-harness-test:0.3"
if ! OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_GRAPH_DISPATCH_FAKE_WORKERS=1 python3 "$TMPDIR_TEST/lib/graph_node_dispatcher.py" node-verdict --graph "$GRAPH" --node S1 --verdict pass --dry-run 2>&1); then
  echo "$OUT"
  exit 1
fi
check "S1 verdict ok" "$OUT" '"status": "passed"'
check "S1 dry-run effect reports missing sidecar" "$OUT" '"reason": "intent_sidecar_missing_or_invalid"'
if [[ "$OUT" != *'"node": "S3"'* ]]; then ok "S3 still blocked until S2 pass"; else fail "S3 released before S2 pass"; fi
cat > "$TMPDIR_TEST/sprints/${SID}.S2-handoff.md" <<'EOF'
# Handoff S2

## Summary

Fixture handoff for S2.
EOF
cat > "$TMPDIR_TEST/sprints/${SID}.S2-eval.json" <<'EOF'
{"verdict":"PASS","status":"passed","summary":"fixture evaluator pass for S2"}
EOF
if ! OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_GRAPH_DISPATCH_FAKE_WORKERS=1 python3 "$TMPDIR_TEST/lib/graph_node_dispatcher.py" node-verdict --graph "$GRAPH" --node S2 --verdict pass --dry-run 2>&1); then
  echo "$OUT"
  exit 1
fi
check "S2 verdict ok" "$OUT" '"status": "passed"'
check "S3 downstream released" "$OUT" '"node": "S3"'
[[ -s "$TMPDIR_TEST/sprints/${SID}.S3-dispatch.md" ]] && ok "S3 dispatch file exists after join" || fail "S3 dispatch missing after join"

echo "T6: failed node blocks downstream"
SID3="sprint-test-graph-node-fail"
GRAPH3="$TMPDIR_TEST/sprints/${SID3}.task_graph.json"
cp "$GRAPH2" "$GRAPH3"
python3 - "$GRAPH3" "$SID3" <<'PY'
import json, sys
p, sid = sys.argv[1], sys.argv[2]
d = json.load(open(p))
d["sprint_id"] = sid
for n in d["nodes"]:
    n.pop("status", None)
    n.pop("assigned_to", None)
    n.pop("dispatch_id", None)
    n.pop("eval_assigned_to", None)
    n.pop("eval_dispatch_id", None)
    n.pop("eval_dispatched_at", None)
d["nodes"][0]["status"] = "passed"
d["node_results"] = {"S0": {"status": "passed", "updated_at": "2026-05-09T00:00:00Z"}}
d["gate_results"] = {"G0": {"status": "passed", "node": "S0", "updated_at": "2026-05-09T00:00:00Z"}}
json.dump(d, open(p, "w"), indent=2)
PY
if ! OUT=$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" python3 "$TMPDIR_TEST/lib/graph_node_dispatcher.py" node-verdict --graph "$GRAPH3" --node S1 --verdict fail --dry-run 2>&1); then
  echo "$OUT"
  exit 1
fi
check "S1 fail verdict ok" "$OUT" '"status": "failed"'
if [[ "$OUT" != *'"node": "S3"'* ]]; then ok "failed S1 does not release S3"; else fail "failed S1 released S3"; fi

echo "T7: solar-harness graph-dispatch subcommand routing"
OUT=$(bash "$BIN" graph-dispatch help 2>/dev/null || true)
check "graph-dispatch help" "$OUT" "Solar Graph Dispatch"
check "graph-dispatch eval help" "$OUT" "dispatch-evals"
check "graph-dispatch verdict help" "$OUT" "node-verdict"
OUT=$(HARNESS_DIR="$TMPDIR_TEST" bash "$BIN" graph-dispatch drain-queue --sprint "$SID2" --dry-run 2>/dev/null || true)
check "graph-dispatch drain route" "$OUT" '"sprint_id": "sprint-test-graph-node-drain"'

echo ""
echo "=== Graph Node Dispatcher: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
