#!/usr/bin/env bash
# Runtime-backed run-state transitions — status.json remains cache, session log is updated.
set -uo pipefail
cd "$(dirname "$0")/../.."
PASS=0; FAIL=0
ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

export PYTHONPATH="$PWD/lib:${PYTHONPATH:-}"
export SPRINTS_DIR="$TMP_DIR/sprints"
mkdir -p "$SPRINTS_DIR"

python3 -m py_compile lib/runtime_status.py \
  && ok "runtime_status.py compiles" \
  || { fail "runtime_status.py compile failed"; echo "PASS=$PASS FAIL=$FAIL"; exit 1; }

# shellcheck source=/dev/null
source lib/run-state.sh

make_status() {
  local sid="$1" status="$2" round="${3:-0}"
  cat > "$SPRINTS_DIR/${sid}.status.json" <<JSON
{"id":"${sid}","sid":"${sid}","sprint_id":"${sid}","status":"${status}","round":${round},"history":[]}
JSON
}

OUT=$(python3 - "$TMP_DIR" <<'PY'
import os, sys
print(os.path.exists(os.path.join(sys.argv[1], "sessions")))
PY
)
[[ "$OUT" == "False" ]] && ok "fixture starts without session log" || fail "fixture already has sessions"

make_status "sprint-runtime-rs-transition" "planning" 1
OUT=$(rs_transition "sprint-runtime-rs-transition" "approved" "plan_reviewed" "evaluator" '{"verdict":"APPROVE"}')
[[ "$OUT" == *"planning -> approved"* ]] \
  && ok "rs_transition reports planning -> approved" \
  || fail "rs_transition output: $OUT"

OUT=$(python3 - "$TMP_DIR" <<'PY'
import json, os, sys
sys.path.insert(0, "lib")
from projection_engine import ProjectionEngine
h=sys.argv[1]
sid="sprint-runtime-rs-transition"
status=json.load(open(os.path.join(h,"sprints",f"{sid}.status.json")))
assert status["status"] == "approved", status
assert status["phase"] == "plan_reviewed", status
assert status["runtime_state_source"] == "activity_runtime", status
assert os.path.exists(os.path.join(h,"sessions",sid,"events.jsonl")), "session log missing"
state=ProjectionEngine(sid, harness_dir=h).project()
assert state.status == "approved", state.status
# Status transition event must be present and projection-backed.
events=open(os.path.join(h,"sessions",sid,"events.jsonl")).read()
assert '"type": "state_transition"' in events, events
assert '"to": "approved"' in events, events
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "rs_transition writes status cache and session state_transition" \
                      || fail "rs_transition verification: $OUT"

make_status "sprint-runtime-rs-bump" "active" 2
OUT=$(rs_transition_with_round_bump "sprint-runtime-rs-bump" "reviewing" "implementation_completed" "builder" '{}')
[[ "$OUT" == *"active -> reviewing"* && "$OUT" == *"round=2->3"* ]] \
  && ok "rs_transition_with_round_bump reports round increment" \
  || fail "round bump output: $OUT"

OUT=$(python3 - "$TMP_DIR" <<'PY'
import json, os, sys
sys.path.insert(0, "lib")
from projection_engine import ProjectionEngine
h=sys.argv[1]
sid="sprint-runtime-rs-bump"
status=json.load(open(os.path.join(h,"sprints",f"{sid}.status.json")))
assert status["status"] == "reviewing", status
assert status["round"] == 3, status
assert status["handoff_to"] == "evaluator", status
state=ProjectionEngine(sid, harness_dir=h).project()
assert state.status == "reviewing", state.status
assert state.round == 3, state.round
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "round bump transition projects reviewing round=3" \
                      || fail "round bump verification: $OUT"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && echo "PASS" && exit 0 || { echo "FAIL"; exit 1; }
