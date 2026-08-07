#!/usr/bin/env bash
# Projection Engine — rebuild sprint status from events; legacy status.json cache
set -uo pipefail
cd "$(dirname "$0")/../.."
PASS=0; FAIL=0
ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

export PYTHONPATH="$PWD/lib:${PYTHONPATH:-}"

python3 -m py_compile lib/projection_engine.py \
  && ok "projection_engine.py compiles" \
  || { fail "projection_engine.py compile failed"; echo "PASS=$PASS FAIL=$FAIL"; exit 1; }

# ---- active sprint projects to 'active' ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys, os
sys.path.insert(0, 'lib')
from session_log import SessionLog
from projection_engine import ProjectionEngine

sid = "sprint-proj-active"
log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("command_issued",   actor="coordinator", sprint_id=sid, activity_id="a1", payload={})
log.append("activity_started", actor="builder",     sprint_id=sid, activity_id="a1", payload={})

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "active", f"expected active, got {state.status}"
assert state.event_count == 2
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "command_issued + activity_started → status=active" \
                      || fail "active projection: $OUT"

# ---- succeeded sprint projects to 'passed' ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog
from projection_engine import ProjectionEngine

sid = "sprint-proj-passed"
log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("command_issued",    actor="coordinator", sprint_id=sid, activity_id="a1", payload={})
log.append("activity_started",  actor="builder",     sprint_id=sid, activity_id="a1", payload={})
log.append("activity_succeeded",actor="builder",     sprint_id=sid, activity_id="a1", payload={})

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "passed", f"expected passed, got {state.status}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "activity_succeeded → status=passed" \
                      || fail "passed projection: $OUT"

# ---- handoff projects to 'reviewing' ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog
from projection_engine import ProjectionEngine

sid = "sprint-proj-reviewing"
log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("command_issued",  actor="coordinator", sprint_id=sid, activity_id="a1", payload={})
log.append("activity_started",actor="builder",     sprint_id=sid, activity_id="a1", payload={})
log.append("activity_handoff",actor="builder",     sprint_id=sid, activity_id="a1",
           payload={"to_actor":"evaluator","round":1})

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "reviewing", f"expected reviewing, got {state.status}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "activity_handoff → status=reviewing" \
                      || fail "reviewing projection: $OUT"

# ---- error projection ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog
from projection_engine import ProjectionEngine

sid = "sprint-proj-error"
log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("command_issued",  actor="coordinator", sprint_id=sid, activity_id="a1", payload={})
log.append("activity_started",actor="builder",     sprint_id=sid, activity_id="a1", payload={})
log.append("activity_failed", actor="builder",     sprint_id=sid, activity_id="a1",
           payload={"error": "compilation failed"})

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "error", f"expected error, got {state.status}"
assert state.activities[0].error_count == 1
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "activity_failed → status=error, error_count=1" \
                      || fail "error projection: $OUT"

# ---- write_status_cache produces legacy-compatible JSON ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys, os, json
sys.path.insert(0, 'lib')
from session_log import SessionLog
from projection_engine import ProjectionEngine

sid = "sprint-proj-cache"
os.makedirs(os.path.join(sys.argv[1], "sprints"), exist_ok=True)

log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("command_issued",    actor="coordinator", sprint_id=sid, activity_id="a1", payload={})
log.append("activity_succeeded",actor="builder",     sprint_id=sid, activity_id="a1", payload={})

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
eng.write_status_cache(state)

path = os.path.join(sys.argv[1], "sprints", f"{sid}.status.json")
assert os.path.exists(path), "status.json not written"
with open(path) as fh:
    data = json.load(fh)
assert data["status"] == "passed",   f"bad status: {data['status']}"
assert data["sprint_id"] == sid,     "sprint_id missing"
assert "projected_at" in data,       "projected_at missing"
assert data["event_count"] == 2,     f"event_count wrong: {data['event_count']}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "write_status_cache writes legacy-compatible status.json" \
                      || fail "write_status_cache: $OUT"

# ---- duplicate command detection ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog, DuplicateEventError
from projection_engine import ProjectionEngine

sid = "sprint-proj-dup"
log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("command_issued", actor="coordinator", sprint_id=sid, activity_id="a1",
           idempotency_key="cmd:round1", payload={})
# Force a second command_issued with same key by writing raw line (simulates legacy tools)
import json, os
log_path = os.path.join(sys.argv[1], "sessions", sid, "events.jsonl")
with open(log_path, "a") as fh:
    import uuid, datetime
    ev = {
        "event_id": str(uuid.uuid4()),
        "session_id": sid,
        "seq": 2,
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": "command_issued",
        "actor": "coordinator",
        "source": "test",
        "sprint_id": sid,
        "activity_id": "a1",
        "correlation_id": None,
        "causation_id": None,
        "idempotency_key": "cmd:round1",
        "payload": {},
    }
    fh.write(json.dumps(ev) + "\n")

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert len(state.duplicate_commands) >= 1, f"no dup detected: {state.duplicate_commands}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "duplicate command events flagged in projection" \
                      || fail "duplicate command detection: $OUT"

# ---- composite legacy state identity normalizes to embedded status ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog
from projection_engine import ProjectionEngine

sid = "sprint-composite-state"
log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("activity_failed", actor="coordinator", sprint_id=sid,
           activity_id="old-dispatch", payload={"error": "old failure"})
log.append("state_transition", actor="coordinator", sprint_id=sid,
           payload={"from": "", "to": f"{sid}:passed:eval_passed:_:abc123", "round": 3})
state = ProjectionEngine(sid, harness_dir=sys.argv[1]).project()
assert state.status == "passed", state.status
assert state.stale_activities == [], state.stale_activities
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "composite legacy state identity normalizes to embedded status" \
                      || fail "composite legacy state: $OUT"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && echo "PASS" && exit 0 || { echo "FAIL"; exit 1; }
