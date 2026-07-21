"""
Unit tests for budgets.py — one test class per stopper, plus Budget validation.

Coverage targets:
  - StopReason: dataclass immutability, code/message/details fields
  - Budget: validation, default_stoppers() factory
  - SpendStopper: below cap → None, at cap → StopReason
  - EvalStopper: below cap → None, at cap → StopReason
  - WalltimeStopper: under time → None, over time → StopReason
  - PlateauStopper: insufficient history → None, plateau detected → StopReason,
                    improvement resets → None, edge cases
  - StopFileStopper: no file → None, file present → StopReason
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'integrations'))

from gepa_optimizer.budgets import (
    Budget,
    BudgetError,
    EvalStopper,
    PlateauStopper,
    RunState,
    SpendStopper,
    StopFileStopper,
    StopReason,
    StopperProtocol,
    WalltimeStopper,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(
    evaluations: int = 0,
    spend_usd: float = 0.0,
    started_at_monotonic: float = 0.0,
    best_score: float | None = None,
    history: tuple[float, ...] = (),
) -> RunState:
    return RunState(
        evaluations=evaluations,
        spend_usd=spend_usd,
        started_at_monotonic=started_at_monotonic,
        best_score=best_score,
        history=history,
    )


class _FakeTime:
    """Controllable time source for WalltimeStopper tests."""

    def __init__(self, current: float = 0.0) -> None:
        self.current = current

    def now(self) -> float:
        return self.current


# ---------------------------------------------------------------------------
# StopReason
# ---------------------------------------------------------------------------


class TestStopReason:
    def test_fields_accessible(self):
        sr = StopReason(code="test.code", message="msg", details={"k": 1})
        assert sr.code == "test.code"
        assert sr.message == "msg"
        assert sr.details == {"k": 1}

    def test_frozen(self):
        sr = StopReason(code="x", message="y")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            sr.code = "z"  # type: ignore[misc]

    def test_default_details_empty_dict(self):
        sr = StopReason(code="x", message="y")
        assert sr.details == {}

    def test_details_are_independent_instances(self):
        sr1 = StopReason(code="x", message="y")
        sr2 = StopReason(code="x", message="y")
        assert sr1.details is not sr2.details


# ---------------------------------------------------------------------------
# Budget validation
# ---------------------------------------------------------------------------


class TestBudget:
    def test_valid_budget(self):
        b = Budget(max_evals=10, max_spend_usd=1.0, max_walltime_seconds=60.0)
        assert b.max_evals == 10

    def test_zero_evals_raises(self):
        with pytest.raises(BudgetError):
            Budget(max_evals=0, max_spend_usd=1.0, max_walltime_seconds=60.0)

    def test_negative_evals_raises(self):
        with pytest.raises(BudgetError):
            Budget(max_evals=-1, max_spend_usd=1.0, max_walltime_seconds=60.0)

    def test_zero_spend_raises(self):
        with pytest.raises(BudgetError):
            Budget(max_evals=10, max_spend_usd=0.0, max_walltime_seconds=60.0)

    def test_negative_spend_raises(self):
        with pytest.raises(BudgetError):
            Budget(max_evals=10, max_spend_usd=-0.01, max_walltime_seconds=60.0)

    def test_zero_walltime_raises(self):
        with pytest.raises(BudgetError):
            Budget(max_evals=10, max_spend_usd=1.0, max_walltime_seconds=0.0)

    def test_negative_walltime_raises(self):
        with pytest.raises(BudgetError):
            Budget(max_evals=10, max_spend_usd=1.0, max_walltime_seconds=-1.0)

    def test_budget_frozen(self):
        b = Budget(max_evals=10, max_spend_usd=1.0, max_walltime_seconds=60.0)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            b.max_evals = 99  # type: ignore[misc]

    def test_default_stoppers_no_run_dir(self):
        b = Budget(max_evals=5, max_spend_usd=0.5, max_walltime_seconds=30.0)
        stoppers = b.default_stoppers()
        assert len(stoppers) == 3
        assert all(isinstance(s, StopperProtocol) for s in stoppers)

    def test_default_stoppers_with_run_dir(self, tmp_path):
        b = Budget(max_evals=5, max_spend_usd=0.5, max_walltime_seconds=30.0)
        stoppers = b.default_stoppers(run_dir=tmp_path)
        assert len(stoppers) == 4

    def test_default_stoppers_types(self, tmp_path):
        b = Budget(max_evals=5, max_spend_usd=0.5, max_walltime_seconds=30.0)
        stoppers = b.default_stoppers(run_dir=tmp_path)
        types = {type(s) for s in stoppers}
        assert SpendStopper in types
        assert EvalStopper in types
        assert WalltimeStopper in types
        assert StopFileStopper in types

    def test_default_stoppers_custom_time_source(self, tmp_path):
        fake = _FakeTime(100.0)
        b = Budget(max_evals=5, max_spend_usd=0.5, max_walltime_seconds=30.0)
        stoppers = b.default_stoppers(run_dir=tmp_path, time_source=fake)
        walltime_stopper = next(s for s in stoppers if isinstance(s, WalltimeStopper))
        # With start=0 and fake.now()=100 > 30 cap, should trip
        state = _state(started_at_monotonic=0.0)
        reason = walltime_stopper.check(state)
        assert reason is not None
        assert reason.code == "budget.walltime"


# ---------------------------------------------------------------------------
# SpendStopper
# ---------------------------------------------------------------------------


class TestSpendStopper:
    def test_below_cap_returns_none(self):
        s = SpendStopper(max_spend_usd=1.0)
        assert s.check(_state(spend_usd=0.99)) is None

    def test_zero_spend_returns_none(self):
        s = SpendStopper(max_spend_usd=1.0)
        assert s.check(_state(spend_usd=0.0)) is None

    def test_at_cap_returns_stop_reason(self):
        s = SpendStopper(max_spend_usd=1.0)
        reason = s.check(_state(spend_usd=1.0))
        assert reason is not None
        assert reason.code == "budget.spend"

    def test_over_cap_returns_stop_reason(self):
        s = SpendStopper(max_spend_usd=1.0)
        reason = s.check(_state(spend_usd=1.5))
        assert reason is not None
        assert reason.code == "budget.spend"

    def test_details_contain_values(self):
        s = SpendStopper(max_spend_usd=2.0)
        reason = s.check(_state(spend_usd=3.0))
        assert reason is not None
        assert reason.details["spend_usd"] == pytest.approx(3.0)
        assert reason.details["max_spend_usd"] == pytest.approx(2.0)

    def test_message_is_nonempty(self):
        s = SpendStopper(max_spend_usd=1.0)
        reason = s.check(_state(spend_usd=2.0))
        assert reason is not None
        assert len(reason.message) > 0

    def test_implements_stopper_protocol(self):
        assert isinstance(SpendStopper(max_spend_usd=1.0), StopperProtocol)


# ---------------------------------------------------------------------------
# EvalStopper
# ---------------------------------------------------------------------------


class TestEvalStopper:
    def test_below_cap_returns_none(self):
        s = EvalStopper(max_evals=10)
        assert s.check(_state(evaluations=9)) is None

    def test_zero_evals_returns_none(self):
        s = EvalStopper(max_evals=10)
        assert s.check(_state(evaluations=0)) is None

    def test_at_cap_returns_stop_reason(self):
        s = EvalStopper(max_evals=10)
        reason = s.check(_state(evaluations=10))
        assert reason is not None
        assert reason.code == "budget.evals"

    def test_over_cap_returns_stop_reason(self):
        s = EvalStopper(max_evals=10)
        reason = s.check(_state(evaluations=11))
        assert reason is not None
        assert reason.code == "budget.evals"

    def test_details_contain_values(self):
        s = EvalStopper(max_evals=5)
        reason = s.check(_state(evaluations=7))
        assert reason is not None
        assert reason.details["evaluations"] == 7
        assert reason.details["max_evals"] == 5

    def test_message_is_nonempty(self):
        s = EvalStopper(max_evals=3)
        reason = s.check(_state(evaluations=3))
        assert reason is not None
        assert len(reason.message) > 0

    def test_implements_stopper_protocol(self):
        assert isinstance(EvalStopper(max_evals=1), StopperProtocol)


# ---------------------------------------------------------------------------
# WalltimeStopper
# ---------------------------------------------------------------------------


class TestWalltimeStopper:
    def test_under_time_returns_none(self):
        fake = _FakeTime(50.0)
        s = WalltimeStopper(max_seconds=60.0, time_source=fake)
        state = _state(started_at_monotonic=0.0)
        assert s.check(state) is None

    def test_at_cap_returns_stop_reason(self):
        fake = _FakeTime(60.0)
        s = WalltimeStopper(max_seconds=60.0, time_source=fake)
        state = _state(started_at_monotonic=0.0)
        reason = s.check(state)
        assert reason is not None
        assert reason.code == "budget.walltime"

    def test_over_cap_returns_stop_reason(self):
        fake = _FakeTime(75.0)
        s = WalltimeStopper(max_seconds=60.0, time_source=fake)
        state = _state(started_at_monotonic=0.0)
        reason = s.check(state)
        assert reason is not None
        assert reason.code == "budget.walltime"

    def test_details_contain_elapsed_and_max(self):
        fake = _FakeTime(90.0)
        s = WalltimeStopper(max_seconds=60.0, time_source=fake)
        state = _state(started_at_monotonic=0.0)
        reason = s.check(state)
        assert reason is not None
        assert reason.details["elapsed_seconds"] == pytest.approx(90.0)
        assert reason.details["max_seconds"] == pytest.approx(60.0)

    def test_nonzero_start_time(self):
        fake = _FakeTime(100.0)
        s = WalltimeStopper(max_seconds=30.0, time_source=fake)
        # started 80s ago → elapsed = 20s < 30s → no stop
        state = _state(started_at_monotonic=80.0)
        assert s.check(state) is None

    def test_nonzero_start_time_trips(self):
        fake = _FakeTime(120.0)
        s = WalltimeStopper(max_seconds=30.0, time_source=fake)
        # started 80s ago → elapsed = 40s > 30s → stop
        state = _state(started_at_monotonic=80.0)
        reason = s.check(state)
        assert reason is not None
        assert reason.code == "budget.walltime"

    def test_message_is_nonempty(self):
        fake = _FakeTime(999.0)
        s = WalltimeStopper(max_seconds=1.0, time_source=fake)
        reason = s.check(_state(started_at_monotonic=0.0))
        assert reason is not None
        assert len(reason.message) > 0

    def test_implements_stopper_protocol(self):
        assert isinstance(WalltimeStopper(max_seconds=60.0), StopperProtocol)


# ---------------------------------------------------------------------------
# PlateauStopper
# ---------------------------------------------------------------------------


class TestPlateauStopper:
    def test_empty_history_returns_none(self):
        s = PlateauStopper(patience=5)
        assert s.check(_state(history=())) is None

    def test_short_history_returns_none(self):
        s = PlateauStopper(patience=5)
        # history len <= patience → no trigger
        assert s.check(_state(history=(0.5, 0.6, 0.7, 0.8, 0.9))) is None

    def test_history_exactly_patience_returns_none(self):
        s = PlateauStopper(patience=3)
        # len=3 <= patience=3 → no trigger
        assert s.check(_state(history=(0.1, 0.2, 0.3))) is None

    def test_plateau_detected(self):
        s = PlateauStopper(patience=3, epsilon=1e-3)
        # window of 4 (patience+1): all same → no improvement
        history = (0.5, 0.5, 0.5, 0.5)
        reason = s.check(_state(history=history))
        assert reason is not None
        assert reason.code == "plateau.no_improvement"

    def test_improvement_above_epsilon_no_trip(self):
        s = PlateauStopper(patience=3, epsilon=1e-3)
        # window: 0.5 → 0.502 = improvement of 0.002 > 1e-3
        history = (0.5, 0.500, 0.501, 0.502)
        assert s.check(_state(history=history)) is None

    def test_improvement_below_epsilon_trips(self):
        s = PlateauStopper(patience=3, epsilon=1e-3)
        # improvement = 0.0005 < 1e-3 → plateau
        history = (0.5, 0.5001, 0.5003, 0.5005)
        reason = s.check(_state(history=history))
        assert reason is not None
        assert reason.code == "plateau.no_improvement"

    def test_improvement_exactly_epsilon_trips(self):
        # current_best - baseline == epsilon → NOT > epsilon → trips
        s = PlateauStopper(patience=3, epsilon=0.1)
        history = (0.5, 0.5, 0.5, 0.6)  # improvement = 0.1 exactly
        reason = s.check(_state(history=history))
        assert reason is not None
        assert reason.code == "plateau.no_improvement"

    def test_uses_last_patience_plus_one_window(self):
        s = PlateauStopper(patience=3, epsilon=1e-3)
        # long history: early part has big jump, recent window is flat
        history = (0.0, 0.9, 0.9, 0.9, 0.9)  # window[-4:] = (0.9,0.9,0.9,0.9)
        reason = s.check(_state(history=history))
        assert reason is not None
        assert reason.code == "plateau.no_improvement"

    def test_details_contain_expected_keys(self):
        s = PlateauStopper(patience=3, epsilon=0.01)
        history = (0.5, 0.5, 0.5, 0.5)
        reason = s.check(_state(history=history))
        assert reason is not None
        assert "baseline" in reason.details
        assert "current_best" in reason.details
        assert "epsilon" in reason.details
        assert "patience" in reason.details

    def test_zero_patience_raises(self):
        with pytest.raises(BudgetError):
            PlateauStopper(patience=0)

    def test_negative_patience_raises(self):
        with pytest.raises(BudgetError):
            PlateauStopper(patience=-1)

    def test_negative_epsilon_raises(self):
        with pytest.raises(BudgetError):
            PlateauStopper(epsilon=-0.01)

    def test_zero_epsilon_allowed(self):
        # epsilon=0 means any improvement counts
        s = PlateauStopper(patience=3, epsilon=0.0)
        # all same → plateau
        history = (0.5, 0.5, 0.5, 0.5)
        reason = s.check(_state(history=history))
        assert reason is not None

    def test_implements_stopper_protocol(self):
        assert isinstance(PlateauStopper(), StopperProtocol)


# ---------------------------------------------------------------------------
# StopFileStopper
# ---------------------------------------------------------------------------


class TestStopFileStopper:
    def test_no_file_returns_none(self, tmp_path):
        s = StopFileStopper(run_dir=tmp_path)
        assert s.check(_state()) is None

    def test_file_present_returns_stop_reason(self, tmp_path):
        (tmp_path / "STOP").touch()
        s = StopFileStopper(run_dir=tmp_path)
        reason = s.check(_state())
        assert reason is not None
        assert reason.code == "explicit.stop_file"

    def test_details_contain_path(self, tmp_path):
        sentinel = tmp_path / "STOP"
        sentinel.touch()
        s = StopFileStopper(run_dir=tmp_path)
        reason = s.check(_state())
        assert reason is not None
        assert "path" in reason.details
        assert str(sentinel) in reason.details["path"]

    def test_custom_filename_no_file(self, tmp_path):
        s = StopFileStopper(run_dir=tmp_path, filename="KILL")
        assert s.check(_state()) is None

    def test_custom_filename_file_present(self, tmp_path):
        (tmp_path / "KILL").touch()
        s = StopFileStopper(run_dir=tmp_path, filename="KILL")
        reason = s.check(_state())
        assert reason is not None
        assert reason.code == "explicit.stop_file"

    def test_wrong_filename_not_triggered(self, tmp_path):
        # STOP file present but stopper watches KILL
        (tmp_path / "STOP").touch()
        s = StopFileStopper(run_dir=tmp_path, filename="KILL")
        assert s.check(_state()) is None

    def test_accepts_pathlike(self, tmp_path):
        s = StopFileStopper(run_dir=Path(tmp_path))
        assert s.check(_state()) is None

    def test_accepts_string_path(self, tmp_path):
        s = StopFileStopper(run_dir=str(tmp_path))
        (tmp_path / "STOP").touch()
        reason = s.check(_state())
        assert reason is not None

    def test_message_is_nonempty(self, tmp_path):
        (tmp_path / "STOP").touch()
        s = StopFileStopper(run_dir=tmp_path)
        reason = s.check(_state())
        assert reason is not None
        assert len(reason.message) > 0

    def test_implements_stopper_protocol(self, tmp_path):
        assert isinstance(StopFileStopper(run_dir=tmp_path), StopperProtocol)


# ---------------------------------------------------------------------------
# Integration: multiple stoppers, first-wins semantics
# ---------------------------------------------------------------------------


class TestMultipleStoppers:
    def test_all_stoppers_pass(self, tmp_path):
        fake = _FakeTime(10.0)
        stoppers = [
            SpendStopper(max_spend_usd=1.0),
            EvalStopper(max_evals=100),
            WalltimeStopper(max_seconds=60.0, time_source=fake),
            StopFileStopper(run_dir=tmp_path),
        ]
        state = _state(spend_usd=0.5, evaluations=50, started_at_monotonic=0.0)
        results = [s.check(state) for s in stoppers]
        assert all(r is None for r in results)

    def test_spend_trips_first(self, tmp_path):
        fake = _FakeTime(10.0)
        stoppers = [
            SpendStopper(max_spend_usd=0.1),
            EvalStopper(max_evals=100),
            WalltimeStopper(max_seconds=60.0, time_source=fake),
            StopFileStopper(run_dir=tmp_path),
        ]
        state = _state(spend_usd=0.5, evaluations=50, started_at_monotonic=0.0)
        reasons = [s.check(state) for s in stoppers]
        assert reasons[0] is not None
        assert reasons[0].code == "budget.spend"
        assert all(r is None for r in reasons[1:])
