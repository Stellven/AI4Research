#!/usr/bin/env bash
# N2-NC-5 · approval-required
# Asserts: high-risk contract is rejected when broker.approvals does not
#          contain the action_id (policy_denied via approval_policy.check).
# Also asserts: the same contract PASSES policy when approvals=[action_id]
#               (positive control proves the gate, not a tautology).

set -euo pipefail

TMPDIR=$(mktemp -d -t "vnext-nc5-XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT
SCOPE_DIR="$TMPDIR/scope"
SIDE_EFFECT="$SCOPE_DIR/touched.txt"
mkdir -p "$SCOPE_DIR"

cd ~/.solar

python3 - "$TMPDIR" "$SCOPE_DIR" "$SIDE_EFFECT" <<'PY'
import os, sys
from harness.lib.event_ledger import EventLedger
from harness.lib.execution_broker import ExecutionBroker, ExecOutcome

tmp, scope, side_effect = sys.argv[1], sys.argv[2], sys.argv[3]
ledger = EventLedger(base_dir=tmp)
SID = "sprint-nc5-approval-required"

def touch_executor(c):
    with open(side_effect, "w") as fh:
        fh.write("ran\n")
    return ExecOutcome(exit_code=0, stdout="touched", evidence_refs=["e1"])

broker_denied = ExecutionBroker(
    ledger,
    sprint_id=SID,
    node_write_scope=[scope],
    executors={"shell": touch_executor},
    approvals=[],
)

contract = {
    "schema_version": "solar.action_contract.v1",
    "action_id": "A1",
    "node_id": "N2",
    "kind": "shell",
    "intent": "apply patch foo.diff",
    "read_set": [],
    "write_set": [],
    "required_capabilities": [],
    "preconditions": [],
    "success_predicates": [],
    "verification": {"static": True, "runtime": [], "evidence": []},
    "risk_class": "high",
}

result = broker_denied.propose_action(contract)
assert result.final_state == "policy_denied", (
    f"expected policy_denied got {result.final_state}; detail={result.detail!r}"
)
assert "approval required" in (result.detail or "").lower(), (
    f"detail did not mention approval: {result.detail!r}"
)
assert not os.path.exists(side_effect), (
    f"executor side-effect leaked despite missing approval: {side_effect}"
)

# Positive-control proves the gate works in BOTH directions.
broker_ok = ExecutionBroker(
    ledger,
    sprint_id=SID + "-approved",
    node_write_scope=[scope],
    executors={"shell": touch_executor},
    approvals=["A1"],
)
ok_result = broker_ok.propose_action(contract)
assert ok_result.final_state == "committed", (
    f"approved high-risk action did NOT pass; final={ok_result.final_state}"
)
assert os.path.exists(side_effect), "approved executor did not run"
os.remove(side_effect)

ledger.append({
    "event_type": "action.rejected.approval_required",
    "sprint_id": SID,
    "actor": "negative_control",
    "payload": {
        "test": "N2-NC-5",
        "broker_final_state": result.final_state,
        "reason": result.reason,
        "detail": result.detail,
        "risk_class": "high",
        "positive_control": {"final_state": ok_result.final_state, "approvals": ["A1"]},
    },
})

events = ledger.replay(SID)
matched = [e for e in events if e["event_type"] == "action.rejected.approval_required"]
assert matched, (
    f"action.rejected.approval_required not in ledger; types={[e['event_type'] for e in events]}"
)
print(f"PASS N2-NC-5 final={result.final_state} reason={result.reason} ledger_events={len(events)}")
PY

echo "OK test-vnext-approval-required.sh"
