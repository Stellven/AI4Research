#!/usr/bin/env bash
# N2-NC-2 · no-write-scope
# Asserts: contract requesting writes is rejected when broker is constructed
#          with empty node_write_scope (policy_denied via write_scope_policy).

set -euo pipefail

TMPDIR=$(mktemp -d -t "vnext-nc2-XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT
SIDE_EFFECT="$TMPDIR/side_effect.txt"

cd ~/.solar

python3 - "$TMPDIR" "$SIDE_EFFECT" <<'PY'
import os, sys
from harness.lib.event_ledger import EventLedger
from harness.lib.execution_broker import ExecutionBroker, ExecOutcome

tmp, side_effect = sys.argv[1], sys.argv[2]
ledger = EventLedger(base_dir=tmp)
SID = "sprint-nc2-no-write-scope"

# Broker has empty node_write_scope → any non-empty write_set must be denied.
broker = ExecutionBroker(
    ledger,
    sprint_id=SID,
    node_write_scope=[],
    executors={
        "file_write": lambda c: (_ for _ in ()).throw(
            AssertionError("executor must not run when policy denies")
        ),
    },
)

contract = {
    "schema_version": "solar.action_contract.v1",
    "action_id": "A1",
    "node_id": "N2",
    "kind": "file_write",
    "intent": "write side effect file",
    "read_set": [],
    "write_set": [side_effect],
    "required_capabilities": [],
    "preconditions": [],
    "success_predicates": [],
    "verification": {"static": True, "runtime": [], "evidence": []},
    "risk_class": "medium",
}

result = broker.propose_action(contract)
assert result.final_state == "policy_denied", (
    f"expected policy_denied got {result.final_state}; detail={result.detail!r}"
)
assert result.reason == "policy_denied", f"unexpected reason: {result.reason!r}"
assert "node_write_scope is empty" in (result.detail or ""), (
    f"detail did not mention empty scope: {result.detail!r}"
)
assert not os.path.exists(side_effect), f"side effect leaked: {side_effect}"

# Record the structured negative-control assertion event.
ledger.append({
    "event_type": "action.rejected.no_write_scope",
    "sprint_id": SID,
    "actor": "negative_control",
    "payload": {
        "test": "N2-NC-2",
        "broker_final_state": result.final_state,
        "reason": result.reason,
        "detail": result.detail,
        "broker_event_count": len(result.events),
    },
})

events = ledger.replay(SID)
matched = [e for e in events if e["event_type"] == "action.rejected.no_write_scope"]
assert matched, (
    f"action.rejected.no_write_scope not in ledger; types={[e['event_type'] for e in events]}"
)
# Broker itself emits: proposed → validated → policy_denied  (3 events)
# Plus the NC marker = 4 total.
assert len(events) == 4, f"unexpected event count: {len(events)}"
print(f"PASS N2-NC-2 final={result.final_state} reason={result.reason} ledger_events={len(events)}")
PY

echo "OK test-vnext-no-write-scope.sh"
