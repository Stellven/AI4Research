from __future__ import annotations

from harness.lib.event_ledger import EventLedger
from harness.lib.failure_handler import (
    EXECUTION_FAILED,
    PLAN_INVALID,
    UNKNOWN_FAILURE,
    VERIFICATION_FAILED,
    classify,
    classify_detail,
    emit_failure_event,
)


def test_plan_invalid_from_graph_scheduler_validate_exit_code():
    event = {
        "event_type": "graph_scheduler.validate",
        "payload": {"exit_code": 2, "reason": "invalid DAG"},
    }
    assert classify(event) == PLAN_INVALID
    detail = classify_detail(event)
    assert detail.reason == "invalid DAG"


def test_plan_invalid_from_graph_scheduler_validate_ok_false():
    event = {
        "event_type": "graph.validate",
        "payload": {"ok": False, "detail": "cycle detected"},
    }
    assert classify(event) == PLAN_INVALID


def test_execution_failed_from_action_executed_non_zero():
    event = {
        "event_type": "action.executed",
        "payload": {"action_id": "A1", "exit_code": 127, "reason": "no executor"},
    }
    assert classify(event) == EXECUTION_FAILED


def test_execution_failed_from_action_failed_event():
    event = {
        "event_type": "action.failed",
        "payload": {"action_id": "A2", "reason": "non_zero_exit"},
    }
    assert classify(event) == EXECUTION_FAILED


def test_verification_failed_from_verifier_verdict_fail():
    event = {
        "event_type": "verifier.verdict",
        "payload": {"action_id": "A3", "verdict": "FAIL", "reason": "assertion"},
    }
    assert classify(event) == VERIFICATION_FAILED


def test_verification_failed_from_verify_failed_state():
    event = {
        "event_type": "broker.state",
        "payload": {"state": "verify_failed", "detail": "bad artifact"},
    }
    assert classify(event) == VERIFICATION_FAILED


def test_unknown_failure_is_warn_classification():
    detail = classify_detail({"event_type": "misc", "payload": {}})
    assert detail.failure_type == UNKNOWN_FAILURE
    assert detail.severity == "warn"


def test_emit_failure_event_includes_reason(tmp_path):
    ledger = EventLedger(base_dir=str(tmp_path / "ledger"))
    source_event = {
        "event_type": "action.executed",
        "node_id": "N3",
        "payload": {
            "action_id": "A7",
            "state": "exec_failed",
            "exit_code": 1,
            "reason": "unit test failure",
        },
    }

    event_id = emit_failure_event(
        ledger,
        sprint_id="sprint-test",
        source_event=source_event,
    )
    events = ledger.replay("sprint-test")

    assert event_id
    assert len(events) == 1
    payload = events[0]["payload"]
    assert events[0]["event_type"] == "failure.classified"
    assert payload["failure_type"] == EXECUTION_FAILED
    assert payload["reason"] == "unit test failure"
    assert payload["source_action_id"] == "A7"
    assert payload["source_state"] == "exec_failed"


def test_emit_plan_invalid_event_includes_reason(tmp_path):
    ledger = EventLedger(base_dir=str(tmp_path / "ledger"))
    emit_failure_event(
        ledger,
        sprint_id="sprint-test",
        source_event={
            "event_type": "graph_scheduler.validate",
            "payload": {"exit_code": 2, "reason": "missing dependency"},
        },
        node_id="planner",
    )
    event = ledger.replay("sprint-test")[0]
    assert event["node_id"] == "planner"
    assert event["payload"]["failure_type"] == PLAN_INVALID
    assert event["payload"]["reason"] == "missing dependency"
