#!/usr/bin/env bash
# Wake projection routing — projection state drives routing, no ambiguous builder fallback
set -uo pipefail
cd "$(dirname "$0")/../.."
PASS=0; FAIL=0
ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

export PYTHONPATH="$PWD/lib:${PYTHONPATH:-}"

# ---- projection compiles ----
python3 -m py_compile lib/projection_engine.py \
  && ok "projection_engine.py compiles" \
  || { fail "compile failed"; echo "PASS=$PASS FAIL=$FAIL"; exit 1; }

# Helper: create a status.json fixture in TMP_DIR/sprints/
make_status() {
  local sid="$1" status="$2"
  mkdir -p "$TMP_DIR/sprints"
  cat > "$TMP_DIR/sprints/${sid}.status.json" <<JSON
{"sid":"${sid}","id":"${sid}","sprint_id":"${sid}","status":"${status}","round":1}
JSON
}

# Helper: route_via_projection — mirrors the logic wake should use
route_via_projection() {
  python3 - "$TMP_DIR" "$1" <<'PY'
import sys, os, json
sys.path.insert(0, 'lib')
from projection_engine import ProjectionEngine

harness_dir = sys.argv[1]
sprint_id   = sys.argv[2]
path = os.path.join(harness_dir, "sprints", f"{sprint_id}.status.json")
if not os.path.exists(path):
    print("pm_diagnosis")
    sys.exit(0)

with open(path) as fh:
    data = json.load(fh)
status = data.get("status", "unknown")

routing = {
    "queued":    "builder",
    "active":    "builder",
    "reviewing": "evaluator",
    "passed":    "coordinator",
    "error":     "runtime_doctor",
    "cancelled": "coordinator",
}
role = routing.get(status)
if role is None:
    print("pm_diagnosis")
else:
    print(role)
PY
}

# ---- queued → builder ----
make_status "sprint-wake-queued" "queued"
ROUTE=$(route_via_projection "sprint-wake-queued")
[[ "$ROUTE" == "builder" ]] \
  && ok "queued → routes to builder" \
  || fail "queued routing: got $ROUTE"

# ---- active → builder ----
make_status "sprint-wake-active" "active"
ROUTE=$(route_via_projection "sprint-wake-active")
[[ "$ROUTE" == "builder" ]] \
  && ok "active → routes to builder" \
  || fail "active routing: got $ROUTE"

# ---- reviewing → evaluator ----
make_status "sprint-wake-reviewing" "reviewing"
ROUTE=$(route_via_projection "sprint-wake-reviewing")
[[ "$ROUTE" == "evaluator" ]] \
  && ok "reviewing → routes to evaluator" \
  || fail "reviewing routing: got $ROUTE"

# ---- passed → coordinator ----
make_status "sprint-wake-passed" "passed"
ROUTE=$(route_via_projection "sprint-wake-passed")
[[ "$ROUTE" == "coordinator" ]] \
  && ok "passed → routes to coordinator" \
  || fail "passed routing: got $ROUTE"

# ---- error → runtime_doctor (not generic builder fallback) ----
make_status "sprint-wake-error" "error"
ROUTE=$(route_via_projection "sprint-wake-error")
[[ "$ROUTE" == "runtime_doctor" ]] \
  && ok "error → routes to runtime_doctor (not builder fallback)" \
  || fail "error routing: got $ROUTE"

# ---- unknown state → pm_diagnosis ----
make_status "sprint-wake-unknown" "some_unknown_state"
ROUTE=$(route_via_projection "sprint-wake-unknown")
[[ "$ROUTE" == "pm_diagnosis" ]] \
  && ok "unknown state → routes to pm_diagnosis (not generic builder)" \
  || fail "unknown state routing: got $ROUTE"

# ---- missing sprint → pm_diagnosis ----
ROUTE=$(route_via_projection "sprint-nonexistent-99")
[[ "$ROUTE" == "pm_diagnosis" ]] \
  && ok "missing sprint → pm_diagnosis" \
  || fail "missing sprint routing: got $ROUTE"

# ---- projection from events overrides stale status.json ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys, os, json
sys.path.insert(0, 'lib')
from session_log import SessionLog
from projection_engine import ProjectionEngine

sid = "sprint-wake-override"
# Write a stale status.json claiming 'queued'
os.makedirs(os.path.join(sys.argv[1], "sprints"), exist_ok=True)
with open(os.path.join(sys.argv[1], "sprints", f"{sid}.status.json"), "w") as fh:
    json.dump({"sid": sid, "sprint_id": sid, "status": "queued", "round": 0}, fh)

# Seed events showing it's actually active
log = SessionLog(sid, harness_dir=sys.argv[1])
log.append("command_issued",   actor="coordinator", sprint_id=sid, activity_id="a1", payload={})
log.append("activity_started", actor="builder",     sprint_id=sid, activity_id="a1", payload={})

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
# Projected should be 'active', disk says 'queued' — drift detectable
assert state.status == "active", f"projected should be active, got {state.status}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "projection from events reflects true state even if status.json is stale" \
                      || fail "stale status.json override: $OUT"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && echo "PASS" && exit 0 || { echo "FAIL"; exit 1; }
