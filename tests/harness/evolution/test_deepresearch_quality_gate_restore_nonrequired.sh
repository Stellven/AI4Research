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

SID="sprint-test-dr-restore"
GRAPH="$TMPDIR_TEST/sprints/$SID.task_graph.json"
cat > "$GRAPH" <<JSON
{
  "sprint_id": "$SID",
  "nodes": [
    {
      "id": "N1",
      "goal": "Write DeepResearch PRD, not a research report",
      "status": "reviewing",
      "required_capabilities": ["product.requirements"],
      "quality_gate_repair_requested_at": "2026-05-14T00:00:00Z"
    },
    {
      "id": "N2",
      "goal": "Write research final report",
      "status": "reviewing",
      "required_capabilities": ["research.report.compile"],
      "quality_gate_repair_requested_at": "2026-05-14T00:00:00Z"
    }
  ],
  "node_results": {
    "N1": {"status": "reviewing", "gate_status": "reviewing"},
    "N2": {"status": "reviewing", "gate_status": "reviewing"}
  }
}
JSON

cat > "$TMPDIR_TEST/sprints/$SID.events.jsonl" <<JSONL
{"event":"evolution_deepresearch_quality_gate_repair_requested","sprint_id":"$SID","data":{"sprint_id":"$SID","node_id":"N1","node_status":"passed"}}
{"event":"evolution_deepresearch_quality_gate_repair_requested","sprint_id":"$SID","data":{"sprint_id":"$SID","node_id":"N2","node_status":"passed"}}
JSONL

OUT="$(HARNESS_DIR="$TMPDIR_TEST" HARNESS_STATE_DB="$TMPDIR_TEST/run/state.db" python3 "$TMPDIR_TEST/lib/evolution_engine.py" restore-nonrequired-deepresearch-repairs --apply --json)"
python3 - "$OUT" "$GRAPH" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
graph = json.loads(Path(sys.argv[2]).read_text())
if payload.get("candidate_count") != 1 or payload.get("restored_count") != 1:
    raise SystemExit(f"bad restore payload: {payload}")
nodes = {node["id"]: node for node in graph["nodes"]}
if nodes["N1"].get("status") != "passed":
    raise SystemExit(f"N1 not restored: {nodes['N1']}")
if nodes["N2"].get("status") != "reviewing":
    raise SystemExit(f"N2 should still require gate: {nodes['N2']}")
if "quality_gate_repair_requested_at" in nodes["N1"]:
    raise SystemExit(f"N1 repair marker not cleared: {nodes['N1']}")
if graph["node_results"]["N1"].get("status") != "passed":
    raise SystemExit(f"N1 result not restored: {graph['node_results']['N1']}")
print(json.dumps({"ok": True, "feature": "deepresearch_restore_nonrequired_repairs"}, ensure_ascii=False))
PY

echo "PASS: evolution engine restores non-required DeepResearch repair false positives"
