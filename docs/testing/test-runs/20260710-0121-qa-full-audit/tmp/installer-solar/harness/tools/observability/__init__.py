"""Observability metrics for Code-as-Harness Runtime.

S04 N4: sprint-20260519-solar-harness-vnext-code-as-harness-runtime-s04-orchestration-ui

Six metrics computed from the event ledger (JSONL) and sprint status files:
    1. broker_coverage_pct       — % of executed actions covered by a passing contract
    2. policy_denied_rate        — % of policy.verdict events with FAIL outcome
    3. approval_pending_count    — # of human-approval blockers still unresolved
    4. event_ledger_lag_sec      — seconds since the last event was written
    5. dispatcher_dead_letter    — # of dispatcher dead-letter events
    6. sprint_blocked_count      — # of sprints currently in a blocked state

Public API: harness.lib.observability.metrics module exposes all six functions
plus the threshold table. Stdlib only (json, datetime, pathlib, os).
"""
from harness.lib.observability.metrics import (
    ALARM_THRESHOLDS,
    approval_pending_count,
    broker_coverage_pct,
    dispatcher_dead_letter,
    event_ledger_lag_sec,
    iter_events_from_jsonl,
    policy_denied_rate,
    sprint_blocked_count,
)

__all__ = [
    "ALARM_THRESHOLDS",
    "approval_pending_count",
    "broker_coverage_pct",
    "dispatcher_dead_letter",
    "event_ledger_lag_sec",
    "iter_events_from_jsonl",
    "policy_denied_rate",
    "sprint_blocked_count",
]
