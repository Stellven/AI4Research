"""Tests for PaneClearManager — /clear execution + three-signal verification + retry."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from pane_constants import CLEAR_FAILED_EXHAUSTED
from pane_hygiene_registry import PaneEntry, PaneHygieneRegistry, PaneState
from pane_clear_manager import PaneClearManager, ClearResult, _tmux_send_keys

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "tmux_capture_samples"
CODEX_IDLE_CAPTURE = """
╭──────────────────────────────────────────────────────╮
│ >_ OpenAI Codex (v0.141.0)                           │
│                                                      │
│ permissions: YOLO mode                               │
╰──────────────────────────────────────────────────────╯

› Run /review on my current changes

  gpt-5.5 xhigh fast · /tmp/solar-codex-runtime-integration
"""
CODEX_SLASH_RESIDUE_CAPTURE = """
╭──────────────────────────────────────────────────────╮
│ >_ OpenAI Codex (v0.141.0)                           │
│ permissions: YOLO mode                               │
╰──────────────────────────────────────────────────────╯

› /clear

  gpt-5.5 xhigh fast · /tmp/solar-codex-runtime-integration
"""
CODEX_ROTATED_IDLE_CAPTURE = """
╭──────────────────────────────────────────────────────╮
│ >_ OpenAI Codex (v0.141.0)                           │
│ permissions: YOLO mode                               │
╰──────────────────────────────────────────────────────╯

  Tip: Use /side to start a side conversation in a temporary fork.

› Write tests for @filename

  gpt-5.5 xhigh fast · /tmp/solar-codex-runtime-integration
