#!/usr/bin/env bash
# Activity Runtime — lifecycle event convergence tests
set -uo pipefail
cd "$(dirname "$0")/../.."
PASS=0; FAIL=0
ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

export PYTHONPATH="$PWD/lib:${PYTHONPATH:-}"

python3 -m py_compile lib/activity_runtime.py \
  && ok "activity_runtime.py compiles" \
  || { fail "activity_runtime.py compile failed"; echo "PASS=$PASS FAIL=$FAIL"; exit 1; }

# ---- full happy path ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from activity_runtime import ActivityRuntime
from projection_engine import ProjectionEngine

sid = "sprint-art-happy"
rt = ActivityRuntime(sid, harness_dir=sys.argv[1])
rt.command_issued("act-1", actor="coordinator", target="builder", round_num=1)
rt.activity_started("act-1", actor="builder")
rt.activity_succeeded("act-1", actor="builder", payload={"files": ["x.py"]})

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "passed",     f"expected passed, got {state.status}"
assert len(state.activities) == 1
assert state.event_count == 3
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "command_issued → started → succeeded converges to passed" \
                      || fail "happy path: $OUT"

# ---- retry lifecycle ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from activity_runtime import ActivityRuntime
from projection_engine import ProjectionEngine

sid = "sprint-art-retry"
rt = ActivityRuntime(sid, harness_dir=sys.argv[1])
rt.command_issued("act-1", actor="coordinator", round_num=1)
rt.activity_started("act-1", actor="builder")
rt.activity_failed("act-1", actor="builder", error="compilation error")
rt.activity_retry_scheduled("act-1", actor="coordinator", retry_num=1)
rt.activity_started("act-1", actor="builder")
rt.activity_succeeded("act-1", actor="builder")

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "passed", f"expected passed after retry, got {state.status}"
act = state.activities[0]
assert act.error_count == 1, f"error_count={act.error_count}"
assert act.retry_count == 1, f"retry_count={act.retry_count}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "failed → retry_scheduled → started → succeeded converges to passed" \
                      || fail "retry lifecycle: $OUT"

# ---- cancellation lifecycle ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from activity_runtime import ActivityRuntime
from projection_engine import ProjectionEngine

sid = "sprint-art-cancel"
rt = ActivityRuntime(sid, harness_dir=sys.argv[1])
rt.command_issued("act-1", actor="coordinator", round_num=1)
rt.activity_cancelled("act-1", actor="coordinator", reason="user request")

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "cancelled", f"expected cancelled, got {state.status}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "command_issued → cancelled converges to cancelled" \
                      || fail "cancellation lifecycle: $OUT"

# ---- handoff lifecycle ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from activity_runtime import ActivityRuntime
from projection_engine import ProjectionEngine

sid = "sprint-art-handoff"
rt = ActivityRuntime(sid, harness_dir=sys.argv[1])
rt.command_issued("act-1", actor="coordinator", round_num=1)
rt.activity_started("act-1", actor="builder")
rt.activity_handoff("act-1", actor="builder", to_actor="evaluator", round_num=1)

eng = ProjectionEngine(sid, harness_dir=sys.argv[1])
state = eng.project()
assert state.status == "reviewing", f"expected reviewing, got {state.status}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "started → handoff converges to reviewing" \
                      || fail "handoff lifecycle: $OUT"

# ---- idempotent command_issued (at-least-once) ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from activity_runtime import ActivityRuntime
from session_log import SessionLog

sid = "sprint-art-idem"
rt = ActivityRuntime(sid, harness_dir=sys.argv[1])
# First dispatch
eid1 = rt.command_issued("act-1", actor="coordinator", round_num=1)
assert eid1, "first dispatch returned empty"
# At-least-once re-delivery
eid2 = rt.command_issued("act-1", actor="coordinator", round_num=1)
assert eid2 == "", f"duplicate dispatch should return '', got {eid2!r}"

log = SessionLog(sid, harness_dir=sys.argv[1])
cmds = list(log.replay(event_type="command_issued"))
assert len(cmds) == 1, f"expected 1 command_issued event, got {len(cmds)}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "duplicate command_issued suppressed by idempotency_key" \
                      || fail "command_issued idempotency: $OUT"

# ---- state_transition tracking ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from activity_runtime import ActivityRuntime
from session_log import SessionLog

sid = "sprint-art-state"
rt = ActivityRuntime(sid, harness_dir=sys.argv[1])
rt.state_transition(actor="coordinator", from_status="queued", to_status="active", round_num=1)
rt.state_transition(actor="coordinator", from_status="active", to_status="reviewing", round_num=1)

log = SessionLog(sid, harness_dir=sys.argv[1])
transitions = list(log.replay(event_type="state_transition"))
assert len(transitions) == 2, f"expected 2 transitions, got {len(transitions)}"
assert transitions[0]["payload"]["from"] == "queued"
assert transitions[1]["payload"]["to"] == "reviewing"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "state_transition events recorded with correct payload" \
                      || fail "state_transition: $OUT"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && echo "PASS" && exit 0 || { echo "FAIL"; exit 1; }
