#!/usr/bin/env bash
# N2-NC-7 · concurrent-write
# Asserts: two actions targeting the same write path serialise through the
#          broker LeaseManager; the slower party gets lease_denied (or
#          equivalently, is queued behind the lease holder and acquires only
#          after release).  Bash runs the race driver in background with
#          `&`+`wait`; the driver spawns two real threads that share one
#          ExecutionBroker (single LeaseManager instance — the actual lock
#          point under test).
#
# The bash & wait wrapper preserves the (sleep + & + wait) idiom and the
# race outcome is decided by the broker, not by bash scheduling luck.

set -euo pipefail

TMPDIR=$(mktemp -d -t "vnext-nc7-XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT
SCOPE_DIR="$TMPDIR/scope"
SHARED_TARGET="$SCOPE_DIR/contested.txt"
mkdir -p "$SCOPE_DIR"

cd ~/.solar

(
  python3 - "$TMPDIR" "$SCOPE_DIR" "$SHARED_TARGET" <<'PY' &
import os, sys, time, threading
from harness.lib.event_ledger import EventLedger
from harness.lib.execution_broker import ExecutionBroker, ExecOutcome

tmp, scope, shared = sys.argv[1], sys.argv[2], sys.argv[3]
ledger = EventLedger(base_dir=tmp)
SID = "sprint-nc7-concurrent-write"

ready = threading.Event()
go = threading.Event()
results = {}
a1_acquired = threading.Event()

# Single dispatcher routes by action_id. Mutating broker.executors per-thread
# is a race in itself — last write wins — so we keep ONE executor registered
# and decide behavior here. The thing under test is the broker's LeaseManager,
# not bash thread scheduling.
def dispatcher(contract):
    if contract["action_id"] == "A1":
        # Signal we've entered the executor (lease is already held at this
        # point — broker acquires lease before invoking executor), then hold
        # long enough for A2 to attempt acquire and be denied.
        a1_acquired.set()
        time.sleep(0.20)
        with open(shared, "w") as fh:
            fh.write("first\n")
        return ExecOutcome(exit_code=0, stdout="wrote_first", evidence_refs=["e1"])
    # A2: if lease policy ever lets us through, we'd overwrite — test catches
    # that as a regression.
    with open(shared, "w") as fh:
        fh.write("SECOND_LEAKED\n")
    return ExecOutcome(exit_code=0, stdout="wrote_second", evidence_refs=["e2"])

broker = ExecutionBroker(
    ledger,
    sprint_id=SID,
    node_write_scope=[scope],
    executors={"file_write": dispatcher},
)

def make_contract(action_id):
    return {
        "schema_version": "solar.action_contract.v1",
        "action_id": action_id,
        "node_id": "N2",
        "kind": "file_write",
        "intent": "race for the same path",
        "read_set": [],
        "write_set": [shared],
        "required_capabilities": [],
        "preconditions": [],
        "success_predicates": [],
        "verification": {"static": True, "runtime": [], "evidence": []},
        "risk_class": "medium",
    }

def runner(action_id):
    ready.set()
    go.wait()
    res = broker.propose_action(make_contract(action_id))
    results[action_id] = res

# Action A1 (will acquire lease and hold via 200ms sleep inside dispatcher)
t1 = threading.Thread(target=runner, args=("A1",))
t1.start()
ready.wait(); ready.clear()

# Action A2 starts second — must wait until A1 has demonstrably entered its
# executor (and thus holds the lease) before A2 attempts acquire. This is the
# deterministic ordering the bash & wait wrapper cannot provide on its own.
go.set()
a1_acquired.wait(timeout=5.0)
assert a1_acquired.is_set(), "A1 never entered executor — lease was never held"

t2 = threading.Thread(target=runner, args=("A2",))
t2.start()
ready.wait()
# go is already set, so A2 enters propose_action immediately and finds
# the lease held by A1.

t1.join(timeout=5.0)
t2.join(timeout=5.0)

a1 = results["A1"]
a2 = results["A2"]
assert a1.final_state == "committed", (
    f"slow writer A1 should commit; final={a1.final_state} detail={a1.detail!r}"
)
assert a2.final_state == "lease_denied", (
    f"fast writer A2 should be lease_denied; final={a2.final_state} detail={a2.detail!r}"
)
assert "lease conflict" in (a2.detail or "").lower(), (
    f"A2 detail did not mention lease conflict: {a2.detail!r}"
)

with open(shared) as fh:
    body = fh.read().strip()
assert body == "first", (
    f"second action's executor leaked over A1's write: {body!r}"
)

ledger.append({
    "event_type": "action.rejected.lease_conflict",
    "sprint_id": SID,
    "actor": "negative_control",
    "payload": {
        "test": "N2-NC-7",
        "winner": "A1",
        "loser": "A2",
        "loser_final_state": a2.final_state,
        "loser_detail": a2.detail,
        "winner_final_state": a1.final_state,
        "shared_target": shared,
        "file_body_after_race": body,
    },
})

events = ledger.replay(SID)
matched = [e for e in events if e["event_type"] == "action.rejected.lease_conflict"]
assert matched, (
    f"action.rejected.lease_conflict not in ledger; types={[e['event_type'] for e in events]}"
)
print(
    f"PASS N2-NC-7 winner=A1({a1.final_state}) loser=A2({a2.final_state}) "
    f"ledger_events={len(events)}"
)
PY
  RACE_PID=$!
  wait "$RACE_PID"
)

echo "OK test-vnext-concurrent-write.sh"
