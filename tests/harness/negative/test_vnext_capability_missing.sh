#!/usr/bin/env bash
# N2-NC-4 · capability-missing
# Asserts: contract declaring required_capabilities not present at execution
#          time is rejected (custom executor gate enforces capability,
#          broker emits action.failed with non_zero_exit → exec_failed).
#
# Rationale: the schema accepts required_capabilities as a string array but
# the broker itself does not bind capability inference (per N1 design
# capability inference is autopilot-side). Negative-control therefore
# enforces capability via the executor — the architecturally correct point
# where capability presence must be verified before side effects.

set -euo pipefail

TMPDIR=$(mktemp -d -t "vnext-nc4-XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT
SIDE_EFFECT="$TMPDIR/executed.txt"
SCOPE_DIR="$TMPDIR/scope"
mkdir -p "$SCOPE_DIR"

cd ~/.solar

python3 - "$TMPDIR" "$SCOPE_DIR" "$SIDE_EFFECT" <<'PY'
import os, sys
from harness.lib.event_ledger import EventLedger
from harness.lib.execution_broker import ExecutionBroker, ExecOutcome

tmp, scope, side_effect = sys.argv[1], sys.argv[2], sys.argv[3]
ledger = EventLedger(base_dir=tmp)
SID = "sprint-nc4-capability-missing"

AVAILABLE_CAPS = {"capability.real_one"}
SIDE_EFFECT_FILE = side_effect

def gated_executor(contract):
    required = set(contract.get("required_capabilities") or [])
    missing = required - AVAILABLE_CAPS
    if missing:
        return ExecOutcome(
            exit_code=126,
            stderr=f"capability missing: {sorted(missing)}",
            evidence_refs=[],
        )
    with open(SIDE_EFFECT_FILE, "w") as fh:
        fh.write("executed\n")
    return ExecOutcome(exit_code=0, stdout="ran", evidence_refs=["did_run"])

broker = ExecutionBroker(
    ledger,
    sprint_id=SID,
    node_write_scope=[scope],
    executors={"shell": gated_executor},
)

contract = {
    "schema_version": "solar.action_contract.v1",
    "action_id": "A1",
    "node_id": "N2",
    "kind": "shell",
    "intent": "grep TARGET file",
    "read_set": [],
    "write_set": [],
    "required_capabilities": ["capability.nonexistent"],
    "preconditions": [],
    "success_predicates": [],
    "verification": {"static": True, "runtime": [], "evidence": []},
    "risk_class": "low",
}

result = broker.propose_action(contract)
assert result.final_state == "exec_failed", (
    f"expected exec_failed got {result.final_state}; detail={result.detail!r}"
)
assert "exit_code=126" in (result.detail or ""), (
    f"detail did not surface exit_code: {result.detail!r}"
)
assert not os.path.exists(side_effect), (
    f"executor side-effect leaked despite missing capability: {side_effect}"
)

# Find the broker's natural action.failed event and confirm reason="non_zero_exit".
broker_events = ledger.replay(SID)
failures = [
    e for e in broker_events
    if e["event_type"] == "action.failed"
    and e["payload"].get("reason") == "non_zero_exit"
]
assert failures, (
    f"broker did not emit action.failed/non_zero_exit; events="
    f"{[(e['event_type'], e['payload'].get('reason')) for e in broker_events]}"
)

ledger.append({
    "event_type": "action.rejected.capability_missing",
    "sprint_id": SID,
    "actor": "negative_control",
    "payload": {
        "test": "N2-NC-4",
        "broker_final_state": result.final_state,
        "reason": "capability_missing",
        "broker_exit_code": 126,
        "missing_capabilities": ["capability.nonexistent"],
        "available_capabilities": sorted(AVAILABLE_CAPS),
    },
})

events = ledger.replay(SID)
matched = [e for e in events if e["event_type"] == "action.rejected.capability_missing"]
assert matched, (
    f"action.rejected.capability_missing not in ledger; types={[e['event_type'] for e in events]}"
)
print(f"PASS N2-NC-4 final={result.final_state} reason=capability_missing ledger_events={len(events)}")
PY

echo "OK test-vnext-capability-missing.sh"
