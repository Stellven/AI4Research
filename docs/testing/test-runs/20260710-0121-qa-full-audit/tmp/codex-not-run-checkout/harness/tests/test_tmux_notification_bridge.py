#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import tmux_notification_bridge as bridge


def test_decorate_title_replaces_old_marker():
    title = bridge.decorate_title(
        "MT builder/demo | 模型:sonnet | provider:anthropic | 状态:running | 提醒:ERR",
        "running",
    )
    assert title.endswith("| 提醒:RUN")
    assert title.count("提醒:") == 1


def test_notify_tmux_state_emits_tmux_commands(monkeypatch):
    calls: list[list[str]] = []
    titles: list[tuple[str, str | None]] = []

    def _fake_run(cmd, check=False, capture_output=False, text=False):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n" if text else b"ok\n", stderr="" if text else b"")

    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,123,0")
    monkeypatch.setattr(bridge, "_apply_pane_title", lambda title, pane_id=None: titles.append((title, pane_id)))
    monkeypatch.setattr(bridge.subprocess, "run", _fake_run)

    decorated = bridge.notify_tmux_state(
        "MT builder/demo | 状态:failed",
        state="failed",
        pane_id="%3",
        message="multi-task failed: N1",
    )

    assert decorated.endswith("| 提醒:ERR")
    assert titles == [(decorated, "%3")]
    assert any(cmd[:4] == ["tmux", "set-window-option", "-q", "-t"] and "monitor-activity" in cmd for cmd in calls)
    assert any(cmd[:4] == ["tmux", "set-window-option", "-q", "-t"] and "monitor-bell" in cmd for cmd in calls)
    assert any(cmd[:3] == ["tmux", "display-message", "-t"] for cmd in calls)
    assert any(cmd[:3] == ["tmux", "run-shell", "-b"] for cmd in calls)


def test_emit_osc_notification_requires_opt_in(monkeypatch):
    monkeypatch.delenv("SOLAR_TMUX_NOTIFY_OSC_PASSTHROUGH", raising=False)
    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,123,0")
    assert bridge.emit_osc_notification("hello") is False
