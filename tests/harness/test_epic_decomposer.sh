#!/usr/bin/env bash
# Regression test: large requirement -> Epic + child PRDs/contracts + dependency activation.

set -euo pipefail
cd "$(dirname "$0")/.."

PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT
mkdir -p "$TMPDIR_TEST/sprints" "$TMPDIR_TEST/lib" "$TMPDIR_TEST/events" "$TMPDIR_TEST/run" "$TMPDIR_TEST/state"
cp lib/epic_decomposer.py "$TMPDIR_TEST/lib/epic_decomposer.py"
cp lib/prerequisite_resolver.py "$TMPDIR_TEST/lib/prerequisite_resolver.py"

ok() { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

run_epic() {
  HARNESS_DIR="$TMPDIR_TEST" SPRINTS_DIR="$TMPDIR_TEST/sprints" \
    python3 lib/epic_decomposer.py "$@"
}

json_get() {
  python3 - "$1" "$2" <<'PY'
import json, sys
obj=json.loads(sys.argv[1])
cur=obj
for part in sys.argv[2].split("."):
    if part.isdigit():
        cur=cur[int(part)]
    else:
        cur=cur[part]
print(cur)
PY
}

CLASSIFIER="$(sed -n '/^should_epic_decompose_request()/,/^}/p' solar-harness.sh)"
eval "$CLASSIFIER"
if declare -F should_epic_decompose_request >/dev/null 2>&1; then
  should_epic_decompose_request "请改造 solar-harness 的 PM/Planner 流程：先分析需求，写 PRD 和设计文档，生成任务图，再并行调度 builder 开发，最后自动验证闭环。" \
    && ok "complex classifier triggers without special keyword" \
    || fail "complex classifier missed ordinary complex request"
  if should_epic_decompose_request "修一个 typo"; then
    fail "complex classifier over-triggered simple request"
  else
    ok "complex classifier leaves simple request as sprint"
  fi
else
  ok "complex classifier unavailable in this install; epic tests continue"
fi

REQ="把 Solar-Harness 改造成自动拆 PRD、设计、任务图、并行调度和防半截完成的系统。"
OUT="$(run_epic create --title "复杂需求拆分运行时" --request "$REQ" --slug epic-split-test --activate-ready --json)"
EPIC_ID="$(json_get "$OUT" epic_id)"
FIRST_SID="$(json_get "$OUT" children.0.sid)"
SECOND_SID="$(json_get "$OUT" children.1.sid)"

[[ -f "$TMPDIR_TEST/sprints/${EPIC_ID}.epic.md" ]] && ok "epic markdown written" || fail "epic markdown missing"
[[ -f "$TMPDIR_TEST/sprints/${EPIC_ID}.epic.json" ]] && ok "epic metadata written" || fail "epic metadata missing"
[[ -f "$TMPDIR_TEST/sprints/${EPIC_ID}.task_graph.json" ]] && ok "parent task graph written" || fail "parent task graph missing"
[[ -f "$TMPDIR_TEST/sprints/${EPIC_ID}.traceability.json" ]] && ok "traceability metadata written" || fail "traceability missing"
[[ -f "$TMPDIR_TEST/sprints/${FIRST_SID}.prd.md" && -f "$TMPDIR_TEST/sprints/${FIRST_SID}.contract.md" ]] \
  && ok "first child PRD/contract written" || fail "first child PRD/contract missing"

FIRST_STATUS="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$TMPDIR_TEST/sprints/${FIRST_SID}.status.json")"
SECOND_STATUS="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$TMPDIR_TEST/sprints/${SECOND_SID}.status.json")"
[[ "$FIRST_STATUS" == "active" ]] && ok "root child activated" || fail "root child status expected active got $FIRST_STATUS"
[[ "$SECOND_STATUS" == "queued" ]] && ok "dependent child queued" || fail "dependent child status expected queued got $SECOND_STATUS"

OUT_CAPPED="$(run_epic create --title "全局 WIP 已满的复杂需求" --request "$REQ" --slug epic-split-capped --activate-ready --global-active-limit 1 --json)"
CAPPED_EPIC_ID="$(json_get "$OUT_CAPPED" epic_id)"
CAPPED_FIRST_SID="$(json_get "$OUT_CAPPED" children.0.sid)"
CAPPED_FIRST_STATUS="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$TMPDIR_TEST/sprints/${CAPPED_FIRST_SID}.status.json")"
[[ "$CAPPED_FIRST_STATUS" == "queued" ]] && ok "global WIP cap prevents initial root child activation" || fail "capped root child expected queued got $CAPPED_FIRST_STATUS"
CAPPED_EPIC_STATUS="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$TMPDIR_TEST/sprints/${CAPPED_EPIC_ID}.epic.json")"
[[ "$CAPPED_EPIC_STATUS" == "queued" ]] && ok "capped epic remains queued" || fail "capped epic expected queued got $CAPPED_EPIC_STATUS"
CAP_ACTIVATE_OUT="$(run_epic activate-ready "$CAPPED_EPIC_ID" --global-active-limit 1 --json)"
python3 - "$CAP_ACTIVATE_OUT" <<'PY' \
  && ok "activate-ready reports global WIP backpressure" || fail "activate-ready did not report WIP backpressure"
