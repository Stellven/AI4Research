#!/usr/bin/env bash
# Runtime adoption bridge — legacy status/events become session-log v2 facts.
set -uo pipefail
cd "$(dirname "$0")/../.."
PASS=0; FAIL=0
ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

export PYTHONPATH="$PWD/lib:${PYTHONPATH:-}"

python3 -m py_compile lib/runtime_bridge.py lib/projection_engine.py lib/runtime_doctor.py \
  && ok "runtime adoption modules compile" \
  || { fail "compile failed"; echo "PASS=$PASS FAIL=$FAIL"; exit 1; }

mkdir -p "$TMP_DIR/sprints"

OUT=$(python3 - "$TMP_DIR" <<'PY'
import json, os, sys
sys.path.insert(0, "lib")
from runtime_bridge import adopt_sprint
from projection_engine import ProjectionEngine

h = sys.argv[1]
sid = "sprint-runtime-adopt-pass"
status_path = os.path.join(h, "sprints", f"{sid}.status.json")
events_path = os.path.join(h, "sprints", f"{sid}.events.jsonl")
with open(status_path, "w") as fh:
    json.dump({"id": sid, "sprint_id": sid, "status": "passed", "phase": "eval_passed", "round": 2}, fh)
with open(events_path, "w") as fh:
    fh.write(json.dumps({"ts": "2026-05-11T00:00:00Z", "event": "dispatched", "by": "coordinator", "data": {"to": "builder"}}) + "\n")

result = adopt_sprint(sid, harness_dir=__import__("pathlib").Path(h), write_cache=True)
assert os.path.exists(os.path.join(h, "sessions", sid, "events.jsonl")), "session log missing"
state = ProjectionEngine(sid, harness_dir=h).project()
assert state.status == "passed", state.status
assert state.event_count >= 4, state.event_count
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "adopt_sprint creates session log and projects passed" \
                      || fail "adopt_sprint passed projection: $OUT"

OUT=$(python3 - "$TMP_DIR" <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, "lib")
from runtime_bridge import record_legacy_event
from projection_engine import ProjectionEngine

h = Path(sys.argv[1])
sid = "sprint-runtime-dual-write"
(h / "sprints").mkdir(exist_ok=True)
result = record_legacy_event(sid, "dispatched", "coordinator", {"to": "builder", "task": "implement", "round": 1}, harness_dir=h)
assert result["ok"], result
state = ProjectionEngine(sid, harness_dir=str(h)).project()
assert state.status == "queued", state.status
assert state.event_count >= 2, state.event_count
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "record_legacy_event dual-writes dispatch as command" \
                      || fail "dual-write dispatch: $OUT"

OUT=$(python3 - "$TMP_DIR" <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, "lib")
import runtime_doctor

h = Path(sys.argv[1])
runtime_doctor.HARNESS_DIR = str(h)
runtime_doctor.SPRINTS_DIR = str(h / "sprints")
runtime_doctor.SESSIONS_DIR = str(h / "sessions")
sid = "sprint-runtime-doctor-adopts"
(h / "sprints").mkdir(exist_ok=True)
with open(h / "sprints" / f"{sid}.status.json", "w") as fh:
    json.dump({"id": sid, "sprint_id": sid, "status": "active", "round": 1}, fh)
report = runtime_doctor.doctor_sprint(sid)
assert os.path.exists(h / "sessions" / sid / "events.jsonl"), "doctor did not adopt"
assert report["checks"]["event_log_health"]["event_count"] > 0, report
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "runtime doctor adopts legacy sprint before checks" \
                      || fail "runtime doctor adoption: $OUT"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && echo "PASS" && exit 0 || { echo "FAIL"; exit 1; }
