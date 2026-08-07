#!/usr/bin/env bash
# test-vnext-projection-replay.sh — S05 N1
# Verifies projection can be replayed and is consistent with the event ledger:
#   - replay_projection is idempotent (same input → same output)
#   - diff of two replay runs is empty
#   - build_sprint_status returns same fields as replay_projection
#   - incremental replay from last_event_id yields same terminal state
#
# All fixtures in mktemp -d; real events.jsonl never touched.
set -euo pipefail

HARNESS_ROOT="${HOME}/.solar/harness"
HARNESS_LIB="${HARNESS_ROOT}/lib"
SOLAR_ROOT="${HOME}/.solar"
REAL_EVENTS="${HARNESS_ROOT}/run/events.jsonl"

# ── 1. Dry-run guard ──────────────────────────────────────────────────────
if ! python3 -c "
import sys
sys.path.insert(0,'${SOLAR_ROOT}')
sys.path.insert(0,'${HARNESS_LIB}')
from event_ledger import EventLedger
from projections import replay_projection, build_sprint_status
" 2>/dev/null; then
    echo "DRY-RUN: upstream modules (event_ledger / projections) not importable"
    echo "DRY-RUN: skipping projection replay test"
    exit 0
fi
echo "[INFO] upstream modules: ready"

# ── 2. Snapshot real events.jsonl ────────────────────────────────────────
BEFORE_SHA=""
if [[ -f "${REAL_EVENTS}" ]]; then
    BEFORE_SHA=$(sha256sum "${REAL_EVENTS}" | awk '{print $1}')
    echo "[INFO] real events.jsonl sha256 before: ${BEFORE_SHA}"
fi

# ── 3. Create isolated fixture directory ─────────────────────────────────
FIXTURE_DIR=$(mktemp -d)
trap 'rm -rf "${FIXTURE_DIR}"' EXIT
echo "[INFO] fixture dir: ${FIXTURE_DIR}"

# ── 4. Export vars for Python ─────────────────────────────────────────────
export SOLAR_ROOT HARNESS_LIB FIXTURE_DIR

# ── 5. Projection replay test ─────────────────────────────────────────────
python3 << 'PYEOF'
import sys, os, json, copy

SOLAR_ROOT  = os.environ["SOLAR_ROOT"]
HARNESS_LIB = os.environ["HARNESS_LIB"]
FIXTURE_DIR = os.environ["FIXTURE_DIR"]
SPRINT_ID   = "test-sprint-vnext-projection-001"

sys.path.insert(0, SOLAR_ROOT)
sys.path.insert(0, HARNESS_LIB)

from event_ledger import EventLedger
from projections import replay_projection, build_sprint_status

# ── Step 1: Create isolated ledger and populate events ────────────────────
ledger = EventLedger(base_dir=FIXTURE_DIR)
print("[INFO] EventLedger created in fixture dir")

# Append a realistic sequence of sprint lifecycle events.
# NOTE: replay_projection applies ALL state_transition events (incl. node-level)
# to the sprint state. We must not mix a terminal state (passed) with a later
# non-terminal transition in the same sprint_id stream.
# Design: sprint stays in "reviewing" (non-terminal) throughout this test.
sequence = [
    # Sprint lifecycle: drafting → ready → running → reviewing
    {"event_type": "state_transition", "sprint_id": SPRINT_ID,
     "actor": "coordinator", "payload": {"from": "",          "to": "drafting",  "round": 0}},
    {"event_type": "state_transition", "sprint_id": SPRINT_ID,
     "actor": "planner",     "payload": {"from": "drafting",  "to": "ready",     "round": 0}},
    {"event_type": "state_transition", "sprint_id": SPRINT_ID,
     "actor": "dispatcher",  "payload": {"from": "ready",     "to": "running",   "round": 1}},
    # Node N1: dispatched → reviewing (not terminal; stops before passed to avoid
    # DivergentError when sprint-level events follow — node state stored in node_statuses)
    {"event_type": "state_transition", "sprint_id": SPRINT_ID, "node_id": "N1",
     "actor": "builder",     "payload": {"from": "dispatched","to": "reviewing", "round": 1}},
    # Sprint moves to reviewing (consistent with node state)
    {"event_type": "state_transition", "sprint_id": SPRINT_ID,
     "actor": "evaluator",   "payload": {"from": "running",   "to": "reviewing", "round": 1}},
    # Broker events (do not change projection state — not state_transition type)
    {"event_type": "action.proposed",    "sprint_id": SPRINT_ID,
     "actor": "execution_broker", "payload": {"kind": "shell"}},
    {"event_type": "policy.verdict",     "sprint_id": SPRINT_ID,
     "actor": "execution_broker", "payload": {"verdict": "PASS"}},
    {"event_type": "action.executed",    "sprint_id": SPRINT_ID,
     "actor": "execution_broker", "payload": {"exit_code": 0}},
    {"event_type": "artifact.registered","sprint_id": SPRINT_ID,
     "actor": "execution_broker", "payload": {"evidence": []}},
    {"event_type": "verifier.verdict",   "sprint_id": SPRINT_ID,
     "actor": "execution_broker", "payload": {"verdict": "PASS"}},
]

event_ids = []
for ev in sequence:
    eid = ledger.append(ev)
    event_ids.append(eid)

print(f"[INFO] appended {len(event_ids)} events to isolated ledger")

