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

python3 - "$TMPDIR_TEST/sprints/$SID.task_graph.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
graph = json.loads(path.read_text())
record = {
    "schema_version": "solar.human_review.v1",
    "generation": 1,
    "state": "blocked",
    "reason": "operator result failed repeatedly",
}
graph["nodes"][0]["status"] = "needs_human_review"
graph["nodes"][0]["human_review"] = record
graph["node_results"]["R8"] = {
    "status": "needs_human_review",
    "human_review": record,
}
path.write_text(json.dumps(graph))
PY

HARNESS_DIR="$TMPDIR_TEST" python3 - "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/sprints/$SID.task_graph.json" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

module_path = Path(sys.argv[1])
graph_path = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

# Simulate a finding collected immediately before another writer escalated the
# node.  Apply-time validation must protect the newer human-review authority.
actions = module.apply_findings(
    [{
        "sid": "sprint-test-deepresearch-gate-autopilot",
        "type": "deepresearch_quality_gate_repair",
        "node_id": "R8",
        "graph_path": str(graph_path),
        "node_status": "passed",
        "gate_status": "missing",
    }],
    dispatch=False,
    state={"actions": {}},
    cooldown=0,
)
graph = json.loads(graph_path.read_text())
node = graph["nodes"][0]
if node.get("status") != "needs_human_review":
    raise SystemExit(f"stale repair finding reopened human review: {node}")
if not any(a.get("skipped") == "needs_human_review_requires_explicit_resume" for a in actions):
    raise SystemExit(f"missing explicit-resume skip: {actions}")
print(json.dumps({"ok": True, "feature": "human_review_absorbs_stale_autopilot_repair"}))
PY

echo "PASS: stale quality-gate findings cannot reopen human review"
