#!/usr/bin/env bash
# N2-NC-3 · scope-violation
# Asserts: contract write_set path outside node_write_scope is denied
#          (policy_denied via write_scope_policy "not in node write_scope").

set -euo pipefail

TMPDIR=$(mktemp -d -t "vnext-nc3-XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT
ALLOWED_DIR="$TMPDIR/allowed"
FORBIDDEN_TARGET="$TMPDIR/forbidden/leak.txt"
mkdir -p "$ALLOWED_DIR"

cd ~/.solar

python3 - "$TMPDIR" "$ALLOWED_DIR" "$FORBIDDEN_TARGET" <<'PY'
import os, sys
from harness.lib.event_ledger import EventLedger
from harness.lib.execution_broker import ExecutionBroker

tmp, allowed_dir, forbidden = sys.argv[1], sys.argv[2], sys.argv[3]
ledger = EventLedger(base_dir=tmp)
SID = "sprint-nc3-scope-violation"

# Broker only allows writes under allowed_dir/.
broker = ExecutionBroker(
    ledger,
    sprint_id=SID,
    node_write_scope=[allowed_dir],
    executors={
        "file_write": lambda c: (_ for _ in ()).throw(
            AssertionError("executor must not run on scope violation")
        ),
    },
)

contract = {
    "schema_version": "solar.action_contract.v1",
    "action_id": "A1",
    "node_id": "N2",
    "kind": "file_write",
    "intent": "attempt to write outside scope",
    "read_set": [],
    "write_set": [forbidden],
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
assert "not in node write_scope" in (result.detail or ""), (
    f"detail did not mention scope mismatch: {result.detail!r}"
)
assert not os.path.exists(forbidden), f"forbidden path leaked: {forbidden}"
assert not os.path.exists(os.path.dirname(forbidden)) or os.listdir(
    os.path.dirname(forbidden)
) == [], "forbidden directory should be empty (no executor side effect)"

ledger.append({
    "event_type": "action.rejected.scope_violation",
    "sprint_id": SID,
    "actor": "negative_control",
    "payload": {
        "test": "N2-NC-3",
        "broker_final_state": result.final_state,
        "reason": result.reason,
        "detail": result.detail,
        "attempted_path": forbidden,
        "allowed_scope": [allowed_dir],
    },
})

events = ledger.replay(SID)
matched = [e for e in events if e["event_type"] == "action.rejected.scope_violation"]
assert matched, (
    f"action.rejected.scope_violation not in ledger; types={[e['event_type'] for e in events]}"
)
print(f"PASS N2-NC-3 final={result.final_state} reason={result.reason} ledger_events={len(events)}")
PY

echo "OK test-vnext-scope-violation.sh"