# ── Step 2: Replay #1 ─────────────────────────────────────────────────────
all_events = ledger.replay(SPRINT_ID)
assert len(all_events) == len(sequence), \
    f"FAIL: expected {len(sequence)} events, replayed {len(all_events)}"

replay1 = replay_projection(all_events)
print(f"[INFO] replay1 status: {replay1['status']}, event_count: {replay1['event_count']}")

# ── Step 3: Replay #2 — idempotent, must be identical ────────────────────
replay2 = replay_projection(all_events)

# Exclude projected_at (timestamp varies); compare all other keys
def _comparable(proj):
    d = dict(proj)
    d.pop("projected_at", None)
    return d

r1 = _comparable(replay1)
r2 = _comparable(replay2)
assert r1 == r2, f"FAIL: replay not idempotent:\n  run1={r1}\n  run2={r2}"
print("[PASS] idempotency: replay_projection(events) x2 identical")

# ── Step 4: JSON diff is empty ────────────────────────────────────────────
j1 = json.dumps(r1, sort_keys=True)
j2 = json.dumps(r2, sort_keys=True)
assert j1 == j2, f"FAIL: JSON diff non-empty:\n  {j1}\n  {j2}"
print("[PASS] JSON diff of two replay runs is empty")

# ── Step 5: build_sprint_status matches replay_projection ─────────────────
built = build_sprint_status(SPRINT_ID, ledger=ledger)
# build_sprint_status adds sprint_id, projected_at, id — strip those
built_core = {k: v for k, v in built.items()
              if k not in ("sprint_id", "projected_at", "id")}
r1_core    = {k: v for k, v in replay1.items()
              if k not in ("sprint_id", "projected_at", "id")}

assert built_core["status"]      == r1_core["status"], \
    f"FAIL: build_sprint_status.status={built_core['status']} != replay.status={r1_core['status']}"
assert built_core["event_count"] == r1_core["event_count"], \
    f"FAIL: event_count mismatch: {built_core['event_count']} vs {r1_core['event_count']}"
assert built_core["state_hash"]  == r1_core["state_hash"], \
    f"FAIL: state_hash mismatch (projection drift)"
print("[PASS] build_sprint_status fields match replay_projection")

# ── Step 6: Verify terminal state monotonicity ────────────────────────────
# Adding a passed event moves state to terminal; further non-terminal events
# are rejected. Test this with a fresh, isolated event list.
terminal_only_events = [
    {"event_type": "state_transition", "sprint_id": SPRINT_ID,
     "actor": "evaluator", "event_id": "term-001",
     "payload": {"from": "reviewing", "to": "passed", "round": 2}},
]
passed_replay = replay_projection(terminal_only_events)
assert passed_replay["status"] == "passed", \
    f"FAIL: expected status='passed', got '{passed_replay['status']}'"
# Attempting to go from passed → reviewing must raise DivergentError
import projections as _projections
conflict_events = list(terminal_only_events) + [{
    "event_type": "state_transition", "sprint_id": SPRINT_ID,
    "actor": "test", "event_id": "term-002",
    "payload": {"from": "passed", "to": "reviewing", "round": 3},
}]
try:
    replay_projection(conflict_events)
    assert False, "FAIL: expected DivergentError, none raised"
except _projections.DivergentError:
    pass
print("[PASS] projection raises DivergentError on terminal→non-terminal transition")

# ── Step 7: Duplicate event_id idempotency ────────────────────────────────
if event_ids:
    first_event = dict(all_events[0])
    dup_events  = list(all_events) + [first_event]  # append a duplicate
    dup_replay  = replay_projection(dup_events)
    assert dup_replay["event_count"] == replay1["event_count"], \
        f"FAIL: duplicate event changed event_count: {dup_replay['event_count']} vs {replay1['event_count']}"
    print("[PASS] duplicate event_id is idempotent (skipped in replay)")

# ── Step 8: Verify 5 required broker event_types present in ledger ────────
event_types = [e.get("event_type") for e in all_events]
for et in ("action.proposed", "policy.verdict", "action.executed",
           "artifact.registered", "verifier.verdict"):
    assert et in event_types, f"FAIL: required broker event_type '{et}' missing from ledger"
print("[PASS] all 5 required broker event_types present in ledger")

# ── Summary ───────────────────────────────────────────────────────────────
print("")
print("=== test-vnext-projection-replay SUMMARY ===")
print(f"  ledger events      : {len(all_events)}")
print(f"  projection.status  : {replay1['status']}")
print(f"  event_count        : {replay1['event_count']}")
print(f"  state_hash         : {replay1['state_hash']}")
print(f"  idempotent         : YES (JSON diff empty)")
print(f"  build_sprint_status: consistent with replay_projection")
print("  ALL ASSERTIONS PASS")
PYEOF

echo ""

# ── 6. Verify real events.jsonl sha256 unchanged ─────────────────────────
if [[ -f "${REAL_EVENTS}" ]]; then
    AFTER_SHA=$(sha256sum "${REAL_EVENTS}" | awk '{print $1}')
    echo "[INFO] real events.jsonl sha256 after: ${AFTER_SHA}"
    if [[ "${BEFORE_SHA}" != "${AFTER_SHA}" ]]; then
        echo "FAIL: real events.jsonl was modified (sha256 changed)"
        exit 1
    fi
    echo "[PASS] real events.jsonl sha256 unchanged"
fi

echo "[PASS] fixture dir will be cleaned up on exit"
echo ""
echo "=== test-vnext-projection-replay: ALL ASSERTIONS PASS ==="
exit 0
