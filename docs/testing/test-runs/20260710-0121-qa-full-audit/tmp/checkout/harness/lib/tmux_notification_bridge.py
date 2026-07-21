#!/usr/bin/env python3
"""Best-effort tmux notification bridge for pane titles, bells, and OSC."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import Optional

_TITLE_MARKER_RE = re.compile(r"\s*\|\s*提醒:[A-Z_]+\s*$")
_BELL_STATES = {
    "completed",
    "failed",
    "failed_missing_handoff",
    "failed_stale_handoff",
    "error",
    "auth_expired",
    "quota_exhausted",
    "cooldown",
    "deferred",
    "draining",
}


def state_marker(state: str) -> str:
    value = str(state or "").strip().lower()
    if value in {"running"}:
        return "RUN"
    if value in {"ready", "idle", "completed"}:
        return "OK"
    if value in {"cooldown", "deferred", "draining"}:
        return "WAIT"
    if value in {"failed", "failed_missing_handoff", "failed_stale_handoff", "error", "auth_expired", "quota_exhausted"}:
        return "ERR"
    return value.upper()[:12] or "INFO"


def decorate_title(title: str, state: str) -> str:
    base = _TITLE_MARKER_RE.sub("", str(title or "")).strip()
    marker = state_marker(state)
    return f"{base} | 提醒:{marker}" if base else f"提醒:{marker}"


def _run_tmux(args: list[str]) -> bool:
    if not os.environ.get("TMUX"):
        return False
    try:
        proc = subprocess.run(["tmux"] + args, check=False, capture_output=True)
        return proc.returncode == 0
    except Exception:
        return False


def _apply_pane_title(title: str, pane_id: Optional[str] = None) -> None:
    if not os.environ.get("TMUX"):
        return
    target_args: list[str] = []
    if pane_id:
        target_args = ["-t", pane_id]
    try:
        subprocess.run(
            ["tmux", "select-pane"] + target_args + ["-T", title],
            check=False,
            capture_output=True,
        )
    except Exception:
        return


def _allow_osc_passthrough() -> bool:
    if os.environ.get("SOLAR_TMUX_NOTIFY_OSC_PASSTHROUGH", "0") != "1":
        return False
    if not os.environ.get("TMUX") or not sys.stdout.isatty():
        return False
    try:
        proc = subprocess.run(
            ["tmux", "show-options", "-gv", "allow-passthrough"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False
    return proc.returncode == 0 and proc.stdout.strip().lower() == "on"


def _osc_sequence(message: str) -> str:
    kind = str(os.environ.get("SOLAR_TMUX_NOTIFY_OSC_KIND", "777") or "777").strip()
    safe = str(message or "").replace("\a", " ").replace("\x1b", " ")
    if kind == "9":
        inner = f"\033]9;{safe}\a"
    elif kind == "99":
        inner = f"\033]99;{safe}\a"
    else:
        inner = f"\033]777;notify;Solar Harness;{safe}\a"
    return f"\033Ptmux;\033{inner.replace(chr(27), chr(27) * 2)}\033\\"


def emit_osc_notification(message: str) -> bool:
    if not _allow_osc_passthrough():
        return False
    try:
        sys.stdout.write(_osc_sequence(message))
        sys.stdout.flush()
        return True
    except Exception:
        return False


def notify_tmux_state(
    title: str,
    *,
    state: str,
    pane_id: Optional[str] = None,
    message: str = "",
) -> str:
    decorated = decorate_title(title, state)
    _apply_pane_title(decorated, pane_id=pane_id)

    target_args: list[str] = []
    if pane_id:
        target_args = ["-t", pane_id]
    _run_tmux(["set-window-option", "-q"] + target_args + ["monitor-activity", "on"])
    _run_tmux(["set-window-option", "-q"] + target_args + ["monitor-bell", "on"])

    state_value = str(state or "").strip().lower()
    if state_value in _BELL_STATES:
        display = str(message or f"Solar Harness state={state_value}")
        _run_tmux(["display-message"] + target_args + [display])
        _run_tmux(["run-shell", "-b", "printf '\\a' >/dev/tty 2>/dev/null || true"])
        emit_osc_notification(display)
    return decorated


def _cmd_notify(args: argparse.Namespace) -> int:
    notify_tmux_state(
        args.title,
        state=args.state,
        pane_id=args.pane_id or os.environ.get("TMUX_PANE"),
        message=args.message or "",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tmux_notification_bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_notify = sub.add_parser("notify", help="Apply title marker and emit best-effort tmux notifications.")
    p_notify.add_argument("--title", required=True)
    p_notify.add_argument("--state", required=True)
    p_notify.add_argument("--pane-id", default="")
    p_notify.add_argument("--message", default="")
    p_notify.set_defaults(func=_cmd_notify)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
