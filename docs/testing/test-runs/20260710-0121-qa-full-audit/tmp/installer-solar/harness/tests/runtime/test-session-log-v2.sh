#!/usr/bin/env bash
# Session Log v2 — append / replay / idempotency tests
set -uo pipefail
cd "$(dirname "$0")/../.."
PASS=0; FAIL=0
ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

export PYTHONPATH="$PWD/lib:${PYTHONPATH:-}"

# ---- basic compile ----
python3 -m py_compile lib/session_log.py \
  && ok "session_log.py compiles" \
  || { fail "session_log.py compile failed"; echo "PASS=$PASS FAIL=$FAIL"; exit 1; }

# ---- append and replay ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys, os
sys.path.insert(0, 'lib')
from session_log import SessionLog

log = SessionLog("test-session-basic", harness_dir=sys.argv[1])
eid1 = log.append("command_issued", actor="coordinator",
                   sprint_id="sprint-test", activity_id="act-1",
                   payload={"target": "builder"})
eid2 = log.append("activity_started", actor="builder",
                   sprint_id="sprint-test", activity_id="act-1")
eid3 = log.append("activity_succeeded", actor="builder",
                   sprint_id="sprint-test", activity_id="act-1")

events = log.all_events()
assert len(events) == 3, f"expected 3 events, got {len(events)}"
seqs = [e["seq"] for e in events]
assert seqs == [1, 2, 3], f"bad seqs: {seqs}"
assert events[0]["event_id"] == eid1
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "append 3 events, replay returns correct seq" \
                      || fail "basic append/replay: $OUT"

# ---- idempotency key deduplication ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog, DuplicateEventError

log = SessionLog("test-session-idem", harness_dir=sys.argv[1])
log.append("command_issued", actor="coordinator",
            sprint_id="sprint-test", activity_id="act-1",
            idempotency_key="dispatch:sprint-test:round-1",
            payload={})
try:
    log.append("command_issued", actor="coordinator",
               sprint_id="sprint-test", activity_id="act-1",
               idempotency_key="dispatch:sprint-test:round-1",
               payload={})
    print("MISSING_ERROR")
except DuplicateEventError:
    print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "duplicate idempotency_key raises DuplicateEventError" \
                      || fail "idempotency dedup: $OUT"

# ---- at-least-once: second instance reads existing idem keys ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog, DuplicateEventError

# First instance appends one event
log1 = SessionLog("test-session-al1", harness_dir=sys.argv[1])
log1.append("command_issued", actor="coordinator",
            sprint_id="s", activity_id="a1",
            idempotency_key="k1", payload={})

# Second instance opens the same log
log2 = SessionLog("test-session-al1", harness_dir=sys.argv[1])
try:
    log2.append("command_issued", actor="coordinator",
               sprint_id="s", activity_id="a1",
               idempotency_key="k1", payload={})
    print("MISSING_ERROR")
except DuplicateEventError:
    print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "cross-process at-least-once: second instance rejects duplicate" \
                      || fail "cross-process idempotency: $OUT"

# ---- stale first instance: lock-time dedupe rejects keys written by sibling instance ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog, DuplicateEventError

log1 = SessionLog("test-session-stale-instance", harness_dir=sys.argv[1])
log2 = SessionLog("test-session-stale-instance", harness_dir=sys.argv[1])
log2.append("command_issued", actor="coordinator",
            sprint_id="s", activity_id="a1",
            idempotency_key="same-key", payload={})
try:
    log1.append("command_issued", actor="coordinator",
               sprint_id="s", activity_id="a1",
               idempotency_key="same-key", payload={})
    print("MISSING_ERROR")
except DuplicateEventError:
    events = log1.all_events()
    print("ok" if len(events) == 1 and [e["seq"] for e in events] == [1] else events)
PY
)
[[ "$OUT" == "ok" ]] && ok "lock-time idempotency rejects stale sibling duplicate" \
                      || fail "lock-time idempotency: $OUT"

# ---- replay filters ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog

log = SessionLog("test-session-filter", harness_dir=sys.argv[1])
log.append("command_issued",     actor="coordinator", sprint_id="s1", activity_id="a1", payload={})
log.append("activity_started",   actor="builder",     sprint_id="s1", activity_id="a1", payload={})
log.append("command_issued",     actor="coordinator", sprint_id="s2", activity_id="a2", payload={})

by_sprint = list(log.replay(sprint_id="s1"))
assert len(by_sprint) == 2, f"expected 2 for s1, got {len(by_sprint)}"

by_type = list(log.replay(event_type="command_issued"))
assert len(by_type) == 2, f"expected 2 command_issued, got {len(by_type)}"

by_act = list(log.replay(activity_id="a2"))
assert len(by_act) == 1, f"expected 1 for a2, got {len(by_act)}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "replay filters: sprint_id / event_type / activity_id" \
                      || fail "replay filters: $OUT"

# ---- invalid event type ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog

log = SessionLog("test-session-invalid", harness_dir=sys.argv[1])
try:
    log.append("NOT_A_VALID_TYPE", actor="x", payload={})
    print("MISSING_ERROR")
except ValueError:
    print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "invalid event type raises ValueError" \
                      || fail "invalid event type: $OUT"

# ---- monotonic seq across restarts ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog

log1 = SessionLog("test-session-mono", harness_dir=sys.argv[1])
log1.append("command_issued", actor="coordinator", sprint_id="s", payload={})
log1.append("activity_started", actor="builder",  sprint_id="s", payload={})

log2 = SessionLog("test-session-mono", harness_dir=sys.argv[1])
log2.append("activity_succeeded", actor="builder", sprint_id="s", payload={})

events = log2.all_events()
seqs = [e["seq"] for e in events]
assert seqs == [1, 2, 3], f"seqs not monotonic after restart: {seqs}"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "monotonic seq preserved across log re-open" \
                      || fail "monotonic seq: $OUT"

# ---- for_sprint classmethod ----
OUT=$(python3 - "$TMP_DIR" <<'PY'
import sys
sys.path.insert(0, 'lib')
from session_log import SessionLog

log = SessionLog.for_sprint("sprint-test-cm", harness_dir=sys.argv[1])
log.append("log_message", actor="coordinator", sprint_id="sprint-test-cm", payload={"msg": "hi"})
events = log.all_events()
assert len(events) == 1
assert events[0]["sprint_id"] == "sprint-test-cm"
print("ok")
PY
)
[[ "$OUT" == "ok" ]] && ok "SessionLog.for_sprint classmethod works" \
                      || fail "for_sprint classmethod: $OUT"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && echo "PASS" && exit 0 || { echo "FAIL"; exit 1; }
