"""N3 acceptance tests for harness/lib/execution_broker.py.

Coverage targets (per N3-dispatch.md Acceptance):
- ExecutionBroker.propose_action drives the full chain.
- All 12 acceptance-named states emitted at least once across the suite:
  proposed, validated, policy_passed, leased, executing, verified, committed,
  schema_failed, policy_denied, lease_denied, exec_failed, verify_failed.
- shell / file_write / tool_call each exercised end-to-end.
- Uncontracted action raises UncontractedActionError.
- Low-risk shell action commits cleanly through the full chain.
- Each transition produces a ledger event (one event per history entry minimum).
- pytest + py_compile.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from execution_broker import (
    ALL_STATES,
    ActionResult,
    ExecOutcome,
    ExecutionBroker,
    LeaseManager,
    SCHEMA_VERSION,
    UncontractedActionError,
    VerifierResult,
)
from event_ledger import EventLedger


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger(tmp_path):
    return EventLedger(base_dir=str(tmp_path / "ledger"))


def make_contract(**overrides) -> Dict:
    base = {
        "schema_version": SCHEMA_VERSION,
        "action_id": "A1",
        "node_id": "N1",
        "kind": "shell",
        "intent": "grep TODO src/main.py",
        "read_set": [],
        "write_set": [],
        "required_capabilities": [],
        "preconditions": [],
        "success_predicates": [],
        "verification": {"static": True, "runtime": [], "evidence": []},
        "risk_class": "low",
        "approval_required": False,
        "rollback": {"kind": "none", "target": []},
    }
    base.update(overrides)
    return base


def make_broker(ledger, *, node_write_scope=None, **kwargs):
    return ExecutionBroker(
        ledger,
        sprint_id="sprint-test",
        node_write_scope=node_write_scope if node_write_scope is not None
        else ["harness/lib/policy", "harness/tests"],
        **kwargs,
    )


def ok_executor(_):
    return ExecOutcome(exit_code=0, stdout="ok", evidence_refs=["test:ok"])


def states_emitted(result: ActionResult) -> List[str]:
    return list(result.history)


# ---------------------------------------------------------------------------
# Structural / metadata
# ---------------------------------------------------------------------------


def test_production_package_import_works():
    from harness.lib.execution_broker import ExecutionBroker as PackageBroker

    assert PackageBroker is not None


def test_all_states_enumerated():
    # 7 happy + 5 fail = 12 acceptance-named states; covers the S02 §2.2
    # 11-state FSM plus the explicit `verify_failed` terminal called out in
    # design.md §7.
    assert len(ALL_STATES) == 12
    for s in (
        "proposed", "validated", "policy_passed", "leased",
        "executing", "verified", "committed",
        "schema_failed", "policy_denied", "lease_denied",
        "exec_failed", "verify_failed",
    ):
        assert s in ALL_STATES, s


# ---------------------------------------------------------------------------
# Uncontracted action
# ---------------------------------------------------------------------------


def test_uncontracted_action_raises_none(ledger):
    broker = make_broker(ledger)
    with pytest.raises(UncontractedActionError):
        broker.propose_action(None)


def test_uncontracted_action_raises_empty(ledger):
    broker = make_broker(ledger)
    with pytest.raises(UncontractedActionError):
        broker.propose_action({})


def test_uncontracted_action_raises_non_dict(ledger):
    broker = make_broker(ledger)
    with pytest.raises(UncontractedActionError):
        broker.propose_action("not a contract")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Schema validation → schema_failed
# ---------------------------------------------------------------------------


def test_schema_missing_field_yields_schema_failed(ledger):
    broker = make_broker(ledger)
    c = make_contract()
    c.pop("verification")
    result = broker.propose_action(c)
    assert result.final_state == "schema_failed"
    assert "proposed" in result.history
    assert "schema_failed" in result.history
    assert result.reason == "schema_failed"


def test_schema_unsupported_kind_yields_schema_failed(ledger):
    broker = make_broker(ledger)
    result = broker.propose_action(make_contract(kind="telepathy"))
    assert result.final_state == "schema_failed"


def test_schema_bad_risk_class_yields_schema_failed(ledger):
    broker = make_broker(ledger)
    result = broker.propose_action(make_contract(risk_class="catastrophic"))
    assert result.final_state == "schema_failed"


def test_schema_bad_version_yields_schema_failed(ledger):
    broker = make_broker(ledger)
    result = broker.propose_action(make_contract(schema_version="v0.9"))
    assert result.final_state == "schema_failed"


# ---------------------------------------------------------------------------
# Policy → policy_denied
# ---------------------------------------------------------------------------


def test_unscoped_write_yields_policy_denied(ledger):
    broker = make_broker(ledger, node_write_scope=["harness/lib/policy"])
    c = make_contract(
        kind="file_write",
        write_set=["/etc/passwd"],
        risk_class="medium",
    )
    result = broker.propose_action(c)
    assert result.final_state == "policy_denied"
    assert "validated" in result.history
    assert "policy_denied" in result.history


def test_high_risk_without_approval_yields_policy_denied(ledger):
    broker = make_broker(ledger)
    c = make_contract(risk_class="high")
    result = broker.propose_action(c)
    assert result.final_state == "policy_denied"
    assert "approval required" in (result.detail or "").lower()


def test_high_risk_with_approval_passes_policy(ledger):
    broker = make_broker(ledger, approvals=["A1"],
                         executors={"shell": ok_executor})
    c = make_contract(risk_class="high")
    result = broker.propose_action(c)
    assert result.final_state == "committed"
    assert "policy_passed" in result.history


# ---------------------------------------------------------------------------
# Lease → lease_denied
# ---------------------------------------------------------------------------


def test_lease_conflict_yields_lease_denied(ledger):
    shared_lease = LeaseManager()
    broker = make_broker(ledger, lease=shared_lease,
                         node_write_scope=["harness/lib/policy"],
                         executors={"file_write": ok_executor})

    first = broker.propose_action(make_contract(
        action_id="A1",
        kind="file_write",
        write_set=["harness/lib/policy/action_policy.py"],
        risk_class="medium",
        verification={"static": True, "runtime": [], "evidence": []},
    ))
    assert first.final_state == "committed"

    # Hold the lease manually to simulate concurrent action
    shared_lease.acquire("OTHER", ["harness/lib/policy/__init__.py"])

    second = broker.propose_action(make_contract(
        action_id="A2",
        kind="file_write",
        write_set=["harness/lib/policy/__init__.py"],
        risk_class="medium",
    ))
    assert second.final_state == "lease_denied"
    assert "lease_denied" in second.history


# ---------------------------------------------------------------------------
# Execute → exec_failed
# ---------------------------------------------------------------------------


def test_executor_non_zero_yields_exec_failed(ledger):
    def failing_shell(_):
        return ExecOutcome(exit_code=2, stderr="boom")

    broker = make_broker(ledger, executors={"shell": failing_shell})
    result = broker.propose_action(make_contract())
    assert result.final_state == "exec_failed"
    assert "leased" in result.history
    assert "exec_failed" in result.history


def test_executor_crash_yields_exec_failed(ledger):
    def crashing_shell(_):
        raise RuntimeError("sandbox died")

    broker = make_broker(ledger, executors={"shell": crashing_shell})
    result = broker.propose_action(make_contract())
    assert result.final_state == "exec_failed"
    assert "sandbox died" in (result.detail or "")


# ---------------------------------------------------------------------------
# Verify → verify_failed (+ reverted via rollback payload)
# ---------------------------------------------------------------------------


def test_verifier_fail_no_rollback_yields_verify_failed(ledger):
    def passing_shell(_):
        return ExecOutcome(exit_code=0, stdout="ok")

    def failing_verifier(_aid, _c, _o):
        return VerifierResult(verdict="FAIL", detail="expected output not present")

    broker = make_broker(
        ledger,
        executors={"shell": passing_shell},
        verifier=failing_verifier,
    )
    result = broker.propose_action(make_contract())
    assert result.final_state == "verify_failed"
    assert "executing" in result.history
    assert "verify_failed" in result.history
    assert result.reason == "verify_failed"


def test_verifier_fail_with_rollback_emits_rollback_invoked(ledger):
    def passing_shell(_):
        return ExecOutcome(exit_code=0)

    def failing_verifier(_aid, _c, _o):
        return VerifierResult(verdict="FAIL", can_rollback=True)

    broker = make_broker(
        ledger,
        executors={"shell": passing_shell},
        verifier=failing_verifier,
    )
    c = make_contract(rollback={"kind": "git_restore",
                                "target": ["harness/lib/policy/action_policy.py"]})
    result = broker.propose_action(c)
    assert result.final_state == "verify_failed"

    events = ledger.replay("sprint-test")
    types = [e["event_type"] for e in events]
    assert "rollback.invoked" in types


# ---------------------------------------------------------------------------
# Full happy-path chain — shell / file_write / tool_call
# ---------------------------------------------------------------------------


def test_low_risk_shell_commits_full_chain(ledger):
    """Acceptance: low-risk shell complete chain → committed."""
    def shell_executor(_):
        return ExecOutcome(exit_code=0, stdout="ok",
                           evidence_refs=["log:/tmp/out.txt"])

    broker = make_broker(ledger, executors={"shell": shell_executor})
    result = broker.propose_action(make_contract())
    assert result.final_state == "committed"
    expected = ["proposed", "validated", "policy_passed", "leased",
                "executing", "executing", "verified", "verified",
                "committed", "committed"]
    # 'executing' & 'verified' appear twice (state entry + sub-event)
    for state in ("proposed", "validated", "policy_passed", "leased",
                  "executing", "verified", "committed"):
        assert state in result.history, state


def test_file_write_action_commits(ledger):
    def fw_executor(_):
        return ExecOutcome(exit_code=0, evidence_refs=["fs:harness/lib/policy/__init__.py"])

    broker = make_broker(
        ledger,
        executors={"file_write": fw_executor},
        node_write_scope=["harness/lib/policy"],
    )
    c = make_contract(
        kind="file_write",
        write_set=["harness/lib/policy/__init__.py"],
        risk_class="medium",
    )
    result = broker.propose_action(c)
    assert result.final_state == "committed"


def test_tool_call_action_commits(ledger):
    def tc_executor(_):
        return ExecOutcome(exit_code=0, evidence_refs=["tool:resp"])

    broker = make_broker(ledger, executors={"tool_call": tc_executor})
    c = make_contract(kind="tool_call", risk_class="medium",
                      intent="mcp__filesystem__read")
    result = broker.propose_action(c)
    assert result.final_state == "committed"


# ---------------------------------------------------------------------------
# Ledger event coverage
# ---------------------------------------------------------------------------


def test_every_transition_emits_event(ledger):
    def shell_executor(_):
        return ExecOutcome(exit_code=0)

    broker = make_broker(ledger, executors={"shell": shell_executor})
    result = broker.propose_action(make_contract())
    events = ledger.replay("sprint-test")

    # Each history entry has a corresponding event_id recorded in the result.
    assert len(result.events) == len(result.history)
    assert len(events) == len(result.events)

    types = [e["event_type"] for e in events]
    for required in ("action.proposed",
                     "broker.state",
                     "policy.verdict",
                     "lease.acquired",
                     "action.executed",
                     "verifier.invoked",
                     "verifier.verdict",
                     "artifact.registered",
                     "projection.updated"):
        assert required in types, f"missing event_type: {required}"


def test_event_payloads_carry_action_id(ledger):
    broker = make_broker(ledger, executors={"shell": ok_executor})
    broker.propose_action(make_contract(action_id="A42"))
    events = ledger.replay("sprint-test")
    for ev in events:
        assert ev["payload"].get("action_id") == "A42", ev


def test_ledger_records_distinct_event_ids(ledger):
    def shell_executor(_):
        return ExecOutcome(exit_code=0)

    broker = make_broker(ledger, executors={"shell": shell_executor})
    result = broker.propose_action(make_contract())
    assert len(result.events) == len(set(result.events)), "event_ids must be unique"


# ---------------------------------------------------------------------------
# Lease release on terminal
# ---------------------------------------------------------------------------


def test_lease_released_after_commit(ledger):
    def fw_executor(_):
        return ExecOutcome(exit_code=0)

    lease = LeaseManager()
    broker = make_broker(
        ledger,
        executors={"file_write": fw_executor},
        lease=lease,
        node_write_scope=["harness/lib/policy"],
    )
    broker.propose_action(make_contract(
        kind="file_write",
        write_set=["harness/lib/policy/__init__.py"],
        risk_class="medium",
    ))
    assert lease.held() == {}, "committed action must release lease"


def test_lease_released_after_verify_failed(ledger):
    def fw_executor(_):
        return ExecOutcome(exit_code=0)

    def failing_verifier(_a, _c, _o):
        return VerifierResult(verdict="FAIL")

    lease = LeaseManager()
    broker = make_broker(
        ledger,
        executors={"file_write": fw_executor},
        verifier=failing_verifier,
        lease=lease,
        node_write_scope=["harness/lib/policy"],
    )
    broker.propose_action(make_contract(
        kind="file_write",
        write_set=["harness/lib/policy/__init__.py"],
        risk_class="medium",
    ))
    assert lease.held() == {}, "verify_failed must release lease"


# ---------------------------------------------------------------------------
# State-coverage matrix — guarantees each acceptance state is observed
# ---------------------------------------------------------------------------


def test_state_coverage_matrix(ledger):
    """One mega-scenario that ensures every acceptance state is hit by the
    suite as a whole (each is also covered by a focused test above; this
    test pins the contract)."""

    seen: set[str] = set()

    # happy path
    broker = make_broker(ledger, executors={"shell": ok_executor})
    seen.update(broker.propose_action(make_contract(action_id="happy")).history)

    # schema_failed
    seen.update(broker.propose_action(make_contract(action_id="sf", risk_class="bogus")).history)

    # policy_denied (high-risk w/o approval)
    seen.update(broker.propose_action(make_contract(action_id="pd", risk_class="high")).history)

    # lease_denied
    lease = LeaseManager()
    lease.acquire("OTHER", ["harness/lib/policy/x.py"])
    broker_l = make_broker(ledger, lease=lease,
                           node_write_scope=["harness/lib/policy"])
    seen.update(broker_l.propose_action(make_contract(
        action_id="ld", kind="file_write",
        write_set=["harness/lib/policy/x.py"], risk_class="medium",
    )).history)

    # exec_failed
    def bad(_):
        return ExecOutcome(exit_code=1, stderr="nope")
    broker_x = make_broker(ledger, executors={"shell": bad})
    seen.update(broker_x.propose_action(make_contract(action_id="ef")).history)

    # verify_failed
    def fail_v(_a, _c, _o):
        return VerifierResult(verdict="FAIL")
    broker_v = make_broker(ledger, executors={"shell": ok_executor},
                           verifier=fail_v)
    seen.update(broker_v.propose_action(make_contract(action_id="vf")).history)

    for state in ALL_STATES:
        assert state in seen, f"state never observed in matrix run: {state}"
