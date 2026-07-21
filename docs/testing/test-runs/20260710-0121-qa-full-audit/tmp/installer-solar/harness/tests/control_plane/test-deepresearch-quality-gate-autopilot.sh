#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST/tools" "$TMPDIR_TEST/lib" "$TMPDIR_TEST/sprints" "$TMPDIR_TEST/run" "$TMPDIR_TEST/state" "$TMPDIR_TEST/events"
cp "$HARNESS_DIR_REAL/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/tools/solar-autopilot-monitor.py"
cp "$HARNESS_DIR_REAL/lib/graph_scheduler.py" "$TMPDIR_TEST/lib/graph_scheduler.py"

SID="sprint-test-deepresearch-gate-autopilot"
cat > "$TMPDIR_TEST/sprints/$SID.status.json" <<JSON
{
  "sprint_id": "$SID",
  "status": "active",
  "phase": "reviewing",
  "handoff_to": "evaluator",
  "priority": "P0"
}
JSON

cat > "$TMPDIR_TEST/sprints/$SID.task_graph.json" <<JSON
{
  "sprint_id": "$SID",
  "nodes": [
    {
      "id": "R8",
      "goal": "DeepResearch factuality gate",
      "status": "passed",
      "required_capabilities": ["research.factuality_evaluator"],
      "write_scope": ["$TMPDIR_TEST/out"]
    }
  ],
  "node_results": {
    "R8": {
      "status": "passed",
      "gate_status": "passed"
    }
  },
  "gate_results": {}
}
JSON

OUT="$(HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_KB_PROBE_INTERVAL_SEC=999999 SOLAR_MODEL_DOCTOR_INTERVAL_SEC=999999 python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --apply --json --cooldown 0)"
python3 - "$OUT" "$TMPDIR_TEST/sprints/$SID.task_graph.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
graph = json.loads(Path(sys.argv[2]).read_text())
actions = payload.get("actions") or []
if not any(a.get("action") == "deepresearch_quality_gate_repair" and a.get("reopened") for a in actions):
    raise SystemExit(f"missing repair action: {actions}")
node = graph["nodes"][0]
if node.get("status") != "reviewing":
    raise SystemExit(f"node not reopened: {node}")
if "research_quality_gate" in node:
    raise SystemExit(f"stale quality gate not cleared: {node}")
result = graph["node_results"]["R8"]
if result.get("status") != "reviewing" or result.get("gate_status") != "reviewing":
    raise SystemExit(f"node_results not reopened: {result}")
print(json.dumps({"ok": True, "feature": "deepresearch_quality_gate_autopilot_repair"}, ensure_ascii=False))
PY

echo "PASS: autopilot reopens completed DeepResearch nodes with missing/failed quality gate"
