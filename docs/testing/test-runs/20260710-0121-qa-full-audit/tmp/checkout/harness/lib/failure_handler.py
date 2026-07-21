"""Failure classification and event emission for S03 N7."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

try:
    from harness.lib.event_ledger import EventLedger
except ModuleNotFoundError:  # pragma: no cover - legacy direct import path
    from event_ledger import EventLedger

PLAN_INVALID = "PLAN_INVALID"
EXECUTION_FAILED = "EXECUTION_FAILED"
VERIFICATION_FAILED = "VERIFICATION_FAILED"
UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


@dataclass(frozen=True)
class FailureClassification:
    failure_type: str
    reason: str
    source_event_type: str = ""
    severity: str = "error"


def classify(event: Mapping[str, Any]) -> str:
    """Return the P0 failure type for a graph/broker/verifier event."""
    return classify_detail(event).failure_type


def classify_detail(event: Mapping[str, Any]) -> FailureClassification:
    event_type = str(event.get("event_type") or event.get("type") or "")
    payload = _payload(event)

    if _is_plan_invalid(event_type, payload):
        return FailureClassification(
            PLAN_INVALID,
            _reason(payload, "graph_scheduler_validate_failed"),
            event_type,
        )
    if _is_execution_failed(event_type, payload):
        return FailureClassification(
            EXECUTION_FAILED,
            _reason(payload, "broker_execution_failed"),
            event_type,
        )
    if _is_verification_failed(event_type, payload):
        return FailureClassification(
            VERIFICATION_FAILED,
            _reason(payload, "verifier_failed"),
            event_type,
        )
    return FailureClassification(
        UNKNOWN_FAILURE,
        _reason(payload, "unclassified_failure"),
        event_type,
        severity="warn",
    )


def emit_failure_event(
    ledger: EventLedger,
    *,
    sprint_id: str,
    source_event: Mapping[str, Any],
    actor: str = "failure_handler",
    node_id: Optional[str] = None,
) -> str:
    detail = classify_detail(source_event)
    source_payload = _payload(source_event)
    return ledger.append(
        {
            "event_type": "failure.classified",
            "sprint_id": sprint_id,
            "node_id": node_id or source_event.get("node_id"),
            "actor": actor,
            "payload": {
                "failure_type": detail.failure_type,
                "reason": detail.reason,
                "severity": detail.severity,
                "source_event_type": detail.source_event_type,
                "source_action_id": source_payload.get("action_id"),
                "source_state": source_payload.get("state"),
            },
        }
    )


def _payload(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _reason(payload: Mapping[str, Any], fallback: str) -> str:
    value = payload.get("reason") or payload.get("detail") or fallback
    return str(value)


def _is_plan_invalid(event_type: str, payload: Mapping[str, Any]) -> bool:
    if event_type in {"graph.validate", "graph.validation", "graph_scheduler.validate"}:
        return int(payload.get("exit_code", 0) or 0) != 0 or payload.get("ok") is False
    return str(payload.get("phase") or "") == "graph_scheduler_validate" and (
        int(payload.get("exit_code", 0) or 0) != 0 or payload.get("ok") is False
    )


def _is_execution_failed(event_type: str, payload: Mapping[str, Any]) -> bool:
    if event_type in {"action.failed", "broker.exec_failed"}:
        return True
    if event_type == "action.executed":
        try:
            return int(payload.get("exit_code", 0) or 0) != 0
        except (TypeError, ValueError):
            return True
    return str(payload.get("state") or "") == "exec_failed"


def _is_verification_failed(event_type: str, payload: Mapping[str, Any]) -> bool:
    if event_type in {"verifier.verdict", "verification.verdict"}:
        return str(payload.get("verdict") or "").upper() == "FAIL"
    return str(payload.get("state") or "") == "verify_failed"


__all__ = [
    "EXECUTION_FAILED",
    "FailureClassification",
    "PLAN_INVALID",
    "UNKNOWN_FAILURE",
    "VERIFICATION_FAILED",
    "classify",
    "classify_detail",
    "emit_failure_event",
]
