#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST/lib" "$TMPDIR_TEST/sprints" "$TMPDIR_TEST/run" "$TMPDIR_TEST/events"
cp "$HARNESS_DIR_REAL/lib/evolution_engine.py" "$TMPDIR_TEST/lib/evolution_engine.py"
cp "$HARNESS_DIR_REAL/lib/capability_registry.py" "$TMPDIR_TEST/lib/capability_registry.py"
cp "$HARNESS_DIR_REAL/lib/failure_miner.py" "$TMPDIR_TEST/lib/failure_miner.py"
cp "$HARNESS_DIR_REAL/lib/eval_runner.py" "$TMPDIR_TEST/lib/eval_runner.py"

SID="sprint-test-dr-debt"
GRAPH="$TMPDIR_TEST/sprints/$SID.task_graph.json"
cat > "$GRAPH" <<JSON
{
  "sprint_id": "$SID",
  "nodes": [
    {
      "id": "R8",
      "goal": "DeepResearch factuality gate",
      "status": "passed",
      "required_capabilities": ["research.factuality_evaluator"],
      "research_quality_gate": {
        "ok": false,
        "verdict": "FAIL",
        "reason": "old evaluator skipped artifacts"
      },
      "eval_assigned_to": "pane-test",
      "eval_dispatch_id": "dispatch-old",
      "eval_dispatched_at": "2026-05-14T00:00:00Z"
    },
    {
      "id": "R9",
      "goal": "Regular engineering node",
      "status": "passed",
      "required_capabilities": ["python.edit"]
    }
  ],
  "node_results": {
    "R8": {
      "status": "passed",
      "gate_status": "passed",
      "research_quality_gate": {"ok": false}
    },
    "R9": {
      "status": "passed",
      "gate_status": "passed"
    }
  }
}
JSON

BEFORE_SHA="$(shasum -a 256 "$GRAPH" | awk '{print $1}')"
DRY_OUT="$(HARNESS_DIR="$TMPDIR_TEST" HARNESS_STATE_DB="$TMPDIR_TEST/run/state.db" python3 "$TMPDIR_TEST/lib/evolution_engine.py" repair-deepresearch-gates --json)"
AFTER_SHA="$(shasum -a 256 "$GRAPH" | awk '{print $1}')"
if [[ "$BEFORE_SHA" != "$AFTER_SHA" ]]; then
  echo "dry run mutated graph" >&2
  exit 1
fi

python3 - "$DRY_OUT" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
if payload.get("candidate_count") != 1 or payload.get("repaired_count") != 0:
    raise SystemExit(f"bad dry-run payload: {payload}")
print(json.dumps({"ok": True, "phase": "dry_run"}, ensure_ascii=False))
PY

APPLY_OUT="$(HARNESS_DIR="$TMPDIR_TEST" HARNESS_STATE_DB="$TMPDIR_TEST/run/state.db" python3 "$TMPDIR_TEST/lib/evolution_engine.py" repair-deepresearch-gates --apply --limit 1 --json)"
python3 - "$APPLY_OUT" "$GRAPH" "$TMPDIR_TEST/events/all.jsonl" "$TMPDIR_TEST/sprints/$SID.events.jsonl" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
graph = json.loads(Path(sys.argv[2]).read_text())
if payload.get("candidate_count") != 1 or payload.get("repaired_count") != 1:
    raise SystemExit(f"bad apply payload: {payload}")
nodes = {node["id"]: node for node in graph["nodes"]}
node = nodes["R8"]
if node.get("status") != "reviewing":
    raise SystemExit(f"node not reopened: {node}")
for key in ("research_quality_gate", "eval_assigned_to", "eval_dispatch_id", "eval_dispatched_at"):
    if key in node:
        raise SystemExit(f"stale field not cleared: {key} in {node}")
result = graph["node_results"]["R8"]
if result.get("status") != "reviewing" or result.get("gate_status") != "reviewing":
    raise SystemExit(f"node_results not reopened: {result}")
if graph["node_results"]["R9"].get("status") != "passed":
    raise SystemExit(f"non research node mutated: {graph['node_results']['R9']}")
for event_path in (Path(sys.argv[3]), Path(sys.argv[4])):
    text = event_path.read_text()
    if "evolution_deepresearch_quality_gate_repair_requested" not in text:
        raise SystemExit(f"missing event in {event_path}: {text}")
print(json.dumps({"ok": True, "phase": "apply"}, ensure_ascii=False))
PY

echo "PASS: evolution engine repairs historical DeepResearch quality gate debt"
