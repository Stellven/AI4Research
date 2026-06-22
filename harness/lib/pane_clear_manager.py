"""PaneClearManager — /clear execution + three-signal verification + retry.

Per architecture.md §6.3, success = (empty prompt) AND (no queued) AND (no confirm).
Retry: 3 attempts with 5s/10s/15s backoff per OQ-02; 4th failure → needs_respawn.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from pane_constants import CLEAR_FAILED_EXHAUSTED
from pane_hygiene_registry import PaneHygieneRegistry, PaneState
from recover_detector import (
    DET_PROCEED,
    DET_QUEUED,
    DET_PERMISSION,
    DetectResult,
    PromptType,
    RecoverDetector,
)

PATTERN_EMPTY_PROMPT = re.compile(
    r'^\s*(?:[\$>]|❯(?:\s*$|\s+Try\s+")|›(?:\s*$|\s+(?!/).+))'
)
PASSIVE_PERMISSIONS_FOOTER_RE = re.compile(r"bypass permissions on", re.I)
PASSIVE_CODEX_PERMISSIONS_RE = re.compile(r"^\s*[│|]?\s*permissions:\s+YOLO mode\b", re.I)


def _pane_runtime() -> str:
    runtime = os.environ.get("SOLAR_PANE_RUNTIME", "claude").strip().lower()
    return runtime if runtime in {"claude", "codex"} else "claude"


def _clear_command() -> str:
    return "/new" if _pane_runtime() == "codex" else "/clear"


def _clear_wait_s(default: float) -> float:
    if _pane_runtime() != "codex":
        return default
    raw = os.environ.get("SOLAR_CODEX_CLEAR_WAIT_SEC", "5.0")
    try:
        return max(default, float(raw))
    except ValueError:
        return max(default, 5.0)


class ClearLedger(Protocol):
    """Minimal ledger interface for recording clear attempts."""

    def record_clear(
        self,
        pane_id: str,
        *,
        success: bool,
        attempt: int,
        reason: str = "",
    ) -> None: ...


@dataclass
class ClearResult:
    pane_id: str
    success: bool
    attempts: int
    final_state: PaneState
    signal_empty: bool = False
    signal_no_queued: bool = False
    signal_no_confirm: bool = False
    reason: str = ""
    ts: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tmux_send_keys(pane_id: str, keys: str, tmux_binary: str = "tmux") -> None:
    """Submit a slash command after removing any live prompt residue.

    Claude Code panes can retain an unsubmitted `/clear` or dispatch path in
    the editable prompt. Sending another `/clear` without clearing first turns
    that residue into a new malformed command and eventually marks a healthy
    pane as `needs_respawn`. Use the same literal-send discipline as graph
    dispatch: clear the input line, send the command as literal text, then
    submit it.
    """
    if _pane_runtime() == "codex":
        subprocess.run(
            [tmux_binary, "send-keys", "-t", pane_id, "C-c"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.2)
    subprocess.run(
        [tmux_binary, "send-keys", "-t", pane_id, "C-u"],
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        [tmux_binary, "send-keys", "-t", pane_id, "-l", keys],
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        [tmux_binary, "send-keys", "-t", pane_id, "Enter"],
        capture_output=True,
        timeout=5,
    )


class PaneClearManager:
    """Execute /clear on a dirty TUI pane and verify three-signal success."""

    MAX_RETRY: int = 3
    BACKOFF_BASE_S: float = 5.0
    WAIT_S: float = 1.0

    def __init__(
        self,
        registry: PaneHygieneRegistry,
        detector: RecoverDetector,
        ledger: Optional[ClearLedger] = None,
        *,
        send_fn: Optional[Callable[[str, str], None]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._registry = registry
        self._detector = detector
        self._ledger = ledger
        self._send = send_fn or _tmux_send_keys
        self._sleep = sleep_fn or time.sleep

    def clear_pane(self, pane_id: str) -> ClearResult:
        """Send '/clear' to pane and verify once.

        Raises ValueError if pane not in dirty state.
        """
        entry = self._registry.get_pane_state(pane_id)
        if entry.state != PaneState.dirty:
            raise ValueError(
                f"clear_pane requires dirty state, got {entry.state.value}"
            )

        self._send(pane_id, _clear_command())
        self._sleep(_clear_wait_s(self.WAIT_S))

        s_empty, s_no_queued, s_no_confirm = self.verify_clear_success(pane_id)
        success = s_empty and s_no_queued and s_no_confirm

        if success:
            self._registry.transition_state(
                pane_id, PaneState.clean, reason="clear_success", reset_fail=True
            )

        ts = _utc_now()
        if self._ledger:
            self._ledger.record_clear(
                pane_id, success=success, attempt=1,
                reason="ok" if success else "single_fail",
            )

        return ClearResult(
            pane_id=pane_id,
            success=success,
            attempts=1,
            final_state=PaneState.clean if success else entry.state,
            signal_empty=s_empty,
            signal_no_queued=s_no_queued,
            signal_no_confirm=s_no_confirm,
            reason="ok" if success else "single_fail",
            ts=ts,
        )

    def verify_clear_success(self, pane_id: str) -> tuple[bool, bool, bool]:
        """Check three-signal success criteria per architecture.md §6.3."""
        output = self._detector._capture(pane_id)
        lines = output.splitlines()
        window = lines[-12:] if lines else []
        last_empty_idx = -1
        for idx, line in enumerate(window):
            if PATTERN_EMPTY_PROMPT.match(line.strip()):
                last_empty_idx = idx

        signal_empty = last_empty_idx >= 0
        live_window = window[last_empty_idx:] if signal_empty else window

        signal_no_queued = not any(
            DET_QUEUED.search(line) for line in live_window
        )

        signal_no_confirm = not any(
            DET_PROCEED.search(line)
            or (
                DET_PERMISSION.search(line)
                and not PASSIVE_PERMISSIONS_FOOTER_RE.search(line)
                and not PASSIVE_CODEX_PERMISSIONS_RE.search(line)
            )
            for line in live_window
        )

        return signal_empty, signal_no_queued, signal_no_confirm

    def clear_with_retry(
        self,
        pane_id: str,
        *,
        max_retry: int = 3,
        backoff_base_s: float = 5.0,
    ) -> ClearResult:
        """Execute /clear with retry per OQ-02. 4th failure → needs_respawn."""
        entry = self._registry.get_pane_state(pane_id)
        if entry.state != PaneState.dirty:
            raise ValueError(
                f"clear_with_retry requires dirty state, got {entry.state.value}"
            )

        total_attempts = max_retry + 1
        s_empty = s_no_queued = s_no_confirm = False

        for attempt in range(1, total_attempts + 1):
            self._send(pane_id, _clear_command())
            self._sleep(_clear_wait_s(self.WAIT_S))

            s_empty, s_no_queued, s_no_confirm = self.verify_clear_success(pane_id)
            success = s_empty and s_no_queued and s_no_confirm

            if success:
                self._registry.transition_state(
                    pane_id, PaneState.clean,
                    reason="clear_retry_success", reset_fail=True,
                )
                if self._ledger:
                    self._ledger.record_clear(
                        pane_id, success=True, attempt=attempt,
                        reason="retry_ok",
                    )
                return ClearResult(
                    pane_id=pane_id,
                    success=True,
                    attempts=attempt,
                    final_state=PaneState.clean,
                    signal_empty=s_empty,
                    signal_no_queued=s_no_queued,
                    signal_no_confirm=s_no_confirm,
                    reason="retry_ok",
                    ts=_utc_now(),
                )

            if attempt <= max_retry:
                backoff = backoff_base_s * attempt  # 5, 10, 15
                if self._ledger:
                    self._ledger.record_clear(
                        pane_id, success=False, attempt=attempt,
                        reason="retry_backoff",
                    )
                self._sleep(backoff)

        # All retries exhausted → cooling → needs_recover → needs_respawn
        self._registry.transition_state(
            pane_id, PaneState.cooling,
            reason=CLEAR_FAILED_EXHAUSTED, increment_fail=True,
        )
        self._schedule_cooldown(pane_id, seconds=30)
        self._registry.transition_state(
            pane_id, PaneState.needs_recover,
            reason="clear_exhausted_cooldown",
        )
        self._registry.transition_state(
            pane_id, PaneState.needs_respawn,
            reason="clear_exhausted_to_respawn",
        )

        if self._ledger:
            self._ledger.record_clear(
                pane_id, success=False, attempt=total_attempts,
                reason="exhausted",
            )

        return ClearResult(
            pane_id=pane_id,
            success=False,
            attempts=total_attempts,
            final_state=PaneState.needs_respawn,
            signal_empty=s_empty,
            signal_no_queued=s_no_queued,
            signal_no_confirm=s_no_confirm,
            reason="exhausted",
            ts=_utc_now(),
        )

    def _schedule_cooldown(self, pane_id: str, *, seconds: int = 30) -> None:
        """Write cooldown_until to registry entry (does not change state)."""
        from datetime import timedelta

        entry = self._registry.get_pane_state(pane_id)
        cooldown_ts = (
            datetime.now(timezone.utc) + timedelta(seconds=seconds)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry.cooldown_until = cooldown_ts
        entry.cooldown_reason = CLEAR_FAILED_EXHAUSTED
        self._registry._persist()