import json, sys
payload = json.loads(sys.argv[1])
assert payload["activated"] == [], payload
assert payload["backpressure"] is True, payload
assert payload["backpressure_reason"] == "global_epic_child_wip_limit", payload
PY
HARNESS_DIR="$TMPDIR_TEST" SOLAR_EPIC_ACTIVE_CHILD_LIMIT=1 python3 - "$CAPPED_EPIC_ID" <<'PY' \
  && ok "autopilot suppresses ready children when global WIP cap is full" || fail "autopilot did not suppress ready children under WIP cap"
import importlib.util
import sys
from pathlib import Path

root = Path.cwd()
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", root / "tools" / "solar-autopilot-monitor.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
findings = mod.inspect_epics()
assert any(f.get("type") == "epic_activation_backpressure" for f in findings), findings
assert not any(
    f.get("type") == "epic_ready_children" and f.get("sid") == sys.argv[1]
    for f in findings
), findings
PY
python3 - "$TMPDIR_TEST" "$CAPPED_EPIC_ID" <<'PY'
import json, sys
from pathlib import Path

root = Path(sys.argv[1]) / "sprints"
epic_id = sys.argv[2]
meta_path = root / f"{epic_id}.epic.json"
meta = json.loads(meta_path.read_text())
for sid in meta.get("child_sprints", []):
    status_path = root / f"{sid}.status.json"
    if not status_path.exists():
        continue
    status = json.loads(status_path.read_text())
    status["status"] = "cancelled"
    status["phase"] = "superseded"
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
meta["status"] = "closed"
meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
PY

run_epic validate "$EPIC_ID" --json | grep -q '"ok": true' \
  && ok "epic validates" || fail "epic validate failed"

PYTHONPATH=lib python3 - "$TMPDIR_TEST/sprints/${EPIC_ID}.task_graph.json" <<'PY' \
  && ok "parent task graph is valid" || fail "parent task graph invalid"
import json, sys
from graph_scheduler import validate_graph, topo_layers
graph=json.load(open(sys.argv[1]))
v=validate_graph(graph)
assert v["ok"], v
layers=topo_layers(graph)
assert layers[0] == ["S01_requirements"], layers
assert "S03_core_runtime" in layers[2] and "S04_orchestration_ui" in layers[2], layers
PY

python3 - "$TMPDIR_TEST/sprints/${FIRST_SID}.status.json" <<'PY'
import json, sys
p=sys.argv[1]
d=json.load(open(p))
d["status"]="passed"
d["phase"]="completed"
open(p,"w").write(json.dumps(d, ensure_ascii=False, indent=2)+"\n")
PY

cat > "$TMPDIR_TEST/sprints/${SECOND_SID}.task_graph.json" <<JSON
{
  "sprint_id": "${SECOND_SID}",
  "prerequisites": ["sprint-external-runtime:passed"],
  "dependency_policy": {"blocks_until": ["sprint-external-runtime:passed"]},
  "nodes": [
    {
      "id": "N1",
      "goal": "waits for external runtime",
      "depends_on": [],
      "write_scope": ["lib/runtime-ui.py"],
      "acceptance": ["blocked until external runtime passed"]
    }
  ]
}
JSON
cat > "$TMPDIR_TEST/sprints/${SECOND_SID}.design.md" <<< "# Design"
cat > "$TMPDIR_TEST/sprints/${SECOND_SID}.plan.md" <<< "# Plan"
HARNESS_DIR="$TMPDIR_TEST" python3 - "$EPIC_ID" "$SECOND_SID" <<'PY' \
  && ok "external child task_graph prerequisite blocks epic activation" || fail "external child prerequisite did not block activation"
import importlib.util
import sys
from pathlib import Path

root = Path.cwd()
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", root / "tools" / "solar-autopilot-monitor.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
findings = mod.inspect_epics()
assert not any(f.get("type") == "epic_ready_children" and f.get("sid") == sys.argv[1] for f in findings), findings
PY
python3 - "$TMPDIR_TEST/sprints/sprint-external-runtime.status.json" <<'PY'
import json, sys
open(sys.argv[1], "w").write(json.dumps({"id":"sprint-external-runtime","status":"passed","phase":"eval_passed"}, ensure_ascii=False, indent=2)+"\n")
PY

HARNESS_DIR="$TMPDIR_TEST" python3 - "$EPIC_ID" "$SECOND_SID" <<'PY' \
  && ok "autopilot activates dependency-ready child" || fail "autopilot did not activate ready child"
import importlib.util
import os
import sys
from pathlib import Path

root = Path.cwd()
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", root / "tools" / "solar-autopilot-monitor.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
findings = mod.inspect_epics()
assert any(f.get("type") == "epic_ready_children" and f.get("sid") == sys.argv[1] for f in findings), findings
state = mod.load_state()
actions = mod.apply_findings(findings, dispatch=False, state=state, cooldown=0)
assert any(a.get("action") == "epic_ready_children" and a.get("ok") for a in actions), actions
PY
SECOND_AFTER="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$TMPDIR_TEST/sprints/${SECOND_SID}.status.json")"
[[ "$SECOND_AFTER" == "active" ]] && ok "second child status active after activation" || fail "second child activation status got $SECOND_AFTER"

bash -n solar-harness.sh && ok "solar-harness.sh syntax ok" || fail "solar-harness.sh syntax failed"
python3 -m py_compile lib/epic_decomposer.py tools/solar-autopilot-monitor.py && ok "epic/autopilot python compile" || fail "python compile failed"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
