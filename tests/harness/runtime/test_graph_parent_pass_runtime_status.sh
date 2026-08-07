#!/usr/bin/env bash
set -euo pipefail

REAL_HARNESS="${HOME}/.solar/harness"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/sprints" "$TMP/run"
ln -s "$REAL_HARNESS/lib" "$TMP/lib"

export HARNESS_DIR="$TMP"
sid="sprint-test-graph-parent-runtime"

cat > "$TMP/sprints/${sid}.status.json" <<JSON
{
  "id": "$sid",
  "sprint_id": "$sid",
  "status": "active",
  "phase": "planning_complete",
  "round": 0,
  "history": []
}
JSON

python3 - "$sid" <<'PY'
import os
import sys

harness = os.environ["HARNESS_DIR"]
sys.path.insert(0, f"{harness}/lib")

import graph_node_dispatcher as dispatcher

ok = dispatcher._mark_parent_sprint_passed_if_ready(
    sys.argv[1],
    {"ready": True, "node_count": 2, "required_gates": ["G1"]},
    False,
)
assert ok is True
PY

python3 - "$TMP" "$sid" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
sid = sys.argv[2]
status = json.loads((root / "sprints" / f"{sid}.status.json").read_text())
assert status["status"] == "passed", status
assert status["runtime_state_source"] == "activity_runtime", status
assert status["graph_parent_ready"]["node_count"] == 2, status

session_path = root / "sessions" / sid / "events.jsonl"
events = [json.loads(line) for line in session_path.read_text().splitlines() if line.strip()]
types = [e.get("type") for e in events]
assert "state_transition" in types, types
assert "activity_succeeded" in types, types
print("PASS graph parent pass uses runtime_status and session log")
PY

