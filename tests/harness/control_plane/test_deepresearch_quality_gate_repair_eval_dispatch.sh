#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST/lib" "$TMPDIR_TEST/sprints" "$TMPDIR_TEST/state" "$TMPDIR_TEST/run"
cp "$HARNESS_DIR_REAL/lib/graph_node_dispatcher.py" "$TMPDIR_TEST/lib/graph_node_dispatcher.py"
cp "$HARNESS_DIR_REAL/lib/graph_scheduler.py" "$TMPDIR_TEST/lib/graph_scheduler.py"
cp "$HARNESS_DIR_REAL/lib/task_queue.py" "$TMPDIR_TEST/lib/task_queue.py"
cp "$HARNESS_DIR_REAL/lib/pane_lease.py" "$TMPDIR_TEST/lib/pane_lease.py"

SID="sprint-test-deepresearch-repair-eval"
GRAPH="$TMPDIR_TEST/sprints/$SID.task_graph.json"
cat > "$GRAPH" <<JSON
{
  "sprint_id": "$SID",
  "nodes": [
    {
      "id": "N1",
      "goal": "DeepResearch historical node needs factuality gate repair",
      "status": "reviewing",
      "required_capabilities": ["research.factuality_evaluator"],
      "quality_gate_repair_requested_at": "2026-05-14T00:00:00Z",
      "quality_gate_repair_reason": "missing"
    }
  ],
  "node_results": {
    "N1": {
      "status": "reviewing",
      "gate_status": "reviewing"
    }
  }
}
JSON

cat > "$TMPDIR_TEST/sprints/$SID.N1-eval.json" <<'JSON'
{"verdict": "PASS", "stale": true}
JSON

OUT="$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" python3 "$TMPDIR_TEST/lib/graph_node_dispatcher.py" dispatch-evals --graph "$GRAPH" --dry-run --max-items 1)"
python3 - "$OUT" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
items = payload.get("dispatched") or []
if len(items) != 1:
    raise SystemExit(f"repair eval dispatch was skipped: {payload}")
item = items[0]
if item.get("node") != "N1" or not item.get("dry_run"):
    raise SystemExit(f"bad dispatch item: {item}")
print(json.dumps({"ok": True, "feature": "deepresearch_repair_eval_dispatch"}, ensure_ascii=False))
PY

echo "PASS: DeepResearch quality gate repair nodes dispatch evaluator despite stale eval json or missing handoff"
