"""Tests for harness/lib/observability/metrics.py (S04 N4).

Acceptance:
  1. 6 metric functions each have unit test (12+ test cases total).
  2. Empty events.jsonl handled gracefully (no exception, safe defaults).
  3. Each metric < 200ms wall-clock on a 1k-event fixture.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from harness.lib.observability import (
    ALARM_THRESHOLDS,
    approval_pending_count,
    broker_coverage_pct,
    dispatcher_dead_letter,
    event_ledger_lag_sec,
    iter_events_from_jsonl,
    policy_denied_rate,
    sprint_blocked_count,
)
from harness.lib.observability import metrics as metrics_mod


def _ev(event_type: str, action_id: str = None, **payload) -> Dict[str, Any]:
    p: Dict[str, Any] = dict(payload)
    if action_id is not None:
        p["action_id"] = action_id
    return {
        "event_type": event_type,
        "sprint_id": "sprint-test",
        "actor": "test",
        "payload": p,
        "created_at": "2026-05-20T10:00:00Z",
    }


# ---------------------------------------------------------------------------
# 1. broker_coverage_pct
# ---------------------------------------------------------------------------
class TestBrokerCoveragePct:
    def test_empty_returns_full_coverage(self):
        assert broker_coverage_pct([]) == 100.0

    def test_all_actions_contracted(self):
        events = [
            _ev("action.proposed", "a1"),
            _ev("action.proposed", "a2"),
            _ev("policy.verdict", "a1", verdict="PASS"),
            _ev("policy.verdict", "a2", verdict="PASS"),
        ]
        assert broker_coverage_pct(events) == 100.0

    def test_partial_coverage(self):
        events = [
            _ev("action.proposed", "a1"),
            _ev("action.proposed", "a2"),
            _ev("action.proposed", "a3"),
            _ev("action.proposed", "a4"),
            _ev("policy.verdict", "a1", verdict="PASS"),
            _ev("policy.verdict", "a2", verdict="PASS"),
            _ev("policy.verdict", "a3", verdict="FAIL"),
        ]
        assert broker_coverage_pct(events) == 50.0

    def test_string_payload_parsed(self):
        events = [
            {"event_type": "action.proposed",
             "payload": json.dumps({"action_id": "a1"})},
            {"event_type": "policy.verdict",
             "payload": json.dumps({"action_id": "a1", "verdict": "PASS"})},
        ]
        assert broker_coverage_pct(events) == 100.0

    def test_pass_for_unrelated_action_id_ignored(self):
        events = [
            _ev("action.proposed", "a1"),
            _ev("policy.verdict", "ghost", verdict="PASS"),  # not in proposed
        ]
        assert broker_coverage_pct(events) == 0.0


# ---------------------------------------------------------------------------
# 2. policy_denied_rate
# ---------------------------------------------------------------------------
class TestPolicyDeniedRate:
    def test_empty_returns_zero(self):
        assert policy_denied_rate([]) == 0.0

    def test_all_pass(self):
        events = [_ev("policy.verdict", f"a{i}", verdict="PASS") for i in range(4)]
        assert policy_denied_rate(events) == 0.0

    def test_all_fail(self):
        events = [_ev("policy.verdict", f"a{i}", verdict="FAIL") for i in range(3)]
        assert policy_denied_rate(events) == 100.0

    def test_mixed_rate(self):
        events = (
            [_ev("policy.verdict", f"p{i}", verdict="PASS") for i in range(7)]
            + [_ev("policy.verdict", f"f{i}", verdict="FAIL") for i in range(3)]
        )
        assert policy_denied_rate(events) == 30.0

    def test_non_verdict_events_ignored(self):
        events = [
            _ev("action.proposed", "a1"),
            _ev("policy.verdict", "a1", verdict="FAIL"),
            _ev("action.executed", "a1"),
        ]
        assert policy_denied_rate(events) == 100.0


# ---------------------------------------------------------------------------
# 3. approval_pending_count
# ---------------------------------------------------------------------------
class TestApprovalPendingCount:
    def test_empty_returns_zero(self):
        assert approval_pending_count([]) == 0

    def test_pending_unresolved(self):
        events = [
            _ev("policy.verdict", "a1", verdict="FAIL", reason="HUMAN_APPROVAL_REQUIRED"),
            _ev("policy.verdict", "a2", verdict="FAIL", reason="approval_pending"),
        ]
        assert approval_pending_count(events) == 2

    def test_pending_resolved_by_subsequent_pass(self):
        events = [
            _ev("policy.verdict", "a1", verdict="FAIL", reason="HUMAN_APPROVAL_REQUIRED"),
            _ev("policy.verdict", "a1", verdict="PASS"),
        ]
        assert approval_pending_count(events) == 0

    def test_pending_resolved_by_execution(self):
        events = [
            _ev("policy.verdict", "a1", verdict="FAIL", reason="HUMAN_APPROVAL_REQUIRED"),
            _ev("action.executed", "a1"),
        ]
        assert approval_pending_count(events) == 0

    def test_non_approval_fail_not_counted(self):
        events = [
            _ev("policy.verdict", "a1", verdict="FAIL", reason="write_scope_violation"),
        ]
        assert approval_pending_count(events) == 0


# ---------------------------------------------------------------------------
# 4. event_ledger_lag_sec
# ---------------------------------------------------------------------------
class TestEventLedgerLagSec:
    def test_empty_returns_zero(self):
        assert event_ledger_lag_sec([]) == 0.0

    def test_picks_latest_event(self):
        now = datetime(2026, 5, 20, 10, 0, 30, tzinfo=timezone.utc)
        events = [
            {"created_at": "2026-05-20T10:00:00Z"},
            {"created_at": "2026-05-20T09:59:00Z"},
            {"created_at": "2026-05-20T10:00:25Z"},
        ]
        # latest is 10:00:25, now is 10:00:30 → 5.0 s
        assert event_ledger_lag_sec(events, now=now) == 5.0

    def test_handles_z_suffix_and_microseconds(self):
        now = datetime(2026, 5, 20, 10, 0, 1, tzinfo=timezone.utc)
        events = [{"created_at": "2026-05-20T10:00:00.500000Z"}]
        lag = event_ledger_lag_sec(events, now=now)
        assert 0.4 < lag < 0.6

    def test_unparseable_ts_skipped(self):
        now = datetime(2026, 5, 20, 10, 0, 5, tzinfo=timezone.utc)
        events = [
            {"created_at": "not-a-date"},
            {"created_at": "2026-05-20T10:00:00Z"},
        ]
        assert event_ledger_lag_sec(events, now=now) == 5.0

    def test_future_event_clamped_to_zero(self):
        now = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
        events = [{"created_at": "2026-05-20T10:00:30Z"}]
        assert event_ledger_lag_sec(events, now=now) == 0.0


# ---------------------------------------------------------------------------
# 5. dispatcher_dead_letter
# ---------------------------------------------------------------------------
class TestDispatcherDeadLetter:
    def test_empty_returns_zero(self):
        assert dispatcher_dead_letter([]) == 0

    def test_counts_explicit_dead_letter_types(self):
        events = [
            _ev("dispatcher.dead_letter"),
            _ev("node.dispatch.dead_letter"),
            _ev("dispatch.failed"),
            _ev("action.executed", "a1"),  # not counted
        ]
        assert dispatcher_dead_letter(events) == 3

    def test_counts_payload_dead_letter_flag(self):
        events = [
            {"event_type": "dispatch.retry", "payload": {"dead_letter": True}},
            {"event_type": "dispatch.retry", "payload": {"dead_letter": False}},
        ]
        assert dispatcher_dead_letter(events) == 1

    def test_counts_failure_classified_with_dispatcher_origin(self):
        events = [
            _ev("failure.classified", origin="dispatcher", classification="EXECUTION_FAILED"),
            _ev("failure.classified", origin="builder", classification="EXECUTION_FAILED"),
        ]
        assert dispatcher_dead_letter(events) == 1


# ---------------------------------------------------------------------------
# 6. sprint_blocked_count
# ---------------------------------------------------------------------------
class TestSprintBlockedCount:
    def test_empty_dir_returns_zero(self, tmp_path: Path):
        assert sprint_blocked_count(tmp_path) == 0

    def test_missing_dir_returns_zero(self, tmp_path: Path):
        assert sprint_blocked_count(tmp_path / "does-not-exist") == 0

    def test_counts_blocked_by_list(self, tmp_path: Path):
        (tmp_path / "s1.status.json").write_text(json.dumps({
            "id": "s1", "status": "active", "blocked_by": ["dep-1"]
        }))
        (tmp_path / "s2.status.json").write_text(json.dumps({
            "id": "s2", "status": "active", "blocked_by": []
        }))
        assert sprint_blocked_count(tmp_path) == 1

    def test_counts_status_token(self, tmp_path: Path):
        (tmp_path / "a.status.json").write_text(json.dumps({"status": "blocked"}))
        (tmp_path / "b.status.json").write_text(json.dumps({"status": "active"}))
        (tmp_path / "c.status.json").write_text(json.dumps({"phase": "waiting"}))
        assert sprint_blocked_count(tmp_path) == 2

    def test_terminal_sprints_not_blocked(self, tmp_path: Path):
        # blocked_by set but status terminal — terminal wins.
        (tmp_path / "p.status.json").write_text(json.dumps({
            "status": "passed", "blocked_by": ["dep-still-there"]
        }))
        assert sprint_blocked_count(tmp_path) == 0

    def test_corrupted_status_json_skipped(self, tmp_path: Path):
        (tmp_path / "bad.status.json").write_text("{not json")
        (tmp_path / "ok.status.json").write_text(json.dumps({
            "status": "blocked"
        }))
        assert sprint_blocked_count(tmp_path) == 1

    def test_accepts_iterable_of_dicts(self):
        docs = [
            {"status": "active", "blocked_by": ["x"]},
            {"status": "passed", "blocked_by": ["x"]},
            {"status": "blocked"},
        ]
        assert sprint_blocked_count(docs) == 2


# ---------------------------------------------------------------------------
# Edge: iter_events_from_jsonl + ALARM_THRESHOLDS
# ---------------------------------------------------------------------------
class TestHelpers:
    def test_iter_missing_file_yields_nothing(self, tmp_path: Path):
        assert list(iter_events_from_jsonl(tmp_path / "missing.jsonl")) == []

    def test_iter_parses_valid_lines_skips_bad(self, tmp_path: Path):
        p = tmp_path / "events.jsonl"
        p.write_text('{"event_type":"a"}\n\n{bad json\n{"event_type":"b"}\n')
        rows = list(iter_events_from_jsonl(p))
        assert [r["event_type"] for r in rows] == ["a", "b"]

    def test_alarm_thresholds_cover_all_six_metrics(self):
        expected = {
            "broker_coverage_pct", "policy_denied_rate",
            "approval_pending_count", "event_ledger_lag_sec",
            "dispatcher_dead_letter", "sprint_blocked_count",
        }
        assert set(ALARM_THRESHOLDS.keys()) == expected
        for name, spec in ALARM_THRESHOLDS.items():
            assert spec["op"] in {"<", ">"}
            assert "threshold" in spec
            assert spec["severity"] in {"ALARM", "CRITICAL"}


# ---------------------------------------------------------------------------
# Performance: each metric < 200ms on a 1k-event fixture
# ---------------------------------------------------------------------------
def _make_fixture_events(n: int) -> List[Dict[str, Any]]:
    base = datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
    events: List[Dict[str, Any]] = []
    for i in range(n):
        aid = f"a{i}"
        ts = (base + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")
        events.append({"event_type": "action.proposed",
                       "payload": {"action_id": aid, "kind": "shell"},
                       "created_at": ts})
        if i % 5 != 0:
            events.append({"event_type": "policy.verdict",
                           "payload": {"action_id": aid, "verdict": "PASS"},
                           "created_at": ts})
        else:
            events.append({"event_type": "policy.verdict",
                           "payload": {"action_id": aid, "verdict": "FAIL",
                                       "reason": "write_scope_violation"},
                           "created_at": ts})
        if i % 50 == 0:
            events.append({"event_type": "dispatch.failed",
                           "payload": {"node_id": "N1"},
                           "created_at": ts})
        events.append({"event_type": "action.executed",
                       "payload": {"action_id": aid},
                       "created_at": ts})
    return events


def _timed(fn, *args, **kwargs) -> float:
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0  # ms


def test_each_metric_under_200ms(tmp_path: Path):
    events = _make_fixture_events(1000)
    # Seed a status_dir for sprint_blocked_count
    for i in range(20):
        (tmp_path / f"s{i}.status.json").write_text(json.dumps({
            "status": "active" if i % 2 else "blocked",
            "blocked_by": ["dep"] if i % 3 == 0 else [],
        }))

    budgets_ms = 200.0
    timings = {
        "broker_coverage_pct":    _timed(broker_coverage_pct, events),
        "policy_denied_rate":     _timed(policy_denied_rate, events),
        "approval_pending_count": _timed(approval_pending_count, events),
        "event_ledger_lag_sec":   _timed(event_ledger_lag_sec, events,
                                          now=datetime.now(timezone.utc)),
        "dispatcher_dead_letter": _timed(dispatcher_dead_letter, events),
        "sprint_blocked_count":   _timed(sprint_blocked_count, tmp_path),
    }
    over_budget = {k: v for k, v in timings.items() if v >= budgets_ms}
    assert not over_budget, f"metrics over 200ms: {over_budget} (all: {timings})"


# ---------------------------------------------------------------------------
# Realism: round-trip through EventLedger (real call-path, not synthetic dicts)
# ---------------------------------------------------------------------------
def test_metrics_consume_real_event_ledger(tmp_path: Path):
    """Drive metrics on events appended via the real EventLedger.replay()."""
    from harness.lib.event_ledger import EventLedger

    base = tmp_path / "ledger-base"
    ledger = EventLedger(base_dir=str(base))
    sid = "sprint-obs-test"
    for i in range(5):
        ledger.append({
            "event_type": "action.proposed",
            "sprint_id": sid, "actor": "test",
            "payload": {"action_id": f"a{i}", "kind": "shell"},
        })
        ledger.append({
            "event_type": "policy.verdict",
            "sprint_id": sid, "actor": "test",
            "payload": {"action_id": f"a{i}", "verdict": "PASS" if i < 4 else "FAIL"},
        })

    events = ledger.replay(sid)
    assert broker_coverage_pct(events) == 80.0
    assert policy_denied_rate(events) == 20.0
    assert approval_pending_count(events) == 0
    assert dispatcher_dead_letter(events) == 0
    # lag is recent (just appended), well under threshold
    assert event_ledger_lag_sec(events) < 60.0
