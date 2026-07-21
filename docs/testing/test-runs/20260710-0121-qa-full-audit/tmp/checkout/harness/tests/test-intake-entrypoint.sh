#!/usr/bin/env bash
# Regression: user request intake must create sprint/epic artifacts without
# manually crafting status files, and must archive the raw request for KB ingest.

set -euo pipefail
cd "$(dirname "$0")/.."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/lib" "$TMP/sprints" "$TMP/personas" "$TMP/templates" "$TMP/raw" "$TMP/tools"

cp -R lib/. "$TMP/lib/"
cp -R tools/. "$TMP/tools/"
[[ -d config ]] && cp -R config "$TMP/config"
[[ -d schemas ]] && cp -R schemas "$TMP/schemas"

cp solar-harness.sh "$TMP/solar-harness.sh"

python3 - "$TMP/solar-harness.sh" "$TMP" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
tmp = sys.argv[2]
s = p.read_text()
s = s.replace('HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"', f'HARNESS_DIR="${{HARNESS_DIR:-{tmp}}}"', 1)
s = s.replace('HARNESS_DIR="$HOME/.solar/harness"', f'HARNESS_DIR="{tmp}"', 1)
p.write_text(s)
PY
chmod +x "$TMP/solar-harness.sh"

RAW_DIR="$TMP/raw"
INTENT_DIR="$TMP/intents"

SOLAR_KNOWLEDGE_RAW_DIR="$RAW_DIR" SOLAR_INTENT_GATEWAY_DIR="$INTENT_DIR" "$TMP/solar-harness.sh" intake --no-dispatch --stdin <<'EOF'
修复一个按钮文案 typo。
EOF

status_count=$(find "$TMP/sprints" -name 'sprint-*.status.json' | wc -l | tr -d ' ')
raw_count=$(find "$RAW_DIR" -name 'intake-*.md' | wc -l | tr -d ' ')
consumer_count=$(find "$INTENT_DIR" -name 'consumer.json' | wc -l | tr -d ' ')
[[ "$status_count" -eq 1 ]] || { echo "FAIL: expected one sprint status, got $status_count"; exit 1; }
[[ "$raw_count" -eq 1 ]] || { echo "FAIL: expected one raw intake record, got $raw_count"; exit 1; }
[[ "$consumer_count" -eq 1 ]] || { echo "FAIL: expected one intent consumer record, got $consumer_count"; exit 1; }

python3 - "$TMP/sprints" "$INTENT_DIR" <<'PY'
import json
import pathlib
import sys
sprints = pathlib.Path(sys.argv[1])
intents = pathlib.Path(sys.argv[2])
status = json.loads(next(sprints.glob("sprint-*.status.json")).read_text())
assert status["status"] == "drafting", status
assert status["phase"] == "prd_ready", status
assert status["handoff_to"] == "planner", status
contract = next(sprints.glob("sprint-*.contract.md")).read_text()
assert "修复一个按钮文案 typo" in contract, contract
raw_intent = next(sprints.glob("sprint-*.raw_intent.json"))
rewritten = next(sprints.glob("sprint-*.rewritten_intent.json"))
ir = next(sprints.glob("sprint-*.requirement_ir.json"))
trace = next(sprints.glob("sprint-*.requirement_trace.json"))
assert json.loads(raw_intent.read_text())["schema_version"] == "solar.raw_intent.v1"
assert json.loads(rewritten.read_text())["schema_version"] == "solar.rewritten_intent.v1"
assert json.loads(ir.read_text())["compiler_next"] == "pm_planner_task_graph"
assert json.loads(trace.read_text())["stages"][0]["stage"] == "raw_intent_capture"
consumer = json.loads(next(intents.glob("intent-*/consumer.json")).read_text())
assert consumer["status"] == "consumed", consumer
assert consumer["sprint_id"] == (status.get("sprint_id") or status["id"]), consumer
PY

simple_sid=$(python3 - "$TMP/sprints" <<'PY'
import json
import pathlib
import sys
sprints = pathlib.Path(sys.argv[1])
status = json.loads(next(sprints.glob("sprint-*.status.json")).read_text())
print(status.get("sprint_id") or status["id"])
PY
)

HARNESS_DIR="$TMP" python3 - "$TMP/tools/solar-autopilot-monitor.py" "$simple_sid" <<'PY'
import importlib.util
import sys

script, sid = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor_test", script)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
findings = mod.inspect_sprints()
matches = [f for f in findings if f.get("sid") == sid and f.get("type") == "ready_for_pm"]
if not matches:
    matches = [f for f in findings if f.get("sid") == sid and f.get("type") == "ready_for_planner"]
assert matches, findings
assert ".prd.md" in matches[0].get("message", ""), matches[0]
assert matches[0].get("target", "").endswith(":0.1"), matches[0]
PY

HARNESS_DIR="$TMP" python3 - "$TMP/tools/solar-autopilot-monitor.py" <<'PY'
import importlib.util
import json
import sys

script = sys.argv[1]
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor_queue_test", script)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
mod.QUEUE.parent.mkdir(parents=True, exist_ok=True)
mod.QUEUE.write_text(json.dumps({
    "sid": "sprint-20990101-missing",
    "type": "ready_for_planner",
    "target": "solar-harness:0.1",
    "created_at_epoch": 0,
}, ensure_ascii=False) + "\n")
actions = mod.retry_queue({}, dispatch=False, cooldown=0)
assert actions and actions[0].get("dropped") == "stale_sprint", actions
assert mod.load_queue() == [], mod.load_queue()

sid = "sprint-20990101-terminal"
(mod.SPRINTS / f"{sid}.status.json").write_text(json.dumps({
    "sprint_id": sid,
    "status": "passed",
    "phase": "completed",
    "handoff_to": "done",
}, ensure_ascii=False) + "\n")
mod.QUEUE.write_text(json.dumps({
    "sid": sid,
    "type": "graph_node_idle_assigned",
    "target": "solar-harness-lab:0.2",
    "created_at_epoch": 9999999999,
}, ensure_ascii=False) + "\n")
actions = mod.retry_queue({}, dispatch=True, cooldown=0)
assert actions and actions[0].get("dropped") == "terminal_sprint", actions
assert mod.load_queue() == [], mod.load_queue()
PY

SOLAR_KNOWLEDGE_RAW_DIR="$RAW_DIR" SOLAR_INTENT_GATEWAY_DIR="$INTENT_DIR" SOLAR_EPIC_MIN_CHARS=60 "$TMP/solar-harness.sh" intake --no-dispatch \
  "把 Solar-Harness 改造成大需求自动拆分、多个 PRD、设计、任务图、并行调度、验证闭环的系统。"

epic_count=$(find "$TMP/sprints" -name 'epic-*.epic.json' | wc -l | tr -d ' ')
[[ "$epic_count" -eq 1 ]] || { echo "FAIL: expected one epic, got $epic_count"; exit 1; }

python3 - "$TMP/sprints" <<'PY'
import json
import pathlib
import sys
sprints = pathlib.Path(sys.argv[1])
epic = json.loads(next(sprints.glob("epic-*.epic.json")).read_text())
assert epic["status"] == "active", epic
children = epic["child_sprints"]
assert len(children) >= 3, children
root = json.loads((sprints / f"{children[0]}.status.json").read_text())
second = json.loads((sprints / f"{children[1]}.status.json").read_text())
assert root["status"] == "active" and root["handoff_to"] == "planner", root
assert second["status"] == "queued", second
PY

echo "PASS: intake entrypoint creates PM-first sprint and epic DAG records"
