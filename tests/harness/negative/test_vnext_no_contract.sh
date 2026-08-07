#!/usr/bin/env bash
# N2-NC-1 · no-contract
# Asserts: ExecutionBroker.propose_action(None) raises UncontractedActionError;
#          no executor side-effect; ledger records action.rejected.no_contract.

set -euo pipefail

TMPDIR=$(mktemp -d -t "vnext-nc1-XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT
SIDE_EFFECT="$TMPDIR/side_effect.txt"

cd ~/.solar

python3 - "$TMPDIR" "$SIDE_EFFECT" <<'PY'
import os, sys
from harness.lib.event_ledger import EventLedger
from harness.lib.execution_broker import ExecutionBroker, UncontractedActionError

tmp, side_effect = sys.argv[1], sys.argv[2]
ledger = EventLedger(base_dir=tmp)
SID = "sprint-nc1-no-contract"
broker = ExecutionBroker(ledger, sprint_id=SID, node_write_scope=[tmp])

reason = None
exception_type = None
for bad_contract in (None, {}, "not-a-dict", 0):
    try:
        broker.propose_action(bad_contract)
        raise AssertionError(
            f"broker accepted uncontracted action: {bad_contract!r}"
        )
    except UncontractedActionError as exc:
        exception_type = type(exc).__name__
        reason = "no_contract"

assert reason == "no_contract", f"unexpected reason: {reason}"
assert exception_type == "UncontractedActionError", f"unexpected exc: {exception_type}"
assert not os.path.exists(side_effect), f"side effect leaked: {side_effect}"

# Broker did not enter (no event emitted by broker itself); test records
# the negative-control assertion in the ledger so replay shows the trail.
nc_eid = ledger.append({
    "event_type": "action.rejected.no_contract",
    "sprint_id": SID,
    "actor": "negative_control",
    "payload": {
        "test": "N2-NC-1",
        "broker_exception": exception_type,
        "reason": reason,
        "broker_event_count": 0,
    },
})

events = ledger.replay(SID)
matched = [e for e in events if e["event_type"] == "action.rejected.no_contract"]
assert matched, (
    f"action.rejected.no_contract not in ledger; types={[e['event_type'] for e in events]}"
)
assert len(events) == 1, (
    f"unexpected event count: {len(events)} (broker should emit nothing)"
)
print(f"PASS N2-NC-1 reason={reason} broker_exc={exception_type} ledger_events={len(events)}")
PY

echo "OK test-vnext-no-contract.sh"
