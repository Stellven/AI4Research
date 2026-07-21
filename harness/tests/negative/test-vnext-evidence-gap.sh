#!/usr/bin/env bash
# N2-NC-6 · evidence-gap
# Asserts: a verifier that requires evidence_refs returns FAIL when the
#          executor produced zero evidence, and the broker transitions
#          to verify_failed (not committed). No artifact may be registered.

set -euo pipefail

TMPDIR=$(mktemp -d -t "vnext-nc6-XXXXXX")
trap 'rm -rf "$TMPDIR"' EXIT
SCOPE_DIR="$TMPDIR/scope"
SIDE_EFFECT="$SCOPE_DIR/written.txt"
mkdir -p "$SCOPE_DIR"

cd ~/.solar

python3 - "$TMPDIR" "$SCOPE_DIR" "$SIDE_EFFECT" <<'PY'
import os, sys
from harness.lib.event_ledger import EventLedger
from harness.lib.execution_broker import ExecutionBroker, ExecOutcome, VerifierResult

tmp, scope, side_effect = sys.argv[1], sys.argv[2], sys.argv[3]
ledger = EventLedger(base_dir=tmp)
SID = "sprint-nc6-evidence-gap"

# Executor "succeeds" (exit 0) but produces NO evidence_refs. The verifier
# must catch this gap and return FAIL.
def empty_evidence_executor(c):
    with open(side_effect, "w") as fh:
        fh.write("temp\n")
    return ExecOutcome(exit_code=0, stdout="ran", evidence_refs=[])

def strict_verifier(action_id, contract, outcome):
    if not outcome.evidence_refs:
        return VerifierResult(
            verdict="FAIL",
            can_rollback=True,
            evidence=[],
            detail="verifier requires non-empty evidence_refs",
        )
    return VerifierResult(verdict="PASS", evidence=outcome.evidence_refs)

broker = ExecutionBroker(
    ledger,
    sprint_id=SID,
    node_write_scope=[scope],
    executors={"shell": empty_evidence_executor},
    verifier=strict_verifier,
)

contract = {
    "schema_version": "solar.action_contract.v1",
    "action_id": "A1",
    "node_id": "N2",
    "kind": "shell",
    "intent": "grep foo bar.log",
    "read_set": [],
    "write_set": [],
    "required_capabilities": [],
    "preconditions": [],
    "success_predicates": [],
    "verification": {"static": True, "runtime": [], "evidence": ["non-empty"]},
    "risk_class": "low",
    "rollback": {"kind": "file_delete", "target": [side_effect]},
}

result = broker.propose_action(contract)
assert result.final_state == "verify_failed", (
    f"expected verify_failed got {result.final_state}; detail={result.detail!r}"
)
assert "evidence_refs" in (result.detail or ""), (
    f"detail did not mention evidence_refs: {result.detail!r}"
)

# Broker must NOT have emitted artifact.registered for this action.
broker_events = ledger.replay(SID)
registered = [
    e for e in broker_events
    if e["event_type"] == "artifact.registered"
    and e["payload"].get("action_id") == "A1"
]
assert not registered, (
    f"artifact.registered leaked despite verify_failed: {registered}"
)

# Verifier-as-rollback is declared; the broker should have emitted
# rollback.invoked because rollback.kind=file_delete is supported.
rollback_events = [e for e in broker_events if e["event_type"] == "rollback.invoked"]
assert rollback_events, (
    f"rollback.invoked not emitted; types={[e['event_type'] for e in broker_events]}"
)

ledger.append({
    "event_type": "action.rejected.evidence_gap",
    "sprint_id": SID,
    "actor": "negative_control",
    "payload": {
        "test": "N2-NC-6",
        "broker_final_state": result.final_state,
        "reason": result.reason,
        "detail": result.detail,
        "rollback_triggered": True,
    },
})

events = ledger.replay(SID)
matched = [e for e in events if e["event_type"] == "action.rejected.evidence_gap"]
assert matched, (
    f"action.rejected.evidence_gap not in ledger; types={[e['event_type'] for e in events]}"
)
print(f"PASS N2-NC-6 final={result.final_state} reason={result.reason} ledger_events={len(events)}")
PY

echo "OK test-vnext-evidence-gap.sh"
