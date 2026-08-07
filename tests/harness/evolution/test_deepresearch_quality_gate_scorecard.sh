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

touch "$TMPDIR_TEST/events/all.jsonl"
cat > "$TMPDIR_TEST/sprints/sprint-test-dr.task_graph.json" <<'JSON'
{
  "sprint_id": "sprint-test-dr",
  "nodes": [
    {
      "id": "R8",
      "goal": "DeepResearch factuality gate",
      "status": "passed",
      "required_capabilities": ["research.factuality_evaluator"],
      "research_quality_gate": {
        "ok": true,
        "verdict": "PASS",
        "auto_run": true,
        "metrics": {"citation_accuracy": 1.0}
      },
      "quality_gate_repair_requested_at": "2026-05-14T00:00:00Z"
    }
  ],
  "node_results": {
    "R8": {"status": "passed", "gate_status": "passed"}
  }
}
JSON

cat > "$TMPDIR_TEST/events/all.jsonl" <<'JSONL'
{"event":"autopilot_deepresearch_quality_gate_repair","sprint_id":"sprint-test-dr"}
JSONL

OUT="$(HARNESS_DIR="$TMPDIR_TEST" HARNESS_STATE_DB="$TMPDIR_TEST/run/state.db" python3 "$TMPDIR_TEST/lib/evolution_engine.py" scorecard --json)"
python3 - "$OUT" "$TMPDIR_TEST/run/state.db" <<'PY'
import json
import sqlite3
import sys

payload = json.loads(sys.argv[1])
cards = payload.get("scorecards") or []
card = next((c for c in cards if c.get("capability") == "deepresearch.quality_gate"), None)
if not card:
    raise SystemExit(f"missing scorecard in payload: {payload}")
if card.get("level") != "closed_loop":
    raise SystemExit(f"unexpected level: {card}")
if card.get("auto_run_count") != 1:
    raise SystemExit(f"missing auto_run count: {card}")
conn = sqlite3.connect(sys.argv[2])
row = conn.execute(
    "SELECT payload FROM capability_scorecards WHERE capability='deepresearch.quality_gate' AND provider='solar-harness'"
).fetchone()
conn.close()
if not row:
    raise SystemExit("scorecard row not persisted")
stored = json.loads(row[0])
if stored.get("repair_count", 0) < 1:
    raise SystemExit(f"repair_count missing: {stored}")
print(json.dumps({"ok": True, "feature": "deepresearch_quality_gate_scorecard"}, ensure_ascii=False))
PY

echo "PASS: DeepResearch quality gate scorecard persisted to evolution engine"
