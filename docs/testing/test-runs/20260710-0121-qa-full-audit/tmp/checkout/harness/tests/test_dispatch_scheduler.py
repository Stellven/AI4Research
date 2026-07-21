"""Tests for DispatchScheduler — spillover select + dedup + safety guards."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from dispatch_scheduler import (
    DispatchScheduler,
    ScheduleResult,
    SafetyViolationError,
    PROTECTED_PANES,
    DEFAULT_SPILLOVER_POOL,
)
from pane_hygiene_registry import PaneHygieneRegistry, PaneState


class FakeInjectionResult:
    def __init__(self, success=True):
        self.success = success


class FakeReinjector:
    def __init__(self, succeed=True):
        self.calls = []
        self._succeed = succeed

    def inject_all(self, pane_id, role, sprint_id):
        self.calls.append((pane_id, role, sprint_id))
        return FakeInjectionResult(self._succeed)


@pytest.fixture
def registry(tmp_path):
    r = PaneHygieneRegistry(str(tmp_path / "test-sched.json"))
    r.register_pane("solar-harness:0.3", "evaluator", model="anthropic-opus")
    r.register_pane("solar-harness-lab:0.0", "builder", model="glm-5.1")
    r.register_pane("solar-harness-lab:0.1", "builder", model="glm-5.1")
    r.register_pane("solar-harness-lab:0.2", "builder", model="glm-5.1")
    r.register_pane("solar-harness-lab:0.3", "builder", model="anthropic-sonnet")
    return r


class FakeLedger:
    def __init__(self):
        self.records = []

    def record_reinject(self, pane_id, **kw):
        self.records.append(("reinject", pane_id))

    def record_reassign(self, from_pane, to_pane, **kw):
        self.records.append(("reassign", from_pane, to_pane))

    def record_respawn(self, pane_id, **kw):
        self.records.append(("respawn", pane_id, kw))


def _make_scheduler(registry, reinjector=None, ledger=None):
    return DispatchScheduler(
        registry, ledger or FakeLedger(), reinjector or FakeReinjector(),
    )


# --- select_pane ---

class TestSelectPane:
    def test_select_clean_pane(self, registry):
        sched = _make_scheduler(registry)
        result = sched.select_pane("task-1", "sprint-1", role="evaluator")
        assert result.ok
        assert len(result.assigned) == 1
        pane_id = result.assigned[0][1]
        entry = registry.get_pane_state(pane_id)
        assert entry.state == PaneState.running

    def test_no_clean_panes(self, registry):
        for pane in ["solar-harness:0.3"]:
            registry.transition_state(pane, PaneState.running, reason="test")
            registry.transition_state(pane, PaneState.dirty, reason="test")
        sched = _make_scheduler(registry)
        result = sched.select_pane("task-1", "sprint-1", role="evaluator")
        assert not result.ok
        assert result.reason == "no_clean_panes"

    def test_inject_failure_skips_pane(self, registry):
        reinjector = FakeReinjector(succeed=False)
        sched = _make_scheduler(registry, reinjector=reinjector)
        result = sched.select_pane("task-1", "sprint-1", role="evaluator")
        assert not result.ok


# --- spillover_select ---

class TestSpilloverSelect:
    def test_three_tasks_three_panes(self, registry):
        sched = _make_scheduler(registry)
        result = sched.spillover_select(
            ["task-1", "task-2", "task-3"], "sprint-1",
            max_items=3, role="evaluator",
        )
        assert result.ok
        assert len(result.assigned) == 3
        pane_ids = [a[1] for a in result.assigned]
        assert len(set(pane_ids)) == 3  # zero collision

    def test_dedup_no_same_pane(self, registry):
        sched = _make_scheduler(registry)
        result = sched.spillover_select(
            ["task-1", "task-2", "task-3"], "sprint-1",
            max_items=3,
        )
        pane_ids = [a[1] for a in result.assigned]
        assert len(pane_ids) == len(set(pane_ids))

    def test_insufficient_panes(self, registry):
        sched = _make_scheduler(registry)
        result = sched.spillover_select(
            ["t1", "t2", "t3", "t4", "t5", "t6"], "sprint-1",
            max_items=6,
        )
        assert not result.ok or len(result.assigned) < 6

    def test_max_items_limits(self, registry):
        sched = _make_scheduler(registry)
        result = sched.spillover_select(
            ["t1", "t2", "t3", "t4"], "sprint-1", max_items=2,
        )
        assert len(result.assigned) <= 2


# --- mark_busy / mark_idle ---

class TestMarkBusyIdle:
    def test_mark_idle_transitions_to_dirty(self, registry):
        registry.transition_state("solar-harness:0.3", PaneState.running, reason="test")
        sched = _make_scheduler(registry)
        sched.mark_idle("solar-harness:0.3")
        entry = registry.get_pane_state("solar-harness:0.3")
        assert entry.state == PaneState.dirty

    def test_mark_idle_raises_on_non_running(self, registry):
        sched = _make_scheduler(registry)
        with pytest.raises(ValueError, match="running"):
            sched.mark_idle("solar-harness:0.3")


# --- SafetyGuard ---

class TestSafetyGuard:
    def test_kill_main_pane_blocked(self):
        sched = DispatchScheduler.__new__(DispatchScheduler)
        with pytest.raises(SafetyViolationError):
            sched._assert_not_kill_main_pane("solar-harness:0.0")

    def test_lab_pane_allowed(self):
        sched = DispatchScheduler.__new__(DispatchScheduler)
        sched._assert_not_kill_main_pane("solar-harness-lab:0.0")

    def test_protected_panes_include_main_and_spillover(self):
        assert len(PROTECTED_PANES) == 8
        assert "solar-harness:0.0" in PROTECTED_PANES
        assert "solar-harness-lab:0.3" in PROTECTED_PANES

    def test_respawn_protected_pane_blocked(self):
        sched = DispatchScheduler.__new__(DispatchScheduler)
        with pytest.raises(SafetyViolationError):
            sched._assert_respawn_target_allowed("solar-harness-lab:0.0")

    def test_respawn_max_concurrent_zero_blocks(self, registry):
        sched = DispatchScheduler(
            registry, FakeLedger(), FakeReinjector(),
            respawn_max_concurrent=0,
        )
        result = sched.can_respawn("scratch-worker:0.0")
        assert not result.ok
        assert result.reason == "respawn_disabled_by_max_concurrent_zero"

    def test_begin_respawn_records_rejection(self, registry):
        ledger = FakeLedger()
        sched = DispatchScheduler(
            registry, ledger, FakeReinjector(),
            respawn_max_concurrent=0,
        )
        result = sched.begin_respawn(
            "scratch-worker:0.0",
            reason="test",
            sprint_id="sprint-1",
            task_id="task-1",
        )
        assert not result.ok
        assert ledger.records[0][0] == "respawn"
        assert ledger.records[0][2]["success"] is False

    def test_begin_finish_respawn_tracks_concurrency(self, registry):
        ledger = FakeLedger()
        sched = DispatchScheduler(
            registry, ledger, FakeReinjector(),
            respawn_max_concurrent=1,
        )
        first = sched.begin_respawn("scratch-worker:0.0", reason="test")
        second = sched.begin_respawn("scratch-worker:0.1", reason="test")
        assert first.ok
        assert not second.ok
        assert second.reason == "respawn_max_concurrent_reached"
        sched.finish_respawn("scratch-worker:0.0")
        third = sched.begin_respawn("scratch-worker:0.1", reason="test")
        assert third.ok

    def test_forbidden_command_pattern(self):
        sched = DispatchScheduler.__new__(DispatchScheduler)
        with pytest.raises(SafetyViolationError):
            sched._assert_no_thunderomlx_restart("pkill -f thunderomlx")

    def test_safe_command_passes(self):
        sched = DispatchScheduler.__new__(DispatchScheduler)
        sched._assert_no_thunderomlx_restart("echo hello")