"""


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def _make_dirty(registry, pane_id="solar-harness:0.3"):
    """Transition pane to dirty via legal FSM path: clean -> running -> dirty."""
    registry.transition_state(pane_id, PaneState.running, reason="test_setup")
    registry.transition_state(pane_id, PaneState.dirty, reason="test_setup")


@pytest.fixture
def registry(tmp_path):
    r = PaneHygieneRegistry(str(tmp_path / "test-pane-hygiene.json"))
    r.register_pane("solar-harness:0.3", "evaluator", model="anthropic-opus")
    r.register_pane("solar-harness-lab:0.0", "builder", model="glm-5.1")
    return r


@pytest.fixture
def clean_capture():
    return lambda _: _load_fixture("clean.txt")


@pytest.fixture
def dirty_capture():
    return lambda _: _load_fixture("queued.txt")


@pytest.fixture
def proceed_capture():
    return lambda _: _load_fixture("proceed.txt")


@pytest.fixture
def permission_capture():
    return lambda _: _load_fixture("permission.txt")


def _make_manager(registry, capture_fn, sent=None, slept=None):
    from recover_detector import RecoverDetector
    det = RecoverDetector(capture_fn=capture_fn)
    sends = sent or []
    sleeps = slept or []
    mgr = PaneClearManager(
        registry, det,
        send_fn=lambda pid, k: sends.append((pid, k)),
        sleep_fn=lambda s: sleeps.append(s),
    )
    return mgr, sends, sleeps


# --- clear_pane single attempt ---

class TestClearPane:
    def test_success_on_clean(self, registry, clean_capture):
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, clean_capture)
        result = mgr.clear_pane("solar-harness:0.3")
        assert result.success
        assert result.attempts == 1
        assert result.signal_empty
        assert result.signal_no_queued
        assert result.signal_no_confirm
        assert sends == [("solar-harness:0.3", "/clear")]

    def test_codex_runtime_uses_new_thread_command(self, registry, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, lambda _: CODEX_IDLE_CAPTURE)
        result = mgr.clear_pane("solar-harness:0.3")
        assert result.success
        assert result.signal_empty
        assert result.signal_no_queued
        assert result.signal_no_confirm
        assert sends == [("solar-harness:0.3", "/new")]

    def test_fail_on_dirty(self, registry, dirty_capture):
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, dirty_capture)
        result = mgr.clear_pane("solar-harness:0.3")
        assert not result.success
        assert not result.signal_no_queued

    def test_fail_on_proceed(self, registry, proceed_capture):
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, proceed_capture)
        result = mgr.clear_pane("solar-harness:0.3")
        assert not result.success
        assert not result.signal_no_confirm

    def test_fail_on_permission(self, registry, permission_capture):
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, permission_capture)
        result = mgr.clear_pane("solar-harness:0.3")
        assert not result.success

    def test_raises_on_non_dirty(self, registry, clean_capture):
        mgr, _, _ = _make_manager(registry, clean_capture)
        with pytest.raises(ValueError, match="dirty"):
            mgr.clear_pane("solar-harness:0.3")

    def test_transitions_to_clean_on_success(self, registry, clean_capture):
        _make_dirty(registry)
        mgr, _, _ = _make_manager(registry, clean_capture)
        mgr.clear_pane("solar-harness:0.3")
        entry = registry.get_pane_state("solar-harness:0.3")
        assert entry.state == PaneState.clean

    def test_default_tmux_sender_clears_residue_and_sends_literal(self, monkeypatch):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)

            class Result:
                returncode = 0

            return Result()

        monkeypatch.setattr("pane_clear_manager.subprocess.run", fake_run)

        _tmux_send_keys("solar-harness-lab:0.3", "/clear")

        assert calls == [
            ["tmux", "send-keys", "-t", "solar-harness-lab:0.3", "C-u"],
            ["tmux", "send-keys", "-t", "solar-harness-lab:0.3", "-l", "/clear"],
            ["tmux", "send-keys", "-t", "solar-harness-lab:0.3", "Enter"],
        ]

    def test_codex_tmux_sender_does_not_cancel_clean_composer(self, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)

            class Result:
                returncode = 0
                stdout = CODEX_IDLE_CAPTURE

            return Result()

        monkeypatch.setattr("pane_clear_manager.subprocess.run", fake_run)
        monkeypatch.setattr("pane_clear_manager.time.sleep", lambda _: None)

        _tmux_send_keys("solar-harness:0.0", "/new")

        assert calls == [
            ["tmux", "capture-pane", "-pt", "solar-harness:0.0", "-S", "-30"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "C-u"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "-l", "/new"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "Enter"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "Enter"],
            ["tmux", "capture-pane", "-pt", "solar-harness:0.0", "-S", "-30"],
        ]

    def test_codex_tmux_sender_cancels_slash_completion_before_literal(self, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        calls = []
        captures = iter([CODEX_SLASH_RESIDUE_CAPTURE, CODEX_IDLE_CAPTURE])

        def fake_run(args, **kwargs):
            calls.append(args)

            class Result:
                returncode = 0
                stdout = (
                    next(captures, CODEX_IDLE_CAPTURE)
                    if args[:2] == ["tmux", "capture-pane"]
                    else ""
                )

            return Result()

        monkeypatch.setattr("pane_clear_manager.subprocess.run", fake_run)
        monkeypatch.setattr("pane_clear_manager.time.sleep", lambda _: None)

        _tmux_send_keys("solar-harness:0.0", "/new")

        assert calls == [
            ["tmux", "capture-pane", "-pt", "solar-harness:0.0", "-S", "-30"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "C-c"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "C-u"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "-l", "/new"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "Enter"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "Enter"],
            ["tmux", "capture-pane", "-pt", "solar-harness:0.0", "-S", "-30"],
        ]

    def test_codex_tmux_sender_resubmits_when_new_residue_persists(self, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        calls = []
        captures = iter([
            CODEX_IDLE_CAPTURE,
            CODEX_SLASH_RESIDUE_CAPTURE,
            CODEX_IDLE_CAPTURE,
        ])

        def fake_run(args, **kwargs):
            calls.append(args)

            class Result:
                returncode = 0
                stdout = (
                    next(captures, CODEX_IDLE_CAPTURE)
                    if args[:2] == ["tmux", "capture-pane"]
                    else ""
                )

            return Result()

        monkeypatch.setattr("pane_clear_manager.subprocess.run", fake_run)
        monkeypatch.setattr("pane_clear_manager.time.sleep", lambda _: None)

        _tmux_send_keys("solar-harness:0.0", "/new")

        assert calls == [
            ["tmux", "capture-pane", "-pt", "solar-harness:0.0", "-S", "-30"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "C-u"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "-l", "/new"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "Enter"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "Enter"],
            ["tmux", "capture-pane", "-pt", "solar-harness:0.0", "-S", "-30"],
            ["tmux", "send-keys", "-t", "solar-harness:0.0", "Enter"],
            ["tmux", "capture-pane", "-pt", "solar-harness:0.0", "-S", "-30"],
        ]


# --- verify_clear_success three-signal ---

class TestVerifyClearSuccess:
    def test_clean_pane_three_signals(self, registry, clean_capture):
        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=clean_capture)
        mgr = PaneClearManager(registry, det)
        s_empty, s_no_queued, s_no_confirm = mgr.verify_clear_success("test")
        assert s_empty
        assert s_no_queued
        assert s_no_confirm

    def test_queued_fails_no_queued_signal(self, registry, dirty_capture):
        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=dirty_capture)
        mgr = PaneClearManager(registry, det)
        _, s_no_queued, _ = mgr.verify_clear_success("test")
        assert not s_no_queued

    def test_proceed_fails_no_confirm_signal(self, registry, proceed_capture):
        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=proceed_capture)
        mgr = PaneClearManager(registry, det)
        _, _, s_no_confirm = mgr.verify_clear_success("test")
        assert not s_no_confirm

    def test_codex_idle_composer_is_clean(self, registry, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=lambda _: CODEX_IDLE_CAPTURE)
        mgr = PaneClearManager(registry, det)
        assert mgr.verify_clear_success("test") == (True, True, True)

    def test_codex_rotated_idle_composer_is_clean(self, registry, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=lambda _: CODEX_ROTATED_IDLE_CAPTURE)
        mgr = PaneClearManager(registry, det)
        assert mgr.verify_clear_success("test") == (True, True, True)

    def test_codex_slash_residue_is_not_empty_prompt(self, registry, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=lambda _: CODEX_SLASH_RESIDUE_CAPTURE)
        mgr = PaneClearManager(registry, det)
        s_empty, s_no_queued, s_no_confirm = mgr.verify_clear_success("test")
        assert not s_empty
        assert s_no_queued
        assert s_no_confirm


# --- clear_with_retry ---

class TestClearWithRetry:
    def test_succeeds_first_try(self, registry, clean_capture):
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, clean_capture)
        result = mgr.clear_with_retry("solar-harness:0.3")
        assert result.success
        assert result.attempts == 1
        assert sends == [("solar-harness:0.3", "/clear")]

    def test_codex_clear_with_retry_uses_new_thread_command(self, registry, monkeypatch):
        monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, lambda _: CODEX_IDLE_CAPTURE)
        result = mgr.clear_with_retry("solar-harness:0.3")
        assert result.success
        assert result.attempts == 1
        assert sends == [("solar-harness:0.3", "/new")]

    def test_succeeds_second_try(self, registry):
        _make_dirty(registry)
        dirty_then_clean = iter([
            _load_fixture("queued.txt"),
            _load_fixture("clean.txt"),
        ])
        capture_fn = lambda _: next(dirty_then_clean)
        mgr, sends, sleeps = _make_manager(registry, capture_fn)
        result = mgr.clear_with_retry("solar-harness:0.3")
        assert result.success
        assert result.attempts == 2
        assert len(sends) == 2
        assert sleeps == [1.0, 5.0, 1.0]  # WAIT_S + backoff(5*1) + WAIT_S

    def test_exhausted_transitions_to_needs_respawn(self, registry, dirty_capture):
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, dirty_capture)
        result = mgr.clear_with_retry("solar-harness:0.3")
        assert not result.success
        assert result.reason == "exhausted"
        assert result.final_state == PaneState.needs_respawn
        assert len(sends) == 4

    def test_backoff_values(self, registry, dirty_capture):
        _make_dirty(registry)
        mgr, sends, sleeps = _make_manager(registry, dirty_capture)
        mgr.clear_with_retry("solar-harness:0.3")
        # Pattern: WAIT_S(1.0) before verify, backoff after fail
        assert sleeps == [1.0, 5.0, 1.0, 10.0, 1.0, 15.0, 1.0]

    def test_raises_on_non_dirty(self, registry, clean_capture):
        mgr, _, _ = _make_manager(registry, clean_capture)
        with pytest.raises(ValueError, match="dirty"):
            mgr.clear_with_retry("solar-harness:0.3")

    def test_no_cooling_to_running_direct(self, registry, dirty_capture):
        """AC: no cooling->running direct transition."""
        _make_dirty(registry)
        mgr, _, _ = _make_manager(registry, dirty_capture)
        mgr.clear_with_retry("solar-harness:0.3")
        entry = registry.get_pane_state("solar-harness:0.3")
        assert entry.state == PaneState.needs_respawn
        assert entry.state != PaneState.running


# --- Ledger recording ---

class TestLedger:
    def test_ledger_records_success(self, registry, clean_capture):
        _make_dirty(registry)
        records = []

        class FakeLedger:
            def record_clear(self, pane_id, *, success, attempt, reason=""):
                records.append({"pane_id": pane_id, "success": success,
                                "attempt": attempt, "reason": reason})

        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=clean_capture)
        mgr = PaneClearManager(registry, det, ledger=FakeLedger())
        mgr.clear_pane("solar-harness:0.3")
        assert len(records) == 1
        assert records[0]["success"] is True
        assert records[0]["attempt"] == 1

    def test_ledger_records_retry_exhausted(self, registry, dirty_capture):
        _make_dirty(registry)
        records = []

        class FakeLedger:
            def record_clear(self, pane_id, *, success, attempt, reason=""):
                records.append({"attempt": attempt, "reason": reason})

        from recover_detector import RecoverDetector
        det = RecoverDetector(capture_fn=dirty_capture)
        mgr = PaneClearManager(registry, det, ledger=FakeLedger())
        mgr.clear_with_retry("solar-harness:0.3")
        assert len(records) == 4
        assert records[-1]["reason"] == "exhausted"
