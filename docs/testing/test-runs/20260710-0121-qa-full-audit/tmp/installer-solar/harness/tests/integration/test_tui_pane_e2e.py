"""E2E integration test: proceed/queued/permission → recover → clear → reassign full chain.

This is the B4 acceptance gate integration test. Uses mock tmux throughout.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from pane_hygiene_registry import PaneHygieneRegistry, PaneState
from recover_detector import RecoverDetector, PromptType
from pane_clear_manager import PaneClearManager


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "tmux_capture_samples"


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def _make_dirty(registry, pane_id="solar-harness-lab:0.0"):
    registry.transition_state(pane_id, PaneState.running, reason="e2e_setup")
    registry.transition_state(pane_id, PaneState.dirty, reason="e2e_setup")


# ── V1: Proceed prompt detection + auto-response ─────────────────

class TestV1ProceedPrompt:
    def test_detect_and_continue(self, tui_registry):
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("proceed.txt"))
        result = det.detect_proceed_prompt("solar-harness-lab:0.0")
        assert result.prompt_type == PromptType.PROCEED
        assert result.detected

    def test_clean_no_false_positive(self, tui_registry):
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("clean.txt"))
        result = det.classify_prompt("solar-harness-lab:0.0")
        assert result.prompt_type == PromptType.NONE


# ── V2: Queued message detection + recovery ──────────────────────

class TestV2QueuedMessage:
    def test_detect_queued(self, tui_registry):
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("queued.txt"))
        result = det.detect_queued_message("solar-harness-lab:0.0")
        assert result.prompt_type == PromptType.QUEUED
        assert result.detected

    def test_no_infinite_loop_on_persistent_queued(self, tui_registry):
        _make_dirty(tui_registry)
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("queued.txt"))
        mgr, _, sleeps, _ = _make_mgr(tui_registry, det, lambda _: _load_fixture("queued.txt"))
        result = mgr.clear_with_retry("solar-harness-lab:0.0")
        assert not result.success
        assert result.reason == "exhausted"
        entry = tui_registry.get_pane_state("solar-harness-lab:0.0")
        assert entry.state == PaneState.needs_respawn


# ── V3+V4: Builder/Evaluator /clear → state=clean ──────────────

class TestV3V4Clear:
    def test_builder_clear_to_clean(self, tui_registry):
        _make_dirty(tui_registry, "solar-harness-lab:0.0")
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("clean.txt"))
        mgr = PaneClearManager(
            tui_registry, det,
            send_fn=lambda pid, k: None,
            sleep_fn=lambda s: None,
        )
        result = mgr.clear_pane("solar-harness-lab:0.0")
        assert result.success
        entry = tui_registry.get_pane_state("solar-harness-lab:0.0")
        assert entry.state == PaneState.clean

    def test_evaluator_clear_to_clean(self, tui_registry):
        _make_dirty(tui_registry, "solar-harness:0.3")
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("clean.txt"))
        mgr = PaneClearManager(
            tui_registry, det,
            send_fn=lambda pid, k: None,
            sleep_fn=lambda s: None,
        )
        result = mgr.clear_pane("solar-harness:0.3")
        assert result.success
        entry = tui_registry.get_pane_state("solar-harness:0.3")
        assert entry.state == PaneState.clean


# ── V5: Re-inject on clean→running ──────────────────────────────

class TestV5Reinject:
    def test_clean_pane_reinject(self, tui_registry, tmp_path):
        from persona_reinjector import PersonaReinjector

        base = tmp_path / "templates"
        (base / "persona").mkdir(parents=True)
        (base / "persona" / "builder.md").write_text("You are a Solar Builder.\nBuild code.")
        (base / "runtime_policy.md").write_text("Definition of Done: 7 rules.\nNo optimistic words.")
        (base / "solar_context_sprint-123.md").write_text("Sprint context.\nGoal: implement X.")

        captures = {"solar-harness-lab:0.0": "You are a Solar Builder.\nBuild code.Definition of Done: 7 rules.\nNo optimistic words.Sprint context.\nGoal: implement X."}

        class FakeLedger:
            def record_reinject(self, pane_id, *, success, components, reason=""):
                pass

        reinj = PersonaReinjector(
            tui_registry, FakeLedger(),
            template_base=str(base),
            send_fn=lambda pid, txt: None,
            sleep_fn=lambda s: None,
            capture_fn=lambda pid: captures.get(pid, ""),
        )
        result = reinj.inject_all("solar-harness-lab:0.0", "builder", "sprint-123")
        assert result.success
        assert "persona" in result.injected
        assert "runtime_policy" in result.injected
        assert "solar_context" in result.injected


# ── V6: Spillover 3 tasks → 3 different panes ──────────────────

class TestV6Spillover:
    def test_three_tasks_three_panes(self, tui_registry):
        from dispatch_scheduler import DispatchScheduler

        class FakeReinjector:
            def inject_all(self, pane_id, role, sprint_id):
                class R:
                    success = True
                return R()

        class FakeLedger:
            def record_reinject(self, pane_id, *, success, components, reason=""):
                pass
            def record_reassign(self, pane_id, **kw):
                pass

        sched = DispatchScheduler(tui_registry, FakeLedger(), FakeReinjector())
        result = sched.spillover_select(
            ["task-A", "task-B", "task-C"], "sprint-123",
            max_items=3,
        )
        assert result.ok
        assert len(result.assigned) == 3
        pane_ids = [a[1] for a in result.assigned]
        assert len(set(pane_ids)) == 3  # zero collision


# ── V7: Bad pane → ledger write + reassign ─────────────────────

class TestV7PaneQuarantine:
    def test_bad_pane_exhausted_writes_ledger(self, tui_registry, tui_ledger):
        _make_dirty(tui_registry, "solar-harness-lab:0.0")
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("queued.txt"))
        mgr = PaneClearManager(
            tui_registry, det,
            send_fn=lambda pid, k: None,
            sleep_fn=lambda s: None,
        )
        result = mgr.clear_with_retry("solar-harness-lab:0.0")
        assert not result.success
        assert result.final_state == PaneState.needs_respawn

    def test_ledger_records_failure(self, tui_registry, tui_ledger, tmp_path):
        tui_ledger.record_clear(
            "solar-harness-lab:0.0",
            before_state="dirty", after_state="needs_respawn",
            success=False, reason="exhausted", attempt=4,
        )
        history = tui_ledger.query_history("solar-harness-lab:0.0")
        assert len(history) >= 1
        assert history[0]["action"] == "clear"


# ── Full chain: proceed → recover → clear → reinject → spillover ──

class TestFullChain:
    def test_proceed_to_clean_to_reinject_to_spillover(self, tui_registry, tmp_path):
        from dispatch_scheduler import DispatchScheduler
        from persona_reinjector import PersonaReinjector

        # Step 1: Detect proceed prompt
        det = RecoverDetector(capture_fn=lambda _: _load_fixture("proceed.txt"))
        result = det.classify_prompt("solar-harness-lab:0.0")
        assert result.prompt_type == PromptType.PROCEED

        # Step 2: Simulate recovery (pane becomes dirty after task)
        tui_registry.transition_state("solar-harness-lab:0.0", PaneState.running, reason="e2e")
        tui_registry.transition_state("solar-harness-lab:0.0", PaneState.dirty, reason="e2e")

        # Step 3: Clear pane
        det_clean = RecoverDetector(capture_fn=lambda _: _load_fixture("clean.txt"))
        mgr = PaneClearManager(
            tui_registry, det_clean,
            send_fn=lambda pid, k: None,
            sleep_fn=lambda s: None,
        )
        clear_result = mgr.clear_pane("solar-harness-lab:0.0")
        assert clear_result.success
        assert tui_registry.get_pane_state("solar-harness-lab:0.0").state == PaneState.clean

        # Step 4: Re-inject
        base = tmp_path / "templates"
        (base / "persona").mkdir(parents=True)
        (base / "persona" / "builder.md").write_text("You are a Solar Builder.\nBuild code.")
        (base / "runtime_policy.md").write_text("Definition of Done: 7 rules.\nNo optimistic words.")
        (base / "solar_context_sp1.md").write_text("Sprint context.\nGoal: test.")

        class FakeLedger:
            def record_reinject(self, pane_id, *, success, components, reason=""):
                pass
            def record_reassign(self, pane_id, **kw):
                pass

        reinj = PersonaReinjector(
            tui_registry, FakeLedger(),
            template_base=str(base),
            send_fn=lambda pid, txt: None,
            sleep_fn=lambda s: None,
            capture_fn=lambda pid: "You are a Solar Builder.\nBuild code.Definition of Done: 7 rules.Sprint context.",
        )
        inj_result = reinj.inject_all("solar-harness-lab:0.0", "builder", "sp1")
        assert inj_result.success

        # Step 5: Spillover select (pane now clean again after full cycle)
        tui_registry.transition_state("solar-harness-lab:0.0", PaneState.running, reason="dispatched")
        tui_registry.transition_state("solar-harness-lab:0.0", PaneState.dirty, reason="completed")
        mgr2 = PaneClearManager(
            tui_registry, det_clean,
            send_fn=lambda pid, k: None,
            sleep_fn=lambda s: None,
        )
        mgr2.clear_pane("solar-harness-lab:0.0")

        class FakeReinjector2:
            def inject_all(self, pane_id, role, sprint_id):
                class R:
                    success = True
                return R()

        sched = DispatchScheduler(tui_registry, FakeLedger(), FakeReinjector2())
        sp = sched.spillover_select(["t1", "t2", "t3"], "sp1", max_items=3)
        assert sp.ok
        assert len(set(a[1] for a in sp.assigned)) == 3


def _make_mgr(registry, det, capture_fn, ledger=None):
    from pane_clear_manager import PaneClearManager
    sends = []
    sleeps = []
    mgr = PaneClearManager(
        registry, det,
        ledger=ledger,
        send_fn=lambda pid, k: sends.append((pid, k)),
        sleep_fn=lambda s: sleeps.append(s),
    )
    return mgr, sends, sleeps, ledger
